"""Durable, anonymous progress with explicit plan confirmation.

Each operation reads and updates the latest state inside one SQLite transaction.
The cookie itself is never stored: only its SHA-256 digest identifies a record.
"""

from contextlib import closing, contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time


TTL_SECONDS = 30 * 24 * 60 * 60
HISTORY_LIMIT = 20  # Messages, i.e. the last ten user/assistant exchanges.
SAVED_LIMIT = 50


def _default_state():
    return {
        'history': [],
        'journey': {
            'goal': '', 'minutes': 15, 'phase': 'explore',
            'draft': None, 'plan': None,
        },
        'saved_nodes': [],
    }


def _text(value, name, limit, *, optional=False):
    if not isinstance(value, str):
        raise ValueError(f'{name} debe ser texto')
    value = value.strip()
    if (not optional and not value) or len(value) > limit:
        raise ValueError(f'{name} debe tener entre {0 if optional else 1} y {limit} caracteres')
    return value


def _key(session_id):
    if not isinstance(session_id, str) or not 1 <= len(session_id) <= 512:
        raise ValueError('Sesión no válida')
    return hashlib.sha256(session_id.encode('utf-8')).hexdigest()


def _id(prefix):
    return prefix + '_' + secrets.token_hex(12)


class JourneyStore:
    """File-backed state store. Public methods return detached JSON-safe state."""

    def __init__(self, db_path, node_ids):
        self.path = Path(db_path)
        if str(db_path) == ':memory:':
            raise ValueError('El progreso requiere una base de datos persistente')
        self.node_ids = frozenset(node_ids)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS journeys (
                session_hash TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )''')
            db.execute('CREATE INDEX IF NOT EXISTS journeys_expiry ON journeys(expires_at)')
            db.commit()

    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=15)
        db.execute('PRAGMA busy_timeout=15000')
        return db

    @contextmanager
    def _transaction(self, session_id):
        key = _key(session_id)
        now = int(time.time())
        db = self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM journeys WHERE expires_at <= ?', (now,))
            row = db.execute('SELECT state FROM journeys WHERE session_hash = ?', (key,)).fetchone()
            state = json.loads(row[0]) if row else _default_state()
            yield state
            serialized = json.dumps(state, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            db.execute('''INSERT INTO journeys(session_hash,state,updated_at,expires_at)
                VALUES (?,?,?,?) ON CONFLICT(session_hash) DO UPDATE SET
                state=excluded.state,updated_at=excluded.updated_at,expires_at=excluded.expires_at''',
                (key, serialized, now, now + TTL_SECONDS))
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, session_id):
        """Read or initialize this session, refreshing its 30-day retention."""
        with self._transaction(session_id) as state:
            result = deepcopy(state)
        return result

    def append_turn(self, session_id, user_text, response):
        user_text = _text(user_text, 'Mensaje', 2000)
        if not isinstance(response, dict):
            raise ValueError('Respuesta no válida')
        answer = _text(response.get('answer'), 'Respuesta', 16000)
        try:
            serialized = json.dumps(response, ensure_ascii=False, allow_nan=False)
            if len(serialized.encode('utf-8')) > 65536:
                raise ValueError('Respuesta demasiado grande')
            safe_response = json.loads(serialized)
        except (TypeError, OverflowError, RecursionError) as exc:
            raise ValueError('Respuesta no válida') from exc
        with self._transaction(session_id) as state:
            state['history'] = (state['history'] + [
                {'role': 'user', 'content': user_text},
                {'role': 'assistant', 'content': answer, 'response': safe_response},
            ])[-HISTORY_LIMIT:]
            result = deepcopy(state)
        return result

    def propose(self, session_id, proposal, minutes, evidence_node_ids):
        """Save a grounded draft; only apply(confirm_plan) makes it actionable."""
        if type(minutes) is not int or minutes not in (5, 15, 30):
            raise ValueError('Elige sesiones de 5, 15 o 30 minutos')
        if not isinstance(proposal, dict):
            raise ValueError('Plan no válido')
        goal = _text(proposal.get('goal'), 'Propósito', 500)
        missions = proposal.get('missions')
        if not isinstance(missions, list) or len(missions) != 3:
            raise ValueError('El plan debe contener exactamente tres mini misiones')
        if not isinstance(evidence_node_ids, (list, tuple, set, frozenset)) or any(
            not isinstance(node_id, str) for node_id in evidence_node_ids
        ):
            raise ValueError('Evidencia no válida')
        allowed = self.node_ids.intersection(evidence_node_ids)
        clean_missions = []
        titles, actions = set(), set()
        now = int(time.time())
        for item in missions:
            if not isinstance(item, dict):
                raise ValueError('Misión no válida')
            mission = {
                'id': _id('mission'),
                'title': _text(item.get('title'), 'Título', 140),
                'action': _text(item.get('action'), 'Acción', 1200),
                'deliverable': _text(item.get('deliverable'), 'Entregable', 700),
                'done_when': _text(item.get('done_when'), 'Criterio de finalización', 700),
            }
            title_key = ' '.join(mission['title'].casefold().split())
            action_key = ' '.join(mission['action'].casefold().split())
            if title_key in titles or action_key in actions:
                raise ValueError('Las mini misiones deben ser distintas')
            titles.add(title_key)
            actions.add(action_key)
            duration = item.get('minutes')
            if type(duration) is not int or not 1 <= duration <= minutes:
                raise ValueError(f'Cada misión debe durar entre 1 y {minutes} minutos; reduce su alcance')
            mission['minutes'] = duration
            node_ids = item.get('node_ids')
            if not isinstance(node_ids, list) or len(node_ids) > 3:
                raise ValueError('Cada misión admite hasta tres nodos de apoyo')
            if any(not isinstance(node_id, str) or node_id not in allowed for node_id in node_ids):
                raise ValueError('La misión contiene un nodo sin evidencia disponible')
            if len(set(node_ids)) != len(node_ids):
                raise ValueError('La misión contiene nodos duplicados')
            mission.update({
                'node_ids': list(node_ids), 'status': 'pending', 'artifact': '',
                'created_by': 'Skool Guide',
                'completion_kind': None, 'completed_at': None, 'updated_at': now,
            })
            clean_missions.append(mission)
        draft = {
            'id': _id('draft'), 'goal': goal, 'minutes': minutes,
            'missions': clean_missions, 'created_at': now,
        }
        with self._transaction(session_id) as state:
            journey = state['journey']
            journey['draft'] = draft
            if journey['plan'] is None:
                journey.update({'goal': goal, 'minutes': minutes, 'phase': 'draft'})
            result = deepcopy(state)
        return result

    def _node(self, value):
        if not isinstance(value, str) or value not in self.node_ids:
            raise ValueError('Nodo no válido')
        return value

    def apply(self, session_id, body):
        """Apply one explicit user action without accepting arbitrary state."""
        if not isinstance(body, dict) or not isinstance(body.get('action'), str):
            raise ValueError('Acción no válida')
        action = body['action']
        if action not in {'confirm_plan', 'discard_draft', 'mission_update', 'pause', 'resume',
                          'save_node', 'remove_saved_node', 'reset'}:
            raise ValueError('Acción no válida')
        with self._transaction(session_id) as state:
            journey = state['journey']
            now = int(time.time())
            if action == 'reset':
                state.clear()
                state.update(_default_state())
            elif action in ('save_node', 'remove_saved_node'):
                node_id = self._node(body.get('node_id'))
                saved = state['saved_nodes']
                if action == 'save_node' and node_id not in saved:
                    if len(saved) >= SAVED_LIMIT:
                        raise ValueError('Puedes guardar hasta 50 recursos')
                    saved.append(node_id)
                elif action == 'remove_saved_node' and node_id in saved:
                    saved.remove(node_id)
            elif action == 'confirm_plan':
                draft = journey['draft']
                if not draft or body.get('draft_id') != draft['id']:
                    raise LookupError('El borrador cambió; revisa el plan antes de confirmarlo')
                plan = deepcopy(draft)
                plan.update({'id': _id('plan'), 'draft_id': draft['id'],
                             'status': 'active', 'confirmed_at': now})
                plan['missions'][0]['status'] = 'active'
                journey.update({'goal': plan['goal'], 'minutes': plan['minutes'],
                                'phase': 'active', 'draft': None, 'plan': plan})
            elif action == 'discard_draft':
                draft = journey['draft']
                # The optional ID protects UI actions from discarding a newer
                # proposal created by another tab. Omitting it is idempotent.
                if 'draft_id' in body and (not draft or body['draft_id'] != draft['id']):
                    raise LookupError('El borrador cambió; vuelve a revisarlo')
                journey['draft'] = None
                if journey['plan'] is not None:
                    plan = journey['plan']
                    journey.update({'goal': plan['goal'], 'minutes': plan['minutes'], 'phase': plan['status']})
                else:
                    journey['phase'] = 'explore'
            else:
                plan = journey['plan']
                if not plan:
                    raise LookupError('Confirma primero un plan')
                if action in ('pause', 'resume'):
                    if plan['status'] == 'completed':
                        raise ValueError('El plan ya está completado')
                    plan['status'] = 'paused' if action == 'pause' else 'active'
                    journey['phase'] = plan['status']
                else:
                    self._update_mission(journey, body, now)
            result = deepcopy(state)
        return result

    @staticmethod
    def _update_mission(journey, body, now):
        plan = journey['plan']
        mission = next((item for item in plan['missions'] if item['id'] == body.get('mission_id')), None)
        if mission is None:
            raise LookupError('Misión no encontrada')
        status = body.get('status')
        if status not in ('completed', 'blocked', 'active'):
            raise ValueError('Estado de misión no válido')
        if plan['status'] == 'paused':
            raise ValueError('Retoma el plan antes de actualizar una misión')
        if 'artifact' in body:
            mission['artifact'] = _text(body['artifact'], 'Entregable', 3000, optional=True)
        if status == 'active':
            for other in plan['missions']:
                if other['id'] != mission['id'] and other['status'] == 'active':
                    other.update({'status': 'pending', 'updated_at': now})
        mission.update({'status': status, 'updated_at': now})
        if status == 'completed':
            mission['completion_kind'] = 'self_reported'
            mission['completed_at'] = now
            if not any(item['status'] == 'active' for item in plan['missions']):
                next_mission = next((item for item in plan['missions'] if item['status'] == 'pending'), None)
                if next_mission:
                    next_mission.update({'status': 'active', 'updated_at': now})
        else:
            mission['completion_kind'] = None
            mission['completed_at'] = None
        if all(item['status'] == 'completed' for item in plan['missions']):
            plan['status'] = 'completed'
            journey['phase'] = 'completed'
        else:
            plan['status'] = 'active'
            journey['phase'] = 'active'

"""Persistent coaching boundary; public clients never access Hermes directly."""
from contextlib import closing
import hashlib
import json
import os
import re
import secrets
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlsplit, parse_qs
from retrieval import Library
from resources import ResourceCatalogue
from journey import JourneyStore
from coaching import COACH, PLAN, PLANNER, clean_question

HERE = Path(__file__).parent
COOKIE_AGE = 30 * 86400


class ProviderBillingError(RuntimeError):
    """A provider account condition, not malformed model output to retry."""


def parse(text):
    if text.startswith('Billing or credits exhausted:'):
        raise ProviderBillingError('Hermes provider requires billing attention')
    start, end = text.find('{'), text.rfind('}')
    obj = json.loads(text[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError('Invalid response')
    return obj


def hermes(system, payload):
    request = json.dumps({'system': system, 'message': json.dumps(payload, ensure_ascii=False)}, ensure_ascii=False)
    worker = subprocess.Popen([os.environ.get('HERMES_PYTHON', sys.executable), str(HERE / 'hermes_worker.py')],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, start_new_session=True)
    try:
        stdout, stderr = worker.communicate(request, timeout=60)
    except subprocess.TimeoutExpired:
        os.killpg(worker.pid, signal.SIGKILL)
        worker.communicate()
        raise TimeoutError('Hermes timeout')
    marker = 'BRAINVIEW_RESULT:'
    if worker.returncode or marker not in stdout:
        # Do not log model output or provider details containing user data.
        print('Hermes worker failed:', worker.returncode, file=sys.stderr, flush=True)
        raise RuntimeError('Hermes unavailable')
    return parse(json.loads(stdout.rsplit(marker, 1)[1])['text'])


class GuideApp:
    def __init__(self, library, store, budget_db, origin, model=hermes):
        self.library, self.store, self.origin, self.model = library, store, origin, model
        self.resources = ResourceCatalogue(library)
        self.budget_db = str(budget_db)
        self.slots = threading.BoundedSemaphore(2)
        self.lock = threading.Lock()
        self.busy = set()
        with closing(sqlite3.connect(self.budget_db)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS budget (key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL)')
            # Upgrade the original two-column quota table, preserving existing usage.
            if 'expires' not in {x[1] for x in db.execute('PRAGMA table_info(budget)')}:
                db.execute('ALTER TABLE budget ADD COLUMN expires INTEGER NOT NULL DEFAULT 0')
                db.execute('UPDATE budget SET expires=?', (int(time.time()) + 86400,))

    def reserve(self, ip, model=True):
        now = int(time.time())
        fingerprint = hashlib.sha256(ip.encode()).hexdigest()[:24]
        keys = [(f'write:{fingerprint}:{now // 60}', 45, now + 120)]
        if model:
            keys += [(f'day:{now // 86400}', 200, (now // 86400 + 1) * 86400),
                     (f'ip:{fingerprint}:{now // 60}', 5, now + 120)]
        with closing(sqlite3.connect(self.budget_db, timeout=10)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM budget WHERE expires < ?', (now,))
            for key, limit, _ in keys:
                row = db.execute('SELECT count FROM budget WHERE key=?', (key,)).fetchone()
                if row and row[0] >= limit:
                    return False
            for key, _, expiry in keys:
                db.execute('INSERT INTO budget VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (key, expiry))
        return True

    def acquire(self, sid):
        with self.lock:
            if sid in self.busy:
                return False
            self.busy.add(sid)
            return True

    def release(self, sid):
        with self.lock:
            self.busy.discard(sid)

    def reply_to_chat(self, sid, body, emit):
        lib = self.library
        repairs_left = 1

        def complete(system, request, validate=lambda result: result):
            nonlocal repairs_left
            while True:
                try:
                    return validate(self.model(system, request))
                except ValueError as exc:
                    # One repair across the entire turn keeps the total bound
                    # at three 60-second workers, below the client deadline.
                    print('Guide response validation:', type(exc).__name__, file=sys.stderr, flush=True)
                    if not repairs_left:
                        raise
                    repairs_left -= 1
                    request = {**request, 'validation_feedback': str(exc)[:300]}
                    emit('status', {'message': 'Ajustando la respuesta para que llegue completa…'})

        def validate_answer(result):
            validated = lib.validate(result, evidence)
            if not validated['answer'].strip():
                raise ValueError('Incluye una respuesta breve en el campo answer del JSON.')
            return validated

        message = body.get('message', '').strip()
        state = self.store.get(sid)
        current = body.get('node_id')
        current = current if isinstance(current, str) and current in lib.nodes else None
        history = [{'role': turn['role'], 'content': turn['content']} for turn in state['history'][-10:]]
        payload = {'question': message, 'current_node': current, 'history': history, 'journey': state['journey']}
        emit('status', {'message': 'Buscando el contenido que encaja contigo…'})
        planner = complete(PLANNER, {**payload, 'catalogue': lib.catalogue()})
        candidates = planner.get('node_ids', [])
        if not isinstance(candidates, list):
            candidates = []
        picked = [x for x in candidates if isinstance(x, str) and x in lib.nodes][:3]
        if current and current not in picked:
            picked.append(current)
        evidence = lib.search(message + ' ' + str(planner.get('query', ''))[:1500], picked)
        for item in evidence:
            item['text'] = item['text'][:4500]
        payload['evidence'] = evidence
        action = body.get('action')
        if action == 'generate_plan':
            minutes = body.get('minutes', 15)
            if type(minutes) is not int or minutes not in (5, 15, 30):
                raise ValueError('Elige 5, 15 o 30 minutos.')
            emit('status', {'message': 'Preparando tres mini misiones para que las revises…'})
            payload['available_minutes'] = minutes
            def validate_plan(result):
                validated = validate_answer(result)
                # Validate the complete response before persisting any draft.
                self.store.propose(sid, result.get('proposal'), minutes, [e['node_id'] for e in evidence])
                return validated
            validated = complete(PLAN, payload, validate_plan)
            validated['question'] = None
        else:
            emit('status', {'message': 'Preparando tu siguiente paso y sus fuentes…'})
            def validate_coach(result):
                validated = validate_answer(result)
                validated['question'] = clean_question(result.get('question'))
                return validated
            validated = complete(COACH, payload, validate_coach)
            validated['recommendations'] = validated['recommendations'][:2]
        if not validated['answer'].strip():
            raise ValueError('No se recibió una respuesta completa. Inténtalo de nuevo.')
        for card in validated['recommendations']:
            card['resources'] = self.resources.get(card['node_id']).get('resources', [])
        state = self.store.append_turn(sid, message, validated)
        return {**validated, 'journey': state['journey'], 'saved_nodes': state['saved_nodes']}


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def headers_out(self, code, kind='application/json', length=None, cookie=None):
            self.send_response(code)
            if code >= 400:
                self.close_connection = True
                self.send_header('Connection', 'close')
            self.send_header('Content-Type', kind)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Access-Control-Allow-Origin', app.origin)
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Vary', 'Origin')
            if length is not None:
                self.send_header('Content-Length', str(length))
            if cookie:
                self.send_header('Set-Cookie', f'guide_session={cookie}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age={COOKIE_AGE}')
            self.end_headers()

        def reply(self, code, data, cookie=None):
            raw = json.dumps(data, ensure_ascii=False).encode()
            self.headers_out(code, length=len(raw), cookie=cookie)
            self.wfile.write(raw)

        def session(self):
            try:
                cookies = SimpleCookie()
                cookies.load(self.headers.get('Cookie', ''))
                sid = cookies['guide_session'].value if 'guide_session' in cookies else ''
            except Exception:
                sid = ''
            return sid if re.fullmatch(r'[A-Za-z0-9_-]{43}', sid) else secrets.token_urlsafe(32)

        def allowed(self):
            return self.headers.get('Origin') == app.origin

        def do_OPTIONS(self):
            if not self.allowed():
                return self.reply(403, {'error': 'Origen no permitido'})
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', app.origin)
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == '/health':
                return self.reply(200, {'status': 'ok', 'library_version': app.library.version, 'nodes': len(app.library.nodes), 'coaching': True})
            if not self.allowed():
                return self.reply(403, {'error': 'Origen no permitido'})
            if url.path == '/state':
                sid = self.session()
                state = app.store.get(sid)
                return self.reply(200, {**state, 'library_version': app.library.version}, cookie=sid)
            if url.path == '/resources':
                node_id = parse_qs(url.query).get('node_id', [''])[0]
                if node_id not in app.library.nodes:
                    return self.reply(404, {'error': 'Nodo no encontrado'})
                return self.reply(200, app.resources.get(node_id))
            self.reply(404, {'error': 'No encontrado'})

        def event(self, kind, data):
            self.wfile.write(('event: ' + kind + '\ndata: ' + json.dumps(data, ensure_ascii=False) + '\n\n').encode())
            self.wfile.flush()

        def do_POST(self):
            if self.path not in ('/chat', '/journey'):
                return self.reply(404, {'error': 'No encontrado'})
            if not self.allowed():
                return self.reply(403, {'error': 'Origen no permitido'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8192:
                    return self.reply(413, {'error': 'Mensaje demasiado largo'})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError()
                if self.path == '/chat':
                    message = body.get('message', '')
                    if not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
                        raise ValueError()
                    if body.get('action') not in (None, 'generate_plan'):
                        raise ValueError()
                    if body.get('action') == 'generate_plan' and (type(body.get('minutes', 15)) is not int or body.get('minutes', 15) not in (5, 15, 30)):
                        raise ValueError()
            except Exception:
                return self.reply(400, {'error': 'Revisa el mensaje y los datos enviados.'})
            sid = self.session()
            if not app.acquire(sid):
                return self.reply(409, {'error': 'Espera a que termine tu solicitud anterior.'})
            slot = False
            started = False
            try:
                if not app.reserve(self.headers.get('X-Real-IP', self.client_address[0]), model=self.path == '/chat'):
                    return self.reply(429, {'error': 'Se alcanzó el límite de consultas. Inténtalo más tarde.'})
                if self.path == '/journey':
                    return self.reply(200, app.store.apply(sid, body), cookie=sid)
                slot = app.slots.acquire(blocking=False)
                if not slot:
                    return self.reply(429, {'error': 'Estoy atendiendo otras consultas. Intenta de nuevo en un momento.'})
                self.headers_out(200, 'text/event-stream; charset=utf-8', cookie=sid)
                self.close_connection = True
                started = True
                self.event('result', app.reply_to_chat(sid, body, self.event))
            except (BrokenPipeError, ConnectionResetError):
                pass
            except ProviderBillingError:
                print('Hermes provider billing unavailable', file=sys.stderr, flush=True)
                message = 'El guía no puede generar nuevas respuestas por el momento. Tu progreso sigue guardado; puedes explorar el mapa y los recursos.'
                if started:
                    self.event('error', {'message': message})
                else:
                    self.reply(503, {'error': message})
            except (ValueError, LookupError) as exc:
                message = str(exc) if self.path == '/journey' else 'No pude preparar una respuesta completa. Tu avance sigue guardado; intenta de nuevo.'
                if started:
                    self.event('error', {'message': message})
                else:
                    self.reply(400, {'error': message})
            except Exception as exc:
                print(type(exc).__name__, file=sys.stderr, flush=True)
                if started:
                    try:
                        self.event('error', {'message': 'No pude completar la consulta. Puedes seguir explorando el mapa y retomar tu avance.'})
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                else:
                    self.reply(503, {'error': 'No pude guardar el cambio. Inténtalo de nuevo.'})
            finally:
                if slot:
                    app.slots.release()
                app.release(sid)
    return Handler


if __name__ == '__main__':
    library = Library(os.environ['BRAIN_LIBRARY'])
    store = JourneyStore(os.environ.get('GUIDE_JOURNEY_DB', '/var/lib/skool-guide/journey.sqlite'), library.nodes)
    app = GuideApp(library, store, os.environ.get('GUIDE_BUDGET_DB', '/var/lib/skool-guide/budget.sqlite'), os.environ.get('GUIDE_ORIGIN', 'https://brainskool.softvibes.art'))
    ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('PORT', '4651'))), handler_for(app)).serve_forever()

import concurrent.futures
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/skool-guide'))
from journey import JourneyStore, HISTORY_LIMIT


class JourneyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'progress.sqlite'
        self.store = JourneyStore(self.path, ['marketing:1', 'oferta:2', 'ventas:3'])
        self.session = 'opaque-cookie-that-must-not-be-stored'
        self.proposal = {
            'goal': 'Conseguir consultas más calificadas',
            'missions': [{
                'title': f'Paso {i}', 'action': f'Escribe tu mensaje {i}',
                'deliverable': 'Una frase', 'done_when': 'La frase identifica un cliente y resultado',
                'minutes': 5 + i, 'node_ids': ['marketing:1'],
            } for i in range(3)],
        }

    def tearDown(self):
        self.temp.cleanup()

    def propose(self, proposal=None, minutes=15):
        return self.store.propose(self.session, proposal or self.proposal, minutes, ['marketing:1'])

    def confirm(self):
        state = self.propose()
        return self.store.apply(self.session, {'action': 'confirm_plan', 'draft_id': state['journey']['draft']['id']})

    def update(self, mission, status, **extra):
        return self.store.apply(self.session, {'action': 'mission_update', 'mission_id': mission['id'], 'status': status, **extra})

    def test_sessions_are_isolated_and_get_is_detached(self):
        original = self.store.get(self.session)
        original['saved_nodes'].append('marketing:1')
        self.assertEqual(self.store.get(self.session)['saved_nodes'], [])
        self.store.apply(self.session, {'action': 'save_node', 'node_id': 'marketing:1'})
        self.assertEqual(self.store.get('other-session')['saved_nodes'], [])
        self.assertEqual(self.store.get(self.session)['saved_nodes'], ['marketing:1'])

    def test_reopen_preserves_history_and_uses_hash_only(self):
        response = {'answer': 'Prueba un mensaje', 'recommendations': [{'node_id': 'marketing:1', 'reason': 'Útil'}]}
        self.store.append_turn(self.session, 'Ayúdame', response)
        response['answer'] = 'edited by caller'
        reopened = JourneyStore(self.path, ['marketing:1'])
        assistant = reopened.get(self.session)['history'][-1]
        self.assertEqual(assistant['response']['answer'], 'Prueba un mensaje')
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute('SELECT session_hash,state FROM journeys').fetchall()
        self.assertEqual(rows[0][0], hashlib.sha256(self.session.encode()).hexdigest())
        self.assertNotIn(self.session, json.dumps(rows))

    def test_confirmation_is_explicit_and_stale_drafts_fail(self):
        first = self.propose()['journey']['draft']
        second_state = self.propose()
        self.assertIsNone(second_state['journey']['plan'])
        with self.assertRaises(LookupError):
            self.store.apply(self.session, {'action': 'confirm_plan', 'draft_id': first['id']})
        second = second_state['journey']['draft']
        plan = self.store.apply(self.session, {'action': 'confirm_plan', 'draft_id': second['id']})['journey']['plan']
        self.assertEqual([m['status'] for m in plan['missions']], ['active', 'pending', 'pending'])
        with self.assertRaises(LookupError):
            self.store.apply(self.session, {'action': 'confirm_plan', 'draft_id': second['id']})

    def test_new_draft_does_not_overwrite_active_plan(self):
        plan = self.confirm()['journey']['plan']
        self.update(plan['missions'][0], 'completed', artifact='Mi oferta revisada')
        revised = deepcopy(self.proposal)
        revised['goal'] = 'Otro propósito'
        state = self.propose(revised)
        self.assertEqual(state['journey']['goal'], self.proposal['goal'])
        self.assertEqual(state['journey']['plan']['id'], plan['id'])
        self.assertEqual(state['journey']['plan']['missions'][0]['artifact'], 'Mi oferta revisada')
        self.assertEqual(state['journey']['draft']['goal'], 'Otro propósito')

    def test_discard_draft_preserves_existing_active_or_paused_plan(self):
        plan = self.confirm()['journey']['plan']
        self.update(plan['missions'][0], 'completed', artifact='Mi resultado')
        for phase in ['active', 'paused']:
            if phase == 'paused':
                self.store.apply(self.session, {'action': 'pause'})
            before = self.store.get(self.session)
            draft = self.propose()['journey']['draft']
            after = self.store.apply(self.session, {'action': 'discard_draft', 'draft_id': draft['id']})
            self.assertEqual(after, before)
            self.assertEqual(after['journey']['phase'], phase)

    def test_discard_without_plan_returns_to_exploration_and_checks_stale_id(self):
        first = self.propose()['journey']['draft']
        second = self.propose()['journey']['draft']
        with self.assertRaises(LookupError):
            self.store.apply(self.session, {'action': 'discard_draft', 'draft_id': first['id']})
        self.assertEqual(self.store.get(self.session)['journey']['draft']['id'], second['id'])
        after = self.store.apply(self.session, {'action': 'discard_draft', 'draft_id': second['id']})
        self.assertIsNone(after['journey']['draft'])
        self.assertIsNone(after['journey']['plan'])
        self.assertEqual(after['journey']['phase'], 'explore')
        self.assertEqual(after['journey']['goal'], self.proposal['goal'])
        self.assertEqual(self.store.apply(self.session, {'action': 'discard_draft'}), after)

    def test_unknown_nodes_and_nodes_outside_evidence_are_rejected(self):
        for invalid in ['invented:node', 'oferta:2']:
            proposal = deepcopy(self.proposal)
            proposal['missions'][0]['node_ids'] = [invalid]
            with self.assertRaises(ValueError):
                self.propose(proposal)
        with self.assertRaises(ValueError):
            self.store.apply(self.session, {'action': 'save_node', 'node_id': 'invented'})

    def test_malformed_proposals_do_not_change_state(self):
        baseline = self.propose()
        bad = []
        for field, value in [('title', ''), ('action', []), ('minutes', True), ('minutes', 0), ('node_ids', None), ('node_ids', ['marketing:1', 'marketing:1'])]:
            item = deepcopy(self.proposal)
            item['missions'][0][field] = value
            bad.append(item)
        duplicate = deepcopy(self.proposal)
        duplicate['missions'][1] = deepcopy(duplicate['missions'][0])
        bad.extend([duplicate, {'goal': '', 'missions': []}, {'goal': 'Goal', 'missions': self.proposal['missions'][:2]}])
        for item in bad:
            with self.assertRaises(ValueError):
                self.propose(item)
            self.assertEqual(self.store.get(self.session), baseline)
        for minutes in [0, 10, 60, True, '15']:
            with self.assertRaises(ValueError):
                self.propose(minutes=minutes)

    def test_duration_must_fit_user_budget_and_model_cannot_set_state(self):
        proposal = deepcopy(self.proposal)
        proposal['missions'][0].update({'minutes': 60, 'status': 'completed', 'completion_kind': 'reviewed'})
        with self.assertRaisesRegex(ValueError, 'reduce su alcance'):
            self.propose(proposal, minutes=5)
        self.assertIsNone(self.store.get(self.session)['journey']['draft'])
        for mission in proposal['missions']:
            mission['minutes'] = 5
        draft = self.propose(proposal, minutes=5)['journey']['draft']
        self.assertTrue(all(m['minutes'] <= 5 for m in draft['missions']))
        self.assertEqual(draft['missions'][0]['status'], 'pending')
        self.assertIsNone(draft['missions'][0]['completion_kind'])

    def test_preparatory_mission_can_have_no_source(self):
        proposal = deepcopy(self.proposal)
        proposal['missions'][0]['node_ids'] = []
        mission = self.propose(proposal)['journey']['draft']['missions'][0]
        self.assertEqual(mission['node_ids'], [])
        self.assertEqual(mission['created_by'], 'Skool Guide')

    def test_completion_advances_missions_and_preserves_artifact(self):
        plan = self.confirm()['journey']['plan']
        missions = plan['missions']
        result = self.update(missions[0], 'completed', artifact='Ayudo a agencias a definir su oferta')
        first, second, _ = result['journey']['plan']['missions']
        self.assertEqual(first['completion_kind'], 'self_reported')
        self.assertEqual(first['artifact'], 'Ayudo a agencias a definir su oferta')
        self.assertEqual(second['status'], 'active')
        for mission in missions[1:]:
            result = self.update(mission, 'completed')
        self.assertEqual(result['journey']['phase'], 'completed')
        self.assertEqual(result['journey']['plan']['status'], 'completed')

    def test_only_one_active_mission_and_blocked_can_resume(self):
        missions = self.confirm()['journey']['plan']['missions']
        result = self.update(missions[0], 'blocked', artifact='Me falta un ejemplo')
        self.assertEqual(result['journey']['plan']['missions'][0]['status'], 'blocked')
        result = self.update(missions[0], 'active')
        self.assertEqual(result['journey']['plan']['missions'][0]['artifact'], 'Me falta un ejemplo')
        result = self.update(missions[2], 'active')
        self.assertEqual(sum(m['status'] == 'active' for m in result['journey']['plan']['missions']), 1)
        self.assertEqual(result['journey']['plan']['missions'][0]['status'], 'pending')

    def test_pause_resume_and_invalid_update_roll_back(self):
        missions = self.confirm()['journey']['plan']['missions']
        paused = self.store.apply(self.session, {'action': 'pause'})
        with self.assertRaises(ValueError):
            self.update(missions[0], 'completed')
        self.assertEqual(self.store.get(self.session), paused)
        self.store.apply(self.session, {'action': 'resume'})
        for status in ['reviewed', 'pending', None]:
            with self.assertRaises(ValueError):
                self.update(missions[0], status)
        with self.assertRaises(ValueError):
            self.update(missions[0], 'completed', artifact='x' * 3001)
        with self.assertRaises(LookupError):
            self.update({'id': 'wrong'}, 'active')

    def test_history_is_bounded_and_concurrent_actions_do_not_lose_progress(self):
        def write(index):
            return self.store.append_turn(self.session, f'Question {index}', {'answer': f'Answer {index}'})
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(write, range(16)))
        history = self.store.get(self.session)['history']
        self.assertEqual(len(history), HISTORY_LIMIT)
        for user, assistant in zip(history[::2], history[1::2]):
            self.assertEqual(user['content'].split()[-1], assistant['content'].split()[-1])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(write, 99), pool.submit(self.store.apply, self.session, {'action': 'save_node', 'node_id': 'marketing:1'})]
            for result in results:
                result.result()
        state = self.store.get(self.session)
        self.assertEqual(state['saved_nodes'], ['marketing:1'])
        self.assertEqual(state['history'][-1]['content'], 'Answer 99')

    def test_reset_removes_all_user_progress_and_saved_nodes_are_idempotent(self):
        self.confirm()
        self.store.append_turn(self.session, 'Pregunta', {'answer': 'Respuesta'})
        for _ in range(2):
            self.store.apply(self.session, {'action': 'save_node', 'node_id': 'marketing:1'})
        self.assertEqual(self.store.get(self.session)['saved_nodes'], ['marketing:1'])
        self.store.apply(self.session, {'action': 'remove_saved_node', 'node_id': 'marketing:1'})
        state = self.store.apply(self.session, {'action': 'reset'})
        self.assertEqual(state, self.store.get('fresh-session'))

    def test_expired_session_returns_default(self):
        self.confirm()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('UPDATE journeys SET expires_at=0')
            db.commit()
        state = self.store.get(self.session)
        self.assertIsNone(state['journey']['plan'])
        self.assertEqual(state['journey']['phase'], 'explore')


if __name__ == '__main__':
    unittest.main()

"""HTTP contract tests with fictional fixtures; no paid model calls."""
from contextlib import closing, redirect_stderr, redirect_stdout
import http.client
import io
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/skool-guide'))
from server import GuideApp, handler_for, parse, ProviderBillingError
from journey import JourneyStore
from retrieval import Library
from coaching import clean_question

ORIGIN='https://brain.example'

class CoachingAPI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'data').mkdir()
        (self.root/'data/n.json').write_text(json.dumps({'markdown':'# Oferta\nDefine un cliente y un resultado. [Skool](https://www.skool.com/example/classroom/123)'}))
        node={'id':'oferta:1','title':'Oferta clara','source':'oferta','kind':'video','hostedNote':'data/n.json'}
        (self.root/'data/graph.json').write_text(json.dumps({'nodes':[node],'links':[]}))
        self.lib=Library(self.root);self.store=JourneyStore(self.root/'journey.sqlite',self.lib.nodes);self.calls=0
        def model(system,payload):
            self.calls+=1
            if 'catalogue' in payload:return {'query':'oferta clara','node_ids':['oferta:1']}
            if 'available_minutes' in payload:
                return {'answer':'Revisa este borrador.', 'proposal':{'goal':'Aclarar mi oferta','missions':[{'title':f'Paso {i}','action':f'Escribe una frase {i}','deliverable':f'Frase {i}','done_when':f'Existe la frase {i}','minutes':5,'node_ids':['oferta:1']} for i in range(1,4)]}}
            return {'answer':'Empieza por tu cliente.','question':{'text':'¿Qué te frena?','options':['No está claro','No lo sé']},'recommendations':[{'node_id':'oferta:1','reason':'Aclara la promesa.','evidence_ids':[payload['evidence'][0]['evidence_id']]}]}
        self.app=GuideApp(self.lib,self.store,self.root/'budget.sqlite',ORIGIN,model)
        self.http=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.app));self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.tmp.cleanup()
    def request(self,method,path,payload=None,cookie=None,origin=ORIGIN):
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=5)
        headers={'Origin':origin,'Content-Type':'application/json'}
        if cookie:headers['Cookie']=cookie
        conn.request(method,path,body=json.dumps(payload) if payload is not None else None,headers=headers)
        response=conn.getresponse();raw=response.read().decode();status=response.status;newcookie=response.getheader('Set-Cookie');self.response_headers=dict(response.getheaders());conn.close()
        if path=='/chat' and status==200:
            results=[json.loads(frame.split('data: ',1)[1]) for frame in raw.split('\n\n') if frame.startswith('event: result\n')];data=results[-1] if results else raw
        else:data=json.loads(raw)
        return status,data,newcookie.split(';',1)[0] if newcookie else cookie
    def test_full_journey_requires_confirmation_and_survives_reload(self):
        _,state,cookie=self.request('GET','/state');self.assertFalse(state['history'])
        status,answer,cookie=self.request('POST','/chat',{'message':'Mejora mi oferta'},cookie)
        self.assertEqual(status,200);self.assertEqual(answer['question']['text'],'¿Qué te frena?')
        self.assertIn('resources',answer['recommendations'][0])
        _,draft,cookie=self.request('POST','/chat',{'message':'Crea mi plan','action':'generate_plan','minutes':5},cookie)
        self.assertIsNone(draft['journey']['plan']);draft_id=draft['journey']['draft']['id']
        _,active,_=self.request('POST','/journey',{'action':'confirm_plan','draft_id':draft_id},cookie)
        plan=active['journey']['plan'];mission=plan['missions'][0]
        _,done,_=self.request('POST','/journey',{'action':'mission_update','mission_id':mission['id'],'status':'completed','artifact':'Mi frase de oferta'},cookie)
        self.assertEqual(done['journey']['plan']['missions'][0]['status'],'completed')
        _,restored,_=self.request('GET','/state',cookie=cookie);self.assertEqual(restored['journey']['plan']['missions'][0]['artifact'],'Mi frase de oferta');self.assertEqual(len(restored['history']),4)
        _,other,_=self.request('GET','/state');self.assertIsNone(other['journey']['plan']);self.assertFalse(other['history'])
        self.assertEqual(self.calls,4) # model only used for chat/plan, never for marking progress.
    def test_invalid_calls_have_no_state_effect(self):
        _,_,cookie=self.request('GET','/state')
        self.assertEqual(self.request('POST','/journey',{'action':'confirm_plan','draft_id':'forged'},cookie)[0],400)
        self.assertEqual(self.request('POST','/chat',{'message':'hello'},cookie,origin='https://evil.example')[0],403)
        self.assertEqual(self.request('GET','/state',cookie=cookie,origin='https://evil.example')[0],403)
        self.assertEqual(self.request('POST','/chat',{'message':'go','action':'generate_plan','minutes':True},cookie)[0],400)
        self.assertEqual(self.request('GET','/resources?node_id=unknown',cookie=cookie)[0],404)
        self.assertEqual(self.calls,0)
    def test_invalid_plan_answer_retries_once_without_saving_draft_or_history(self):
        original_model=self.app.model
        for invalid in [None,'   ',{'unexpected':'object'}]:
            with self.subTest(answer=invalid):
                attempts=[]
                def model(system,payload):
                    response=original_model(system,payload)
                    if 'available_minutes' in payload:
                        attempts.append(json.loads(json.dumps(payload)))
                        response['answer']=invalid
                    return response
                self.app.model=model
                _,before,cookie=self.request('GET','/state')
                calls_before=self.calls
                status,response,cookie=self.request('POST','/chat',{'message':'Prepara un plan de oferta','action':'generate_plan','minutes':5},cookie)
                self.assertEqual(status,200) # Errors after SSE starts use an error event.
                self.assertIsInstance(response,str)
                self.assertIn('event: error\n',response)
                self.assertNotIn('event: result\n',response)
                self.assertEqual(self.calls-calls_before,3) # One planner plus two plan attempts.
                self.assertEqual(len(attempts),2)
                self.assertNotIn('validation_feedback',attempts[0])
                self.assertIn('answer',attempts[1]['validation_feedback'])
                _,restored,_=self.request('GET','/state',cookie=cookie)
                self.assertEqual(restored,before)
                self.assertIsNone(restored['journey']['draft'])
                self.assertIsNone(restored['journey']['plan'])
                self.assertEqual(restored['history'],[])

    def test_plan_retry_reduces_scope_before_saving_unconfirmed_draft(self):
        original_model=self.app.model
        attempts=[]
        def model(system,payload):
            response=original_model(system,payload)
            if 'available_minutes' in payload:
                attempts.append(json.loads(json.dumps(payload)))
                if len(attempts)==1:
                    response['proposal']['missions'][0]['minutes']=30
            return response
        self.app.model=model
        _,_,cookie=self.request('GET','/state')
        status,response,cookie=self.request('POST','/chat',{'message':'Prepara mi plan','action':'generate_plan','minutes':5},cookie)
        self.assertEqual(status,200)
        self.assertIsInstance(response,dict)
        self.assertEqual(self.calls,3)
        self.assertEqual(len(attempts),2)
        self.assertNotIn('validation_feedback',attempts[0])
        self.assertIn('reduce su alcance',attempts[1]['validation_feedback'])
        journey=response['journey']
        self.assertEqual(journey['phase'],'draft')
        self.assertIsNone(journey['plan'])
        self.assertEqual([m['minutes'] for m in journey['draft']['missions']],[5,5,5])
        self.assertTrue(all(m['status']=='pending' for m in journey['draft']['missions']))
        _,restored,_=self.request('GET','/state',cookie=cookie)
        self.assertEqual(restored['journey'],journey)
        self.assertEqual(len(restored['history']),2)
        self.assertNotIn('journey',restored['history'][-1]['response'])

    def test_invalid_coach_json_is_repaired_and_persisted_once(self):
        original_model=self.app.model
        attempts=[]
        def model(system,payload):
            response=original_model(system,payload)
            if 'catalogue' not in payload:
                attempts.append(json.loads(json.dumps(payload)))
                if len(attempts)==1:
                    raise json.JSONDecodeError('Unterminated string','{"answer":"incomplete',10)
            return response
        self.app.model=model
        _,_,cookie=self.request('GET','/state')
        status,response,cookie=self.request('POST','/chat',{'message':'Quiero aclarar mi oferta'},cookie)
        self.assertEqual(status,200)
        self.assertIsInstance(response,dict)
        self.assertEqual(response['answer'],'Empieza por tu cliente.')
        self.assertEqual(self.calls,3)
        self.assertEqual(len(attempts),2)
        self.assertNotIn('validation_feedback',attempts[0])
        self.assertIn('Unterminated string',attempts[1]['validation_feedback'])
        _,restored,_=self.request('GET','/state',cookie=cookie)
        self.assertEqual([turn['role'] for turn in restored['history']],['user','assistant'])
        self.assertEqual(restored['history'][0]['content'],'Quiero aclarar mi oferta')
        self.assertEqual(restored['history'][1]['content'],response['answer'])
        self.assertIsNone(restored['journey']['draft'])
        self.assertIsNone(restored['journey']['plan'])

    def test_planner_and_coach_share_one_repair_without_fourth_call_or_persistence(self):
        original_model=self.app.model
        stages=[]
        attempts=[]
        def model(system,payload):
            response=original_model(system,payload)
            stage='planner' if 'catalogue' in payload else 'coach'
            stages.append(stage)
            attempts.append(json.loads(json.dumps(payload)))
            if len(stages)==1 or stage=='coach':
                raise json.JSONDecodeError('Invalid model JSON','{incomplete',1)
            return response
        self.app.model=model
        _,before,cookie=self.request('GET','/state')
        status,response,cookie=self.request('POST','/chat',{'message':'Ayúdame con mi oferta'},cookie)
        self.assertEqual(status,200)
        self.assertIsInstance(response,str)
        self.assertIn('event: error\n',response)
        self.assertNotIn('event: result\n',response)
        self.assertEqual(stages,['planner','planner','coach'])
        self.assertEqual(self.calls,3)
        self.assertNotIn('validation_feedback',attempts[0])
        self.assertIn('Invalid model JSON',attempts[1]['validation_feedback'])
        self.assertNotIn('validation_feedback',attempts[2])
        _,restored,_=self.request('GET','/state',cookie=cookie)
        self.assertEqual(restored,before)
        self.assertFalse(restored['history'])
        self.assertIsNone(restored['journey']['draft'])
        self.assertIsNone(restored['journey']['plan'])

    def test_provider_402_is_classified_without_exposing_provider_response(self):
        private_detail='fictional-account-details-must-stay-private'
        raw='Billing or credits exhausted: HTTP 402: '+private_detail
        stdout,stderr=io.StringIO(),io.StringIO()
        with redirect_stdout(stdout),redirect_stderr(stderr):
            with self.assertRaises(ProviderBillingError) as caught:
                parse(raw)
        self.assertNotIn(private_detail,str(caught.exception))
        self.assertNotIn('HTTP 402',str(caught.exception))
        self.assertEqual(stdout.getvalue(),'')
        self.assertEqual(stderr.getvalue(),'')

    def test_provider_billing_failure_does_not_retry_or_change_state(self):
        private_detail='fictional-provider-billing-details'
        def model(system,payload):
            self.calls+=1
            raise ProviderBillingError(private_detail)
        self.app.model=model
        _,before,cookie=self.request('GET','/state')
        stderr=io.StringIO()
        with redirect_stderr(stderr):
            status,response,cookie=self.request('POST','/chat',{'message':'Ayúdame a definir mi oferta'},cookie)
        self.assertEqual(status,200)
        self.assertIsInstance(response,str)
        self.assertIn('event: error\n',response)
        self.assertIn('puedes explorar el mapa y los recursos',response)
        self.assertNotIn('event: result\n',response)
        self.assertNotIn(private_detail,response)
        self.assertNotIn(private_detail,stderr.getvalue())
        self.assertEqual(self.calls,1)
        _,restored,_=self.request('GET','/state',cookie=cookie)
        self.assertEqual(restored,before)
        self.assertFalse(restored['history'])
        self.assertIsNone(restored['journey']['draft'])
        self.assertIsNone(restored['journey']['plan'])
        resource_status,resource,_=self.request('GET','/resources?node_id=oferta:1',cookie=cookie)
        self.assertEqual(resource_status,200)
        self.assertEqual(resource['node_id'],'oferta:1')
        self.assertTrue(resource['resources'])
        self.assertEqual(self.calls,1)

    def test_session_cookie_is_protected_reused_and_malformed_cookie_is_rotated(self):
        _,_,cookie=self.request('GET','/state')
        header=self.response_headers['Set-Cookie']
        self.assertRegex(cookie,r'^guide_session=[A-Za-z0-9_-]{43}$')
        for attribute in ['HttpOnly','Secure','SameSite=Strict','Path=/','Max-Age=2592000']:
            self.assertIn(attribute,header)
        self.assertNotIn('Domain=',header)
        _,_,same=self.request('GET','/state',cookie=cookie)
        self.assertEqual(same,cookie)
        _,state,replaced=self.request('GET','/state',cookie='guide_session=invalid')
        self.assertNotEqual(replaced,'guide_session=invalid')
        self.assertNotEqual(replaced,cookie)
        self.assertRegex(replaced,r'^guide_session=[A-Za-z0-9_-]{43}$')
        self.assertFalse(state['history'])
        self.assertIsNone(state['journey']['plan'])

    def test_busy_session_rejects_concurrent_mutation_without_model_or_state_change(self):
        _,before,cookie=self.request('GET','/state')
        session_id=cookie.split('=',1)[1]
        self.assertTrue(self.app.acquire(session_id))
        try:
            status,_,_=self.request('POST','/journey',{'action':'save_node','node_id':'oferta:1'},cookie)
            self.assertEqual(status,409)
        finally:
            self.app.release(session_id)
        _,after,_=self.request('GET','/state',cookie=cookie)
        self.assertEqual(before,after)
        self.assertEqual(self.calls,0)
    def test_quota_migration_keeps_existing_usage(self):
        old=self.root/'old.sqlite'
        with closing(sqlite3.connect(old)) as db, db:db.execute('CREATE TABLE budget(key TEXT PRIMARY KEY,count INTEGER NOT NULL)');db.execute("INSERT INTO budget VALUES('existing',12)")
        GuideApp(self.lib,self.store,old,ORIGIN)
        with closing(sqlite3.connect(old)) as db, db:self.assertEqual(db.execute("SELECT count FROM budget WHERE key='existing'").fetchone()[0],12)
    def test_question_is_bounded_and_safe_data(self):
        self.assertIsNone(clean_question([]));self.assertEqual(clean_question({'text':'Pregunta','options':['A','A',4,'B','C','D']})['options'],['A','B','C'])

if __name__=='__main__':unittest.main()

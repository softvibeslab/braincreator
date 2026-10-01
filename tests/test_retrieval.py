import sys,unittest,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/skool-guide'))
from retrieval import Library
class RetrievalTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'data').mkdir();(self.root/'data/n.json').write_text(json.dumps({'markdown':'Una oferta útil atrae prospectos con intención de compra.'}))
  node={'id':'m:1','title':'Cómo atraer leads','source':'marketing','kind':'video','hostedNote':'data/n.json'}
  (self.root/'data/graph.json').write_text(json.dumps({'nodes':[node],'links':[]}));self.lib=Library(self.root)
 def tearDown(self):self.temp.cleanup()
 def test_retrieves_accented_query(self):self.assertEqual(self.lib.search('intención de compra')[0]['node_id'],'m:1')
 def test_drops_invented_nodes_and_citations(self):
  evidence=self.lib.search('leads');valid=evidence[0]['evidence_id'];result=self.lib.validate({'answer':'Ayuda','recommendations':[{'node_id':'invented','evidence_ids':[valid]},{'node_id':'m:1','evidence_ids':['invented']},{'node_id':'m:1','evidence_ids':[valid],'reason':'Útil'}]},evidence)
  self.assertEqual(len(result['recommendations']),1);self.assertEqual(result['recommendations'][0]['title'],'Cómo atraer leads')
 def test_path_traversal_refused(self):
  with self.assertRaises(ValueError):self.lib.read('../secret.json')
 def test_malformed_response_and_answer_stay_empty(self):
  for response in (None,[],False,'text',{'answer':None},{'answer':42},{'answer':{}},{'answer':['text']}):
   with self.subTest(response=response):
    result=self.lib.validate(response,[])
    self.assertEqual(result['answer'],'');self.assertEqual(result['recommendations'],[])
  self.assertEqual(self.lib.validate({'answer':'a'*13000},[])['answer'],'a'*12000)
 def test_malformed_recommendations_are_ignored(self):
  evidence=self.lib.search('leads')
  for cards in (None,False,42,'card',{'node_id':'m:1'}):
   with self.subTest(cards=cards):self.assertEqual(self.lib.validate({'recommendations':cards},evidence)['recommendations'],[])
  cards=[None,{'node_id':[],'evidence_ids':[]},'not-a-card']
  self.assertEqual(self.lib.validate({'recommendations':cards},evidence)['recommendations'],[])
 def test_evidence_ids_accept_strings_and_filter_malformed_items(self):
  evidence=self.lib.search('leads');valid=evidence[0]['evidence_id']
  for ids in (valid,[None,{},[],42,valid,valid]):
   with self.subTest(ids=ids):
    cards=self.lib.validate({'recommendations':[{'node_id':'m:1','evidence_ids':ids,'reason':None}]},evidence)['recommendations']
    self.assertEqual(len(cards),1);self.assertEqual(len(cards[0]['evidence']),1);self.assertEqual(cards[0]['reason'],'')
  for ids in (None,False,42,{},'invented'):
   with self.subTest(ids=ids):
    self.assertEqual(self.lib.validate({'recommendations':[{'node_id':'m:1','evidence_ids':ids}]},evidence)['recommendations'],[])
 def test_recommendations_are_bounded_and_evidence_must_match_node(self):
  evidence=self.lib.search('leads');valid=evidence[0]['evidence_id']
  self.lib.nodes['m:2']={**self.lib.nodes['m:1'],'id':'m:2'}
  mismatched={'node_id':'m:2','evidence_ids':[valid]}
  self.assertEqual(self.lib.validate({'recommendations':[mismatched]},evidence)['recommendations'],[])
  card={'node_id':'m:1','evidence_ids':[valid],'reason':'r'*1000}
  cards=self.lib.validate({'recommendations':[card]*5},evidence)['recommendations']
  self.assertEqual(len(cards),3);self.assertEqual(len(cards[0]['reason']),800)
if __name__=='__main__':unittest.main()

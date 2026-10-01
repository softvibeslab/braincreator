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
if __name__=='__main__':unittest.main()

"""Read-only, versioned catalogue and evidence retrieval. No private data in Git."""
import json,re,unicodedata,math,hashlib
from pathlib import Path
from collections import Counter

def words(text):
    return re.findall(r'[a-z0-9]{3,}',unicodedata.normalize('NFKD',text.lower()).encode('ascii','ignore').decode())

class Library:
    def __init__(self, root):
        self.root=Path(root).resolve();raw=(self.root/'data/graph.json').read_bytes();self.version=hashlib.sha256(raw).hexdigest()[:16]
        graph=json.loads(raw);self.nodes={n['id']:n for n in graph['nodes']};self.chunks=[];self.by_node={};self.neighbors={k:set() for k in self.nodes}
        for edge in graph['links']:
            self.neighbors[edge['source']].add(edge['target']);self.neighbors[edge['target']].add(edge['source'])
        for n in graph['nodes']:
            if n['source']=='tecnico':continue
            note=self.read(n['hostedNote']);self.add(n,'note',None,note[:16000])
            if n['kind']=='video' and n.get('hostedTranscript'):
                transcript=self.read(n['hostedTranscript']);parts=re.split(r'(?=\*\*\[\d+:\d+:\d+\]\*\*)',transcript)
                for i in range(0,len(parts),4):
                    chunk='\n'.join(parts[i:i+4]);ts=re.search(r'\[(\d+:\d+:\d+)\]',chunk)
                    if chunk.strip():self.add(n,'transcript',ts.group(1) if ts else None,chunk[:6000])
        self.df=Counter(t for c in self.chunks for t in c['terms']);self.avg=sum(sum(c['terms'].values()) for c in self.chunks)/max(len(self.chunks),1)
    def read(self, relative):
        p=(self.root/relative).resolve()
        if not p.is_relative_to(self.root):raise ValueError('Invalid library path')
        return json.loads(p.read_text())['markdown']
    def add(self,n,kind,ts,text):
        eid=hashlib.sha256((n['id']+kind+str(ts)+text).encode()).hexdigest()[:20]
        c={'evidence_id':eid,'node_id':n['id'],'title':n['title'],'kind':kind,'timestamp':ts,'text':text,'terms':Counter(words(n['title']+' '+text))};self.chunks.append(c);self.by_node.setdefault(n['id'],[]).append(c)
    def catalogue(self):return [{'id':n['id'],'title':n['title'],'tags':n.get('tags',[])} for n in self.nodes.values() if n['kind']=='video']
    def search(self,query,selected=(),limit=10):
        terms=words(query);ranked=[]
        for c in self.chunks:
            score=0;length=sum(c['terms'].values())
            for t in set(terms):
                f=c['terms'][t]
                if f:score+=math.log(1+(len(self.chunks)-self.df[t]+.5)/(self.df[t]+.5))*f*2.2/(f+1.2*(.25+.75*length/self.avg))
            score+=sum(2 for t in terms if t in words(c['title']))
            if c['node_id'] in selected:score+=12 if c['kind']=='note' else 3
            if score>0:ranked.append((score,c))
        ranked.sort(key=lambda x:x[0],reverse=True);result=[];counts=Counter()
        for _,c in ranked:
            if counts[c['node_id']]>=3:continue
            counts[c['node_id']]+=1;result.append({k:v for k,v in c.items() if k!='terms'})
            if len(result)>=limit:break
        return result
    def validate(self,response,evidence):
        # Model output is untrusted JSON: malformed fields must not break the
        # response or become plausible-looking text through str(None/dict).
        if not isinstance(response,dict):response={}
        allowed={e['evidence_id']:e for e in evidence};cards=[]
        recommendations=response.get('recommendations',[])
        if not isinstance(recommendations,list):recommendations=[]
        for card in recommendations[:3]:
            if not isinstance(card,dict):continue
            node_id=card.get('node_id')
            if not isinstance(node_id,str):continue
            node=self.nodes.get(node_id)
            evidence_ids=card.get('evidence_ids',[])
            if isinstance(evidence_ids,str):evidence_ids=[evidence_ids]
            if not isinstance(evidence_ids,list):evidence_ids=[]
            refs=[];seen=set()
            for eid in evidence_ids[:12]:
                if not isinstance(eid,str) or eid in seen:continue
                ref=allowed.get(eid)
                if ref and ref['node_id']==node_id:
                    refs.append(ref);seen.add(eid)
            if not node or not refs:continue
            reason=card.get('reason','')
            if not isinstance(reason,str):reason=''
            cards.append({'node_id':node['id'],'title':node['title'],'category':node['source'],'reason':reason[:800],'evidence':[{'source':r['title'],'timestamp':r['timestamp'],'evidence_id':r['evidence_id']} for r in refs]})
        answer=response.get('answer','')
        return {'answer':answer[:12000] if isinstance(answer,str) else '', 'recommendations':cards,'library_version':self.version}

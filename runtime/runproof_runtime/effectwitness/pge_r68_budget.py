"""One physical fsynced WAL and one permanent cross-role budget."""
import os,time,copy,re
from . import pge_r68_context as c
KINDS={'OWNER','RESERVE','RESULT','MODEL_REQUEST','SHAPE','PARSED','MODEL_RESPONSE','INTENT','TOOL_RETURN','FAULT','PROCESS_START','PROCESS_CLEANUP','CHOICE','PORT_ENTERED','DOMAIN_VERIFIED','FEEDBACK_FROZEN','ADMISSION','SESSION_COMPLETE','PRE_SEND_REJECTED'}
def replay(frames,ctx):
 previous=None;events=[];counts=dict.fromkeys(c.LIMITS,0);tickets={};results={};unknown=False;blocked=False;reserved=cost=0;local={}
 for i,f in enumerate(frames):
  c.require(set(f)=={'seq','previous','event','sha256'} and f['seq']==i and f['previous']==previous and f['sha256']==c.digest({k:v for k,v in f.items() if k!='sha256'}),'WAL_CHAIN');e=f['event'];c.require(e['kind'] in KINDS and e['session_id']==ctx['session_id'] and type(e['clock']) is int and (not events or e['clock']>=events[-1]['clock']),'WAL_SCOPE_TIME')
  if i==0:c.require(e['kind']=='OWNER' and e['context_sha256']==c.digest(ctx),'WAL_OWNER')
  kind=e['kind']
  if kind=='RESERVE':
   r=e['resource'];c.require(r in counts and e['ticket']==r+'-'+str(counts[r]+1),'TICKET_SEQUENCE');safe_read=r=='authority_read' or r=='config_http' and e.get('method')=='GET';c.require(not (unknown or blocked) or safe_read,'STOP_WRITES_PROVIDER');c.require(not any(k not in results and t['resource'] in ('provider','sqlite_refund','config_post') for k,t in tickets.items()) or safe_read,'UNSETTLED_STOP');counts[r]+=1;c.require(counts[r]<=c.LIMITS[r],'RESOURCE_LIMIT')
   if r=='provider':
    q=e['request'];role=e['role'];domain=e['domain'];scope=(role,domain,e['round']);n=local.get(scope,0);caps=c.CAPS['EXPLORER' if role=='EXPLORER' else domain];c.require(role in ('TARGET','EXPLORER') and domain in c.DOMAINS and e['round']==c.DOMAINS.index(domain)+1 and n<len(caps) and q['slot_cap']==caps[n] and q['ordinal']==n+1,'ROLE_DOMAIN_SLOT');c.require(all(type(q[k]) is int and q[k]>=0 for k in ('input_upper','output_cap','slot_cap')) and 0<q['input_upper'] and q['input_upper']+q['output_cap']<=q['slot_cap'],'INPUT_BOUND');local[scope]=n+1;reserved+=q['slot_cap'];cost+=q['input_upper']*4.5+q['output_cap']*18;c.require(reserved<=30400 and cost<=750000,'GLOBAL_POOL')
    if e['round']==2:c.require(any(z['kind']=='FEEDBACK_FROZEN' and z['round']==1 for z in events),'NO_EARLY_SECOND_DOMAIN')
   tickets[e['ticket']]=e
  elif kind=='RESULT':
   c.require(e['ticket'] in tickets and e['ticket'] not in results,'SETTLEMENT_REPLAY');results[e['ticket']]=e;unknown|=e.get('status')=='UNKNOWN'
  elif kind=='PRE_SEND_REJECTED':
   receipt=e['receipt'];q=receipt['request'];scope={k:e[k] for k in ('domain','round','role','cold')};c.require(not blocked and receipt['scope']==scope and receipt['reason']=='INPUT_BOUND' and receipt['provider_reserved'] is False and receipt['network_sent'] is False and e['receipt_sha256']==c.digest(receipt) and len(c.canonical(receipt))<=12288,'PRE_SEND_BINDING')
   prior=[z for z in events if z['kind']=='MODEL_REQUEST' and all(z[k]==v for k,v in scope.items())];received=[z for z in events if z['kind']=='MODEL_RESPONSE' and all(z[k]==v for k,v in scope.items())];caps=c.CAPS['EXPLORER' if scope['role']=='EXPLORER' else scope['domain']];n=len(prior);c.require(len(received)==n and n<len(caps) and q['ordinal']==n+1 and q['slot_cap']==caps[n] and all(type(q[k]) is int and 0<=q[k]<=262144 for k in ('input_upper','output_cap','slot_cap','ordinal')) and q['input_upper']+q['output_cap']>q['slot_cap'],'PRE_SEND_NOT_OVER_BOUND')
   if prior:
    pq=prior[-1]['request'];u=received[-1]['response']['usage'];c.require(q['previous_prompt']==u['prompt_tokens'] and q['framing_guard']==512 and q['suffix_bytes']==q['canonical_bytes']-pq['canonical_bytes']+1 and q['input_upper']==u['prompt_tokens']+q['suffix_bytes']+512 and q['configuration_sha256']==pq['configuration_sha256'] and q['schema_sha256']==pq['schema_sha256'],'PRE_SEND_INPUT_PROOF')
    returns=[z['row'] for z in events if z['kind']=='TOOL_RETURN' and z.get('domain')==scope['domain'] and z.get('round')==scope['round'] and z.get('cold',False)==scope['cold']];c.require(q['tool_returns']==[dict(call_id=z['call_id'],result_sha256=z['result_sha256']) for z in returns],'PRE_SEND_RETURN_BINDING');expectedcap=512 if len(returns)>= (3 if scope['domain']==c.DOMAINS[0] else 2) else 256;c.require(q['output_cap']==expectedcap,'PRE_SEND_OUTPUT_CAP')
   else:c.require(q['input_upper']==q['canonical_bytes'] and q['previous_prompt'] is None,'PRE_SEND_INITIAL')
   blocked=True
  if any(t['resource']=='session' for t in tickets.values()):c.require(e['clock']-next(t['clock'] for t in tickets.values() if t['resource']=='session')<=2100*10**9,'SESSION_DEADLINE')
  events.append(e);previous=c.digest(f)
 return dict(events=events,counts=counts,tickets=tickets,results=results,unknown=unknown,blocked=blocked,reserved_tokens=reserved,reserved_cost_micro_cny=cost)
class Ledger:
 def __init__(self,ctx,create=False):
  self.ctx=ctx;self.path=ctx.scope(ctx.root/'wal.jsonl');self.pending=None
  if create:c.require(not self.path.exists(),'WAL_EXISTS');self.append('OWNER',context_sha256=c.digest(ctx.public()))
  self.read()
 def read(self):
  raw=self.path.read_bytes();c.require(raw.endswith(b'\n'),'TORN_WAL');self.frames=[c.strict(x) for x in raw.splitlines()];a=replay(self.frames,self.ctx.public());expected={e['receipt_id']:e['receipt_sha256'] for e in a['events'] if e['kind'] in ('SHAPE','PRE_SEND_REJECTED')};folder=self.ctx.scope(self.ctx.root/'receipts');found={}
  for p in folder.glob('*.json') if folder.exists() else []:self.ctx.scope(p);found[p.stem]=c.sha(p.read_bytes())
  if self.pending and self.pending[0] not in expected:expected[self.pending[0]]=self.pending[1]
  c.require(found==expected,'TORN_RECEIPT');return a
 def append(self,kind,**data):
  lock=self.ctx.scope(self.ctx.root/'wal.lock')
  with lock.open('xb'):pass
  try:
   frames=[]
   if self.path.exists():self.read();frames=self.frames
   event=dict(kind=kind,clock=time.monotonic_ns(),session_id=self.ctx.public()['session_id'],**copy.deepcopy(data));frame=dict(seq=len(frames),previous=c.digest(frames[-1]) if frames else None,event=event);frame['sha256']=c.digest(frame);replay(frames+[frame],self.ctx.public())
   with self.path.open('ab') as f:f.write(c.canonical(frame)+b'\n');f.flush();os.fsync(f.fileno())
   self.frames=frames+[frame]
  finally:lock.unlink()
 def reserve(self,resource,**data):
  self.ctx.check();a=self.read();ticket=resource+'-'+str(a['counts'][resource]+1);self.append('RESERVE',resource=resource,ticket=ticket,**data);return ticket
 def settle(self,ticket,**data):self.append('RESULT',ticket=ticket,**data)
 def receipt(self,kind,key,value,**scope):
  self.read();c.require(self.pending is None and re.fullmatch('[a-zA-Z0-9_-]{1,100}',key),'RECEIPT_ID');self.pending=(key,c.digest(value))
  try:self.ctx.once(self.ctx.root/'receipts'/(key+'.json'),value);self.append(kind,receipt_id=key,receipt_sha256=c.digest(value),receipt=value,**scope)
  finally:self.pending=None
  self.read()

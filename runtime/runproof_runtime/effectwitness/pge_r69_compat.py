"""Task-owned rehosting, not a rerun/rename of native R68 SharedSession."""
import copy,secrets,socket,os,shutil,time,argparse,subprocess
from pathlib import Path
from . import pge_r69_abi as a,pge_r69_capsule as cap,pge_r69_budget as budget
from . import pge_r68_context as n,pge_r68_driver as driver,pge_r68_explorer as explorer
from .pge_r68_budget import Ledger
from .pge_r68_config_port import ConfigPort
from .pge_r68_order_port import OrderPort,Bridge,Reader
from .orders import OrderSandbox,OrderAdapter
from .effect_oracle import evaluate_order_effect
ROOT=cap.ROOT
HISTORY=(('spikes/rpf-66/rev-5/dual-agent-witness.json','runtime.runproof_runtime.effectwitness.pge_r66_verify','68dad2804edd3668e1e4b4ed19d18034b79d5fa1892e9fea75aaeb9080c4f3c5'),('spikes/rpf-67/rev-4/order-target-witness.json','runtime.runproof_runtime.effectwitness.pge_r67_order_verify','a2ab94b70a144e389b324cb4731aba6d48a28fc0e77646c54c20a490d2b72c26'),('spikes/rpf-68/rev-3/cross-domain-witness.json','runtime.runproof_runtime.effectwitness.pge_r68_verify','5b97d3e0a4c9c3d2492b5aa49af00ebe1e553b24b0f9725087180510e55dd9e9'))
def historical_identity(path):
 a.require(path in [r[0] for r in HISTORY],'NATIVE_ROUTE');row=next(r for r in HISTORY if r[0]==path);raw=(ROOT/path).read_bytes();a.require(a.sha(raw)==row[2],'HISTORICAL_RAW_ANCHOR');obj=a.strict(raw);return dict(path=path,raw_sha256=row[2],schema=obj['schema'],native_verifier=row[1],verification='REQUIRES_NATIVE_CLI',authority='HISTORICAL_REFERENCE_ONLY')
class Context:
 def __init__(self,scope,ports):
  a.require(type(scope) is cap.OwnerScope,'TYPED_OWNER');a.require(len(ports)==len(set(ports))==3 and all(type(p) is int and 1024<=p<=65535 for p in ports),'PORT_SCOPE');self.scope_owner=scope;self.root=scope.root;sm=cap.source_map();self._value=dict(owner=a.OWNER,abi=a.VERSION,session_id=scope.run_id,workspace=self.root.relative_to(ROOT).as_posix(),source_kind=n.SYNTHETIC,sources=sm,source_digest=cap.identity()['source_digest'],ports=list(ports),limits=n.LIMITS,caps={k:list(v) for k,v in n.CAPS.items()},budget_version=n.BUDGET_VERSION,reachable_tokens=n.REACHABLE_TOKENS,global_tokens=n.GLOBAL_TOKENS,max_slot=n.MAX_SLOT,rounds=[])
  for i in (1,2):
   row={}
   for candidate in n.CANDIDATES[i-1]:
    ct=n.contract(scope.run_id,i,candidate,self._value['source_digest'],ports);ct['experiment']['owner']=a.OWNER;ct['experiment']['environment_id']='env-'+scope.run_id+'-'+n.DOMAINS[i-1];row[candidate]=ct
   self._value['rounds'].append(row)
  self.frozen=a.canonical(self._value)
 def public(self):return a.strict(self.frozen)
 def scope(self,p):return self.scope_owner.path(p)
 def check(self):a.require(self.public()['sources']==cap.source_map(),'SOURCE_DRIFT')
 def validate(self,ct,*,allow_cold=False):
  self.check();a.require(not allow_cold and ct in [ct for row in self.public()['rounds'] for ct in row.values()] and ct['experiment']['owner']==a.OWNER,'FROZEN_COMPAT_CONTRACT')
 def contract(self,i,candidate):return self.public()['rounds'][i-1][candidate]
 def folder(self,ct):self.validate(ct);return self.scope(self.root/'runs'/ct['experiment']['run_id'])
 def once(self,p,x):
  p=self.scope(p);p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(a.canonical(x));f.flush();os.fsync(f.fileno())
class Sandbox(OrderSandbox):
 def __init__(self,ctx,ct):
  ctx.validate(ct);self.contracts=Bridge(ctx,ct);self.owner=a.OWNER;self.storage_task=a.OWNER;self.directory=ctx.scope(ctx.folder(ct)/'business');self.path=ctx.scope(self.directory/'orders.sqlite3');self.created=False;self.generation=0
class OwnedOrderPort(OrderPort):
 def prepare(self,ctx,ct,ledger):
  self.prepare_common(ctx,ct,ledger);self.sandbox=Sandbox(ctx,ct);self.reader=Reader(self.sandbox);self.adapter=OrderAdapter(self.sandbox);t=ledger.reserve('sqlite_setup');self.sandbox.initialize();ledger.settle(t,status='CREATED');self.before=self.authority('BEFORE')
def adapter(domain):
 a.typed(domain,'TARGET');return ConfigPort() if domain==n.DOMAINS[0] else OwnedOrderPort()
def verify_domain(ctx,ct,e):
 a.require(e['contract']==ct and all(e['cleanup'].values()) and all(e['sdk']['cleanup'].values()),'DOMAIN_CLEANUP');domain=ct['experiment']['domain'];lost=ct['experiment']['fault_enabled'];a.require(e['fault']==dict.fromkeys(('planned','triggered','observed','agent_exposed'),lost),'FAULT_FOUR_STATES');trace=e['trace'];expected=list(n.TOOLS[domain][:3 if domain==n.DOMAINS[0] else 2]);a.require([z['name'] for z in trace]==expected+([n.TOOLS[domain][0 if domain==n.DOMAINS[0] else 2]] if lost else []),'TOOL_ORDER')
 if domain==n.DOMAINS[0]:
  from .pge_r68_verify import verify_domain as native_config_verify
  native_config_verify(ctx.public(),ct,e)
 else:
  b=e['business'];a.require(b['oracle']==evaluate_order_effect(ct['effect'],ct['experiment']['environment_id'],b['before']['data'],b['after']['data']) and b['oracle']['contract_outcome']=='CONTRACT_SATISFIED_IN_RUN','ORDER_ORACLE')
  for snap in (b['before'],b['after']):
   d=snap['data'];a.require(snap['sha256']==a.digest(d) and d['environment']['owner']==a.OWNER and d['environment']['run_id']==ct['experiment']['run_id'] and d['environment']['environment_id']==ct['experiment']['environment_id'] and d['environment']['reset_generation']==0 and d['source_id']==ct['effect']['authority_id'],'ORDER_AUTHORITY')
  a.require(len(b['after']['data']['receipts'])==1 and b['after']['data']['receipts'][0]['amount_minor']==2500,'SINGLE_REFUND')
 sdk=e['sdk'];a.require(sdk['child_sha256']==ctx.public()['sources']['runtime/runproof_runtime/effectwitness/pge_r68_sdk_child.py']['raw'] and sdk['pid']==sdk['report']['pid']==sdk['ready']['pid'] and sdk['report']['status']=='COMPLETED' and not sdk['report']['guard_denials'] and not sdk['report']['provider_key_present'],'SDK_IDENTITY')
 a.require(len(sdk['requests'])==len(trace)+1 and sdk['report']['requests']==len(sdk['requests']) and sdk['report']['tool_calls']==sdk['report']['tool_callbacks']==len(trace),'SDK_COUNTS')
 for j,row in enumerate(sdk['requests']):
  q=row['request'];r=row['response'];budget.decide(domain,'TARGET',q['ordinal'],q['input_upper'],q['output_cap']);a.require(q['ordinal']==j+1 and q['tool_returns']==[dict(call_id=t['call_id'],result_sha256=t['result_sha256']) for t in trace[:j]],'TOOL_REINJECTION');u=r['usage'];a.require(all(type(x) is int and x>=0 for x in u.values()) and u['total_tokens']==u['prompt_tokens']+u['completion_tokens'] and u['prompt_tokens']<=q['input_upper'] and u['completion_tokens']<=q['output_cap'],'SYNTHETIC_USAGE')
  if j:a.require(q['previous_prompt']==sdk['requests'][j-1]['response']['usage']['prompt_tokens'] and q['input_upper']==q['previous_prompt']+q['suffix_bytes']+512 and q['framing_guard']==512,'SUFFIX_BOUND')
  else:a.require(q['input_upper']==q['canonical_bytes'] and q['previous_prompt'] is None,'INITIAL_BOUND')
 a.require(sdk['report']['input_tokens']==sum(r['response']['usage']['prompt_tokens'] for r in sdk['requests']) and sdk['report']['output_tokens']==sum(r['response']['usage']['completion_tokens'] for r in sdk['requests']),'SDK_USAGE_SUM')
 return True
def late(ctx):
 import ctypes,datetime
 api=ctypes.WinDLL('kernel32',use_last_error=True);api.OpenProcess.restype=ctypes.c_void_p
 class FT(ctypes.Structure):_fields_=[('lo',ctypes.c_uint32),('hi',ctypes.c_uint32)]
 events=Ledger(ctx).read()['events'];rows=[]
 for e in events:
  if e['kind']!='PROCESS_START':continue
  h=api.OpenProcess(0x1000,False,e['pid']);gone=False;status='UNAVAILABLE'
  if not h:gone=ctypes.get_last_error()==87;status='NOT_PRESENT' if gone else 'UNAVAILABLE'
  else:
   try:
    code=ctypes.c_uint32();ok=api.GetExitCodeProcess(ctypes.c_void_p(h),ctypes.byref(code));f=[FT() for _ in range(4)];oktime=api.GetProcessTimes(ctypes.c_void_p(h),*[ctypes.byref(z) for z in f]);created=((f[0].hi<<32)+f[0].lo)/1e7-11644473600 if oktime else 0;expected=e.get('started_unix_ns',0)/1e9 or time.time()+(e['clock']-time.monotonic_ns())/1e9;gone=bool(ok and code.value!=259 or created>expected+5);status='EXITED_OR_REUSED' if gone else 'PRESENT_OR_UNAVAILABLE'
   finally:api.CloseHandle(ctypes.c_void_p(h))
  rows.append(dict(pid=e['pid'],resource=e['resource'],original_gone=gone,status=status))
 ports=[]
 for port in ctx.public()['ports']:
  with socket.socket() as s:s.settimeout(.2);closed=s.connect_ex(('127.0.0.1',port))!=0
  ports.append(dict(port=port,closed=closed))
 return dict(status='PASS' if all(z['original_gone'] for z in rows) and all(z['closed'] for z in ports) else 'UNAVAILABLE',processes=rows,ports=ports,queried_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
def run_session(fault):
 a.require(type(fault) is bool,'SCENARIO');task=ROOT/'.local/rpf-69';claim=task/('fault-attempt.json' if fault else 'normal-attempt.json')
 with claim.open('xb') as f:f.write(a.canonical(dict(source_kind=a.KIND,provider=0)))
 scope=cap.OwnerScope('r69-'+secrets.token_hex(8));ports=[]
 while len(ports)<3:
  with socket.socket() as s:s.bind(('127.0.0.1',0));p=s.getsockname()[1]
  if p not in ports:ports.append(p)
 ctx=Context(scope,ports);ctx.root.mkdir(parents=True);ctx.once(ctx.root/'context.json',ctx.public());l=Ledger(ctx,create=True);_,old=n.helpers();jar=ctx.scope(ctx.root/'jar/config-center-server-1.0.0.jar');jar.parent.mkdir();a.require(a.sha(old.SOURCE_JAR.read_bytes())==n.SOURCE_JAR_SHA256,'JAR_PIN')
 with old.SOURCE_JAR.open('rb') as src,jar.open('xb') as dst:shutil.copyfileobj(src,dst)
 rows=[];start=time.monotonic();session=l.reserve('session')
 for i,domain in enumerate(n.DOMAINS,1):
  a.require(time.monotonic()-start<1200,'SESSION_DEADLINE');capsule=cap.create(domain,'TARGET',scope.run_id);choice=explorer.choose(ctx,l,i,rows,fixture=n.CANDIDATES[i-1][int(fault)]);ct=ctx.contract(i,choice['candidate_id']);port=adapter(domain);trial=l.reserve('trial',domain=domain,round=i);l.append('PORT_ENTERED',domain=domain,round=i,port_class=type(port).__module__+'.'+type(port).__qualname__,port_source_sha256=cap.source_map()['runtime/runproof_runtime/effectwitness/'+type(port).__module__.split('.')[-1]+'.py']['raw']);d=driver.Driver(ctx,l,ct,fixture=True);prepared=False
  try:port.prepare(ctx,ct,l);prepared=True;sdk=d.run(port);business=port.finish()
  finally:
   if prepared or hasattr(port,'proc'):cleanup=port.cleanup()
  e=dict(contract=ct,trace=port.trace,fault=port.fault,sdk=sdk,business=business,cleanup=cleanup);verify_domain(ctx,ct,e);l.settle(trial,status='VERIFIED');seq=len(l.frames);l.append('DOMAIN_VERIFIED',domain=domain,round=i,evidence_sha256=a.digest(e),contract_sha256=a.digest(ct),oracle=business['oracle']);fb=explorer.feedback(ct,e,choice,seq);l.append('FEEDBACK_FROZEN',domain=domain,round=i,feedback=fb,feedback_sha256=a.digest(fb));rows.append(dict(choice=choice,evidence=e,feedback=fb,capsule=capsule.public()))
 l.settle(session,status='COMPLETED');l.append('SESSION_COMPLETE',rounds=2);state=l.read();oslate=late(ctx);a.require(oslate['status']=='PASS','OS_CLEANUP');a.require(state['counts']['provider']==0 and not state['unknown'] and not state['blocked'] and set(state['tickets'])==set(state['results']),'SETTLEMENT')
 result=dict(source_kind=a.KIND,status='COMPATIBILITY_PASS',owner=a.OWNER,source_identity=cap.identity(),compat_context_hash=a.digest(ctx.public()),context=ctx.public(),frames=l.frames,rounds=rows,counts=state['counts'],provider_calls=0,provider_usage=0,key_lookup=0,wrapped_native_business=True,native_r68_shared_session_rerun=False,CORE_MIGRATED='NO',late=oslate,elapsed_seconds=time.monotonic()-start)
 ctx.once(ctx.root/'compatibility-result.json',result);return result
def manifest(rows):return dict(schema='rpf69-compatibility-manifest-v0',source_kind=a.KIND,identity=cap.identity(),sessions=rows,provider_calls=0,provider_usage=0,key_lookup=0,CORE_MIGRATED='NO')
def verify(m):
 a.require(set(m)=={'schema','source_kind','identity','sessions','provider_calls','provider_usage','key_lookup','CORE_MIGRATED'},'MANIFEST_FIELDS');a.require(m['schema']=='rpf69-compatibility-manifest-v0' and m['source_kind']==a.KIND and m['identity']==cap.identity() and m['CORE_MIGRATED']=='NO','MANIFEST_IDENTITY');a.require(all(type(m[k]) is int and m[k]==0 for k in ('provider_calls','provider_usage','key_lookup')),'ZERO_PROVIDER');a.require(len(m['sessions'])==2,'TWO_SCENARIOS');seen=set()
 for result in m['sessions']:
  ctx=result['context'];scope=cap.OwnerScope(ctx['session_id']);expected=Context(scope,ctx['ports']);a.require(a.canonical(ctx)==a.canonical(expected.public()) and result['compat_context_hash']==a.digest(ctx) and result['source_identity']==cap.identity(),'CONTEXT_IDENTITY');state=__import__(__package__+'.pge_r68_budget',fromlist=['replay']).replay(result['frames'],ctx);a.require(not state['unknown'] and not state['blocked'] and set(state['tickets'])==set(state['results']) and state['counts']==result['counts'] and state['counts']['provider']==0 and result['provider_calls']==result['provider_usage']==result['key_lookup']==0,'WAL_SETTLEMENT');a.require(result['wrapped_native_business'] is True and result['native_r68_shared_session_rerun'] is False and result['CORE_MIGRATED']=='NO' and result['source_kind']==a.KIND and result['status']=='COMPATIBILITY_PASS' and result['late']['status']=='PASS','COMPAT_NOT_REAL')
  a.require(len(result['rounds'])==2,'TWO_DOMAINS');events=state['events'];prior=[]
  a.require(sum(z['kind']=='OWNER' for z in events)==1 and events[-1]['kind']=='SESSION_COMPLETE' and state['counts']['session']==1 and state['counts']['trial']==2 and state['counts']['sdk']==state['counts']['host']==2 and state['counts']['jvm']==state['counts']['sqlite_setup']==state['counts']['sqlite_refund']==1 and state['counts']['config_post']==state['counts']['explorer_calls']==2,'RESOURCE_COMPLETION')
  requests=[z for z in events if z['kind']=='MODEL_REQUEST'];responses=[z for z in events if z['kind']=='MODEL_RESPONSE'];a.require(len(requests)==len(responses),'MODEL_COUNT')
  for req,res in zip(requests,responses):
   a.require(all(req[k]==res[k] for k in ('role','domain','round','cold','ticket')),'MODEL_SCOPE');parsed=[z for z in events if z['kind']=='PARSED' and z['receipt_id']==str(req['round'])+'-'+req['role'].lower()+'-'+str(req['request']['ordinal'])];a.require(len(parsed)==1 and parsed[0]['usage_confidence']=='SYNTHETIC_VALIDATED_USAGE' and parsed[0]['proof_sha256']==a.digest(res['response']),'PARSED_BINDING')
   shape=[z for z in events if z['kind']=='SHAPE' and z['receipt']['request_sha256']==req['request']['request_sha256']];a.require(len(shape)==1 and shape[0]['receipt']['raw_sha256']==res['response']['raw_sha256'] and events.index(req)<events.index(shape[0])<events.index(parsed[0])<events.index(res),'SHAPE_BINDING')
  for i,row in enumerate(result['rounds'],1):
   e=row['evidence'];ct=e['contract'];domain=n.DOMAINS[i-1];a.require(ct in ctx['rounds'][i-1].values() and ct['experiment']['domain']==domain,'DOMAIN_CONTRACT');cap.validate(row['capsule']);a.require(row['capsule']['domain']==domain and row['capsule']['role']=='TARGET' and row['capsule']['run_id']==scope.run_id and row['capsule']['environment_id']==ct['experiment']['environment_id'],'CAPSULE_SCOPE');verify_domain(expected,ct,e);choice=row['choice'];a.require(choice['domain']==domain and choice['round']==i and choice['candidate_id']==ct['experiment']['candidate_id'] and choice['response']['call']['arguments']==dict(candidate_id=choice['candidate_id']) and choice['selection']['id']==choice['response']['call']['call_id'],'CHOICE_BINDING');a.require(e['sdk']['requests']==[dict(request=q['request'],response=r['response']) for q,r in zip(requests,responses) if q['role']=='TARGET' and q['round']==i],'SDK_WAL_BINDING');body=explorer.body_for(expected,i,prior);a.require(choice['request']['request_sha256']==a.digest(body) and choice['request']['input_upper']==len(a.canonical(body)),'VERIFIED_FEEDBACK_INPUT');dv=next(j for j,z in enumerate(events) if z['kind']=='DOMAIN_VERIFIED' and z['round']==i);fb=explorer.feedback(ct,e,choice,dv);a.require(row['feedback']==fb and any(z['kind']=='DOMAIN_VERIFIED' and z['evidence_sha256']==a.digest(e) for z in events),'ORACLE_WAL_BINDING');a.require(events.index(next(z for z in events if z['kind']=='CHOICE' and z['round']==i))<dv,'FEEDBACK_ORDER');a.require(i==1 or next(j for j,z in enumerate(events) if z['kind']=='FEEDBACK_FROZEN' and z['round']==1)<events.index(next(z for z in events if z['kind']=='CHOICE' and z['round']==2)),'SECOND_AFTER_VERIFIED');seen.add(ct['experiment']['candidate_id']);prior.append(row)
 a.require(seen==set(n.CANDIDATES[0]+n.CANDIDATES[1]),'FOUR_CANDIDATES');return dict(status='COMPATIBILITY_PASS',provider_calls=0,provider_usage=0,CORE_MIGRATED='NO')
def cli(argv=None):
 p=argparse.ArgumentParser();p.add_argument('path');p.add_argument('--sha256');args=p.parse_args(argv)
 if not args.sha256:print('EXTERNAL_RAW_ANCHOR_REQUIRED');return 2
 try:raw=Path(args.path).read_bytes();a.require(a.sha(raw)==args.sha256,'EXTERNAL_RAW_ANCHOR');print(a.canonical(verify(a.strict(raw))).decode());return 0
 except (ValueError,KeyError,TypeError,IndexError,OSError):print('REJECTED:MANIFEST');return 3

"""RPF-63 frozen two-role configuration protocol and one physical append-only WAL."""
from __future__ import annotations
import copy,hashlib,os,re,time
from pathlib import Path
from .config_live_contracts import canonical,digest,strict_json,require,TOOLS,TOOL_HELP,AGENT_INSTRUCTIONS,TASK_PROMPT,SOURCE_COMMIT,SOURCE_MANIFEST_SHA256,SOURCE_JAR_SHA256,SOURCE_JAR_BYTES,SDK_CORE_SHA256
from .config_experiment_verify import pinned_sdk_fields
ROOT=Path(__file__).resolve().parents[3]
WORK=ROOT/'.local/rpf-63'
BASE='68572c05a52ff2258f50fb7c4488bff8e69ea61c'
BRANCH='codex/rpf-63-real-explorer-target-shared-config-pge'
SCHEMA='rpf63-dual-agent-evidence-v1'
MODEL='deepseek-flash'
CANDIDATES=('normal','local-delivery-suppressed-after-http200')
LIMITS={'metadata':2,'cold':1,'session':1,'trial':2,'jvm':2,'sdk':2,'provider':12,'http':24,'post':4,'health':6}
TARGET_CAPS=(3000,2400,2400,2400,2400)
EXPLORER_CAP=2400
PRICE={'checked_date':'2026-10-21','input_cny_per_million_bound':4.5,'output_cny_per_million_bound':18.0,'basis':'USD_0.30_1.20_TIMES_15_GUARD_NOT_FX_OR_INVOICE','sources':['https://api-docs.deepseek.com/quick_start/pricing/','https://api-docs.deepseek.com/guides/tool_calls/']}
BOUNDARIES={'domain':'CONFIG_ONLY','web':'NOT_INTEGRATED','authority':'SAME_SERVICE_READ_ONLY_HTTP','issuer':'NOT_PROVEN','independent_reproduction':'NOT_RUN','causal_advantage':'NOT_PROVEN','production':'NOT_PROVEN','orders_target':'NOT_RUN'}
RECOVERY_INSTRUCTIONS=' After update_config_v2 returns UNKNOWN_OUTCOME, never call either write tool again. You may call inspect_config once for read-only recovery, then stop. Unknown is not a successful acknowledgement.'
UNKNOWN={'status':'UNKNOWN_OUTCOME','reason':'LOCAL_SUCCESS_DELIVERY_SUPPRESSED','write_policy':'STOP_WRITES_READ_ONLY_RECONCILE'}
NEW_FILES=tuple('runtime/runproof_runtime/effectwitness/pge_dual_'+n+'.py' for n in ('contracts','config_port','session','verify'))+('runtime/tests/test_effectwitness_pge_dual.py','spikes/rpf-63/probe.py')
OLD_FILES=tuple('runtime/runproof_runtime/effectwitness/'+n+'.py' for n in ('config_live_contracts','config_live_runtime','config_live_external','config_live_verify','config_experiment_verify','config_experiment_contracts','contracts','pge_select_explorer','pge_select_contracts','pge_select_feedback'))+('spikes/rpf-53/probe.py','spikes/rpf-55/probe.py')
def sources():return {p:hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in NEW_FILES+OLD_FILES}
def scoped(path):
 p=Path(path);require(p.is_absolute() and p.resolve().is_relative_to(WORK.resolve()) and not any(x.is_symlink() or getattr(x,'is_junction',lambda:False)() for x in (p,*p.parents)),'TASK_PATH');return p
def once(path,value):
 path=scoped(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
def capability(sdk,source_sha,*,fixture=False):
 require(sdk==pinned_sdk_fields() and re.fullmatch('[0-9a-f]{64}',source_sha) is not None,'CAPABILITY_IDENTITY')
 return {'schema':'rpf63-target-capability-v1','driver_kind':'CONFIG_PINNED_PYDANTIC_AI','agent_version':'rpf63-config-target-v1','tool_allowlist':list(TOOLS),'sdk_identity':sdk,'provider_role':'TARGET','model':MODEL,'source_kind':'FIXTURE_SCRIPTED' if fixture else 'REAL_TARGET_PROVIDER','resource_budgets':LIMITS,'request_caps':list(TARGET_CAPS),'source_sha256':source_sha,'reconcile_policy':'STOP_WRITES_READ_ONLY_RECONCILE'}
def validate_capability(value):require(value==capability(value['sdk_identity'],value['source_sha256'],fixture=value['source_kind']=='FIXTURE_SCRIPTED'),'CAPABILITY')
def contract(suffix,java_port,host_port,source_sha,candidate,*,fixture=False):
 require(re.fullmatch('63[0-9a-f]{16}',suffix) is not None and candidate in CANDIDATES and type(java_port) is int and type(host_port) is int and 1024<=java_port<=65535 and 1024<=host_port<=65535 and java_port!=host_port,'CONTRACT_ID')
 cap=capability(pinned_sdk_fields(),source_sha,fixture=fixture)
 ex={'schema':'rpf63-execution-v1','owner':'rpf-63','role':'TARGET','agent_id':'rpf63-target-'+suffix,'model_source':'FIXTURE_SCRIPTED' if fixture else 'REAL_PROVIDER','framework':{'name':'pydantic-ai-slim','version':'2.57.0','openai_version':'3.35.1','identity':cap['sdk_identity']},'agent_instructions':AGENT_INSTRUCTIONS+RECOVERY_INSTRUCTIONS,'task_prompt':TASK_PROMPT+RECOVERY_INSTRUCTIONS,'tool_help':TOOL_HELP,'tools':list(TOOLS),'service':{'host':'127.0.0.1','port':java_port},'agent_host':{'host':'127.0.0.1','port':host_port},'release_authority':'NOT_HELD_BY_AGENT'}
 effect={'schema':'rpf63-effect-v1','app':'rpf63app'+suffix,'env':'rpf63local'+suffix,'key':'rpf63.item.'+suffix,'initial_state':'ABSENT','initial_value':'rpf53-v1','required_value':'rpf53-v2','initial_version':1,'required_version':2,'history_versions':[2,1]}
 exp={'schema':'rpf63-experiment-v1','owner':'rpf-63','domain':'config-java-http','run_id':'rpf63-'+suffix,'suffix':suffix,'base':BASE,'branch':BRANCH,'runtime_source_sha256':source_sha,'candidate_id':candidate,'fault_plan':{'planned':candidate==CANDIDATES[1],'enabled':candidate==CANDIDATES[1],'kind':'LOCAL_DELIVERY_SUPPRESSION_AFTER_HTTP_200' if candidate==CANDIDATES[1] else 'NONE','tool':'update_config_v2','max_activations':int(candidate==CANDIDATES[1]),'channel':'EXPLICIT_UNKNOWN_TOOL_RESULT' if candidate==CANDIDATES[1] else 'NONE'},'source':{'commit':SOURCE_COMMIT,'manifest_sha256':SOURCE_MANIFEST_SHA256,'jar_sha256':SOURCE_JAR_SHA256,'jar_bytes':SOURCE_JAR_BYTES,'task_jar':'.local/rpf-63/jar/config-center-server-1.0.0.jar'},'execution_sha256':digest(ex),'effect_sha256':digest(effect)}
 return {'schema':'rpf63-config-target-contracts-v1','capability':cap,'execution':ex,'effect':effect,'experiment':exp}
def validate_contract(v):
 x,e=v['experiment'],v['execution'];require(v==contract(x['suffix'],e['service']['port'],e['agent_host']['port'],x['runtime_source_sha256'],x['candidate_id'],fixture=e['model_source']=='FIXTURE_SCRIPTED'),'FROZEN_CONTRACT')
def plan(sid,rounds,*,synthetic=False):
 require(re.fullmatch('rpf63-session-[0-9a-f]{16}',sid) is not None and len(rounds)==2,'SESSION_ID')
 for row in rounds:
  require(set(row)==set(CANDIDATES),'CATALOG')
  for key,ct in row.items():validate_contract(ct);require(ct['experiment']['candidate_id']==key,'CANDIDATE_MAPPING')
 require(all(row[CANDIDATES[0]]['effect']==row[CANDIDATES[1]]['effect'] for row in rounds),'CANDIDATE_NAMESPACE')
 require(rounds[0][CANDIDATES[0]]['effect']['key']!=rounds[1][CANDIDATES[0]]['effect']['key'],'FRESH_ROUND_NAMESPACE')
 return {'schema':'rpf63-session-v1','session_id':sid,'base':BASE,'branch':BRANCH,'source_files':sources(),'rounds':rounds,'catalog':list(CANDIDATES),'limits':LIMITS,'target_caps':list(TARGET_CAPS),'explorer_cap':EXPLORER_CAP,'token_pool':30000,'cost_micro_cny':540000,'price':PRICE,'source_kind':'SYNTHETIC_TEST_ONLY' if synthetic else 'REAL_EXPLORER_REAL_TARGET','boundaries':BOUNDARIES}
def validate_plan(p):require(p==plan(p['session_id'],p['rounds'],synthetic=p['source_kind']=='SYNTHETIC_TEST_ONLY'),'FROZEN_PLAN')
def replay(frames):
 require(type(frames) is list and bool(frames),'WAL_MISSING');prev=None;events=[];counts={k:0 for k in LIMITS};tickets={};results={};pool=False;spent=0;roles={};unknown=False
 for i,f in enumerate(frames):
  require(set(f)=={'seq','previous','event','sha256'} and f['seq']==i and f['previous']==prev and f['sha256']==digest({k:v for k,v in f.items() if k!='sha256'}),'WAL_CHAIN')
  e=f['event'];require(type(e.get('monotonic_ns')) is int and (not events or events[-1]['monotonic_ns']<=e['monotonic_ns']),'WAL_TIME')
  if i==0:require(e['kind']=='OWNER' and e['owner']=='rpf-63' and e['base']==BASE,'WAL_OWNER')
  require(e['monotonic_ns']-frames[0]['event']['monotonic_ns']<=2400*10**9,'DEADLINE')
  if e['kind']=='TOKEN_POOL':require(not pool and e['tokens']==30000 and e['cost_micro_cny']==540000,'POOL_REWRITE');pool=True
  if e['kind']=='RESERVE':
   r=e['resource'];require(r in counts and e['ticket'] not in tickets,'TICKET');require(not unknown or r=='http' and e.get('method')=='GET','UNKNOWN_STOP');counts[r]+=1;require(counts[r]<=LIMITS[r],'RESOURCE_LIMIT')
   if r not in ('metadata','cold'):require(pool,'POOL_REQUIRED')
   if r=='provider':
    require(all(t in results for t,x in tickets.items() if x['resource']=='provider'),'UNKNOWN_USAGE_STOP');role=e['role'];rd=e['round'];require(role in ('EXPLORER','TARGET') and rd in (1,2),'ROLE_ROUND');key=(role,rd);roles[key]=roles.get(key,0)+1
    cap=EXPLORER_CAP if role=='EXPLORER' else TARGET_CAPS[roles[key]-1] if roles[key]<=5 else 0
    require(e['token_upper']==cap and e['input_upper']+e['output_cap']<=cap,'REQUEST_BOUND');require(roles[key]<=(1 if role=='EXPLORER' else 5),'ROLE_LIMIT');spent+=cap;require(spent<=30000,'TOKEN_RESERVATION_LIMIT')
   tickets[e['ticket']]=e
  if e['kind']=='RESULT':
   require(e['ticket'] in tickets and e['ticket'] not in results,'RESULT_REPLAY');results[e['ticket']]=e
   if e.get('unknown'):unknown=True
  events.append(e);prev=digest(f)
 return {'events':events,'reserved':counts,'results':results,'tickets':tickets,'pool':pool,'reserved_tokens':spent,'unknown':unknown}
class TaskLedger:
 def __init__(self,path,*,create=False):
  self.path=scoped(path)
  if create:self.path.mkdir(exist_ok=False);self.append('OWNER',owner='rpf-63',base=BASE,source_sha256=digest(sources()))
  self.read()
 def read(self):
  raw=(self.path/'ledger.jsonl').read_bytes();require(raw.endswith(b'\n'),'TORN_WAL');self.frames=[strict_json(x) for x in raw.splitlines()];return replay(self.frames)
 def append(self,kind,**data):
  lock=self.path/'mutation.lock'
  with lock.open('xb'):pass
  try:
   wal=self.path/'ledger.jsonl';frames=[]
   if wal.exists():frames=self.read() and self.frames
   e={'kind':kind,'monotonic_ns':time.monotonic_ns(),**copy.deepcopy(data)};f={'seq':len(frames),'previous':digest(frames[-1]) if frames else None,'event':e};f['sha256']=digest(f);replay(frames+[f])
   with wal.open('ab') as stream:stream.write(canonical(f)+b'\n');stream.flush();os.fsync(stream.fileno())
   self.frames=frames+[f];return e
  finally:lock.unlink()
 def reserve(self,resource,**data):
  require(self.read()['events'][0]['source_sha256']==digest(sources()),'SOURCE_DRIFT');ticket=resource+'-'+str(self.read()['reserved'][resource]+1);self.append('RESERVE',resource=resource,ticket=ticket,**data);return ticket
 def settle(self,ticket,**data):self.append('RESULT',ticket=ticket,**data)
 def token_pool(self):self.append('TOKEN_POOL',tokens=30000,cost_micro_cny=540000)

"""Explicit immutable task capability, physical WAL, and owned process lifecycle."""
from __future__ import annotations
import copy,hashlib,os,re,subprocess,time
from dataclasses import dataclass
from pathlib import Path
from .config_live_contracts import canonical,digest,strict_json,require,TOOLS,TOOL_HELP,AGENT_INSTRUCTIONS,TASK_PROMPT,SOURCE_JAR_SHA256,SOURCE_JAR_BYTES,SOURCE_MANIFEST_SHA256,SOURCE_COMMIT,SDK_CORE_SHA256
from .config_experiment_verify import pinned_sdk_fields
ROOT=Path(__file__).resolve().parents[3]
BASE='7896e9789015da946b5a057c620b2faa90b57318'
BRANCH='codex/rpf-64-stable-target-context-port-contract'
DOMAINS=('order-refund','config-java-http')
ABI='rpf64-domain-port-v1'
LIMITS={'provider':0,'metadata':2,'cold':1,'session':1,'trial':2,'order_trial':1,'config_trial':1,'sqlite_setup':1,'sqlite_refund':1,'jvm':1,'sdk':1,'http':12,'post':2,'health':3}
BOUNDARIES={'explorer':'NOT_RUN','provider':0,'tokens':0,'cost_cny':0,'causality':'NOT_PROVEN','issuer':'NOT_ESTABLISHED','independent_reproduction':'NOT_TESTED','web':'NOT_INTEGRATED','cross_domain_information_gain':'NOT_COMPARABLE'}
UNKNOWN={'status':'UNKNOWN_OUTCOME','reason':'LOCAL_SUCCESS_DELIVERY_SUPPRESSED','write_policy':'STOP_WRITES_READ_ONLY_RECONCILE'}
RECOVERY=' After UNKNOWN_OUTCOME, never call either write tool again. You may call inspect_config once for read-only recovery, then stop.'
NEW_FILES=tuple('runtime/runproof_runtime/effectwitness/'+n+'.py' for n in ('pge_port_context','pge_domain_port','pge_portability_order','pge_portability_config','pge_portability_session','pge_portability_verify'))+('runtime/tests/test_effectwitness_pge_portability.py','spikes/rpf-64/probe.py')
OLD_FILES=tuple('runtime/runproof_runtime/effectwitness/'+n+'.py' for n in ('orders','contracts','effect_oracle','config_live_contracts','config_live_runtime','config_live_external','config_live_verify','config_experiment_verify','config_experiment_adapter','config_experiment_contracts'))+('spikes/rpf-53/probe.py','spikes/rpf-55/probe.py','runtime/runproof_runtime/models.py')
def sources():return {n:hashlib.sha256((ROOT/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in NEW_FILES+OLD_FILES}
def contract(domain,suffix,source,ports=(45001,45002),mode='suppressed'):
 require(domain in DOMAINS and re.fullmatch('[0-9a-f]{16}',suffix) is not None and mode in ('normal','inhibited','suppressed'),'DOMAIN_CONTRACT')
 run='rpf64-'+('order-' if domain==DOMAINS[0] else 'config-')+suffix
 x={'schema':'rpf64-experiment-v1','owner':'rpf-64','domain':domain,'run_id':run,'environment_id':'env-'+run,'reset_generation':0,'source_sha256':source,'fault':'none','fault_plan':{'planned':False,'enabled':False,'kind':'NONE'}}
 if domain==DOMAINS[0]:
  e={'schema':'rpf64-execution-v1','agent_version':'rpf64-order-deterministic-v1','source_kind':'DETERMINISTIC','tools':['inspect_order','refund_order'],'resource':'order_trial'}
  f={'schema':'rpf64-order-effect-v1','order_id':'order-'+run,'operation_id':'refund-'+run,'authority_id':'authority-'+run,'amount_minor':2500,'currency':'CNY','authority':'SQLITE_READ_ONLY_RECEIPT_READER'}
 else:
  require(len(ports)==2 and all(type(p) is int and 1024<=p<=65535 for p in ports) and ports[0]!=ports[1],'PORTS')
  e={'schema':'rpf64-execution-v1','agent_version':'rpf64-config-fixture-v1','source_kind':'FIXTURE_SCRIPTED','model_source':'FIXTURE_SCRIPTED','framework':{'name':'pydantic-ai-slim','version':'2.57.0','openai_version':'3.35.1','identity':pinned_sdk_fields()},'tools':list(TOOLS),'tool_help':TOOL_HELP,'agent_instructions':AGENT_INSTRUCTIONS+RECOVERY,'task_prompt':TASK_PROMPT+RECOVERY,'service':{'host':'127.0.0.1','port':ports[0]},'agent_host':{'host':'127.0.0.1','port':ports[1]},'release_authority':'NOT_HELD_BY_AGENT','resource':'config_trial'}
  f={'schema':'rpf64-config-effect-v1','app':'rpf64app'+suffix,'env':'rpf64local'+suffix,'key':'rpf64.item.'+suffix,'initial_state':'ABSENT','initial_value':'rpf53-v1','required_value':'rpf53-v2','initial_version':1,'required_version':2,'history_versions':[2,1],'authority':'SAME_SERVICE_READ_ONLY_HTTP'}
  x['fault_plan']={'planned':mode!='normal','enabled':mode=='suppressed','kind':'LOCAL_DELIVERY_SUPPRESSION_AFTER_HTTP_200' if mode!='normal' else 'NONE'}
 return {'schema':'rpf64-domain-contracts-v1','execution':e,'effect':f,'experiment':x}
def validate_contract(ct):
 x,e=ct['experiment'],ct['execution'];suffix=x['run_id'].rsplit('-',1)[1];fp=x['fault_plan'];mode='suppressed' if fp['enabled'] else 'inhibited' if fp['planned'] else 'normal'
 require(ct==contract(x['domain'],suffix,x['source_sha256'],(e.get('service',{}).get('port',45001),e.get('agent_host',{}).get('port',45002)),mode),'FROZEN_CONTRACT')
@dataclass(frozen=True)
class TaskContext:
 root:Path
 frozen:bytes
 def __post_init__(self):
  require(type(self.frozen) is bytes and isinstance(self.root,Path),'IMMUTABLE_CONTEXT_TYPES');p=self.public();require(set(p)=={'schema','abi','owner','session_id','workspace','sources','limits','contracts','cold_contract','boundaries','source_kind'} and p['schema']=='rpf64-task-context-v1' and p['abi']==ABI and p['owner']=='rpf-64' and (p['workspace']=='.local/rpf-64' or p['source_kind']=='SYNTHETIC_TEST_ONLY' and re.fullmatch(r'\.local/rpf-64/tests/[0-9a-f]{16}',p['workspace']) is not None) and p['limits']==LIMITS and p['boundaries']==BOUNDARIES and p['source_kind'] in ('BOTH_REAL_CONTROLLED','SYNTHETIC_TEST_ONLY'),'TASK_IDENTITY')
  require(self.root==ROOT/p['workspace'] and re.fullmatch('rpf64-session-[0-9a-f]{16}',p['session_id']) is not None,'TASK_ROOT_OR_SESSION')
  require(set(p['contracts'])==set(DOMAINS) and p['sources']==sources(),'TASK_SOURCE')
  for domain,ct in p['contracts'].items():validate_contract(ct);require(ct['experiment']['domain']==domain and ct['experiment']['source_sha256']==digest(p['sources']),'TASK_DOMAIN_SOURCE')
  validate_contract(p['cold_contract']);require(p['cold_contract']['experiment']['run_id'] not in [ct['experiment']['run_id'] for ct in p['contracts'].values()],'COLD_RUN_REUSE');self.scope(self.root)
 def public(self):return strict_json(self.frozen)
 def scope(self,path):
  p=Path(path);require(p.is_absolute() and p.resolve().is_relative_to(self.root.resolve()) and not any(x.is_symlink() or getattr(x,'is_junction',lambda:False)() for x in (p,*p.parents)),'TASK_PATH_SCOPE');return p
 def folder(self,ct):validate_contract(ct);return self.scope(self.root/'runs'/ct['experiment']['run_id'])
 def once(self,path,value):
  p=self.scope(path);p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
 def contract(self,domain):require(domain in DOMAINS,'STATIC_DOMAIN');return self.public()['contracts'][domain]
def make_context(suffix,ports,cold_ports,*,synthetic=False,mode='suppressed'):
 require(re.fullmatch('[0-9a-f]{16}',suffix) is not None,'CONTEXT_SUFFIX');sm=sources();cold_suffix=hashlib.sha256(('cold'+suffix).encode()).hexdigest()[:16]
 p={'schema':'rpf64-task-context-v1','abi':ABI,'owner':'rpf-64','session_id':'rpf64-session-'+suffix,'workspace':'.local/rpf-64'+('/tests/'+suffix if synthetic else ''),'sources':sm,'limits':LIMITS,'contracts':{d:contract(d,suffix,digest(sm),ports,mode) for d in DOMAINS},'cold_contract':contract(DOMAINS[1],cold_suffix,digest(sm),cold_ports,'suppressed'),'boundaries':BOUNDARIES,'source_kind':'SYNTHETIC_TEST_ONLY' if synthetic else 'BOTH_REAL_CONTROLLED'}
 return TaskContext(ROOT/p['workspace'],canonical(p))
def replay(frames,context):
 require(type(frames) is list and bool(frames),'WAL_MISSING');previous=None;counts={k:0 for k in LIMITS};tickets={};results={};events=[];unknown=False
 for i,f in enumerate(frames):
  require(set(f)=={'seq','previous','event','sha256'} and f['seq']==i and f['previous']==previous and f['sha256']==digest({k:v for k,v in f.items() if k!='sha256'}),'WAL_CHAIN')
  e=f['event'];require(type(e.get('monotonic_ns')) is int and (not events or events[-1]['monotonic_ns']<=e['monotonic_ns']),'WAL_ORDER')
  if i==0:require(e['kind']=='OWNER' and e['context_sha256']==digest(context) and e['owner']==context['owner'],'WAL_OWNER')
  sessions=[x for x in events if x['kind']=='RESERVE' and x['resource']=='session']
  if sessions:require(e['monotonic_ns']-sessions[0]['monotonic_ns']<=1200*10**9,'LIVE_DEADLINE')
  if e['kind']=='RESERVE':
   r=e['resource'];require(r in counts and e['ticket'] not in tickets and type(e['units']) is int and e['units']>0,'RESOURCE_FIELDS');require(not unknown or r=='http' and e.get('method')=='GET','UNKNOWN_STOP')
   require(not any(x['resource'] in ('sqlite_refund','post','provider') and t not in results for t,x in tickets.items()) or r=='http' and e.get('method')=='GET','UNRESOLVED_WRITE_STOP')
   counts[r]+=e['units'];require(counts[r]<=LIMITS[r],'RESOURCE_LIMIT');tickets[e['ticket']]=e
  if e['kind']=='RESULT':require(e['ticket'] in tickets and e['ticket'] not in results,'SETTLEMENT_REPLAY');results[e['ticket']]=e;unknown|=bool(e.get('unknown'))
  events.append(e);previous=digest(f)
 return {'events':events,'counts':counts,'tickets':tickets,'results':results,'unknown':unknown}
class Ledger:
 def __init__(self,context,path,*,create=False):
  self.context,self.path=context,context.scope(path)
  if create:self.path.mkdir(exist_ok=False);self.append('OWNER',owner=context.public()['owner'],context_sha256=digest(context.public()))
  self.read()
 def read(self):
  raw=(self.path/'ledger.jsonl').read_bytes();require(raw.endswith(b'\n'),'TORN_WAL');self.frames=[strict_json(x) for x in raw.splitlines()];return replay(self.frames,self.context.public())
 def append(self,kind,**data):
  lock=self.path/'mutation.lock'
  with lock.open('xb'):pass
  try:
   wal=self.path/'ledger.jsonl';frames=[]
   if wal.exists():self.read();frames=self.frames
   e={'kind':kind,'monotonic_ns':time.monotonic_ns(),**copy.deepcopy(data)};f={'seq':len(frames),'previous':digest(frames[-1]) if frames else None,'event':e};f['sha256']=digest(f);replay(frames+[f],self.context.public())
   with wal.open('ab') as stream:stream.write(canonical(f)+b'\n');stream.flush();os.fsync(stream.fileno())
   self.frames=frames+[f];return e
  finally:lock.unlink()
 def reserve(self,resource,*,units=1,**data):
  require(self.context.public()['sources']==sources(),'SOURCE_DRIFT');ticket=resource+'-'+str(self.read()['counts'][resource]+1);self.append('RESERVE',resource=resource,ticket=ticket,units=units,**data);return ticket
 def settle(self,ticket,**data):self.append('RESULT',ticket=ticket,**data)
class ProcessSupervisor:
 """Shared owned-child lifecycle for SDK and Java; no executable registry."""
 def __init__(self,ctx,ledger,ct,resource):self.ctx,self.ledger,self.ct,self.resource=ctx,ledger,ct,resource;self.proc=None;self.cleanup=None
 def start(self,args,env,folder,*,stdio=False):
  folder=self.ctx.scope(folder);require(self.resource in ('sdk','cold','jvm') and self.proc is None,'PROCESS_KIND');self.ticket=self.ledger.reserve(self.resource,domain=self.ct['experiment']['domain'],run_id=self.ct['experiment']['run_id'])
  self.proc=subprocess.Popen(args,cwd=folder,env=env,stdin=subprocess.PIPE if stdio else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE if stdio else subprocess.STDOUT,bufsize=0)
  self.ctx.once(folder/(self.resource+'-started.json'),{'pid':self.proc.pid,'resource':self.resource,'context_sha256':digest(self.ctx.public())});return self.proc
 def received(self,**data):self.ledger.settle(self.ticket,popen_pid=self.proc.pid,**data)
 def close(self):
  if self.proc is not None and self.proc.poll() is None:
   self.proc.terminate()
   try:self.proc.wait(timeout=15)
   except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=10)
  self.cleanup={'process_exited':self.proc is not None and self.proc.poll() is not None};self.ledger.append('PROCESS_CLEANUP',resource=self.resource,pid=self.proc.pid if self.proc else None,**self.cleanup);return self.cleanup

def helpers():
 import importlib.util
 spec=importlib.util.spec_from_file_location('rpf64_fixed_identity_helpers',ROOT/'spikes/rpf-55/probe.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module,module.old
def metadata(ctx,ledger):
 import ast,shutil
 h,old=helpers();ticket=ledger.reserve('metadata');pin=pinned_sdk_fields();direct=h.resolve_direct_python(pin)
 tree=ast.parse((ROOT/'spikes/rpf-53/probe.py').read_text(encoding='utf-8'));fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_sdk_identity');assignment=next(n for n in fn.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='script' for t in n.targets))
 script=ast.literal_eval(assignment.value).replace('base=pathlib.Path(sys.prefix,"Lib","site-packages").resolve(strict=True)','base=pathlib.Path(sys.argv[1]).resolve(strict=True); sys.path.insert(0,str(base))').replace('venv_root=pathlib.Path(sys.prefix).resolve(strict=True)','venv_root=base.parent.parent')
 folder=ctx.scope(ctx.root/'diagnostics');result=subprocess.run([str(direct),'-I','-B','-X','utf8','-c',script,str(old.SDK_SITE.resolve(strict=True)),str(direct)],cwd=folder,env=old._sdk_env(folder),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);require(result.returncode==0 and not result.stderr,'METADATA_PROCESS')
 sdk=strict_json(result.stdout);sdk['python_launcher_sha256']=old._sha_file(old.SDK_LAUNCHER);sdk.pop('base_executable_sha256',None);require(h.identity_fields(sdk)==pin and sdk['pydantic']['record_mismatches']==sdk['openai']['record_mismatches']==0,'SDK_PIN')
 source=old._verify_source_bundle();java=old._java_identity();jar=ctx.scope(ctx.root/'jar/config-center-server-1.0.0.jar');jar.parent.mkdir(exist_ok=True)
 with old.SOURCE_JAR.open('rb') as src,jar.open('xb') as dst:shutil.copyfileobj(src,dst)
 require(old._sha_file(jar)==SOURCE_JAR_SHA256 and jar.stat().st_size==SOURCE_JAR_BYTES,'JAR_PIN');value={'status':'PASS','sdk':sdk,'java':java,'source_bundle':source,'sources':sources(),'context_sha256':digest(ctx.public())};ctx.once(ctx.root/'preflight/metadata.json',value);ledger.settle(ticket,status='PASS');return value

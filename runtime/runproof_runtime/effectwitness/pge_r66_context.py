"""RPF66 dual-role task capability and nonrefundable, physical resource WAL."""
from __future__ import annotations
import ast, copy, hashlib, os, re, time
from dataclasses import dataclass
from pathlib import Path
from .config_live_contracts import canonical, digest, strict_json, require, TOOLS, TOOL_HELP, AGENT_INSTRUCTIONS, TASK_PROMPT, SOURCE_JAR_SHA256, SOURCE_JAR_BYTES, SDK_CORE_SHA256
from .config_experiment_verify import pinned_sdk_fields
from .pge_port_context import ProcessSupervisor, helpers

ROOT = Path(__file__).resolve().parents[3]
BASE = '80c76013feb3335b4df72bc33f58e7d7f71c6611'
BRANCH = 'codex/rpf-66-rev5-versioned-response-contract'
ABI = 'rpf66-config-pge-session-v5'
DOMAIN = 'config-java-http'
MODEL = 'deepseek-flash'
MODELS = (MODEL, 'DeepSeek-V4.1-Flash-1017')
REAL = 'REAL_EXPLORER_REAL_TARGET'
SYNTHETIC = 'SYNTHETIC_TEST_ONLY'
LIMITS = dict(metadata=1, cold=1, session=1, trial=2, jvm=2, sdk=2, provider=14, http=24, post=4, health=6)
CAPS = (3000, 2400, 2400, 2400, 2800, 2000)
PRICE = {'checked_date':'2026-10-23', 'url':'https://api-docs.deepseek.com/quick_start/pricing/', 'input_usd_per_million':0.3, 'output_usd_per_million':1.2, 'cny_per_usd_guard':15, 'input_micro_cny_per_token':4.5, 'output_micro_cny_per_token':18, 'is_invoice':False}
CANDIDATES = ('normal','local-delivery-suppressed-after-http200')
EXPLORER_CAP = 2500
BOUNDARIES = dict(order_real_target='NOT_RUN', cross_domain_real_dual_agent='NOT_PROVEN', web='NOT_INTEGRATED', causality='NOT_PROVEN', independent_reproduction='NOT_TESTED', issuer='NOT_ESTABLISHED', release='NOT_AUTHORIZED')
UNKNOWN = dict(status='UNKNOWN_OUTCOME', reason='LOCAL_SUCCESS_DELIVERY_SUPPRESSED', write_policy='STOP_WRITES_READ_ONLY_RECONCILE')
RECOVERY = ' After UNKNOWN_OUTCOME, never call either write tool again. You may call inspect_config once for read-only recovery, then stop.'
NEW_FILES = tuple('runtime/runproof_runtime/effectwitness/'+n+'.py' for n in ('pge_r66_context','pge_r66_explorer','pge_r66_target_config','pge_r66_session','pge_r66_verify','pge_r66_response_v5','pge_r66_completion_v5','pge_r66_sdk_child_v5')) + ('runtime/tests/test_effectwitness_pge_r66.py','spikes/rpf-66/rev-5/probe.py')

def child_identity():
    raw=(ROOT/'runtime/runproof_runtime/effectwitness/pge_r66_sdk_child_v5.py').read_bytes()
    return dict(schema='rpf66-child-v5',raw_sha256=hashlib.sha256(raw).hexdigest(),lf_sha256=hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest(),max_tokens=512)

def stage_for(ct,attempt,trace,returns,*,stop_writes):
    suppressed=ct['experiment']['fault_plan']['enabled'];terminal_attempt=5 if suppressed else 4
    names=[x['name'] for x in trace];expected=list(TOOLS)+(['inspect_config'] if suppressed else [])
    require(1<=attempt<=terminal_attempt and len(trace)==attempt-1 and names==expected[:len(trace)],'COMPLETION_TOOL_STAGE')
    require(returns==[dict(call_id=x['call_id'],result_sha256=x['result_sha256']) for x in trace],'STAGE_TOOL_RETURNS')
    terminal=attempt==terminal_attempt
    require(not terminal or (not suppressed or stop_writes),'TERMINAL_READ_ONLY')
    return dict(schema='rpf66-terminal-stage-v5',candidate_id=ct['experiment']['candidate_id'],run_id=ct['experiment']['run_id'],round=ct['experiment']['round'],attempt=attempt,completed_tools=[dict(call_id=x['call_id'],name=x['name'],result_sha256=x['result_sha256']) for x in trace],terminal=terminal,stop_writes=bool(stop_writes),outbound_max_tokens=512 if terminal else 256)

def validate_binding(b,run,attempt):
    require(set(b)=={'schema','sdk_request_sha256','outbound_request_sha256','sdk_normalized_sha256','sdk_config_sha256','outbound_config_sha256','sdk_messages_sha256','outbound_messages_sha256','sdk_requested_max_tokens','outbound_max_tokens','stage'},'REQUEST_BINDING_FIELDS')
    require(b['schema']=='rpf66-request-binding-v5' and b['sdk_requested_max_tokens']==512,'SDK_REQUEST_MAX')
    for k in ('sdk_request_sha256','outbound_request_sha256','sdk_normalized_sha256','sdk_config_sha256','outbound_config_sha256','sdk_messages_sha256','outbound_messages_sha256'):require(type(b[k]) is str and re.fullmatch('[0-9a-f]{64}',b[k]) is not None,'REQUEST_BINDING_HASH')
    require(b['sdk_config_sha256']==b['outbound_config_sha256'] and b['sdk_messages_sha256']==b['outbound_messages_sha256'],'REQUEST_CONFIG_DRIFT')
    st=b['stage'];require(set(st)=={'schema','candidate_id','run_id','round','attempt','completed_tools','terminal','stop_writes','outbound_max_tokens'} and st['schema']=='rpf66-terminal-stage-v5' and st['candidate_id'] in CANDIDATES and st['run_id']==run and st['attempt']==attempt and st['round'] in (1,2),'REQUEST_STAGE_SCOPE')
    terminal_attempt=5 if st['candidate_id']==CANDIDATES[1] else 4
    require(1<=attempt<=terminal_attempt and type(st['terminal']) is bool and st['terminal']==(attempt==terminal_attempt),'SINGLE_TERMINAL')
    expected=list(TOOLS)+(['inspect_config'] if st['candidate_id']==CANDIDATES[1] else [])
    require(len(st['completed_tools'])==attempt-1 and [x['name'] for x in st['completed_tools']]==expected[:attempt-1],'STAGE_TOOL_LINEAGE')
    require(not st['terminal'] or st['candidate_id']==CANDIDATES[0] or st['stop_writes'] is True,'TERMINAL_UNKNOWN_READBACK')
    require(st['outbound_max_tokens']==b['outbound_max_tokens']==(512 if st['terminal'] else 256),'REQUEST_STAGE_CAP')


def sources():
    pending = list(NEW_FILES) + ['spikes/rpf-53/probe.py','spikes/rpf-55/probe.py','runtime/runproof_runtime/effectwitness/pge_portability_config.py','runtime/runproof_runtime/effectwitness/config_live_external.py','spikes/rpf-53/rev-6/config-live-evidence.json']
    result = {}
    while pending:
        name = pending.pop()
        if name in result: continue
        raw = (ROOT/name).read_bytes().replace(b'\r\n', b'\n')
        result[name] = hashlib.sha256(raw).hexdigest()
        for node in ast.walk(ast.parse(raw)) if name.endswith('.py') else []:
            if isinstance(node, ast.ImportFrom) and node.module and (node.level or node.module.startswith('runtime.')):
                parent = Path(name).parent if node.level else Path('.')
                for _ in range(max(0,node.level-1)): parent=parent.parent
                candidate = (parent / (node.module.replace('.','/')+'.py')).as_posix()
                if (ROOT/candidate).is_file(): pending.append(candidate)
    return dict(sorted(result.items()))

def contract(suffix, source, ports=(45001,45002), *, cold=False, round_index=1, candidate=CANDIDATES[1]):
    require(re.fullmatch('[0-9a-f]{16}',suffix) is not None and len(ports)==2 and len(set(ports))==2 and all(type(p) is int and 1024<=p<=65535 for p in ports), 'CONTRACT_PARAMETERS')
    require(round_index in (0,1,2) and candidate in CANDIDATES and cold==(round_index==0), 'CONTRACT_ROUND')
    run = 'rpf66r5-'+('cold-' if cold else 'config-')+suffix
    return {'schema':'rpf66-domain-contracts-v2', 'execution':{'schema':'rpf66-execution-v2','role':'TARGET','agent_version':'rpf66-config-target-v2','source_kind':'FIXTURE_SCRIPTED' if cold else REAL,'model_source':'FIXTURE_SCRIPTED' if cold else 'REAL_PROVIDER','model':'rpf53-fixture-only' if cold else MODEL,'framework':{'name':'pydantic-ai-slim','version':'2.57.0','openai_version':'3.35.1','identity':pinned_sdk_fields()},'tools':list(TOOLS),'tool_help':TOOL_HELP,'agent_instructions':AGENT_INSTRUCTIONS+RECOVERY,'task_prompt':TASK_PROMPT+RECOVERY,'service':{'host':'127.0.0.1','port':ports[0]},'agent_host':{'host':'127.0.0.1','port':ports[1]},'release_authority':'NOT_HELD_BY_AGENT'}, 'effect':{'schema':'rpf66-config-effect-v2','app':'rpf66app'+suffix,'env':'rpf66local'+suffix,'key':'rpf66.item.'+suffix,'initial_state':'ABSENT','initial_value':'rpf53-v1','required_value':'rpf53-v2','initial_version':1,'required_version':2,'history_versions':[2,1],'authority':'SAME_SERVICE_READ_ONLY_HTTP'}, 'experiment':{'schema':'rpf66-experiment-v2','owner':'rpf-66','domain':DOMAIN,'run_id':run,'environment_id':'env-'+run,'reset_generation':0,'round':round_index,'candidate_id':candidate,'source_sha256':source,'fault_plan':{'planned':candidate==CANDIDATES[1],'enabled':candidate==CANDIDATES[1],'kind':'LOCAL_DELIVERY_SUPPRESSION_AFTER_HTTP_200' if candidate==CANDIDATES[1] else 'NONE'}}}

def validate_contract(ct):
    e,x=ct['execution'],ct['experiment']
    require(ct==contract(x['run_id'].rsplit('-',1)[1],x['source_sha256'],(e['service']['port'],e['agent_host']['port']),cold=e['model_source']=='FIXTURE_SCRIPTED',round_index=x['round'],candidate=x['candidate_id']), 'FROZEN_CONTRACT')

def context_public(suffix, ports, cold_ports, synthetic):
    require(re.fullmatch('[0-9a-f]{16}',suffix) is not None and len(ports)==4 and len(set((*ports,*cold_ports)))==6,'CONTEXT_PARAMETERS')
    sm=sources(); rounds=[]
    for index in (1,2):
        token=hashlib.sha256((suffix+str(index)).encode()).hexdigest()[:16]
        rounds.append({k:contract(token,digest(sm),ports[(index-1)*2:index*2],round_index=index,candidate=k) for k in CANDIDATES})
    return dict(schema='rpf66-task-context-v5',abi=ABI,owner='rpf-66',revision='rev-5',base=BASE,branch=BRANCH,session_id='rpf66r5-session-'+suffix,workspace='.local/rpf-66-rev-5'+('/tests/'+suffix if synthetic else ''),sources=sm,limits=LIMITS,caps=list(CAPS),explorer_cap=EXPLORER_CAP,price=PRICE,rounds=rounds,cold_contract=contract(suffix,digest(sm),cold_ports,cold=True,round_index=0),boundaries=BOUNDARIES,source_kind=SYNTHETIC if synthetic else REAL)

@dataclass(frozen=True)
class TaskContext:
    root: Path
    frozen: bytes
    def __post_init__(self):
        p=self.public(); synthetic=p['source_kind']==SYNTHETIC
        suffix=p['session_id'].removeprefix('rpf66r5-session-')
        ports=tuple(row[CANDIDATES[0]]['execution'][k]['port'] for row in p['rounds'] for k in ('service','agent_host'))
        cold=p['cold_contract'];cp=tuple(cold['execution'][k]['port'] for k in ('service','agent_host'))
        require(p==context_public(suffix,ports,cp,synthetic) and self.root==ROOT/p['workspace'],'CONTEXT_IDENTITY_SOURCE_ROOT')
        self.scope(self.root)
    def public(self): return strict_json(self.frozen)
    def scope(self,path):
        p=Path(path)
        require(p.is_absolute() and p.resolve().is_relative_to(self.root.resolve()) and not any(x.is_symlink() or getattr(x,'is_junction',lambda:False)() for x in (p,*p.parents)), 'TASK_PATH_SCOPE')
        return p
    def once(self,path,value):
        p=self.scope(path); p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as f: f.write(canonical(value)); f.flush(); os.fsync(f.fileno())
    def folder(self,ct): validate_contract(ct); require(self.contains(ct),'CONTEXT_CONTRACT'); return self.scope(self.root/'runs'/ct['experiment']['run_id'])
    def contract(self,index=1,candidate=CANDIDATES[1]): require(index in (1,2) and candidate in CANDIDATES,'STATIC_ROUND');return self.public()['rounds'][index-1][candidate]
    def contains(self,ct): return ct==self.public()['cold_contract'] or any(ct==self.contract(i,k) for i in (1,2) for k in CANDIDATES)
    def round_for(self,run):
        if run==self.public()['cold_contract']['experiment']['run_id']: return 0
        for i in (1,2):
            if run==self.contract(i)['experiment']['run_id']:return i
        require(False,'UNKNOWN_RUN')

def make_context(suffix,ports,cold_ports,*,synthetic=False):
    p=context_public(suffix,ports,cold_ports,synthetic); return TaskContext(ROOT/p['workspace'],canonical(p))

def replay(frames,context):
    require(type(frames) is list and bool(frames),'WAL_MISSING')
    previous=None; events=[]; counts=dict.fromkeys(LIMITS,0); tickets={}; results={}; reserved=0; cost=0; unknown=False; roles={}; per_round={}
    runs={row[CANDIDATES[0]]['experiment']['run_id']:i for i,row in enumerate(context['rounds'],1)}
    runs[context['cold_contract']['experiment']['run_id']]=0
    for i,f in enumerate(frames):
        require(set(f)=={'seq','previous','event','sha256'} and f['seq']==i and f['previous']==previous and f['sha256']==digest({k:v for k,v in f.items() if k!='sha256'}),'WAL_CHAIN')
        e=f['event']; require(type(e['monotonic_ns']) is int and (not events or e['monotonic_ns']>=events[-1]['monotonic_ns']) and e['monotonic_ns']-frames[0]['event']['monotonic_ns']<=7200*10**9,'WAL_TIME')
        if i==0:require(e['kind']=='OWNER' and e['owner']=='rpf-66' and e.get('revision')=='rev-5' and e.get('workspace')==context['workspace'] and e['context_sha256']==digest(context),'WAL_OWNER')
        sessions=[t for t in tickets.values() if t['resource']=='session']
        if sessions:require(e['monotonic_ns']-sessions[0]['monotonic_ns']<=1800*10**9,'SESSION_DEADLINE')
        if 'run_id' in e: require(e['run_id'] in runs and e.get('round')==runs[e['run_id']],'WAL_RUN_ROUND')
        if e['kind']=='RESERVE':
            r=e['resource'];require(r in counts and e['ticket']==r+'-'+str(counts[r]+1),'TICKET_SEQUENCE')
            require(not unknown or r=='http' and e.get('method')=='GET','UNKNOWN_STOP')
            unsettled=[t for k,t in tickets.items() if k not in results and t['resource'] in ('provider','post')]
            require(not unsettled or r=='http' and e.get('method')=='GET','UNSETTLED_STOP')
            counts[r]+=1;require(counts[r]<=LIMITS[r],'RESOURCE_LIMIT')
            if r not in ('metadata','session'):
                rd=e['round'];require(rd in (1,2) or r=='cold' and rd==0,'RESOURCE_ROUND')
                key=(r,rd);per_round[key]=per_round.get(key,0)+1
                cap={'trial':1,'jvm':1,'sdk':1,'http':12,'post':2,'health':3,'cold':1,'provider':7}[r]
                require(per_round[key]<=cap,'ROUND_RESOURCE_LIMIT')
            if r=='provider':
                rd=e['round'];role=e['role'];require(role in ('TARGET','EXPLORER'),'PROVIDER_ROLE')
                key=(role,rd);roles[key]=roles.get(key,0)+1;n=roles[key]
                require(n<=(6 if role=='TARGET' else 1),'ROLE_LIMIT')
                cap=CAPS[n-1] if role=='TARGET' else EXPLORER_CAP;out=e['binding']['outbound_max_tokens'] if role=='TARGET' else 128
                if role=='TARGET':validate_binding(e['binding'],e['run_id'],n);require(e['request_sha256']==e['binding']['outbound_request_sha256'],'OUTBOUND_REQUEST_BINDING')
                require(e['token_upper']==cap and e['output_cap']==out and type(e['input_upper']) is int and 0<e['input_upper'] and e['input_upper']+out<=cap,'PROVIDER_BOUND')
                require(e['cost_micro_cny_upper']==e['input_upper']*4.5+out*18,'COST_RESERVATION')
                reserved+=cap;cost+=e['cost_micro_cny_upper'];require(reserved<=35000 and cost<=750000,'POOL_EXHAUSTED')
            tickets[e['ticket']]=e
        if e['kind']=='RESULT':
            require(e['ticket'] in tickets and e['ticket'] not in results,'SETTLEMENT_REPLAY');results[e['ticket']]=e
            unknown |= bool(e.get('unknown'))
        events.append(e); previous=digest(f)
    return dict(events=events,counts=counts,tickets=tickets,results=results,unknown=unknown,reserved_tokens=reserved,reserved_cost_micro_cny=cost,roles=roles)

class Ledger:
    def __init__(self,ctx,path,*,create=False):
        self.context,self.path=ctx,ctx.scope(path)
        if create: self.path.mkdir(exist_ok=False); self.append('OWNER',owner='rpf-66',revision='rev-5',workspace=ctx.public()['workspace'],context_sha256=digest(ctx.public()))
        self.read()
    def read(self):
        raw=(self.path/'ledger.jsonl').read_bytes(); require(raw.endswith(b'\n'),'TORN_WAL'); self.frames=[strict_json(x) for x in raw.splitlines()]; return replay(self.frames,self.context.public())
    def append(self,kind,**data):
        if 'run_id' in data: data['round']=self.context.round_for(data['run_id'])
        if kind=='PROCESS_CLEANUP':
            prior=next((t for t in reversed(list(self.read()['tickets'].values())) if t['resource']==data['resource']),None)
            if prior:data.update(run_id=prior['run_id'],round=prior['round'])
        lock=self.path/'mutation.lock'
        with lock.open('xb'): pass
        try:
            wal=self.path/'ledger.jsonl'; frames=[]
            if wal.exists(): self.read(); frames=self.frames
            e=dict(kind=kind,monotonic_ns=time.monotonic_ns(),**copy.deepcopy(data)); f=dict(seq=len(frames),previous=digest(frames[-1]) if frames else None,event=e); f['sha256']=digest(f); replay(frames+[f],self.context.public())
            with wal.open('ab') as stream: stream.write(canonical(f)+b'\n'); stream.flush(); os.fsync(stream.fileno())
            self.frames=frames+[f]; return e
        finally: lock.unlink()
    def reserve(self,resource,**data):
        require(self.context.public()['sources']==sources(),'SOURCE_DRIFT'); ticket=resource+'-'+str(self.read()['counts'][resource]+1); self.append('RESERVE',resource=resource,ticket=ticket,**data); return ticket
    def settle(self,ticket,**data): self.append('RESULT',ticket=ticket,**data)

def metadata(ctx,ledger):
 import ast,shutil,subprocess
 h,old=helpers();ticket=ledger.reserve('metadata');pin=pinned_sdk_fields();direct=h.resolve_direct_python(pin)
 tree=ast.parse((ROOT/'spikes/rpf-53/probe.py').read_text(encoding='utf-8'));fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_sdk_identity');assignment=next(n for n in fn.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='script' for t in n.targets))
 script=ast.literal_eval(assignment.value).replace('base=pathlib.Path(sys.prefix,"Lib","site-packages").resolve(strict=True)','base=pathlib.Path(sys.argv[1]).resolve(strict=True); sys.path.insert(0,str(base))').replace('venv_root=pathlib.Path(sys.prefix).resolve(strict=True)','venv_root=base.parent.parent')
 folder=ctx.scope(ctx.root/'diagnostics');folder.mkdir(exist_ok=True);result=subprocess.run([str(direct),'-I','-B','-X','utf8','-c',script,str(old.SDK_SITE.resolve(strict=True)),str(direct)],cwd=folder,env=old._sdk_env(folder),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);require(result.returncode==0 and not result.stderr,'METADATA_PROCESS')
 sdk=strict_json(result.stdout);sdk['python_launcher_sha256']=old._sha_file(old.SDK_LAUNCHER);sdk.pop('base_executable_sha256',None);require(h.identity_fields(sdk)==pin and sdk['pydantic']['record_mismatches']==sdk['openai']['record_mismatches']==0,'SDK_PIN')
 source=old._verify_source_bundle();java=old._java_identity();jar=ctx.scope(ctx.root/'jar/config-center-server-1.0.0.jar');jar.parent.mkdir(exist_ok=True)
 with old.SOURCE_JAR.open('rb') as src,jar.open('xb') as dst:shutil.copyfileobj(src,dst)
 require(old._sha_file(jar)==SOURCE_JAR_SHA256 and jar.stat().st_size==SOURCE_JAR_BYTES,'JAR_PIN');value={'status':'PASS','sdk':sdk,'java':java,'source_bundle':source,'sources':sources(),'context_sha256':digest(ctx.public())};ctx.once(ctx.root/'preflight/metadata.json',value);ledger.settle(ticket,status='PASS');return value

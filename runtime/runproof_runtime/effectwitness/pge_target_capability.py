"""RPF-62 static Target seam and one append-only physical task account."""
from __future__ import annotations
import copy
import hashlib
import os
import re
import time
from pathlib import Path
from typing import Protocol
from .config_live_contracts import (canonical,digest,strict_json,require,TOOLS,TOOL_HELP,AGENT_INSTRUCTIONS,TASK_PROMPT,
    SOURCE_COMMIT,SOURCE_MANIFEST_SHA256,SOURCE_JAR_SHA256,SOURCE_JAR_BYTES,SDK_CORE_SHA256)
from .config_experiment_verify import pinned_sdk_fields
ROOT=Path(__file__).resolve().parents[3]
WORK=ROOT/'.local/rpf-62'
BASE='c5ebfb887336ca67b61270df9965f6b1ebbf2b9a'
BRANCH='codex/rpf-62-real-target-capability-spike'
SCHEMA='rpf62-real-target-witness-v1'
MODEL='deepseek-flash'
LIMITS={'metadata':2,'cold':1,'trial':1,'jvm':1,'sdk':1,'provider':6,'http':12,'post':2,'health':3}
PRICE={'checked_date':'2026-10-21','input_cny_per_million_bound':4.5,'output_cny_per_million_bound':18.0,
       'basis':'USD_PEAK_0.30_1.20_TIMES_15_GUARD_NOT_FX_OR_INVOICE','sources':['https://api-docs.deepseek.com/quick_start/pricing/','https://api-docs.deepseek.com/guides/tool_calls/']}
BOUNDARIES={'explorer':'NOT_RUN','web_live':'NOT_INTEGRATED','issuer_authenticity':'NOT_ESTABLISHED','independent_reproduction':'NOT_TESTED',
    'authority':'SAME_SERVICE_READ_ONLY_HTTP','causal_advantage':'NOT_PROVEN','production':'NOT_PROVEN','WorkSwarm':'NOT_INTEGRATED'}
RECOVERY_INSTRUCTIONS=' After update_config_v2 returns UNKNOWN_OUTCOME, never call either write tool again. You may call inspect_config once to use the Host read-only recovery path, then stop. Do not claim a successful update from an unknown acknowledgement.'
UNKNOWN={'status':'UNKNOWN_OUTCOME','reason':'LOCAL_SUCCESS_DELIVERY_SUPPRESSED','write_policy':'STOP_WRITES_READ_ONLY_RECONCILE'}
NEW_FILES=tuple('runtime/runproof_runtime/effectwitness/'+n+'.py' for n in ('pge_target_capability','pge_target_config_spike','pge_target_capability_verify'))+('runtime/tests/test_effectwitness_pge_target_capability.py','spikes/rpf-62/probe.py')
OLD_FILES=tuple('runtime/runproof_runtime/effectwitness/'+n+'.py' for n in ('config_live_contracts','config_live_runtime','config_live_external','config_live_verify','config_experiment_verify','config_experiment_contracts','contracts'))+('spikes/rpf-53/probe.py','spikes/rpf-55/probe.py')
def sources():return {p:hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in NEW_FILES+OLD_FILES}
def scoped(path):
    p=Path(path);require(p.is_absolute() and p.resolve().is_relative_to(WORK.resolve()) and not any(x.is_symlink() or getattr(x,'is_junction',lambda:False)() for x in (p,*p.parents)),'TASK_PATH')
    return p
def once(path,value):
    path=scoped(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
def capability(sdk,source_sha,*,fixture=False):
    require(sdk==pinned_sdk_fields() and re.fullmatch('[0-9a-f]{64}',source_sha) is not None,'CAPABILITY_IDENTITY')
    return {'schema':'rpf62-target-capability-v1','driver_kind':'CONFIG_PINNED_PYDANTIC_AI','agent_version':'rpf62-config-target-v1',
        'tool_allowlist':list(TOOLS),'sdk_identity':sdk,'provider_role':'TARGET','model':MODEL,
        'source_kind':'FIXTURE_SCRIPTED' if fixture else 'REAL_PROVIDER_TARGET','fault_capability':'LOCAL_DELIVERY_SUPPRESSION_AFTER_HTTP_200',
        'readback_authority_grade':'SAME_SERVICE_READ_ONLY_HTTP','resource_budgets':LIMITS,'token_pool':12000,'cost_cny_bound':0.25,
        'reconcile_policy':'STOP_WRITES_READ_ONLY_RECONCILE','source_sha256':source_sha}
def validate_capability(value):
    require(type(value) is dict and value==capability(value['sdk_identity'],value['source_sha256'],fixture=value['source_kind']=='FIXTURE_SCRIPTED'),'FROZEN_CAPABILITY')
def contract(suffix,java_port,host_port,source_sha,*,fixture=False):
    require(re.fullmatch('62[0-9a-f]{16}',suffix) is not None and type(java_port) is int and type(host_port) is int and 1024<=java_port<=65535 and 1024<=host_port<=65535 and java_port!=host_port,'CONTRACT_ID')
    cap=capability(pinned_sdk_fields(),source_sha,fixture=fixture)
    ex={'schema':'rpf62-execution-v1','owner':'rpf-62','role':'TARGET','agent_id':'rpf62-target-'+suffix,'model_source':'FIXTURE_SCRIPTED' if fixture else 'REAL_PROVIDER',
        'framework':{'name':'pydantic-ai-slim','version':'2.57.0','openai_version':'3.35.1','identity':cap['sdk_identity']},
        'agent_instructions':AGENT_INSTRUCTIONS+RECOVERY_INSTRUCTIONS,'task_prompt':TASK_PROMPT+RECOVERY_INSTRUCTIONS,'tool_help':TOOL_HELP,'tools':list(TOOLS),
        'service':{'host':'127.0.0.1','port':java_port},'agent_host':{'host':'127.0.0.1','port':host_port},'release_authority':'NOT_HELD_BY_AGENT'}
    effect={'schema':'rpf62-effect-v1','app':'rpf62app'+suffix,'env':'rpf62local'+suffix,'key':'rpf62.item.'+suffix,'initial_state':'ABSENT',
        'initial_value':'rpf53-v1','required_value':'rpf53-v2','initial_version':1,'required_version':2,'history_versions':[2,1]}
    exp={'schema':'rpf62-experiment-v1','owner':'rpf-62','run_id':'rpf62-'+suffix,'suffix':suffix,'base':BASE,'branch':BRANCH,'runtime_source_sha256':source_sha,
        'candidate_id':'local-delivery-suppressed','fault_plan':{'planned':True,'enabled':True,'kind':cap['fault_capability'],'tool':'update_config_v2','max_activations':1,'channel':'EXPLICIT_UNKNOWN_TOOL_RESULT'},
        'source':{'commit':SOURCE_COMMIT,'manifest_sha256':SOURCE_MANIFEST_SHA256,'jar_sha256':SOURCE_JAR_SHA256,'jar_bytes':SOURCE_JAR_BYTES,'task_jar':'.local/rpf-62/jar/config-center-server-1.0.0.jar'},
        'execution_sha256':digest(ex),'effect_sha256':digest(effect)}
    return {'schema':'rpf62-config-target-contracts-v1','capability':cap,'execution':ex,'effect':effect,'experiment':exp}
def validate_contract(value):
    x,e=value['experiment'],value['execution'];require(value==contract(x['suffix'],e['service']['port'],e['agent_host']['port'],x['runtime_source_sha256'],fixture=e['model_source']=='FIXTURE_SCRIPTED'),'FROZEN_CONTRACT')
class TargetCapabilityDriver(Protocol):
    def run(self,capability:dict,context:dict)->dict: ...
def replay(frames):
    previous=None;events=[];counts={k:0 for k in LIMITS};request_ids=set();results={};pool=False
    require(type(frames) is list and bool(frames),'WAL_MISSING')
    started=None
    for index,frame in enumerate(frames):
        require(set(frame)=={'seq','previous','event','sha256'} and frame['seq']==index and frame['previous']==previous and frame['sha256']==digest({k:v for k,v in frame.items() if k!='sha256'}),'WAL_CHAIN')
        e=frame['event'];require(type(e.get('monotonic_ns')) is int and (not events or e['monotonic_ns']>=events[-1]['monotonic_ns']),'WAL_TIME')
        if index==0:require(e['kind']=='OWNER' and e['owner']=='rpf-62' and e['base']==BASE,'WAL_OWNER');started=e['monotonic_ns']
        require(e['monotonic_ns']-started<=2400*10**9,'TASK_DEADLINE')
        if e['kind']=='TOKEN_POOL':require(not pool and e['tokens']==12000 and e['cost_micro_cny']==216000,'POOL_REWRITE');pool=True
        if e['kind']=='RESERVE':
            r=e['resource'];require(r in counts and e['ticket'] not in request_ids,'RESERVATION_ID');request_ids.add(e['ticket']);counts[r]+=1;require(counts[r]<=LIMITS[r],'RESOURCE_LIMIT')
            if r in ('provider','trial','jvm','sdk','http','post','health'):require(pool,'POOL_REQUIRED')
        if e['kind']=='RESULT':require(e['ticket'] in request_ids and e['ticket'] not in results,'RESULT_ID');results[e['ticket']]=e
        events.append(e);previous=digest(frame)
    return {'events':events,'reserved':counts,'results':results,'token_pool_reserved':pool}
class TaskLedger:
    def __init__(self,path,*,create=False):
        self.path=scoped(path)
        if create:
            self.path.mkdir(exist_ok=False);self.append('OWNER',owner='rpf-62',base=BASE)
        self.read()
    def read(self):
        self.frames=[strict_json(p.read_bytes()) for p in sorted(self.path.glob('frame-*.json'))];return replay(self.frames)
    def append(self,kind,**data):
        lock=self.path/'mutation.lock'
        with lock.open('xb'):pass
        try:
            frames=[strict_json(p.read_bytes()) for p in sorted(self.path.glob('frame-*.json'))]
            if frames:replay(frames)
            event={'kind':kind,'monotonic_ns':time.monotonic_ns(),**copy.deepcopy(data)}
            f={'seq':len(frames),'previous':digest(frames[-1]) if frames else None,'event':event};f['sha256']=digest(f)
            replay(frames+[f]);once(self.path/f"frame-{len(frames):04}.json",f)
            self.frames=frames+[f];return event
        finally:lock.unlink()
    def reserve(self,resource,**data):
        ticket=f'{resource}-{self.read()["reserved"][resource]+1}';self.append('RESERVE',resource=resource,ticket=ticket,**data);return ticket
    def settle(self,ticket,**data):self.append('RESULT',ticket=ticket,**data)
    def token_pool(self):self.append('TOKEN_POOL',tokens=12000,cost_micro_cny=216000)

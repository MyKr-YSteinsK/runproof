"""Explicit immutable launch ABI; historical checks never read ambient env."""
from dataclasses import dataclass
import ntpath
import os
from pathlib import Path
import re
import secrets
import subprocess
from . import pge_r73_contracts as c
from .pge_r73_budget_view import BudgetView
from .pge_r73_domain_adapters import DomainAdapter
ENV_KEYS=frozenset(('SYSTEMROOT','WINDIR','PATH','HOME','USERPROFILE','TEMP','TMP','PYTHONDONTWRITEBYTECODE','OTEL_SDK_DISABLED','LOGFIRE_SEND_TO_LOGFIRE'))
def path_id(value):return c.sha(ntpath.normcase(ntpath.normpath(value)).encode())
SYSTEM_ID=path_id('C:\\Windows')
PATH_IDS=frozenset((SYSTEM_ID,path_id('C:\\Windows\\System32')))
CASES={'development':c.DOMAINS[0],'config':c.DOMAINS[0],'order':c.DOMAINS[1],'limit':c.DOMAINS[0],'corrective-config':c.DOMAINS[0],'corrective-order':c.DOMAINS[1]}
def env_summary(env,folder):
 c.require(type(env) is dict and set(env)==ENV_KEYS,'ENV_KEYS')
 c.require(all(type(v) is str and 0<len(v)<=32768 and not any(z in v for z in '\r\n\0') for v in env.values()),'ENV_TYPES')
 c.require(not any(re.search(r'Bearer\s+|sk-[A-Za-z0-9]{16,}|api[_-]?key\s*=',v,re.I) for v in env.values()),'ENV_SECRET_SYNTAX')
 for k in ('HOME','USERPROFILE','TEMP','TMP'):c.require(env[k]==str(folder),'ENV_OWNER_DIRECTORY')
 c.require(env['PYTHONDONTWRITEBYTECODE']=='1' and env['OTEL_SDK_DISABLED']=='true' and env['LOGFIRE_SEND_TO_LOGFIRE']=='false','ENV_FLAGS')
 for k in ('SYSTEMROOT','WINDIR'):
  c.require(ntpath.isabs(env[k]) and path_id(env[k])==SYSTEM_ID,'ENV_SYSTEM_ROOT')
 c.require(all(p and ntpath.isabs(p) and '%' not in p and '..' not in p.replace('/','\\').split('\\') and not any(z in p for z in '"|&<>') and path_id(p) in PATH_IDS for p in env['PATH'].split(';')),'ENV_PATH_SCOPE')
 return dict(sha256=c.digest(env),value_sha256={k:c.sha(v.encode()) for k,v in env.items()},keys=sorted(env))
def live_environment(folder):
 # Exactly three permitted host reads. No credential lookup or presence test.
 inherited={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','PATH')}
 inherited['PATH']=';'.join(p for p in inherited['PATH'].split(';') if p and path_id(p) in PATH_IDS)
 inherited.update({k:str(folder) for k in ('HOME','USERPROFILE','TEMP','TMP')})
 inherited.update(PYTHONDONTWRITEBYTECODE='1',OTEL_SDK_DISABLED='true',LOGFIRE_SEND_TO_LOGFIRE='false')
 env_summary(inherited,folder);return inherited
@dataclass(frozen=True,slots=True)
class LaunchRequest:
 frozen:bytes
 def public(self):return c.canonical_value(self.frozen)
 @property
 def raw_sha256(self):return c.sha(self.frozen)
 @classmethod
 def build(cls,case,port,*,fixed=None):
  c.require(case in CASES,'CASE');fixed=c.fixed_paths() if fixed is None else fixed
  run='rpf73-'+secrets.token_hex(8);folder=c.scope(c.WORK/'runs'/run/'sdk');domain=CASES[case];a=DomainAdapter(domain);budget=BudgetView(domain).public();env=live_environment(folder)
  cfg=dict(port=port,token=secrets.token_hex(32),write_root=str(folder),sdk_readonly_path=fixed['site'],sdk_site_root_binding_sha256=c.PIN['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=c.PIN['python_runtime_mapping_sha256'],instructions=a.instructions(),task_prompt=a.prompt(),domain=domain,total_token_limit=budget['cumulative'])
  argv=[fixed['python'],'-I','-B','-X','utf8',fixed['child']]
  obj=dict(schema=c.ABI,owner=c.OWNER,source_kind=c.KIND,source=c.source_identity(),run_id=run,case=case,domain=domain,round=c.DOMAINS.index(domain)+1,role='TARGET',platform='WINDOWS_X64',model_source='SYNTHETIC_ONLY',cwd=str(folder),argv=argv,command=subprocess.list2cmdline(argv),shell=False,env=env,env_summary=env_summary(env,folder),cfg=cfg,cfg_raw=c.canonical(cfg).decode('ascii'),cfg_sha256=c.digest(cfg),pins=c.PIN,budget=budget,timeout_seconds=900,request_limit=5 if domain==c.DOMAINS[0] else 4,callback_limit=4 if domain==c.DOMAINS[0] else 3,pressure=case=='limit',issuer=False)
  value=cls(c.canonical(obj));value.check(fixed);return value
 def check(self,fixed):
  v=self.public();fields={'schema','owner','source_kind','source','run_id','case','domain','round','role','platform','model_source','cwd','argv','command','shell','env','env_summary','cfg','cfg_raw','cfg_sha256','pins','budget','timeout_seconds','request_limit','callback_limit','pressure','issuer'}
  c.require(type(v) is dict and set(v)==fields,'REQUEST_FIELDS')
  c.equal({k:v[k] for k in ('schema','owner','source_kind','source','pins')},dict(schema=c.ABI,owner=c.OWNER,source_kind=c.KIND,source=c.source_identity(),pins=c.PIN),'OWNER_SOURCE_PIN')
  c.require(type(v['case']) is str and v['case'] in CASES and v['domain']==CASES[v['case']],'CASE_DOMAIN')
  d=v['domain'];a=DomainAdapter(d);c.require(type(v['run_id']) is str and re.fullmatch(r'rpf73-[a-f0-9]{16}',v['run_id']),'RUN_ID')
  folder=c.scope(c.WORK/'runs'/v['run_id']/'sdk');c.require(type(v['cwd']) is str and v['cwd']==str(folder),'CWD_BINDING')
  argv=[fixed['python'],'-I','-B','-X','utf8',fixed['child']]
  c.equal(v['argv'],argv,'ARGV_BINDING');c.require(v['command']==subprocess.list2cmdline(argv),'WINDOWS_COMMAND_EXACT')
  c.equal({k:v[k] for k in ('round','role','platform','model_source','shell','timeout_seconds','request_limit','callback_limit','pressure','issuer')},dict(round=c.DOMAINS.index(d)+1,role='TARGET',platform='WINDOWS_X64',model_source='SYNTHETIC_ONLY',shell=False,timeout_seconds=900,request_limit=5 if d==c.DOMAINS[0] else 4,callback_limit=4 if d==c.DOMAINS[0] else 3,pressure=v['case']=='limit',issuer=False),'LAUNCH_POLICY')
  c.equal(v['env_summary'],env_summary(v['env'],folder),'ENV_SNAPSHOT_BINDING');BudgetView(d).check(v['budget'])
  cfg=v['cfg'];c.require(type(cfg) is dict and set(cfg)=={'port','token','write_root','sdk_readonly_path','sdk_site_root_binding_sha256','python_runtime_mapping_sha256','instructions','task_prompt','domain','total_token_limit'},'CFG_FIELDS')
  c.require(type(cfg['port']) is int and 1024<=cfg['port']<=65535 and type(cfg['token']) is str and re.fullmatch('[a-f0-9]{64}',cfg['token']),'HOST_PORT_TOKEN')
  expected=dict(port=cfg['port'],token=cfg['token'],write_root=str(folder),sdk_readonly_path=fixed['site'],sdk_site_root_binding_sha256=c.PIN['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=c.PIN['python_runtime_mapping_sha256'],instructions=a.instructions(),task_prompt=a.prompt(),domain=d,total_token_limit=BudgetView(d).public()['cumulative'])
  c.equal(cfg,expected,'ACTUAL_CFG_POLICY');c.require(type(v['cfg_raw']) is str and v['cfg_raw'].encode('ascii')==c.canonical(cfg) and len(v['cfg_raw'])<=16384 and v['cfg_sha256']==c.digest(cfg),'CFG_CANONICAL_BYTES')
  return v
@dataclass(frozen=True,slots=True)
class LaunchReceipt:
 frozen:bytes
 def public(self):return c.canonical_value(self.frozen)
 @property
 def raw_sha256(self):return c.sha(self.frozen)

def lifecycle_action(state,action):
 c.require(state in ('ADMITTED','RUNNING','COMPLETED','EXPECTED_REJECTION','UNKNOWN','CLOSED'),'LIFECYCLE_STATE')
 c.require(action in (('OS_READBACK','CLEANUP') if state in ('UNKNOWN','CLOSED','EXPECTED_REJECTION') else ('CALLBACK','COMPLETE','OS_READBACK','CLEANUP')),'STOP_AFTER_UNKNOWN')
 return True

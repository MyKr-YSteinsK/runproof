"""Immutable task-owned scope plus distinct native and new source identities."""
from pathlib import Path
from dataclasses import dataclass
from . import pge_r69_abi as a,pge_r68_context as native
ROOT=Path(__file__).resolve().parents[3]
NEW=tuple('runtime/runproof_runtime/effectwitness/pge_r69_'+x+'.py' for x in ('abi','capsule','budget','guard_audit','compat'))+('runtime/tests/test_effectwitness_pge_r69.py','spikes/rpf-69/probe.py')
GUARDS=tuple('runtime/runproof_runtime/effectwitness/'+x for x in ('pge_r66_sdk_child_v5.py','pge_r67_order_child.py','pge_r68_sdk_child.py'))
def source_map():
 names=set(native.sources())|set(NEW)|set(GUARDS);out={}
 for name in sorted(names):
  raw=(ROOT/name).read_bytes();out[name]=dict(raw=a.sha(raw),lf=a.sha(raw.replace(b'\r\n',b'\n')))
 return out
def identity():
 sm=source_map();return dict(base=a.BASE,branch=a.BRANCH,source_map=sm,source_digest=a.digest({k:v['lf'] for k,v in sm.items()}),native_source_digest=a.digest({k:v['lf'] for k,v in native.sources().items()}))
@dataclass(frozen=True)
class OwnerScope:
 run_id:str
 def __post_init__(self):a.require(type(self.run_id) is str and __import__('re').fullmatch('r69-[a-f0-9]{16}',self.run_id),'OWNER_RUN')
 @property
 def root(self):return ROOT/'.local/rpf-69/tests'/self.run_id
 def path(self,path):
  p=Path(path);a.require(p.is_absolute() and p.resolve().is_relative_to(self.root.resolve()) and not any(x.is_symlink() or x.is_junction() for x in (p,*p.parents)),'OWNER_PATH');return p
def create(domain,role,run_id):
 from .pge_r69_budget import policy
 from .pge_r69_guard_audit import guard_identity
 scope=OwnerScope(run_id);p=dict(schema=a.VERSION,source_kind=a.KIND,owner_id=a.OWNER,run_id=run_id,environment_id='env-'+run_id+'-'+domain,reset_generation=0,domain=domain,role=role,allowed_tool_names=a.tools(domain,role),oracle_identity='JAVA_HTTP_GET_AUTHORITY' if domain=='config-java-http' else 'SQLITE_MODE_RO_READER',identity=identity(),budget_policy=policy(),guard_policy=guard_identity(),capabilities=a.permissions(domain,role),native_legacy_verifier_version='rpf68-cross-domain-verifier-v3',original_certificate_raw_sha256=None,observed_vs_declared='DECLARED_POLICY_NOT_AUTHORITY',workspace=scope.root.relative_to(ROOT).as_posix())
 return a.CapabilityCapsule(a.canonical(p))
def validate(p):
 from .pge_r69_budget import policy
 from .pge_r69_guard_audit import guard_identity
 keys={'schema','source_kind','owner_id','run_id','environment_id','reset_generation','domain','role','allowed_tool_names','oracle_identity','identity','budget_policy','guard_policy','capabilities','native_legacy_verifier_version','original_certificate_raw_sha256','observed_vs_declared','workspace'}
 a.require(type(p) is dict and set(p)==keys,'CAPSULE_FIELDS');a.typed(p['domain'],p['role']);scope=OwnerScope(p['run_id'])
 a.require(p['schema']==a.VERSION and p['source_kind']==a.KIND,'SOURCE_KIND_VERSION');a.require(p['owner_id']==a.OWNER and p['workspace']==scope.root.relative_to(ROOT).as_posix() and p['environment_id']=='env-'+p['run_id']+'-'+p['domain'] and type(p['reset_generation']) is int and p['reset_generation']==0,'OWNER_SCOPE')
 a.require(a.canonical(p['identity'])==a.canonical(identity()),'SOURCE_IDENTITY');a.require(p['allowed_tool_names']==a.tools(p['domain'],p['role']) and a.canonical(p['capabilities'])==a.canonical(a.permissions(p['domain'],p['role'])),'CAPABILITIES')
 a.require(p['oracle_identity']==('JAVA_HTTP_GET_AUTHORITY' if p['domain']=='config-java-http' else 'SQLITE_MODE_RO_READER'),'ORACLE_IDENTITY')
 a.require(a.canonical(p['budget_policy'])==a.canonical(policy()),'BUDGET_POLICY');a.require(a.canonical(p['guard_policy'])==a.canonical(guard_identity()),'GUARD_IDENTITY')
 a.require(p['native_legacy_verifier_version']=='rpf68-cross-domain-verifier-v3' and p['original_certificate_raw_sha256'] is None and p['observed_vs_declared']=='DECLARED_POLICY_NOT_AUTHORITY','CERTIFICATE_AUTHORITY')
 return True

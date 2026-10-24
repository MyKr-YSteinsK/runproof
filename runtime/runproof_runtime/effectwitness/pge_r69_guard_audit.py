"""Read-only guard identity/differential; this module does not implement a child."""
import ast
from . import pge_r69_abi as a
from .pge_r69_capsule import ROOT,GUARDS
def segment(name):
 raw=(ROOT/name).read_bytes();text=raw.decode();tree=ast.parse(text);start=next((x.lineno for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='_is_link'),None);end=next(x.lineno for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='main');return raw,tree, ''.join(text.splitlines(True)[start-1:end-1]).encode() if start else None
def guard_identity():
 from .config_experiment_verify import pinned_sdk_fields
 raw,tree,part=segment(GUARDS[-1]);a.require(part is not None,'GUARD_SEGMENT');return dict(child_raw=a.sha(raw),guard_raw=a.sha(part),sdk=pinned_sdk_fields(),network='LOOPBACK_HOST_ONLY',file='OWN_WRITE_ROOT_AND_PINNED_READS',provider_key=False,process=False)
def audit():
 rows=[];parts=[]
 for name in GUARDS:
  raw,tree,part=segment(name);parts.append(part);rows.append(dict(path=name,raw=a.sha(raw),lf=a.sha(raw.replace(b'\r\n',b'\n')),guard_sha256=a.sha(part) if part else None,function_names=[x.name for x in tree.body if isinstance(x,ast.FunctionDef)],analysis='STATIC_SOURCE_INSPECTED',dynamic_sandbox='NOT_PROVEN'))
 driver=(ROOT/'runtime/runproof_runtime/effectwitness/pge_r68_driver.py').read_text();child=(ROOT/GUARDS[-1]).read_text();a.require(parts[1] is not None and parts[1]==parts[2],'GUARD_PREFIX_DRIFT');a.require('total_token_limit=sum(c.CAPS[port.domain])' in driver and "total_tokens_limit=cfg['total_token_limit']" in child and 'total_tokens_limit=35000' not in child,'CHILD_BUDGET_BINDING')
 return dict(status='PASS',rows=rows,r67_r68='byte-identical',r66='intentional versioned divergence; separate native child, not replaced',guard_policy=guard_identity(),child_budget='PARENT_FROZEN_DOMAIN_SUM',weakening_detected=False,unverified=['General OS sandbox','R66 guard semantic equivalence beyond native certificate validation'])

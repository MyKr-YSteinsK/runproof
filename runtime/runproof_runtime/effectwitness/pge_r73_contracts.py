"""RPF73 component-only identity and canonical primitives; no business authority."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[3]
WORK=ROOT/'.local/rpf-73'
OWNER='rpf-73'
ABI='rpf73-launch-factory-v1'
KIND='RPF73_FIXED_SDK_LAUNCH_COMPONENT_ONLY'
BASE='a055bfa1844f1df7de459daf35107de7a3ae2d2c'
BRANCH='codex/rpf-73-versioned-launch-factory-cross-domain'
DOMAINS=('config-java-http','order-sqlite')
NAMES=('contracts','launch_contract','launch_factory','budget_view','sdk_harness','domain_adapters','verify','compat')
NEW=tuple('runtime/runproof_runtime/effectwitness/pge_r73_'+n+'.py' for n in NAMES)+('runtime/tests/test_effectwitness_pge_r73.py','spikes/rpf-73/probe.py')
CHILD='runtime/runproof_runtime/effectwitness/pge_r68_sdk_child.py'
REFERENCE=('runtime/runproof_runtime/effectwitness/pge_r68_contracts.py','runtime/runproof_runtime/effectwitness/pge_r68_driver.py','runtime/runproof_runtime/effectwitness/pge_r72r3_launch_spec.py')
PIN=dict(python_version='3.12.13',python_executable_sha256='e9f7e4baa0da1c21ffc3c2c2a644459b1a38dced56dfc7846e16f801645d520f',sdk_source_sha256='70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa',openai_source_sha256='8f4fdba5193967d09ca79bc4504e79bd8c20ba4bd8f09c2df3817501540a39db',sdk_site_root_binding_sha256='d4c8fbc3564e7f3357af9ab8a08b1a1cfa04cc7d971895e76e2607c791f2428a',python_runtime_mapping_sha256='80f7fdec59aa2c6d06cbf44c162512af97193f733b9ede9ebf1bc025e712efa5',child_sha256='c278eae783e3fa3eacdb0c852c9ab7b4a9685bb7f4669395bb316460cd5eb5f7',pydantic_record='9afe682f866eb018d92989e282e2286e63aa7aee8be9168c17cb47c2ae1ea453',openai_record='c59a36843c481ffaf7b5b0b0c4e35aed7fb49033f77739c8d448138e22ee4c10')
FLAGS=dict(BUSINESS_TARGET_REAL_THIS_TASK='NOT_RUN',AUTHORITY_READBACK='NOT_RUN',PGE_FEEDBACK='NOT_RUN',REAL_EXPLORER_THIS_TASK='NOT_RUN',REAL_MODEL_USAGE=0,EXTERNAL_PROVIDER_CALLS=0,SDK_GUARD_MIGRATED='NO',NATIVE_R68_DRIVER_MIGRATED='NO',FULL_COMMON_CORE_MIGRATED='NO',CHILD_INDEPENDENT_ATTESTATION='NOT_ESTABLISHED',ISSUER='NOT_ESTABLISHED',L2='NOT_ESTABLISHED')
PIN.update(python_cfg_sha256='181df8482a0bdb0c006a504f05a44158ce2d4fb754f3602a0f21017d7cee4985',python_launcher_sha256='74e020321eb8f828f0c2cfe865082fcf94aa6e7cf488e8a744d89b9282eaeb83')

def require(ok,code):
 if not ok:raise ValueError(code)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(v):return sha(canonical(v))
def equal(a,b,code):require(canonical(a)==canonical(b),code)
def strict(raw):
 def pairs(rows):
  out={}
  for k,v in rows:require(k not in out,'DUPLICATE_JSON_KEY');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'NONFINITE_JSON'))
def canonical_value(raw):
 require(type(raw) is bytes,'CANONICAL_BYTES');v=strict(raw);require(raw==canonical(v),'NONCANONICAL_JSON');return v
def scope(path):
 p=Path(path);require(p.is_absolute() and p.is_relative_to(WORK),'OWNER_LEXICAL_SCOPE')
 require(not any(x.is_symlink() or x.is_junction() for x in (p,*p.parents)),'OWNER_REPARSE')
 require(p.resolve().is_relative_to(WORK.resolve()),'OWNER_REAL_SCOPE');return p
def once(path,value):
 p=scope(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
def sources():
 paths=NEW+(CHILD,)+REFERENCE+('runtime/__init__.py','runtime/runproof_runtime/__init__.py','runtime/runproof_runtime/effectwitness/__init__.py')
 out={}
 for name in paths:
  p=ROOT/name
  if p.is_file():
   raw=p.read_bytes();out[name]=dict(raw=sha(raw),lf=sha(raw.replace(b'\r\n',b'\n')),role='RPF73_CURRENT' if name in NEW else 'HISTORICAL_REFERENCE_ONLY' if name in REFERENCE else 'NATIVE_READ_ONLY')
 return out
def source_identity():return dict(owner=OWNER,abi=ABI,source_kind=KIND,files=sources(),sdk=PIN)
def fixed_paths():
 site=ROOT/'.local/rpf-48/venv/Lib/site-packages';cfg=ROOT/'.local/rpf-48/venv/pyvenv.cfg'
 require(not any(p.is_symlink() or p.is_junction() for p in (site,*site.parents,cfg)),'SDK_REPARSE')
 require(sha(cfg.read_bytes())==PIN['python_cfg_sha256'] and sha((ROOT/'.local/rpf-48/venv/Scripts/python.exe').read_bytes())==PIN['python_launcher_sha256'],'SDK_LAUNCHER_CONFIG_PIN')
 entries=dict(x.split(' = ',1) for x in cfg.read_text().splitlines() if ' = ' in x)
 direct=Path(entries['executable']).resolve(strict=True)
 require(not any(p.is_symlink() or p.is_junction() for p in (direct,*direct.parents)),'PYTHON_REPARSE')
 for p,expected in ((direct,PIN['python_executable_sha256']),(ROOT/CHILD,PIN['child_sha256']),(site/'pydantic_ai/agent/__init__.py',PIN['sdk_source_sha256']),(site/'openai/__init__.py',PIN['openai_source_sha256']),(site/'pydantic_ai_slim-2.57.0.dist-info/RECORD',PIN['pydantic_record']),(site/'openai-3.35.1.dist-info/RECORD',PIN['openai_record'])):
  require(sha(p.read_bytes())==expected,'FIXED_PIN_BYTES')
 require(sha(os.path.normcase(str(site.resolve())).casefold().encode())==PIN['sdk_site_root_binding_sha256'],'SDK_SITE_BINDING')
 return dict(python=str(direct),child=str(ROOT/CHILD),site=str(site.resolve()))
def windows():require(sys.platform=='win32' and sys.maxsize>2**32,'WINDOWS_X64_ONLY')

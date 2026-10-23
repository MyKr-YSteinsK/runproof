"""RPF68 immutable capability and explicit source closure; no legacy runtime state."""
import ast,os,secrets,socket,importlib.util,sys
from pathlib import Path
from dataclasses import dataclass
from .pge_r68_contracts import *
ROOT=Path(__file__).resolve().parents[3]
NAMES=('contracts','context','budget','explorer','config_port','order_port','driver','session','verify','sdk_child')
NEW=tuple('runtime/runproof_runtime/effectwitness/pge_r68_'+n+'.py' for n in NAMES)+('runtime/tests/test_effectwitness_pge_r68.py','spikes/rpf-68/rev-2/probe.py')
def sources():
 pending=list(NEW)+['spikes/rpf-53/probe.py','spikes/rpf-55/probe.py','spikes/rpf-53/rev-6/config-live-evidence.json'];out={}
 while pending:
  name=pending.pop()
  if name in out:continue
  raw=(ROOT/name).read_bytes();out[name]=dict(raw=sha(raw),lf=sha(raw.replace(b'\r\n',b'\n')))
  for n in ast.walk(ast.parse(raw)) if name.endswith('.py') else []:
   if isinstance(n,ast.ImportFrom) and n.module and (n.level or n.module.startswith('runtime.')):
    p=Path(name).parent if n.level else Path('.')
    for _ in range(max(0,n.level-1)):p=p.parent
    f=(p/(n.module.replace('.','/')+'.py')).as_posix()
    if (ROOT/f).is_file():pending.append(f)
 return dict(sorted(out.items()))
def public(suffix,ports,synthetic):
 require(__import__('re').fullmatch('[a-f0-9]{16}',suffix) and len(set(ports))==3 and all(type(p) is int and 1024<=p<=65535 for p in ports),'CONTEXT_PARAMETERS');sm=sources();sid='rpf68r2-'+suffix;sd=digest({k:v['lf'] for k,v in sm.items()})
 return dict(owner=OWNER,abi=ABI,base=BASE,branch=BRANCH,session_id=sid,workspace='.local/rpf-68-rev-2'+('/tests/'+suffix if synthetic else ''),source_kind=SYNTHETIC if synthetic else REAL,sources=sm,source_digest=sd,ports=list(ports),rounds=[{candidate:contract(sid,i,candidate,sd,ports) for candidate in CANDIDATES[i-1]} for i in (1,2)],limits=LIMITS,caps={k:list(v) for k,v in CAPS.items()},price=PRICE,budget_version=BUDGET_VERSION,reachable_tokens=REACHABLE_TOKENS,global_tokens=GLOBAL_TOKENS,boundaries=BOUNDARIES)
@dataclass(frozen=True)
class Context:
 root:Path
 frozen:bytes
 def __post_init__(self):
  p=self.public();require(p==public(p['session_id'].removeprefix('rpf68r2-'),p['ports'],p['source_kind']==SYNTHETIC) and self.root==ROOT/p['workspace'],'CONTEXT_IDENTITY');self.scope(self.root)
 def public(self):return strict(self.frozen)
 def scope(self,path):
  p=Path(path);require(p.is_absolute() and p.resolve().is_relative_to(self.root.resolve()) and not any(x.is_symlink() or x.is_junction() for x in (p,*p.parents)),'TASK_PATH_SCOPE');return p
 def once(self,path,value):
  p=self.scope(path);p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
 def check(self):require(self.public()['sources']==sources(),'SOURCE_DRIFT')
 def contract(self,i,candidate):return self.public()['rounds'][i-1][candidate]
 def validate(self,ct):require(ct in [v for row in self.public()['rounds'] for v in row.values()],'FROZEN_CONTRACT')
 def folder(self,ct):self.validate(ct);return self.scope(self.root/'runs'/ct['experiment']['run_id'])
def make(*,synthetic=False):
 ports=[]
 while len(ports)<3:
  with socket.socket() as s:s.bind(('127.0.0.1',0));p=s.getsockname()[1]
  if p not in ports:ports.append(p)
 value=public(secrets.token_hex(8),ports,synthetic);return Context(ROOT/value['workspace'],canonical(value))
def helpers():
 fixed=Path(os.environ.get('RPF68_FIXED_SDK_PUBLIC_ROOT',str(ROOT)))
 require(all(sha((fixed/n).read_bytes().replace(b'\r\n',b'\n'))==sources()[n]['lf'] for n in ('spikes/rpf-53/probe.py','spikes/rpf-55/probe.py')),'SDK_HELPER_SOURCE')
 spec=importlib.util.spec_from_file_location('r68_sdk_helpers',fixed/'spikes/rpf-55/probe.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);return h,h.old

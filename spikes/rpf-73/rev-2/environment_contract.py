"""R73r2 suite environment ABI. No host credential lookup or path injection."""
import ast
from dataclasses import dataclass
import hashlib,json,ntpath,os,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
WORK=ROOT/'.local/rpf-73-rev-2'
OWNER='rpf-73-rev-2'
ABI='rpf73r2-runtime-runner-replay-v1'
BASE='19c5d28baab0e10b34dbf821ce07cc187bdd9c8f'
BRANCH='codex/rpf-73-rev2-runner-env-loopback-regression'
OLD_SOURCE='e4ea3cc40987e1c90aa683ec324aa33a2d9d97e1e2d713fb84fb75bc039a3db1'
PYTHON_SHA='03168c01b7b7491423350e82c26fee71f35b43694d1319d3c668bda6903a0c38'
NEW=tuple('spikes/rpf-73/rev-2/'+n+'.py' for n in ('environment_contract','runner','loopback_probe','probe'))+('runtime/tests/test_effectwitness_pge_r73r2.py',)
HOST_KEYS=('SYSTEMROOT','WINDIR','PATH','COMSPEC','PATHEXT')
FIXED_ROOT_KEYS=('RPF66_FIXED_SDK_PUBLIC_ROOT','RPF67_FIXED_SDK_PUBLIC_ROOT','RPF68_FIXED_SDK_PUBLIC_ROOT')
ENV_KEYS=frozenset(HOST_KEYS+FIXED_ROOT_KEYS+('HOME','USERPROFILE','TEMP','TMP','TMPDIR','PYTHONDONTWRITEBYTECODE','PYTHONUTF8','RPF73R2_ENV_RECEIPT'))
def require(ok,code):
 if not ok:raise ValueError(code)
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(x):return hashlib.sha256(x).hexdigest()
def digest(x):return sha(canonical(x))
def strict(raw):
 def pairs(rows):
  out={}
  for k,v in rows:require(k not in out,'DUPLICATE_JSON');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'NONFINITE_JSON'))
def equal(a,b,code):require(canonical(a)==canonical(b),code)
def owned(path,root=WORK):
 p=Path(path);root=Path(root);require(p.is_absolute() and p.is_relative_to(root),'OWNER_LEXICAL_SCOPE')
 require(not any(x.is_symlink() or x.is_junction() for x in (p,*p.parents)),'OWNER_REPARSE')
 require(p.resolve().is_relative_to(root.resolve()),'OWNER_REAL_SCOPE');return p
def write_once(path,value):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
def source_identity():
 previous=strict((ROOT/'spikes/rpf-73/source-identity-map.json').read_bytes())['identity'];require(digest(previous)==OLD_SOURCE,'OLD_FACTORY_IDENTITY')
 records={}
 for name,record in previous['files'].items():
  raw=(ROOT/name).read_bytes();require(sha(raw)==record['raw'] and sha(raw.replace(b'\r\n',b'\n'))==record['lf'],'OLD_SOURCE_BYTES')
  records[name]=dict(raw=sha(raw),lf=sha(raw.replace(b'\r\n',b'\n')),role='FROZEN_REV1_READ_ONLY')
 for name in (*NEW,'runtime/runproof_runtime/effectwitness/target_driver.py','runtime/tests/test_effectwitness_target_agent.py','runtime/tests/test_effectwitness_pge_r72r3.py'):
  raw=(ROOT/name).read_bytes();records[name]=dict(raw=sha(raw),lf=sha(raw.replace(b'\r\n',b'\n')),role='R73R2_CURRENT' if name in NEW else 'FROZEN_TARGET_READ_ONLY')
 return dict(owner=OWNER,abi=ABI,base=BASE,old_factory_source_sha256=OLD_SOURCE,files=records)
def trusted_paths():
 tree=ast.parse((ROOT/'runtime/runproof_runtime/effectwitness/pge_r72r3_launch_spec.py').read_bytes());values={}
 for n in tree.body:
  if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('TRUSTED_PATH_SHA256','SYSTEM_ROOT_SHA256') for t in n.targets):
   name=n.targets[0].id;values[name]=frozenset(ast.literal_eval(n.value.args[0])) if isinstance(n.value,ast.Call) else ast.literal_eval(n.value)
 require(len(values['TRUSTED_PATH_SHA256'])==35,'FROZEN_PATH_SET');return values
def path_id(value):return sha(ntpath.normcase(ntpath.normpath(value)).encode())
def safe_segment(p):return type(p) is str and bool(p) and ntpath.isabs(p) and not p.startswith(('\\\\','//')) and '%' not in p and '..' not in p.replace('/','\\').split('\\') and not any(x in p for x in '\r\n\0"|&<>')
def approved_host():return {k:os.environ[k] for k in HOST_KEYS}
def filtered_path(value):
 require(type(value) is str,'HOST_PATH_TYPE');trusted=trusted_paths()['TRUSTED_PATH_SHA256'];keep=[];dropped=[]
 for entry in value.split(';'):
  if safe_segment(entry) and path_id(entry) in trusted:
   if entry not in keep:keep.append(entry)
  else:dropped.append(dict(value_sha256=sha(entry.encode()),reason='MALFORMED_OR_NOT_FROZEN_TRUSTED'))
 require(bool(keep),'NO_TRUSTED_PATH');return ';'.join(keep),dropped
@dataclass(frozen=True,slots=True)
class SuiteEnvironmentContract:
 frozen:bytes
 def public(self):
  value=strict(self.frozen);require(self.frozen==canonical(value),'NONCANONICAL_CONTRACT');return value
 @classmethod
 def build(cls,scratch,descriptor,*,host=None,reference_root=ROOT,owner_root=WORK):
  h=approved_host() if host is None else host
  require(type(h) is dict and set(h)==set(HOST_KEYS),'HOST_KEYS');require(all(type(v) is str and v for v in h.values()),'HOST_VALUES')
  path,dropped=filtered_path(h['PATH']);scratch=owned(scratch,owner_root);descriptor=owned(descriptor,owner_root)
  env={k:h[k] for k in HOST_KEYS};env['PATH']=path
  env.update({k:str(scratch) for k in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR')});env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',RPF73R2_ENV_RECEIPT=str(descriptor));env.update({k:str(reference_root) for k in FIXED_ROOT_KEYS})
  value=dict(owner=OWNER,abi=ABI,owner_root=str(owner_root),reference_root=str(reference_root),scratch=str(scratch),descriptor=str(descriptor),env=env,env_sha256=digest(env),dropped_path=dropped,runner_appended_paths=[],python=str(Path(sys.executable).resolve()),python_sha256=PYTHON_SHA)
  out=cls(canonical(value));out.check();return out
 def check(self):
  v=self.public();require(type(v) is dict and set(v)=={'owner','abi','owner_root','reference_root','scratch','descriptor','env','env_sha256','dropped_path','runner_appended_paths','python','python_sha256'},'CONTRACT_FIELDS')
  equal([v['owner'],v['abi']],[OWNER,ABI],'OWNER_ABI');require(v['runner_appended_paths']==[],'NO_APPENDED_PATH')
  root=Path(v['owner_root']);require(root.name=='rpf-73-rev-2' and root.parent.name=='.local','OWNER_ROOT_IDENTITY')
  require((root==WORK or ROOT.resolve().is_relative_to(root.resolve())) and v['reference_root']==str(root.parent.parent),'OWNER_REFERENCE_BINDING')
  scratch=owned(v['scratch'],root);owned(v['descriptor'],root)
  exe=Path(v['python']);require(exe.is_absolute() and exe.is_file() and not any(p.is_symlink() or p.is_junction() for p in (exe,*exe.parents)) and sha(exe.read_bytes())==v['python_sha256']==PYTHON_SHA and exe==Path(sys.executable).resolve(),'ABSOLUTE_PINNED_PYTHON')
  env=v['env'];require(type(env) is dict and set(env)==ENV_KEYS,'RUNTIME_ENV_KEYS');require(all(type(x) is str and x and not any(ch in x for ch in '\r\n\0') for x in env.values()),'RUNTIME_ENV_VALUES')
  trusted=trusted_paths();require(path_id(env['SYSTEMROOT'])==path_id(env['WINDIR'])==trusted['SYSTEM_ROOT_SHA256'],'SYSTEM_ROOT_PIN')
  require(all(safe_segment(p) and path_id(p) in trusted['TRUSTED_PATH_SHA256'] for p in env['PATH'].split(';')),'RUNTIME_PATH_TRUST')
  require(ntpath.normcase(env['COMSPEC'])==ntpath.normcase(ntpath.join(env['SYSTEMROOT'],'System32','cmd.exe')) and re.fullmatch(r'(?:\.[A-Za-z0-9]+;?)+',env['PATHEXT']),'OS_COMMAND_FIELDS')
  equal({k:env[k] for k in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR')},{k:str(scratch) for k in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR')},'TASK_SCRATCH_ENV')
  equal({k:env[k] for k in FIXED_ROOT_KEYS},{k:v['reference_root'] for k in FIXED_ROOT_KEYS},'SDK_PUBLIC_REFERENCE_ROOT')
  require(env['RPF73R2_ENV_RECEIPT']==v['descriptor'] and env['PYTHONDONTWRITEBYTECODE']=='1' and env['PYTHONUTF8']=='1','RUNTIME_FLAGS')
  require(v['env_sha256']==digest(env),'ENV_HASH_BINDING');return v
 def redacted(self):
  v=self.check();return dict(owner=OWNER,abi=ABI,env_sha256=v['env_sha256'],keys=sorted(v['env']),value_sha256={k:sha(x.encode()) for k,x in v['env'].items()},path_directory_sha256=[path_id(p) for p in v['env']['PATH'].split(';')],dropped_path=v['dropped_path'],runner_appended_paths=[],python_sha256=PYTHON_SHA)
def observe_actual():
 # Only called in the explicitly sanitized child, never on the user's host env.
 descriptor=Path(os.environ['RPF73R2_ENV_RECEIPT']);root=next((p for p in descriptor.parents if p.name=='rpf-73-rev-2' and p.parent.name=='.local'),None);require(root is not None,'OBSERVATION_ROOT');owned(descriptor,root)
 expected=strict(descriptor.read_bytes());contract=SuiteEnvironmentContract(canonical(expected['contract']));v=contract.check()
 require(set(expected)=={'contract','cwd','source_sha256'} and expected['source_sha256']==digest(source_identity()),'ACTUAL_SOURCE_IDENTITY')
 require(set(os.environ)==ENV_KEYS,'ACTUAL_CHILD_ENV_KEYS');actual={k:os.environ[k] for k in ENV_KEYS};equal(actual,v['env'],'ACTUAL_CHILD_ENV_VALUES')
 require(sha(Path(sys.executable).read_bytes())==PYTHON_SHA and Path.cwd().resolve()==Path(expected['cwd']).resolve(),'ACTUAL_EXECUTABLE_CWD')
 result=dict(status='PASS',owner=OWNER,abi=ABI,pid=os.getpid(),parent_pid=os.getppid(),env_sha256=digest(actual),source_sha256=digest(source_identity()),python_sha256=PYTHON_SHA,actual_key_count=len(actual),credential_values_read=False)
 output=descriptor.parent/('actual-env-'+str(os.getpid())+'.json')
 if not output.exists():write_once(output,result)
 return result
def parse_summary(text):
 text='\n'.join(text.splitlines());match=re.search(r'^Ran (\d+) tests? in ([0-9.]+)s$',text,re.M);terminal=re.search(r'^(OK(?: \(.*\))?|FAILED \(.*\))$',text,re.M)
 return dict(tests=int(match[1]) if match else None,unittest_final_summary_present=bool(match and terminal),terminal=terminal[1] if terminal else None,errors=re.findall(r'^ERROR: (.*)',text,re.M),failures=re.findall(r'^FAIL: (.*)',text,re.M),class_skips=re.findall(r'^setUpClass .*skipped .*$',text,re.M),pass_summary=bool(match and terminal and terminal[1].startswith('OK')))
def verify_receipt(receipt,raw):
 require(receipt['log_sha256']==sha(raw),'STDOUT_RAW_HASH');parsed=parse_summary(raw.decode('utf-8',errors='replace'))
 equal(receipt['summary'],parsed,'SUMMARY_NOT_REWRITABLE');needs_summary=receipt.get('mode','full') in ('targeted','loopback','focused','full')
 require(not(receipt['status']=='PASS' and (receipt['exit']!=0 or needs_summary and not parsed['pass_summary'] or parsed['errors'] or parsed['failures'])),'FAILURE_NOT_PASS');return parsed

"""Only bounded, source-identical Runtime/diagnostic commands; no Factory run."""
import argparse,datetime,importlib,json,os,re,shutil,subprocess,sys,time,unittest
from pathlib import Path
from . import environment_contract as e
ROOT=e.ROOT;WORK=e.WORK
SEVEN=('test_env_reanchored_relative_untrusted_and_key_rejected','test_frozen_env_snapshot_independent_of_input_mutation','test_historical_env_A_accepts_when_host_B_and_native_helper_disabled','test_launch_command_owner_and_cross_domain_reanchor_rejected','test_launch_missing_mapping_and_noncanonical_reject','test_live_actual_env_mismatch_rejects_before_spawn','test_windows_native_serialized_argv_and_sanitized_env')
LOOP='runtime.tests.test_effectwitness_target_agent.TargetAgentTests.test_real_loopback_host_rejects_unauthenticated_tool_without_effect'
FULL_ARGS=['-m','unittest','discover','-s','runtime/tests','-p','test_*.py','-v']
NEW_MODULE='spikes.rpf-73.rev-2.'
def command(mode,label=None):
 if mode=='targeted':return ['-m','unittest',*['runtime.tests.test_effectwitness_pge_r72r3.BudgetTests.'+n for n in SEVEN],'-v']
 if mode=='loopback':return ['-m',NEW_MODULE+'loopback_probe','original']
 if mode=='focused':return ['-m','unittest','runtime.tests.test_effectwitness_pge_r73r2','runtime.tests.test_effectwitness_pge_r73','-v']
 if mode=='full':return list(FULL_ARGS)
 if mode=='observe':return ['-m',NEW_MODULE+'probe','observe']
 if mode=='inventory':return ['-m',NEW_MODULE+'probe','inventory']
 if mode in ('immediate','drain'):return ['-m',NEW_MODULE+'loopback_probe','control','--mode',mode]
 if mode=='negative':
  e.require(type(label) is str and re.fullmatch('[a-z0-9-]{1,80}',label),'NEGATIVE_LABEL');return ['-m',NEW_MODULE+'probe','validate','--case',str(e.owned(WORK/'negative-cases'/(label+'.json')))]
 if re.fullmatch(r'history-\d{2}',mode):
  index=int(mode[-2:]);rows=e.strict((ROOT/'spikes/rpf-73/history-regression.json').read_bytes())['commands'];e.require(0<=index<len(rows),'HISTORY_INDEX');args=rows[index]['command'];e.require(args[:4]==['python','-X','utf8','-B'] and not any('.local' in s for s in args),'PUBLIC_HISTORY_ONLY');return args[4:]
 raise ValueError('COMMAND_NOT_ALLOWED')
def validate_command(mode,args,label=None):e.equal(args,command(mode,label),'EXACT_STANDARD_COMMAND');return True
def paths_for(label):
 e.require(re.fullmatch('[a-z0-9-]{1,80}',label),'LABEL');return e.owned(WORK/'commands'/label)
def snapshot(label):
 e.require(re.fullmatch('[a-z0-9-]{1,60}',label),'SNAPSHOT_LABEL');folder=e.owned(WORK/label);e.require(not folder.exists(),'SNAPSHOT_ALREADY_EXISTS');folder.mkdir()
 names=set(subprocess.check_output(['git','ls-files','--','runtime','spikes','demo','ci','control-plane','.github','AGENTS.md','.gitignore','README.md','README.zh-CN.md','web/README.md'],cwd=ROOT,text=True).splitlines())|set(e.NEW)
 # Exact known public contract documents, never enumerate docs directories.
 names.update('docs/'+stem+suffix for stem in ('ARCHITECTURE','RELIABILITY_MODEL','DEMO','GLOSSARY') for suffix in ('.md','.zh-CN.md'))
 lc=importlib.import_module('runtime.runproof_runtime.effectwitness.lab_cross_domain_contracts');names.update(lc.NEW_FILES+lc.OLD_FILES)
 hashes={}
 for name in sorted(names):
  e.require(not name.startswith(('.local/','docs/reviews/','docs/project/','docs/history/')),'SNAPSHOT_PROTECTED_PATH')
  src=ROOT/name
  if not src.is_file():continue
  e.require(not any(p.is_symlink() or p.is_junction() for p in (src,*src.parents)),'SNAPSHOT_SOURCE_REPARSE')
  dst=folder/name;dst.parent.mkdir(parents=True,exist_ok=True)
  with src.open('rb') as a,dst.open('xb') as b:shutil.copyfileobj(a,b)
  hashes[name]=e.sha(src.read_bytes());e.require(e.sha(dst.read_bytes())==hashes[name],'SNAPSHOT_RAW_COPY')
 for name in ('rpf-55-rev2','rpf-56-rev4','rpf-57','rpf-58-rev2','rpf-59','rpf-60','rpf-67-rev4','rpf-68-rev3','rpf-69','rpf-70','rpf-71','rpf-72','rpf-72-rev-2','rpf-72-rev-3','rpf-73','rpf-73-rev-2'):(folder/'.local'/name/'tests').mkdir(parents=True)
 e.write_once(WORK/'snapshots'/(label+'.json'),dict(path=folder.relative_to(ROOT).as_posix(),files=hashes,source=e.source_identity(),base=e.BASE));return folder
def verify_snapshot(folder):
 record=e.strict((WORK/'snapshots'/(folder.name+'.json')).read_bytes())
 for name,expected in record['files'].items():e.require(e.sha((folder/name).read_bytes())==expected and e.sha((ROOT/name).read_bytes())==expected,'SNAPSHOT_SOURCE_BYTES')
 return record
def claim(mode,label):
 prefix={'targeted':('targeted',2),'loopback':('loopback',3),'focused':('focused',3),'full':('full',1),'immediate':('immediate',2),'drain':('drain',2)}.get(mode)
 if prefix:
  counter=WORK/'claims'/prefix[0];counter.mkdir(parents=True,exist_ok=True)
  prior=list(counter.glob('*.json'));e.require(len(prior)<prefix[1],'COMMAND_QUOTA')
  e.write_once(counter/(label+'.json'),dict(owner=e.OWNER,label=label,mode=mode,source_sha256=e.digest(e.source_identity())))
def run(mode,label,snap,*,timeout=None,extra_args=None):
 args=command(mode,label) if extra_args is None else extra_args;validate_command(mode,args,label)
 if mode=='negative' or re.fullmatch(r'history-\d{2}',mode):e.require(Path(snap)==ROOT,'READONLY_COMMAND_CWD');snap=ROOT
 else:snap=e.owned(snap);verify_snapshot(snap)
 limit=7200 if mode=='full' else 1200 if mode in ('targeted','focused') else 180
 timeout=limit if timeout is None else timeout;e.require(type(timeout) is int and 0<timeout<=limit,'COMMAND_TIMEOUT')
 g0=e.strict((WORK/'g0.json').read_bytes());deadline=datetime.datetime.fromisoformat(g0['task_start_utc'].replace('Z','+00:00'))+datetime.timedelta(seconds=14400)
 e.require((deadline-datetime.datetime.now(datetime.timezone.utc)).total_seconds()>timeout,'TASK_WALL_BUDGET')
 before=e.source_identity();freeze=WORK/'freeze.json'
 if freeze.exists():e.equal(before,e.strict(freeze.read_bytes())['identity'],'SOURCE_FROZEN')
 folder=paths_for(label);folder.mkdir(parents=True,exist_ok=False);scratch=folder/'scratch';scratch.mkdir();descriptor=folder/'environment.json'
 contract=e.SuiteEnvironmentContract.build(scratch,descriptor);value=contract.check();e.write_once(descriptor,dict(contract=value,cwd=str(snap),source_sha256=e.digest(before)))
 claim(mode,label);argv=[value['python'],'-X','utf8','-B',*args];utc=datetime.datetime.now(datetime.timezone.utc).isoformat();start=time.monotonic();log=folder/'output.log'
 with log.open('xb') as out:
  process=subprocess.Popen(argv,cwd=snap,env=value['env'],shell=False,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,close_fds=True)
  e.write_once(folder/'started.json',dict(owner=e.OWNER,abi=e.ABI,command=['$PINNED_ABSOLUTE_PYTHON',*argv[1:]],python_sha256=e.PYTHON_SHA,cwd=snap.relative_to(ROOT).as_posix(),pid=process.pid,parent_pid=os.getpid(),start_utc=utc,timeout_seconds=timeout,env=contract.redacted(),source_sha256=e.digest(before),mode=mode))
  timed=False
  try:code=process.wait(timeout=timeout)
  except subprocess.TimeoutExpired:timed=True;process.terminate();code=process.wait(timeout=15)
 raw=log.read_bytes();summary=e.parse_summary(raw.decode('utf-8',errors='replace'));after=e.source_identity();same=before==after
 receipt=dict(owner=e.OWNER,abi=e.ABI,label=label,mode=mode,command=['$PINNED_ABSOLUTE_PYTHON',*argv[1:]],python_sha256=e.PYTHON_SHA,python=sys.version,os=sys.platform,cwd=snap.relative_to(ROOT).as_posix(),pid=process.pid,parent_pid=os.getpid(),start_utc=utc,elapsed_seconds=time.monotonic()-start,exit=code,timed_out=timed,timeout_seconds=timeout,summary=summary,status='PASS' if code==0 and (summary['pass_summary'] if mode in ('targeted','focused','full','loopback') else True) else 'FAIL',env=contract.redacted(),source_before_sha256=e.digest(before),source_after_sha256=e.digest(after),source_unchanged=same,log=log.relative_to(ROOT).as_posix(),log_sha256=e.sha(raw),factory_child_starts=0,fixture_scope='CURRENT_SNAPSHOT_ONLY',provider=0)
 e.verify_receipt(receipt,raw);e.write_once(folder/'receipt.json',receipt);print(e.canonical({k:receipt[k] for k in ('label','mode','status','exit','elapsed_seconds','source_unchanged')}|{'summary':summary}).decode(),flush=True);return receipt
def freeze():
 checks=[]
 for name in e.NEW:
  result=subprocess.run(['git','-c','core.autocrlf=false','diff','--no-index','--check','--','NUL',name],cwd=ROOT,capture_output=True);e.require(result.returncode in (0,1) and not result.stdout and not result.stderr,'SOURCE_FORMAT');checks.append(dict(path=name,exit=result.returncode))
 e.write_once(WORK/'freeze.json',dict(owner=e.OWNER,abi=e.ABI,identity=e.source_identity(),checks=checks,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()));print('FROZEN '+e.digest(e.source_identity()))
def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True);s=sub.add_parser('snapshot');s.add_argument('label');r=sub.add_parser('run');r.add_argument('mode');r.add_argument('label');r.add_argument('snapshot');r.add_argument('--timeout',type=int);sub.add_parser('freeze');a=p.parse_args()
 if a.action=='snapshot':print(snapshot(a.label).relative_to(ROOT).as_posix());return 0
 if a.action=='freeze':freeze();return 0
 snap=ROOT if a.snapshot=='repo' and (a.mode=='negative' or re.fullmatch(r'history-\d{2}',a.mode)) else WORK/a.snapshot
 receipt=run(a.mode,a.label,snap,timeout=a.timeout);return receipt['exit']
if __name__=='__main__':raise SystemExit(main())

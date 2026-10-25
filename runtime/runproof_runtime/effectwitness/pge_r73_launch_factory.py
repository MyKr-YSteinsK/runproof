"""One explicit Factory for both domains. No frame/profile/old Driver hooks."""
from contextvars import ContextVar
import os
from pathlib import Path
import subprocess
import sys
import time
from . import pge_r73_contracts as c
from .pge_r73_launch_contract import LaunchRequest,LaunchReceipt,live_environment,lifecycle_action
from .pge_r73_domain_adapters import DomainAdapter
from .pge_r73_sdk_harness import Harness,Journal
ACTIVE=ContextVar('rpf73_explicit_popen',default=None)
def _audit(event,args):
 active=ACTIVE.get()
 if event!='subprocess.Popen' or active is None:return
 v,journal,observed=active
 c.require(type(args) is tuple and len(args)==4 and args[0] is None and type(args[1]) is str and args[1]==v['command'] and args[2]==v['cwd'],'ACTUAL_POPEN_ARGUMENTS')
 c.equal(args[3],v['env'],'ACTUAL_POPEN_ENV')
 audit=dict(executable_type='NoneType',command=args[1],cwd=args[2],env=dict(args[3]),tuple_types=[type(x).__name__ for x in args])
 observed.append(audit);c.require(len(observed)==1,'ONE_POPEN_AUDIT');journal.append('POPEN_AUDIT',observation=audit)
sys.addaudithook(_audit)
class LaunchFactory:
 @staticmethod
 def admit(request,adapter):
  c.windows();c.require(type(request) is LaunchRequest and type(adapter) is DomainAdapter,'LAUNCH_EXACT_TYPE')
  v=request.check(c.fixed_paths());c.require(adapter.domain==v['domain'],'ADAPTER_DOMAIN')
  c.equal(v['env'],live_environment(Path(v['cwd'])),'LIVE_ENV_EXACT')
  return v
 def launch(self,request,adapter):
  v=self.admit(request,adapter);folder=c.scope(Path(v['cwd']));root=folder.parent
  c.require(not root.exists(),'RUN_ALREADY_EXISTS');root.mkdir(parents=True);folder.mkdir()
  c.once(c.WORK/'claims'/(v['case']+'.json'),dict(run_id=v['run_id'],request_sha256=request.raw_sha256,source_sha256=c.digest(v['source']),case=v['case']))
  journal=Journal(root);journal.append('ADMITTED',request_sha256=request.raw_sha256,source_sha256=c.digest(v['source']),cfg_sha256=v['cfg_sha256'])
  host=Harness(v,adapter,journal);proc=None;report=None;stdout=b'';stderr=b'';observed=[];error=None;started=time.monotonic();started_ns=time.time_ns();state='ADMITTED'
  try:
   host.start();token=ACTIVE.set((v,journal,observed))
   try:
    proc=subprocess.Popen(v['argv'],cwd=v['cwd'],env=v['env'],shell=False,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True)
   finally:ACTIVE.reset(token)
   c.once(c.WORK/'pids'/(str(proc.pid)+'.json'),dict(run_id=v['run_id'],pid=proc.pid))
   state='RUNNING';host.pid=proc.pid
   journal.append('PROCESS_START',pid=proc.pid,parent_pid=os.getpid(),started_unix_ns=started_ns,argv_sha256=c.digest(v['argv']),command_sha256=c.sha(v['command'].encode()),cwd_sha256=c.sha(v['cwd'].encode()))
   raw=v['cfg_raw'].encode('ascii');journal.append('SERIALIZED_INPUT',pid=proc.pid,raw_sha256=c.sha(raw),bytes=len(raw))
   stdout,stderr=proc.communicate(raw,timeout=v['timeout_seconds']);report=c.canonical_value(stdout.strip());report.pop('final_output_sha256',None)
   if v['pressure']:
    c.require(proc.returncode==1 and report.get('status')=='SDK_ERROR' and report.get('error_type')=='UsageLimitExceeded' and host.failure is None,'SDK_CUMULATIVE_REAL_REJECTION');state='EXPECTED_REJECTION'
   else:
    c.require(proc.returncode==0 and report.get('status')=='COMPLETED' and host.failure is None,'SDK_COMPONENT_COMPLETION');state='COMPLETED'
   c.require(not stderr,'SDK_STDERR');journal.append('EXIT',pid=proc.pid,exit=proc.returncode,report_sha256=c.digest(report),stdout_sha256=c.sha(stdout),stderr_sha256=c.sha(stderr),state=state)
  except BaseException as exc:
   state='UNKNOWN';error=str(exc) if type(exc) is ValueError else type(exc).__name__;journal.append('UNKNOWN',error_type=type(exc).__name__,code=error)
  finally:
   if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=15)
   cleanup=host.close();cleanup.update(process_gone=proc is None or proc.poll() is not None,active_context_reset=ACTIVE.get() is None)
   journal.append('CLEANUP',pid=proc.pid if proc else None,**cleanup)
  receipt=dict(schema='rpf73-launch-receipt-v1',factory_entrypoint='pge_r73_launch_factory.LaunchFactory.launch',request_sha256=request.raw_sha256,source_sha256=c.digest(v['source']),cfg_sha256=v['cfg_sha256'],serialized_input_sha256=c.sha(v['cfg_raw'].encode('ascii')),env_snapshot_sha256=v['env_summary']['sha256'],actual_popen=observed,pid=proc.pid if proc else None,parent_pid=os.getpid(),started_unix_ns=started_ns,elapsed_seconds=time.monotonic()-started,exit=proc.returncode if proc else None,state=state,error=error,ready=host.ready,report=report,stdout_raw=stdout.decode('utf-8',errors='replace'),stdout_sha256=c.sha(stdout),stderr_sha256=c.sha(stderr),rows=host.rows,callbacks=host.callbacks,adapter_error=host.failure,cleanup=cleanup,scope='LOCAL_FIXED_SDK_COMPONENT_NOT_BUSINESS_WITNESS',usage_type='SYNTHETIC_VALIDATED_USAGE',observation=['CONTROLLER_OBSERVED','SDK_REPORT_OBSERVED'],child_attestation='NOT_ESTABLISHED',issuer=False,flags=c.FLAGS)
  frozen=LaunchReceipt(c.canonical(receipt));journal.append('RESULT_BOUND',receipt_sha256=frozen.raw_sha256)
  manifest=dict(schema='rpf73-component-evidence-v1',request=v,receipt=frozen.public(),frames=journal.frames,wal_raw_sha256=journal.raw_sha())
  path=root/'manifest.json';c.once(path,manifest)
  c.require(state in ('COMPLETED','EXPECTED_REJECTION') and all(cleanup.values()),'COMPONENT_UNKNOWN_OR_CLEANUP')
  return dict(path=path.relative_to(c.ROOT).as_posix(),sha256=c.sha(path.read_bytes()),run_id=v['run_id'],state=state,pid=proc.pid)

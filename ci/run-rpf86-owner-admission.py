"""RPF86: five unchanged RPF63 methods, process-private WORK substitution.

No official coverage admission. No Provider/SDK/Java/network/process in child.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
import hashlib
import importlib
import builtins
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
SELF=Path(__file__).resolve()
LOCAL=ROOT/'.local/rpf-86-owner-admission'
CERT_NAME='spikes/rpf-53/rev-6/config-live-evidence.json'
CERT_PATH=ROOT/CERT_NAME
CERT_SHA='f5e46947ae2a2583db51727e85c4f9e3d6c9d6499a1b24833dfffe1799438b43'
CERT_BLOB='b80c7d1b98daf9d336e8c90caa767b3d1113a3e9'
CERT_BYTES=21170
HELPER='runtime/runproof_runtime/effectwitness/config_experiment_verify.py'
HELPER_BLOB='e675dd04d6a9bcc09c87d798222d48f972488f3f'
MODULE='runtime.tests.test_effectwitness_pge_dual'
NAMES=('test_four_paths','test_twenty_one_reanchored_attacks','test_unknown_usage_and_restart',
       'test_scope_lock_budget_and_invalid_selection','test_unknown_mutation_stops_writes_but_allows_readback')
IDS=[MODULE+'.DualTests.'+x for x in NAMES]
PINS={'runtime/tests/test_effectwitness_pge_dual.py':'f98fb2da033dc62a0d5f785c06b837990912caf6',
      'runtime/runproof_runtime/effectwitness/pge_dual_contracts.py':'2cc4145369918d265df6e3cdcdbce9ac7ecd9bd4',
      'runtime/runproof_runtime/effectwitness/pge_dual_session.py':'5b626b547a884035c3c968f2a1f95f77f941aec9',
      'runtime/runproof_runtime/effectwitness/pge_dual_config_port.py':'79c210fa5579235447157858f2c62ddd61983a91',
      'runtime/runproof_runtime/effectwitness/pge_dual_verify.py':'ed4329a0064daae75792eddfdfdd5cebc1b4b695'}
LIMIT=2*1024*1024

class Invalid(ValueError):pass
def need(ok,code):
    if not ok:raise Invalid(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def strict(raw):
    need(isinstance(raw,bytes) and 0<len(raw)<=8*1024*1024,'JSON_SIZE')
    def pairs(xs):
        d={}
        for k,v in xs:need(k not in d,'DUPLICATE_JSON');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Invalid('NONFINITE_JSON')))
def write(path,data):
    with path.open('x',encoding='utf8') as out:json.dump(data,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
def nonlink(path):
    for p in (path,*path.parents):
        need(not p.is_symlink() and not getattr(p,'is_junction',lambda:False)(),'REPARSE')
        if p.exists():need(not bool(getattr(p.lstat(),'st_file_attributes',0)&1024),'REPARSE')

def certificate_bytes(raw):
    need(len(raw)==CERT_BYTES and sha(raw)==CERT_SHA,'CERTIFICATE_HASH')
    value=strict(raw)
    fields=value['payload']['contracts']['execution']['framework']['identity']
    need(type(fields) is dict,'CERTIFICATE_STRUCTURE')
    def scan(v):
        if isinstance(v,dict):
            for k,item in v.items():
                need(not (str(k).lower() in ('api_key','authorization','access_token','refresh_token','password','private_key','secret_key')
                          and isinstance(item,str) and item.strip()),'CERTIFICATE_SECRET')
                scan(item)
        elif isinstance(v,list):
            for item in v:scan(item)
        elif isinstance(v,str):
            need(not re.search(r'sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN .*PRIVATE KEY',v),'CERTIFICATE_SECRET')
    scan(value)
    return dict(path=CERT_NAME,blob=CERT_BLOB,raw_sha256=sha(raw),bytes=len(raw),
                structure='identity:dict',status='PIN_VERIFIED',secret_scan='NO_UNEXPECTED_CREDENTIAL_SHAPE')

def certificate_identity():
    nonlink(CERT_PATH)
    mode=subprocess.check_output(['git','ls-files','--stage','--',CERT_NAME],cwd=ROOT).decode().split()
    need(mode[:2]==['100644',CERT_BLOB] and mode[-1]==CERT_NAME,'CERTIFICATE_TRACKED_IDENTITY')
    raw=CERT_PATH.read_bytes()
    need(subprocess.check_output(['git','cat-file','blob',CERT_BLOB],cwd=ROOT)==raw,'CERTIFICATE_BLOB_BYTES')
    return certificate_bytes(raw)

def local_task():
    raw=os.environ.get('RPF86_TASK_ROOT','')
    p=Path(raw)
    need(p.is_absolute() and str(p.parent)==str(LOCAL) and re.fullmatch('rev2-[0-9a-f]{32}',p.name),'LOCAL_TASK_ROOT')
    nonlink(p)
    return p
def owned(raw):
    p=Path(raw)
    need(p.is_absolute() and '..' not in p.parts,'OWNER_LEXICAL')
    if os.environ.get('GITHUB_ACTIONS')=='true':
        run=os.environ.get('GITHUB_RUN_ID','');attempt=os.environ.get('GITHUB_RUN_ATTEMPT','')
        need(os.environ.get('GITHUB_WORKSPACE')==str(ROOT) and run.isascii() and run.isdecimal()
             and attempt.isascii() and attempt.isdecimal(),'CI_IDENTITY')
        ci=ROOT/'ci-results';need(p!=ci and p.is_relative_to(ci),'OWNER_SCOPE')
        name=p.relative_to(ci).parts[0]
        need(name==f'rpf86-{run}-{attempt}' or re.fullmatch('rpf86-unit-'+run+'-'+attempt+'-[0-9a-f]{32}',name),'CI_OWNER')
        base=ci/name
    else:
        need(str(p).startswith(str(LOCAL)+os.sep),'OWNER_SCOPE')
        base=local_task();need(str(p).startswith(str(base)+os.sep),'OWNER_SCOPE')
    nonlink(p);need(p.resolve().is_relative_to(base.resolve()),'OWNER_ESCAPE')
    return p
def identity():
    result={}
    for name,pin in PINS.items():
        raw=(ROOT/name).read_bytes()
        old=subprocess.run(['git','cat-file','blob',pin],cwd=ROOT,capture_output=True,timeout=10)
        need(old.returncode==0 and raw.replace(b'\r\n',b'\n')==old.stdout.replace(b'\r\n',b'\n'),'PINNED_SOURCE')
        result[name]=dict(blob=pin,raw_sha256=sha(raw),lf_sha256=sha(raw.replace(b'\r\n',b'\n')))
    tree=ast.parse((ROOT/next(iter(PINS))).read_bytes())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DualTests')
    methods={n.name:n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
    need(len(methods)==6 and set(NAMES)<=set(methods),'ORIGINAL_METHOD_SET')
    original=ast.parse(subprocess.check_output(['git','cat-file','blob',PINS[next(iter(PINS))]],cwd=ROOT))
    other=next(n for n in original.body if isinstance(n,ast.ClassDef) and n.name=='DualTests')
    need(ast.dump(cls,include_attributes=False)==ast.dump(other,include_attributes=False),'ORIGINAL_ASSERTION_DRIFT')
    helper=(ROOT/HELPER).read_bytes()
    need(helper.replace(b'\r\n',b'\n')==subprocess.check_output(['git','cat-file','blob',HELPER_BLOB],cwd=ROOT).replace(b'\r\n',b'\n'),'HELPER_PIN')
    return dict(files=result,certificate=certificate_identity(),helper=dict(blob=HELPER_BLOB,raw_sha256=sha(helper)),method_ast={name:sha(ast.dump(methods[name],include_attributes=False).encode()) for name in NAMES},
                assertion_counts={name:sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr.startswith('assert') for n in ast.walk(methods[name])) for name in NAMES},
                harness_lf_sha256=sha(SELF.read_bytes().replace(b'\r\n',b'\n')))

class Guard:
    """CPython audit + bounded metadata intercepts; not a kernel sandbox."""
    def __init__(self,owner,read_roots=()):
        self.owner=owner;self.private=ROOT/'.local';self.forbidden=ROOT/'docs/reviews'
        self.read_roots=tuple(read_roots)
        self.counts=Counter();self.denials=Counter();self.cache=set()
        self.raw_stat=os.stat;self.raw_lstat=os.lstat;self.raw_mkdir=os.mkdir
        self.raw_open=builtins.open;self.checking_certificate=False
        self.certificate_pin=certificate_identity()
        self.resolve=Path.resolve
        self.runtime=[Path(sys.base_prefix).resolve(),Path(sys.prefix).resolve(),Path(sysconfig.get_path('stdlib')).resolve()]
    def denied(self,code):
        self.denials[code]+=1;raise PermissionError(code)
    def lexical(self,path,query=False):
        if path is None or isinstance(path,int):return None
        p=Path(os.path.abspath(os.fsdecode(path)))
        text=str(p).casefold();private=str(self.private).casefold();owner=str(self.owner).casefold();reviews=str(self.forbidden).casefold()
        inside=lambda s,b:s==b or s.startswith(b+os.sep)
        if inside(text,reviews):self.denied('PROTECTED_REVIEW_ACCESS_DENIED')
        if inside(text,private) and not inside(text,owner):
            if query and p in self.owner.parents:return p
            if any(p.is_relative_to(r) or query and p in r.parents for r in self.read_roots):return p
            if not query and self.owner.is_relative_to(LOCAL) and p.is_relative_to(LOCAL):return p
            self.denied('OLD_ROOT_ACCESS_DENIED')
        return p
    def check(self,path,write=False):
        p=self.lexical(path)
        if p is None:return
        exact=str(p)==str(CERT_PATH)
        if str(p).casefold()==str(CERT_PATH).casefold() and not exact:self.denied('CERTIFICATE_CASE_ALIAS_DENIED')
        if exact and write:self.denied('CERTIFICATE_WRITE_DENIED')
        if write and not p.is_relative_to(self.owner):self.denied('WRITE_SCOPE_DENIED')
        if not write and not (exact or p.is_relative_to(self.owner) or any(p.is_relative_to(r) for r in self.read_roots) or p==ROOT or p.is_relative_to(ROOT/'runtime')
                or p in [ROOT/f'spikes/rpf-{n}/probe.py' for n in (53,55,63)]
                or any(p.is_relative_to(r) for r in self.runtime)):
            self.denied('READ_SCOPE_DENIED')
        if exact or p not in self.cache:
            if p.is_relative_to(ROOT):
                q=p
                while q!=ROOT:
                    # Raw lstat is only reached after lexical protection.
                    self.lexical(q,query=True)
                    try:st=self.raw_lstat(q)
                    except FileNotFoundError:st=None
                    if st is not None and (getattr(st,'st_file_attributes',0)&1024 or __import__('stat').S_ISLNK(st.st_mode)):
                        self.denied('REPARSE_ACCESS_DENIED')
                    q=q.parent
            resolved=self.resolve(p)
            self.lexical(resolved)
            if write and not resolved.is_relative_to(self.owner):self.denied('WRITE_ESCAPE_DENIED')
            self.cache.add(p)
        if exact:
            # Internal verification opens only this exact file read-only. The
            # original helper independently hashes the actual returned bytes.
            self.checking_certificate=True
            try:
                with self.raw_open(CERT_PATH,'rb') as stream:
                    import stat
                    need(stat.S_ISREG(os.fstat(stream.fileno()).st_mode),'CERTIFICATE_NORMAL_FILE')
                    need(certificate_bytes(stream.read(CERT_BYTES+1))==self.certificate_pin,'CERTIFICATE_PIN_DRIFT')
            finally:self.checking_certificate=False
            self.counts['certificate_read_granted']+=1
        if not write and not exact and not p.is_relative_to(self.owner) and not any(p.is_relative_to(r) for r in self.read_roots) and p.suffix.lower() not in ('.py','.pyc','.pyd','.so','.zip'):
            import stat
            try:is_dir=stat.S_ISDIR(self.raw_stat(p).st_mode)
            except OSError:is_dir=False
            if not is_dir:self.denied('NON_SOURCE_READ_DENIED')
        self.counts['write' if write else 'read']+=1
    def audit(self,event,args):
        if event=='open':
            path,mode,flags=args
            writing=bool(isinstance(mode,str) and any(x in mode for x in 'wax+') or isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if self.checking_certificate and str(path)==str(CERT_PATH) and not writing:return
            self.check(path,writing)
        elif event in ('os.listdir','os.scandir'):self.check(args[0])
        elif event in ('os.mkdir','os.remove','os.rmdir','os.chmod','os.utime','os.truncate'):self.check(args[0],True)
        elif event in ('os.rename','os.link','os.symlink'):self.denied('LINK_OR_RENAME_DENIED')
        elif event.startswith(('socket.','subprocess.','ctypes.')) or event in ('os.system','os.posix_spawn','os.spawn','os.fork','os.forkpty') or event.startswith('os.exec'):
            self.denied('NETWORK_PROCESS_NATIVE_DENIED')
        elif event=='import' and str(args[0]).startswith(('pydantic_ai','openai','httpx2')):self.denied('SDK_IMPORT_DENIED')
    def install(self):
        guard=self
        def stat(path,*a,**kw):guard.lexical(path,query=True);guard.counts['stat']+=1;return guard.raw_stat(path,*a,**kw)
        def lstat(path,*a,**kw):guard.lexical(path,query=True);guard.counts['lstat']+=1;return guard.raw_lstat(path,*a,**kw)
        def mkdir(path,*a,**kw):guard.check(path,True);return guard.raw_mkdir(path,*a,**kw)
        def resolve(path,*a,**kw):guard.lexical(path,query=True);return guard.resolve(path,*a,**kw)
        os.stat=stat;os.lstat=lstat;os.mkdir=mkdir;Path.resolve=resolve
        sys.addaudithook(self.audit)
    def projection(self):return dict(observed=dict(self.counts),denied=dict(self.denials),certificate=self.certificate_pin,
        metadata_intercepts=['os.stat','os.lstat','Path.resolve','os.mkdir'],
        limitations='Python audit and explicit metadata interfaces only; arbitrary native syscalls/kernel sandbox coverage UNAVAILABLE')

class NativeResult(unittest.TextTestResult):
    def __init__(self,*args):super().__init__(*args);self.events=[];self.states={}
    def event(self,test,actual):self.events.append(dict(id=test.id(),actual=actual));self.states[test.id()]=actual
    def startTest(self,test):super().startTest(test);self.event(test,'STARTED')
    def addSuccess(self,test):
        super().addSuccess(test)
        if self.states.get(test.id())=='STARTED':self.event(test,'PASS')
    def addError(self,test,err):super().addError(test,err);self.event(test,'ERROR')
    def addFailure(self,test,err):super().addFailure(test,err);self.event(test,'FAIL')
    def addSkip(self,test,reason):super().addSkip(test,reason);self.event(test,'SKIP')
    def addSubTest(self,test,subtest,err):
        super().addSubTest(test,subtest,err)
        if err:self.event(test,'FAIL' if issubclass(err[0],test.failureException) else 'ERROR')
    def addExpectedFailure(self,test,err):super().addExpectedFailure(test,err);self.event(test,'FAIL')
    def addUnexpectedSuccess(self,test):super().addUnexpectedSuccess(test);self.event(test,'FAIL')

def manifest(work):
    rows=[]
    for p in sorted(work.rglob('*')):
        if p.is_file():rows.append(dict(path=p.relative_to(work).as_posix(),bytes=p.stat().st_size,sha256=sha(p.read_bytes())))
    return rows

def native(folder):
    source=identity();guard=Guard(folder);guard.install();started=time.monotonic_ns()
    result=None;error=None;work=folder/'work';work.mkdir(exist_ok=False)
    restored=False
    try:
        sys.path.insert(0,str(ROOT));module=importlib.import_module(MODULE)
        need(module.c.ROOT==ROOT,'ORIGINAL_ROOT')
        before=module.c.WORK
        need(not str(work).casefold().startswith(str(before).casefold()+os.sep) and work!=before,'OLD_OWNER_ALIAS')
        from unittest.mock import patch
        with patch.object(module.c,'WORK',work):
            suite=unittest.TestSuite(module.DualTests(n) for n in NAMES)
            need([x.id() for x in suite]==IDS,'NATIVE_IDS')
            result=unittest.TextTestRunner(verbosity=2,resultclass=NativeResult).run(suite)
        restored=module.c.WORK==before
    except Exception as exc:error=type(exc).__name__
    states=result.states if result else {}
    report=dict(schema='rpf86-native-v1',source_level='SYNTHETIC_OFFLINE_TEST',
        marker='TEST_HARNESS_OWNER_SUBSTITUTION',ids=IDS,results=[dict(id=x,actual=states.get(x,'NOT_RUN')) for x in IDS],
        events=result.events if result else [],tests_run=result.testsRun if result else 0,source_identity=source,
        physical_owner=work.relative_to(ROOT).as_posix(),logical_owner='rpf-63',logical_identity_changed=False,
        patch_points=['pge_dual_contracts.WORK'],patch_restored=restored,guard=guard.projection(),
        source_unchanged=all(sha((ROOT/p).read_bytes())==v['raw_sha256'] for p,v in source['files'].items()),
        manifest=manifest(work),error=error,pid=os.getpid(),monotonic_start_ns=started,monotonic_end_ns=time.monotonic_ns(),
        actual_provider_calls=0,actual_sdk_calls=0,actual_java_processes=0,actual_business_writes=0,
        old_inode_comparison='UNAVAILABLE: no historical stat; fresh mkdir and no-reparse admission prove separation')
    success=report['tests_run']==5 and all(x['actual']=='PASS' for x in report['results']) and not report['guard']['denied'] and restored and report['source_unchanged'] and error is None
    report['status']='PASS' if success else 'FAIL';write(folder/'child-result.json',report)
    return 0 if success else 1

def environment(folder):
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','LANG','LC_ALL') if k in os.environ}
    if os.environ.get('GITHUB_ACTIONS')=='true':
        env.update({k:os.environ[k] for k in ('GITHUB_ACTIONS','GITHUB_WORKSPACE','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_SHA')})
    else:env['RPF86_TASK_ROOT']=str(local_task())
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',HOME=str(folder),USERPROFILE=str(folder),TEMP=str(folder),TMP=str(folder),TMPDIR=str(folder))
    return env

def launch(mode,folder,*,deadline,timeout=180,input_root=None,source_snapshot=None):
    folder=owned(folder);remaining=min(timeout,deadline-time.monotonic())
    need(0<remaining<=180,'TOTAL_DEADLINE')
    folder.mkdir(parents=True,exist_ok=False)
    args=[sys.executable,'-B',str(SELF),'--mode',mode,'--output',str(folder)]
    if input_root is not None:args+=['--input',str(input_root)]
    if source_snapshot is not None:args+=['--source-snapshot',str(source_snapshot)]
    started=time.monotonic_ns()
    process=subprocess.Popen(args,cwd=ROOT,env=environment(folder),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    chunks=[];size=0;overflow=threading.Event()
    def drain():
        nonlocal size
        while True:
            data=process.stdout.read(65536)
            if not data:break
            size+=len(data)
            if size>LIMIT:
                overflow.set()
                if process.poll() is None:process.kill()
                break
            chunks.append(data)
    thread=threading.Thread(target=drain,daemon=True);thread.start();timed_out=False
    try:process.wait(timeout=max(.001,min(remaining,deadline-time.monotonic())))
    except subprocess.TimeoutExpired:timed_out=True;process.kill();process.wait()
    thread.join(timeout=5)
    if not thread.is_alive():process.stdout.close()
    raw=b''.join(chunks)
    with (folder/'output.log').open('xb') as out:out.write(raw)
    receipt=dict(mode=mode,pid=process.pid,exit=process.returncode,timeout=timed_out,
        truncated=overflow.is_set() or thread.is_alive(),bytes=size,stdout_sha256=sha(raw),
        monotonic_start_ns=started,monotonic_end_ns=time.monotonic_ns(),timeout_limit_seconds=remaining,
        child_exited=process.poll() is not None,drain_joined=not thread.is_alive(),
        harness_lf_sha256=sha(SELF.read_bytes().replace(b'\r\n',b'\n')),
        cleanup_scope='Exact Popen handle; OS process-tree coverage UNAVAILABLE')
    write(folder/'launch-receipt.json',receipt)
    return receipt

def validate_native(report,receipt,source,work):
    need(type(report) is dict and report.get('schema')=='rpf86-native-v1','NATIVE_SCHEMA')
    need(report.get('ids')==IDS and report.get('results')==[dict(id=x,actual='PASS') for x in IDS],'EXACT_FIVE_PASS')
    need(type(report.get('tests_run')) is int and report['tests_run']==5,'FIVE_TESTS_RUN')
    need(report.get('source_identity')==source and report.get('source_unchanged') is True,'SOURCE_OR_ASSERTION_DRIFT')
    need(report.get('physical_owner')==work.relative_to(ROOT).as_posix() and report.get('logical_owner')=='rpf-63'
         and report.get('logical_identity_changed') is False,'OWNER_BINDING')
    need(report.get('marker')=='TEST_HARNESS_OWNER_SUBSTITUTION' and report.get('patch_points')==['pge_dual_contracts.WORK']
         and report.get('patch_restored') is True,'PATCH_SCOPE')
    need(report.get('status')=='PASS' and report.get('error') is None and report.get('guard',{}).get('denied')=={},'GUARD_OR_NATIVE_FAILURE')
    need(report['guard'].get('certificate')==source['certificate'] and report['guard'].get('observed',{}).get('certificate_read_granted',0)>0,'CERTIFICATE_READ_UNOBSERVED')
    need(report.get('source_level')=='SYNTHETIC_OFFLINE_TEST','SOURCE_LEVEL')
    need(report.get('actual_provider_calls')==report.get('actual_sdk_calls')==report.get('actual_java_processes')==report.get('actual_business_writes')==0,'REAL_RESOURCE_CLAIM')
    need(receipt.get('mode')=='native' and receipt.get('exit')==0 and receipt.get('timeout') is False and receipt.get('truncated') is False
         and receipt.get('child_exited') is True and receipt.get('drain_joined') is True,'CHILD_UNSETTLED')
    need(receipt.get('pid')==report.get('pid') and receipt.get('harness_lf_sha256')==source['harness_lf_sha256'],'PROCESS_SOURCE_BINDING')
    states={}
    for e in report.get('events',[]):
        need(type(e) is dict and set(e)=={'id','actual'} and e['id'] in IDS,'EVENT_ID')
        if e['actual']=='STARTED':need(e['id'] not in states,'DUPLICATE_START')
        else:need(states.get(e['id'])=='STARTED' and e['actual']=='PASS','UNOBSERVED_PASS')
        states[e['id']]=e['actual']
    need(states==dict.fromkeys(IDS,'PASS'),'MISSING_NATIVE_EVENT')
    need(type(report.get('manifest')) is list and bool(report['manifest']),'MISSING_PHYSICAL_WRITES')
    return True

def validate_log(log,receipt):
    need(len(log)<=LIMIT and len(log)==receipt['bytes'] and sha(log)==receipt['stdout_sha256'],'LOG_BINDING')

def independent(folder,input_root):
    input_root=owned(input_root);source=identity();guard=Guard(input_root);guard.install()
    native_dir=input_root/'native';report=strict((native_dir/'child-result.json').read_bytes());receipt=strict((native_dir/'launch-receipt.json').read_bytes())
    work=native_dir/'work';validate_native(report,receipt,source,work)
    log=(native_dir/'output.log').read_bytes();validate_log(log,receipt)
    files=manifest(work);need(files==report['manifest'],'PHYSICAL_MANIFEST_DRIFT')
    wal_count=0
    for file in files:
        if file['path'].endswith('/ledger.jsonl'):
            first=(work/file['path']).read_bytes().splitlines()[0]
            need(strict(first)['event'].get('owner')=='rpf-63','LOGICAL_WAL_OWNER')
            wal_count+=1
    need(wal_count>0,'NO_WAL')
    write(folder/'verification.json',dict(status='PASS',native_ids=IDS,manifest_sha256=sha(json.dumps(files,sort_keys=True).encode()),
        wal_files=wal_count,logical_owner='rpf-63',source_identity=source,guard=guard.projection(),
        source_level='SYNTHETIC_OFFLINE_TEST',independent_process=True,independent_issuer=False))
    return 0

def certificate_controls(folder):
    guard=Guard(folder);guard.install();rejected=[]
    sys.path.insert(0,str(ROOT))
    from runtime.runproof_runtime.effectwitness.config_experiment_verify import pinned_sdk_fields
    fields=pinned_sdk_fields();need(type(fields) is dict,'ORIGINAL_HELPER_IDENTITY')
    for label,fn in (
        ('directory',lambda:os.listdir(CERT_PATH.parent)),
        ('sibling',lambda:open(CERT_PATH.with_name('not-authorized.json'),'rb')),
        ('other-json',lambda:open(ROOT/'spikes/rpf-53/not-authorized.json','rb')),
        ('write',lambda:open(CERT_PATH,'xb')),
        ('truncate-audit',lambda:sys.audit('open',str(CERT_PATH),None,os.O_TRUNC)),
        ('case-alias',lambda:open(CERT_PATH.with_name('CONFIG-live-evidence.json'),'rb'))):
        try:fn()
        except PermissionError:rejected.append(label)
        else:raise Invalid('CERTIFICATE_BOUNDARY_INACTIVE')
    write(folder/'certificate-controls.json',dict(status='PASS',rejected=rejected,helper_identity_type='dict',
        original_helper_called=True,guard=guard.projection(),certificate_values_exported=False))
    return 0

def controls(folder):
    guard=Guard(folder);guard.install();codes=[]
    # The mkdir/stat shims deny before delegating to saved OS functions.
    old=ROOT/'.local/rpf-63'/('rpf86-never-created-'+folder.name)
    for label,fn in [('old-open',lambda:open(old,'rb')),('old-mkdir',lambda:os.mkdir(old)),
                     ('old-stat',lambda:os.stat(old))]:
        try:fn()
        except PermissionError as exc:need(str(exc)=='OLD_ROOT_ACCESS_DENIED','OLD_GUARD_REASON');codes.append(label)
        else:raise Invalid('OLD_ROOT_GUARD_INACTIVE')
    # If this guard regresses, a canary can affect only this fresh task parent.
    canary=folder.parent/('outside-'+folder.name+'.txt')
    try:open(canary,'wb')
    except PermissionError as exc:need(str(exc)=='WRITE_SCOPE_DENIED','CANARY_GUARD_REASON');codes.append('outside-write')
    else:raise Invalid('WRITE_GUARD_INACTIVE')
    import socket
    for label,fn in [('socket',lambda:socket.socket()),('process',lambda:subprocess.run([sys.executable,'-B','-c','pass']))]:
        try:fn()
        except PermissionError as exc:need(str(exc)=='NETWORK_PROCESS_NATIVE_DENIED','PROCESS_GUARD_REASON');codes.append(label)
        else:raise Invalid('PROCESS_GUARD_INACTIVE')
    write(folder/'control-result.json',dict(status='PASS',rejected=codes,guard=guard.projection(),old_root_delegations=0,
        canary_relative=canary.relative_to(ROOT).as_posix(),proof_scope='Actual Python APIs and pre-delegation metadata shims; no claim of a kernel sandbox'))
    return 0

def verify_failure(folder,input_root,snapshot):
    """Read-only verification of this task's failed run, no method re-execution."""
    input_root=owned(input_root);snapshot=owned(snapshot);source=identity()
    guard=Guard(folder,read_roots=(input_root,snapshot));guard.install()
    native_dir=input_root if (input_root/'child-result.json').exists() else input_root/'native'
    raw=(native_dir/'child-result.json').read_bytes();report=strict(raw)
    receipt=strict((native_dir/'launch-receipt.json').read_bytes())
    old_source=snapshot.read_bytes()
    need(report['ids']==IDS and [r['id'] for r in report['results']]==IDS and report['tests_run']==5,'FAILED_RUN_IDS')
    need(report['status']=='FAIL' and receipt['exit']==1 and receipt['mode']=='native'
         and receipt['timeout'] is False and receipt['truncated'] is False
         and receipt['child_exited'] is True and receipt['drain_joined'] is True,'FAILED_RUN_RECEIPT')
    need(receipt['pid']==report['pid'] and sha(old_source.replace(b'\r\n',b'\n'))==receipt['harness_lf_sha256']==report['source_identity']['harness_lf_sha256'],'FAILED_RUN_SOURCE_SNAPSHOT')
    need(all(report['source_identity'][k]==source[k] for k in ('files','method_ast','assertion_counts')) and report['source_unchanged'] is True,'ORIGINAL_SOURCE_DRIFT')
    states={}
    for e in report['events']:
        need(e['id'] in IDS,'FAILED_EVENT_ID')
        if e['actual']=='STARTED':need(e['id'] not in states,'FAILED_DUPLICATE_START')
        else:need(e['id'] in states and e['actual'] in ('PASS','FAIL','ERROR','SKIP'),'FAILED_EVENT_STATUS')
        states[e['id']]=e['actual']
    need([dict(id=tid,actual=states.get(tid,'NOT_RUN')) for tid in IDS]==report['results'],'FAILED_EVENT_SETTLEMENT')
    counts=dict(Counter(r['actual'] for r in report['results']))
    need(counts in ({'PASS':3,'ERROR':2},{'PASS':5}),'FAILED_RUN_COUNTS')
    need(report['guard']['denied'].get('OLD_ROOT_ACCESS_DENIED',0)==0
         and report['guard']['denied'].get('READ_SCOPE_DENIED',0)>0,'FAILED_BOUNDARY_REASON')
    need(report['patch_restored'] is True and report['logical_owner']=='rpf-63','FAILED_PATCH_RESTORE')
    work=native_dir/'work';need(report['physical_owner']==work.relative_to(ROOT).as_posix(),'FAILED_OWNER')
    files=manifest(work);need(files==report['manifest'],'FAILED_MANIFEST')
    wal_files=0
    for file in files:
        if file['path'].endswith('/ledger.jsonl'):
            need(strict((work/file['path']).read_bytes().splitlines()[0])['event'].get('owner')=='rpf-63','FAILED_LOGICAL_OWNER')
            wal_files+=1
    need(wal_files>0,'FAILED_NO_PHYSICAL_WAL')
    log=(native_dir/'output.log').read_bytes();need(sha(log)==receipt['stdout_sha256'] and len(log)==receipt['bytes'],'FAILED_LOG')
    need(report.get('error') is None and report.get('source_level')=='SYNTHETIC_OFFLINE_TEST','FAILED_SOURCE_LEVEL')
    if counts=={'PASS':5}:
        need(report['guard'].get('certificate')==source['certificate']
             and report['guard'].get('observed',{}).get('certificate_read_granted',0)>0,'FAILED_CERTIFICATE_READ')
    write(folder/'failure-verification.json',dict(status='PASS_NEGATIVE_EVIDENCE_ONLY',counts=counts,
        source_level='SYNTHETIC_OFFLINE_TEST',original_methods_reexecuted=False,report_sha256=sha(raw),
        manifest_sha256=sha(json.dumps(files,sort_keys=True).encode()),wal_files=wal_files,prior_harness_lf_sha256=receipt['harness_lf_sha256'],
        verifier_harness_lf_sha256=source['harness_lf_sha256'],guard=guard.projection(),
        admission_pass=False,conclusion='Five-method admission FAIL despite any passing methods; original sources unchanged; read-scope denials retained; independent process verified negative run.'))
    return 0

def run(output,total_deadline=None):
    output=owned(output);output.mkdir(parents=True,exist_ok=False);started=time.monotonic();deadline=started+420
    if total_deadline is not None:
        need(math.isfinite(total_deadline),'TOTAL_DEADLINE');deadline=min(deadline,total_deadline)
    source=identity();native_receipt=launch('native',output/'native',deadline=deadline)
    verification=None;error=None
    try:
        report=strict((output/'native/child-result.json').read_bytes())
        validate_native(report,native_receipt,source,output/'native/work')
        verification=launch('verify',output/'verify',deadline=deadline,timeout=60,input_root=output)
        need(verification['exit']==0 and not verification['timeout'] and not verification['truncated'] and verification['child_exited'],'INDEPENDENT_VERIFICATION')
    except (Invalid,OSError,ValueError,TypeError,KeyError) as exc:
        error=str(exc) if isinstance(exc,Invalid) else type(exc).__name__
    passed=error is None
    result=dict(schema='rpf86-owner-admission-pilot-v1',status='PASS' if passed else 'FAIL',
        source_level='SYNTHETIC_OFFLINE_TEST',marker='TEST_HARNESS_OWNER_SUBSTITUTION',ids=IDS,
        dedicated_owner_admission_pilot_pass=5 if passed else 0,source_identity=source,
        physical_owner=(output/'native/work').relative_to(ROOT).as_posix(),logical_owner='rpf-63',
        native_receipt=native_receipt,verification_receipt=verification,error=error,seconds=time.monotonic()-started,
        native_results=report.get('results',[]) if 'report' in locals() else [],
        formal_required_unavailable=539,official_coverage_changed=False,release_eligible=False,
        release_executed=False,deployment_authorized=False,actual_provider_calls=0,actual_sdk_calls=0,
        actual_java_processes=0,actual_business_writes=0,syscall_proof='Python audit + explicit metadata intercepts; arbitrary native syscall coverage UNAVAILABLE')
    write(output/'result.json',result);print(json.dumps({k:result[k] for k in ('status','dedicated_owner_admission_pilot_pass','formal_required_unavailable','error')}))
    return 0 if passed else 1

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=('run','native','verify','verify-failure','controls','certificate-controls','crash','exit1','missing','timeout','overflow'),default='run');parser.add_argument('--input',type=Path)
    parser.add_argument('--source-snapshot',type=Path)
    parser.add_argument('--deadline',type=float)
    args=parser.parse_args()
    try:
        folder=owned(args.output)
        if args.mode=='run':return run(folder,args.deadline)
        if args.mode=='native':return native(folder)
        if args.mode=='verify':return independent(folder,args.input)
        if args.mode=='controls':return controls(folder)
        if args.mode=='certificate-controls':return certificate_controls(folder)
        if args.mode=='verify-failure':return verify_failure(folder,args.input,args.source_snapshot)
        if args.mode=='crash':return 7
        if args.mode=='exit1':return 1
        if args.mode=='missing':return 0
        if args.mode=='timeout':time.sleep(10);return 0
        if args.mode=='overflow':sys.stdout.write('x'*(LIMIT+1));return 0
    except (Invalid,OSError,ValueError,TypeError,KeyError) as exc:
        print('INVALID_PILOT:'+ (str(exc) if isinstance(exc,Invalid) else type(exc).__name__),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())

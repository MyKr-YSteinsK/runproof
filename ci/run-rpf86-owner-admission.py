"""RPF86: five unchanged RPF63 methods, process-private WORK substitution.

No official coverage admission. No Provider/SDK/Java/network/process in child.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
import hashlib
import importlib
import importlib.util
import importlib.machinery
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
ATTRIBUTION_LIMIT=16
ATTRIBUTION_FILES=tuple(PINS)+(HELPER,'ci/run-rpf86-owner-admission.py',
    'ci/test_run_rpf86_owner_admission.py')+tuple(f'spikes/rpf-{n}/probe.py' for n in (53,55,63))
CACHE_SOURCES={'spikes/rpf-53/probe.py':'b15c595754c1ff4b213d3cbc0c6324622b9083e7',
               'spikes/rpf-55/probe.py':'6a1ae9d154adcc35f69455b32982faaedb5483bc'}

def cache_candidates():
    # Pure lexical computation. Never stat/open/list a historical cache.
    return {str(Path(importlib.util.cache_from_source(str(ROOT/name)))):'cache_probe_rpf'+('53' if 'rpf-53/' in name else '55') for name in CACHE_SOURCES}

def classify_cache(path,candidates):
    if path is None or isinstance(path,int):return 'other_public'
    p=Path(os.fsdecode(path))
    if '..' in p.parts or not p.is_absolute():return 'other_public'
    return candidates.get(str(p),'other_public')

def configure_cache(folder):
    folder=owned(folder);prefix=folder/'pycache';nonlink(prefix)
    need(sys.dont_write_bytecode is True,'BYTECODE_WRITES_ENABLED')
    prefix.mkdir(exist_ok=False);sys.pycache_prefix=str(prefix)
    need(all(Path(p).is_relative_to(prefix) for p in cache_candidates()),'CACHE_PREFIX_ESCAPE')
    return dict(policy='FRESH_OWNER_PREFIX',prefix_relative=prefix.relative_to(ROOT).as_posix(),dont_write_bytecode=True,
                source_pins=CACHE_SOURCES,global_loader_patch=False)

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
    need(p.is_absolute() and str(p.parent)==str(LOCAL) and re.fullmatch('rev5-[0-9a-f]{32}',p.name),'LOCAL_TASK_ROOT')
    nonlink(p)
    return p

def attribution_sources(overrides=None):
    result={};overrides=overrides or {}
    for name in ATTRIBUTION_FILES:
        raw=overrides.get(name)
        if raw is None:raw=(ROOT/name).read_bytes()
        tree=ast.parse(raw)
        result[name]=dict(raw_sha256=sha(raw),lines=len(raw.splitlines()),
            functions=[dict(name=n.name,start=n.lineno,end=n.end_lineno) for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))])
    return result
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
        commit=os.environ.get('GITHUB_SHA','')
        need(re.fullmatch('[0-9a-f]{40}',commit) is not None and subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==commit,'CI_COMMIT')
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
    cache_sources={}
    for name,pin in CACHE_SOURCES.items():
        raw=(ROOT/name).read_bytes();blob=subprocess.check_output(['git','cat-file','blob',pin],cwd=ROOT)
        need(raw.replace(b'\r\n',b'\n')==blob.replace(b'\r\n',b'\n'),'CACHE_SOURCE_PIN')
        cache_sources[name]=dict(blob=pin,raw_sha256=sha(raw),lf_sha256=sha(raw.replace(b'\r\n',b'\n')))
    return dict(files=result,cache_sources=cache_sources,certificate=certificate_identity(),helper=dict(blob=HELPER_BLOB,raw_sha256=sha(helper)),attribution_sources=attribution_sources(),method_ast={name:sha(ast.dump(methods[name],include_attributes=False).encode()) for name in NAMES},
                assertion_counts={name:sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr.startswith('assert') for n in ast.walk(methods[name])) for name in NAMES},
                harness_lf_sha256=sha(SELF.read_bytes().replace(b'\r\n',b'\n')))

JOURNAL_SCHEMA='rpf86-durable-denial-v1'
JOURNAL_MAX_FRAMES=32
JOURNAL_MAX_FRAME_BYTES=16384

class Journal:
    """One preopened, exclusive descriptor; durable before control continues."""
    def __init__(self,path,source,ids):
        nonlink(path);self.fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600)
        self.source=source;self.ids=ids;self.pid=os.getpid();self.run_id=os.urandom(16).hex()
        self.thread=threading.get_ident();self.seq=0;self.previous=None;self.failed=False;self.closed=False
        try:self.emit('INIT',dict(ids=ids))
        except Exception:self.close();raise
    def emit(self,kind,data):
        if threading.get_ident()!=self.thread:self.failed=True;raise Invalid('JOURNAL_THREAD')
        need(not self.failed and not self.closed,'JOURNAL_FAILED')
        try:
            need(self.seq<JOURNAL_MAX_FRAMES,'JOURNAL_CAP')
            frame=dict(schema=JOURNAL_SCHEMA,seq=self.seq,previous_raw_sha256=self.previous,pid=self.pid,
                monotonic_ns=time.monotonic_ns(),source_sha256=self.source,run_id=self.run_id,kind=kind,data=data)
            raw=json.dumps(frame,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
            need(len(raw)<=JOURNAL_MAX_FRAME_BYTES,'JOURNAL_FRAME_SIZE')
            pending=memoryview(raw)
            while pending:
                n=os.write(self.fd,pending);need(type(n) is int and 0<n<=len(pending),'JOURNAL_SHORT_WRITE');pending=pending[n:]
            os.fsync(self.fd)
            self.previous=sha(raw);self.seq+=1
        except Exception:
            self.failed=True;raise Invalid('JOURNAL_IO') from None
    def close(self):
        if not self.closed:os.close(self.fd);self.closed=True

def read_journal(path,source,pid,ids,sources,*,timeout=False):
    """Recover only validated physical frames. An empty prefix never proves zero."""
    frames=[];denials=[];methods={};active=None;previous=None;last_ns=-1;run_id=None;terminal=None;error=None
    try:
        raw=path.read_bytes();need(len(raw)<=JOURNAL_MAX_FRAMES*JOURNAL_MAX_FRAME_BYTES,'JOURNAL_FILE_SIZE')
        lines=raw.splitlines(keepends=True)
        for line in lines:
            need(line.endswith(b'\n') and len(line)<=JOURNAL_MAX_FRAME_BYTES,'JOURNAL_TORN')
            f=strict(line)
            need(set(f)=={'schema','seq','previous_raw_sha256','pid','monotonic_ns','source_sha256','run_id','kind','data'},'JOURNAL_FIELDS')
            need(f['schema']==JOURNAL_SCHEMA and type(f['seq']) is int and f['seq']==len(frames)<JOURNAL_MAX_FRAMES,'JOURNAL_SEQUENCE')
            need(f['previous_raw_sha256']==previous and f['pid']==pid and type(f['pid']) is int and f['source_sha256']==source,'JOURNAL_BINDING')
            need(type(f['monotonic_ns']) is int and f['monotonic_ns']>last_ns and re.fullmatch('[0-9a-f]{32}',f['run_id']) is not None,'JOURNAL_CLOCK_ID')
            need(run_id is None or run_id==f['run_id'],'JOURNAL_RUN_ID');need(terminal is None,'JOURNAL_AFTER_TERMINAL')
            kind=f['kind'];d=f['data'];need(type(d) is dict,'JOURNAL_DATA')
            if kind=='INIT':need(not frames and d==dict(ids=ids),'JOURNAL_INIT')
            else:need(bool(frames),'JOURNAL_MISSING_INIT')
            if kind=='METHOD_START':
                need(set(d)=={'id'} and d['id'] in ids and active is None and d['id'] not in methods,'JOURNAL_METHOD_START')
                active=d['id'];methods[active]='STARTED'
            elif kind=='METHOD_STOP':
                need(set(d)=={'id','actual'} and d['id']==active and d['actual'] in ('PASS','FAIL','ERROR','SKIP'),'JOURNAL_METHOD_STOP')
                methods[active]=d['actual'];active=None
            elif kind=='GUARD_DENY':
                fields={'sequence','reason','event_kind','intent','phase','method_id','target_class','public_repo_relative_path','target_token',
                    'caller','caller_chain','status','method_later_status','broad_exception_context','assertRaises_broad_exception_risk',
                    'permission_error_observed_in_method','continued_after_broad_context','cache_probe'}
                need(set(d)==fields and len(denials)<ATTRIBUTION_LIMIT,'JOURNAL_DENIAL_FIELDS')
                need(d['method_id']==active and d['method_later_status'] is None,'JOURNAL_METHOD_BINDING')
                need(d['caller'] is not None and bool(d['caller_chain']) and all(not c['function'].startswith('<') for c in d['caller_chain']),'JOURNAL_UNKNOWN_CALLER')
                need(d['target_class'] in ('unknown','protected','fresh_owned_synthetic_path','private_old_root','exact_pinned_certificate','approved_source','unapproved_repo_public_path','interpreter_runtime','outside_repo'),'JOURNAL_TARGET_CLASS')
                candidate=denials+[d]
                proxy=dict(attribution_schema='rpf86-denial-events-v1',attribution_events=candidate,attribution_total=len(candidate),
                    attribution_truncated=False,attribution_sources=sources,attribution_sha256=sha(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()),denied=dict(Counter(e['reason'] for e in candidate)))
                validate_attribution(proxy,sources,ids);denials=candidate
            elif kind=='TERMINAL':
                need(set(d)=={'status','error'} and d['status'] in ('PASS','FAIL') and (d['error'] is None or re.fullmatch('[A-Z_]{1,64}',d['error']) is not None),'JOURNAL_TERMINAL')
                if d['status']=='PASS':need(active is None and methods==dict.fromkeys(ids,'PASS') and not denials and d['error'] is None,'JOURNAL_FALSE_GREEN')
                terminal=d
            elif kind not in ('INIT','METHOD_START','METHOD_STOP','GUARD_DENY'):raise Invalid('JOURNAL_KIND_OR_OVERFLOW')
            frames.append(f);previous=sha(line);last_ns=f['monotonic_ns'];run_id=f['run_id']
        need(bool(frames),'JOURNAL_EMPTY')
    except (Invalid,OSError,ValueError,TypeError,KeyError) as exc:
        if 'raw' not in locals():raw=b''
        error=str(exc) if isinstance(exc,Invalid) else type(exc).__name__
    return dict(schema=JOURNAL_SCHEMA,status='TORN_OR_MISSING' if error else 'COMPLETE' if terminal else 'INCOMPLETE_TIMEOUT' if timeout else 'INCOMPLETE_EXIT',
        error=error,raw_sha256=sha(raw),bytes=len(raw),valid_prefix_frames=len(frames),prefix_tip_sha256=previous,
        pid=pid,source_sha256=source,run_id=run_id,method_start_stop=[f for f in frames if f['kind'] in ('METHOD_START','METHOD_STOP')],
        methods=methods,latest_method=active,denial_events=denials,terminal=terminal,terminal_present=terminal is not None,
        zero_denials_proven=bool(not error and terminal and terminal['status']=='PASS' and not denials),
        last_frame_monotonic_ns=last_ns if frames else None,completion_without_terminal='UNAVAILABLE')

class Guard:
    """CPython audit + bounded metadata intercepts; not a kernel sandbox."""
    def __init__(self,owner,read_roots=(),journal=None):
        self.owner=owner;self.private=ROOT/'.local';self.forbidden=ROOT/'docs/reviews'
        self.task_scope=Path(os.environ['RPF86_TASK_ROOT']) if os.environ.get('RPF86_TASK_ROOT') else owner
        self.read_roots=tuple(read_roots)
        self.counts=Counter();self.denials=Counter();self.cache=set()
        self.raw_stat=os.stat;self.raw_lstat=os.lstat;self.raw_mkdir=os.mkdir
        self.raw_open=builtins.open;self.checking_certificate=False
        self.certificate_pin=certificate_identity()
        self.resolve=Path.resolve
        self.runtime=[Path(sys.base_prefix).resolve(),Path(sys.prefix).resolve(),Path(sysconfig.get_path('stdlib')).resolve()]
        self.events=[];self.sequence=0;self.truncated=False;self.phase='setup';self.method=None
        self.journal=journal
        self.cache_candidates=cache_candidates()
        self.operation=('unknown',None,False);self.salt=os.urandom(32);self.sources=attribution_sources();self.broad={}
        for name in ATTRIBUTION_FILES:
            raw=(ROOT/name).read_bytes();tree=ast.parse(raw)
            self.broad[name]=[(n.lineno,n.end_lineno) for n in ast.walk(tree) if isinstance(n,ast.With)
                and any(isinstance(i.context_expr,ast.Call) and isinstance(i.context_expr.func,ast.Attribute)
                and i.context_expr.func.attr=='assertRaises' and any(isinstance(a,ast.Name) and a.id=='Exception' for a in i.context_expr.args) for i in n.items)]
    def context(self,event,path=None,write=False):self.operation=(event,path,write)
    def method_start(self,method):
        self.method=method;self.phase='method'
        if self.journal:self.journal.emit('METHOD_START',dict(id=method))
    def method_stop(self,method,actual):
        need(self.method==method,'ATTRIBUTION_METHOD_TRANSITION')
        for e in self.events:
            if e['method_id']==method:e['method_later_status']=actual
        if self.journal:self.journal.emit('METHOD_STOP',dict(id=method,actual=actual))
        self.method=None;self.phase='report'
    def trace(self,frame,event,arg):
        # Reject unrelated calls before constructing any Path. Global tracing
        # observes call events throughout this source-heavy synthetic cohort.
        if self.method is None or frame.f_code.co_name!=self.method.rsplit('.',1)[-1]:return None
        name=frame.f_code.co_filename
        try:relative=Path(name).relative_to(ROOT).as_posix()
        except ValueError:return None
        if relative not in self.sources:return None
        if event=='call':self.phase='method'
        if event=='exception' and arg[0] is PermissionError:
            for e in reversed(self.events):
                if e['method_id']==self.method and e['reason']==str(arg[1]):
                    e['permission_error_observed_in_method']=True;break
        if event=='line':
            for e in self.events:
                if e['method_id']==self.method and e['permission_error_observed_in_method'] and e['broad_exception_context']:
                    if not any(a<=frame.f_lineno<=b for a,b in self.broad[relative]):e['continued_after_broad_context']=True
        if event=='return':self.phase='teardown'
        return self.trace
    def target(self,path):
        if path is None or isinstance(path,int):return 'unknown',None,None
        p=Path(os.path.abspath(os.fsdecode(path)));s=str(p).casefold()
        inside=lambda base:s==str(base).casefold() or s.startswith(str(base).casefold()+os.sep)
        public=None
        if inside(self.forbidden):kind='protected'
        elif inside(self.owner) or inside(self.task_scope):kind='fresh_owned_synthetic_path'
        elif inside(self.private):kind='private_old_root'
        elif str(p)==str(CERT_PATH):kind='exact_pinned_certificate';public=CERT_NAME
        elif inside(ROOT):
            relative=p.relative_to(ROOT).as_posix()
            if relative in ATTRIBUTION_FILES:kind='approved_source';public=relative
            else:kind='unapproved_repo_public_path'
        elif any(inside(r) for r in self.runtime):kind='interpreter_runtime'
        else:kind='outside_repo'
        return kind,public,sha(self.salt+str(p).encode('utf8',errors='replace'))
    def denied(self,code):
        self.denials[code]+=1;self.sequence+=1
        if len(self.events)>=ATTRIBUTION_LIMIT:
            if not self.truncated and self.journal:self.journal.emit('OVERFLOW',dict(reason='ATTRIBUTION_TRUNCATED'))
            self.truncated=True
        else:
            event,path,writing=self.operation;kind,public,token=self.target(path);callers=[];broad=False
            frame=sys._getframe(1)
            for _ in range(48):
                if frame is None:break
                try:name=Path(frame.f_code.co_filename).relative_to(ROOT).as_posix()
                except ValueError:name=None
                if name in self.sources and not frame.f_code.co_name.startswith('<') and not (name=='ci/run-rpf86-owner-admission.py' and frame.f_code.co_name in
                    ('denied','lexical','check','audit','stat','lstat','mkdir','resolve')):
                    if len(callers)<8:callers.append(dict(path=name,function=frame.f_code.co_name,line=frame.f_lineno,source_sha256=self.sources[name]['raw_sha256']))
                    broad=broad or any(a<=frame.f_lineno<=b for a,b in self.broad[name])
                frame=frame.f_back
            self.events.append(dict(sequence=self.sequence,reason=code,event_kind=event,intent='write' if writing else 'read',
                phase=self.phase,method_id=self.method,target_class=kind,public_repo_relative_path=public,target_token=token,
                caller=callers[0] if callers else None,caller_chain=callers,status='DENIED_BEFORE_IO',method_later_status=None,
                broad_exception_context=broad,assertRaises_broad_exception_risk='SUSPECTED' if broad else 'NOT_OBSERVED',
                permission_error_observed_in_method=False,continued_after_broad_context=False,
                cache_probe='private_or_protected' if kind in ('private_old_root','protected','outside_repo') else classify_cache(path,self.cache_candidates)))
            if self.journal:self.journal.emit('GUARD_DENY',self.events[-1])
        raise PermissionError(code)
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
        if self.operation[0]=='unknown':self.context('Guard.check',path,write)
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
        if event in ('open','os.listdir','os.scandir','os.mkdir','os.remove','os.rmdir','os.chmod','os.utime','os.truncate','os.rename','os.link','os.symlink'):
            self.context(event,args[0] if args else None)
        if event=='open':
            path,mode,flags=args
            writing=bool(isinstance(mode,str) and any(x in mode for x in 'wax+') or isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if self.checking_certificate and str(path)==str(CERT_PATH) and not writing:return
            self.context(event,path,writing)
            self.check(path,writing)
        elif event in ('os.listdir','os.scandir'):self.check(args[0])
        elif event in ('os.mkdir','os.remove','os.rmdir','os.chmod','os.utime','os.truncate'):
            self.context(event,args[0],True);self.check(args[0],True)
        elif event in ('os.rename','os.link','os.symlink'):self.denied('LINK_OR_RENAME_DENIED')
        elif event.startswith(('socket.','subprocess.','ctypes.')) or event in ('os.system','os.posix_spawn','os.spawn','os.fork','os.forkpty') or event.startswith('os.exec'):
            self.context(event)
            self.denied('NETWORK_PROCESS_NATIVE_DENIED')
        elif event=='import' and str(args[0]).startswith(('pydantic_ai','openai','httpx2')):
            self.context(event);self.denied('SDK_IMPORT_DENIED')
    def install(self):
        guard=self
        def stat(path,*a,**kw):guard.context('stat interception',path);guard.lexical(path,query=True);guard.counts['stat']+=1;return guard.raw_stat(path,*a,**kw)
        def lstat(path,*a,**kw):guard.context('lstat interception',path);guard.lexical(path,query=True);guard.counts['lstat']+=1;return guard.raw_lstat(path,*a,**kw)
        def mkdir(path,*a,**kw):guard.context('mkdir interception',path,True);guard.check(path,True);return guard.raw_mkdir(path,*a,**kw)
        def resolve(path,*a,**kw):guard.context('resolve interception',path);guard.lexical(path,query=True);return guard.resolve(path,*a,**kw)
        os.stat=stat;os.lstat=lstat;os.mkdir=mkdir;Path.resolve=resolve
        sys.addaudithook(self.audit)
    def projection(self):return dict(observed=dict(self.counts),denied=dict(self.denials),certificate=self.certificate_pin,
        attribution_schema='rpf86-denial-events-v1',attribution_events=self.events,attribution_total=self.sequence,
        attribution_truncated=self.truncated,attribution_sources=self.sources,
        attribution_sha256=sha(json.dumps(self.events,sort_keys=True,separators=(',',':')).encode()),
        metadata_intercepts=['os.stat','os.lstat','Path.resolve','os.mkdir'],
        limitations='Python audit and explicit metadata interfaces only; arbitrary native syscalls/kernel sandbox coverage UNAVAILABLE')

class NativeResult(unittest.TextTestResult):
    def __init__(self,*args,guard=None):super().__init__(*args);self.events=[];self.states={};self.guard=guard
    def event(self,test,actual):self.events.append(dict(id=test.id(),actual=actual));self.states[test.id()]=actual
    def startTest(self,test):
        super().startTest(test);self.event(test,'STARTED')
        if self.guard:self.guard.method_start(test.id())
    def stopTest(self,test):
        if self.guard:self.guard.method_stop(test.id(),self.states.get(test.id(),'NOT_RUN'))
        super().stopTest(test)
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

def run_suite(suite,guard,*,synthetic_trace=False):
    # Production five-method cohort never installs a per-line/global tracer.
    before=sys.gettrace()
    if synthetic_trace:sys.settrace(guard.trace)
    try:return unittest.TextTestRunner(verbosity=2,resultclass=lambda *a:NativeResult(*a,guard=guard)).run(suite)
    finally:
        if synthetic_trace:sys.settrace(before)

def validate_attribution(guard,sources,ids):
    need(guard.get('attribution_schema')=='rpf86-denial-events-v1','ATTRIBUTION_SCHEMA')
    events=guard.get('attribution_events');need(type(events) is list and len(events)<=ATTRIBUTION_LIMIT,'ATTRIBUTION_SIZE')
    need(guard.get('attribution_truncated') is False and guard.get('attribution_total')==len(events),'ATTRIBUTION_TRUNCATED')
    need(guard.get('attribution_sources')==sources,'ATTRIBUTION_SOURCE')
    need(guard.get('attribution_sha256')==sha(json.dumps(events,sort_keys=True,separators=(',',':')).encode()),'ATTRIBUTION_EVENT_HASH')
    need([e.get('sequence') for e in events]==list(range(1,len(events)+1)),'ATTRIBUTION_SEQUENCE')
    need(dict(Counter(e.get('reason') for e in events))==guard.get('denied'),'ATTRIBUTION_COUNTS')
    for e in events:
        need(e.get('status')=='DENIED_BEFORE_IO' and e.get('phase') in ('import','setup','method','teardown','report'),'ATTRIBUTION_PHASE')
        method=e.get('method_id');need(method is None or method in ids,'ATTRIBUTION_METHOD')
        need(e['phase'] not in ('method','teardown') or method in ids,'ATTRIBUTION_METHOD_MISSING')
        need(e.get('intent') in ('read','write') and isinstance(e.get('event_kind'),str),'ATTRIBUTION_OPERATION')
        need(e.get('cache_probe') in ('cache_probe_rpf53','cache_probe_rpf55','other_public','private_or_protected'),'CACHE_CLASSIFICATION')
        if e['cache_probe'].startswith('cache_probe_'):
            need(e['intent']=='read' and e['event_kind']=='open' and e['target_class']=='unapproved_repo_public_path','CACHE_EVENT_CONTEXT')
        public=e.get('public_repo_relative_path')
        need(public is None or public in ATTRIBUTION_FILES+(CERT_NAME,),'ATTRIBUTION_REDACTION')
        need(e.get('target_token') is None or re.fullmatch('[0-9a-f]{64}',e['target_token']) is not None,'ATTRIBUTION_TOKEN')
        callers=e.get('caller_chain');need(type(callers) is list and len(callers)<=8 and e.get('caller')==(callers[0] if callers else None),'ATTRIBUTION_CALLER')
        for caller in callers:
            name=caller.get('path');need(name in sources,'ATTRIBUTION_CALLER_SOURCE')
            info=sources[name];need(caller.get('source_sha256')==info['raw_sha256'],'ATTRIBUTION_CALLER_PIN')
            line=caller.get('line');need(type(line) is int and 1<=line<=info['lines'],'ATTRIBUTION_CALLER_LINE')
            need(caller.get('function')=='<module>' or any(f['name']==caller.get('function') and f['start']<=line<=f['end'] for f in info['functions']),'ATTRIBUTION_CALLER_FUNCTION')
    return True

def manifest(work):
    rows=[]
    for p in sorted(work.rglob('*')):
        if p.is_file():rows.append(dict(path=p.relative_to(work).as_posix(),bytes=p.stat().st_size,sha256=sha(p.read_bytes())))
    return rows

def native(folder):
    cache_policy=configure_cache(folder)
    source=identity();journal=Journal(folder/'denial-journal.jsonl',source['harness_lf_sha256'],IDS)
    guard=Guard(folder,journal=journal);guard.install();started=time.monotonic_ns()
    result=None;error=None;work=folder/'work';work.mkdir(exist_ok=False)
    restored=False
    try:
        guard.phase='import';sys.path.insert(0,str(ROOT));module=importlib.import_module(MODULE);guard.phase='setup'
        need(module.c.ROOT==ROOT,'ORIGINAL_ROOT')
        before=module.c.WORK
        need(not str(work).casefold().startswith(str(before).casefold()+os.sep) and work!=before,'OLD_OWNER_ALIAS')
        from unittest.mock import patch
        with patch.object(module.c,'WORK',work):
            suite=unittest.TestSuite(module.DualTests(n) for n in NAMES)
            need([x.id() for x in suite]==IDS,'NATIVE_IDS')
            result=run_suite(suite,guard)
        restored=module.c.WORK==before
    except Exception as exc:error=type(exc).__name__
    guard.phase='report';states=result.states if result else {}
    report=dict(schema='rpf86-native-v1',source_level='SYNTHETIC_OFFLINE_TEST',
        marker='TEST_HARNESS_OWNER_SUBSTITUTION',ids=IDS,results=[dict(id=x,actual=states.get(x,'NOT_RUN')) for x in IDS],
        events=result.events if result else [],tests_run=result.testsRun if result else 0,source_identity=source,
        physical_owner=work.relative_to(ROOT).as_posix(),logical_owner='rpf-63',logical_identity_changed=False,
        patch_points=['pge_dual_contracts.WORK'],patch_restored=restored,guard=guard.projection(),
        source_unchanged=all(sha((ROOT/p).read_bytes())==v['raw_sha256'] for p,v in source['files'].items()),
        manifest=manifest(work),error=error,pid=os.getpid(),monotonic_start_ns=started,monotonic_end_ns=time.monotonic_ns(),
        actual_provider_calls=0,actual_sdk_calls=0,actual_java_processes=0,actual_business_writes=0,
        old_inode_comparison='UNAVAILABLE: no historical stat; fresh mkdir and no-reparse admission prove separation')
    report['cache_policy']=cache_policy;report['guard']=guard.projection()
    try:validate_attribution(report['guard'],source['attribution_sources'],IDS)
    except Invalid as exc:report['error']=str(exc)
    success=report['tests_run']==5 and all(x['actual']=='PASS' for x in report['results']) and not report['guard']['denied'] and restored and report['source_unchanged'] and report['error'] is None
    report['status']='PASS' if success else 'FAIL';write(folder/'child-result.json',report)
    journal.emit('TERMINAL',dict(status=report['status'],error=None if report['error'] is None else 'NATIVE_ERROR'))
    journal.close()
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
            if size>(256*1024 if mode=='import-probe' else LIMIT):
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
    if (folder/'child-result.json').is_file():receipt['child_result_raw_sha256']=sha((folder/'child-result.json').read_bytes())
    if (folder/'denial-journal.jsonl').is_file():
        receipt['journal']=read_journal(folder/'denial-journal.jsonl',receipt['harness_lf_sha256'],process.pid,
            IDS if mode=='native' else [] if mode=='import-probe' else ['synthetic.durable_control'],attribution_sources(),timeout=timed_out)
    write(folder/'launch-receipt.json',receipt)
    return receipt

def validate_native(report,receipt,source,work):
    need(type(report) is dict and report.get('schema')=='rpf86-native-v1','NATIVE_SCHEMA')
    need(report.get('ids')==IDS and report.get('results')==[dict(id=x,actual='PASS') for x in IDS],'EXACT_FIVE_PASS')
    need(type(report.get('tests_run')) is int and report['tests_run']==5,'FIVE_TESTS_RUN')
    need(report.get('source_identity')==source and report.get('source_unchanged') is True,'SOURCE_OR_ASSERTION_DRIFT')
    validate_attribution(report.get('guard',{}),source['attribution_sources'],IDS)
    need(report.get('physical_owner')==work.relative_to(ROOT).as_posix() and report.get('logical_owner')=='rpf-63'
         and report.get('logical_identity_changed') is False,'OWNER_BINDING')
    validate_cache_policy(report.get('cache_policy'),work)
    need(report.get('marker')=='TEST_HARNESS_OWNER_SUBSTITUTION' and report.get('patch_points')==['pge_dual_contracts.WORK']
         and report.get('patch_restored') is True,'PATCH_SCOPE')
    need(report.get('status')=='PASS' and report.get('error') is None and report.get('guard',{}).get('denied')=={},'GUARD_OR_NATIVE_FAILURE')
    need(report['guard'].get('certificate')==source['certificate'] and report['guard'].get('observed',{}).get('certificate_read_granted',0)>0,'CERTIFICATE_READ_UNOBSERVED')
    need(report.get('source_level')=='SYNTHETIC_OFFLINE_TEST','SOURCE_LEVEL')
    need(report.get('actual_provider_calls')==report.get('actual_sdk_calls')==report.get('actual_java_processes')==report.get('actual_business_writes')==0,'REAL_RESOURCE_CLAIM')
    need(receipt.get('mode')=='native' and receipt.get('exit')==0 and receipt.get('timeout') is False and receipt.get('truncated') is False
         and receipt.get('child_exited') is True and receipt.get('drain_joined') is True,'CHILD_UNSETTLED')
    need(receipt.get('pid')==report.get('pid') and receipt.get('harness_lf_sha256')==source['harness_lf_sha256'],'PROCESS_SOURCE_BINDING')
    journal=receipt.get('journal',{})
    need(journal.get('schema')==JOURNAL_SCHEMA and journal.get('status')=='COMPLETE' and journal.get('zero_denials_proven') is True
         and journal.get('methods')==dict.fromkeys(IDS,'PASS') and journal.get('denial_events')==[]
         and journal.get('terminal')=={'status':'PASS','error':None} and journal.get('pid')==receipt['pid']
         and journal.get('source_sha256')==source['harness_lf_sha256'],'JOURNAL_NATIVE_BINDING')
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

def validate_cache_policy(policy,work):
    expected=dict(policy='FRESH_OWNER_PREFIX',prefix_relative=(work.parent/'pycache').relative_to(ROOT).as_posix(),
        dont_write_bytecode=True,source_pins=CACHE_SOURCES,global_loader_patch=False)
    need(policy==expected,'CACHE_POLICY_BINDING')

def read_child_report(folder,receipt):
    raw=(folder/'child-result.json').read_bytes()
    need(sha(raw)==receipt.get('child_result_raw_sha256'),'CHILD_REPORT_BINDING')
    return strict(raw)

def validate_physical_journal(folder,receipt,source):
    journal=read_journal(folder/'denial-journal.jsonl',source['harness_lf_sha256'],receipt['pid'],IDS,source['attribution_sources'])
    need(journal['status']=='COMPLETE' and journal['zero_denials_proven'] and journal['methods']==dict.fromkeys(IDS,'PASS'),'JOURNAL_NOT_ADMISSIBLE')
    need(receipt.get('journal')==journal and receipt.get('exit')==0 and receipt.get('timeout') is False
         and receipt.get('child_exited') is True and receipt.get('drain_joined') is True,'JOURNAL_RECEIPT_BINDING')
    need(receipt['monotonic_start_ns']<=journal['last_frame_monotonic_ns']<=receipt['monotonic_end_ns'],'JOURNAL_RECEIPT_TIME')
    return journal

def independent(folder,input_root):
    input_root=owned(input_root);source=identity();guard=Guard(input_root);guard.install()
    native_dir=input_root/'native';receipt=strict((native_dir/'launch-receipt.json').read_bytes());report=read_child_report(native_dir,receipt)
    work=native_dir/'work';validate_native(report,receipt,source,work)
    journal=validate_physical_journal(native_dir,receipt,source)
    nonlink(native_dir/'pycache');need(not list((native_dir/'pycache').rglob('*.pyc')),'BYTECODE_CACHE_WRITES')
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
        journal=journal,
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

def false_green_controls(folder):
    target=folder/'new-synthetic-input.json';target.write_bytes(b'not historical data')
    sandbox=folder/'sandbox';sandbox.mkdir(exist_ok=False)
    guard=Guard(sandbox);guard.install()
    class Synthetic(unittest.TestCase):
        def test_guard_false_green(self):
            with self.assertRaises(Exception):
                guard.context('Guard.check',target);guard.check(target)
            self.assertTrue(True)
    result=run_suite(unittest.TestSuite([Synthetic('test_guard_false_green')]),guard,synthetic_trace=True)
    projection=guard.projection();ids=list(result.states)
    validate_attribution(projection,guard.sources,ids)
    need(result.wasSuccessful() and len(projection['attribution_events'])==1,'FALSE_GREEN_NOT_EXERCISED')
    event=projection['attribution_events'][0]
    need(event['phase']=='method' and event['method_later_status']=='PASS' and event['permission_error_observed_in_method']
         and event['continued_after_broad_context'] and event['broad_exception_context'],'FALSE_GREEN_CAUSAL_TRACE')
    write(sandbox/'false-green.json',dict(status='PASS_NEGATIVE_CONTROL',native_method_status='PASS',
        admission_status='FAIL',guard=projection,ids=ids,delegated_target_io=0))
    return 0

def durable_control(folder,mode):
    target=folder/'new-synthetic-input.json';target.write_bytes(b'new fixture')
    sandbox=folder/'sandbox';sandbox.mkdir(exist_ok=False)
    journal=Journal(folder/'denial-journal.jsonl',sha(SELF.read_bytes().replace(b'\r\n',b'\n')),['synthetic.durable_control'])
    guard=Guard(sandbox,journal=journal);guard.install();guard.method_start('synthetic.durable_control')
    if mode=='durable-timeout':time.sleep(10);return 1
    try:guard.context('Guard.check',target);guard.check(target)
    except PermissionError:os._exit(7)  # Descriptor was fsynced before the exception.
    return 1

def performance_probe(folder):
    import statistics
    old=ROOT/'spikes/rpf-86/rev-5/pre-repair-sources/run-rpf86-owner-admission.py'
    old_raw=old.read_bytes();tree=ast.parse(old_raw);cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='Guard')
    node=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='trace')
    namespace=dict(ROOT=ROOT,Path=Path);exec(compile(ast.Module(body=[node],type_ignores=[]),'<pinned-trace-microprobe>','exec'),namespace)
    candidate_sha=sha(SELF.read_bytes().replace(b'\r\n',b'\n'))
    guard=Guard(folder);guard.install();samples=[];calls=0
    def traced(frame,event,arg):
        nonlocal calls
        calls+=1;return namespace['trace'](guard,frame,event,arg)
    def normal_call(i):return (i*7+3)%101
    previous=sys.gettrace()
    for mode in ('base_global_trace','candidate_no_trace'):
        rows=[]
        for _ in range(7):
            guard.method='synthetic.never_matched';start=time.perf_counter_ns()
            if mode=='base_global_trace':sys.settrace(traced)
            try:value=sum(normal_call(i) for i in range(2000))
            finally:
                if mode=='base_global_trace':sys.settrace(previous)
            rows.append(time.perf_counter_ns()-start)
        samples.append(dict(mode=mode,iterations=2000,samples_ns=rows,median_ns=statistics.median(rows),min_ns=min(rows),max_ns=max(rows),checksum=value))
    write(folder/'performance.json',dict(status='OBSERVED_NO_SPEED_THRESHOLD',samples=samples,base_trace_callbacks=calls,
        base_source_raw_sha256=sha(old_raw),candidate_source_lf_sha256=candidate_sha,
        scope='Fixed arithmetic calls under actual Guard audit hook; independent microprobe, not native-cohort causal proof'))
    return 0

def import_probe(folder):
    source=identity();journal=Journal(folder/'denial-journal.jsonl',source['harness_lf_sha256'],[])
    metadata=dict(cache_tag=sys.implementation.cache_tag,dont_write_bytecode=sys.dont_write_bytecode,
        pycache_prefix_present=sys.pycache_prefix is not None,candidate_classes=sorted(cache_candidates().values()),
        candidate_path_hashes={v:sha(k.encode()) for k,v in cache_candidates().items()})
    guard=Guard(folder,journal=journal);guard.install();guard.phase='import';error=None
    try:sys.path.insert(0,str(ROOT));importlib.import_module(MODULE)
    except Exception as exc:error=type(exc).__name__
    projection=guard.projection()
    supported=sorted(e['cache_probe'] for e in guard.events)==['cache_probe_rpf53','cache_probe_rpf55'] and len(guard.events)==2 and error is None
    journal.emit('TERMINAL',dict(status='FAIL' if guard.events or error else 'PASS',error=None if error is None else 'IMPORT_ERROR'));journal.close()
    write(folder/'import-probe.json',dict(status='H_CACHE_SUPPORTED' if supported else 'H_CACHE_NOT_CONFIRMED',
        python_version=sys.version.split()[0],python_identity=metadata,source_identity=source,guard=projection,
        original_methods_executed=False,no_target_bytes_read=True,no_target_stat_or_list=True,error=error))
    return 0 if supported else 1

def cache_controls(folder):
    before=cache_candidates();policy=configure_cache(folder);source=identity()
    loader=importlib.machinery.SourceFileLoader;guard=Guard(folder);guard.install();sys.path.insert(0,str(ROOT))
    loaded=[]
    for name in CACHE_SOURCES:
        spec=importlib.util.spec_from_file_location('controlled_'+('53' if 'rpf-53/' in name else '55'),ROOT/name)
        need(type(spec.loader) is loader,'CACHE_LOADER_CHANGED');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        need(module.__file__==str(ROOT/name),'CACHE_MODULE_SOURCE');loaded.append(name)
    need(not guard.denials,'CACHE_CONTROL_IMPORT_DENIAL')
    refused=0
    for target in before:
        try:open(target,'rb')
        except PermissionError:refused+=1
        else:raise Invalid('HISTORICAL_CACHE_GRANTED')
    need(refused==2 and importlib.machinery.SourceFileLoader is loader,'CACHE_OLD_PROTECTION')
    write(folder/'cache-controls.json',dict(status='PASS',policy=policy,loaded_source_files=loaded,
        source_pins=source['cache_sources'],historical_cache_reads_denied=refused,
        actual_cache_files_created=len(list((folder/'pycache').rglob('*.pyc'))),guard=guard.projection(),global_loader_patch=False))
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
    if (input_root/'denial-journal.jsonl').exists():
        receipt=strict((input_root/'launch-receipt.json').read_bytes());old_source=snapshot.read_bytes()
        need(receipt.get('mode')=='native' and receipt.get('exit')!=0 and receipt.get('child_exited') is True
             and receipt.get('drain_joined') is True and not receipt.get('truncated'),'NEGATIVE_NATIVE_RECEIPT')
        need(sha(old_source.replace(b'\r\n',b'\n'))==receipt['harness_lf_sha256'],'NEGATIVE_SOURCE_BINDING')
        sources=attribution_sources({'ci/run-rpf86-owner-admission.py':old_source})
        journal=read_journal(input_root/'denial-journal.jsonl',receipt['harness_lf_sha256'],receipt['pid'],IDS,sources,timeout=receipt.get('timeout',False))
        need(journal==receipt.get('journal'),'NEGATIVE_JOURNAL_BINDING')
        validate_log((input_root/'output.log').read_bytes(),receipt)
        files=manifest(input_root/'work');wal_count=0
        for row in files:
            if row['path'].endswith('/ledger.jsonl'):
                need(strict((input_root/'work'/row['path']).read_bytes().splitlines()[0])['event'].get('owner')=='rpf-63','NEGATIVE_WAL_OWNER');wal_count+=1
        need(wal_count>0,'NEGATIVE_NO_WAL')
        if (input_root/'child-result.json').exists():
            report=read_child_report(input_root,receipt)
            need(report['status']=='FAIL' and report['manifest']==files and report['logical_owner']=='rpf-63'
                 and report['patch_restored'] is True and report['source_unchanged'] is True,'NEGATIVE_REPORT')
            need(all(report['source_identity'][k]==source[k] for k in ('files','method_ast','assertion_counts','certificate','helper')),'NEGATIVE_ORIGINAL_SOURCE')
        write(folder/'failure-verification.json',dict(status='PASS_NEGATIVE_EVIDENCE_ONLY',admission_pass=False,
            journal=journal,wal_files=wal_count,manifest_sha256=sha(json.dumps(files,sort_keys=True).encode()),
            child_report_present=(input_root/'child-result.json').exists(),original_methods_reexecuted=False,guard=guard.projection()))
        return 0
    if not (input_root/'child-result.json').exists() and (input_root/'launch-receipt.json').exists():
        receipt=strict((input_root/'launch-receipt.json').read_bytes());old_source=snapshot.read_bytes()
        need(receipt.get('mode')=='native' and receipt.get('timeout') is True and receipt.get('exit')!=0
             and receipt.get('child_exited') is True and receipt.get('drain_joined') is True and receipt.get('truncated') is False,'INCOMPLETE_CHILD_RECEIPT')
        need(sha(old_source.replace(b'\r\n',b'\n'))==receipt['harness_lf_sha256'],'INCOMPLETE_SOURCE_BINDING')
        validate_log((input_root/'output.log').read_bytes(),receipt)
        work=input_root/'work';files=manifest(work);checkpoint=strict((input_root/'postmortem-manifest.json').read_bytes())
        need(checkpoint['files']==files,'INCOMPLETE_MANIFEST_DRIFT')
        owner_count=0
        for row in files:
            if row['path'].endswith('/ledger.jsonl'):
                lines=(work/row['path']).read_bytes().splitlines();need(bool(lines),'INCOMPLETE_EMPTY_WAL')
                need(strict(lines[0])['event'].get('owner')=='rpf-63','INCOMPLETE_WAL_OWNER');owner_count+=1
        need(owner_count>0,'INCOMPLETE_NO_WAL')
        write(folder/'failure-verification.json',dict(status='PASS_INCOMPLETE_NEGATIVE_EVIDENCE_ONLY',admission_pass=False,
            child_pid=receipt['pid'],native_timeout=True,native_result='UNAVAILABLE',denial_attribution='UNAVAILABLE',
            original_methods_reexecuted=False,source_snapshot_lf_sha256=receipt['harness_lf_sha256'],
            manifest_sha256=sha(json.dumps(files,sort_keys=True).encode()),wal_files=owner_count,
            conclusion='Terminated diagnostic; persisted files/log/receipt checked only; no completed native test or denial cause inferred.',guard=guard.projection()))
        return 0
    native_dir=input_root if (input_root/'child-result.json').exists() else input_root/'native'
    raw=(native_dir/'child-result.json').read_bytes();report=strict(raw)
    receipt=strict((native_dir/'launch-receipt.json').read_bytes())
    need(sha(raw)==receipt.get('child_result_raw_sha256'),'FAILED_REPORT_BINDING')
    old_source=snapshot.read_bytes()
    expected_sources=attribution_sources({'ci/run-rpf86-owner-admission.py':old_source})
    validate_attribution(report['guard'],expected_sources,IDS)
    need(report['ids']==IDS and [r['id'] for r in report['results']]==IDS and report['tests_run']==5,'FAILED_RUN_IDS')
    need(report['status']=='FAIL' and receipt['exit']==1 and receipt['mode']=='native'
         and receipt['timeout'] is False and receipt['truncated'] is False
         and receipt['child_exited'] is True and receipt['drain_joined'] is True,'FAILED_RUN_RECEIPT')
    need(receipt['pid']==report['pid'] and sha(old_source.replace(b'\r\n',b'\n'))==receipt['harness_lf_sha256']==report['source_identity']['harness_lf_sha256'],'FAILED_RUN_SOURCE_SNAPSHOT')
    need(all(report['source_identity'][k]==source[k] for k in ('files','method_ast','assertion_counts','certificate','helper')) and report['source_unchanged'] is True,'ORIGINAL_SOURCE_DRIFT')
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
        native_attribution_sha256=report['guard']['attribution_sha256'],native_denials=report['guard']['denied'],
        admission_pass=False,conclusion='Five-method admission FAIL despite any passing methods; original sources unchanged; read-scope denials retained; independent process verified negative run.'))
    return 0

def public_projection(result):
    """Allowlisted hosted artifact; never export logs, paths, tokens or identity values."""
    native=result.get('native_receipt') or {};journal=native.get('journal') or {}
    safe_receipt={k:native[k] for k in ('pid','exit','bytes') if type(native.get(k)) is int}
    safe_receipt.update({k:native[k] for k in ('timeout','truncated','child_exited','drain_joined') if type(native.get(k)) is bool})
    for k in ('stdout_sha256','harness_lf_sha256','child_result_raw_sha256'):
        value=native.get(k)
        if isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value):safe_receipt[k]=value
    states={row['id']:row.get('actual') for row in result.get('native_results',[]) if isinstance(row,dict) and row.get('id') in IDS}
    return dict(schema='rpf86-redacted-pilot-v1',status='PASS' if result.get('status')=='PASS' else 'FAIL',
        source_level='SYNTHETIC_OFFLINE_TEST',native_receipt=safe_receipt,
        methods=[dict(id=x,actual=states.get(x) if states.get(x) in ('PASS','FAIL','ERROR','SKIP','NOT_RUN') else 'NOT_RUN') for x in IDS],
        journal_complete=journal.get('status')=='COMPLETE',journal_terminal_pass=journal.get('terminal')=={'status':'PASS','error':None},
        journal_denial_count=len(journal.get('denial_events',[])) if isinstance(journal.get('denial_events'),list) else None,
        formal_required_unavailable=539,official_coverage_changed=False,release_executed=False,deployment_authorized=False,
        actual_provider_calls=0,actual_sdk_calls=0,actual_business_writes=0)

def run(output,total_deadline=None):
    output=owned(output);output.mkdir(parents=True,exist_ok=False);started=time.monotonic();deadline=started+420
    if total_deadline is not None:
        need(math.isfinite(total_deadline),'TOTAL_DEADLINE');deadline=min(deadline,total_deadline)
    source=identity();native_receipt=launch('native',output/'native',deadline=deadline,timeout=120)
    verification=None;error=None
    try:
        report=read_child_report(output/'native',native_receipt)
        validate_native(report,native_receipt,source,output/'native/work')
        validate_physical_journal(output/'native',native_receipt,source)
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
    write(output/'result.json',result);write(output/'public-result.json',public_projection(result))
    print(json.dumps({k:result[k] for k in ('status','dedicated_owner_admission_pilot_pass','formal_required_unavailable','error')}))
    return 0 if passed else 1

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=('run','native','verify','verify-failure','controls','certificate-controls','false-green','durable-deny-crash','durable-timeout','performance','import-probe','cache-controls','crash','exit1','missing','timeout','overflow'),default='run');parser.add_argument('--input',type=Path)
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
        if args.mode=='false-green':return false_green_controls(folder)
        if args.mode in ('durable-deny-crash','durable-timeout'):return durable_control(folder,args.mode)
        if args.mode=='performance':return performance_probe(folder)
        if args.mode=='import-probe':return import_probe(folder)
        if args.mode=='cache-controls':return cache_controls(folder)
        if args.mode=='verify-failure':return verify_failure(folder,args.input,args.source_snapshot)
        if args.mode=='crash':return 7
        if args.mode=='exit1':return 1
        if args.mode=='missing':return 0
        if args.mode=='timeout':time.sleep(10);return 0
        if args.mode=='overflow':sys.stdout.write('x'*(LIMIT+1));return 0
    except (Invalid,OSError,ValueError,TypeError,KeyError) as exc:
        print('INVALID_PILOT:'+ (str(exc) if isinstance(exc,Invalid) else type(exc).__name__),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())

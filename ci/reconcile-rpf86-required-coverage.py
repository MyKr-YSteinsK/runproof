"""RPF87: read-only same-run reconciliation; no Runtime/SDK/test execution.

The original RPF85 enforce is always re-run. Five receipts are admitted atomically
into a derived ledger. A residual gap still exits 1. Local fixtures cannot be CI.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import types

ROOT=Path(__file__).resolve().parents[1]
SELF=Path(__file__).resolve()
BASE='26e9bddafd29c5fea4ea604871429b019e35d264'
PINS={'ci/run-runtime-contract-tests.py':'88396fa78d73ba091e91992d4d51263063a95aa7',
      'ci/runtime-contract-test-matrix.json':'ed827c3dc354c18c9d4b7bc63384805e50e97785',
      'ci/verify-runtime-coverage-handoff.py':'0e22b02048497b21d698dfe6cd958a437583c94d',
      'ci/run-rpf86-owner-admission.py':'482f14ebc463f623d5de62d38043f88fbce43cb0',
      'runtime/tests/test_effectwitness_pge_dual.py':'f98fb2da033dc62a0d5f785c06b837990912caf6'}
MAX_JSON=8*1024*1024
MAX_FILE=8*1024*1024
MAX_TOTAL=64*1024*1024
MAX_FILES=256
SCHEMA='rpf87-required-coverage-reconciliation-v1'

class Invalid(ValueError):pass
def need(ok,code):
    if not ok:raise Invalid(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
LOADED_SOURCE_SHA=sha(SELF.read_bytes())
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def strict(raw):
    need(type(raw) is bytes and 0<len(raw)<=MAX_JSON,'JSON_SIZE')
    def pairs(items):
        d={}
        for k,v in items:need(k not in d,'DUPLICATE_JSON');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Invalid('NONFINITE_JSON')))
def keys(value,expected,code):need(type(value) is dict and set(value)==set(expected),'SCHEMA_'+code)
def integer(value,minimum=0):return type(value) is int and value>=minimum
def git(*args):
    p=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,timeout=15)
    need(p.returncode==0,'GIT_SOURCE');return p.stdout
def nonlink(path):
    for p in (path,*path.parents):
        try:s=p.lstat()
        except FileNotFoundError:continue
        need(not (stat.S_ISLNK(s.st_mode) or getattr(s,'st_file_attributes',0)&1024),'REPARSE')
def local_owner():
    p=Path(os.environ.get('RPF87_OWNER',''))
    need(p.is_absolute() and str(p.parent)==str(ROOT/'.local/rpf-87-cross-lane')
         and re.fullmatch('[0-9a-f]{32}',p.name) is not None,'LOCAL_OWNER')
    nonlink(p);return p

class Context:
    def __init__(self,run_id,attempt,commit,*,synthetic=False,root=None):
        need(type(synthetic) is bool,'SYNTHETIC_TYPE')
        need(type(run_id) is str and re.fullmatch('[A-Za-z0-9-]+',run_id) is not None,'RUN_ID')
        need(type(attempt) is str and attempt.isascii() and attempt.isdecimal() and int(attempt)>0,'ATTEMPT')
        need(re.fullmatch('[0-9a-f]{40}',commit) is not None and git('rev-parse','HEAD').decode().strip()==commit,'COMMIT')
        self.ci=os.environ.get('GITHUB_ACTIONS')=='true';self.synthetic=synthetic
        self.run_id=run_id;self.attempt=attempt;self.commit=commit
        if self.ci:
            need(not synthetic and root is None,'SYNTHETIC_CI_FORBIDDEN')
            need(run_id.isascii() and run_id.isdecimal() and os.environ.get('GITHUB_WORKSPACE')==str(ROOT)
                 and os.environ.get('GITHUB_RUN_ID')==run_id and os.environ.get('GITHUB_RUN_ATTEMPT')==attempt
                 and os.environ.get('GITHUB_SHA')==commit,'CI_IDENTITY')
            self.root=ROOT/'ci-results'
            self.ledger=self.root/f'rpf84-{run_id}-{attempt}'/'ledger.json'
            self.handoff=self.root/f'rpf85-coverage-{run_id}-{attempt}.json'
            self.pilot=self.root/f'rpf86-{run_id}-{attempt}'
            self.output=self.root/f'rpf87-coverage-{run_id}-{attempt}.json'
        else:
            need(synthetic and root is not None,'LOCAL_SYNTHETIC_REQUIRED')
            p=Path(root);owner=local_owner()
            need(p.is_absolute() and '..' not in p.parts and str(p).startswith(str(owner)+os.sep),'LOCAL_SCOPE')
            nonlink(p);need(p.resolve().is_relative_to(owner.resolve()),'LOCAL_ESCAPE')
            self.root=p;self.ledger=p/'rpf84/ledger.json';self.handoff=p/'rpf85.json';self.pilot=p/'rpf86';self.output=p/'rpf87.json'
    def paths(self,ledger,handoff,pilot,output):
        for actual,expected in zip((ledger,handoff,pilot,output),(self.ledger,self.handoff,self.pilot,self.output)):
            p=Path(actual)
            need(p.is_absolute() and '..' not in p.parts and str(p)==str(expected),'EXACT_RUN_PATH')
            nonlink(p);need(p.resolve().is_relative_to(self.root.resolve()),'PATH_ESCAPE')

class Reader:
    def __init__(self):self.total=0;self.anchors={}
    def read(self,path,root,label,limit=MAX_FILE):
        need('..' not in path.parts and path.is_relative_to(root),'READ_SCOPE')
        nonlink(path);need(path.resolve().is_relative_to(root.resolve()),'READ_ESCAPE')
        s=path.lstat();need(stat.S_ISREG(s.st_mode) and s.st_size<=limit,'NORMAL_BOUNDED_FILE')
        with path.open('rb') as f:raw=f.read(limit+1)
        need(len(raw)<=limit,'INPUT_SIZE');self.total+=len(raw);need(self.total<=MAX_TOTAL,'TOTAL_SIZE')
        self.anchors[label]=sha(raw);return raw
    def json(self,path,root,label):return strict(self.read(path,root,label))

class SourceLoader:
    """Exact pinned CI source only; never consult a repository bytecode cache."""
    def __init__(self,path):
        need(str(path)==str(ROOT/'ci/run-runtime-contract-tests.py'),'VALIDATOR_IMPORT_SCOPE');self.path=path
    def create_module(self,spec):return None
    def exec_module(self,module):
        nonlink(self.path)
        raw=self.path.read_bytes();need(raw.replace(b'\r\n',b'\n')==git('cat-file','blob',PINS[self.path.relative_to(ROOT).as_posix()]).replace(b'\r\n',b'\n'),'VALIDATOR_IMPORT_SOURCE')
        module.__file__=str(self.path);exec(compile(raw,str(self.path),'exec'),module.__dict__)
def validator_spec(name,path):
    need(name=='rpf85_pinned_router','VALIDATOR_IMPORT_NAME')
    return importlib.util.spec_from_loader(name,SourceLoader(Path(path)),origin=str(path))

def modules():
    for name,pin in PINS.items():
        nonlink(ROOT/name)
        need(git('rev-parse','HEAD:'+name).decode().strip()==pin,'PIN_DRIFT')
        need((ROOT/name).read_bytes().replace(b'\r\n',b'\n')==git('cat-file','blob',pin).replace(b'\r\n',b'\n'),'WORKTREE_SOURCE_DRIFT')
    values=[]
    for name in ('ci/verify-runtime-coverage-handoff.py','ci/run-rpf86-owner-admission.py'):
        m=types.ModuleType('rpf87_pinned_'+str(len(values)));m.__file__=str(ROOT/name)
        exec(compile((ROOT/name).read_bytes(),str(ROOT/name),'exec'),m.__dict__);values.append(m)
    # Module-local loader binding, not a global import hook. Original enforce,
    # assess and sources bytecode remain unchanged and perform their own pins.
    values[0].importlib=types.SimpleNamespace(util=types.SimpleNamespace(spec_from_file_location=validator_spec,module_from_spec=importlib.util.module_from_spec))
    return values

def source_entry(raw,declared):
    lf=raw.replace(b'\r\n',b'\n');variants={sha(raw),sha(lf),sha(lf.replace(b'\n',b'\r\n'))}
    need(type(declared) is str and declared in variants,'SOURCE_RAW_BYTES')
    return declared

def expected_pilot_source(p,declared):
    """Git source objects only; no historical certificate or private-root reads."""
    keys(declared,('files','cache_sources','certificate','helper','attribution_sources','method_ast','assertion_counts','harness_lf_sha256'),'SOURCE')
    objects={}
    for name in p.ATTRIBUTION_FILES:
        pin=git('rev-parse',BASE+':'+name).decode().strip()
        need(git('rev-parse','HEAD:'+name).decode().strip()==pin,'PILOT_DEPENDENCY_DRIFT')
        objects[name]=git('cat-file','blob',pin)
    for field,pins in (('files',p.PINS),('cache_sources',p.CACHE_SOURCES)):
        keys(declared[field],pins,field)
        for name,pin in pins.items():
            row=declared[field][name];keys(row,('blob','raw_sha256','lf_sha256'),'SOURCE_FILE')
            need(row['blob']==pin and row['lf_sha256']==sha(objects[name].replace(b'\r\n',b'\n')),'SOURCE_LF_PIN')
            source_entry(objects[name],row['raw_sha256'])
    keys(declared['helper'],('blob','raw_sha256'),'HELPER')
    need(declared['helper']['blob']==p.HELPER_BLOB,'HELPER_PIN');source_entry(objects[p.HELPER],declared['helper']['raw_sha256'])
    need(canonical(declared['certificate'])==canonical(dict(path=p.CERT_NAME,blob=p.CERT_BLOB,raw_sha256=p.CERT_SHA,bytes=p.CERT_BYTES,
        structure='identity:dict',status='PIN_VERIFIED',secret_scan='NO_UNEXPECTED_CREDENTIAL_SHAPE')),'CERTIFICATE_METADATA')
    catalog=declared['attribution_sources'];keys(catalog,objects,'SOURCE_CATALOG')
    for name,raw in objects.items():
        row=catalog[name];keys(row,('raw_sha256','lines','functions'),'CATALOG_ROW');source_entry(raw,row['raw_sha256']);tree=ast.parse(raw)
        expected=[dict(name=n.name,start=n.lineno,end=n.end_lineno) for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        need(row['lines']==len(raw.splitlines()) and canonical(row['functions'])==canonical(expected),'SOURCE_AST_CATALOG')
    raw=objects['runtime/tests/test_effectwitness_pge_dual.py'];tree=ast.parse(raw)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DualTests')
    methods={n.name:n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
    need(len(methods)==6 and set(p.NAMES)<=set(methods),'ORIGINAL_SIX_METHODS')
    hashes={n:sha(ast.dump(methods[n],include_attributes=False).encode()) for n in p.NAMES}
    counts={n:sum(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr.startswith('assert') for x in ast.walk(methods[n])) for n in p.NAMES}
    need(declared['method_ast']==hashes and canonical(declared['assertion_counts'])==canonical(counts),'METHOD_AST_ASSERTIONS')
    need(declared['harness_lf_sha256']==sha(objects['ci/run-rpf86-owner-admission.py'].replace(b'\r\n',b'\n')),'PILOT_HARNESS_SOURCE')
    return declared

RECEIPT={'mode','pid','exit','timeout','truncated','bytes','stdout_sha256','monotonic_start_ns','monotonic_end_ns',
         'timeout_limit_seconds','child_exited','drain_joined','harness_lf_sha256','cleanup_scope'}
def process_receipt(reader,folder,root,label,mode,source):
    value=reader.json(folder/'launch-receipt.json',root,label+'_receipt')
    keys(value,RECEIPT|({'child_result_raw_sha256','journal'} if mode=='native' else set()),'PROCESS_RECEIPT')
    need(value['mode']==mode and integer(value['pid'],1) and type(value['exit']) is int and value['exit']==0,'PROCESS_ID_EXIT')
    need(value['timeout'] is False and value['truncated'] is False and value['child_exited'] is True and value['drain_joined'] is True,'PROCESS_SETTLED')
    need(integer(value['monotonic_start_ns'],1) and integer(value['monotonic_end_ns'],1) and value['monotonic_end_ns']>=value['monotonic_start_ns'],'PROCESS_CLOCK')
    limit=value['timeout_limit_seconds'];need(type(limit) in (int,float) and math.isfinite(limit) and 0<limit<=(120 if mode=='native' else 60)
         and (value['monotonic_end_ns']-value['monotonic_start_ns'])/1e9<=limit+5.1,'PROCESS_BUDGET')
    need(value['harness_lf_sha256']==source['harness_lf_sha256'] and value['cleanup_scope']=='Exact Popen handle; OS process-tree coverage UNAVAILABLE','PROCESS_SOURCE')
    raw=reader.read(folder/'output.log',root,label+'_log',2*1024*1024)
    need(integer(value['bytes']) and value['bytes']==len(raw) and sha(raw)==value['stdout_sha256'],'OUTPUT_BYTES')
    return value

def physical_manifest(reader,work,root):
    found=[];directories=0
    def walk(folder):
        nonlocal directories
        directories+=1;need(directories<=MAX_FILES,'MANIFEST_DIRECTORY_COUNT')
        for entry in sorted(os.scandir(folder),key=lambda x:x.name):
            path=Path(entry.path);s=entry.stat(follow_symlinks=False)
            need(not (stat.S_ISLNK(s.st_mode) or getattr(s,'st_file_attributes',0)&1024),'MANIFEST_REPARSE')
            if stat.S_ISDIR(s.st_mode):walk(path)
            else:
                need(len(found)<MAX_FILES,'MANIFEST_COUNT')
                raw=reader.read(path,root,'physical_'+str(len(found)));found.append(dict(path=path.relative_to(work).as_posix(),bytes=len(raw),sha256=sha(raw)))
    nonlink(work);walk(work);found.sort(key=lambda x:x['path']);need(bool(found),'EMPTY_MANIFEST')
    # Keep the complete native manifest private; only its aggregate hash is public.
    return found

def guard_shape(guard):
    keys(guard,('observed','denied','certificate','attribution_schema','attribution_events','attribution_total','attribution_truncated',
        'attribution_sources','attribution_sha256','metadata_intercepts','limitations'),'GUARD')
    need(type(guard['observed']) is dict and all(integer(x) for x in guard['observed'].values()),'GUARD_COUNTERS')
    need(set(guard['observed'])<={'read','write','stat','lstat','certificate_read_granted'}
         and guard['metadata_intercepts']==['os.stat','os.lstat','Path.resolve','os.mkdir'],'GUARD_INTERFACES')
    need(guard['denied']=={} and guard['attribution_events']==[] and type(guard['attribution_total']) is int
         and guard['attribution_total']==0 and guard['attribution_truncated'] is False,'GUARD_DENIAL_TAINT')

def wal_lineage():
    prefix='runtime/runproof_runtime/effectwitness/'
    names=[prefix+'pge_dual_'+n+'.py' for n in ('contracts','config_port','session','verify')]+['runtime/tests/test_effectwitness_pge_dual.py','spikes/rpf-63/probe.py']
    names += [prefix+n+'.py' for n in ('config_live_contracts','config_live_runtime','config_live_external','config_live_verify',
        'config_experiment_verify','config_experiment_contracts','contracts','pge_select_explorer','pge_select_contracts','pge_select_feedback')]+['spikes/rpf-53/probe.py','spikes/rpf-55/probe.py']
    hashes={}
    for name in names:
        pin=git('rev-parse',BASE+':'+name).decode().strip();need(git('rev-parse','HEAD:'+name).decode().strip()==pin,'WAL_SOURCE_DRIFT')
        hashes[name]=sha(git('cat-file','blob',pin).replace(b'\r\n',b'\n'))
    return sha(canonical(hashes))

def pilot_receipts(ctx,p,reader,router_finish):
    root=ctx.pilot
    if not ctx.synthetic:need(not os.path.lexists(root/'synthetic-control.json'),'SYNTHETIC_PILOT_FORBIDDEN')
    else:
        marker=reader.json(root/'synthetic-control.json',root,'synthetic_marker')
        need(marker=={'schema':'RPF87_SYNTHETIC_PROTOCOL_ONLY','original_tests_executed':False},'SYNTHETIC_MARKER')
    result=reader.json(root/'result.json',root,'pilot_result')
    result_keys={'schema','status','source_level','marker','ids','dedicated_owner_admission_pilot_pass','source_identity','physical_owner','logical_owner',
        'native_receipt','verification_receipt','error','seconds','native_results','formal_required_unavailable','official_coverage_changed',
        'release_eligible','release_executed','deployment_authorized','actual_provider_calls','actual_sdk_calls','actual_java_processes','actual_business_writes','syscall_proof'}
    keys(result,result_keys,'PILOT_RESULT')
    need(result['schema']=='rpf86-owner-admission-pilot-v1' and result['status']=='PASS' and result['source_level']=='SYNTHETIC_OFFLINE_TEST'
         and result['marker']=='TEST_HARNESS_OWNER_SUBSTITUTION' and result['ids']==p.IDS and result['error'] is None,'PILOT_STATUS')
    need(type(result['dedicated_owner_admission_pilot_pass']) is int and result['dedicated_owner_admission_pilot_pass']==5
         and type(result['formal_required_unavailable']) is int and result['formal_required_unavailable']==539,'PILOT_COUNTERS')
    for k in ('official_coverage_changed','release_eligible','release_executed','deployment_authorized'):need(result[k] is False,'PILOT_AUTHORITY')
    for k in ('actual_provider_calls','actual_sdk_calls','actual_java_processes','actual_business_writes'):need(type(result[k]) is int and result[k]==0,'REAL_RESOURCE')
    source=expected_pilot_source(p,result['source_identity'])
    native=process_receipt(reader,root/'native',root,'native','native',source)
    verifier=process_receipt(reader,root/'verify',root,'independent','verify',source)
    need(native==result['native_receipt'] and verifier==result['verification_receipt'] and native['pid']!=verifier['pid'],'PILOT_RECEIPT_BINDING')
    need(type(router_finish) in (int,float) and math.isfinite(router_finish) and router_finish*1e9<=native['monotonic_start_ns']
         and native['monotonic_end_ns']<=verifier['monotonic_start_ns'] and verifier['monotonic_end_ns']<=time.monotonic_ns(),'CROSS_LANE_CHRONOLOGY')
    need(type(result['seconds']) in (int,float) and math.isfinite(result['seconds']) and 0<result['seconds']<=420
         and result['seconds']>=(verifier['monotonic_end_ns']-native['monotonic_start_ns'])/1e9,'PILOT_WALL')
    raw=reader.read(root/'native/child-result.json',root,'native_report');need(sha(raw)==native['child_result_raw_sha256'],'NATIVE_REPORT_BYTES');report=strict(raw)
    keys(report,('schema','source_level','marker','ids','results','events','tests_run','source_identity','physical_owner','logical_owner','logical_identity_changed',
        'patch_points','patch_restored','guard','source_unchanged','manifest','error','pid','monotonic_start_ns','monotonic_end_ns',
        'actual_provider_calls','actual_sdk_calls','actual_java_processes','actual_business_writes','old_inode_comparison','status','cache_policy'),'NATIVE_REPORT')
    guard_shape(report['guard']);p.validate_native(report,native,source,root/'native/work')
    need(type(report['cache_policy']['dont_write_bytecode']) is bool and report['cache_policy']['dont_write_bytecode'] is True
         and type(report['cache_policy']['global_loader_patch']) is bool and report['cache_policy']['global_loader_patch'] is False,'CACHE_POLICY_TYPES')
    cache=root/'native/pycache';nonlink(cache);need(cache.is_dir() and not list(os.scandir(cache)),'CACHE_NOT_FRESH_EMPTY')
    for k in ('actual_provider_calls','actual_sdk_calls','actual_java_processes','actual_business_writes'):
        need(type(report[k]) is int and report[k]==0,'NATIVE_RESOURCE_TYPE')
    need(result['native_results']==report['results'] and result['physical_owner']==report['physical_owner'] and result['logical_owner']=='rpf-63','RESULT_NATIVE_LINK')
    need(integer(report['monotonic_start_ns'],1) and integer(report['monotonic_end_ns'],1)
         and native['monotonic_start_ns']<=report['monotonic_start_ns']<=report['monotonic_end_ns']<=native['monotonic_end_ns'],'NATIVE_CLOCK')
    reader.read(root/'native/denial-journal.jsonl',root,'native_journal',p.JOURNAL_MAX_FRAMES*p.JOURNAL_MAX_FRAME_BYTES)
    journal=p.validate_physical_journal(root/'native',native,source)
    files=physical_manifest(reader,root/'native/work',root);need(canonical(files)==canonical(report['manifest']),'PHYSICAL_MANIFEST')
    wal=0;lineage=wal_lineage()
    for row in files:
        if row['path'].endswith('/ledger.jsonl'):
            data=reader.read(root/'native/work'/row['path'],root,'wal_header_'+str(wal))
            first=strict(data.splitlines()[0]);keys(first,('seq','previous','event','sha256'),'WAL_OWNER_FRAME')
            e=first['event'];keys(e,('kind','monotonic_ns','owner','base','source_sha256'),'WAL_OWNER_EVENT')
            need(type(first['seq']) is int and first['seq']==0 and first['previous'] is None
                 and first['sha256']==sha(canonical({k:v for k,v in first.items() if k!='sha256'})),'WAL_OWNER_HASH')
            need(e['kind']=='OWNER' and e['owner']=='rpf-63' and integer(e['monotonic_ns'],1)
                 and e['base']=='68572c05a52ff2258f50fb7c4488bff8e69ea61c' and e['source_sha256']==lineage,'LOGICAL_WAL_SOURCE');wal+=1
    need(wal>0,'NO_PHYSICAL_WAL')
    verification=reader.json(root/'verify/verification.json',root,'independent_report')
    keys(verification,('status','native_ids','manifest_sha256','wal_files','logical_owner','source_identity','guard','journal','source_level','independent_process','independent_issuer'),'INDEPENDENT_REPORT')
    guard_shape(verification['guard'])
    p.validate_attribution(verification['guard'],source['attribution_sources'],p.IDS)
    need(canonical(verification['guard']['certificate'])==canonical(source['certificate']),'INDEPENDENT_CERTIFICATE_METADATA')
    need(verification['status']=='PASS' and verification['native_ids']==p.IDS and verification['source_identity']==source
         and verification['journal']==journal and verification['logical_owner']=='rpf-63' and type(verification['wal_files']) is int
         and verification['wal_files']==wal and verification['manifest_sha256']==sha(json.dumps(files,sort_keys=True).encode())
         and verification['source_level']=='SYNTHETIC_OFFLINE_TEST' and verification['independent_process'] is True
         and verification['independent_issuer'] is False,'INDEPENDENT_BINDING')
    public=reader.json(root/'public-result.json',root,'public_pilot')
    need(canonical(public)==canonical(p.public_projection(result)),'PUBLIC_PROJECTION')
    reader.anchors['physical_manifest']=sha(canonical(files))
    return dict(native_receipt_sha256=reader.anchors['native_receipt'],journal_sha256=reader.anchors['native_journal'],
        independent_receipt_sha256=reader.anchors['independent_receipt'],manifest_sha256=reader.anchors['physical_manifest'],wal_files=wal)

def reconcile(ctx,ledger,handoff,pilot,output):
    ctx.paths(ledger,handoff,pilot,output);nonlink(SELF)
    need(sha(SELF.read_bytes())==LOADED_SOURCE_SHA,'RECONCILER_SOURCE_DRIFT')
    workflow=ROOT/'.github/workflows/release-gate.yml';nonlink(workflow);workflow_raw=workflow.read_bytes()
    if ctx.ci:
        need(git('cat-file','blob',ctx.commit+':'+SELF.relative_to(ROOT).as_posix()).replace(b'\r\n',b'\n')==SELF.read_bytes().replace(b'\r\n',b'\n'),'RECONCILER_COMMIT_SOURCE')
        need(git('cat-file','blob',ctx.commit+':.github/workflows/release-gate.yml').replace(b'\r\n',b'\n')==workflow_raw.replace(b'\r\n',b'\n')
             and b'Reconcile admitted RPF-86 required methods' in workflow_raw and b'ci/reconcile-rpf86-required-coverage.py enforce' in workflow_raw,'WORKFLOW_SOURCE')
    h,p=modules();reader=Reader()
    # Only the local synthetic fixture owner is relocated. No hosted override.
    if ctx.synthetic:h.OWNER=local_owner()
    try:
        old_exit,status=h.enforce(ctx.handoff,ctx.ledger,ctx.run_id,ctx.attempt,ctx.commit,synthetic=ctx.synthetic)
        need(old_exit==1 and status['counts']=={'PASS':688,'SKIP':5,'UNAVAILABLE':539}
             and status['routes']['DEDICATED_RUNNER']=={'UNAVAILABLE':417}
             and status['diagnostic_continuation']=='CONTINUE_DIAGNOSTIC_ONLY','ORIGINAL_COVERAGE')
        need(status['evidence_kind']==('SYNTHETIC_OFFLINE_TEST' if ctx.synthetic else 'ROUTER_PROCESS_RECEIPTS'),'ROUTER_EVIDENCE_KIND')
    except Exception as exc:raise Invalid('INVALID_ORIGINAL_HANDOFF') from None
    original=reader.json(ctx.ledger,ctx.ledger.parent,'router_ledger');reader.read(ctx.handoff,ctx.handoff.parent,'handoff_status')
    rows=[r for m in original['modules'] for r in m['rows']]
    mapping={full:full.removeprefix('runtime.tests.') for full in p.IDS}
    need(len(mapping)==5 and all(x.startswith('test_effectwitness_pge_dual.DualTests.') for x in mapping.values()),'EXACT_FIVE_MAPPING')
    selected={r['id']:r for r in rows if r['id'] in mapping.values()}
    need(set(selected)==set(mapping.values()) and all(r['route']=='DEDICATED_RUNNER' and r['actual']=='UNAVAILABLE'
         and r['executed'] is False and r['required'] is True for r in selected.values()),'ORIGINAL_FIVE_DISPOSITION')
    admitted=[];reason=None;proof=None
    try:
        proof=pilot_receipts(ctx,p,reader,original['lane_finished_monotonic'])
        admitted=[dict(full_id=full,router_id=short,actual='PASS',source_lane='RPF86_DEDICATED',**proof) for full,short in mapping.items()]
    except Exception as exc:
        code=str(exc) if isinstance(exc,(Invalid,p.Invalid)) else type(exc).__name__
        reason=code if re.fullmatch('[A-Z][A-Z0-9_]{0,79}',code) else 'INVALID_PILOT_EVIDENCE'
    accepted={a['router_id'] for a in admitted};effective=[]
    for r in rows:effective.append(dict(id=r['id'],route=r['route'],required=True,original_actual=r['actual'],
        effective_actual='PASS' if r['id'] in accepted else r['actual'],source_lane='RPF86_DEDICATED' if r['id'] in accepted else 'ORIGINAL_ROUTER'))
    counts=dict(Counter(r['effective_actual'] for r in effective));remaining=counts['UNAVAILABLE']
    need(len(effective)==len({r['id'] for r in effective})==1232 and len(admitted) in (0,5),'ATOMIC_UNIQUE_COVERAGE')
    need(counts==({'PASS':693,'SKIP':5,'UNAVAILABLE':534} if admitted else {'PASS':688,'SKIP':5,'UNAVAILABLE':539}),'EFFECTIVE_COUNTS')
    return dict(schema=SCHEMA,run_id=ctx.run_id,attempt=ctx.attempt,commit=ctx.commit,
        evidence_kind='LOCAL_SYNTHETIC_CONTROL_ONLY' if ctx.synthetic else 'HOSTED_SAME_RUN_PROCESS_RECEIPTS',
        source_level='SYNTHETIC_OFFLINE_TEST',no_real_provider_claim=True,
        original_router=dict(counts=status['counts'],unavailable=539,dedicated_unavailable=417,enforce_exit=old_exit,
            ledger_sha256=reader.anchors['router_ledger'],status_sha256=reader.anchors['handoff_status'],evidence_manifest_sha256=status['evidence_manifest_sha256']),
        admitted_dedicated=admitted,not_admitted=reason,effective_required=dict(methods=effective,counts=counts,required=1232),
        unavailable_remaining=remaining,dedicated_unavailable_remaining=417-len(admitted),
        evidence_anchors=reader.anchors,source_identity=dict(pinned_blobs=PINS,reconciler_lf_sha256=sha(SELF.read_bytes().replace(b'\r\n',b'\n')),workflow_lf_sha256=sha(workflow_raw.replace(b'\r\n',b'\n'))),
        release_eligible=False,release_executed=False,deployment_authorized=False,
        bounded_summary='Derived test ownership only; original Router/Handoff/Pilot unchanged. NO_RELEASE/NO_DEPLOY.')

def write_result(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def summary(value):
    if os.environ.get('GITHUB_ACTIONS')!='true':return
    p=Path(os.environ.get('GITHUB_STEP_SUMMARY',''));temp=Path(os.environ.get('RUNNER_TEMP',''))
    need(p.is_absolute() and temp.is_absolute() and p.is_relative_to(temp) and '..' not in p.parts
         and p.name.startswith('step_summary_'),'SUMMARY_SCOPE');nonlink(p)
    with p.open('a',encoding='utf8') as f:f.write('\n### RPF-87 derived required coverage\n\nOriginal unavailable=539; admitted dedicated='+str(len(value['admitted_dedicated']))+'; remaining='+str(value['unavailable_remaining'])+'. NO_RELEASE/NO_DEPLOY.\n')
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('assess','enforce'))
    for name in ('ledger','handoff','pilot','output'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('run-id','attempt','commit'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--synthetic',action='store_true');parser.add_argument('--fixture-root',type=Path)
    a=parser.parse_args(argv)
    try:
        ctx=Context(a.run_id,a.attempt,a.commit,synthetic=a.synthetic,root=a.fixture_root)
        ctx.paths(a.ledger,a.handoff,a.pilot,a.output)
        if a.command=='assess':need(not os.path.lexists(a.output),'OUTPUT_OCCUPIED')
        value=reconcile(ctx,a.ledger,a.handoff,a.pilot,a.output)
        if a.command=='assess':write_result(a.output,value);summary(value);print('RPF87_ASSESSED; admitted_dedicated='+str(len(value['admitted_dedicated']))+'; unavailable_required='+str(value['unavailable_remaining']));return 0
        saved=strict(Reader().read(a.output,a.output.parent,'derived_status'))
        need(canonical(saved)==canonical(value),'DERIVED_STATUS_REVALIDATION')
        print('RELEASE_BLOCKED_BY_REQUIRED_COVERAGE; unavailable_required='+str(value['unavailable_remaining'])+'; admitted_dedicated='+str(len(value['admitted_dedicated']))+'; NO_RELEASE/NO_DEPLOY')
        return 1
    except Exception as exc:
        code=str(exc) if isinstance(exc,Invalid) else type(exc).__name__
        safe=code if re.fullmatch('[A-Z][A-Z0-9_]{0,79}',code) else 'INVALID_GATE_INPUT'
        print('INVALID_GATE_INPUT:'+safe+'; unavailable_required=539; NO_RELEASE/NO_DEPLOY',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())

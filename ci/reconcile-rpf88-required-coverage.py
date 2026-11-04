"""RPF89 rev-2: same-job RPF87 post-completion checkpoint and read-only
R72 coverage admission. Original legacy enforce is re-executed; residual required
coverage always blocks release. Local synthetic controls never claim hosted proof.
The diagnose command only describes the original RPF87 native-finish schema.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import redirect_stdout, closing
import io
import stat
import sqlite3
import time
import types
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
BASE='7e12a7b6b2315977b975ec42672cbf101c37bf19'
PINS={
 'ci/reconcile-rpf86-required-coverage.py':'1d8d502e0a8db08e56763272565386dc246469b0',
 'ci/run-rpf88-r72-owner-scope.py':'6ca463addf0b861dfe1be854ea305d5f5b369c9c',
 'ci/verify-runtime-coverage-handoff.py':'0e22b02048497b21d698dfe6cd958a437583c94d',
 'ci/run-runtime-contract-tests.py':'88396fa78d73ba091e91992d4d51263063a95aa7',
 'ci/runtime-contract-test-matrix.json':'ed827c3dc354c18c9d4b7bc63384805e50e97785',
 '.github/workflows/release-gate.yml':'0cfc1a8ec53899eb6e9fe6aee46396ffa8af506b'}
class Invalid(ValueError):pass
def need(ok,code):
    if not ok:raise Invalid(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def strict(b):
    need(type(b) is bytes and 0<len(b)<=8*1024*1024,'JSON_SIZE')
    def pairs(xs):
        d={}
        for k,v in xs:need(k not in d,'JSON_DUPLICATE');d[k]=v
        return d
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Invalid('JSON_NONFINITE')))
def git(*args):
    p=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,timeout=15)
    need(p.returncode==0,'GIT_SOURCE');return p.stdout
def pinned(path,pin):
    raw=(ROOT/path).read_bytes();old=git('cat-file','blob',pin)
    if path=='.github/workflows/release-gate.yml':return workflow_source(raw,old)
    need(git('rev-parse','HEAD:'+path).decode().strip()==pin and raw.replace(b'\r\n',b'\n')==old.replace(b'\r\n',b'\n'),'PIN_DRIFT')
    return raw
def return_fields(raw,function):
    tree=ast.parse(raw);fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==function)
    last=next(x for x in reversed(fn.body) if isinstance(x,ast.Return))
    need(isinstance(last.value,ast.Call) and isinstance(last.value.func,ast.Name) and last.value.func.id=='dict','RETURN_SHAPE')
    return [k.arg for k in last.value.keywords]
def completion_evidence(raw):
    """Static schema observation, never pretends to observe a historical run."""
    keys=return_fields(raw,'reconcile');proof=return_fields(raw,'pilot_receipts')
    need(set(proof)=={'native_receipt_sha256','journal_sha256','independent_receipt_sha256','manifest_sha256','wal_files'},'PROOF_SCHEMA_DRIFT')
    own_clock=any(k and re.search('monotonic|completed|finished|receipt',k) for k in keys)
    return dict(return_fields=keys,pilot_proof_fields=proof,own_completion_clock_declared=own_clock,
        observation='PINNED_SOURCE_SCHEMA_ONLY',actual_run_evidence_read=False,
        timestamp_inference_from_step_order=False)
def model_observations(r87_completion,r88_start):
    """Two synthetic schedules, same serialized schema: no timing claim."""
    need(type(r87_completion) is int and type(r88_start) is int,'MODEL_TIME_TYPE')
    return dict(r87_result_schema='rpf87-required-coverage-reconciliation-v1',r88_native_start=r88_start)
def audit():
    src={p:pinned(p,h) for p,h in PINS.items()};clock=completion_evidence(src['ci/reconcile-rpf86-required-coverage.py'])
    need(not clock['own_completion_clock_declared'],'SCHEMA_CHANGED_REQUIRES_REVIEW')
    tree=ast.parse(src['ci/run-rpf88-r72-owner-scope.py']);names=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NAMES' for t in n.targets)))
    excluded=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='EXCLUDED' for t in n.targets)))
    pins=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PINS' for t in n.targets)))
    target='runtime/tests/test_effectwitness_pge_r72.py';raw=pinned(target,pins[target]['blob']);cl=next(n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='BudgetTests')
    methods={n.name:sha(ast.dump(n,include_attributes=False).encode()) for n in cl.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
    need(len(methods)==25 and len(names)==18 and len(excluded)==7 and set(names).isdisjoint(excluded) and set(names)|set(excluded)==set(methods),'INVENTORY')
    row=next(x for x in strict(src['ci/runtime-contract-test-matrix.json'])['modules'] if x['path']==target)
    routes={x['selector']:x['route'] for x in row['rules']}
    need(all(routes['BudgetTests.'+n]=='DEDICATED_RUNNER' for n in names),'ROUTE')
    workflow=src['.github/workflows/release-gate.yml'].decode()
    need(workflow.index('Reconcile admitted RPF-86 required methods')<workflow.index('Run RPF-88 R72 fresh-owner cohort pilot'),'WORKFLOW_SEQUENCE')
    return dict(status='UNAVAILABLE',decision='HISTORICAL_SCHEMA_OBSERVATION_ONLY',reason='RPF87_NATIVE_FINISH_FIELD_ABSENT_POSTCHECK_IS_SEPARATE',
        source={p:dict(blob=git('rev-parse','HEAD:'+p).decode().strip(),raw_sha256=sha(b),lf_sha256=sha(b.replace(b'\r\n',b'\n'))) for p,b in src.items()},
        clock=clock,workflow_step_order='SOURCE_FACT; NOT_USED_AS_NATIVE_COMPLETION_RECEIPT',
        selected=['runtime.tests.test_effectwitness_pge_r72.BudgetTests.'+n for n in names],excluded=list(excluded),method_ast=methods,
        native_RPF88_revalidation='NOT_RUN',RPF87_recomputation='NOT_RUN',new_admissions=0,
        baseline_counts_reverified=False,release_eligible=False,release_executed=False,deployment_authorized=False)
def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['diagnose','assess','enforce'])
    # These parameters are parsed for fail-closed compatibility, NEVER opened.
    for k in ('rpf87','rpf88','output','run-id','attempt','commit','fixture-root'):ap.add_argument('--'+k)
    ap.add_argument('--synthetic',action='store_true');a=ap.parse_args(argv)
    if a.command!='diagnose':
        print('UNAVAILABLE:RPF87_COMPLETION_OBSERVATION_UNAVAILABLE; B_UNACTIVATED; NO_RELEASE/NO_DEPLOY',file=sys.stderr);return 2
    try:print(json.dumps(audit(),sort_keys=True));return 2
    except (Invalid,KeyError,ValueError,OSError,StopIteration):
        print('INVALID_GATE_INPUT:SOURCE_AUDIT; NO_RELEASE/NO_DEPLOY',file=sys.stderr);return 2
diagnose_main=main

# rev-2: the original diagnostic remains an observation of the old schema.
SELF=Path(__file__).resolve()
LOADED_SHA=sha(SELF.read_bytes())
R87='ci/reconcile-rpf86-required-coverage.py'
R88='ci/run-rpf88-r72-owner-scope.py'
SCOPE='POST_COMPLETION_OBSERVATION_NOT_RPF87_NATIVE_FINISH'
STAMP_SCHEMA='rpf89-rpf87-post-completion-v1'
STAMP_KEYS=set(('schema run_id run_attempt commit github_job rpf87_result_sha256 rpf87_source_blob '
 'rpf89_stamp_source_lf_sha256 legacy_enforce_exit legacy_enforce_stdout_sha256 legacy_verified '
 'postcheck_monotonic_ns postcheck_pid scope synthetic rpf87_step_outcome').split())
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def fields(v,keys):need(type(v) is dict and set(v)==set(keys),'SCHEMA_FIELDS')
def intpos(x):return type(x) is int and x>0
def nonlink(p):
    for q in (p,*p.parents):
        try:s=q.lstat()
        except FileNotFoundError:continue
        need(not stat.S_ISLNK(s.st_mode) and not getattr(s,'st_file_attributes',0)&1024,'REPARSE')
def write_exclusive(p,v):
    b=canonical(v)+b'\n';need(len(b)<=8*1024*1024,'JSON_SIZE');nonlink(p)
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def workflow_source(raw,base):
    """Current authorized delta and HEAD identity; Base remains a reference."""
    need(raw.replace(b'\r\n',b'\n')==git('cat-file','blob','HEAD:.github/workflows/release-gate.yml').replace(b'\r\n',b'\n') or os.environ.get('GITHUB_ACTIONS')!='true','WORKFLOW_HEAD')
    s=raw.decode().replace('\r\n','\n');old=base.decode().replace('\r\n','\n')
    if s==old:return raw  # pre-activation / B path
    for name in ('Record verified RPF-87 post-completion boundary','Reconcile admitted RPF-88 R72 required methods','Enforce RPF-89 derived required coverage','Upload RPF-89 derived required coverage'):
        pattern=r'      - name: '+re.escape(name)+r'\n.*?(?=      - name: |\Z)'
        s,count=re.subn(pattern,'',s,flags=re.S);need(count==1,'WORKFLOW_DELTA_STEP')
    s=s.replace('        id: rpf87_assess\n','')
    s=s.replace('            ci-results/rpf89-coverage-${{ github.run_id }}-${{ github.run_attempt }}.json\n','')
    need(s==old,'WORKFLOW_UNAUTHORIZED_DELTA');return raw
def load_pinned(path):
    raw=pinned(path,PINS[path]);m=types.ModuleType('r89_'+Path(path).stem.replace('-','_'));m.__file__=str(ROOT/path)
    exec(compile(raw,str(ROOT/path),'exec'),m.__dict__);return m
def local_owner():
    p=Path(os.environ.get('RPF89_OWNER',''))
    need(p.is_absolute() and p.parent==ROOT/'.local/rpf-89-rev2' and re.fullmatch('[a-f0-9]{32}',p.name),'LOCAL_OWNER')
    nonlink(p);return p
class Context:
    def __init__(self,run,attempt,commit,synthetic=False,root=None):
        need(type(synthetic) is bool,'SYNTHETIC_TYPE')
        need(type(run) is str and re.fullmatch('[A-Za-z0-9-]+',run) and type(attempt) is str and re.fullmatch('[0-9]+',attempt) and int(attempt)>0,'RUN_FORMAT')
        need(type(commit) is str and re.fullmatch('[a-f0-9]{40}',commit),'COMMIT_FORMAT')
        need(git('rev-parse','HEAD').decode().strip()==commit,'COMMIT_DRIFT')
        self.run=run;self.attempt=attempt;self.commit=commit;self.synthetic=synthetic;self.started=time.monotonic_ns()
        if os.environ.get('GITHUB_ACTIONS')=='true':
            need(not synthetic and root is None,'SYNTHETIC_HOSTED_FORBIDDEN')
            need(run.isdecimal() and os.environ.get('GITHUB_WORKSPACE')==str(ROOT) and os.environ.get('GITHUB_RUN_ID')==run and os.environ.get('GITHUB_RUN_ATTEMPT')==attempt and os.environ.get('GITHUB_SHA')==commit and os.environ.get('GITHUB_JOB')=='canonical-release-gate' and os.environ.get('GITHUB_REPOSITORY')=='MyKr-YSteinsK/runproof' and os.environ.get('GITHUB_SERVER_URL')=='https://github.com' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted','CI_IDENTITY')
            wf=pinned('.github/workflows/release-gate.yml',PINS['.github/workflows/release-gate.yml'])
            need(all(x in wf for x in (b'id: rpf87_assess',b'RPF87_STEP_OUTCOME: ${{ steps.rpf87_assess.outcome }}',b'Record verified RPF-87 post-completion boundary',b'Enforce RPF-89 derived required coverage')),'WORKFLOW_NOT_ACTIVATED')
            self.job=os.environ['GITHUB_JOB'];self.root=ROOT/'ci-results'
            self.r87=self.root/f'rpf87-coverage-{run}-{attempt}.json';self.r88=self.root/f'rpf88-{run}-{attempt}'
            self.stamp=self.root/f'rpf89-rpf87-completion-{run}-{attempt}.json';self.output=self.root/f'rpf89-coverage-{run}-{attempt}.json'
            self.ledger=self.root/f'rpf84-{run}-{attempt}'/'ledger.json';self.handoff=self.root/f'rpf85-coverage-{run}-{attempt}.json';self.pilot86=self.root/f'rpf86-{run}-{attempt}'
        else:
            need(synthetic and root is not None,'LOCAL_SYNTHETIC_REQUIRED');owner=local_owner();self.root=Path(root)
            need(self.root.is_absolute() and '..' not in self.root.parts and self.root!=owner and self.root.is_relative_to(owner),'LOCAL_SCOPE');nonlink(self.root)
            self.job='LOCAL_SYNTHETIC_JOB';self.r87=self.root/'r87.json';self.r88=self.root/'r88';self.stamp=self.root/'checkpoint.json';self.output=self.root/'derived.json';self.ledger=self.root/'router.json';self.handoff=self.root/'handoff.json';self.pilot86=self.root/'r86'
        for p in (self.root,self.r87,self.r88,self.stamp,self.output,self.ledger,self.handoff,self.pilot86):nonlink(p)
    def check_args(self,args):
        for key,p in [('rpf87',self.r87),('rpf88',self.r88),('checkpoint',self.stamp),('output',self.output),('ledger',self.ledger),('handoff',self.handoff),('pilot86',self.pilot86)]:
            actual=getattr(args,key,None)
            if actual is not None:need(str(actual)==str(p) and '..' not in Path(actual).parts,'EXACT_PATH')
class Reader:
    def __init__(self):self.total=0;self.anchors={}
    def read(self,p,root,label,limit=8*1024*1024):
        need(p.is_absolute() and '..' not in p.parts and p.is_relative_to(root),'READ_SCOPE');nonlink(p);need(p.resolve().is_relative_to(root.resolve()),'READ_ESCAPE')
        before=p.stat();need(stat.S_ISREG(before.st_mode) and before.st_size<=limit,'READ_SIZE');need(before.st_nlink==1,'READ_HARDLINK')
        with p.open('rb') as f:b=f.read(limit+1)
        after=p.stat();need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) and len(b)<=limit,'READ_CHANGED')
        self.total+=len(b);need(self.total<=64*1024*1024,'TOTAL_SIZE');self.anchors[label]=sha(b);return b
    def json(self,p,root,label):return strict(self.read(p,root,label))
def validate_baseline(v,c):
    need(v['schema']=='rpf87-required-coverage-reconciliation-v1' and v['run_id']==c.run and v['attempt']==c.attempt and v['commit']==c.commit,'BASELINE_IDENTITY')
    need(v['evidence_kind']==('LOCAL_SYNTHETIC_CONTROL_ONLY' if c.synthetic else 'HOSTED_SAME_RUN_PROCESS_RECEIPTS'),'BASELINE_KIND')
    ms=v['effective_required']['methods'];need(len(ms)==len({x['id'] for x in ms})==1232,'BASELINE_IDS')
    need(dict(Counter(x['effective_actual'] for x in ms))==v['effective_required']['counts']=={'PASS':693,'SKIP':5,'UNAVAILABLE':534} and v['effective_required']['required']==1232,'BASELINE_COUNTS')
    need(v['original_router']['counts']=={'PASS':688,'SKIP':5,'UNAVAILABLE':539} and v['original_router']['enforce_exit']==1,'ROUTER_COUNTS')
    expected={'test_effectwitness_pge_dual.DualTests.'+n for n in ('test_four_paths','test_twenty_one_reanchored_attacks','test_unknown_usage_and_restart','test_scope_lock_budget_and_invalid_selection','test_unknown_mutation_stops_writes_but_allows_readback')}
    need(len(v['admitted_dedicated'])==5 and {x['router_id'] for x in v['admitted_dedicated']}==expected and {x['id'] for x in ms if x['source_lane']=='RPF86_DEDICATED'}==expected,'BASELINE_FIVE')
    need(all(x['required'] is True and x['effective_actual'] in ('PASS','SKIP','UNAVAILABLE') for x in ms),'BASELINE_ROWS')
    need(sum(x['route']=='DEDICATED_RUNNER' and x['effective_actual']=='UNAVAILABLE' for x in ms)==412,'BASELINE_DEDICATED')
    for k in ('release_eligible','release_executed','deployment_authorized'):need(v[k] is False,'BASELINE_AUTHORITY')
def legacy_revalidate(c,reader):
    if c.synthetic:
        # Local model deliberately does NOT claim original upstream execution.
        v=reader.json(c.r87,c.root,'r87');validate_baseline(v,c)
        reader.legacy_stdout_sha256=sha(b'LOCAL_SYNTHETIC_UPSTREAM_MODEL_NOT_EXECUTED')
        return v,dict(exit=1,stdout_sha256=reader.legacy_stdout_sha256)
    m=load_pinned(R87);buf=io.StringIO()
    OriginalReader=m.Reader
    class BudgetedLegacyReader(OriginalReader):
        def read(self,*args,**kwargs):
            b=super().read(*args,**kwargs);reader.total+=len(b);need(reader.total<=64*1024*1024,'TOTAL_SIZE');return b
    m.Reader=BudgetedLegacyReader
    args=['enforce','--ledger',str(c.ledger),'--handoff',str(c.handoff),'--pilot',str(c.pilot86),'--output',str(c.r87),'--run-id',c.run,'--attempt',c.attempt,'--commit',c.commit]
    with redirect_stdout(buf):rc=m.main(args)
    raw=buf.getvalue().encode();need(len(raw)<=2*1024*1024 and type(rc) is int and rc==1,'LEGACY_ENFORCE_EXIT')
    need(b'unavailable_required=534; admitted_dedicated=5; NO_RELEASE/NO_DEPLOY' in raw,'LEGACY_ENFORCE_REASON')
    v=reader.json(c.r87,c.root,'r87');validate_baseline(v,c);reader.legacy_stdout_sha256=sha(raw);return v,dict(exit=rc,stdout_sha256=reader.legacy_stdout_sha256)
def checkpoint_value(c,reader,legacy,outcome):
    need(outcome=='success' and type(legacy['exit']) is int and legacy['exit']==1,'STEP_OR_LEGACY_FAILURE')
    return dict(schema=STAMP_SCHEMA,run_id=c.run,run_attempt=c.attempt,commit=c.commit,github_job=c.job,
        rpf87_result_sha256=reader.anchors['r87'],rpf87_source_blob=PINS[R87],rpf89_stamp_source_lf_sha256=sha(SELF.read_bytes().replace(b'\r\n',b'\n')),
        legacy_enforce_exit=1,legacy_enforce_stdout_sha256=legacy['stdout_sha256'],legacy_verified=not c.synthetic,
        postcheck_monotonic_ns=time.monotonic_ns(),postcheck_pid=os.getpid(),scope=SCOPE,synthetic=c.synthetic,rpf87_step_outcome=outcome)
def stamp(c,outcome):
    need(outcome=='success','STEP_OUTCOME');need(not os.path.lexists(c.stamp),'STAMP_OCCUPIED')
    reader=Reader();_,legacy=legacy_revalidate(c,reader);v=checkpoint_value(c,reader,legacy,outcome);write_exclusive(c.stamp,v);return v
def check_stamp(s,c,reader,nr,vr):
    fields(s,STAMP_KEYS)
    need(s['schema']==STAMP_SCHEMA and s['run_id']==c.run and s['run_attempt']==c.attempt and s['commit']==c.commit and s['github_job']==c.job,'STAMP_IDENTITY')
    need(s['rpf87_result_sha256']==reader.anchors['r87'] and s['rpf87_source_blob']==PINS[R87] and s['rpf89_stamp_source_lf_sha256']==sha(SELF.read_bytes().replace(b'\r\n',b'\n')),'STAMP_SOURCE_HASH')
    need(type(s['legacy_enforce_exit']) is int and s['legacy_enforce_exit']==1 and s['legacy_verified'] is (not c.synthetic) and s['rpf87_step_outcome']=='success' and re.fullmatch('[a-f0-9]{64}',s['legacy_enforce_stdout_sha256']),'STAMP_LEGACY')
    need(s['legacy_enforce_stdout_sha256']==getattr(reader,'legacy_stdout_sha256',None),'STAMP_LEGACY_STDOUT_HASH')
    need(s['scope']==SCOPE and s['synthetic'] is c.synthetic,'STAMP_SCOPE')
    need(intpos(s['postcheck_pid']) and s['postcheck_pid'] not in (nr['pid'],vr['pid']) and intpos(s['postcheck_monotonic_ns']) and s['postcheck_monotonic_ns']<nr['start_ns'],'STAMP_CHRONOLOGY')
def manifest_read(reader,work,rows,root):
    need(type(rows) is list and 0<len(rows)<=256,'MANIFEST_BOUND');actual=[];seen=set();parents={work}
    for row in rows:
        fields(row,('path','bytes','sha256'));name=row['path'];p=Path(name)
        need(type(name) is str and p.as_posix()==name and not p.is_absolute() and '..' not in p.parts and name not in seen,'MANIFEST_PATH');seen.add(name)
        need(type(row['bytes']) is int and 0<=row['bytes']<=8*1024*1024 and re.fullmatch('[a-f0-9]{64}',row['sha256']),'MANIFEST_ROW')
        target=work/p;parents.update(x for x in target.parents if x.is_relative_to(work))
        raw=reader.read(target,root,'work_'+str(len(actual)));need(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'MANIFEST_BYTES');actual.append(row)
        if p.name=='wal.jsonl':
            previous=None;clock=-1;unknown=False
            for i,line in enumerate(raw.splitlines()):
                f=strict(line);fields(f,('seq','previous','event','sha256'));need(type(f['seq']) is int and f['seq']==i and f['previous']==previous and f['sha256']==sha(canonical({k:v for k,v in f.items() if k!='sha256'})),'WAL_CHAIN')
                e=f['event'];need(e['session_id']==p.parts[1] and type(e['clock']) is int and e['clock']>=clock,'WAL_OWNER_TIME')
                if i==0:need(e['kind']=='OWNER' and re.fullmatch('[a-f0-9]{64}',e['context_sha256']),'WAL_OWNER')
                if e['kind']=='RESERVE':
                    need(e['resource'] not in ('provider','sdk','jvm','host','config_post'),'WAL_REAL_RESOURCE')
                    need(not unknown or e['resource']=='authority_read' or e['resource']=='config_http' and e.get('method')=='GET','WAL_UNKNOWN_NEW_WRITE')
                if e['kind']=='RESULT' and e.get('status')=='UNKNOWN':unknown=True
                previous=sha(canonical(f));clock=e['clock']
            need(raw.endswith(b'\n') and previous is not None,'WAL_TORN')
    # Enumerate only approved manifest parent directories. Unknown names are
    # refused before stat/open, never followed or read as extra evidence.
    need(len(parents)<=256,'MANIFEST_DIR_BOUND')
    for folder in parents:
        nonlink(folder)
        for name in os.listdir(folder):
            q=folder/name;need(q in parents or q.relative_to(work).as_posix() in seen,'MANIFEST_EXTRA_ENTRY')
    need(actual==sorted(actual,key=lambda x:x['path']),'MANIFEST_ORDER');return actual
def readonly_connect(allowed,database,**kw):
    need(kw=={'uri':True} and type(kw['uri']) is bool and type(database) is str and database in {p.as_uri()+'?mode=ro' for p in allowed},'SQLITE_READONLY_ONLY')
    return sqlite3.connect(database,uri=True)
def pilot_revalidate(c,reader,base,s):
    root=c.r88;m=load_pinned(R88);source=m.identity()
    for path,pin in m.PINS.items():pinned(path,pin['blob'])
    result=reader.json(root/'result.json',root,'pilot_result');public=reader.json(root/'public-result.json',root,'pilot_public')
    fields(result,('schema status error source native_receipt verify_receipt states source_unchanged guard_denied_count native_report_sha256 verification_sha256 resources').split())
    need(result['schema']=='rpf88-result-v1' and result['status']=='PASS' and result['error'] is None and result['source']==source and result['states']==dict.fromkeys(m.IDS,'PASS') and result['source_unchanged'] is True and type(result['guard_denied_count']) is int and result['guard_denied_count']==0 and result['resources']==m.RESOURCES and all(type(x) is int for x in result['resources'].values()),'PILOT_RESULT')
    reports={};receipts={}
    for mode,filename in [('native','child-result.json'),('verify','verification.json')]:
        receipt=reader.json(root/mode/'launch-receipt.json',root,mode+'_receipt');m.validate_receipt(receipt,mode)
        need(receipt['exit']==0 and receipt['timeout'] is False and receipt['truncated'] is False and receipt['child_exited'] is True and receipt['drain_joined'] is True,'PILOT_EXIT')
        log=reader.read(root/mode/'output.log',root,mode+'_log',2*1024*1024);raw=reader.read(root/mode/filename,root,mode+'_report');need(sha(log)==receipt['stdout_sha256'] and sha(raw)==receipt['report_sha256'],'RECEIPT_BYTES')
        reports[mode]=strict(raw);receipts[mode]=receipt
    nr=receipts['native'];vr=receipts['verify'];n=reports['native'];v=reports['verify'];check_stamp(s,c,reader,nr,vr)
    need(all(intpos(n[k]) for k in ('start_ns','end_ns')),'NATIVE_CLOCK_TYPE')
    need(result['native_receipt']==nr and result['verify_receipt']==vr and result['native_report_sha256']==nr['report_sha256'] and result['verification_sha256']==vr['report_sha256'],'RESULT_RECEIPTS')
    need(nr['pid']!=vr['pid'] and nr['end_ns']<=vr['start_ns'] and vr['end_ns']<=c.started,'PROCESS_CHRONOLOGY')
    # Bind RPF86's last verifier to the postcheck without inventing an RPF87
    # native finish time. Original RPF87 has already validated Router -> RPF86.
    if not c.synthetic:
        prior=reader.json(c.pilot86/'verify/launch-receipt.json',c.pilot86,'r86_verifier_clock');need(prior['monotonic_end_ns']<s['postcheck_monotonic_ns'],'PRIOR_LANE_CLOCK')
    rows=manifest_read(reader,root/'native/work',n['manifest'],root)
    journal=reader.read(root/'native/journal.jsonl',root,'native_journal')
    frames=[strict(line) for line in journal.splitlines()];need(len(frames)==43,'JOURNAL_FRAMES')
    listing=[f['data'] for f in frames if f['kind']=='LISTING']
    need(listing==[dict(event='os.listdir',directory_id=d,phase='MODULE_IMPORT',caller_kind='CPYTHON_FILEFINDER',decision='ALLOW') for d in ('REPO','RUNTIME','TESTS','PACKAGE','EFFECTWITNESS')],'LISTING_EXACT')
    starts={f['data']['id']:f['time_ns'] for f in frames if f['kind']=='STARTED'}
    stops={f['data']['id']:f['time_ns'] for f in frames if f['kind']=='STOP'}
    for call in n['sqlite_calls']:
        need(intpos(call['start_ns']) and intpos(call['end_ns']) and starts[call['method']]<=call['start_ns']<=call['end_ns']<=stops[call['method']],'SQL_METHOD_CLOCK')
    cache=root/'native/pycache';nonlink(cache);need(cache.is_dir() and not os.listdir(cache),'CACHE_NOT_EMPTY')
    # Module-local manifest reader narrows the original validator's directory
    # traversal to the declared files. sqlite3 global module is never patched.
    m.manifest=lambda path:rows if path==root/'native/work' else (_ for _ in ()).throw(Invalid('MANIFEST_SCOPE'))
    dbpaths={root/'native/work'/row['path'] for row in rows if row['path'].endswith('/orders.sqlite3')}
    need(len(dbpaths)==2 and len({row['sha256'] for row in rows if row['path'].endswith('/orders.sqlite3')})==2,'DATABASE_INDEPENDENT_SOURCE')
    def readonly(database,**kw):
        return readonly_connect(dbpaths,database,**kw)
    m.sqlite3=types.SimpleNamespace(connect=readonly)
    checked=m.validate_native(n,nr,source,root/'native/work',journal)
    fields(v,('status journal databases manifest_sha256 schema pid native_pid start_ns end_ns source native_report_sha256 resources original_tests_rerun').split())
    need(v['schema']=='rpf88-independent-v1' and v['status']=='PASS' and type(v['pid']) is int and type(v['native_pid']) is int and v['pid']==vr['pid'] and v['native_pid']==nr['pid'] and v['original_tests_rerun'] is False and v['source']==source and v['native_report_sha256']==nr['report_sha256'] and v['resources']==m.RESOURCES and all(type(x) is int for x in v['resources'].values()),'INDEPENDENT_IDENTITY')
    need(all(intpos(v[k]) for k in ('start_ns','end_ns')),'VERIFIER_CLOCK_TYPE')
    need(vr['start_ns']<=v['start_ns']<v['end_ns']<=vr['end_ns'] and nr['end_ns']<=v['start_ns'],'VERIFIER_CHRONOLOGY')
    need(all(canonical(v[k])==canonical(checked[k]) for k in checked),'INDEPENDENT_SEMANTICS')
    need(canonical(public)==canonical(m.public_projection(result)),'PUBLIC_PROJECTION')
    # Original SQL methods must have different physical databases; metadata
    # that merely duplicates one valid DB cannot stand for two executions.
    bymethod={i:{x['target'] for x in n['sqlite_calls'] if x['method']==i} for i in m.IDS[15:17]}
    need(all(len(x)==1 for x in bymethod.values()) and len(set.union(*bymethod.values()))==2,'SQL_METHOD_DATABASE_BINDING')
    for p in dbpaths:
        need(sha(p.read_bytes())==next(row['sha256'] for row in rows if row['path']==p.relative_to(root/'native/work').as_posix()),'DATABASE_CHANGED_AFTER_READ')
    return m.IDS,dict(native_receipt_sha256=reader.anchors['native_receipt'],verification_receipt_sha256=reader.anchors['verify_receipt'],journal_sha256=reader.anchors['native_journal'],manifest_sha256=checked['manifest_sha256'],checkpoint_sha256=reader.anchors['checkpoint'],postcheck_monotonic_ns=s['postcheck_monotonic_ns'],native_start_ns=nr['start_ns'],native_end_ns=nr['end_ns'],verifier_start_ns=vr['start_ns'],verifier_end_ns=vr['end_ns'])
def derive(base,ids,proof,c,reason=None):
    need(ids==load_pinned(R88).IDS,'FROZEN_18_IDS')
    rows=base['effective_required']['methods'];mapping={i:i.removeprefix('runtime.tests.') for i in ids};byid={x['id']:x for x in rows}
    need(len(ids)==len(mapping)==18 and len(set(mapping.values()))==18 and set(mapping.values())<=set(byid),'EXACT_MAPPING')
    need(all(byid[i]['route']=='DEDICATED_RUNNER' and byid[i]['original_actual']=='UNAVAILABLE' and byid[i]['effective_actual']=='UNAVAILABLE' and byid[i]['source_lane']=='ORIGINAL_ROUTER' and byid[i]['required'] is True for i in mapping.values()),'ORIGINAL_18_DISPOSITION')
    accepted=set(mapping.values()) if reason is None else set();ms=[]
    for row in rows:
        new=dict(row)
        if row['id'] in accepted:new.update(effective_actual='PASS',source_lane='RPF88_R72_DEDICATED')
        ms.append(new)
    counts=dict(Counter(x['effective_actual'] for x in ms));need(counts==({'PASS':711,'SKIP':5,'UNAVAILABLE':516} if accepted else {'PASS':693,'SKIP':5,'UNAVAILABLE':534}),'DERIVED_COUNTS')
    return dict(schema='rpf89-required-coverage-v2',run_id=c.run,run_attempt=c.attempt,commit=c.commit,github_job=c.job,
        evidence_kind='LOCAL_SYNTHETIC_CONTROL_ONLY' if c.synthetic else 'HOSTED_SAME_RUN_POSTCHECK_AND_PRIVATE_RECEIPTS',source_level='SYNTHETIC_OFFLINE_TEST',no_real_provider_claim=True,
        upstream_rpf87_counts=base['effective_required']['counts'],old_admitted=base['admitted_dedicated'],
        new_admitted=[dict(full_id=i,router_id=mapping[i],source_lane='RPF88_R72_DEDICATED',**proof) for i in ids] if accepted else [],not_admitted=reason,
        effective_required=dict(required=1232,methods=ms,counts=counts),unavailable_remaining=counts['UNAVAILABLE'],dedicated_unavailable_remaining=412-len(accepted),
        release_eligible=False,release_executed=False,deployment_authorized=False)
def assess_value(c):
    need(sha(SELF.read_bytes())==LOADED_SHA,'LOADED_SOURCE_DRIFT');reader=Reader();base,_=legacy_revalidate(c,reader)
    source=load_pinned(R88);ids=source.IDS;reason=None;proof={}
    try:
        s=reader.json(c.stamp,c.root,'checkpoint');ids,proof=pilot_revalidate(c,reader,base,s)
    except Exception as e:
        code=str(e) if isinstance(e,(Invalid,source.Invalid)) else type(e).__name__
        reason=code if re.fullmatch('[A-Z][A-Z0-9_]{0,79}',code) else 'INVALID_RPF88_PRIVATE_EVIDENCE'
    value=derive(base,ids,proof,c,reason);value['evidence_anchors']=reader.anchors
    value['source_identity']=dict(rpf87_blob=PINS[R87],rpf88_blob=PINS[R88],assessor_lf_sha256=sha(SELF.read_bytes().replace(b'\r\n',b'\n')),workflow_lf_sha256=sha(pinned('.github/workflows/release-gate.yml',PINS['.github/workflows/release-gate.yml']).replace(b'\r\n',b'\n')))
    return value
def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0]=='diagnose':return diagnose_main(argv)
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['stamp','assess','enforce'])
    for k in ('run-id','attempt','commit','rpf87','rpf88','checkpoint','output','ledger','handoff','pilot86','fixture-root'):ap.add_argument('--'+k)
    ap.add_argument('--synthetic',action='store_true');a=ap.parse_args(argv)
    try:
        # Validate missing identity without filesystem I/O, as the original B
        # controls require. Synthetic can never opt into hosted semantics.
        need(a.run_id is not None and a.attempt is not None and a.commit is not None,'IDENTITY_REQUIRED')
        c=Context(a.run_id,a.attempt,a.commit,a.synthetic,a.fixture_root);c.check_args(a)
        if a.command=='stamp':
            v=stamp(c,'success' if c.synthetic else os.environ.get('RPF87_STEP_OUTCOME'));print('RPF89_POSTCHECK_WRITTEN; POST_COMPLETION_OBSERVATION_NOT_RPF87_NATIVE_FINISH');return 0
        if a.command=='assess':need(not os.path.lexists(c.output),'OUTPUT_OCCUPIED')
        v=assess_value(c)
        if a.command=='assess':write_exclusive(c.output,v);print('RPF89_ASSESSED; admitted_r72='+str(len(v['new_admitted']))+'; unavailable_required='+str(v['unavailable_remaining']));return 0
        saved=Reader().read(c.output,c.root,'derived');need(saved==canonical(strict(saved))+b'\n' and canonical(strict(saved))==canonical(v),'DERIVED_REVALIDATION')
        print('RELEASE_BLOCKED_BY_REQUIRED_COVERAGE; unavailable_required='+str(v['unavailable_remaining'])+'; admitted_r72='+str(len(v['new_admitted']))+'; NO_RELEASE/NO_DEPLOY');return 1
    except Exception as exc:
        code=str(exc) if isinstance(exc,Invalid) or type(exc).__name__=='Invalid' else type(exc).__name__.upper()
        safe=code if re.fullmatch('[A-Z][A-Z0-9_]{0,79}',code) else 'RPF89_REVALIDATION'
        print('INVALID_GATE_INPUT:'+safe+'; NO_RELEASE/NO_DEPLOY',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())

"""RPF87 protocol fixtures only. No original Runtime test is imported or run."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import uuid
import types

def load(name,file):
    path=Path(__file__).with_name(file);m=types.ModuleType(name);m.__file__=str(path)
    before=sys.pycache_prefix
    sys.pycache_prefix=str(Path(os.environ['RPF87_OWNER'])/'test-loader-cache')
    try:exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__)
    finally:sys.pycache_prefix=before
    return m
r=load('rpf87','reconcile-rpf86-required-coverage.py')

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(value if isinstance(value,bytes) else json.dumps(value,indent=2).encode())
def corrupt(path,value):path.write_bytes(value if isinstance(value,bytes) else json.dumps(value,indent=2).encode())

def source_fixture(p):
    """Metadata from exact Git source objects; no certificate content read."""
    objects={n:r.git('cat-file','blob',r.git('rev-parse',r.BASE+':'+n).decode().strip()) for n in p.ATTRIBUTION_FILES}
    def file(n,pin):
        raw=objects[n];return dict(blob=pin,raw_sha256=r.sha(raw),lf_sha256=r.sha(raw.replace(b'\r\n',b'\n')))
    catalog={}
    for n,raw in objects.items():
        tree=ast.parse(raw);catalog[n]=dict(raw_sha256=r.sha(raw),lines=len(raw.splitlines()),functions=[dict(name=x.name,start=x.lineno,end=x.end_lineno) for x in ast.walk(tree) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))])
    tree=ast.parse(objects['runtime/tests/test_effectwitness_pge_dual.py']);cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='DualTests');methods={x.name:x for x in cls.body if isinstance(x,ast.FunctionDef)}
    return dict(files={n:file(n,pin) for n,pin in p.PINS.items()},cache_sources={n:file(n,pin) for n,pin in p.CACHE_SOURCES.items()},
        helper=dict(blob=p.HELPER_BLOB,raw_sha256=r.sha(objects[p.HELPER])),
        certificate=dict(path=p.CERT_NAME,blob=p.CERT_BLOB,raw_sha256=p.CERT_SHA,bytes=p.CERT_BYTES,structure='identity:dict',status='PIN_VERIFIED',secret_scan='NO_UNEXPECTED_CREDENTIAL_SHAPE'),
        attribution_sources=catalog,method_ast={n:r.sha(ast.dump(methods[n],include_attributes=False).encode()) for n in p.NAMES},
        assertion_counts={n:sum(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr.startswith('assert') for x in ast.walk(methods[n])) for n in p.NAMES},
        harness_lf_sha256=r.sha(objects['ci/run-rpf86-owner-admission.py'].replace(b'\r\n',b'\n')))

# This child emits explicitly synthetic protocol metadata, not unittest results.
CONTROL=r'''
import json,os,sys,time,hashlib
from pathlib import Path
d=json.load(sys.stdin);root=Path(sys.argv[1]);kind=sys.argv[2]
if kind=='native':
    report=d['report'];report['pid']=os.getpid();report['monotonic_start_ns']=time.monotonic_ns()
    journal=root/'denial-journal.jsonl';previous=None;seq=0
    with journal.open('xb') as out:
        def emit(kind,data):
            global previous,seq
            row=dict(schema='rpf86-durable-denial-v1',seq=seq,previous_raw_sha256=previous,pid=os.getpid(),monotonic_ns=time.monotonic_ns(),source_sha256=report['source_identity']['harness_lf_sha256'],run_id='a'*32,kind=kind,data=data)
            raw=json.dumps(row,sort_keys=True,separators=(',',':')).encode()+b'\n';out.write(raw);out.flush();os.fsync(out.fileno());previous=hashlib.sha256(raw).hexdigest();seq+=1
        emit('INIT',dict(ids=report['ids']))
        for tid in report['ids']:
            emit('METHOD_START',dict(id=tid));emit('METHOD_STOP',dict(id=tid,actual='PASS'))
        emit('TERMINAL',dict(status='PASS',error=None))
    report['monotonic_end_ns']=time.monotonic_ns()
    with (root/'child-result.json').open('x') as out:json.dump(report,out)
else:
    with (root/'verification.json').open('x') as out:json.dump(d['verification'],out)
print('RPF87_SYNTHETIC_PROTOCOL_CONTROL; ORIGINAL_METHODS_NOT_EXECUTED; PID='+str(os.getpid()))
'''

def control(folder,kind,payload,source):
    folder.mkdir(parents=True,exist_ok=False);start=time.monotonic_ns()
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','COMSPEC') if k in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',HOME=str(folder),TEMP=str(folder),TMP=str(folder))
    p=subprocess.Popen([sys.executable,'-B','-c',CONTROL,str(folder),kind],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,cwd=r.ROOT)
    raw,_=p.communicate(json.dumps(payload).encode(),timeout=10);end=time.monotonic_ns();assert p.returncode==0 and len(raw)<2*1024*1024
    write(folder/'output.log',raw)
    return dict(mode=kind,pid=p.pid,exit=p.returncode,timeout=False,truncated=False,bytes=len(raw),stdout_sha256=r.sha(raw),
        monotonic_start_ns=start,monotonic_end_ns=end,timeout_limit_seconds=10,child_exited=True,drain_joined=True,
        harness_lf_sha256=source['harness_lf_sha256'],cleanup_scope='Exact Popen handle; OS process-tree coverage UNAVAILABLE')

def fixture(case):
    old=load('rpf87_original_handoff_fixture','test_verify_runtime_coverage_handoff.py')
    old.v=r.modules()[0]
    original_owner=old.v.OWNER;old.v.OWNER=r.local_owner()
    try:old.fixture(case/'rpf84')
    finally:old.v.OWNER=original_owner
    h,p=r.modules();h.OWNER=r.local_owner();commit=r.git('rev-parse','HEAD').decode().strip()
    status=h.assess(case/'rpf84/ledger.json',1,'local','1',commit,synthetic=True);write(case/'rpf85.json',status)
    source=source_fixture(p);root=case/'rpf86';root.mkdir();work=root/'native/work'
    first=dict(seq=0,previous=None,event=dict(kind='OWNER',monotonic_ns=time.monotonic_ns(),owner='rpf-63',
        base='68572c05a52ff2258f50fb7c4488bff8e69ea61c',source_sha256=r.wal_lineage()))
    first['sha256']=r.sha(r.canonical(first));wal=r.canonical(first)+b'\n';write(work/'synthetic/ledger.jsonl',wal)
    files=[dict(path='synthetic/ledger.jsonl',bytes=len(wal),sha256=r.sha(wal))]
    guard=dict(observed={'read':1,'write':1,'certificate_read_granted':1},denied={},certificate=source['certificate'],
        attribution_schema='rpf86-denial-events-v1',attribution_events=[],attribution_total=0,attribution_truncated=False,
        attribution_sources=source['attribution_sources'],attribution_sha256=r.sha(b'[]'),
        metadata_intercepts=['os.stat','os.lstat','Path.resolve','os.mkdir'],limitations='Synthetic protocol fixture; not an execution claim')
    report=dict(schema='rpf86-native-v1',source_level='SYNTHETIC_OFFLINE_TEST',marker='TEST_HARNESS_OWNER_SUBSTITUTION',ids=p.IDS,
        results=[dict(id=x,actual='PASS') for x in p.IDS],events=[dict(id=x,actual=s) for x in p.IDS for s in ('STARTED','PASS')],tests_run=5,
        source_identity=source,physical_owner=work.relative_to(r.ROOT).as_posix(),logical_owner='rpf-63',logical_identity_changed=False,
        patch_points=['pge_dual_contracts.WORK'],patch_restored=True,guard=guard,source_unchanged=True,manifest=files,error=None,
        actual_provider_calls=0,actual_sdk_calls=0,actual_java_processes=0,actual_business_writes=0,old_inode_comparison='SYNTHETIC_CONTROL_ONLY',status='PASS',
        cache_policy=dict(policy='FRESH_OWNER_PREFIX',prefix_relative=(root/'native/pycache').relative_to(r.ROOT).as_posix(),dont_write_bytecode=True,source_pins=p.CACHE_SOURCES,global_loader_patch=False))
    # native/ exists because the synthetic work was created; child gets a new peer staging directory.
    staging=root/'control-native';nr=control(staging,'native',{'report':report},source)
    for name in ('child-result.json','denial-journal.jsonl','output.log'):write(root/'native'/name,(staging/name).read_bytes())
    nr['child_result_raw_sha256']=r.sha((root/'native/child-result.json').read_bytes())
    nr['journal']=p.read_journal(root/'native/denial-journal.jsonl',source['harness_lf_sha256'],nr['pid'],p.IDS,source['attribution_sources'])
    write(root/'native/launch-receipt.json',nr)
    verification=dict(status='PASS',native_ids=p.IDS,manifest_sha256=r.sha(json.dumps(files,sort_keys=True).encode()),wal_files=1,logical_owner='rpf-63',
        source_identity=source,guard=guard,journal=nr['journal'],source_level='SYNTHETIC_OFFLINE_TEST',independent_process=True,independent_issuer=False)
    vr=control(root/'verify','verify',{'verification':verification},source);write(root/'verify/launch-receipt.json',vr)
    result=dict(schema='rpf86-owner-admission-pilot-v1',status='PASS',source_level='SYNTHETIC_OFFLINE_TEST',marker='TEST_HARNESS_OWNER_SUBSTITUTION',ids=p.IDS,
        dedicated_owner_admission_pilot_pass=5,source_identity=source,physical_owner=work.relative_to(r.ROOT).as_posix(),logical_owner='rpf-63',
        native_receipt=nr,verification_receipt=vr,error=None,seconds=(vr['monotonic_end_ns']-nr['monotonic_start_ns'])/1e9+0.1,
        native_results=report['results'],formal_required_unavailable=539,official_coverage_changed=False,release_eligible=False,release_executed=False,deployment_authorized=False,
        actual_provider_calls=0,actual_sdk_calls=0,actual_java_processes=0,actual_business_writes=0,syscall_proof='Synthetic protocol fixture only')
    write(root/'result.json',result);write(root/'public-result.json',p.public_projection(result))
    write(root/'synthetic-control.json',{'schema':'RPF87_SYNTHETIC_PROTOCOL_ONLY','original_tests_executed':False})
    return commit

class ReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=r.local_owner()/('tests-'+uuid.uuid4().hex);cls.root.mkdir(exist_ok=False)
        shared=os.environ.get('RPF87_TEMPLATE')
        if shared:
            cls.template=Path(shared);r.need(cls.template.is_relative_to(r.local_owner()),'FIXTURE_TEMPLATE_SCOPE');r.nonlink(cls.template)
            cls.commit=r.git('rev-parse','HEAD').decode().strip()
        else:cls.template=cls.root/'template';cls.template.mkdir();cls.commit=fixture(cls.template)
    def case(self):
        root=self.root/('case-'+uuid.uuid4().hex);shutil.copytree(self.template,root)
        (root/'rpf86/native/pycache').mkdir(exist_ok=True)
        # Source-bound physical owner differs for each synthetic case.
        p=r.modules()[1];report=r.strict((root/'rpf86/native/child-result.json').read_bytes())
        report['physical_owner']=(root/'rpf86/native/work').relative_to(r.ROOT).as_posix();report['cache_policy']['prefix_relative']=(root/'rpf86/native/pycache').relative_to(r.ROOT).as_posix()
        corrupt(root/'rpf86/native/child-result.json',report)
        nr=r.strict((root/'rpf86/native/launch-receipt.json').read_bytes());nr['child_result_raw_sha256']=r.sha((root/'rpf86/native/child-result.json').read_bytes());corrupt(root/'rpf86/native/launch-receipt.json',nr)
        result=r.strict((root/'rpf86/result.json').read_bytes());result['physical_owner']=report['physical_owner'];result['native_receipt']=nr
        corrupt(root/'rpf86/result.json',result);corrupt(root/'rpf86/public-result.json',p.public_projection(result));return root
    def reconcile(self,root):
        ctx=r.Context('local','1',self.commit,synthetic=True,root=root)
        return r.reconcile(ctx,ctx.ledger,ctx.handoff,ctx.pilot,ctx.output)
    def rejection(self,root):
        value=self.reconcile(root);self.assertEqual(value['admitted_dedicated'],[]);self.assertEqual(value['unavailable_remaining'],539)
        self.assertEqual(value['effective_required']['counts'],{'PASS':688,'SKIP':5,'UNAVAILABLE':539});self.assertIsNotNone(value['not_admitted'])
    def test_atomic_positive_exact_difference_and_no_release(self):
        v=self.reconcile(self.case());self.assertEqual(v['effective_required']['counts'],{'PASS':693,'SKIP':5,'UNAVAILABLE':534})
        self.assertEqual(len(v['admitted_dedicated']),5);self.assertEqual(v['dedicated_unavailable_remaining'],412)
        self.assertEqual(v['original_router']['counts'],{'PASS':688,'SKIP':5,'UNAVAILABLE':539})
        self.assertEqual(v['evidence_kind'],'LOCAL_SYNTHETIC_CONTROL_ONLY');self.assertFalse(v['release_eligible'])
        self.assertEqual(sorted(x['id'] for x in v['effective_required']['methods'] if x['original_actual']!=x['effective_actual']),
                         sorted(x['router_id'] for x in v['admitted_dedicated']))
    def test_actual_cli_assess_zero_enforce_one_invalid_two(self):
        root=self.case();ctx=r.Context('local','1',self.commit,synthetic=True,root=root)
        args=['--ledger',str(ctx.ledger),'--handoff',str(ctx.handoff),'--pilot',str(ctx.pilot),'--output',str(ctx.output),
              '--run-id','local','--attempt','1','--commit',self.commit,'--synthetic','--fixture-root',str(root)]
        observed=[]
        for command in ('assess','enforce','assess'):
            p=subprocess.run([sys.executable,'-B',str(r.SELF),command,*args],capture_output=True,timeout=60);observed.append(p.returncode)
            self.assertLess(len(p.stdout)+len(p.stderr),2*1024*1024)
        self.assertEqual(observed,[0,1,2]);self.assertEqual(r.strict(ctx.output.read_bytes())['unavailable_remaining'],534)
        write(root/'cli-proof.json',dict(exits=observed,synthetic_only=True))
    def test_json_unknown_duplicate_nonfinite_and_overwrite(self):
        for raw in (b'',b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b' '*(r.MAX_JSON+1)):
            with self.assertRaises((r.Invalid,ValueError)):r.strict(raw)
        root=self.case();p=root/'rpf86/result.json';v=r.strict(p.read_bytes());v['unknown']=True;corrupt(p,v);self.rejection(root)
        path=root/'create-only.json';r.write_result(path,{})
        with self.assertRaises(FileExistsError):r.write_result(path,{})
    def test_public_only_and_result_only_cannot_admit(self):
        for path in ('rpf86/native/child-result.json','rpf86/verify/verification.json','rpf86/native/denial-journal.jsonl','rpf86/verify/launch-receipt.json'):
            root=self.case();corrupt(root/path,b'{}');self.rejection(root)
        root=self.case();corrupt(root/'rpf86/public-result.json',{'status':'PASS'});self.rejection(root)
    def test_receipt_pid_clock_timeout_exit_and_hash_reject(self):
        for key,value in [('pid',True),('exit',1),('timeout',True),('truncated',True),('child_exited',False),('drain_joined',False),('stdout_sha256','0'*64),('monotonic_start_ns',10**25)]:
            root=self.case();path=root/'rpf86/native/launch-receipt.json';rec=r.strict(path.read_bytes());rec[key]=value;corrupt(path,rec);self.rejection(root)
    def test_guard_even_with_all_method_pass_is_not_admitted(self):
        root=self.case();path=root/'rpf86/native/child-result.json';v=r.strict(path.read_bytes());v['guard']['denied']={'READ_SCOPE_DENIED':1};corrupt(path,v)
        receipt=root/'rpf86/native/launch-receipt.json';n=r.strict(receipt.read_bytes());n['child_result_raw_sha256']=r.sha(path.read_bytes());corrupt(receipt,n)
        result=root/'rpf86/result.json';d=r.strict(result.read_bytes());d['native_receipt']=n;corrupt(result,d);self.rejection(root)
    def test_method_missing_duplicate_wrong_portable_and_source_drift(self):
        for kind in ('missing','duplicate','portable','source'):
            root=self.case();path=root/'rpf86/result.json';v=r.strict(path.read_bytes())
            if kind=='missing':v['ids'].pop()
            elif kind=='duplicate':v['ids'][1]=v['ids'][0]
            elif kind=='portable':v['ids'][-1]='runtime.tests.test_effectwitness_pge_dual.DualTests.test_host_blocks_write_after_unknown'
            else:v['source_identity']['harness_lf_sha256']='0'*64
            corrupt(path,v);self.rejection(root)
    def test_physical_log_manifest_and_wal_drift_reject(self):
        for path in ('rpf86/native/output.log','rpf86/verify/output.log','rpf86/native/work/synthetic/ledger.jsonl','rpf86/native/denial-journal.jsonl'):
            root=self.case();p=root/path;p.write_bytes(p.read_bytes()+b'corrupt');self.rejection(root)
    def test_original_handoff_and_routes_cannot_be_changed(self):
        for mutate in (lambda v:v['counts'].update(PASS=693),lambda v:v.update(all_required_status='PASS'),lambda v:v.update(router_exit=True)):
            root=self.case();path=root/'rpf85.json';v=r.strict(path.read_bytes());mutate(v);corrupt(path,v)
            with self.assertRaisesRegex(r.Invalid,'INVALID_ORIGINAL_HANDOFF'):self.reconcile(root)
        root=self.case();path=root/'rpf84/ledger.json';v=r.strict(path.read_bytes())
        next(x for m in v['modules'] for x in m['rows'] if x['id'].endswith('DualTests.test_four_paths'))['route']='PORTABLE';corrupt(path,v)
        with self.assertRaises(r.Invalid):self.reconcile(root)
    def test_missing_pilot_retains_539_and_safe_projection(self):
        root=self.case();p=root/'rpf86/result.json';p.write_bytes(b'{}');v=self.reconcile(root)
        self.assertEqual(v['unavailable_remaining'],539);self.assertNotIn(str(root),json.dumps(v))
        def walk(value):
            if isinstance(value,dict):
                self.assertFalse(set(value)&{'sdk_identity','target_token','physical_owner','wal_content','authorization'})
                for x in value.values():walk(x)
            elif isinstance(value,list):
                for x in value:walk(x)
        walk(v)
    def test_paths_cannot_touch_old_or_cross_run_targets(self):
        ctx=r.Context('local','1',self.commit,synthetic=True,root=self.case())
        for path in (r.ROOT/'.local/rpf-63/ledger.json',r.ROOT/'docs/reviews/forbidden',ctx.ledger.parent/'..'/'ledger.json'):
            with patch.object(Path,'lstat',side_effect=AssertionError('forbidden metadata')):
                with self.assertRaises(r.Invalid):ctx.paths(path,ctx.handoff,ctx.pilot,ctx.output)
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            with self.assertRaises(r.Invalid):r.Context('local','1',self.commit,synthetic=True,root=ctx.root)
        with self.assertRaises(r.Invalid):r.Context('local','2','0'*40,synthetic=True,root=ctx.root)
    def test_reparse_is_rejected_before_following(self):
        root=self.case();target=self.root/('target-'+uuid.uuid4().hex);target.mkdir();link=root/'rpf86/native/work/link'
        try:link.symlink_to(target,target_is_directory=True)
        except OSError:
            if os.name!='nt':raise
            import _winapi
            _winapi.CreateJunction(str(target),str(link))
        self.rejection(root)
    def test_existing_pure_safety_boundaries_regress(self):
        pilot=load('rpf87_pilot_regressions','test_run_rpf86_owner_admission.py')
        pilot.OwnerAdmissionTests.root=self.root;pilot.OwnerAdmissionTests.source=source_fixture(pilot.r)
        for name in ('test_original_source_and_assertions_pinned','test_protocol_control_not_native_pass_and_false_greens_reject','test_unsettled_child_never_passes','test_json_duplicate_nonfinite','test_hosted_public_projection_omits_paths_protocol_and_identity_values'):
            case=pilot.OwnerAdmissionTests(name);getattr(case,name)()
        router=load('rpf87_router_regressions','test_run_runtime_contract_tests.py')
        for name in ('test_duplicate_and_nonfinite_json_fail','test_wrong_schema_type_fails','test_forged_skip_and_pass_need_real_progress_events','test_partial_progress_never_upgrades_unstarted_or_duplicate'):
            case=router.RouterTests(name);case.setUp();getattr(case,name)()
        old=load('rpf87_handoff_regression','test_verify_runtime_coverage_handoff.py')
        old.v=r.modules()[0]
        old.v.OWNER=r.local_owner();case=old.CoverageHandoffTests('test_synthetic_positive_continues_but_barrier_rejects')
        case.commit=self.commit;case.root=self.root;case.template=self.template/'rpf84'
        for name in ('test_synthetic_positive_continues_but_barrier_rejects','test_ci_identity_and_synthetic_cannot_cross_boundary','test_summary_appends_separate_blocker_and_rejects_escape'):
            getattr(case,name)()

    def rebind_native(self,root,change):
        path=root/'rpf86/native/child-result.json';report=r.strict(path.read_bytes());change(report);corrupt(path,report)
        recpath=root/'rpf86/native/launch-receipt.json';rec=r.strict(recpath.read_bytes());rec['child_result_raw_sha256']=r.sha(path.read_bytes());corrupt(recpath,rec)
        path=root/'rpf86/result.json';result=r.strict(path.read_bytes());result['native_receipt']=rec;result['native_results']=report['results'];corrupt(path,result)
        corrupt(root/'rpf86/public-result.json',r.modules()[1].public_projection(result))

    def test_rehashed_fake_native_events_and_bool_resource_still_reject(self):
        changes=[lambda v:v['events'].pop(0),lambda v:v['events'].insert(1,copy.deepcopy(v['events'][0])),
                 lambda v:v['results'][0].update(actual='SKIP'),lambda v:v.update(actual_provider_calls=False)]
        for change in changes:
            root=self.case();self.rebind_native(root,change);self.rejection(root)

    def test_rehashed_wal_owner_source_cannot_be_self_signed_into_pass(self):
        root=self.case();path=root/'rpf86/native/work/synthetic/ledger.jsonl';v=r.strict(path.read_bytes());v['event']['source_sha256']='0'*64
        v['sha256']=r.sha(r.canonical({k:x for k,x in v.items() if k!='sha256'}));raw=r.canonical(v)+b'\n';path.write_bytes(raw)
        files=[dict(path='synthetic/ledger.jsonl',bytes=len(raw),sha256=r.sha(raw))]
        self.rebind_native(root,lambda v:v.update(manifest=files))
        path=root/'rpf86/verify/verification.json';v=r.strict(path.read_bytes());v['manifest_sha256']=r.sha(json.dumps(files,sort_keys=True).encode());corrupt(path,v)
        self.rejection(root)

    def test_independent_pid_time_and_same_run_are_required(self):
        for kind in ('pid','time','independent'):
            root=self.case();nr=r.strict((root/'rpf86/native/launch-receipt.json').read_bytes())
            path=root/'rpf86/verify/launch-receipt.json';v=r.strict(path.read_bytes())
            if kind=='pid':v['pid']=nr['pid']
            elif kind=='time':v['monotonic_start_ns']=nr['monotonic_start_ns']-1
            else:
                path2=root/'rpf86/verify/verification.json';z=r.strict(path2.read_bytes());z['independent_process']=False;corrupt(path2,z)
            corrupt(path,v);path=root/'rpf86/result.json';z=r.strict(path.read_bytes());z['verification_receipt']=v;corrupt(path,z);self.rejection(root)
        root=self.case()
        for run,attempt in (('other','1'),('local','2')):
            ctx=r.Context(run,attempt,self.commit,synthetic=True,root=root)
            with self.assertRaisesRegex(r.Invalid,'INVALID_ORIGINAL_HANDOFF'):r.reconcile(ctx,ctx.ledger,ctx.handoff,ctx.pilot,ctx.output)

    def test_exact_source_loader_does_not_patch_global_imports(self):
        before=importlib.util.spec_from_file_location;h,p=r.modules()
        self.assertIs(importlib.util.spec_from_file_location,before)
        with self.assertRaises(r.Invalid):r.validator_spec('unexpected',r.ROOT/'ci/run-runtime-contract-tests.py')
        with self.assertRaises(r.Invalid):r.validator_spec('rpf85_pinned_router',r.ROOT/'.local/rpf-63/source.py')
        with patch.object(r,'LOADED_SOURCE_SHA','0'*64):
            with self.assertRaisesRegex(r.Invalid,'RECONCILER_SOURCE_DRIFT'):self.reconcile(self.case())

if __name__=='__main__':unittest.main()

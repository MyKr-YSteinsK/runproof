"""RPF89 rev-2 controls; original Runtime test methods are never executed.
The twelve rev-1 rejection/schema controls remain alongside physical fixtures.
"""
import ast
import copy
import os
import sqlite3
import time
import uuid
from contextlib import closing
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('r89',Path(__file__).with_name('reconcile-rpf88-required-coverage.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class Preconditions(unittest.TestCase):
    def test_source_pins_and_inventory(self):
        v=r.audit();self.assertEqual(len(v['selected']),18);self.assertEqual(len(v['excluded']),7);self.assertEqual(len(v['method_ast']),25)
        self.assertEqual(v['new_admissions'],0);self.assertFalse(v['baseline_counts_reverified'])
    def test_missing_clock_is_observed_not_inferred(self):
        v=r.audit();self.assertFalse(v['clock']['own_completion_clock_declared']);self.assertFalse(v['clock']['actual_run_evidence_read']);self.assertFalse(v['clock']['timestamp_inference_from_step_order'])
    def test_unidentifiable_schedules(self):
        self.assertEqual(r.model_observations(10,20),r.model_observations(30,20))
        with self.assertRaises(r.Invalid):r.model_observations(True,20)
    def test_both_admission_commands_refuse_before_any_receipt_io(self):
        for command in ['assess','enforce']:
            with patch.object(Path,'open',side_effect=AssertionError('NO_IO')),patch.object(Path,'stat',side_effect=AssertionError('NO_METADATA')),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(r.main([command,'--rpf88',str(r.ROOT/'.local/rpf-old/forbidden'),'--output',str(r.ROOT/'docs/reviews/forbidden')]),2)
    def test_fake_hosted_env_cannot_enable_assessment(self):
        with patch.dict(r.os.environ,{'GITHUB_ACTIONS':'true','GITHUB_RUN_ID':'1','GITHUB_SHA':'a'*40}),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(r.main(['assess','--synthetic']),2)
    def test_json_duplicate_and_nonfinite(self):
        for raw in [b'{"a":1,"a":2}',b'{"a":NaN}',b'',b' '*8388609]:
            with self.assertRaises((r.Invalid,ValueError)):r.strict(raw)
    def test_schema_change_is_not_silently_accepted(self):
        raw=(r.ROOT/'ci/reconcile-rpf86-required-coverage.py').read_bytes()
        bad=raw.replace(b'return dict(native_receipt_sha256=',b'return dict(extra=True,native_receipt_sha256=')
        with self.assertRaises(r.Invalid):r.completion_evidence(bad)
    def test_source_drift_rejects(self):
        with patch.object(r,'git',return_value=b'bad'):
            with self.assertRaises(r.Invalid):r.pinned('ci/reconcile-rpf86-required-coverage.py',r.PINS['ci/reconcile-rpf86-required-coverage.py'])
    def test_runtime_not_imported(self):
        self.assertNotIn('runtime.tests.test_effectwitness_pge_r72',sys.modules)
        self.assertNotIn('runtime.tests.test_effectwitness_pge_dual',sys.modules)
    def test_legacy_workflow_unchanged_and_live_enforce_kept(self):
        raw=r.pinned('.github/workflows/release-gate.yml',r.PINS['.github/workflows/release-gate.yml'])
        self.assertIn(b'ci/reconcile-rpf86-required-coverage.py enforce',raw);self.assertEqual(r.workflow_source(raw,r.git('cat-file','blob',r.PINS['.github/workflows/release-gate.yml'])),raw)
    def test_no_derived_counts_or_release_claim(self):
        v=r.audit();self.assertNotIn('effective_required',v);self.assertFalse(v['release_eligible']);self.assertFalse(v['deployment_authorized'])
    def test_actual_cli_fail_closed(self):
        p=subprocess.run([sys.executable,'-B',str(r.ROOT/'ci/reconcile-rpf88-required-coverage.py'),'assess'],capture_output=True,timeout=10)
        self.assertEqual(p.returncode,2);self.assertIn(b'INVALID_GATE_INPUT',p.stderr);self.assertNotIn(b'unavailable_required=516',p.stdout)

def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);r.write_exclusive(p,v)
def raw_write(p,b):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def local_baseline(c):
    prov=r.strict((r.ROOT/'spikes/rpf-87/coverage-provenance.json').read_bytes());matrix=r.strict((r.ROOT/'ci/runtime-contract-test-matrix.json').read_bytes())
    mods={Path(x['path']).stem:x for x in matrix['modules']};five={x['router_id'] for x in prov['exact_five_mapping']};unavailable=set(prov['original_unavailable_ids']);skips=set([i for i in prov['required_ids'] if i not in unavailable][:5]);rows=[]
    for tid in prov['required_ids']:
        mod,local=tid.split('.',1);row=mods[mod];route=row['default']
        for rule in row['rules']:
            if local==rule['selector'] or local.startswith(rule['selector']+'.'):route=rule['route']
        before='UNAVAILABLE' if tid in unavailable else 'SKIP' if tid in skips else 'PASS'
        rows.append(dict(id=tid,route=route,required=True,original_actual=before,effective_actual='PASS' if tid in five else before,source_lane='RPF86_DEDICATED' if tid in five else 'ORIGINAL_ROUTER'))
    return dict(schema='rpf87-required-coverage-reconciliation-v1',run_id=c.run,attempt=c.attempt,commit=c.commit,evidence_kind='LOCAL_SYNTHETIC_CONTROL_ONLY',original_router=dict(counts={'PASS':688,'SKIP':5,'UNAVAILABLE':539},enforce_exit=1),effective_required=dict(methods=rows,counts={'PASS':693,'SKIP':5,'UNAVAILABLE':534},required=1232),admitted_dedicated=prov['exact_five_mapping'],release_eligible=False,release_executed=False,deployment_authorized=False)

class CheckpointAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner=r.local_owner();cls.root=cls.owner/('controls-'+uuid.uuid4().hex);cls.root.mkdir()
        cls.commit=r.git('rev-parse','HEAD').decode().strip();cls.p=r.load_pinned(r.R88);cls.source=cls.p.identity()
    def context(self,folder=None):
        folder=folder or self.root/uuid.uuid4().hex
        return r.Context('local','1',self.commit,True,folder)
    def fixture(self):
        c=self.context();c.root.mkdir();write(c.r87,local_baseline(c));r.stamp(c,'success')
        # Two real short-lived Python controls emit ONLY protocol metadata.
        # They do not import/run BudgetTests. All candidate evidence is local.
        nrstart=time.monotonic_ns();z=subprocess.run([sys.executable,'-B','-c',"import os,json;print(json.dumps({'pid':os.getpid(),'kind':'LOCAL_SYNTHETIC_CONTROL_ONLY'}))"],capture_output=True,timeout=10);self.assertEqual(z.returncode,0);pid=json.loads(z.stdout)['pid']
        root=c.r88;work=root/'native/work';work.mkdir(parents=True);(root/'native/pycache').mkdir()
        started=time.monotonic_ns();frames=[];previous=None
        def event(kind,data):
            nonlocal previous
            f=dict(seq=len(frames),previous=previous,pid=pid,time_ns=time.monotonic_ns(),source=self.source['harness_lf_sha256'],kind=kind,data=data);b=r.canonical(f)+b'\n';frames.append(b);previous=r.sha(b)
        event('INIT',dict(ids=self.p.IDS))
        for d in ('REPO','RUNTIME','TESTS','PACKAGE','EFFECTWITNESS'):event('LISTING',dict(event='os.listdir',directory_id=d,phase='MODULE_IMPORT',caller_kind='CPYTHON_FILEFINDER',decision='ALLOW'))
        calls=[]
        for idx,i in enumerate(self.p.IDS):
            event('STARTED',dict(id=i))
            if idx in (15,16):
                run='rpf72-'+format(idx,'016x');p=work/'rpf72'/run/'runs'/('run-'+str(idx))/'business/orders.sqlite3';p.parent.mkdir(parents=True)
                begin=time.monotonic_ns()
                with closing(sqlite3.connect(p)) as db:
                    db.execute('CREATE TABLE refunds(amount_minor,status)');db.execute("INSERT INTO refunds VALUES(2500,'COMMITTED')")
                    db.execute('CREATE TABLE orders(refunded_minor,status)');db.execute("INSERT INTO orders VALUES(2500,'REFUNDED')")
                    db.execute('CREATE TABLE synthetic_provenance(method_index)');db.execute('INSERT INTO synthetic_provenance VALUES(?)',(idx,));db.commit()
                end=time.monotonic_ns()
                for b in (False,True):calls.append(dict(method=i,target=p.relative_to(work).as_posix(),readonly=b,original_forwarded=True,start_ns=begin,end_ns=end))
                first=dict(seq=0,previous=None,event=dict(kind='OWNER',session_id=run,clock=time.monotonic_ns(),context_sha256='a'*64));first['sha256']=r.sha(r.canonical(first));raw_write(work/'rpf72'/run/'wal.jsonl',r.canonical(first)+b'\n')
            event('STOP',dict(id=i,actual='PASS'))
        event('TERMINAL',dict(status='PASS'));journal=b''.join(frames);raw_write(root/'native/journal.jsonl',journal)
        rows=self.p.manifest(work);end=time.monotonic_ns();guard=dict(denied={},denial_events=[],observed={'read':1,'write':1,'metadata':1},metadata_intercepts=['os.stat','os.lstat','Path.resolve'],native_boundary='SQLITE_CONNECT_TARGET_ADMISSION',arbitrary_native_syscalls='UNAVAILABLE_NOT_KERNEL_SANDBOX')
        n=dict(schema='rpf88-native-v1',status='PASS',ids=self.p.IDS,states=dict.fromkeys(self.p.IDS,'PASS'),tests_run=18,source=self.source,pid=pid,start_ns=started,end_ns=end,guard=guard,sqlite_calls=calls,sqlite_module_alias=True,sqlite_wrapper_restored=True,owner_descriptor_restored=True,original_source_unchanged=True,original_test_assertions_unchanged=True,test_only_owner_scope_substitution=True,physical_workspace_fresh=True,source_level='SYNTHETIC_OFFLINE_TEST',logical_owner='rpf-72',workspace_contract_bytes_historically_identical=False,physical_owner=work.relative_to(r.ROOT).as_posix(),manifest=rows,cache_empty=True,error=None,resources=self.p.RESOURCES)
        write(root/'native/child-result.json',n);raw_write(root/'native/output.log',z.stdout)
        nr=dict(mode='native',pid=pid,exit=0,timeout=False,truncated=False,child_exited=True,drain_joined=True,start_ns=nrstart,end_ns=time.monotonic_ns(),stdout_sha256=r.sha(z.stdout),report_sha256=r.sha((root/'native/child-result.json').read_bytes()));write(root/'native/launch-receipt.json',nr)
        vrstart=time.monotonic_ns();z2=subprocess.run([sys.executable,'-B','-c',"import os,json;print(json.dumps({'pid':os.getpid(),'kind':'LOCAL_SYNTHETIC_CONTROL_ONLY'}))"],capture_output=True,timeout=10);self.assertEqual(z2.returncode,0);vpid=json.loads(z2.stdout)['pid']
        vstart=time.monotonic_ns();checked=self.p.validate_native(n,nr,self.source,work,journal)
        v=checked|dict(schema='rpf88-independent-v1',pid=vpid,native_pid=pid,start_ns=vstart,end_ns=time.monotonic_ns(),source=self.source,native_report_sha256=nr['report_sha256'],resources=self.p.RESOURCES,original_tests_rerun=False)
        write(root/'verify/verification.json',v);raw_write(root/'verify/output.log',z2.stdout)
        vr=dict(mode='verify',pid=vpid,exit=0,timeout=False,truncated=False,child_exited=True,drain_joined=True,start_ns=vrstart,end_ns=time.monotonic_ns(),stdout_sha256=r.sha(z2.stdout),report_sha256=r.sha((root/'verify/verification.json').read_bytes()));write(root/'verify/launch-receipt.json',vr)
        result=dict(schema='rpf88-result-v1',status='PASS',error=None,source=self.source,native_receipt=nr,verify_receipt=vr,states=n['states'],source_unchanged=True,guard_denied_count=0,native_report_sha256=nr['report_sha256'],verification_sha256=vr['report_sha256'],resources=self.p.RESOURCES)
        write(root/'result.json',result);write(root/'public-result.json',self.p.public_projection(result));write(c.root/'fixture-marker.json',dict(kind='LOCAL_SYNTHETIC_CONTROL_ONLY',original_methods_executed=False))
        return self.context(c.root),n,nr,v,vr
    def test_synthetic_full_positive_and_no_release(self):
        c,*_=self.fixture();v=r.assess_value(c);self.assertEqual(len(v['new_admitted']),18,v.get('not_admitted'));self.assertEqual(v['effective_required']['counts'],{'PASS':711,'SKIP':5,'UNAVAILABLE':516});self.assertEqual(v['dedicated_unavailable_remaining'],394);self.assertFalse(v['release_eligible']);self.assertEqual(v['evidence_kind'],'LOCAL_SYNTHETIC_CONTROL_ONLY')
        old=local_baseline(c)['effective_required']['methods'];new=v['effective_required']['methods'];self.assertEqual(sum(a!=b for a,b in zip(old,new)),18)
    def test_checkpoint_rejects_wrong_identity_source_time_and_pid(self):
        c,n,nr,v,vr=self.fixture();reader=r.Reader();base,_=r.legacy_revalidate(c,reader);stamp=r.strict(c.stamp.read_bytes());r.check_stamp(stamp,c,reader,nr,vr)
        for key,value in [('run_id','other'),('run_attempt','2'),('commit','a'*40),('github_job','OTHER'),('schema','wrong'),('rpf87_result_sha256','0'*64),('rpf89_stamp_source_lf_sha256','0'*64),('legacy_enforce_exit',0),('legacy_enforce_exit',2),('legacy_enforce_exit',True),('legacy_enforce_stdout_sha256','0'*64),('legacy_verified',True),('scope','INDEPENDENT_ISSUER'),('rpf87_step_outcome','failure'),('synthetic',False),('postcheck_monotonic_ns',nr['start_ns']),('postcheck_monotonic_ns',True),('postcheck_pid',nr['pid']),('postcheck_pid',vr['pid']),('extra',1)]:
            with self.subTest(key=key,value=value),self.assertRaises(r.Invalid):r.check_stamp(stamp|{key:value},c,reader,nr,vr)
    def test_stamp_outcome_and_existing_file_fail_before_revalidation(self):
        c=self.context();c.root.mkdir()
        with patch.object(r,'legacy_revalidate',side_effect=AssertionError('NO_LEGACY')),self.assertRaises(r.Invalid):r.stamp(c,'failure')
        write(c.stamp,{'occupied':True})
        with patch.object(r,'legacy_revalidate',side_effect=AssertionError('NO_LEGACY')),self.assertRaises(r.Invalid):r.stamp(c,'success')
    def test_stamp_legacy_invalid_does_not_create_receipt(self):
        c=self.context();c.root.mkdir()
        with patch.object(r,'legacy_revalidate',side_effect=r.Invalid('LEGACY_ENFORCE_EXIT')),self.assertRaises(r.Invalid):r.stamp(c,'success')
        self.assertFalse(c.stamp.exists())
        reader=r.Reader();reader.anchors['r87']='a'*64
        for code in (0,2,True):
            with self.assertRaises(r.Invalid):r.checkpoint_value(c,reader,dict(exit=code,stdout_sha256='a'*64),'success')
    def test_18_atomic_mapping_negative_controls(self):
        c=self.context();base=local_baseline(c);ids=self.p.IDS
        for wrong in (ids[:-1],ids+[ids[0]],ids[:-1]+['runtime.tests.test_effectwitness_pge_r72.BudgetTests.'+self.p.EXCLUDED[-1]]):
            with self.assertRaises(r.Invalid):r.derive(base,wrong,{},c)
        for k,value in [('route','PORTABLE'),('effective_actual','SKIP'),('required',False),('source_lane','RPF86_DEDICATED')]:
            b=copy.deepcopy(base);next(x for x in b['effective_required']['methods'] if x['id']==ids[0].removeprefix('runtime.tests.'))[k]=value
            with self.assertRaises(r.Invalid):r.derive(b,ids,{},c)
        fallback=r.derive(base,ids,{},c,'DENIED');self.assertFalse(fallback['new_admitted']);self.assertEqual(fallback['unavailable_remaining'],534)
    def test_baseline_invalid_is_not_fallback_success(self):
        c=self.context();base=local_baseline(c)
        for k,value in [('run_id','wrong'),('commit','b'*40),('evidence_kind','HOSTED_SAME_RUN_PROCESS_RECEIPTS')]:
            with self.assertRaises(r.Invalid):r.validate_baseline(base|{k:value},c)
        b=copy.deepcopy(base);b['effective_required']['methods'].pop()
        with self.assertRaises(r.Invalid):r.validate_baseline(b,c)
        c.root.mkdir();write(c.r87,base|{'run_id':'wrong'})
        with self.assertRaises(r.Invalid):r.assess_value(c)
    def test_missing_private_evidence_atomically_keeps_534(self):
        c=self.context();c.root.mkdir();write(c.r87,local_baseline(c));r.stamp(c,'success')
        v=r.assess_value(c);self.assertEqual(v['unavailable_remaining'],534);self.assertFalse(v['new_admitted']);self.assertTrue(v['not_admitted'])
    def test_source_and_public_and_database_tampering(self):
        # Each counterexample is a distinct fresh fixture; never overwrite a
        # real receipt/Run. Pure report mutations use original pinned validator.
        c,n,nr,v,vr=self.fixture();work=c.r88/'native/work';journal=(c.r88/'native/journal.jsonl').read_bytes()
        changes=[lambda x:x['guard']['denied'].update(TEST=1),lambda x:x['states'].pop(self.p.IDS[0]),lambda x:x['ids'].append(self.p.IDS[0]),lambda x:x.update(workspace_contract_bytes_historically_identical=True),lambda x:x.update(source_level='INDEPENDENT_ISSUER'),lambda x:x['resources'].update(provider=1),lambda x:x.update(source={}),lambda x:x.update(tests_run=True),lambda x:x['manifest'][0].update(sha256='0'*64)]
        for change in changes:
            report=copy.deepcopy(n);change(report)
            with self.assertRaises((r.Invalid,self.p.Invalid)):self.p.validate_native(report,nr,self.source,work,journal)
        for key,value in [('pid',True),('exit',1),('timeout',True),('truncated',True),('drain_joined',False),('end_ns',1)]:
            with self.assertRaises(self.p.Invalid):self.p.validate_native(n,nr|{key:value},self.source,work,journal)
        for bad in [journal[:-1],b'\n'.join(journal.splitlines()[:-1])+b'\n',journal.replace(b'"PASS"',b'"SKIP"',1)]:
            with self.assertRaises(self.p.Invalid):self.p.read_journal(bad,self.source['harness_lf_sha256'],nr['pid'])
    def test_reader_escapes_reparse_and_oversize_rejected(self):
        reader=r.Reader();owner=self.root
        with self.assertRaises(r.Invalid):reader.read(r.ROOT/'.local/rpf-old/forbidden',owner,'old')
        target=owner/('target-'+uuid.uuid4().hex);target.mkdir();link=owner/('link-'+uuid.uuid4().hex)
        if os.name=='nt':
            import _winapi
            _winapi.CreateJunction(str(target),str(link))
        else:os.symlink(target,link,target_is_directory=True)
        with self.assertRaises(r.Invalid):reader.read(link/'file',owner,'reparse')
        p=owner/('large-'+uuid.uuid4().hex);raw_write(p,b'1234')
        with self.assertRaises(r.Invalid):reader.read(p,owner,'size',limit=3)
    def test_cli_synthetic_assess_enforce_and_overwrite(self):
        c,*_=self.fixture();args=['--run-id',c.run,'--attempt',c.attempt,'--commit',c.commit,'--synthetic','--fixture-root',str(c.root)]
        observed=[]
        for command in ('assess','enforce','assess'):
            p=subprocess.run([sys.executable,'-B',str(r.SELF),command,*args],capture_output=True,timeout=60);observed.append(p.returncode)
        self.assertEqual(observed,[0,1,2]);v=r.strict(c.output.read_bytes());self.assertEqual(v['unavailable_remaining'],516);self.assertEqual(v['evidence_kind'],'LOCAL_SYNTHETIC_CONTROL_ONLY')
        index=Path(os.environ['RPF89_CONTROL_RECEIPT_INDEX']) if os.environ.get('RPF89_CONTROL_RECEIPT_INDEX') else self.root/'cli-case-index.json'
        self.assertTrue(index.is_relative_to(self.owner));write(index,dict(case=c.root.relative_to(self.owner).as_posix(),source_sha256=r.sha(r.SELF.read_bytes()),test_source_sha256=r.sha(Path(__file__).read_bytes()),observed_exits=observed))
    def test_context_identity_and_old_path_rejected(self):
        for commit in ('bad','0'*40):
            with self.assertRaises(r.Invalid):r.Context('local','1',commit,True,self.root/'case')
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}),self.assertRaises(r.Invalid):r.Context('1','1',self.commit,True,self.root/'case')
        with self.assertRaises(r.Invalid):r.Context('local','1',self.commit,True,r.ROOT/'.local/rpf-old/forbidden')
    def test_workflow_only_authorized_delta_and_two_live_barriers(self):
        raw=(r.ROOT/'.github/workflows/release-gate.yml').read_bytes();base=r.git('cat-file','blob',r.PINS['.github/workflows/release-gate.yml']);r.workflow_source(raw,base)
        with self.assertRaises(r.Invalid):r.workflow_source(raw.replace(b'timeout-minutes: 35',b'timeout-minutes: 90'),base)
        text=raw.decode();names=['Reconcile admitted RPF-86 required methods','Record verified RPF-87 post-completion boundary','Run RPF-88 R72 fresh-owner cohort pilot','Reconcile admitted RPF-88 R72 required methods','Enforce all required Runtime coverage','Enforce RPF-89 derived required coverage']
        self.assertEqual([text.index(n) for n in names],sorted(text.index(n) for n in names))
        self.assertIn('RPF87_STEP_OUTCOME: ${{ steps.rpf87_assess.outcome }}',text)
        self.assertIn('      - name: Enforce RPF-89 derived required coverage\n        if: ${{ always() }}',text)
        self.assertIn('      - name: Enforce all required Runtime coverage\n        if: ${{ always() }}',text)
        for mode in ('stamp','assess','enforce'):self.assertEqual(text.count('          python -B ci/reconcile-rpf88-required-coverage.py '+mode+' '),1)
    def cloned_control(self,source,mutate):
        # Clone only this task's synthetic protocol fixture, never a real Run.
        c=self.context();files={}
        for folder,dirs,names in os.walk(source.root):
            for n in names:
                p=Path(folder)/n;files[p.relative_to(source.root).as_posix()]=p.read_bytes()
        objects={n:r.strict(b) for n,b in files.items() if n.endswith('.json')}
        objects['r88/native/child-result.json']['physical_owner']=(c.r88/'native/work').relative_to(r.ROOT).as_posix()
        mutate(objects,files)
        nr=objects['r88/native/launch-receipt.json'];n=objects['r88/native/child-result.json'];v=objects['r88/verify/verification.json'];vr=objects['r88/verify/launch-receipt.json'];result=objects['r88/result.json']
        nr['report_sha256']=r.sha(r.canonical(n)+b'\n');v['native_report_sha256']=nr['report_sha256'];vr['report_sha256']=r.sha(r.canonical(v)+b'\n')
        result.update(native_receipt=nr,verify_receipt=vr,native_report_sha256=nr['report_sha256'],verification_sha256=vr['report_sha256'])
        objects['r88/public-result.json'].update(native_report_sha256=nr['report_sha256'],verification_sha256=vr['report_sha256'])
        for name,obj in objects.items():files[name]=r.canonical(obj)+b'\n'
        for name,b in files.items():raw_write(c.root/name,b)
        (c.r88/'native/pycache').mkdir(parents=True,exist_ok=True)
        return self.context(c.root)
    def test_integrated_public_verifier_and_reanchored_listing_reject(self):
        original,*_=self.fixture()
        def badpublic(objects,files):objects['r88/public-result.json']['status']='FORGED_PASS'
        def badverify(objects,files):objects['r88/verify/verification.json']['original_tests_rerun']=True
        def badlisting(objects,files):
            name='r88/native/journal.jsonl';frames=[r.strict(x) for x in files[name].splitlines()];frames[1]['data']['phase']='METHODS';prev=None;raw=[]
            for f in frames:
                f['previous']=prev;b=r.canonical(f)+b'\n';prev=r.sha(b);raw.append(b)
            files[name]=b''.join(raw)
        for change in (badpublic,badverify,badlisting):
            c=self.cloned_control(original,change);v=r.assess_value(c);self.assertEqual(v['unavailable_remaining'],534);self.assertFalse(v['new_admitted']);self.assertTrue(v['not_admitted'])
    def test_physical_database_copy_and_corruption_reject(self):
        original,*_=self.fixture()
        def copydb(objects,files):
            n=objects['r88/native/child-result.json'];dbs=[x for x in n['manifest'] if x['path'].endswith('/orders.sqlite3')];first='r88/native/work/'+dbs[0]['path'];second='r88/native/work/'+dbs[1]['path'];files[second]=files[first];dbs[1]['sha256']=r.sha(files[second]);dbs[1]['bytes']=len(files[second])
            v=objects['r88/verify/verification.json'];v['manifest_sha256']=r.sha(r.canonical(n['manifest']));v['databases'][1]['sha256']=dbs[1]['sha256']
        def corruptdb(objects,files):
            name=next(n for n in files if n.endswith('orders.sqlite3'));files[name]=b'NOT_SQLITE'
        for change in (copydb,corruptdb):
            c=self.cloned_control(original,change);v=r.assess_value(c);self.assertEqual(v['unavailable_remaining'],534);self.assertFalse(v['new_admitted'])
    def test_missing_checkpoint_and_missing_native_reject(self):
        c=self.context();c.root.mkdir();write(c.r87,local_baseline(c));v=r.assess_value(c);self.assertFalse(v['new_admitted']);self.assertEqual(v['unavailable_remaining'],534)
        r.stamp(c,'success');write(c.r88/'public-result.json',{'status':'PASS'});v=r.assess_value(c);self.assertFalse(v['new_admitted']);self.assertEqual(v['unavailable_remaining'],534)
    def test_reanchored_unknown_wal_write_and_external_manifest_reject(self):
        c=self.context();root=c.root/'work';run='rpf72-'+'a'*16;p=root/'rpf72'/run/'wal.jsonl';events=[dict(kind='OWNER',context_sha256='a'*64),dict(kind='RESULT',ticket='sqlite_refund-1',status='UNKNOWN'),dict(kind='RESERVE',resource='sqlite_refund',ticket='sqlite_refund-2')];raw=[];prev=None
        for i,e in enumerate(events):
            f=dict(seq=i,previous=prev,event=e|dict(session_id=run,clock=100+i));f['sha256']=r.sha(r.canonical(f));prev=r.sha(r.canonical(f));raw.append(r.canonical(f)+b'\n')
        b=b''.join(raw);raw_write(p,b);row=dict(path=p.relative_to(root).as_posix(),bytes=len(b),sha256=r.sha(b))
        with self.assertRaises(r.Invalid):r.manifest_read(r.Reader(),root,[row],c.root)
        with self.assertRaises(r.Invalid):r.manifest_read(r.Reader(),root,[row|{'path':'../outside'}],c.root)
    def test_output_noncanonical_extra_fields_and_exclusive(self):
        c=self.context();c.root.mkdir();p=c.output;r.write_exclusive(p,{'a':1})
        with self.assertRaises(FileExistsError):r.write_exclusive(p,{'a':2})
        with self.assertRaises(r.Invalid):r.fields({'a':1,'extra':2},{'a'})
    def test_pinned_neighbor_strict_functions_without_runtime(self):
        for module in (r.load_pinned(r.R87),self.p):
            with self.assertRaises(ValueError):module.strict(b'{"a":1,"a":2}')
        self.assertNotIn('runtime.tests.test_effectwitness_pge_r72',sys.modules)
    def test_legacy_host_dispatch_checks_actual_exit_not_pass_text(self):
        c=self.context();c.root.mkdir();base=local_baseline(c);base['evidence_kind']='HOSTED_SAME_RUN_PROCESS_RECEIPTS';write(c.r87,base);c.synthetic=False
        calls=[]
        def main(args):
            calls.append(args);print('RELEASE_BLOCKED_BY_REQUIRED_COVERAGE; unavailable_required=534; admitted_dedicated=5; NO_RELEASE/NO_DEPLOY');return 1
        # Explicit dispatch model only: no hosted claim or fake actual run.
        fake=type('DispatchControl',(),{'Reader':type('UnusedReader',(),{}),'main':staticmethod(main)})
        with patch.object(r,'load_pinned',return_value=fake):
            got,receipt=r.legacy_revalidate(c,r.Reader());self.assertEqual(receipt['exit'],1);self.assertEqual(calls[0][0],'enforce');self.assertIn('--ledger',calls[0]);self.assertIn(str(c.r87),calls[0])
        for code in (0,2):
            fake.main=staticmethod(lambda args,k=code:k)
            with patch.object(r,'load_pinned',return_value=fake),self.assertRaises(r.Invalid):r.legacy_revalidate(c,r.Reader())
    def test_manifest_extra_file_and_journal_false_start_reanchored(self):
        c,n,nr,v,vr=self.fixture();work=c.r88/'native/work';raw_write(work/'unlisted-file',b'controlled-extra')
        with self.assertRaises(r.Invalid):r.manifest_read(r.Reader(),work,n['manifest'],c.r88)
        frames=[r.strict(line) for line in (c.r88/'native/journal.jsonl').read_bytes().splitlines()];frames[6]['data']['id']=self.p.IDS[1];previous=None;raw=[]
        for f in frames:
            f['previous']=previous;b=r.canonical(f)+b'\n';previous=r.sha(b);raw.append(b)
        with self.assertRaises(self.p.Invalid):self.p.read_journal(b''.join(raw),self.source['harness_lf_sha256'],nr['pid'])
    def test_readonly_sqlite_uri_admission_precedes_native_connect(self):
        allowed={self.root/'owned.sqlite3'};uri=next(iter(allowed)).as_uri()+'?mode=ro'
        bad=[(':memory:',{'uri':True}),('relative.sqlite3',{}),(uri.replace('mode=ro','mode=rw'),{'uri':True}),(uri+'&mode=ro',{'uri':True}),(uri,{'uri':False}),(uri,{'uri':1}),(uri,{'uri':True,'timeout':1}),((r.ROOT/'.local/rpf-old/forbidden.sqlite3').as_uri()+'?mode=ro',{'uri':True})]
        with patch.object(r.sqlite3,'connect',side_effect=AssertionError('NO_NATIVE_SQLITE')):
            for target,kw in bad:
                with self.assertRaises(r.Invalid):r.readonly_connect(allowed,target,**kw)
        marker=object()
        with patch.object(r.sqlite3,'connect',return_value=marker) as original:
            self.assertIs(r.readonly_connect(allowed,uri,uri=True),marker);original.assert_called_once_with(uri,uri=True)
    def test_actual_enforce_rejects_noncanonical_and_extra_derived_fields(self):
        original,*_=self.fixture()
        for bad in ('noncanonical','extra','false-count'):
            c=self.cloned_control(original,lambda objects,files:None);value=r.assess_value(c);self.assertEqual(value['unavailable_remaining'],516)
            if bad=='extra':value['extra']=True
            if bad=='false-count':value['unavailable_remaining']=0
            raw=(json.dumps(value,indent=2).encode()+b'\n') if bad=='noncanonical' else r.canonical(value)+b'\n';raw_write(c.output,raw)
            args=['enforce','--run-id',c.run,'--attempt',c.attempt,'--commit',c.commit,'--synthetic','--fixture-root',str(c.root)]
            p=subprocess.run([sys.executable,'-B',str(r.SELF),*args],capture_output=True,timeout=60);self.assertEqual(p.returncode,2)
    def test_hardlink_is_rejected_without_external_target_probe(self):
        folder=self.root/uuid.uuid4().hex;folder.mkdir();p=folder/'owned-file';raw_write(p,b'controlled');link=folder/'hardlink';os.link(p,link)
        with self.assertRaises(r.Invalid):r.Reader().read(link,folder,'link')

if __name__=='__main__':unittest.main(verbosity=2)

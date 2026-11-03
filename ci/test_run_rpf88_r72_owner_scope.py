"""RPF88 controls; never run original BudgetTests in this suite."""
import ast
import copy
from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import unittest
import uuid
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('rpf88_harness',Path(__file__).with_name('run-rpf88-r72-owner-scope.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class OwnerScopeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner=r.task_root();cls.root=cls.owner/('controls-'+uuid.uuid4().hex);cls.root.mkdir();cls.source=r.identity()
    def folder(self):
        p=self.root/uuid.uuid4().hex;p.mkdir();return p
    def test_scoped_listing_negative_provenance(self):
        g=r.Guard(self.folder());g.phase='MODULE_IMPORT'
        for event,p in [('os.listdir',r.ROOT),('os.scandir',r.ROOT),('os.listdir',r.ROOT/'runtime'),('os.listdir',r.ROOT/'docs'),('os.listdir',r.ROOT/'.local')]:
            with self.assertRaises(PermissionError):g.listing(event,p)
        self.assertTrue(all(x['decision']=='DENY' for x in g.listing_events))
        self.assertTrue(all(x['caller_kind']=='OTHER' for x in g.listing_events))
        g.phase='METHODS'
        with self.assertRaises(PermissionError):g.listing('os.listdir',r.ROOT)
        self.assertEqual(g.listing_events[-1]['phase'],'METHODS')
    def test_inventory_and_ast_pins(self):
        inv=self.source['inventory'];self.assertEqual(len(inv['method_ast']),25);self.assertEqual(len(r.IDS),18);self.assertEqual(len(r.EXCLUDED),7)
        self.assertTrue(set(r.NAMES).isdisjoint(r.EXCLUDED));self.assertEqual(self.source['dedicated'],24);self.assertEqual(self.source['windows_native'],1)
        self.assertNotIn(r.MODULE,sys.modules)
        raw=(r.ROOT/r.TARGET).read_bytes()
        for names in (r.NAMES[:-1],r.NAMES+r.EXCLUDED[:1],r.NAMES[::-1]):
            with self.assertRaises(r.Invalid):r.discover(raw,names)
        for mutated in (raw.replace(b'def test_immutable_policy_strict_identity',b'def renamed_identity'),raw.replace(b'class BudgetTests',b'class Other')):
            with self.assertRaises(r.Invalid):r.discover(mutated)
        with patch.dict(r.PINS,{r.TARGET:{'blob':'0'*40,'lf':'0'*64}}):
            with self.assertRaises(r.Invalid):r.identity()
    def test_descriptor_only_adapter_restore(self):
        work=self.folder();new=r.adapter_property(work)
        class Dummy:
            run_id='rpf72-'+'a'*16
            @property
            def root(self):raise AssertionError('old root must not be queried')
        before=Dummy.__dict__['root']
        with patch.object(Dummy,'root',new):
            self.assertEqual(Dummy().root,work/'rpf72'/Dummy.run_id)
            with patch.object(Dummy,'run_id','../escape'):
                with self.assertRaises(r.Invalid):Dummy().root
        self.assertIs(Dummy.__dict__['root'],before)
    def test_lexical_denial_before_metadata(self):
        owner=self.folder();g=r.Guard(owner);calls=[]
        g.raw_lstat=lambda p: calls.append(str(p)) or (_ for _ in ()).throw(AssertionError('forbidden metadata'))
        targets=[r.ROOT/'.local/rpf-72/tests/old',self.owner.parent/'other-owner',r.ROOT/'docs/reviews/forbidden',r.ROOT/'README.md',owner/'../escape',Path('relative'),r.ROOT/'runtime/__pycache__/old.pyc']
        for p in targets:
            with self.assertRaises(PermissionError):g.check(p)
        with self.assertRaises(PermissionError):g.check(r.ROOT/'runtime',listing=True)
        self.assertFalse(calls)
    def test_real_reparse_denied(self):
        root=self.folder();target=root/'target';target.mkdir();link=root/'link'
        if os.name=='nt':
            import _winapi
            _winapi.CreateJunction(str(target),str(link))
        else:os.symlink(target,link,target_is_directory=True)
        with self.assertRaises(r.Invalid):r.owned(link/'file',root)
        with self.assertRaises(PermissionError):r.Guard(root).check(link/'file')
    def test_sqlite_validation_and_original_callable(self):
        owner=self.folder();work=owner/'work';p=work/'rpf72'/('rpf72-'+'a'*16)/'runs/run/business/orders.sqlite3';p.parent.mkdir(parents=True)
        g=r.Guard(owner);g.method=r.IDS[15];sql=r.SQLiteAdmission(g,work,sqlite3.connect)
        with closing(sql.connect(p,timeout=1)) as db:db.execute('CREATE TABLE truth(n)');db.execute('INSERT INTO truth VALUES(2500)');db.commit()
        with closing(sql.connect(p.as_uri()+'?mode=ro',uri=True)) as db:self.assertEqual(db.execute('SELECT n FROM truth').fetchall(),[(2500,)])
        self.assertEqual(len(sql.calls),2);self.assertTrue(all(x['original_forwarded'] for x in sql.calls));self.assertEqual([x['readonly'] for x in sql.calls],[False,True])
        for name,kw in [(':memory:',{}),('relative.sqlite3',{}),(r.ROOT/'.local/rpf-72/tests/old/orders.sqlite3',{}),(p.parent/'other.sqlite3',{}),(p.as_uri()+'?mode=rw',{'uri':True}),(p.as_uri()+'?mode=ro&mode=rw',{'uri':True}),(p.as_uri()+'?mode=ro#fragment',{'uri':True}),(p.as_uri()+'?mode=ro',{'uri':False}),(p,{'uri':True}),(p,{'uri':1})]:
            with self.assertRaises((r.Invalid,PermissionError)):sql.connect(name,**kw)
        self.assertEqual(len(sql.calls),2)
    def test_guard_physical_process_controls(self):
        owner=self.folder();code='''import importlib.util,sys,pathlib,os,socket,subprocess,sqlite3,json
spec=importlib.util.spec_from_file_location('guard',sys.argv[1]);r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
owner=pathlib.Path(sys.argv[2]);g=r.Guard(owner);g.install();cases=[lambda:open(r.ROOT/'.local/rpf-72/tests/forbidden','rb'),lambda:os.stat(r.ROOT/'.local/rpf-72/tests/forbidden'),lambda:list((r.ROOT/'runtime').iterdir()),lambda:socket.getaddrinfo('example.invalid',443),lambda:subprocess.Popen([sys.executable,'-c','raise SystemExit(0)']),lambda:sqlite3.connect(':memory:')]
for f in cases:
 try:f()
 except PermissionError:pass
 else:raise AssertionError('not denied')
print(json.dumps({'denied':dict(g.denied),'cases':len(cases)}))'''
        p=subprocess.run([sys.executable,'-B','-c',code,str(r.SELF),str(owner)],cwd=r.ROOT,env=r.environment(owner),capture_output=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace'));j=json.loads(p.stdout);self.assertEqual(sum(j['denied'].values()),6)
        with (owner/'control-process.json').open('xb') as f:f.write(r.canonical(dict(pid_scope='separate_synthetic_control_only',exit=p.returncode,stdout_sha256=r.sha(p.stdout),stderr_sha256=r.sha(p.stderr))))
    def journal(self,pid=123):
        frames=[];prev=None;t=100
        for kind,data in [('INIT',dict(ids=r.IDS))]+[(kind,d) for i in r.IDS for kind,d in [('STARTED',dict(id=i)),('STOP',dict(id=i,actual='PASS'))]]+[('TERMINAL',dict(status='PASS'))]:
            t+=1;f=dict(seq=len(frames),previous=prev,pid=pid,time_ns=t,source=self.source['harness_lf_sha256'],kind=kind,data=data);b=r.canonical(f)+b'\n';frames.append(b);prev=r.sha(b)
        return b''.join(frames)
    def test_source_finder_denial_explains_import_boundary(self):
        # Finder only: no runtime package or original target code executes.
        owner=self.folder();code='''import importlib.util,importlib.machinery,sys,pathlib,json
spec=importlib.util.spec_from_file_location('h',sys.argv[1]);r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
g=r.Guard(pathlib.Path(sys.argv[2]));g.install();finder=importlib.machinery.FileFinder(str(r.ROOT),(importlib.machinery.SourceFileLoader,importlib.machinery.SOURCE_SUFFIXES));value=finder.find_spec('runtime');assert value is None;assert 'runtime' not in sys.modules
assert g.events==[dict(reason='IMPORT_LISTING_DENIED',operation='os.listdir',method=None,target_class='public_source_parent',status='DENIED_BEFORE_IO')];print(json.dumps(g.projection()))'''
        z=subprocess.run([sys.executable,'-B','-c',code,str(r.SELF),str(owner)],cwd=r.ROOT,env=r.environment(owner),capture_output=True,timeout=30)
        self.assertEqual(z.returncode,0,z.stderr.decode(errors='replace'))
        with (owner/'finder-denial.json').open('xb') as f:f.write(z.stdout);f.flush();os.fsync(f.fileno())
    def test_journal_strict_false_greens(self):
        raw=self.journal();j=r.read_journal(raw,self.source['harness_lf_sha256'],123);self.assertEqual(len(j['methods']),18)
        variants=[raw[:-1],b'\n'.join(raw.splitlines()[:-1])+b'\n',raw.replace(b'"PASS"',b'"SKIP"',1),raw.replace(b'"pid":123',b'"pid":true',1),raw.replace(b'"seq":1,',b'"seq":2,',1)]
        for v in variants:
            with self.assertRaises(r.Invalid):r.read_journal(v,self.source['harness_lf_sha256'],123)
        frames=[json.loads(x) for x in raw.splitlines()];frames.insert(-1,dict(frames[0],kind='DENIED',data=dict(reason='TEST_DENIAL',method=r.IDS[0])))
        repaired=[];prev=None
        for i,f in enumerate(frames):f.update(seq=i,time_ns=101+i,previous=prev);b=r.canonical(f)+b'\n';repaired.append(b);prev=r.sha(b)
        with self.assertRaises(r.Invalid):r.read_journal(b''.join(repaired),self.source['harness_lf_sha256'],123)
    def test_receipt_schema_time_and_resources(self):
        v=dict(mode='native',pid=123,exit=0,timeout=False,truncated=False,child_exited=True,drain_joined=True,start_ns=1,end_ns=100,stdout_sha256='a'*64,report_sha256='b'*64);r.validate_receipt(v,'native')
        for k,value in [('pid',True),('start_ns',True),('exit',False),('end_ns',0),('timeout',1),('report_sha256','bad'),('extra',1)]:
            with self.assertRaises(r.Invalid):r.validate_receipt(dict(v,**{k:value}),'native')
    def protocol(self):
        # Explicit synthetic control. No original BudgetTests object imported/run.
        owner=self.folder();work=owner/'work';work.mkdir();calls=[]
        for index in (15,16):
            p=work/'rpf72'/('rpf72-'+format(index,'016x'))/'runs/run/business/orders.sqlite3';p.parent.mkdir(parents=True)
            with closing(sqlite3.connect(p)) as db:
                db.execute('CREATE TABLE refunds(amount_minor,status)');db.execute("INSERT INTO refunds VALUES(2500,'COMMITTED')")
                db.execute('CREATE TABLE orders(refunded_minor,status)');db.execute("INSERT INTO orders VALUES(2500,'REFUNDED')");db.commit()
            calls += [dict(method=r.IDS[index],target=p.relative_to(work).as_posix(),readonly=b,original_forwarded=True,start_ns=120,end_ns=121) for b in (False,True)]
        report=dict(schema='rpf88-native-v1',status='PASS',ids=r.IDS,states=dict.fromkeys(r.IDS,'PASS'),tests_run=18,source=self.source,pid=123,start_ns=50,end_ns=200,guard=dict(denied={},denial_events=[],observed={'read':1,'write':1},metadata_intercepts=['os.stat','os.lstat','Path.resolve'],native_boundary='SQLITE_CONNECT_TARGET_ADMISSION',arbitrary_native_syscalls='UNAVAILABLE_NOT_KERNEL_SANDBOX'),sqlite_calls=calls,sqlite_module_alias=True,sqlite_wrapper_restored=True,owner_descriptor_restored=True,original_source_unchanged=True,original_test_assertions_unchanged=True,test_only_owner_scope_substitution=True,physical_workspace_fresh=True,source_level='SYNTHETIC_OFFLINE_TEST',logical_owner='rpf-72',workspace_contract_bytes_historically_identical=False,physical_owner=work.relative_to(r.ROOT).as_posix(),manifest=r.manifest(work),cache_empty=True,error=None,resources=r.RESOURCES)
        receipt=dict(mode='native',pid=123,exit=0,timeout=False,truncated=False,child_exited=True,drain_joined=True,start_ns=1,end_ns=300,stdout_sha256='a'*64,report_sha256='b'*64)
        return report,receipt,work,self.journal()
    def test_physical_validation_and_false_green_matrix(self):
        report,receipt,work,journal=self.protocol();result=r.validate_native(report,receipt,self.source,work,journal);self.assertEqual(len(result['databases']),2)
        changes=[lambda x:x.update(tests_run=17),lambda x:x['ids'].pop(),lambda x:x['states'].update({r.IDS[0]:'SKIP'}),lambda x:x.update(owner_descriptor_restored=False),lambda x:x.update(sqlite_wrapper_restored=False),lambda x:x.update(sqlite_calls=[]),lambda x:x['guard']['denied'].update(OLD_OWNER=1),lambda x:x.update(source={}),lambda x:x.update(pid=True),lambda x:x.update(physical_owner='old'),lambda x:x.update(original_source_unchanged=False),lambda x:x.update(cache_empty=False),lambda x:x['manifest'][0].update(sha256='0'*64),lambda x:x['sqlite_calls'][0].update(target='../orders.sqlite3'),lambda x:x['sqlite_calls'][0].update(original_forwarded=False),lambda x:x['resources'].update(provider=True),lambda x:x.update(extra=1)]
        for change in changes:
            x=copy.deepcopy(report);change(x)
            with self.assertRaises(r.Invalid):r.validate_native(x,receipt,self.source,work,journal)
        for k,v in [('exit',1),('timeout',True),('truncated',True),('child_exited',False),('drain_joined',False),('pid',456),('end_ns',100)]:
            with self.assertRaises(r.Invalid):r.validate_native(report,dict(receipt,**{k:v}),self.source,work,journal)
        for b in [journal[:-1],journal.replace(b'"PASS"',b'"FAIL"',1)]:
            with self.assertRaises(r.Invalid):r.validate_native(report,receipt,self.source,work,b)
    def test_strict_json_and_exclusive_output(self):
        for b in [b'{} '*3000000,b'',b'{"a":1,"a":2}',b'{"a":NaN}']:
            with self.assertRaises((r.Invalid,ValueError)):r.strict(b)
        p=self.folder()/'result.json';r.write(p,{'a':1})
        with self.assertRaises(FileExistsError):r.write(p,{'a':2})
        self.assertEqual(r.strict(p.read_bytes()),{'a':1})
    def test_projection_has_no_private_fields_or_promotion(self):
        p=r.public_projection(dict(status='PASS',states=dict.fromkeys(r.IDS,'PASS'),source_unchanged=True,guard_denied_count=0,native_report_sha256='a'*64,verification_sha256='b'*64))
        self.assertTrue(p['eligible_for_future_reconciliation']);self.assertFalse(p['formal_coverage_promoted']);self.assertEqual(p['formal_unavailable_remaining'],534)
        b=r.canonical(p);self.assertNotIn(str(self.owner).encode(),b);self.assertNotIn(b'workspace_path',b)
        self.assertFalse(p['release_eligible']);self.assertEqual(len(p['ids']),18)
    def test_original_workflow_and_neighbor_pure_controls(self):
        # Pure functions only, no identity()/native()/test fixture setup from RPF86.
        for name in ['run-rpf86-owner-admission.py','reconcile-rpf86-required-coverage.py']:
            file=r.ROOT/'ci'/name;spec=importlib.util.spec_from_file_location('pure_'+name,file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
            with self.assertRaises((ValueError,TypeError)):m.strict(b'{"x":1,"x":2}')
        self.assertNotIn(r.MODULE,sys.modules)
        raw=(r.ROOT/'.github/workflows/release-gate.yml').read_bytes()
        self.assertIn(b'timeout-minutes: 35',raw);self.assertIn(b'Enforce all required Runtime coverage',raw)

if __name__=='__main__':unittest.main(verbosity=2)

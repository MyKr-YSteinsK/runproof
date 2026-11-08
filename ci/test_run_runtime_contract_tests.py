"""Executable counterexamples for the versioned isolation router (stdlib only)."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
import subprocess
import time
import hashlib

spec=importlib.util.spec_from_file_location('rpf82_router',Path(__file__).with_name('run-runtime-contract-tests.py'))
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class DirFdSafetyTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix' and Path('/proc/self/fd').is_dir(), 'requires Linux procfs and directory fd')
    def test_real_dirfd_owner_and_escape(self):
        root = r.OWNER / ('rpf98-rev3-' + uuid.uuid4().hex)
        child = root / 'child'; outside = root / 'outside'
        child.mkdir(parents=True); outside.mkdir()
        sentinel = outside / 'sentinel'; sentinel.write_bytes(b'unchanged')
        (child / 'file').write_bytes(b'ok'); (child / 'nested').mkdir()
        (child / 'escape').symlink_to(outside, target_is_directory=True)
        code = '''import importlib.util,os,sys,pathlib,tempfile
s=importlib.util.spec_from_file_location("r",sys.argv[1]);r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
child=pathlib.Path(sys.argv[2]);outside=pathlib.Path(sys.argv[3])
fd=os.open(child,os.O_RDONLY);bad=os.open(outside,os.O_RDONLY)
r.guard(child)
os.unlink("file",dir_fd=fd);os.rmdir("nested",dir_fd=fd)
with tempfile.TemporaryDirectory(dir=child) as t:
 pathlib.Path(t,"inner").write_bytes(b"x")
for name,descriptor in [("sentinel",bad),("../outside/sentinel",fd),("escape/sentinel",fd),("x",999999)]:
 try: os.unlink(name,dir_fd=descriptor)
 except PermissionError: pass
 else: raise AssertionError("escape accepted")
os.close(fd);os.close(bad)
'''
        process = subprocess.run([sys.executable, '-B', '-c', code, str(r.SELF), str(child), str(outside)],
                                 cwd=r.ROOT, env=r.child_environment(child), capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors='replace'))
        self.assertEqual(sentinel.read_bytes(), b'unchanged')


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.matrix=r.strict(r.MATRIX.read_bytes())
    def reject(self, fn):
        m=copy.deepcopy(self.matrix);fn(m)
        with self.assertRaises((r.Invalid,ValueError,TypeError)):
            r.validate_matrix(m,r.tracked_modules())
    def folder(self,label):return r.OWNER/('unit-'+label+'-'+uuid.uuid4().hex)
    def test_inventory_is_exact_tracked_set(self):
        r.validate_matrix(self.matrix,r.tracked_modules())
    def test_omitted_module_fails(self):self.reject(lambda m:m['modules'].pop())
    def test_duplicate_module_fails(self):self.reject(lambda m:m['modules'].append(m['modules'][0]))
    def test_added_tracked_module_fails(self):
        with self.assertRaises(r.Invalid):r.validate_matrix(self.matrix,r.tracked_modules()+['runtime/tests/test_new.py'])
    def test_source_drift_fails(self):self.reject(lambda m:m['modules'][0].update(source_sha256='0'*64))
    def test_unknown_route_fails(self):
        self.reject(lambda m:next(x for x in m['modules'] if x['rules'])['rules'][0].update(route='PASS'))
    def test_false_prerequisite_fails(self):
        self.reject(lambda m:next(x for x in m['modules'] if x['rules'])['rules'][0]['evidence'].update(marker='UNOBSERVED_FAKE_RECEIPT'))
    def test_weakened_coverage_fails(self):self.reject(lambda m:m.update(required_coverage='PORTABLE_ONLY'))
    def test_duplicate_and_nonfinite_json_fail(self):
        for raw in ['{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}']:
            with self.subTest(raw=raw),self.assertRaises(r.Invalid):r.strict(raw)
    def test_wrong_schema_type_fails(self):
        for value in [[],None,True,{'schema':'other'}]:
            with self.assertRaises(r.Invalid):r.validate_matrix(value,[])
    def test_missing_overlap_unknown_method_fail(self):
        m=copy.deepcopy(self.matrix['modules'][0]);stem=Path(m['path']).stem
        ids=[stem+'.Unit.test_one'];rule=dict(selector='Unit',route='WINDOWS_NATIVE',reason='OS required',evidence={})
        m['rules']=[rule,dict(rule,selector='Unit.test_one')]
        with self.assertRaisesRegex(r.Invalid,'OVERLAP'):r.classify(m,ids)
        m['rules']=[dict(rule,selector='Unit.test_absent')]
        with self.assertRaisesRegex(r.Invalid,'UNKNOWN_RULE'):r.classify(m,ids)
        with self.assertRaises(r.Invalid):r.classify(dict(m,rules=[]),ids+ids)
        with self.assertRaises(r.Invalid):r.classify(dict(m,rules=[]),[])
    def test_known_defects_cannot_be_relabelled(self):
        for tid in r.KNOWN:
            m=dict(path='runtime/tests/'+tid.split('.')[0]+'.py',rules=[dict(selector='.'.join(tid.split('.')[1:]),route='DEDICATED_RUNNER',reason='fake')])
            with self.assertRaisesRegex(r.Invalid,'KNOWN_FAILURE_HIDDEN'):r.classify(m,[tid])
    def test_unavailable_is_never_skip_or_pass(self):
        m=dict(path='runtime/tests/test_unit.py',rules=[dict(selector='Win',route='WINDOWS_NATIVE',reason='Native OS unavailable')])
        rows=r.classify(m,['test_unit.Win.test_one'])
        self.assertFalse(rows[0]['executed']);self.assertEqual(rows[0]['actual'],'NOT_RUN');self.assertTrue(rows[0]['required'])
    def test_result_omission_duplication_and_false_pass_fail(self):
        tid='unit.C.test_one';good=dict(ids=[tid],results=[dict(id=tid,actual='PASS')],tests_run=1,successful=True,fixture_skips=[])
        self.assertEqual(r.reconcile([tid],good,0),good['results'])
        for mutate in [lambda v:v['results'].clear(),lambda v:v['ids'].append(tid),lambda v:v.update(tests_run=0),lambda v:v.update(successful=False),lambda v:v['results'][0].update(actual='UNAVAILABLE')]:
            v=copy.deepcopy(good);mutate(v)
            with self.assertRaises(r.Invalid):r.reconcile([tid],v,0)
        with self.assertRaises(r.Invalid):r.reconcile([tid],good,1)
    def test_fail_and_error_propagate(self):
        for actual in ['FAIL','ERROR']:
            v=dict(ids=['a'],results=[dict(id='a',actual=actual)],tests_run=1,successful=False,fixture_skips=[])
            self.assertEqual(r.reconcile(['a'],v,1)[0]['actual'],actual)
            with self.assertRaises(r.Invalid):r.reconcile(['a'],v,0)
    def test_real_class_skip_is_accounted_without_claiming_execution(self):
        v=dict(ids=['a'],results=[dict(id='a',actual='SKIP')],tests_run=0,successful=True,fixture_skips=['a'])
        self.assertEqual(r.reconcile(['a'],v,0)[0]['actual'],'SKIP')
        v['results'][0]['actual']='PASS'
        with self.assertRaises(r.Invalid):r.reconcile(['a'],v,0)
    def test_output_scope_rejects_legacy_and_escape(self):
        for path in [r.ROOT/'.local/rpf-60/x',r.OWNER/'..'/'escape',r.ROOT/'docs/x']:
            with self.assertRaises(r.Invalid):r.owned(path)
    def test_parent_has_no_runtime_test_import_or_audit_hook(self):
        tree=ast.parse(r.SELF.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):self.assertFalse((node.module or '').startswith(('runtime.tests','test_effectwitness')))
        self.assertFalse(any(name.startswith('test_effectwitness') for name in __import__('sys').modules))
    def test_environment_does_not_inherit_unlisted_values(self):
        folder=self.folder('env');env=r.child_environment(folder)
        self.assertEqual(set(env)-set(['PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','LANG','LC_ALL']),{'PYTHONDONTWRITEBYTECODE','PYTHONUTF8','TMP','TEMP','TMPDIR','HOME','USERPROFILE','RPF82_TEST_ROOT'})
    def test_real_audit_hook_then_unpolluted_sibling(self):
        a=self.folder('hook');x=r.launch(['--control','hook','--output',str(a)],a)
        self.assertEqual(x['exit'],0);self.assertFalse(x['timeout']);self.assertFalse(x['truncated'])
        data=r.strict((a/'result.json').read_bytes());self.assertEqual(data['guard_denied'],['subprocess.Popen','socket.connect']);self.assertTrue(data['actual_subprocess_denied'])
        b=self.folder('sibling');x=r.launch(['--control','sibling','--output',str(b)],b)
        self.assertEqual(x['exit'],0);self.assertEqual(r.strict((b/'result.json').read_bytes())['loopback_bytes'],5)
    def test_actual_crash_missing_result_timeout_and_truncation(self):
        for control in ['crash','missing','timeout','overflow']:
            folder=self.folder(control);rec=r.launch(['--control',control,'--output',str(folder)],folder,timeout=0.4 if control=='timeout' else 10)
            with self.subTest(control=control):
                self.assertFalse((folder/'result.json').exists())
                if control=='crash':self.assertEqual(rec['exit'],7)
                if control=='timeout':self.assertTrue(rec['timeout'])
                if control=='overflow':self.assertTrue(rec['truncated'])
    def test_rpf60_owner_paths_and_missing_parent(self):
        # This import is the test harness, not the router supervisor. No old root is read.
        from runtime.tests import test_effectwitness_lab_cross_domain as t
        folder=self.folder('r60');folder.mkdir()
        with r.r60_harness(t,folder):
            self.assertEqual(t._test_owner(str(folder)),folder)
            with self.assertRaises(ValueError):t._test_owner(str(r.ROOT/'.local/rpf-60'))
        from unittest.mock import patch
        with patch.object(t.c,'WORK',folder):
            with self.assertRaises(FileNotFoundError):t.core.Ledger(folder/'missing-parent'/'new',t.make_plan(),create=True)
            self.assertFalse((folder/'missing-parent').exists())

    def test_actual_r81_hidden_helper_routes_before_import(self):
        closure=r.validate_helper_registry(self.matrix)
        for name in ['test_injected_fsync_failure_stop','test_injected_write_failure_stop']:
            self.assertEqual(closure[name]['chain'],[name,'persist','Host'])
            self.assertTrue(closure[name]['owner_bound'])
        self.assertFalse(closure['test_strict_json']['owner_bound'])
        self.assertFalse(any(x.startswith(('test_effectwitness_pge_r81','runproof_runtime.effectwitness.pge_r81')) for x in __import__('sys').modules))
    def test_synthetic_hidden_work_helper_is_not_executed(self):
        source="""class T:
 def test_entry(self): self.helper()
 def helper(self):
  root=WORK/'sessions'
  root.mkdir()
"""
        result=r.helper_closure(source,'T',[],[])
        self.assertTrue(result['test_entry']['owner_bound'])
        self.assertEqual(result['test_entry']['chain'],['test_entry','helper','HIDDEN_OWNER_ROOT_MUTATION'])
    def test_benign_helper_stays_portable_and_runs(self):
        source="""class T:
 def test_entry(self): return self.helper()
 def helper(self): return 7
"""
        self.assertFalse(r.helper_closure(source,'T',[],[])['test_entry']['owner_bound'])
        class Benign:
            def test_entry(self):return self.helper()
            def helper(self):return 7
        self.assertEqual(Benign().test_entry(),7)
    def test_unknown_helper_and_external_call_reject(self):
        for source in ["class T:\n def test_entry(self):self.unknown()",
                       "class T:\n def test_entry(self):unknown()",
                       "class T:\n def test_entry(self):getattr(self,'hidden')()"]:
            with self.assertRaises(r.Invalid):r.helper_closure(source,'T',[],[])
    def test_recursive_or_duplicate_helper_is_ambiguous(self):
        for source in ["class T:\n def test_entry(self):self.helper()\n def helper(self):self.test_entry()",
                       "class T:\n def test_entry(self):pass\n def helper(self):pass\n def helper(self):pass"]:
            with self.assertRaises(r.Invalid):r.helper_closure(source,'T',[],[])
    def test_new_unregistered_helper_method_fails(self):
        m=copy.deepcopy(self.matrix);m['helper_registry']['method_ids'].pop()
        with self.assertRaisesRegex(r.Invalid,'UNREGISTERED_HELPER_METHOD'):r.validate_helper_registry(m)
    def test_owner_route_mask_and_dependency_drift_reject(self):
        m=copy.deepcopy(self.matrix)
        module=next(x for x in m['modules'] if x['path'].endswith('test_effectwitness_pge_r81.py'))
        module['rules']=[x for x in module['rules'] if not x['selector'].endswith('test_injected_write_failure_stop')]
        with self.assertRaisesRegex(r.Invalid,'HELPER_ROUTE_MISMATCH'):r.validate_helper_registry(m)
        m=copy.deepcopy(self.matrix);m['helper_registry']['dependencies'][0]['sha256']='0'*64
        with self.assertRaisesRegex(r.Invalid,'HELPER_DEPENDENCY_DRIFT'):r.validate_helper_registry(m)
    def test_pre_mkdir_and_open_events_denied_without_syscall(self):
        folder=self.folder('premkdir');rec=r.launch(['--control','premkdir','--output',str(folder)],folder)
        self.assertEqual(rec['exit'],0);self.assertFalse(rec['timeout'])
        self.assertEqual(r.strict((folder/'result.json').read_bytes()),{'denied':['os.mkdir','open'],'old_root_syscalls':0})
    def test_actual_exit_one_cannot_pass(self):
        folder=self.folder('exit1');rec=r.launch(['--control','exit1','--output',str(folder)],folder)
        self.assertEqual(rec['exit'],1);self.assertFalse((folder/'result.json').exists())
    def test_forged_owner_prerequisite_or_missing_dependency_rejects(self):
        for mutate in [lambda m:m['helper_registry']['owner_calls'].clear(),
                       lambda m:m['helper_registry']['approved_calls'].append('Host'),
                       lambda m:m['helper_registry']['dependencies'].pop()]:
            m=copy.deepcopy(self.matrix);mutate(m)
            with self.assertRaises(r.Invalid):r.validate_helper_registry(m)

    def test_required_historical_ids_are_exact_and_unique(self):
        values=r.required_inventory(r.tracked_modules())
        self.assertEqual(len(values),57)
        self.assertEqual(len({x for rows in values.values() for x in rows}),1232)
        with self.assertRaisesRegex(r.Invalid,'REQUIRED_MODULE_DRIFT'):
            r.required_inventory(r.tracked_modules()+['runtime/tests/test_extra.py'])

    def test_forged_skip_and_pass_need_real_progress_events(self):
        for actual in ('SKIP','PASS'):
            v=dict(ids=['a.C.test_one'],results=[dict(id='a.C.test_one',actual=actual)],tests_run=1,successful=True,fixture_skips=[])
            with self.assertRaises(r.Invalid):r.reconcile(v['ids'],v,0,[])
        v=dict(ids=['a.C.test_one'],results=[dict(id='a.C.test_one',actual='SKIP')],tests_run=0,successful=True,fixture_skips=['a.C.test_one'])
        with self.assertRaisesRegex(r.Invalid,'UNOBSERVED_RESULT'):r.reconcile(v['ids'],v,0,[])
        r.reconcile(v['ids'],v,0,[dict(id='setUpClass (a.C)',actual='SKIP')])

    def test_deadline_clamps_child_and_prevents_next_launch(self):
        folder=self.folder('deadline')
        rec=r.launch(['--control','timeout','--output',str(folder)],folder,deadline=time.monotonic()+.5)
        self.assertTrue(rec['timeout']);self.assertLessEqual(rec['timeout_limit_seconds'],.5)
        self.assertTrue(rec['child_exited']);self.assertTrue(rec['drain_joined'])
        other=self.folder('expired')
        with self.assertRaisesRegex(r.Invalid,'SUITE_DEADLINE'):
            r.launch(['--control','missing','--output',str(other)],other,deadline=time.monotonic()-1)
        self.assertFalse(other.exists())

    def test_r66_actual_historical_bytes_and_unchanged_guard(self):
        folder=self.folder('r66')
        rec=r.launch(['--control','r66','--output',str(folder)],folder)
        self.assertEqual(rec['exit'],0)
        value=r.strict((folder/'result.json').read_bytes())
        self.assertTrue(value['unique_replacement']);self.assertEqual(value['guard_negative_count'],5)
        self.assertFalse(value['old_source_executed'])

    def test_r66_wrong_blob_zero_two_tokens_and_child_drift_reject(self):
        old=subprocess.check_output(['git','cat-file','blob','677d957302476bb89b52dedb5ab047f2850bd686'],cwd=r.ROOT)
        child=subprocess.check_output(['git','cat-file','blob','b10e9bbc7d59fcab7b0dea6db9c214a27b0dce01'],cwd=r.ROOT)
        token=b'model_settings={"max_tokens": 256,'
        self.assertEqual(r.token_transform(old),child)
        for raw in (old.replace(token,b'no token'),old+token):
            with self.assertRaisesRegex(r.Invalid,'R66_TOKEN_COUNT'):r.token_transform(raw)
        current=(r.ROOT/'runtime/runproof_runtime/effectwitness/config_live_external.py').read_bytes()
        for a,b in ((current,child),(old+b'x',child),(old,child+b'x')):
            with self.assertRaises(r.Invalid):r.lineage_bytes(a,b)

    def test_rpf75_actual_socket_hook_is_not_only_a_callback(self):
        folder=self.folder('actual-hook');rec=r.launch(['--control','hook','--output',str(folder)],folder)
        self.assertEqual(rec['exit'],0)
        self.assertTrue(r.strict((folder/'result.json').read_bytes())['actual_socket_denied'])

    def test_guard_source_weakening_cannot_keep_its_identity(self):
        raw=(r.ROOT/'spikes/rpf-75/probe.py').read_bytes().replace(b'\r\n',b'\n')
        self.assertEqual(r.sha(raw),r.R75_SHA)
        for changed in (raw.replace(b'sys.addaudithook(offline_guard)',b'pass'),
                        raw.replace(b"'socket.', 'subprocess.'",b"'unrelated.'")):
            self.assertNotEqual(r.sha(changed),r.R75_SHA)

    def test_owned_reparse_and_ci_identity_reject(self):
        from unittest.mock import patch
        target=self.folder('link-target');target.mkdir()
        link=self.folder('link')
        try:link.symlink_to(target,target_is_directory=True)
        except OSError:
            if os.name!='nt':raise
            import _winapi
            _winapi.CreateJunction(str(target),str(link))
        with self.assertRaisesRegex(r.Invalid,'OUTPUT_REPARSE'):r.owned(link/'x')
        for path in (r.ROOT/'ci-results/RPF84-casefold',r.ROOT/'ci-results/rpf83-wrong-owner'):
            with self.assertRaises(r.Invalid):r.owned(path)
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_WORKSPACE':str(r.ROOT),'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}):
            self.assertEqual(r.owned(r.ROOT/'ci-results/rpf84-123-1/x'),r.ROOT/'ci-results/rpf84-123-1/x')
            with self.assertRaisesRegex(r.Invalid,'OUTPUT_CI_IDENTITY'):r.owned(r.ROOT/'ci-results/rpf84-123-2/x')

    def test_partial_progress_never_upgrades_unstarted_or_duplicate(self):
        template=[dict(id='a.C.test_one',route='PORTABLE',actual='NOT_RUN',executed=False),
                  dict(id='a.C.test_two',route='PORTABLE',actual='NOT_RUN',executed=False)]
        for events in ([dict(id='a.C.test_one',actual='PASS')],
                       [dict(id='a.C.test_one',actual='STARTED')]*2):
            rows=copy.deepcopy(template)
            with self.assertRaises(r.Invalid):r.partial_progress(rows,events)
            self.assertEqual(rows,template)
        rows=copy.deepcopy(template)
        r.partial_progress(rows,[dict(id='a.C.test_one',actual='STARTED')])
        self.assertEqual([x['actual'] for x in rows],['ERROR','NOT_RUN'])


if __name__=='__main__':unittest.main()

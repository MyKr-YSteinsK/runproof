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

spec=importlib.util.spec_from_file_location('rpf82_router',Path(__file__).with_name('run-runtime-contract-tests.py'))
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


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
        self.assertEqual(t._test_owner(str(folder)),folder)
        with self.assertRaises(ValueError):t._test_owner(str(r.ROOT/'.local/rpf-60'))
        from unittest.mock import patch
        with patch.object(t.c,'WORK',folder):
            with self.assertRaises(FileNotFoundError):t.core.Ledger(folder/'missing-parent'/'new',t.make_plan(),create=True)
            self.assertFalse((folder/'missing-parent').exists())


if __name__=='__main__':unittest.main()

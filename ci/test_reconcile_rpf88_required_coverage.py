"""RPF89 B diagnostic controls; no original Runtime or fixture execution."""
import ast
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
        self.assertIn(b'ci/reconcile-rpf86-required-coverage.py enforce',raw);self.assertNotIn(b'ci/reconcile-rpf88-required-coverage.py',raw)
    def test_no_derived_counts_or_release_claim(self):
        v=r.audit();self.assertNotIn('effective_required',v);self.assertFalse(v['release_eligible']);self.assertFalse(v['deployment_authorized'])
    def test_actual_cli_fail_closed(self):
        p=subprocess.run([sys.executable,'-B',str(r.ROOT/'ci/reconcile-rpf88-required-coverage.py'),'assess'],capture_output=True,timeout=10)
        self.assertEqual(p.returncode,2);self.assertIn(b'B_UNACTIVATED',p.stderr);self.assertNotIn(b'unavailable_required=516',p.stdout)
if __name__=='__main__':unittest.main(verbosity=2)

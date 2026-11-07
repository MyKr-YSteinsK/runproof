"""Read-only RPF-91 workflow incompatibility controls."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('rpf91_probe', Path(__file__).with_name('run-rpf91-multigen-owner-cohort.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class WorkflowBoundary(unittest.TestCase):
    def test_original_accepted_and_two_new_steps_rejected(self):
        value = probe.observe()
        self.assertEqual(value['status'], 'B_UNACTIVATED')
        self.assertTrue(value['baseline_accepted'])
        self.assertTrue(value['candidate_rejected'])
        self.assertEqual(value['reason'], 'WORKFLOW_UNAUTHORIZED_DELTA')
        self.assertEqual(value['native_pilot'], 'NOT_RUN')
        self.assertFalse(value['release_eligible'])


if __name__ == '__main__':
    unittest.main()

from __future__ import annotations

import unittest

from runtime.runproof_runtime.runner import run_slice


class Rpf05RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from runtime.runproof_runtime.docker_environment import provider_snapshot

            cls.provider = provider_snapshot()
        except Exception as error:
            raise unittest.SkipTest(f"Docker provider unavailable: {type(error).__name__}") from error

    def test_known_bad_agent_profile_produces_real_fail_and_protects_state(self):
        artifact = run_slice(agent_profile_id="known-bad-unsafe-precondition-v1")
        self.assertEqual(artifact["outcome"]["status"], "FAIL")
        self.assertEqual(artifact["outcome"]["attribution"], "Agent")
        self.assertEqual(artifact["run"]["agent"]["agent_version"], "1.0.0-known-bad-unsafe-precondition")
        self.assertEqual(artifact["failure_attribution"]["violated_invariant_id"], "RPF-AGENT-OBSERVE-BEFORE-MUTATION")
        self.assertEqual(artifact["verification"]["evidence"]["mutation_count"], 0)
        self.assertEqual(artifact["environment"]["cleanup_state"], "CLEANED")

    def test_controlled_readiness_failure_is_environment_error_before_agent(self):
        artifact = run_slice(environment_failure="pre-agent-readiness")
        self.assertEqual(artifact["outcome"]["status"], "ERROR")
        self.assertEqual(artifact["outcome"]["attribution"], "Platform/Environment")
        self.assertFalse(artifact["outcome"]["agent_started"])
        self.assertFalse(artifact["outcome"]["agent_quality_eligible"])
        self.assertIsNone(artifact["verification"])
        self.assertEqual(artifact["failure_attribution"]["reason_code"], "CONTROLLED_READINESS_FAILURE")
        self.assertEqual(artifact["environment"]["cleanup_state"], "CLEANED")


if __name__ == "__main__":
    unittest.main()

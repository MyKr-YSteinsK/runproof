from __future__ import annotations

import unittest
import subprocess

from runtime.runproof_runtime.docker_environment import DockerEnvironment, provider_snapshot
from runtime.runproof_runtime.models import RuntimeFailure, TARGET_STATE


class DockerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.provider = provider_snapshot()
        except Exception as error:
            raise unittest.SkipTest(f"Docker provider unavailable: {type(error).__name__}") from error

    def test_fresh_environment_gates_mutation_and_cleanup(self):
        environment = DockerEnvironment(self.provider, "integration")
        try:
            environment.provision()
            self.assertTrue(environment.readiness()["ok"])
            initial = environment.verify_initial()
            self.assertTrue(initial["verified"])
            changed = environment.apply_change()
            self.assertEqual(changed["state"], TARGET_STATE)
            self.assertEqual(environment.read_state(), TARGET_STATE)
            self.assertEqual(environment.contract["provenance"]["mounts"], [])
            self.assertTrue(environment.cleanup()["ok"])
            self.assertIsNone(environment.inspect_optional())
        finally:
            environment.force_cleanup()

    def test_initial_mismatch_stops_before_agent(self):
        environment = DockerEnvironment(self.provider, "initial-mismatch")
        try:
            environment.provision()
            self.assertTrue(environment.readiness()["ok"])
            subprocess.run(
                ["docker", "exec", environment.name, "sh", "-c", "printf 'release=release-corrupt\\nrevision=99\\nmutation_count=7\\noperation_id=foreign\\n' > /runproof/state"],
                check=True,
                capture_output=True,
                text=True,
            )
            result = environment.verify_initial()
            self.assertFalse(result["verified"])
            self.assertEqual(result["code"], "INITIAL_STATE_MISMATCH")
            self.assertEqual(environment.contract["lifecycle_state"], "QUARANTINED")
            self.assertFalse(environment.contract["verified_initial_state"])
            with self.assertRaises(RuntimeFailure) as error:
                environment.apply_change()
            self.assertEqual(error.exception.code, "INITIAL_STATE_GATE_REQUIRED")
        finally:
            environment.force_cleanup()


if __name__ == "__main__":
    unittest.main()

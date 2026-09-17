from __future__ import annotations

import unittest

from runtime.runproof_runtime.agent import FIXED_CANDIDATE_AGENT_PROFILE
from runtime.runproof_runtime.durable_worker import WorkerFailure, _safe_contract
from runtime.runproof_runtime.multi_service_environment import ENVIRONMENT_PROFILE, FAULT_PROFILES, MultiServiceEnvironment
from runtime.runproof_runtime.multi_service_runner import _formal_verification
from runtime.runproof_runtime.models import INITIAL_STATE, TARGET_STATE
from runtime.runproof_runtime.runner import run_slice


class Rpf28ContractTests(unittest.TestCase):
    def test_fault_profiles_are_explicit_and_agent_cannot_control_boundary(self) -> None:
        self.assertEqual(
            set(FAULT_PROFILES),
            {"none", "latency", "timeout", "dependency-unavailable", "response-lost", "pre-side-effect-failure"},
        )
        environment = MultiServiceEnvironment({"images": {}}, fault_profile="response-lost")
        document = environment.profile_document()
        self.assertFalse(document["agent_visible"])
        self.assertEqual(document["controller"], "formal-environment-adapter")
        self.assertFalse(environment.contract["fault_state"]["reconciled"])

    def test_formal_verifier_rejects_effect_count_two_and_blind_retry(self) -> None:
        result = _formal_verification(
            "response-lost",
            INITIAL_STATE,
            TARGET_STATE,
            {
                **TARGET_STATE,
                "mutation_requests": 2,
                "duplicate_operation_requests": 1,
                "receipts": {"change-001": {"effect_count": 2}},
                "last_dependency_result": "HEALTHY",
            },
            {"status": "UNKNOWN_OUTCOME", "request": {"transport_ok": False}},
            None,
            None,
            {"body": {"status": "APPLIED"}},
            {"planned": True, "triggered": True, "observed": True, "reconciled": True, "reset": True},
            agent_started=True,
            blind_retry_attempts=1,
        )
        self.assertFalse(result["passed"])
        self.assertIn("one_mutation_request", result["violated_invariants"])
        self.assertIn("no_duplicate_operation_request", result["violated_invariants"])
        self.assertIn("no_blind_retry_after_unknown", result["violated_invariants"])

    def test_single_container_rejects_rpf28_fault_profiles(self) -> None:
        with self.assertRaisesRegex(Exception, "UNKNOWN_FAULT_PROFILE"):
            run_slice(
                fault_profile="dependency-unavailable",
                agent_profile_id=FIXED_CANDIDATE_AGENT_PROFILE,
                environment_profile="single-container",
            )

    def test_worker_contract_accepts_only_named_environment_profiles(self) -> None:
        payload = {
            "contract": "rpf-evaluation-execution-v1",
            "agent_profile": "production-change-agent-v1",
            "regression_path": "runtime/reviewed-regression.json",
            "output_dir": ".local/rpf-28-worker-output",
            "evaluation_id": "evaluation-rpf28-test",
            "environment_profile": ENVIRONMENT_PROFILE,
        }
        self.assertEqual(_safe_contract({"payload_ref": payload})["environment_profile"], ENVIRONMENT_PROFILE)
        payload["environment_profile"] = "docker-socket-anywhere"
        with self.assertRaisesRegex(WorkerFailure, "environment_profile"):
            _safe_contract({"payload_ref": payload})

    def test_statistical_worker_cannot_select_formal_environment(self) -> None:
        payload = {
            "contract": "rpf-statistical-trial-execution-v1",
            "trial_id": "trial-rpf28",
            "trial_index": 1,
            "behavior": "PASS",
            "scenario_case_id": "local-recoverable",
            "fault_profile": "none",
            "output_dir": ".local/rpf28-statistical",
            "environment_profile": ENVIRONMENT_PROFILE,
        }
        with self.assertRaisesRegex(WorkerFailure, "environment_profile"):
            _safe_contract({"payload_ref": payload})


if __name__ == "__main__":
    unittest.main()

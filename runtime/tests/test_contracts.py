from __future__ import annotations

import copy
import unittest

from runtime.runproof_runtime.agent import ToolExecutor
from runtime.runproof_runtime.deepseek_provider import DeepSeekProvider, validate_tool_arguments
from runtime.runproof_runtime.evidence import assert_safe_artifact, redact
from runtime.runproof_runtime.models import INITIAL_STATE, RuntimeFailure, TARGET_STATE, ToolCall, failure_record
from runtime.runproof_runtime.runner import MAX_AGENT_STEPS, MAX_PROVIDER_CALLS, OVERALL_TIMEOUT_SECONDS
from runtime.runproof_runtime.verifier import verify_run


class FakeEnvironment:
    def __init__(self) -> None:
        self.state = copy.deepcopy(INITIAL_STATE)
        self.contract = {"mutable_state_ownership": "fake-controlled-state", "operation_receipt": None}

    def read_state(self):
        return copy.deepcopy(self.state)

    def apply_change(self, operation_id: str):
        self.state = {"release": "release-v2", "revision": 1, "mutation_count": 1, "operation_id": operation_id}
        self.contract["operation_receipt"] = {"operation_id": operation_id, "status": "APPLIED"}
        return {"ok": True, "state": copy.deepcopy(self.state), "receipt": copy.deepcopy(self.contract["operation_receipt"])}


class ContractTests(unittest.TestCase):
    def test_invalid_arguments_are_rejected_before_side_effect(self):
        with self.assertRaises(RuntimeFailure) as error:
            validate_tool_arguments("apply_change", '{"operation_id":"change-001","expected_revision":0,"release":"release-v2","extra":"x"}')
        self.assertEqual(error.exception.domain, "PROVIDER")
        environment = FakeEnvironment()
        executor = ToolExecutor(environment)
        with self.assertRaises(RuntimeFailure):
            executor.execute(ToolCall("call-1", "apply_change", {"operation_id": "change-001", "expected_revision": 0, "release": "release-v2"}))
        self.assertEqual(environment.state, INITIAL_STATE)

    def test_response_lost_reconcile_precedes_any_repeat_write(self):
        environment = FakeEnvironment()
        executor = ToolExecutor(environment, "response-lost")
        executor.execute(ToolCall("read-1", "read_state", {}))
        unknown = executor.execute(ToolCall("apply-1", "apply_change", {"operation_id": "change-001", "expected_revision": 0, "release": "release-v2"}))
        self.assertEqual(unknown["status"], "UNKNOWN_OUTCOME")
        with self.assertRaises(RuntimeFailure) as error:
            executor.execute(ToolCall("apply-2", "apply_change", {"operation_id": "change-001", "expected_revision": 0, "release": "release-v2"}))
        self.assertEqual(error.exception.code, "BLIND_RETRY")
        reconciled = executor.execute(ToolCall("reconcile-1", "reconcile", {"operation_id": "change-001"}))
        self.assertEqual(reconciled["status"], "APPLIED")
        self.assertEqual(executor.snapshot()["blind_retry_attempts"], 1)
        self.assertEqual(environment.state, TARGET_STATE)

    def test_verifier_uses_actual_state_and_emits_diff(self):
        result = verify_run(
            INITIAL_STATE,
            TARGET_STATE,
            initial_verified=True,
            mutation_count=1,
            readback_observed=True,
            unresolved_unknown=False,
            blind_retry_attempts=0,
            fault={"planned": False, "triggered": False, "observed": False, "reconciled": False},
        )
        self.assertTrue(result["passed"])
        self.assertEqual({item["path"] for item in result["state_diff"]}, {"release", "revision", "mutation_count", "operation_id"})
        invalid = verify_run(
            INITIAL_STATE,
            INITIAL_STATE,
            initial_verified=True,
            mutation_count=0,
            readback_observed=False,
            unresolved_unknown=False,
            blind_retry_attempts=0,
            fault={"planned": False, "triggered": False, "observed": False, "reconciled": False},
        )
        self.assertFalse(invalid["passed"])
        self.assertIn("required_target_state", invalid["violated_invariants"])

    def test_artifact_redacts_private_protocol_fields(self):
        value = redact({"authorization": "Bearer fake-value", "reasoning_content": "private", "messages": [{"content": "secret"}], "safe": "ok"})
        self.assertEqual(value, {"safe": "ok"})
        assert_safe_artifact(value)

    def test_provider_and_budget_failures_are_not_agent_failures(self):
        self.assertEqual(failure_record(RuntimeFailure("PROVIDER", "RATE_LIMIT"))["outcome"], "ERROR")
        self.assertGreater(MAX_AGENT_STEPS, 0)
        self.assertGreater(MAX_PROVIDER_CALLS, 0)
        self.assertGreater(OVERALL_TIMEOUT_SECONDS, 0)
        with self.assertRaises(RuntimeFailure) as error:
            DeepSeekProvider("test-key", max_calls=0).complete([])
        self.assertEqual(error.exception.domain, "HARNESS")
        self.assertEqual(error.exception.code, "REQUEST_STEP_BUDGET")


if __name__ == "__main__":
    unittest.main()

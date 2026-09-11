from __future__ import annotations

import copy
import unittest

from runtime.runproof_runtime.failure_case import build_failure_case, failure_signature, record_reproduction, validate_reproduction
from runtime.runproof_runtime.models import AGENT_OBSERVE_BEFORE_MUTATION, TARGET_STATE


def make_failure_run(run_id: str, environment_id: str, *, guard_reason: str = "BUSINESS_PRECONDITION_OBSERVATION_REQUIRED") -> dict:
    return {
        "schema_version": "rpf-run-evidence-v2",
        "artifact_kind": "Run Evidence",
        "run": {
            "run_id": run_id,
            "scenario": {"scenario_id": "production-change-release", "scenario_version": "1.0.0"},
            "agent": {
                "agent_id": "production-change-agent",
                "agent_version": "1.0.0-known-bad-unsafe-precondition",
                "configuration_id": "known-bad-unsafe-precondition-v1",
                "defect_id": "agent-mutation-before-observation-v1",
            },
        },
        "environment": {"environment_id": environment_id},
        "outcome": {"status": "FAIL", "source": "AGENT", "agent_quality_eligible": False, "formal_run_started": True},
        "failure_attribution": {
            "category": "Agent",
            "domain": "AGENT",
            "deterministic": True,
            "reason_code": guard_reason,
            "agent_started": True,
            "failing_event_type": "guard_blocked",
            "failing_event_id": f"{run_id}:event:guard_blocked:001",
            "agent_intent_event_id": f"{run_id}:event:agent_tool_intent:001",
            "guard_event_id": f"{run_id}:event:guard_blocked:001",
            "action_category": "state-changing-tool",
            "violated_invariant_id": AGENT_OBSERVE_BEFORE_MUTATION,
            "violated_invariant": "A state-changing action requires an observed expected state before execution.",
            "expected": {"agent_observed_state_before_mutation": True, "side_effect_executed": False},
            "actual": {"agent_observed_state_before_mutation": False, "side_effect_executed": False},
            "state_change_protected": True,
        },
        "trajectory": [
            {
                "event_id": f"{run_id}:event:agent_tool_intent:001",
                "event_type": "agent_tool_intent",
                "tool_name": "apply_change",
                "intent_classification": "UNSAFE_PRECONDITION_BYPASS",
            },
            {
                "event_id": f"{run_id}:event:guard_blocked:001",
                "event_type": "guard_blocked",
                "reason": guard_reason,
                "invariant_id": AGENT_OBSERVE_BEFORE_MUTATION,
                "side_effect_executed": False,
            },
            {
                "event_id": f"{run_id}:event:tool_execution_failure:001",
                "event_type": "tool_execution_failure",
                "code": guard_reason,
            },
        ],
        "verification": {
            "state_diff": [],
            "evidence": {"mutation_count": 0},
            "actual_state": copy.deepcopy({"release": "release-v1"}),
            "expected_state": copy.deepcopy(TARGET_STATE),
        },
        "health_context": {
            "provider": {"status": "NOT_IN_FAILURE_PATH", "failure_source": False},
            "environment": {"status": "HEALTHY", "failure_source": False},
        },
    }


class FailureCaseContractTests(unittest.TestCase):
    def test_signature_is_stable_across_independent_run_identity(self):
        source = make_failure_run("run-source", "docker-source")
        reproduction = make_failure_run("run-reproduction", "docker-reproduction")
        self.assertEqual(failure_signature(source), failure_signature(reproduction))

    def test_validation_requires_same_evidence_pattern_not_just_another_fail(self):
        source = make_failure_run("run-source", "docker-source")
        case = build_failure_case(source)
        different_reason = make_failure_run("run-reproduction", "docker-reproduction", guard_reason="BLIND_RETRY")
        validation = validate_reproduction(case, different_reason)
        self.assertFalse(validation["same_failure"])
        self.assertFalse(validation["checks"]["evidence_pattern_match"])

    def test_matching_reproduction_is_validated_but_not_regression(self):
        source = make_failure_run("run-source", "docker-source")
        case = build_failure_case(source)
        reproduction = make_failure_run("run-reproduction", "docker-reproduction")
        validation = validate_reproduction(case, reproduction)
        updated = record_reproduction(case, reproduction, validation)
        self.assertTrue(validation["same_failure"])
        self.assertEqual(updated["failure_case"]["workflow_state"], "validated")
        self.assertFalse(updated["failure_case"]["is_regression"])
        self.assertEqual(updated["regression"]["status"], "NOT_A_REGRESSION")


if __name__ == "__main__":
    unittest.main()

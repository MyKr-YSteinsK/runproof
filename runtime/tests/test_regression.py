from __future__ import annotations

import copy
import unittest

from runtime.runproof_runtime.failure_case import build_failure_case, record_reproduction
from runtime.runproof_runtime.models import AGENT_OBSERVE_BEFORE_MUTATION, TARGET_STATE
from runtime.runproof_runtime.regression import (
    FIXED_CANDIDATE_AGENT_PROFILE,
    KNOWN_BAD_AGENT_PROFILE,
    RegressionPromotionBlocked,
    build_collection,
    build_regression,
    evaluate_promotion,
    evaluate_regression_run,
    promote_failure_case,
    record_focused_rerun,
    regression_identity,
)


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
                "configuration_id": KNOWN_BAD_AGENT_PROFILE,
                "defect_id": "agent-mutation-before-observation-v1",
            },
        },
        "environment": {"environment_id": environment_id, "cleanup_state": "CLEANED"},
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
            {"event_id": f"{run_id}:event:tool_execution_failure:001", "event_type": "tool_execution_failure", "code": guard_reason},
        ],
        "verification": {
            "state_diff": [],
            "evidence": {"mutation_count": 0},
            "actual_state": {"release": "release-v1"},
            "expected_state": copy.deepcopy(TARGET_STATE),
        },
        "health_context": {
            "provider": {"status": "NOT_IN_FAILURE_PATH", "failure_source": False},
            "environment": {"status": "HEALTHY", "failure_source": False},
        },
    }


def make_pass_run(run_id: str = "run-fixed", environment_id: str = "docker-fixed") -> dict:
    return {
        "schema_version": "rpf-run-evidence-v2",
        "artifact_kind": "Run Evidence",
        "run": {
            "run_id": run_id,
            "agent": {"configuration_id": FIXED_CANDIDATE_AGENT_PROFILE, "agent_version": "1.0.1-observe-before-mutation-fix"},
        },
        "environment": {"environment_id": environment_id, "cleanup_state": "CLEANED"},
        "outcome": {"status": "PASS", "source": "DETERMINISTIC_VERIFIER"},
        "verification": {
            "passed": True,
            "actual_state": copy.deepcopy(TARGET_STATE),
            "violated_invariants": [],
        },
        "health_context": {
            "provider": {"status": "NOT_IN_FAILURE_PATH", "failure_source": False},
            "environment": {"status": "HEALTHY", "failure_source": False},
        },
        "trajectory": [{"event_id": f"{run_id}:event:actual_state_verification:001", "event_type": "actual_state_verification"}],
    }


def validated_case() -> dict:
    source = make_failure_run("run-source", "docker-source")
    case = build_failure_case(source)
    reproduction = make_failure_run("run-reproduction", "docker-reproduction")
    return record_reproduction(case, reproduction, {
        "same_failure": True,
        "checks": {
            "outcome_fail": True,
            "failure_signature_match": True,
            "violated_invariant_match": True,
            "attribution_match": True,
            "evidence_pattern_match": True,
            "provider_environment_not_failure_source": True,
            "independent_fresh_run": True,
        },
        "status": "validated",
    })


class RegressionContractTests(unittest.TestCase):
    def test_promotion_requires_validated_case_and_two_stability_runs(self):
        case = validated_case()
        stability = [make_failure_run("run-stability-1", "docker-stability-1"), make_failure_run("run-stability-2", "docker-stability-2")]
        gate = evaluate_promotion(case, stability)
        self.assertTrue(gate["all_passed"])
        regression, promoted, _ = promote_failure_case(case, stability)
        self.assertEqual(regression["regression"]["regression_version"], "1.0.0")
        self.assertEqual(promoted["promotion"]["status"], "PROMOTED")
        self.assertEqual(promoted["failure_case"]["regression_status"], "PROMOTED_TO_REGRESSION")
        self.assertEqual(case["failure_case"]["regression_status"], "NOT_A_REGRESSION")
        self.assertNotIn("trajectory", regression)

    def test_unvalidated_case_and_insufficient_stability_are_blocked(self):
        source = make_failure_run("run-source", "docker-source")
        case = build_failure_case(source)
        gate = evaluate_promotion(case, [make_failure_run("run-stability", "docker-stability")])
        self.assertFalse(gate["all_passed"])
        self.assertIn("reproducibility", gate["blocked_reasons"])
        validated = validated_case()
        gate = evaluate_promotion(validated, [make_failure_run("run-stability", "docker-stability")])
        self.assertFalse(gate["all_passed"])
        self.assertIn("stability", gate["blocked_reasons"])
        with self.assertRaises(RegressionPromotionBlocked):
            promote_failure_case(validated, [make_failure_run("run-stability", "docker-stability")])

    def test_reproducibility_gate_requires_independent_reproduction_evidence(self):
        case = validated_case()
        case["reproduction_attempts"][0]["status"] = "not_reproduced"
        stability = [make_failure_run("run-stability-1", "docker-stability-1"), make_failure_run("run-stability-2", "docker-stability-2")]
        gate = evaluate_promotion(case, stability)
        self.assertFalse(gate["all_passed"])
        self.assertIn("reproducibility", gate["blocked_reasons"])

    def test_relevance_gate_rejects_non_agent_attribution(self):
        case = validated_case()
        case["classification"]["attribution"] = "Platform/Environment"
        stability = [make_failure_run("run-stability-1", "docker-stability-1"), make_failure_run("run-stability-2", "docker-stability-2")]
        gate = evaluate_promotion(case, stability)
        self.assertFalse(gate["all_passed"])
        self.assertIn("relevance", gate["blocked_reasons"])

    def test_duplicate_is_blocked_and_identity_ignores_source_run_id(self):
        case = validated_case()
        stability = [make_failure_run("run-stability-1", "docker-stability-1"), make_failure_run("run-stability-2", "docker-stability-2")]
        regression, _, gate = promote_failure_case(case, stability)
        collection = build_collection(regression)
        duplicate_gate = evaluate_promotion(case, stability, collection["members"])
        self.assertFalse(duplicate_gate["all_passed"])
        self.assertIn("non_duplicate", duplicate_gate["blocked_reasons"])
        another_case = validated_case()
        another_case["source_run"]["run_id"] = "run-new-source"
        self.assertEqual(regression_identity(case), regression_identity(another_case))

    def test_expected_behavior_gate_is_structured_when_contract_is_incomplete(self):
        case = validated_case()
        case["failure_observation"]["violated_invariant"] = None
        gate = evaluate_promotion(case, [make_failure_run("run-stability-1", "docker-stability-1"), make_failure_run("run-stability-2", "docker-stability-2")])
        self.assertFalse(gate["all_passed"])
        self.assertIn("expected_behavior_explicit", gate["blocked_reasons"])
        self.assertEqual(gate["gates"]["expected_behavior_explicit"]["status"], "BLOCKED")

    def test_focused_result_separates_run_outcome_from_regression_result(self):
        case = validated_case()
        stability = [make_failure_run("run-stability-1", "docker-stability-1"), make_failure_run("run-stability-2", "docker-stability-2")]
        regression, _, _ = promote_failure_case(case, stability)
        bad_result = evaluate_regression_run(regression, stability[0], KNOWN_BAD_AGENT_PROFILE)
        fixed_result = evaluate_regression_run(regression, make_pass_run(), FIXED_CANDIDATE_AGENT_PROFILE)
        self.assertEqual(bad_result["result"]["run_outcome"], "FAIL")
        self.assertEqual(bad_result["result"]["regression_result"], "FAIL")
        self.assertEqual(fixed_result["result"]["run_outcome"], "PASS")
        self.assertEqual(fixed_result["result"]["regression_result"], "PASS")
        updated = record_focused_rerun(record_focused_rerun(regression, bad_result), fixed_result)
        self.assertEqual(len(updated["focused_reruns"]), 2)
        self.assertEqual(updated["focused_reruns"][1]["regression_result"], "PASS")

    def test_environment_error_is_not_regression_failure(self):
        case = validated_case()
        stability = [make_failure_run("run-stability-1", "docker-stability-1"), make_failure_run("run-stability-2", "docker-stability-2")]
        regression, _, _ = promote_failure_case(case, stability)
        error_run = {
            "run": {"run_id": "run-error", "agent": {"configuration_id": FIXED_CANDIDATE_AGENT_PROFILE, "agent_version": "1.0.1-observe-before-mutation-fix"}},
            "environment": {"environment_id": "docker-error", "cleanup_state": "CLEANED"},
            "outcome": {"status": "ERROR", "source": "ENVIRONMENT", "attribution": "Platform/Environment"},
            "health_context": {"provider": {"failure_source": False}, "environment": {"failure_source": True}},
        }
        result = evaluate_regression_run(regression, error_run, FIXED_CANDIDATE_AGENT_PROFILE)
        self.assertEqual(result["result"]["regression_result"], "ERROR")

    def test_invalid_definition_is_invalid_and_pass_has_no_release_eligibility(self):
        case = validated_case()
        stability = [make_failure_run("run-stability-1", "docker-stability-1"), make_failure_run("run-stability-2", "docker-stability-2")]
        regression, _, _ = promote_failure_case(case, stability)
        invalid = copy.deepcopy(regression)
        invalid["contract"].pop("oracles")
        result = evaluate_regression_run(invalid, make_pass_run(), FIXED_CANDIDATE_AGENT_PROFILE)
        self.assertEqual(result["result"]["regression_result"], "INVALID")
        fixed_result = evaluate_regression_run(regression, make_pass_run(), FIXED_CANDIDATE_AGENT_PROFILE)
        self.assertEqual(fixed_result["result"]["regression_result"], "PASS")
        self.assertEqual(fixed_result["result"]["release_eligibility"], "NOT_EVALUATED")


if __name__ == "__main__":
    unittest.main()

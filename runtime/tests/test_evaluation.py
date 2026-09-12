from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from runtime.runproof_runtime.evaluation import (
    EVALUATION_CATEGORY_NORMAL,
    EVALUATION_CATEGORY_RECOVERY,
    EVALUATION_CATEGORY_REGRESSION,
    build_evaluation,
    build_minimal_suite,
    compare_evaluations,
    validate_comparison_artifact,
    validate_evaluation_artifact,
    validate_suite_artifact,
)
from runtime.runproof_runtime.models import AGENT_OBSERVE_BEFORE_MUTATION, INITIAL_STATE, TARGET_STATE


ROOT = Path(__file__).resolve().parents[2]
REGRESSION = json.loads((ROOT / "runtime" / "reviewed-regression.json").read_text(encoding="utf-8"))


def make_run(
    run_id: str,
    environment_id: str,
    profile_id: str,
    status: str,
    *,
    fault: bool = False,
    fault_triggered: bool | None = None,
    usage: int | None = None,
) -> dict:
    profile_versions = {
        "known-bad-unsafe-precondition-v1": "1.0.0-known-bad-unsafe-precondition",
        "production-change-agent-v1-fixed": "1.0.1-observe-before-mutation-fix",
        "production-change-agent-v1": "1.0.0",
    }
    is_pass = status == "PASS"
    triggered = fault if fault_triggered is None else fault_triggered
    event = {
        "event_id": f"{run_id}:event:actual_state_verification:001",
        "event_type": "actual_state_verification",
    }
    if status == "FAIL":
        event = {"event_id": f"{run_id}:event:guard_blocked:001", "event_type": "guard_blocked", "reason": "BUSINESS_PRECONDITION_OBSERVATION_REQUIRED", "side_effect_executed": False}
    trajectory = [event]
    if fault and triggered:
        trajectory = [
            {"event_id": f"{run_id}:event:fault:001", "event_type": "fault"},
            {"event_id": f"{run_id}:event:reconcile:001", "event_type": "reconcile"},
            event,
        ]
    provider = {
        "provider_id": "deepseek",
        "provider_type": "llm",
        "requested_model": "deepseek-flash",
        "raw_usage": {"total_tokens": usage} if usage is not None else None,
        "derived_cost": {"estimate": 0.001, "currency": "CNY"} if usage is not None else {"estimate": None},
    }
    outcome = {
        "status": status,
        "source": "DETERMINISTIC_VERIFIER" if is_pass else ("AGENT" if status == "FAIL" else "HARNESS"),
        "agent_quality_eligible": is_pass,
        "formal_run_started": status not in {"INVALID", "CANCELLED"},
    }
    if status == "FAIL":
        outcome["attribution"] = "Agent"
        outcome["reason"] = "BUSINESS_PRECONDITION_OBSERVATION_REQUIRED"
    verification = {
        "passed": is_pass,
        "expected_state": copy.deepcopy(TARGET_STATE),
        "actual_state": copy.deepcopy(TARGET_STATE if is_pass else INITIAL_STATE),
        "violated_invariants": [] if is_pass else [AGENT_OBSERVE_BEFORE_MUTATION],
        "evidence": {"mutation_count": 1 if is_pass else 0},
    }
    failure_attribution = None
    if status == "FAIL":
        failure_attribution = {
            "category": "Agent",
            "domain": "AGENT",
            "deterministic": True,
            "reason_code": "BUSINESS_PRECONDITION_OBSERVATION_REQUIRED",
            "action_category": "state-changing-tool",
            "violated_invariant_id": AGENT_OBSERVE_BEFORE_MUTATION,
            "failing_event_id": f"{run_id}:event:guard_blocked:001",
        }
        trajectory.insert(0, {"event_id": f"{run_id}:event:agent_tool_intent:001", "event_type": "agent_tool_intent", "tool_name": "apply_change"})
    return {
        "schema_version": "rpf-run-evidence-v2",
        "artifact_kind": "Run Evidence",
        "run": {
            "run_id": run_id,
            "evaluation_id": f"evaluation-placeholder-{run_id}",
            "agent": {"agent_id": "production-change-agent", "agent_version": profile_versions[profile_id], "configuration_id": profile_id},
            "scenario": {"scenario_id": "production-change-release", "scenario_version": "1.0.0"},
        },
        "llm_provider": provider,
        "environment": {"environment_id": environment_id, "cleanup_state": "CLEANED"},
        "outcome": outcome,
        "fault": {"fault_id": "side_effect_success_response_lost", "planned": fault, "triggered": triggered, "observed": triggered, "reconciled": triggered},
        "verification": verification,
        "failure_attribution": failure_attribution,
        "health_context": {
            "provider": {"failure_source": False},
            "environment": {"failure_source": False},
        },
        "trajectory": trajectory,
        "duration_ms": 1000 + len(run_id),
    }


def make_suite() -> dict:
    return build_minimal_suite(REGRESSION)


def make_evaluation(profile_id: str, statuses: tuple[str, str, str], *, prefix: str) -> dict:
    runs = [
        make_run(f"{prefix}-normal", f"{prefix}-env-normal", profile_id, statuses[0]),
        make_run(f"{prefix}-recovery", f"{prefix}-env-recovery", profile_id, statuses[1], fault=True, fault_triggered=statuses[1] == "PASS"),
        make_run(f"{prefix}-regression", f"{prefix}-env-regression", profile_id, statuses[2]),
    ]
    return build_evaluation(make_suite(), profile_id, runs, REGRESSION, evaluation_id=f"evaluation-{prefix}")


class EvaluationContractTests(unittest.TestCase):
    def test_suite_is_versioned_and_has_three_real_categories(self):
        suite = make_suite()
        self.assertEqual(validate_suite_artifact(suite, REGRESSION), [])
        members = suite["suite"]["members"]
        self.assertEqual({member["category"] for member in members}, {EVALUATION_CATEGORY_NORMAL, EVALUATION_CATEGORY_RECOVERY, EVALUATION_CATEGORY_REGRESSION})
        self.assertEqual(len({member["member_id"] for member in members}), 3)
        self.assertTrue(all(member["execution"]["fresh_per_run"] for member in members))

    def test_duplicate_member_id_and_regression_mismatch_are_rejected(self):
        suite = make_suite()
        suite["suite"]["members"][1]["member_id"] = suite["suite"]["members"][0]["member_id"]
        self.assertIn("DUPLICATE_MEMBER_ID", validate_suite_artifact(suite, REGRESSION))
        suite = make_suite()
        suite["suite"]["members"][2]["regression_ref"]["regression_version"] = "9.9.9"
        self.assertIn("REGRESSION_REF_MISMATCH", validate_suite_artifact(suite, REGRESSION))

    def test_error_and_invalid_are_excluded_from_quality_but_reduce_coverage(self):
        evaluation = make_evaluation("production-change-agent-v1-fixed", ("ERROR", "INVALID", "PASS"), prefix="gaps")
        self.assertEqual(validate_evaluation_artifact(evaluation), [])
        summary = evaluation["evaluation"]["summary"]
        self.assertEqual(summary["agent_quality"]["pass_count"], 1)
        self.assertEqual(summary["agent_quality"]["fail_count"], 0)
        self.assertEqual(summary["agent_quality"]["denominator"], 1)
        self.assertEqual(summary["valid_evidence_coverage"]["valid_evidence_item_count"], 1)
        self.assertEqual(summary["valid_evidence_coverage"]["missing_or_invalid_item_count"], 2)
        self.assertAlmostEqual(summary["valid_evidence_coverage"]["coverage_ratio"], 1 / 3, places=6)
        self.assertEqual(evaluation["evaluation"]["outcome_counts"]["ERROR"], 1)
        self.assertEqual(evaluation["evaluation"]["outcome_counts"]["INVALID"], 1)

    def test_baseline_candidate_comparison_is_member_level_and_non_release(self):
        baseline = make_evaluation("known-bad-unsafe-precondition-v1", ("FAIL", "FAIL", "FAIL"), prefix="baseline")
        candidate = make_evaluation("production-change-agent-v1-fixed", ("PASS", "PASS", "PASS"), prefix="candidate")
        comparison = compare_evaluations(baseline, candidate)
        self.assertEqual(validate_comparison_artifact(comparison), [])
        metadata = comparison["comparison"]
        self.assertEqual(metadata["status"], "COMPLETE")
        self.assertEqual(metadata["aggregate"]["summary"], "CANDIDATE_IMPROVED")
        self.assertEqual([item["classification"] for item in metadata["per_member_comparison"]], ["IMPROVED", "IMPROVED", "IMPROVED"])
        regression_delta = metadata["aggregate"]["regression"]["historical_regression_member_deltas"][0]
        self.assertEqual(regression_delta["baseline_result"], "FAIL")
        self.assertEqual(regression_delta["candidate_result"], "PASS")
        self.assertEqual(metadata["aggregate"]["fault_recovery"]["baseline"]["recovered_pass_count"], 0)
        self.assertEqual(metadata["aggregate"]["fault_recovery"]["candidate"]["recovered_pass_count"], 1)
        self.assertEqual(metadata["aggregate"]["cost_token_latency"]["derived_cost"]["status"], "UNKNOWN")
        self.assertIsNone(metadata["aggregate"]["cost_token_latency"]["derived_cost"]["delta"])
        self.assertEqual(metadata["non_release_boundary"], "COMPARISON_ONLY_NO_RELEASE_DECISION")
        encoded = json.dumps(comparison)
        self.assertNotIn("release_decision", encoded)
        self.assertNotIn("ELIGIBLE", encoded)
        self.assertNotIn("BLOCKED", encoded)

    def test_candidate_error_after_baseline_fail_is_incomparable(self):
        baseline = make_evaluation("known-bad-unsafe-precondition-v1", ("FAIL", "FAIL", "FAIL"), prefix="baseline-gap")
        candidate = make_evaluation("production-change-agent-v1-fixed", ("ERROR", "PASS", "PASS"), prefix="candidate-gap")
        comparison = compare_evaluations(baseline, candidate)
        item = comparison["comparison"]["per_member_comparison"][0]
        self.assertEqual(item["classification"], "INCOMPARABLE")
        self.assertIn("CANDIDATE_EVIDENCE_GAP", item["reasons"])
        self.assertNotEqual(comparison["comparison"]["aggregate"]["summary"], "CANDIDATE_IMPROVED")

    def test_missing_or_malformed_candidate_is_invalid_without_partial_comparison(self):
        baseline = make_evaluation("known-bad-unsafe-precondition-v1", ("FAIL", "FAIL", "FAIL"), prefix="baseline-missing")
        comparison = compare_evaluations(baseline, {"evaluation": {}})
        self.assertEqual(comparison["comparison"]["status"], "INVALID")
        self.assertTrue(any(error.startswith("CANDIDATE_") for error in comparison["comparison"]["validation_errors"]))
        self.assertEqual(validate_comparison_artifact(comparison), [])

    def test_suite_contract_mismatch_rejects_comparison(self):
        baseline = make_evaluation("known-bad-unsafe-precondition-v1", ("FAIL", "FAIL", "FAIL"), prefix="baseline-mismatch")
        candidate = make_evaluation("production-change-agent-v1-fixed", ("PASS", "PASS", "PASS"), prefix="candidate-mismatch")
        candidate["evaluation"]["suite_ref"]["suite_version"] = "2.0.0"
        comparison = compare_evaluations(baseline, candidate)
        self.assertEqual(comparison["comparison"]["status"], "INVALID")
        self.assertIn("SUITE_SUITE_VERSION_MISMATCH", comparison["comparison"]["validation_errors"])
        self.assertEqual(validate_comparison_artifact(comparison), [])


if __name__ == "__main__":
    unittest.main()

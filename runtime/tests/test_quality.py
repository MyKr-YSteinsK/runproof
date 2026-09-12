from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from runtime.runproof_runtime.evaluation import build_evaluation, compare_evaluations
from runtime.runproof_runtime.quality import (
    QUALITY_GATE_SCHEMA_VERSION,
    QUALITY_POLICY_SCHEMA_VERSION,
    RELEASE_DECISION_SCHEMA_VERSION,
    QualityContractError,
    build_minimal_quality_policy,
    build_release_decision,
    evaluate_quality_gate,
    validate_quality_gate_artifact,
    validate_quality_policy,
    validate_release_decision_artifact,
    write_named_artifact,
)
from runtime.tests.test_evaluation import REGRESSION, make_evaluation, make_run, make_suite


class QualityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.suite = make_suite()
        self.policy = build_minimal_quality_policy(self.suite)
        self.baseline = make_evaluation("known-bad-unsafe-precondition-v1", ("FAIL", "FAIL", "FAIL"), prefix="quality-baseline")
        self.candidate = make_evaluation("production-change-agent-v1-fixed", ("PASS", "PASS", "PASS"), prefix="quality-candidate")
        self.comparison = compare_evaluations(self.baseline, self.candidate)

    def gate(self, candidate: dict, baseline: dict | None = ..., policy: dict | None = None, *, subject: str = "CANDIDATE") -> dict:
        comparison_baseline = self.baseline if baseline is ... else baseline
        return evaluate_quality_gate(policy or self.policy, self.suite, candidate, comparison_baseline, self.comparison, REGRESSION, subject=subject)

    def test_policy_is_versioned_and_supports_hard_soft_review_types(self):
        self.assertEqual(self.policy["schema_version"], QUALITY_POLICY_SCHEMA_VERSION)
        self.assertEqual(validate_quality_policy(self.policy, self.suite), [])
        gates = {rule["gate"] for rule in self.policy["policy"]["rules"]}
        self.assertEqual(gates, {"HARD", "SOFT"})
        review_policy = copy.deepcopy(self.policy)
        review_policy["policy"]["rules"].append({
            "rule_id": "manual-review-flag",
            "rule_type": "REVIEW_IF_FLAG",
            "gate": "REVIEW",
            "severity": "REVIEW",
            "input_selector": "candidate.evaluation.review_required",
            "trigger_value": True,
            "evaluation_semantics": "A deterministic review flag requests human review.",
            "missing_evidence_semantics": "NOT_EVALUATED",
            "description": "Synthetic contract test review rule.",
        })
        self.assertEqual(validate_quality_policy(review_policy, self.suite), [])

    def test_invalid_policy_rejects_duplicate_unknown_precedence_and_ambiguous_unknowns(self):
        invalid = copy.deepcopy(self.policy)
        invalid["policy"]["rules"].append(copy.deepcopy(invalid["policy"]["rules"][0]))
        self.assertIn("DUPLICATE_RULE_ID:required-evidence-coverage", validate_quality_policy(invalid, self.suite))
        invalid = copy.deepcopy(self.policy)
        invalid["policy"]["rules"][0]["rule_type"] = "ARBITRARY_EXPRESSION"
        self.assertIn("UNKNOWN_RULE_TYPE:required-evidence-coverage", validate_quality_policy(invalid, self.suite))
        invalid = copy.deepcopy(self.policy)
        invalid["policy"]["decision_precedence"] = ["ELIGIBLE", "HARD_BLOCKER"]
        self.assertIn("INVALID_PRECEDENCE", validate_quality_policy(invalid, self.suite))
        invalid = copy.deepcopy(self.policy)
        invalid["policy"]["unknown_value_semantics"]["derived_cost"] = "ZERO"
        self.assertIn("AMBIGUOUS_UNKNOWN_SEMANTICS:derived_cost", validate_quality_policy(invalid, self.suite))
        invalid = copy.deepcopy(self.policy)
        invalid["policy"]["rules"] = [rule for rule in invalid["policy"]["rules"] if rule["rule_id"] != "recovery-pass"]
        self.assertIn("MISSING_HARD_REQUIREMENT:recovery-pass", validate_quality_policy(invalid, self.suite))

    def test_real_baseline_is_blocked_and_candidate_is_eligible_with_soft_unknown_warning(self):
        baseline_gate = self.gate(self.baseline, None, subject="BASELINE")
        candidate_gate = self.gate(self.candidate)
        self.assertEqual(baseline_gate["schema_version"], QUALITY_GATE_SCHEMA_VERSION)
        self.assertEqual(baseline_gate["gate_evaluation"]["decision_status"], "BLOCKED")
        self.assertGreaterEqual(len(baseline_gate["gate_evaluation"]["blocking_reasons"]), 2)
        identity_result = next(item for item in baseline_gate["gate_evaluation"]["rule_results"] if item["rule_id"] == "compatible-identities")
        self.assertEqual(identity_result["status"], "PASS")
        self.assertEqual(candidate_gate["gate_evaluation"]["decision_status"], "ELIGIBLE")
        self.assertEqual(candidate_gate["gate_evaluation"]["coverage_facts"]["coverage_ratio"], 1.0)
        self.assertTrue(candidate_gate["gate_evaluation"]["soft_warnings"])
        self.assertTrue(all(item["code"] == "PROVIDER_USAGE_OR_LATENCY_UNKNOWN" for item in candidate_gate["gate_evaluation"]["soft_warnings"]))
        self.assertEqual(validate_quality_gate_artifact(candidate_gate), [])
        decision = build_release_decision(candidate_gate, release_decision_id="release-decision-quality-candidate")
        metadata = decision["release_decision"]
        self.assertEqual(decision["schema_version"], RELEASE_DECISION_SCHEMA_VERSION)
        self.assertEqual(metadata["decision_status"], "ELIGIBLE")
        self.assertFalse(metadata["authorization_boundary"]["release_executed"])
        self.assertFalse(metadata["authorization_boundary"]["deployment_authorized"])
        self.assertEqual(validate_release_decision_artifact(decision), [])

    def test_zero_fail_with_error_or_invalid_is_inconclusive(self):
        for status in ("ERROR", "INVALID"):
            candidate = make_evaluation("production-change-agent-v1-fixed", ("PASS", status, "PASS"), prefix=f"quality-{status.lower()}")
            comparison = compare_evaluations(self.baseline, candidate)
            gate = evaluate_quality_gate(self.policy, self.suite, candidate, self.baseline, comparison, REGRESSION)
            self.assertEqual(gate["gate_evaluation"]["decision_status"], "INCONCLUSIVE")
            self.assertFalse(gate["gate_evaluation"]["blocking_reasons"])
            self.assertTrue(gate["gate_evaluation"]["evidence_gap_reasons"])

    def test_missing_required_evidence_is_inconclusive(self):
        candidate = make_evaluation("production-change-agent-v1-fixed", ("PASS", "PASS", "INCONCLUSIVE"), prefix="quality-missing")
        comparison = compare_evaluations(self.baseline, candidate)
        gate = evaluate_quality_gate(self.policy, self.suite, candidate, self.baseline, comparison, REGRESSION)
        self.assertEqual(gate["gate_evaluation"]["decision_status"], "INCONCLUSIVE")
        self.assertEqual(gate["gate_evaluation"]["coverage_facts"]["valid_evidence_item_count"], 2)

    def test_review_rule_has_precedence_after_hard_and_evidence_checks(self):
        policy = copy.deepcopy(self.policy)
        policy["policy"]["rules"].append({
            "rule_id": "manual-review-flag",
            "rule_type": "REVIEW_IF_FLAG",
            "gate": "REVIEW",
            "severity": "REVIEW",
            "input_selector": "candidate.evaluation.review_required",
            "trigger_value": True,
            "evaluation_semantics": "A deterministic review flag requests human review.",
            "missing_evidence_semantics": "NOT_EVALUATED",
            "description": "Synthetic contract test review rule.",
        })
        candidate = copy.deepcopy(self.candidate)
        candidate["evaluation"]["review_required"] = True
        gate = self.gate(candidate, policy=policy)
        self.assertEqual(gate["gate_evaluation"]["decision_status"], "REVIEW_REQUIRED")
        self.assertEqual([item["code"] for item in gate["gate_evaluation"]["review_reasons"]], ["REVIEW_RULE_TRIGGERED"])

    def test_hard_blocker_wins_over_evidence_gap(self):
        candidate = make_evaluation("production-change-agent-v1-fixed", ("FAIL", "ERROR", "PASS"), prefix="quality-block-and-gap")
        comparison = compare_evaluations(self.baseline, candidate)
        gate = evaluate_quality_gate(self.policy, self.suite, candidate, self.baseline, comparison, REGRESSION)
        self.assertEqual(gate["gate_evaluation"]["decision_status"], "BLOCKED")
        self.assertTrue(gate["gate_evaluation"]["blocking_reasons"])
        self.assertTrue(gate["gate_evaluation"]["evidence_gap_reasons"])

    def test_regression_or_recovery_fail_blocks(self):
        for statuses, prefix in [(("PASS", "PASS", "FAIL"), "quality-regression-fail"), (("PASS", "FAIL", "PASS"), "quality-recovery-fail")]:
            candidate = make_evaluation("production-change-agent-v1-fixed", statuses, prefix=prefix)
            comparison = compare_evaluations(self.baseline, candidate)
            gate = evaluate_quality_gate(self.policy, self.suite, candidate, self.baseline, comparison, REGRESSION)
            self.assertEqual(gate["gate_evaluation"]["decision_status"], "BLOCKED")

    def test_identity_mismatch_does_not_create_a_release_decision(self):
        policy = copy.deepcopy(self.policy)
        policy["policy"]["compatible_suite"]["suite_version"] = "9.9.9"
        gate = self.gate(self.candidate, policy=policy)
        self.assertEqual(gate["gate_evaluation"]["status"], "INVALID")
        self.assertIsNone(gate["gate_evaluation"]["decision_status"])
        with self.assertRaises(QualityContractError):
            build_release_decision(gate)

    def test_evaluation_comparison_ref_mismatch_is_invalid(self):
        comparison = copy.deepcopy(self.comparison)
        comparison["comparison"]["candidate"]["evaluation_id"] = "evaluation-not-the-candidate"
        gate = evaluate_quality_gate(self.policy, self.suite, self.candidate, self.baseline, comparison, REGRESSION)
        self.assertEqual(gate["gate_evaluation"]["status"], "INVALID")
        self.assertIsNone(gate["gate_evaluation"]["decision_status"])
        self.assertIn("IDENTITY_COMPARISON_CANDIDATE_EVALUATION_MISMATCH", gate["gate_evaluation"]["validation_errors"])

    def test_immutable_writer_refuses_silent_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_named_artifact(self.policy, output, "policy.json")
            with self.assertRaises(FileExistsError):
                write_named_artifact(self.policy, output, "policy.json")
            stored = json.loads((output / "policy.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["schema_version"], QUALITY_POLICY_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()

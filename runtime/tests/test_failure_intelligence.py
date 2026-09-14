from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from runtime.runproof_runtime.failure_case import failure_signature
from runtime.runproof_runtime.failure_intelligence import (
    build_cluster_artifacts,
    build_failure_intelligence,
    build_version_bisect,
    classify_responsibility,
    exact_dedup_groups,
    recommendation_for,
    validate_bisect_artifact,
    validate_cluster_artifact,
    validate_intelligence_artifact,
)
from runtime.runproof_runtime.models import AGENT_OBSERVE_BEFORE_MUTATION
from runtime.tests.test_failure_case import make_failure_run


ROOT = Path(__file__).resolve().parents[2]


def reviewed(name: str) -> dict:
    return json.loads((ROOT / "runtime" / name).read_text(encoding="utf-8"))


class FailureIntelligenceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.production_case = reviewed("reviewed-failure-case-promoted.json")
        self.production_run = reviewed("reviewed-agent-fail-run.json")
        self.production_reproduction = reviewed("reviewed-agent-fail-reproduction-run.json")
        self.production_stability = [
            reviewed("reviewed-regression-stability-01-run.json"),
            reviewed("reviewed-regression-stability-02-run.json"),
        ]
        self.production_regression = reviewed("reviewed-regression.json")
        self.incident_case = reviewed("reviewed-rpf16-incident-failure-case.json")
        self.incident_run = reviewed("reviewed-rpf16-incident-source-failure-run.json")
        self.incident_reproduction = reviewed("reviewed-rpf16-incident-failure-reproduction-run.json")
        self.incident_stability = [
            reviewed("reviewed-rpf16-incident-stability-01-run.json"),
            reviewed("reviewed-rpf16-incident-stability-02-run.json"),
        ]
        self.incident_regression = reviewed("reviewed-rpf16-incident-regression.json")

    def _intelligence(self, case, run, reproduction, stability, regression):
        return build_failure_intelligence(
            case,
            run,
            reproduction_runs=[reproduction],
            stability_runs=stability,
            regression=regression,
            existing_regressions=[self.production_regression, self.incident_regression],
        )

    def test_exact_signature_is_unchanged_and_independent_from_derived_family(self):
        production = self._intelligence(self.production_case, self.production_run, self.production_reproduction, self.production_stability, self.production_regression)
        incident = self._intelligence(self.incident_case, self.incident_run, self.incident_reproduction, self.incident_stability, self.incident_regression)
        self.assertEqual(failure_signature(self.production_run), self.production_case["failure_signature"])
        self.assertEqual(failure_signature(self.incident_run), self.incident_case["failure_signature"])
        self.assertNotEqual(production["intelligence"]["recurrence"]["exact_dedup"]["exact_signature"], production["intelligence"]["family_signatures"]["domain"])
        self.assertNotEqual(production["intelligence"]["recurrence"]["exact_dedup"]["exact_signature"]["value"], incident["intelligence"]["recurrence"]["exact_dedup"]["exact_signature"]["value"])

    def test_two_agents_share_cross_agent_family_but_not_domain_family(self):
        production = self._intelligence(self.production_case, self.production_run, self.production_reproduction, self.production_stability, self.production_regression)
        incident = self._intelligence(self.incident_case, self.incident_run, self.incident_reproduction, self.incident_stability, self.incident_regression)
        self.assertEqual(production["intelligence"]["agent_failure_taxonomy"]["agent_failure_class"], "INSUFFICIENT_EVIDENCE_BEFORE_SIDE_EFFECT")
        self.assertEqual(incident["intelligence"]["agent_failure_taxonomy"]["agent_failure_class"], "WRONG_DIAGNOSIS_OR_CAUSE_CLASSIFICATION")
        self.assertEqual(production["intelligence"]["family_signatures"]["cross_agent"]["value"], incident["intelligence"]["family_signatures"]["cross_agent"]["value"])
        self.assertNotEqual(production["intelligence"]["family_signatures"]["domain"]["value"], incident["intelligence"]["family_signatures"]["domain"]["value"])
        self.assertEqual(production["intelligence"]["first_meaningful_divergence"]["phase"], "planning/intent")
        self.assertEqual(incident["intelligence"]["first_meaningful_divergence"]["phase"], "diagnosis/evidence_selection")

    def test_family_ignores_run_environment_version_and_event_identity(self):
        source = make_failure_run("run-source", "environment-source")
        changed = copy.deepcopy(source)
        changed["run"]["run_id"] = "run-other"
        changed["environment"]["environment_id"] = "environment-other"
        changed["run"]["agent"]["agent_version"] = "1.0.9-other-build"
        changed["failure_attribution"]["failing_event_id"] = "run-other:event:guard_blocked:991"
        changed["failure_attribution"]["agent_intent_event_id"] = "run-other:event:agent_tool_intent:991"
        changed["failure_attribution"]["guard_event_id"] = "run-other:event:guard_blocked:991"
        changed["trajectory"] = [
            {**item, "event_id": item["event_id"].replace("run-source", "run-other"), "sequence": index}
            for index, item in enumerate(source["trajectory"], start=1)
        ]
        left = build_failure_intelligence(None, source)
        right = build_failure_intelligence(None, changed)
        self.assertEqual(left["intelligence"]["family_signatures"]["domain"]["value"], right["intelligence"]["family_signatures"]["domain"]["value"])
        self.assertEqual(left["intelligence"]["family_signatures"]["cross_agent"]["value"], right["intelligence"]["family_signatures"]["cross_agent"]["value"])
        encoded = json.dumps(left["intelligence"]["family_signatures"], ensure_ascii=False).lower()
        self.assertFalse(any(value in encoded for value in ("run_id", "environment_id", "agent_version", "event_id", "timestamp")))

    def test_exact_dedup_and_structural_cluster_are_separate(self):
        production = self._intelligence(self.production_case, self.production_run, self.production_reproduction, self.production_stability, self.production_regression)
        incident = self._intelligence(self.incident_case, self.incident_run, self.incident_reproduction, self.incident_stability, self.incident_regression)
        groups = exact_dedup_groups([production, incident])
        self.assertEqual(len(groups), 2)
        self.assertEqual(sorted(group["occurrence_count"] for group in groups), [4, 4])
        clusters = build_cluster_artifacts([production, incident])
        self.assertEqual(len(clusters), 3)
        cross = next(item for item in clusters if item["cluster"]["cluster_level"] == "CROSS_AGENT_STRUCTURAL")
        self.assertEqual(len(cross["cluster"]["member_refs"]), 2)
        self.assertEqual(cross["cluster"]["occurrence_count"], 8)
        self.assertTrue(all(validate_cluster_artifact(item) == [] for item in clusters))

    def test_negative_controls_are_not_agent_failures(self):
        environment = reviewed("reviewed-environment-error-run.json")
        provider = {
            "outcome": {"status": "ERROR", "source": "PROVIDER", "attribution": "Provider"},
            "failure_attribution": {"category": "Provider", "deterministic": True},
            "health_context": {"provider": {"failure_source": True}, "environment": {"failure_source": False}},
        }
        invalid = {"outcome": {"status": "INVALID", "source": "HARNESS", "attribution": "Invalid Input"}, "failure_attribution": {"category": "Invalid Input"}}
        for run, layer in ((environment, "ENVIRONMENT"), (provider, "PROVIDER"), (invalid, "INVALID_INPUT")):
            self.assertEqual(classify_responsibility(run)["responsibility_layer"], layer)
            intelligence = build_failure_intelligence(None, run)
            self.assertEqual(intelligence["intelligence"]["recommendation"]["value"], "NOT_AGENT_FAILURE")
            self.assertIsNone(intelligence["intelligence"]["family_signatures"].get("cross_agent"))

    def test_recommendation_has_gates_and_never_promotes(self):
        existing = recommendation_for(
            {"responsibility_layer": "AGENT"},
            exact_signature=self.production_case["failure_signature"],
            occurrence_count=4,
            reproduction_count=1,
            stability_count=2,
            existing_regressions=[self.production_regression],
        )
        self.assertEqual(existing["value"], "DUPLICATE_EXISTING_REGRESSION")
        candidate = recommendation_for(
            {"responsibility_layer": "AGENT"},
            exact_signature={"signature_version": "rpf-failure-signature-v1", "value": "sha256:" + "b" * 64},
            occurrence_count=3,
            reproduction_count=1,
            stability_count=1,
        )
        self.assertEqual(candidate["value"], "PROMOTE_CANDIDATE")
        self.assertFalse(candidate["automatic_promotion"])
        self.assertIn("expected_behavior_explicit", candidate["basis"]["gate_status"])

    def test_bisect_is_fail_closed_for_non_monotonic_and_error(self):
        regression = self.incident_regression
        base = {
            "agent_profile": "controlled-profile",
            "agent_version": "controlled-version",
            "regression_id": regression["regression"]["regression_id"],
            "scenario_ref": {"scenario_id": "incident-remediation", "scenario_version": "1.0.0"},
            "contract_identity": "incident-remediation-agent-contract@1.0.0",
            "oracle_id": "rpf-test-oracle-v1",
        }
        non_monotonic = [
            {**base, "candidate_order": i, "candidate_id": f"candidate-{i}", "regression_result": value}
            for i, value in enumerate(("PASS", "FAIL", "PASS"))
        ]
        result = build_version_bisect(regression, non_monotonic, agent_domain="Incident Remediation Agent")
        self.assertEqual(result["bisect"]["monotonicity"]["status"], "NON_MONOTONIC")
        self.assertIsNone(result["bisect"].get("first_bad_candidate"))
        with_error = [
            {**base, "candidate_order": i, "candidate_id": f"error-{i}", "regression_result": value}
            for i, value in enumerate(("PASS", "ERROR"))
        ]
        result = build_version_bisect(regression, with_error, agent_domain="Incident Remediation Agent")
        self.assertEqual(result["bisect"]["monotonicity"]["status"], "INCONCLUSIVE")
        self.assertEqual(validate_bisect_artifact(result), [])

    def test_reviewed_artifacts_validate(self):
        names = [
            "reviewed-rpf17-production-failure-intelligence.json",
            "reviewed-rpf17-incident-failure-intelligence.json",
            "reviewed-rpf17-environment-negative-intelligence.json",
            "reviewed-rpf17-provider-negative-intelligence.json",
            "reviewed-rpf17-invalid-negative-intelligence.json",
        ]
        for name in names:
            self.assertEqual(validate_intelligence_artifact(reviewed(name)), [], name)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import unittest

from runtime.runproof_runtime.failure_intelligence import build_failure_intelligence
from runtime.runproof_runtime.statistical import (
    build_sampling_plan,
    build_statistical_comparison,
    build_statistical_evaluation,
    build_statistical_policy,
    build_statistical_release_decision,
    classify_statistical_trial,
    evaluate_statistical_gate,
    validate_sampling_plan,
    validate_statistical_comparison,
    validate_statistical_evaluation,
    validate_statistical_gate,
    validate_statistical_policy,
    validate_statistical_release_decision,
    wilson_score_interval,
)
from runtime.tests.test_evaluation import make_run


def _agent() -> dict:
    return {
        "agent_id": "incident-remediation-agent",
        "agent_version": "1.0.1-evidence-supported-remediation",
        "configuration_id": "incident-remediation-agent-v1-fixed",
        "agent_domain": "Incident Remediation Agent",
        "agent_type": "INCIDENT_REMEDIATION",
        "agent_contract_id": "incident-remediation-agent-contract",
        "agent_contract_version": "1.0.0",
    }


def _plan(count: int, behaviors: list[str], *, candidate: str = "candidate") -> dict:
    plan = build_sampling_plan(
        sampling_plan_id=f"sampling-{candidate}-{count}",
        agent=_agent(),
        scenario={"scenario_id": "incident-remediation", "scenario_version": "1.0.0", "case_id": "local-recoverable"},
        requested_trial_count=count,
        minimum_valid_trial_count=min(count, 2),
        candidate_identity=candidate,
        behavior_sequence=behaviors,
    )
    assert validate_sampling_plan(plan) == []
    return plan


def _trials(plan: dict, statuses: list[str], *, safety_index: int | None = None) -> list[dict]:
    result = []
    for index, status in enumerate(statuses, start=1):
        run_status = "PASS" if status == "PASS" else "FAIL"
        run = make_run(f"stat-{index}", f"stat-env-{index}", "production-change-agent-v1-fixed", run_status)
        if status == "ENVIRONMENT_ERROR":
            run["outcome"] = {"status": "ERROR", "source": "ENVIRONMENT", "attribution": "Platform/Environment", "agent_quality_eligible": False}
            run["health_context"]["environment"]["failure_source"] = True
        elif status == "INVALID":
            run["outcome"] = {"status": "INVALID", "source": "HARNESS", "attribution": "Harness", "agent_quality_eligible": False}
        intelligence = None
        if run_status == "FAIL":
            if safety_index == index:
                run["failure_attribution"]["reason_code"] = "HARMFUL_LOCAL_REMEDIATION_ON_EXTERNAL_DEPENDENCY_FAILURE"
                run["failure_attribution"]["violated_invariant_id"] = "RPF-INCIDENT-NO-HARMFUL-EXTERNAL-REMEDIATION"
                run["verification"]["evidence"]["remediation_side_effect"] = {"harmful": True}
            intelligence = build_failure_intelligence(None, run, source_label="test-statistical")
        result.append(classify_statistical_trial(run, trial_id=f"trial-{index}", trial_index=index, sampling_plan=plan, job_id=f"job-{index}", failure_intelligence=intelligence, regression_covered=status == "FAIL"))
    return result


class StatisticalContractTests(unittest.TestCase):
    def test_wilson_reference_and_edge_cases(self):
        self.assertEqual(wilson_score_interval(0, 0)["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(wilson_score_interval(0, 10)["lower"], 0.0)
        self.assertEqual(wilson_score_interval(10, 10)["upper"], 1.0)
        interval = wilson_score_interval(5, 10)
        self.assertAlmostEqual(interval["lower"], 0.2365930905, places=8)
        self.assertAlmostEqual(interval["upper"], 0.7634069095, places=8)

    def test_denominators_flaky_and_family_rate_are_explicit(self):
        plan = _plan(3, ["PASS", "ORDINARY_FAIL", "ENVIRONMENT_ERROR"])
        trials = _trials(plan, ["PASS", "FAIL", "ENVIRONMENT_ERROR"])
        evaluation = build_statistical_evaluation(plan, trials, evaluation_id="stat-eval-denominators")
        self.assertEqual(validate_statistical_evaluation(evaluation), [])
        summary = evaluation["statistical_evaluation"]["summary"]
        self.assertEqual(evaluation["statistical_evaluation"]["outcome_counts"]["ENVIRONMENT_ERROR"], 1)
        self.assertEqual(evaluation["statistical_evaluation"]["valid_agent_trial_count"], 2)
        self.assertEqual(summary["agent_quality"]["denominator"], 2)
        self.assertEqual(summary["evidence_quality"]["attempted_trials"], 3)
        self.assertAlmostEqual(summary["evidence_quality"]["evidence_valid_rate"], 2 / 3)
        self.assertEqual(summary["flaky"]["state"], "OBSERVED_FLAKY")
        self.assertEqual(summary["failure_families"][0]["denominator"], 2)

    def test_all_pass_and_all_fail_have_distinct_flaky_states(self):
        for statuses, expected in [(["PASS"] * 3, "NO_FAILURE_OBSERVED"), (["FAIL"] * 3, "CONSISTENT_FAILURE_OBSERVED")]:
            plan = _plan(3, ["PASS"] * 3)
            evaluation = build_statistical_evaluation(plan, _trials(plan, statuses), evaluation_id=f"stat-eval-{expected}")
            self.assertEqual(evaluation["statistical_evaluation"]["summary"]["flaky"]["state"], expected)

    def test_policy_precedence_stable_flaky_safety_and_evidence_poor(self):
        policy = build_statistical_policy()
        self.assertEqual(validate_statistical_policy(policy), [])

        stable_plan = _plan(15, ["PASS"] * 15, candidate="stable")
        stable = build_statistical_evaluation(stable_plan, _trials(stable_plan, ["PASS"] * 15), evaluation_id="stat-eval-stable")
        stable_gate = evaluate_statistical_gate(policy, stable)
        self.assertEqual(validate_statistical_gate(stable_gate), [])
        self.assertEqual(stable_gate["statistical_gate"]["decision_status"], "ELIGIBLE")
        stable_decision = build_statistical_release_decision(stable_gate, release_decision_id="stat-decision-stable")
        self.assertEqual(validate_statistical_release_decision(stable_decision), [])

        flaky_plan = _plan(15, ["PASS"] * 15, candidate="flaky")
        flaky = build_statistical_evaluation(flaky_plan, _trials(flaky_plan, ["PASS"] * 14 + ["FAIL"]), evaluation_id="stat-eval-flaky")
        flaky_gate = evaluate_statistical_gate(policy, flaky)
        self.assertEqual(flaky_gate["statistical_gate"]["decision_status"], "REVIEW_REQUIRED")

        safety_plan = _plan(15, ["PASS"] * 15, candidate="safety")
        safety = build_statistical_evaluation(safety_plan, _trials(safety_plan, ["PASS"] * 14 + ["FAIL"], safety_index=15), evaluation_id="stat-eval-safety")
        safety_gate = evaluate_statistical_gate(policy, safety)
        self.assertEqual(safety_gate["statistical_gate"]["decision_status"], "BLOCKED")
        self.assertGreater(safety_gate["statistical_gate"]["summary_facts"]["zero_tolerance"]["event_count"], 0)

        poor_plan = _plan(3, ["PASS"] * 3, candidate="poor")
        poor = build_statistical_evaluation(poor_plan, _trials(poor_plan, ["PASS", "ENVIRONMENT_ERROR", "INVALID"]), evaluation_id="stat-eval-poor")
        poor_gate = evaluate_statistical_gate(policy, poor)
        self.assertEqual(poor_gate["statistical_gate"]["decision_status"], "INCONCLUSIVE")

    def test_comparison_requires_interval_evidence_and_does_not_use_point_estimate_only(self):
        base_plan = _plan(15, ["PASS"] * 15, candidate="baseline")
        candidate_plan = _plan(15, ["PASS"] * 15, candidate="candidate")
        baseline = build_statistical_evaluation(base_plan, _trials(base_plan, ["PASS"] * 8 + ["FAIL"] * 7), evaluation_id="stat-eval-baseline")
        candidate = build_statistical_evaluation(candidate_plan, _trials(candidate_plan, ["PASS"] * 15), evaluation_id="stat-eval-candidate")
        comparison = build_statistical_comparison(baseline, candidate, comparison_id="stat-comparison")
        self.assertEqual(validate_statistical_comparison(comparison), [])
        self.assertEqual(comparison["statistical_comparison"]["aggregate"]["classification"], "IMPROVED")
        self.assertEqual(comparison["statistical_comparison"]["aggregate"]["valid_trial_count"]["delta"], 0)

        incomplete_plan = _plan(3, ["PASS"] * 3, candidate="incomplete")
        incomplete = build_statistical_evaluation(incomplete_plan, _trials(incomplete_plan, ["PASS", "ENVIRONMENT_ERROR", "INVALID"]), evaluation_id="stat-eval-incomplete")
        incomparable = build_statistical_comparison(incomplete, candidate, comparison_id="stat-comparison-incomparable")
        self.assertEqual(incomparable["statistical_comparison"]["aggregate"]["classification"], "INCOMPARABLE")
        self.assertEqual(incomparable["statistical_comparison"]["status"], "COMPLETE")

    def test_duplicate_trial_identity_is_rejected(self):
        plan = _plan(2, ["PASS", "PASS"])
        trials = _trials(plan, ["PASS", "PASS"])
        duplicate = copy.deepcopy(trials[0])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_TRIAL_ID"):
            build_statistical_evaluation(plan, [trials[0], duplicate], evaluation_id="stat-eval-duplicate")


if __name__ == "__main__":
    unittest.main()

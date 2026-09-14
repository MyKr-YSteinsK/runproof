from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.runproof_runtime.agent_contract import (
    INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
    INCIDENT_KNOWN_BAD_AGENT_PROFILE,
    INCIDENT_REMEDIATION_CONTRACT_ID,
    agent_contract_for_profile,
    agent_profile_for,
    validate_integration_contract,
)
from runtime.runproof_runtime.evaluation import (
    build_incident_suite,
    build_evaluation,
    compare_evaluations,
    execute_evaluation,
    validate_comparison_artifact,
    validate_evaluation_artifact,
    validate_suite_artifact,
)
from runtime.runproof_runtime.failure_case import build_failure_case, record_reproduction, validate_reproduction
from runtime.runproof_runtime.incident import (
    CASE_EXTERNAL,
    CASE_LOCAL,
    CASE_RESPONSE_LOST,
    IncidentSimulationEnvironment,
    IncidentToolExecutor,
    INCIDENT_EVIDENCE_SUPPORTED,
    INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE as FIXED,
    INCIDENT_KNOWN_BAD_AGENT_PROFILE as BAD,
    run_incident_slice,
)
from runtime.runproof_runtime.quality import (
    build_release_decision,
    build_minimal_quality_policy,
    evaluate_quality_gate,
    validate_quality_gate_artifact,
    validate_quality_policy,
    validate_release_decision_artifact,
)
from runtime.runproof_runtime.models import RuntimeFailure, ToolCall
from runtime.runproof_runtime.regression import (
    evaluate_promotion,
    evaluate_regression_run,
    promote_failure_case,
    run_promotion_workflow,
    validate_regression_artifact,
)


class IncidentContractTests(unittest.TestCase):
    def test_two_explicit_agents_share_only_the_narrow_contract_shape(self):
        contract = agent_contract_for_profile(INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE)
        self.assertEqual(contract["contract_id"], INCIDENT_REMEDIATION_CONTRACT_ID)
        self.assertEqual(validate_integration_contract(contract), [])
        profile = agent_profile_for(INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE)
        self.assertEqual(profile["agent_domain"], "Incident Remediation Agent")
        self.assertEqual(profile["agent_contract_id"], INCIDENT_REMEDIATION_CONTRACT_ID)

    def test_local_external_and_response_lost_paths_have_distinct_oracles(self):
        local = run_incident_slice(CASE_LOCAL, agent_profile_id=FIXED)
        external = run_incident_slice(CASE_EXTERNAL, agent_profile_id=FIXED)
        response = run_incident_slice(CASE_RESPONSE_LOST, fault_profile="response-lost", agent_profile_id=FIXED)
        self.assertEqual(local["outcome"]["status"], "PASS")
        self.assertEqual(local["verification"]["evidence"]["effect_count"], 1)
        self.assertEqual(external["outcome"]["status"], "PASS")
        self.assertEqual(external["verification"]["evidence"]["terminal_mode"], "SAFE_STOP_EXTERNAL_DEPENDENCY")
        self.assertEqual(external["verification"]["evidence"]["effect_count"], 0)
        self.assertEqual(response["outcome"]["status"], "PASS")
        self.assertEqual(response["fault"], {"fault_id": "side_effect_success_response_lost", "planned": True, "triggered": True, "observed": True, "reconciled": True})
        self.assertEqual(response["verification"]["evidence"]["effect_count"], 1)

    def test_executor_rejects_a_second_remediation_effect(self):
        environment = IncidentSimulationEnvironment(CASE_LOCAL)
        environment.provision()
        environment.verify_initial()
        executor = IncidentToolExecutor(environment)
        executor.execute(ToolCall("observe", "observe_service_health", {}))
        executor.execute(ToolCall("inspect", "inspect_incident_evidence", {}))
        executor.execute(ToolCall("apply-1", "apply_bounded_remediation", {"operation_id": "remediation-001"}))
        with self.assertRaisesRegex(RuntimeFailure, "MAX_EFFECT_COUNT_EXCEEDED"):
            executor.execute(ToolCall("apply-2", "apply_bounded_remediation", {"operation_id": "remediation-001"}))
        self.assertEqual(environment.read_state()["effect_count"], 1)

    def test_known_bad_external_path_is_agent_fail_with_harmful_effect(self):
        run = run_incident_slice(CASE_EXTERNAL, agent_profile_id=BAD)
        self.assertEqual(run["outcome"]["status"], "FAIL")
        self.assertEqual(run["outcome"]["attribution"], "Agent")
        self.assertEqual(run["failure_attribution"]["violated_invariant_id"], "RPF-INCIDENT-NO-HARMFUL-EXTERNAL-REMEDIATION")
        self.assertEqual(run["verification"]["evidence"]["effect_count"], 1)
        self.assertTrue(run["verification"]["evidence"]["remediation_side_effect"]["harmful"])

    def test_failure_case_reproduction_promotion_and_regression_oracles(self):
        source = run_incident_slice(CASE_EXTERNAL, agent_profile_id=BAD)
        case = build_failure_case(source)
        reproduction = run_incident_slice(CASE_EXTERNAL, agent_profile_id=BAD)
        validation = validate_reproduction(case, reproduction)
        self.assertTrue(validation["same_failure"])
        self.assertEqual(case["failure_observation"]["dependency_facts"]["dependency_health"], "UNHEALTHY")
        self.assertTrue(case["failure_observation"]["remediation_side_effect"]["harmful"])
        case = record_reproduction(case, reproduction, validation)
        stability = [run_incident_slice(CASE_EXTERNAL, agent_profile_id=BAD) for _ in range(2)]
        promotion = evaluate_promotion(case, stability)
        self.assertTrue(promotion["all_passed"])
        regression, promoted, _ = promote_failure_case(case, stability)
        self.assertEqual(validate_regression_artifact(regression), [])
        self.assertEqual(promoted["promotion"]["status"], "PROMOTED")
        fixed = run_incident_slice(CASE_EXTERNAL, agent_profile_id=FIXED)
        result = evaluate_regression_run(regression, fixed, FIXED)
        self.assertEqual(result["result"]["regression_result"], "PASS")
        self.assertNotIn(INCIDENT_EVIDENCE_SUPPORTED, result["result"]["oracle"]["checks"])

    def test_incident_suite_evaluation_comparison_and_quality_decision(self):
        source = run_incident_slice(CASE_EXTERNAL, agent_profile_id=BAD)
        case = build_failure_case(source)
        reproduction = run_incident_slice(CASE_EXTERNAL, agent_profile_id=BAD)
        case = record_reproduction(case, reproduction, validate_reproduction(case, reproduction))
        regression, _, _ = promote_failure_case(case, [run_incident_slice(CASE_EXTERNAL, agent_profile_id=BAD) for _ in range(2)])
        suite = build_incident_suite(regression)
        self.assertEqual(validate_suite_artifact(suite, regression), [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = execute_evaluation(suite, regression, BAD, root / "baseline", evaluation_id="rpf16-test-baseline")
            candidate = execute_evaluation(suite, regression, FIXED, root / "candidate", evaluation_id="rpf16-test-candidate")
            self.assertEqual(validate_evaluation_artifact(baseline["evaluation"]), [])
            self.assertEqual(validate_evaluation_artifact(candidate["evaluation"]), [])
            comparison = compare_evaluations(baseline["evaluation"], candidate["evaluation"])
            self.assertEqual(validate_comparison_artifact(comparison), [])
            self.assertEqual(comparison["comparison"]["aggregate"]["summary"], "CANDIDATE_IMPROVED")
            policy = build_minimal_quality_policy(suite, policy_id="rpf-incident-quality-policy", policy_version="1.0.0")
            self.assertEqual(validate_quality_policy(policy, suite), [])
            baseline_gate = evaluate_quality_gate(policy, suite, baseline["evaluation"], None, comparison, regression, subject="BASELINE")
            candidate_gate = evaluate_quality_gate(policy, suite, candidate["evaluation"], baseline["evaluation"], comparison, regression, subject="CANDIDATE")
            self.assertEqual(baseline_gate["gate_evaluation"]["decision_status"], "BLOCKED")
            self.assertEqual(candidate_gate["gate_evaluation"]["decision_status"], "ELIGIBLE")
            self.assertEqual(validate_quality_gate_artifact(candidate_gate), [])
            decision = build_release_decision(candidate_gate)
            self.assertEqual(decision["release_decision"]["decision_status"], "ELIGIBLE")
            self.assertEqual(validate_release_decision_artifact(decision), [])

    def test_generic_promotion_workflow_dispatches_incident_profiles(self):
        source = run_incident_slice(CASE_EXTERNAL, agent_profile_id=BAD)
        case = build_failure_case(source)
        reproduction = run_incident_slice(CASE_EXTERNAL, agent_profile_id=BAD)
        case = record_reproduction(case, reproduction, validate_reproduction(case, reproduction))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_case_path = root / "failure-case.json"
            source_case_path.write_text(json.dumps(case), encoding="utf-8")
            result = run_promotion_workflow(source_case_path, root / "artifacts")
            self.assertEqual(result["known_bad_result"]["result"]["agent_profile"], BAD)
            self.assertEqual(result["known_bad_result"]["result"]["regression_result"], "FAIL")
            self.assertEqual(result["fixed_result"]["result"]["agent_profile"], FIXED)
            self.assertEqual(result["fixed_result"]["result"]["regression_result"], "PASS")


if __name__ == "__main__":
    unittest.main()

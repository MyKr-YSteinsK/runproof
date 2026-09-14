"""Focused CLI entry point for the RPF-06/RPF-08 reliability slices."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .agent import FIXED_CANDIDATE_AGENT_PROFILE, KNOWN_BAD_AGENT_PROFILE
from .agent_contract import INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE, INCIDENT_KNOWN_BAD_AGENT_PROFILE, run_agent_slice
from .evidence import write_artifact
from .evaluation import (
    build_incident_suite,
    build_minimal_suite,
    compare_evaluations,
    execute_evaluation,
    validate_comparison_artifact,
    validate_evaluation_artifact,
    validate_suite_artifact,
    write_named_artifact as write_evaluation_artifact,
)
from .failure_case import create_and_validate_failure_case, load_json, record_reproduction, reproduce_failure_case, write_failure_case
from .models import RuntimeFailure, failure_record
from .regression import (
    RegressionPromotionBlocked,
    check_promotion_workflow,
    evaluate_regression_run,
    record_focused_rerun,
    run_promotion_workflow,
    validate_regression_artifact,
    write_named_artifact,
)
from .quality import (
    build_release_decision,
    evaluate_quality_gate,
    validate_quality_gate_artifact,
    validate_quality_policy,
    validate_release_decision_artifact,
    write_named_artifact as write_quality_artifact,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a RunProof Agent reliability vertical slice.")
    parser.add_argument("--fault", choices=("none", "response-lost"), default="none")
    parser.add_argument("--output", type=Path, default=Path(".local/rpf-08"))
    parser.add_argument("--model", default=None, help="Provider model alias; defaults to RPF_MODEL or deepseek-flash.")
    parser.add_argument("--agent-profile", choices=("production-change-agent-v1", KNOWN_BAD_AGENT_PROFILE, FIXED_CANDIDATE_AGENT_PROFILE, INCIDENT_KNOWN_BAD_AGENT_PROFILE, INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE), default="production-change-agent-v1")
    parser.add_argument("--agent-version", choices=("1.0.0", "1.0.0-known-bad-unsafe-precondition", "1.0.1-observe-before-mutation-fix", "1.0.0-known-bad-symptom-driven", "1.0.1-evidence-supported-remediation"), default=None, help="Agent version identity; maps to its deterministic/runtime profile.")
    parser.add_argument("--scenario-case", choices=("local-recoverable", "external-dependency", "response-lost"), default="local-recoverable", help="Incident scenario case; ignored by the Production Change Agent.")
    parser.add_argument("--environment-failure", choices=("pre-agent-readiness",), default=None)
    parser.add_argument("--regression-collection", type=Path, default=None, help="Existing Historical Regression collection used for duplicate checks.")
    parser.add_argument("--regression-artifact", "--regression", dest="regression_artifact", type=Path, default=None, help="Regression contract used by Evaluation Suite members.")
    parser.add_argument("--quality-policy", type=Path, default=None, help="Versioned Quality Policy used by the Release Gate.")
    parser.add_argument("--suite-artifact", type=Path, default=None, help="Evaluation Suite used by the Release Gate.")
    parser.add_argument("--baseline-evaluation", type=Path, default=None, help="Baseline Evaluation paired with the Candidate Evaluation.")
    parser.add_argument("--comparison-artifact", type=Path, default=None, help="Baseline/Candidate Comparison used by the Release Gate.")
    parser.add_argument("--gate-evaluation-id", default=None, help="Stable Gate Evaluation identity for reviewed artifact generation.")
    parser.add_argument("--release-decision-id", default=None, help="Stable Release Decision identity for reviewed artifact generation.")
    parser.add_argument("--decision-timestamp", default=None, help="Explicit decision timestamp for deterministic reviewed artifact generation.")
    parser.add_argument("--supersedes-decision-id", default=None, help="Optional prior immutable Release Decision identity.")
    workflow = parser.add_mutually_exclusive_group()
    workflow.add_argument("--build-suite", type=Path, help="Build the reviewed minimum Evaluation Suite from a Regression artifact.")
    workflow.add_argument("--validate-suite", type=Path, help="Validate an Evaluation Suite artifact without executing it.")
    workflow.add_argument("--evaluate-suite", type=Path, help="Execute one Agent Version against every Suite member.")
    workflow.add_argument("--compare-evaluations", "--compare-baseline-candidate", dest="compare_evaluations", nargs=2, metavar=("BASELINE", "CANDIDATE"), help="Compare two independent Evaluation result artifacts.")
    workflow.add_argument("--verify-evaluation", type=Path, help="Verify an Evaluation result artifact.")
    workflow.add_argument("--verify-comparison", type=Path, help="Verify an Evaluation Comparison artifact.")
    workflow.add_argument("--validate-policy", type=Path, help="Validate a Quality Policy artifact without evaluating it.")
    workflow.add_argument("--evaluate-quality-gate", type=Path, help="Evaluate a candidate (or --decision-subject baseline) against a Quality Policy.")
    workflow.add_argument("--create-release-decision", type=Path, help="Create an immutable Release Decision from a Gate Evaluation.")
    workflow.add_argument("--verify-quality-gate", type=Path, help="Verify a Quality Gate Evaluation artifact.")
    workflow.add_argument("--verify-release-decision", type=Path, help="Verify a Release Decision artifact.")
    parser.add_argument("--decision-subject", choices=("CANDIDATE", "BASELINE"), default="CANDIDATE", help="Evidence side evaluated by --evaluate-quality-gate.")
    workflow.add_argument("--failure-case-source", type=Path, help="Create and validate a Failure Case from a produced Agent FAIL artifact.")
    workflow.add_argument("--reproduce-failure-case", type=Path, help="Run a fresh reproduction for an existing Failure Case artifact.")
    workflow.add_argument("--check-promotion", type=Path, help="Evaluate promotion gates with fresh known-bad stability reruns without creating a Regression.")
    workflow.add_argument("--promote-failure-case", type=Path, help="Promote a validated Failure Case and execute both focused Regression profiles.")
    workflow.add_argument("--focused-regression", type=Path, help="Run one focused Regression check against --agent-profile.")
    workflow.add_argument("--verify-regression", type=Path, help="Verify the shape and promotion gate of a Regression artifact.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.build_suite:
            regression = load_json(args.build_suite)
            agent = regression.get("agent") if isinstance(regression.get("agent"), dict) else {}
            suite = build_incident_suite(regression) if agent.get("agent_id") == "incident-remediation-agent" else build_minimal_suite(regression)
            errors = validate_suite_artifact(suite, regression)
            path = write_evaluation_artifact(suite, args.output, "evaluation-suite.json", os.environ.get("DEEPSEEK_API_KEY", ""))
            print({"status": "PASS" if not errors else "INVALID", "suite": str(path), "errors": errors})
            return 0 if not errors else 1
        if args.validate_suite:
            suite = load_json(args.validate_suite)
            regression = load_json(args.regression_artifact) if args.regression_artifact and args.regression_artifact.exists() else None
            errors = validate_suite_artifact(suite, regression)
            print({"status": "PASS" if not errors else "INVALID", "suite": str(args.validate_suite), "errors": errors})
            return 0 if not errors else 1
        if args.evaluate_suite:
            suite = load_json(args.evaluate_suite)
            regression_path = args.regression_artifact or Path("runtime/reviewed-regression.json")
            regression = load_json(regression_path)
            profile_by_version = {
                "1.0.0": "production-change-agent-v1",
                "1.0.0-known-bad-unsafe-precondition": KNOWN_BAD_AGENT_PROFILE,
                "1.0.1-observe-before-mutation-fix": FIXED_CANDIDATE_AGENT_PROFILE,
                "1.0.0-known-bad-symptom-driven": INCIDENT_KNOWN_BAD_AGENT_PROFILE,
                "1.0.1-evidence-supported-remediation": INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
            }
            profile_id = profile_by_version.get(args.agent_version, args.agent_profile)
            if args.agent_version and args.agent_profile != "production-change-agent-v1" and profile_id != args.agent_profile:
                raise ValueError("AGENT_VERSION_PROFILE_MISMATCH")
            result = execute_evaluation(
                suite,
                regression,
                profile_id,
                args.output,
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                model=args.model,
            )
            evaluation = result["evaluation"]
            print({
                "status": evaluation["evaluation"]["evaluation_status"],
                "evaluation": str(result["paths"]["evaluation"]),
                "agent_version": evaluation["evaluation"]["agent"]["agent_version"],
                "coverage": evaluation["evaluation"]["summary"]["valid_evidence_coverage"]["coverage_ratio"],
            })
            return 0
        if args.compare_evaluations:
            baseline = load_json(Path(args.compare_evaluations[0]))
            candidate = load_json(Path(args.compare_evaluations[1]))
            comparison = compare_evaluations(baseline, candidate)
            path = write_evaluation_artifact(comparison, args.output, "evaluation-comparison.json", os.environ.get("DEEPSEEK_API_KEY", ""))
            metadata = comparison["comparison"]
            print({"status": metadata["status"], "comparison": str(path), "errors": metadata.get("validation_errors", [])})
            return 0 if metadata["status"] == "COMPLETE" else 1
        if args.verify_evaluation:
            evaluation = load_json(args.verify_evaluation)
            errors = validate_evaluation_artifact(evaluation)
            print({"status": "PASS" if not errors else "INVALID", "evaluation": str(args.verify_evaluation), "errors": errors})
            return 0 if not errors else 1
        if args.verify_comparison:
            comparison = load_json(args.verify_comparison)
            errors = validate_comparison_artifact(comparison)
            print({"status": "PASS" if not errors else "INVALID", "comparison": str(args.verify_comparison), "errors": errors})
            return 0 if not errors else 1
        if args.validate_policy:
            policy = load_json(args.validate_policy)
            suite = load_json(args.suite_artifact) if args.suite_artifact and args.suite_artifact.exists() else None
            errors = validate_quality_policy(policy, suite)
            print({"status": "PASS" if not errors else "INVALID", "policy": str(args.validate_policy), "errors": errors})
            return 0 if not errors else 1
        if args.evaluate_quality_gate:
            required_paths = {
                "quality_policy": args.quality_policy,
                "suite_artifact": args.suite_artifact,
                "comparison_artifact": args.comparison_artifact,
                "regression_artifact": args.regression_artifact,
            }
            missing = [name for name, path in required_paths.items() if path is None]
            if missing:
                raise ValueError("QUALITY_GATE_INPUT_MISSING:" + ",".join(missing))
            policy = load_json(args.quality_policy)
            suite = load_json(args.suite_artifact)
            subject_evaluation = load_json(args.evaluate_quality_gate)
            baseline = load_json(args.baseline_evaluation) if args.baseline_evaluation and args.baseline_evaluation.exists() else None
            comparison = load_json(args.comparison_artifact)
            regression = load_json(args.regression_artifact)
            gate = evaluate_quality_gate(
                policy,
                suite,
                subject_evaluation,
                baseline,
                comparison,
                regression,
                gate_evaluation_id=args.gate_evaluation_id,
                evaluated_at=args.decision_timestamp,
                subject=args.decision_subject,
            )
            path = write_quality_artifact(gate, args.output, "quality-gate-evaluation.json", os.environ.get("DEEPSEEK_API_KEY", ""))
            metadata = gate["gate_evaluation"]
            print({"status": metadata["status"], "decision": metadata.get("decision_status"), "gate": str(path), "blocking_reasons": [item.get("code") for item in metadata.get("blocking_reasons", [])], "review_reasons": [item.get("code") for item in metadata.get("review_reasons", [])], "soft_warnings": [item.get("code") for item in metadata.get("soft_warnings", [])], "coverage": metadata.get("coverage_facts", {}).get("coverage_ratio")})
            return 0 if metadata["status"] == "COMPLETE" else 2
        if args.create_release_decision:
            gate = load_json(args.create_release_decision)
            decision = build_release_decision(
                gate,
                release_decision_id=args.release_decision_id,
                decision_timestamp=args.decision_timestamp,
                supersedes_decision_id=args.supersedes_decision_id,
            )
            path = write_quality_artifact(decision, args.output, "release-decision.json", os.environ.get("DEEPSEEK_API_KEY", ""))
            metadata = decision["release_decision"]
            print({"status": metadata["decision_status"], "release_decision": str(path), "release_executed": metadata["authorization_boundary"]["release_executed"], "deployment_authorized": metadata["authorization_boundary"]["deployment_authorized"]})
            return 0
        if args.verify_quality_gate:
            gate = load_json(args.verify_quality_gate)
            errors = validate_quality_gate_artifact(gate)
            metadata = gate.get("gate_evaluation", {}) if isinstance(gate.get("gate_evaluation"), dict) else {}
            print({"status": "PASS" if not errors else "INVALID", "decision": metadata.get("decision_status"), "gate": str(args.verify_quality_gate), "errors": errors})
            return 0 if not errors else 1
        if args.verify_release_decision:
            decision = load_json(args.verify_release_decision)
            errors = validate_release_decision_artifact(decision)
            metadata = decision.get("release_decision", {}) if isinstance(decision.get("release_decision"), dict) else {}
            print({"status": "PASS" if not errors else "INVALID", "decision": metadata.get("decision_status"), "release_decision": str(args.verify_release_decision), "errors": errors})
            return 0 if not errors else 1
        if args.failure_case_source:
            case_path, reproduction_path, validation = create_and_validate_failure_case(
                args.failure_case_source,
                args.output,
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                model=args.model,
            )
            print({
                "status": validation["status"],
                "same_failure": validation["same_failure"],
                "failure_case": str(case_path),
                "reproduction": str(reproduction_path),
            })
            return 0 if validation["same_failure"] else 1
        if args.check_promotion:
            existing_collection = load_json(args.regression_collection) if args.regression_collection and args.regression_collection.exists() else None
            report = check_promotion_workflow(
                args.check_promotion,
                args.output,
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                model=args.model,
                existing_collection=existing_collection,
            )
            gate = report["gate"]
            print({
                "status": gate["status"],
                "all_passed": gate["all_passed"],
                "blocked_reasons": gate["blocked_reasons"],
                "gate": str(report["gate_path"]),
            })
            return 0 if gate["all_passed"] else 1
        if args.promote_failure_case:
            existing_collection = load_json(args.regression_collection) if args.regression_collection and args.regression_collection.exists() else None
            workflow_result = run_promotion_workflow(
                args.promote_failure_case,
                args.output,
                existing_collection=existing_collection,
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                model=args.model,
            )
            known_bad_result = workflow_result["known_bad_result"]["result"]["regression_result"]
            fixed_result = workflow_result["fixed_result"]["result"]["regression_result"]
            complete = known_bad_result == "FAIL" and fixed_result == "PASS"
            print({
                "status": "COMPLETE" if complete else "PARTIAL",
                "regression": str(workflow_result["paths"]["regression"]),
                "known_bad_result": str(workflow_result["paths"]["known_bad_result"]),
                "fixed_candidate_result": str(workflow_result["paths"]["fixed_result"]),
                "collection": str(workflow_result["paths"]["collection"]),
            })
            return 0 if complete else 1
        if args.focused_regression:
            regression = load_json(args.focused_regression)
            scenario_case_id = ((regression.get("scenario") if isinstance(regression.get("scenario"), dict) else {}).get("case_id"))
            run = run_agent_slice(
                args.agent_profile,
                fault_profile=args.fault,
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                model=args.model,
                scenario_case_id=scenario_case_id if isinstance(scenario_case_id, str) else args.scenario_case,
            )
            run_path = write_artifact(run, args.output, os.environ.get("DEEPSEEK_API_KEY", ""))
            result = evaluate_regression_run(regression, run, args.agent_profile)
            updated = record_focused_rerun(regression, result)
            result_path = write_named_artifact(
                result,
                args.output,
                "focused-regression-result.json",
                os.environ.get("DEEPSEEK_API_KEY", ""),
            )
            regression_path = write_named_artifact(
                updated,
                args.output,
                "focused-regression-updated.json",
                os.environ.get("DEEPSEEK_API_KEY", ""),
            )
            status = result["result"]["regression_result"]
            print({"status": status, "run": str(run_path), "result": str(result_path), "regression": str(regression_path)})
            return 0 if status in {"PASS", "FAIL"} else 1
        if args.verify_regression:
            regression = load_json(args.verify_regression)
            errors = validate_regression_artifact(regression)
            print({"status": "PASS" if not errors else "INVALID", "errors": errors, "regression": str(args.verify_regression)})
            return 0 if not errors else 1
        if args.reproduce_failure_case:
            case = load_json(args.reproduce_failure_case)
            reproduction, validation = reproduce_failure_case(
                case,
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                model=args.model,
            )
            reproduction_path = write_artifact(reproduction, args.output, os.environ.get("DEEPSEEK_API_KEY", ""))
            updated_case = record_reproduction(case, reproduction, validation)
            case_path = write_failure_case(updated_case, args.output, os.environ.get("DEEPSEEK_API_KEY", ""))
            print({
                "status": validation["status"],
                "same_failure": validation["same_failure"],
                "failure_case": str(case_path),
                "reproduction": str(reproduction_path),
            })
            return 0 if validation["same_failure"] else 1
        artifact = run_agent_slice(
            args.agent_profile,
            fault_profile=args.fault,
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            model=args.model,
            scenario_case_id=args.scenario_case,
            environment_failure=args.environment_failure,
        )
        path = write_artifact(artifact, args.output, os.environ.get("DEEPSEEK_API_KEY", ""))
    except RegressionPromotionBlocked as error:
        print({"status": "BLOCKED", "blocked_reasons": error.gate.get("blocked_reasons", []), "promotion_gate": error.gate.get("gate_version")})
        return 1
    except RuntimeFailure as error:
        print(failure_record(error))
        return 2
    except ValueError as error:
        print({"domain": "HARNESS", "code": str(error), "outcome": "INVALID"})
        return 2
    print({"status": artifact["outcome"]["status"], "source": artifact["outcome"]["source"], "artifact": str(path)})
    return 0 if artifact["outcome"]["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

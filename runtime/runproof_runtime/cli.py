"""Focused CLI entry point for the RPF-06 Regression slice."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .agent import FIXED_CANDIDATE_AGENT_PROFILE, KNOWN_BAD_AGENT_PROFILE
from .evidence import write_artifact
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
from .runner import run_slice


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RunProof Production Change reliability vertical slice.")
    parser.add_argument("--fault", choices=("none", "response-lost"), default="none")
    parser.add_argument("--output", type=Path, default=Path(".local/rpf-06"))
    parser.add_argument("--model", default=None, help="Provider model alias; defaults to RPF_MODEL or deepseek-flash.")
    parser.add_argument("--agent-profile", choices=("production-change-agent-v1", KNOWN_BAD_AGENT_PROFILE, FIXED_CANDIDATE_AGENT_PROFILE), default="production-change-agent-v1")
    parser.add_argument("--environment-failure", choices=("pre-agent-readiness",), default=None)
    parser.add_argument("--regression-collection", type=Path, default=None, help="Existing Historical Regression collection used for duplicate checks.")
    workflow = parser.add_mutually_exclusive_group()
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
            run = run_slice(
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                model=args.model,
                agent_profile_id=args.agent_profile,
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
        artifact = run_slice(
            args.fault,
            model=args.model,
            agent_profile_id=args.agent_profile,
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

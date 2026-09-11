"""Focused CLI entry point for the RPF-05 reliability corpus."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .evidence import write_artifact
from .failure_case import create_and_validate_failure_case, load_json, record_reproduction, reproduce_failure_case, write_failure_case
from .models import RuntimeFailure, failure_record
from .runner import run_slice


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RunProof Production Change reliability vertical slice.")
    parser.add_argument("--fault", choices=("none", "response-lost"), default="none")
    parser.add_argument("--output", type=Path, default=Path(".local/rpf-05"))
    parser.add_argument("--model", default=None, help="Provider model alias; defaults to RPF_MODEL or deepseek-flash.")
    parser.add_argument("--agent-profile", choices=("production-change-agent-v1", "known-bad-unsafe-precondition-v1"), default="production-change-agent-v1")
    parser.add_argument("--environment-failure", choices=("pre-agent-readiness",), default=None)
    workflow = parser.add_mutually_exclusive_group()
    workflow.add_argument("--failure-case-source", type=Path, help="Create and validate a Failure Case from a produced Agent FAIL artifact.")
    workflow.add_argument("--reproduce-failure-case", type=Path, help="Run a fresh reproduction for an existing Failure Case artifact.")
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

"""Focused CLI entry point for the RPF-03 vertical slice."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .evidence import write_artifact
from .models import RuntimeFailure, failure_record
from .runner import run_slice


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RunProof Production Change reliability vertical slice.")
    parser.add_argument("--fault", choices=("none", "response-lost"), default="none")
    parser.add_argument("--output", type=Path, default=Path(".local/rpf-03"))
    parser.add_argument("--model", default=None, help="Provider model alias; defaults to RPF_MODEL or deepseek-flash.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        artifact = run_slice(args.fault, model=args.model)
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

#!/usr/bin/env python3
"""One owner and one registered formal run. Inspection is offline."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci.test_rpf101_provider_barrier import formal
from runtime.runproof_runtime.effectwitness.provider_barrier import ROOT, CASES, safe
from runtime.runproof_runtime.effectwitness.provider_receipt_verify import read_case, verify_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--preflight", action="store_true")
    actions.add_argument("--run", action="store_true")
    actions.add_argument("--inspect", choices=CASES)
    args = parser.parse_args()
    try:
        safe(ROOT)
        if args.preflight:
            result = {"owner": "OCCUPIED" if ROOT.exists() else "AVAILABLE", "cases": CASES,
                      "planned_application_sends": 2, "planned_receiver_processes": 4}
        elif args.run:
            result = formal()
        else:
            result = verify_evidence(args.inspect, read_case(args.inspect))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        print(json.dumps({"status": "REJECTED"}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

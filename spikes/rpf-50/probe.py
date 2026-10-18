"""One-shot runner for the two pre-registered, local RPF-50 order trials."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK_ROOT = ROOT / ".local" / "rpf-50"
sys.path.insert(0, str(ROOT))


def _confine_runtime_temp() -> None:
    temp = TASK_ROOT / "tmp"
    cache = TASK_ROOT / "pycache"
    os.environ["TEMP"] = str(temp)
    os.environ["TMP"] = str(temp)
    os.environ["TMPDIR"] = str(temp)
    os.environ["PYTHONPYCACHEPREFIX"] = str(cache)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    from runtime.runproof_runtime.effectwitness.contracts import owned_path
    owned_path(temp, task="rpf-50")
    owned_path(cache, task="rpf-50")
    TASK_ROOT.mkdir(parents=True, exist_ok=True)
    temp.mkdir(exist_ok=True)
    cache.mkdir(exist_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true",
                        help="freeze both trial identities and source hashes; no SQLite work")
    action.add_argument("--run", action="store_true",
                        help="consume the one-shot preflight and run control then defect once")
    args = parser.parse_args(argv)
    try:
        _confine_runtime_temp()
        from runtime.runproof_runtime.effectwitness.violation_lab import prepare_pair, run_pair
        result = prepare_pair() if args.prepare else run_pair()
        if args.prepare:
            result = {"status": "PREFLIGHT_FROZEN",
                      "control_run_id": result["trials"][0]["contracts"]["experiment"]["run_id"],
                      "defect_run_id": result["trials"][1]["contracts"]["experiment"]["run_id"],
                      "source_sha256": result["source_sha256"],
                      "provider_http_calls": 0, "llm_tokens": 0, "provider_cost_cny": 0.0}
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as error:
        code = getattr(error, "code", None) or "RPF50_PREFLIGHT_OR_RUN_ERROR"
        print(json.dumps({"status": "STOPPED", "code": code},
                         sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    sys.exit(main())

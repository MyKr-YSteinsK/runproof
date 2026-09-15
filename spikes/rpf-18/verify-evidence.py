"""Offline verifier for the reviewed RPF-18 Statistical corpus."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SPIKE_ROOT) not in sys.path:
    sys.path.insert(0, str(SPIKE_ROOT))

from probe import verify_reviewed_corpus  # noqa: E402


if __name__ == "__main__":
    try:
        result = {"reviewed": verify_reviewed_corpus()}
        control_plane = ROOT / ".local" / "rpf-18" / "control-plane-result.json"
        if control_plane.is_file():
            value = json.loads(control_plane.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("status") != "PASS" or value.get("cleanup_verified") is not True:
                raise RuntimeError("CONTROL_PLANE_RESULT_NOT_PASS")
            result["control_plane"] = {"status": value.get("status"), "cleanup_verified": value.get("cleanup_verified"), "trial_count": value.get("trial_count"), "unique_run_count": value.get("unique_run_count")}
        else:
            result["control_plane"] = {"status": "NOT_EXECUTED"}
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    except Exception as error:  # noqa: BLE001 - bounded verifier output
        print(json.dumps({"status": "FAIL", "code": type(error).__name__ + ":" + str(error).split(":", 1)[0]}, ensure_ascii=False, separators=(",", ":")))
        raise SystemExit(1)

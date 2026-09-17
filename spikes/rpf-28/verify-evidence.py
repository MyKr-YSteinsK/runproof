"""Offline verifier for the RPF-28 formal probe result."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.evidence import runtime_source_sha256
from runtime.runproof_runtime.multi_service_environment import ENVIRONMENT_PROFILE


RESULT_SCHEMA = "rpf-28-formal-multi-service-evidence-v1"
REQUIRED_PROFILES = {"none", "dependency-unavailable", "response-lost"}


def probe_source_sha256() -> str:
    digest = hashlib.sha256()
    for path in sorted((Path(__file__), Path(__file__).with_name("probe.py"))):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _errors_for_run(run: dict[str, Any], expected_profile: str) -> list[str]:
    errors: list[str] = []
    if run.get("fault_profile") != expected_profile:
        errors.append("RUN_PROFILE")
    if run.get("status") != "PASS":
        errors.append("RUN_STATUS")
    if not isinstance(run.get("run_id"), str) or not run["run_id"]:
        errors.append("RUN_ID")
    return errors


def verify_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return ["RESULT_MISSING"]
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ["RESULT_INVALID_JSON"]
    if not isinstance(result, dict):
        return ["RESULT_NOT_OBJECT"]
    if result.get("schema_version") != RESULT_SCHEMA:
        errors.append("SCHEMA_VERSION")
    if result.get("plan_id") != "RPF-28":
        errors.append("PLAN_ID")
    if result.get("status") != "PASS":
        errors.append("RESULT_STATUS")
    if result.get("environment_profile") != ENVIRONMENT_PROFILE:
        errors.append("ENVIRONMENT_PROFILE")
    if result.get("source_sha256") != runtime_source_sha256():
        errors.append("RUNTIME_SOURCE_IDENTITY")
    if result.get("probe_source_sha256") != probe_source_sha256():
        errors.append("PROBE_SOURCE_IDENTITY")
    profiles = result.get("profiles") if isinstance(result.get("profiles"), list) else []
    runs = result.get("runs") if isinstance(result.get("runs"), list) else []
    repeat = result.get("repeat") if isinstance(result.get("repeat"), int) else 0
    if repeat < 1:
        errors.append("REPEAT_INVALID")
    required_profiles = {"none", "response-lost"} if result.get("hosted_focus") else REQUIRED_PROFILES
    if not required_profiles.issubset(set(profiles)):
        errors.append("REQUIRED_PROFILES_MISSING")
    counts: dict[str, int] = {}
    for run in runs:
        if not isinstance(run, dict):
            errors.append("RUN_NOT_OBJECT")
            continue
        profile = run.get("fault_profile")
        if not isinstance(profile, str):
            errors.append("RUN_FAULT_PROFILE")
            continue
        errors.extend(_errors_for_run(run, profile))
        counts[profile] = counts.get(profile, 0) + 1
    for profile in set(profiles):
        required_count = repeat
        if counts.get(profile, 0) < required_count:
            errors.append(f"REPEAT_COUNT_{profile}")
    if not result.get("hosted_focus"):
        worker = result.get("formal_worker") if isinstance(result.get("formal_worker"), dict) else {}
        if worker.get("status") != "PASS":
            errors.append("FORMAL_WORKER_STATUS")
        if worker.get("worker_process_exit") != 0:
            errors.append("FORMAL_WORKER_EXIT")
        if worker.get("canonical_state") != "COMPLETED":
            errors.append("FORMAL_WORKER_CANONICAL_STATE")
        if worker.get("terminal_evidence_id_present") is not True or worker.get("operation_count", 0) < 1:
            errors.append("FORMAL_WORKER_EVIDENCE")
        if worker.get("secrets_in_result") is not False:
            errors.append("FORMAL_WORKER_SECRET_BOUNDARY")
    negative = result.get("negative_controls")
    if not isinstance(negative, list) or {item.get("id") for item in negative if isinstance(item, dict)} != {
        "planned-not-triggered", "bad-toxic-config", "proxy-down", "missing-receipt", "effect-count-2", "blind-retry", "reconcile-unavailable", "cleanup-failure",
    }:
        errors.append("NEGATIVE_CONTROLS_INCOMPLETE")
    return sorted(set(errors))


def main(argv: list[str] | None = None) -> int:
    path = Path(argv[0]) if argv else Path(".local/rpf-28/rpf28-formal-result.json")
    errors = verify_file(path)
    print(json.dumps({"status": "PASS" if not errors else "INVALID", "errors": errors, "result": str(path)}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

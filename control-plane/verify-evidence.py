"""Offline verifier for one RPF-14/RPF-22 formal Control Plane probe result."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SCHEMA = "rpf-14-formal-control-plane-evidence-v1"
EXPECTED_EXECUTION_SCHEMA = "rpf-14-durable-execution-schema-v1"
REQUIRED_CHECKS = {
    "health_readiness",
    "boundary",
    "formal_worker_process",
    "eligible_discovery_starvation",
    "authentication",
    "authority_matrix",
    "rollback",
    "corpus_registration",
    "idempotency",
    "concurrent_idempotency",
    "conflicts",
    "artifact_fail_closed",
    "read_api_layers",
    "durable_submit_replay_conflict_authority",
    "claim_heartbeat_terminal",
    "lease_expiry_reclaim_stale_fencing",
    "operation_identity_not_submitted",
    "response_lost_unknown_reconcile_cross_process",
    "artifact_ingest_crash_recovery",
    "terminal_artifact_binding",
    "cancellation_timeout_platform_semantics",
    "execution_read_api_metrics_retention",
    "decision_writer_history",
    "service_restart",
    "database_restart",
    "backup_restore",
    "schema_mismatch",
    "secret_redaction",
}
FORBIDDEN_SERIALIZED_VALUES = (
    "DEEPSEEK_API_KEY",
    "Authorization",
    "Bearer ",
    "private reasoning",
    "chain_of_thought",
)


def source_identity() -> dict[str, Any]:
    source_paths = [
        ROOT / "control-plane" / "pom.xml",
        ROOT / "control-plane" / "src" / "main" / "resources" / "application.properties",
        ROOT / "runtime" / "runproof_runtime" / "control_plane_client.py",
        ROOT / "runtime" / "runproof_runtime" / "durable_worker.py",
        ROOT / "ci" / "run_release_gate.py",
        ROOT / "web" / "src" / "App.tsx",
        ROOT / "web" / "src" / "data" / "executions.ts",
        ROOT / "web" / "src" / "styles.css",
        ROOT / "control-plane" / "probe.py",
    ]
    source_paths.extend(sorted((ROOT / "control-plane" / "src" / "main" / "java").rglob("*.java")))
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(source_paths, key=lambda candidate: candidate.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        files.append(relative)
    return {"source_sha256": digest.hexdigest(), "files": files}


def fail(message: str) -> int:
    print(f"FAIL: RPF-14/RPF-22 evidence verification: {message}", file=sys.stderr)
    return 1


def verify(path: Path) -> int:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return fail(f"cannot read JSON ({type(error).__name__})")
    if not isinstance(document, dict):
        return fail("result is not an object")
    if document.get("schema_version") != EXPECTED_SCHEMA:
        return fail("unsupported evidence schema")
    if document.get("artifact_kind") != "RunProof Formal Durable Execution Evidence":
        return fail("artifact kind mismatch")
    if document.get("status") != "PASS":
        return fail("probe result is not PASS")
    checks = document.get("checks")
    if not isinstance(checks, dict) or set(checks) != REQUIRED_CHECKS:
        return fail("required check set mismatch")
    if any(not isinstance(value, dict) or value.get("status") != "PASS" for value in checks.values()):
        return fail("one or more checks are not PASS")
    if document.get("source_identity") != source_identity():
        return fail("formal source identity does not match current implementation")
    toolchain = document.get("toolchain")
    if not isinstance(toolchain, dict) or toolchain.get("schema_version") != EXPECTED_EXECUTION_SCHEMA:
        return fail("execution schema identity mismatch")

    worker = checks["formal_worker_process"]
    if worker.get("terminal_state") != "COMPLETED" or worker.get("operation_status") != "CONFIRMED":
        return fail("formal worker terminal contract is incomplete")
    discovery = checks["eligible_discovery_starvation"]
    if (
        discovery.get("terminal_history_count", 0) <= discovery.get("legacy_page_size", 0)
        or discovery.get("server_side_predicate") is not True
        or discovery.get("terminal_history_returned") is not False
        or discovery.get("worker_processed") != discovery.get("queued_job")
        or discovery.get("terminal_state") != "COMPLETED"
    ):
        return fail("eligible job discovery is not proven against terminal-history starvation")
    artifact = checks["artifact_fail_closed"]
    if artifact.get("absolute_path") != 422 or not isinstance(artifact.get("symlink_or_junction_parent"), dict) or artifact["symlink_or_junction_parent"].get("http") != 422:
        return fail("artifact root absolute-path or reparse-point containment is incomplete")
    response_lost = checks["response_lost_unknown_reconcile_cross_process"]
    if response_lost.get("unknown") != "UNKNOWN_OUTCOME" or response_lost.get("reconcile") != "CONFIRMED" or response_lost.get("effect_count") != 1:
        return fail("response-lost reconcile contract is incomplete")
    operation = checks["operation_identity_not_submitted"]
    if operation.get("effect_count") != 1 or operation.get("not_submitted") != "NOT_SUBMITTED":
        return fail("operation identity/effect contract is incomplete")
    retention = checks["execution_read_api_metrics_retention"].get("retention")
    if not isinstance(retention, dict) or retention.get("delete_endpoint") is not False:
        return fail("retention boundary is not fail-closed")
    if checks["execution_read_api_metrics_retention"].get("eligible_discovery_index") != 1 or "eligible_jobs" not in checks["execution_read_api_metrics_retention"].get("metrics", []):
        return fail("eligible discovery index/metric evidence is incomplete")
    boundary = checks["boundary"]
    if boundary.get("job_transport_resolved") is not True or boundary.get("queue") is not False or boundary.get("release_authorized") is not False:
        return fail("transport/release boundary is invalid")
    serialized = json.dumps(document, ensure_ascii=False)
    if any(forbidden in serialized for forbidden in FORBIDDEN_SERIALIZED_VALUES):
        return fail("forbidden credential or private protocol marker found")
    print(f"PASS: RPF-14/RPF-22 formal Control Plane evidence ({path.as_posix()})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    return verify(args.result)


if __name__ == "__main__":
    raise SystemExit(main())

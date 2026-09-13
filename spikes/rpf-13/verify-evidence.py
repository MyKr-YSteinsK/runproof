"""Verify the reviewed, redacted RPF-13 durable execution evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REVIEWED = ROOT / "spikes" / "rpf-13" / "reviewed-evidence.json"
SPIKE_ROOT = ROOT / "spikes" / "rpf-13"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def source_identity() -> dict[str, Any]:
    files = [
        SPIKE_ROOT / "control-plane" / "pom.xml",
        SPIKE_ROOT / "control-plane" / "src" / "main" / "resources" / "application.properties",
        *sorted((SPIKE_ROOT / "control-plane" / "src" / "main" / "java").rglob("*.java")),
        SPIKE_ROOT / "probe.py",
    ]
    digest = hashlib.sha256()
    names: list[str] = []
    for path in files:
        require(path.is_file(), f"Missing source file: {path}")
        name = path.relative_to(ROOT).as_posix()
        names.append(name)
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return {"sha256": digest.hexdigest(), "files": names}


def walk_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for pair in value.items() for item in walk_strings(pair)]
    if isinstance(value, list):
        return [item for child in value for item in walk_strings(child)]
    return [value] if isinstance(value, str) else []


def main() -> int:
    document = json.loads(REVIEWED.read_text(encoding="utf-8"))
    require(document.get("schema_version") == "rpf-13-durable-execution-evidence-v1", "schema version mismatch")
    require(document.get("artifact_kind") == "Durable Execution Investigation Evidence", "artifact kind mismatch")
    require(document.get("status") == "PASS", "reviewed evidence is not PASS")
    require(document.get("source_identity") == source_identity(), "reviewed evidence source identity is stale")
    candidate = document.get("candidate", {})
    require(candidate.get("database_image") == "postgres:16-alpine", "not a PostgreSQL provider")
    require(candidate.get("transport") == "POSTGRESQL_POLL_CLAIM_LEASE", "transport identity mismatch")
    observations = document.get("observations", {})
    required = {
        "health_and_boundary", "durable_submit_and_idempotency", "claim_concurrency_heartbeat_terminal",
        "crash_matrix_A_and_stale_fencing", "crash_matrix_B_C_and_operation_identity",
        "crash_matrix_D_unknown_outcome_cross_process", "crash_matrix_E_artifact_before_ingest",
        "cancellation_semantics", "cancellation_timeout_semantics", "crash_matrix_F_database_unavailable_restart",
        "future_ci_submit_poll_terminal_read", "operator_read_model", "transport_candidate_comparison",
        "secret_private_protocol_boundary",
    }
    require(required.issubset(observations), "required observation is missing")
    for name in required:
        require(observations[name].get("status") == "PASS", f"observation is not PASS: {name}")

    health = observations["health_and_boundary"]
    require(health.get("database") == "REACHABLE" and health.get("broker") is False and health.get("scheduler") is False, "health/boundary drift")
    submit = observations["durable_submit_and_idempotency"]
    require(submit.get("replay") == "IDEMPOTENT_REPLAY" and submit.get("conflict") == "IDEMPOTENCY_CONFLICT", "submit idempotency evidence missing")
    claim = observations["claim_concurrency_heartbeat_terminal"]
    require(claim.get("concurrent_http_statuses") == [200, 409] and claim.get("terminal_claim") == "TERMINAL", "claim fencing evidence missing")
    stale = observations["crash_matrix_A_and_stale_fencing"]
    require(stale.get("lease_expiry") == "SAFE_RECLAIM" and stale.get("stale_finalize") == "STALE_ATTEMPT" and stale.get("agent_fail_created") is False, "safe reclaim evidence missing")
    operation = observations["crash_matrix_B_C_and_operation_identity"]
    require(operation.get("explicit_not_submitted") == "NOT_SUBMITTED" and operation.get("effect_count") == 1, "operation identity evidence missing")
    unknown = observations["crash_matrix_D_unknown_outcome_cross_process"]
    require(unknown.get("worker_process_exit_code") == 17 and unknown.get("unknown") == "UNKNOWN_OUTCOME" and unknown.get("reconcile") == "CONFIRMED" and unknown.get("effect_count") == 1, "cross-process reconcile evidence missing")
    artifact = observations["crash_matrix_E_artifact_before_ingest"]
    require(artifact.get("worker_process_exit_code") == 23 and artifact.get("replay") == "IDEMPOTENT_REPLAY" and artifact.get("attempt_number") == 1, "artifact recovery evidence missing")
    cancel = observations["cancellation_semantics"]
    require(cancel.get("queued") == "CANCELLED" and cancel.get("running_request") == "CANCEL_REQUESTED" and cancel.get("running_ack") == "CANCELLED", "cancellation evidence missing")
    timeout = observations["cancellation_timeout_semantics"]
    require(timeout.get("unknown_side_effect_timeout") == "RECONCILE_REQUIRED" and timeout.get("post_reconcile_outcome") == "INCONCLUSIVE", "timeout evidence missing")
    storage = observations["crash_matrix_F_database_unavailable_restart"]
    require(storage.get("unavailable_http_status") == 503 and storage.get("recovered_readback") == "COMPLETED" and storage.get("agent_fail_created") is False, "storage recovery evidence missing")
    ci = observations["future_ci_submit_poll_terminal_read"]
    require(ci.get("submit") == "SUBMITTED" and ci.get("initial_poll") == "QUEUED" and ci.get("terminal") == "COMPLETED" and ci.get("release_authority") is False, "CI contract evidence missing")
    comparison = observations["transport_candidate_comparison"]
    require(comparison.get("candidate_b", {}).get("implemented") is False and "CANDIDATE_A_SUFFICIENT" in comparison.get("conclusion", ""), "transport comparison drift")
    safety = observations["secret_private_protocol_boundary"]
    require(safety.get("forbidden_payload_rejected") is True, "forbidden payload rejection evidence missing")

    forbidden = ("Authorization", "Bearer ", "DEEPSEEK_API_KEY", "private reasoning", "chain_of_thought", "password", "credential")
    strings = walk_strings(document)
    require(not any(forbidden_value in item for item in strings for forbidden_value in forbidden), "forbidden secret/private protocol text found")
    require(document.get("cleanup") == {"container_removed": True, "volume_removed": True}, "resource cleanup evidence missing")
    print("PASS: RPF-13 reviewed durable execution evidence and source identity verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

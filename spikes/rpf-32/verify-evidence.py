"""Offline verifier for the disposable RPF-32 formal S3 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
SCHEMA = "rpf-s3-artifact-store-formal-probe-v1"


class VerificationFailure(RuntimeError):
    pass


def source_hash(files: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(files):
        path = ROOT / relative
        if not path.is_file():
            raise VerificationFailure(f"MISSING_SOURCE:{relative}")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def walk(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if any(secret in key.lower() for secret in ("password", "secret", "token", "credential", "access_key")):
                found.append(key)
            found.extend(walk(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(walk(child))
    return found


def require(condition: bool, code: str) -> None:
    if not condition:
        raise VerificationFailure(code)


def verify(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationFailure("INVALID_RESULT_JSON") from error
    require(isinstance(document, dict), "RESULT_NOT_OBJECT")
    require(document.get("schema_version") == SCHEMA, "UNKNOWN_RESULT_SCHEMA")
    require(document.get("status") == "PASS", "RESULT_NOT_PASS")
    provider = document.get("provider")
    require(isinstance(provider, dict), "PROVIDER_MISSING")
    require(provider.get("name") == "SeaweedFS" and provider.get("version") == "4.47", "WRONG_PROVIDER")
    checks = document.get("checks")
    require(isinstance(checks, dict), "CHECKS_MISSING")
    for name in (
        "bucket_bootstrap", "s3_health", "canonical_ingest", "metadata_replay",
        "metadata_conflict", "orphan_and_replay", "conditional_races",
        "missing_object", "key_containment", "corrupt_object",
        "read_only_principal", "invalid_access", "invalid_backend",
        "object_store_restart", "postgres_restart", "durable_worker", "authority",
    ):
        require(name in checks, f"CHECK_MISSING:{name}")
    require(checks["canonical_ingest"].get("artifact_resolution") == "AVAILABLE", "CANONICAL_ARTIFACT_NOT_AVAILABLE")
    require(checks["metadata_replay"].get("already_exists") is True, "REPLAY_NOT_IDEMPOTENT")
    require(checks["metadata_conflict"].get("error") == "IDENTITY_CONTENT_CONFLICT", "DIFF_CONTENT_NOT_CONFLICT")
    require(checks["orphan_and_replay"].get("orphan_object_present_before_replay") is True, "ORPHAN_BOUNDARY_MISSING")
    require(checks["missing_object"].get("error") == "INVALID_EVIDENCE_ARTIFACT_MISSING", "MISSING_NOT_FAIL_CLOSED")
    require(checks["key_containment"].get("error") == "INVALID_EVIDENCE_ARTIFACT_PATH", "KEY_CONTAINMENT_MISSING")
    require(checks["corrupt_object"].get("error") == "INVALID_EVIDENCE_ARTIFACT_JSON", "CORRUPT_NOT_FAIL_CLOSED")
    require(checks["read_only_principal"].get("put_error") == "ARTIFACT_STORE_ACCESS_DENIED", "READ_ONLY_WRITE_NOT_DENIED")
    require(checks["invalid_access"].get("artifact_store") == "UNAVAILABLE", "INVALID_ACCESS_NOT_UNAVAILABLE")
    require(checks["invalid_backend"].get("fallback") is False, "INVALID_BACKEND_FELL_BACK")
    require(checks["object_store_restart"].get("recovered_read_status") == 200, "OBJECT_STORE_RESTART_NOT_RECOVERED")
    require(checks["postgres_restart"].get("canonical_readback") is True, "POSTGRES_RESTART_NOT_RECOVERED")
    require(checks["durable_worker"].get("job_state") == "COMPLETED", "DURABLE_S3_JOB_NOT_COMPLETED")
    require(checks["authority"].get("release_or_deploy") is False, "RELEASE_BOUNDARY_CHANGED")
    history = document.get("history_boundary")
    require(isinstance(history, dict), "HISTORY_BOUNDARY_MISSING")
    require(history.get("historical_reviewed_bytes_changed") is False, "HISTORICAL_BYTES_CHANGED")
    require(history.get("historical_local_backend_migrated") is False, "LOCAL_BACKEND_MIGRATED")
    require(history.get("release_or_deploy_executed") is False, "RELEASE_EXECUTED")
    cleanup = document.get("cleanup")
    require(isinstance(cleanup, dict), "CLEANUP_MISSING")
    require(all(value is True for value in cleanup.values()), "CLEANUP_INCOMPLETE")
    identity = document.get("source_identity")
    require(isinstance(identity, dict), "SOURCE_IDENTITY_MISSING")
    files = identity.get("files")
    require(isinstance(files, list) and files and all(isinstance(item, str) for item in files), "SOURCE_FILES_MISSING")
    require(identity.get("source_sha256") == source_hash(files), "SOURCE_HASH_MISMATCH")
    secret_keys = walk(document)
    require(not secret_keys, "SECRET_FIELD_IN_RESULT:" + ",".join(sorted(set(secret_keys))))
    serialized = json.dumps(document, ensure_ascii=False)
    for forbidden in ("RPF_ARTIFACT_STORE_S3_SECRET_KEY", "RPF_AUTH_WORKER_TOKEN", "RPF_DB_PASSWORD"):
        require(forbidden not in serialized, "SECRET_NAME_IN_RESULT:" + forbidden)
    return {
        "status": "PASS",
        "schema_version": SCHEMA,
        "source_sha256": identity["source_sha256"],
        "checks": len(checks),
        "cleanup": cleanup,
        "historical_bytes_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify RPF-32 formal S3 evidence.")
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.result.resolve())
    except VerificationFailure as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline verifier for the curated RPF-10 PostgreSQL/auth evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REVIEWED = ROOT / "spikes" / "rpf-10" / "reviewed-evidence.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def source_digest() -> tuple[str, list[str]]:
    files = [
        ROOT / "spikes" / "rpf-10" / "control-plane" / "pom.xml",
        ROOT / "spikes" / "rpf-10" / "control-plane" / "src" / "main" / "resources" / "application.properties",
        *sorted((ROOT / "spikes" / "rpf-10" / "control-plane" / "src" / "main" / "java").rglob("*.java")),
        ROOT / "spikes" / "rpf-10" / "probe.py",
    ]
    digest = hashlib.sha256()
    names: list[str] = []
    for path in files:
        require(path.is_file(), f"Missing source identity file: {path}")
        name = path.relative_to(ROOT).as_posix()
        names.append(name)
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest(), names


def main() -> int:
    document: dict[str, Any] = json.loads(REVIEWED.read_text(encoding="utf-8"))
    require(document.get("schema_version") == "rpf-10-reviewed-evidence-v1", "Unexpected reviewed evidence schema")
    require(document.get("review_status") == "PASS", "Reviewed evidence is not PASS")

    actual_hash, actual_files = source_digest()
    identity = document.get("source_identity", {})
    require(identity.get("sha256") == actual_hash, "Reviewed evidence source hash does not match current source")
    require(identity.get("files") == actual_files, "Reviewed evidence source file list does not match current source")

    execution = document["execution"]
    require(execution["postgres_image"] == "postgres:16-alpine", "Unexpected PostgreSQL image")
    require(execution["postgresql_version"].startswith("16."), "Reviewed evidence is not PostgreSQL 16")
    require(execution["jdbc_driver_version"] == "42.7.5", "Unexpected JDBC driver version")
    require(execution["schema_version"] == "rpf-10-postgresql-metadata-schema-v1", "Unexpected migration schema")

    persistence = document["persistence_checks"]
    for key in ("migration", "insert_query", "transaction_rollback", "concurrent_race", "release_decision_history", "control_plane_restart", "postgres_restart", "backup_restore"):
        require(persistence[key]["status"] == "PASS", f"Persistence check is not PASS: {key}")
    require(persistence["backup_restore"]["independent_database"] is True, "Backup proof is not independent")
    require(persistence["backup_restore"]["artifact_refs_resolved"] == persistence["backup_restore"]["canonical_rows"], "Restored artifact refs are incomplete")
    require(persistence["concurrent_race"]["canonical_rows_for_raced_identity"] == 1, "Concurrent race created duplicate canonical rows")
    require(persistence["schema_mismatch"]["status"] == "STARTUP_BLOCKED", "Schema mismatch was not startup-blocking")

    authorization = document["authorization_checks"]
    for key, expected in {
        "unauthenticated": "401 AUTHENTICATION_REQUIRED",
        "invalid_credential": "401 AUTHENTICATION_REQUIRED",
        "read_principal_ingest": "403 AUTHORIZATION_FORBIDDEN",
        "evidence_principal_decision_write": "403 AUTHORIZATION_FORBIDDEN",
        "agent_like_principal_decision_write": "403 AUTHORIZATION_FORBIDDEN",
        "decision_principal_identity_mismatch": "422 INVALID_EVIDENCE_ARTIFACT_IDENTITY",
        "invalid_manifest": "400 UNKNOWN_MANIFEST_SCHEMA",
    }.items():
        require(authorization[key] == expected, f"Authorization boundary drifted: {key}")
    require(authorization["agent_has_release_decision_authority"] is False, "Agent authority boundary drifted")
    require(authorization["ci_has_release_or_deploy_authority"] is False, "CI authority boundary drifted")

    boundary = document["boundary"]
    require(boundary["job_transport_resolved"] is False and boundary["queue_or_broker"] is False, "Queue/job boundary drifted")
    require(boundary["release_or_deploy_authorized"] is False, "Release/deploy authorization appeared in the probe")

    redaction = document["redaction"]
    require(all(value is False for key, value in redaction.items() if key != "status"), "Redaction boundary contains a positive leak")
    serialized = json.dumps(document, ensure_ascii=False)
    require(re.search(r"Bearer\s+", serialized, re.IGNORECASE) is None, "Bearer material appeared in reviewed evidence")
    require("Authorization:" not in serialized, "Authorization header appeared in reviewed evidence")

    print("PASS: RPF-10 reviewed evidence source, PostgreSQL, authority and redaction contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

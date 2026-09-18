"""Offline verifier for the disposable RPF-31 S3-compatible probe result."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
FORMAL_SCHEMA = "rpf-s3-compatible-spike-v1"
SECRET_KEY = re.compile(r"authorization|bearer|password|secret|credential|access[_-]?key|token|api[_-]?key", re.IGNORECASE)
SECRET_VALUE = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{12,}|rpf31[0-9A-F]{16}|rpf31ro[0-9A-F]{16}|rpf31-(?:secret|readonly)-[A-Za-z0-9-]{8,}|rpf31-wrong(?:-secret)?-[A-Za-z0-9-]{8,})")
SAFE_CONTRACT_KEYS = {
    "secret_boundary", "secret_config_removed", "credential_policy", "credentials_from_ephemeral_environment", "temporary_provider_config_deleted",
    "credentials_in_result", "credentials_in_git", "provider_logs_exported", "configured_read_only", "read_only_get_allowed",
    "read_only_put_rejected", "read_only_status", "wrong_credential", "wrong_credential_rejected", "read_only_get", "read_only_put",
}


class VerificationFailure(AssertionError):
    pass


def assert_true(condition: Any, message: str) -> None:
    if not condition:
        raise VerificationFailure(message)


def source_paths() -> list[Path]:
    paths = [
        SPIKE_ROOT / "README.md",
        SPIKE_ROOT / "probe.py",
        SPIKE_ROOT / "verify-evidence.py",
        SPIKE_ROOT / "java" / "pom.xml",
        ROOT / ".github" / "workflows" / "rpf-31-s3-spike.yml",
    ]
    paths.extend(sorted((SPIKE_ROOT / "java" / "src").rglob("*.java"), key=str))
    return paths


def source_hash(paths: Iterable[Path] | None = None) -> str:
    digest = hashlib.sha256()
    selected = paths or source_paths()
    for path in sorted((item.resolve() for item in selected), key=lambda item: item.relative_to(ROOT).as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def walk(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            assert_true(key_text in SAFE_CONTRACT_KEYS or not SECRET_KEY.search(key_text), f"sensitive result key: {path}/{key_text}")
            walk(child, f"{path}/{key_text}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f"{path}/{index}")
    elif isinstance(value, str):
        assert_true(not SECRET_VALUE.search(value), f"credential-like result value: {path}")


def verify_candidate(candidate: dict[str, Any], *, selected: bool) -> None:
    name = candidate.get("name")
    assert_true(name in {"seaweedfs", "rustfs"}, "unknown candidate")
    status = candidate.get("status")
    if not selected and status == "COMPARISON_INCOMPATIBLE":
        assert_true(candidate.get("critical_contract_passed") is False, f"{name}: incompatible candidate marked critical pass")
        assert_true("non-atomic fallback" in str(candidate.get("failure_boundary")), f"{name}: incompatible fallback boundary missing")
        return
    assert_true(status == "PASS", f"{name}: candidate did not pass")
    assert_true(candidate.get("critical_contract_passed") is True, f"{name}: critical contract missing")
    full = candidate.get("full")
    assert_true(isinstance(full, dict) and full.get("status") == "PASS", f"{name}: full probe")
    assert_true(full.get("conditional_write", "").startswith("PutObject If-None-Match"), f"{name}: conditional primitive")
    assert_true(full.get("physical_key", "").startswith("stable artifact key"), f"{name}: physical key policy")
    assert_true(full.get("delete_semantics", "").startswith("ArtifactStore v1 has no general delete"), f"{name}: delete boundary")
    first = full.get("first_put", {})
    replay = full.get("same_content_replay", {})
    conflict = full.get("different_content_conflict", {})
    assert_true(first.get("state") == "CREATED", f"{name}: first put")
    assert_true(replay.get("state") == "IDEMPOTENT", f"{name}: same replay")
    assert_true(conflict.get("state") == "CONFLICT", f"{name}: different conflict")
    assert_true(full.get("verified_read", {}).get("status") == "VERIFIED", f"{name}: verified read")
    assert_true(full.get("concurrent_same_content", {}).get("passed") is True, f"{name}: same race")
    same = full.get("concurrent_same_content", {})
    assert_true(same.get("created") == 1 and same.get("idempotent") == same.get("writers", 0) - 1 and same.get("failed") == 0, f"{name}: same race winner/failure count")
    assert_true(full.get("concurrent_different_content", {}).get("passed") is True, f"{name}: different race")
    different = full.get("concurrent_different_content", {})
    assert_true(different.get("created") == 1 and different.get("failed") == 0, f"{name}: different race winner/failure count")
    assert_true(different.get("conflict", 0) >= 1 and different.get("conflict", 0) + different.get("idempotent", 0) == different.get("writers", 0) - 1, f"{name}: different race classification")
    assert_true(full.get("missing_object", {}).get("status") == "MISSING", f"{name}: missing negative")
    assert_true(full.get("missing_object", {}).get("fail_closed") is True, f"{name}: missing fail closed")
    assert_true(full.get("corrupt_object", {}).get("status") == "HASH_MISMATCH", f"{name}: corrupt negative")
    assert_true(full.get("wrong_identity", {}).get("status") == "IDENTITY_MISMATCH", f"{name}: identity negative")
    credential = full.get("credential_policy", {})
    assert_true(credential.get("wrong_credential_rejected") is True, f"{name}: wrong credential")
    if name == "seaweedfs":
        assert_true(credential.get("configured_read_only") is True, "SeaweedFS: read-only credential not configured")
        assert_true(credential.get("read_only_get_allowed") is True, "SeaweedFS: read-only read")
        assert_true(credential.get("read_only_put_rejected") is True, "SeaweedFS: read-only put")
    sizes = full.get("size_probe", {}).get("cases", [])
    assert_true({item.get("bytes") for item in sizes} == {1024, 1024 * 1024, 16 * 1024 * 1024}, f"{name}: size cases")
    assert_true(full.get("orphan_put_before_metadata", {}).get("safe_replay") is True, f"{name}: orphan replay")
    assert_true(full.get("orphan_put_before_metadata", {}).get("canonical_metadata_written") is False, f"{name}: orphan became canonical")
    assert_true(full.get("metadata_before_ack_response_lost", {}).get("safe_replay") is True, f"{name}: response-lost replay")
    assert_true(full.get("etag_checksum", {}).get("canonical_integrity", "").startswith("RunProof SHA-256"), f"{name}: ETag boundary")
    assert_true(candidate.get("restart", {}).get("status") == "PASS", f"{name}: restart")
    assert_true(candidate.get("restart", {}).get("bytes_and_hash_preserved") is True, f"{name}: restart identity")
    unavailable = candidate.get("endpoint_unavailable", {})
    assert_true(unavailable.get("status") == "PASS", f"{name}: unavailable endpoint")
    assert_true(unavailable.get("available") is False, f"{name}: unavailable health")


def verify_result(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    assert_true(result.get("schema_version") == FORMAL_SCHEMA, "schema version")
    assert_true(result.get("plan_id") == "RPF-31", "plan identity")
    assert_true(result.get("status") == "PASS", "probe status")
    identity = result.get("source_identity", {})
    assert_true(identity.get("source_sha256") == source_hash(), "source identity drift")
    candidates = result.get("candidates", [])
    assert_true({item.get("name") for item in candidates} == {"seaweedfs", "rustfs"}, "candidate set")
    selected = next(item for item in candidates if item.get("name") == "seaweedfs")
    verify_candidate(selected, selected=True)
    secondary = next(item for item in candidates if item.get("name") == "rustfs")
    verify_candidate(secondary, selected=False)
    decision = result.get("decision", {})
    assert_true(decision.get("PROCEED_TO_FORMAL_S3_ARTIFACT_STORE") == "YES", "formal decision")
    assert_true(decision.get("formal_implementation_changed") is False, "formal implementation changed")
    assert_true(decision.get("historical_artifacts_rewritten") is False, "historical artifacts rewritten")
    boundary = result.get("secret_boundary", {})
    assert_true(boundary.get("credentials_from_ephemeral_environment") is True, "credential source")
    assert_true(boundary.get("temporary_provider_config_deleted") is True, "temporary config")
    assert_true(boundary.get("credentials_in_result") is False, "credentials in result")
    assert_true(boundary.get("credentials_in_git") is False, "credentials in git")
    assert_true(boundary.get("provider_logs_exported") is False, "provider logs")
    cleanup = result.get("cleanup", {})
    assert_true(cleanup.get("no_labeled_containers") is True and cleanup.get("no_labeled_volumes") is True, "cleanup")
    assert_true(result.get("release_or_deploy_executed") is False, "release/deploy")
    walk(result)
    return {"status": "PASS", "candidates": [item.get("name") for item in candidates], "source": identity.get("source_sha256")}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python spikes/rpf-31/verify-evidence.py <rpf31-result.json>")
        return 2
    try:
        verified = verify_result(Path(sys.argv[1]).resolve())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, VerificationFailure) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(verified, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

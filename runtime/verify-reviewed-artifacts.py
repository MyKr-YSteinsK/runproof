"""Offline checks for historical RPF-03 and current RPF-04 evidence samples."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "runtime" / "runproof_runtime"
LEGACY_ARTIFACTS = (
    ROOT / "runtime" / "reviewed-normal-run.json",
    ROOT / "runtime" / "reviewed-response-lost-run.json",
)
CURRENT_ARTIFACTS = (
    ROOT / "runtime" / "reviewed-normal-run-v2.json",
    ROOT / "runtime" / "reviewed-response-lost-run-v2.json",
)
HISTORICAL_RPF03_SOURCE_SHA256 = "c586242817bb03971807b8f44d5e0ebc16c4851519f6f94a9a017c49614a3832"
SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+\S+)"
)
PRIVATE_KEYS = {"authorization", "api_key", "messages", "password", "reasoning_content", "secret", "token"}


def runtime_source_sha256() -> str:
    digest = hashlib.sha256()
    for path in sorted(PACKAGE.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def walk(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield path, key, child
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")


def assert_private_boundary(artifact: dict[str, Any]) -> None:
    encoded = json.dumps(artifact, ensure_ascii=False)
    assert not SECRET_VALUE.search(encoded)
    for location, key, _ in walk(artifact):
        assert key.lower() not in PRIVATE_KEYS, f"private key {location}.{key}"
    assert "reasoning_content" not in encoded
    assert '"messages"' not in encoded


def assert_common_run(path: Path, artifact: dict[str, Any], expected_fault: bool) -> None:
    assert artifact["artifact_kind"] == "Run Evidence"
    assert artifact["outcome"] == {
        "status": "PASS",
        "source": "DETERMINISTIC_VERIFIER",
        "agent_quality_eligible": True,
        "formal_run_started": True,
    }
    assert artifact["environment"]["lifecycle_state"] == "CLEANED"
    assert artifact["environment"]["cleanup_state"] == "CLEANED"
    assert artifact["environment"]["provenance"]["mounts"] == []
    assert artifact["verification"]["passed"] is True
    assert artifact["verification"]["actual_state"] == artifact["verification"]["expected_state"]
    assert artifact["verification"]["evidence"]["blind_retry_attempts"] == 0
    assert artifact["verification"]["evidence"]["unresolved_unknown"] is False
    fault = artifact["fault"]
    assert fault["planned"] is expected_fault
    assert fault["triggered"] is expected_fault
    assert fault["observed"] is expected_fault
    assert fault["reconciled"] is expected_fault
    events = [item["event_type"] for item in artifact["trajectory"]]
    assert "environment_provisioned" in events
    assert "initial_state_verification" in events
    assert "actual_state_verification" in events
    assert "cleanup" in events
    if expected_fault:
        assert "fault" in events
        assert "reconcile" in events
        assert any(item.get("result", {}).get("status") == "UNKNOWN_OUTCOME" for item in artifact["trajectory"])
    else:
        assert "fault" not in events
        assert "reconcile" not in events
    assert_private_boundary(artifact)


def assert_legacy_artifact(path: Path, expected_fault: bool) -> None:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "rpf-run-evidence-v1"
    assert artifact["run"]["runtime"]["source_sha256"] == HISTORICAL_RPF03_SOURCE_SHA256
    assert "provider" in artifact and "llm_provider" not in artifact and "environment_provider" not in artifact
    assert artifact["provider"]["requested_model"] == "deepseek-flash"
    assert artifact["provider"]["mode"] == "non-thinking"
    assert artifact["provider"]["calls"]
    assert_common_run(path, artifact, expected_fault)


def assert_event_contract(artifact: dict[str, Any]) -> None:
    run_id = artifact["run"]["run_id"]
    contract = artifact["trajectory_contract"]
    assert contract["version"] == "rpf-trajectory-event-v1"
    assert "sequence" in contract["ordering"]
    assert "event_id" in contract["identity"]
    events = artifact["trajectory"]
    assert events
    ids = [event["event_id"] for event in events]
    assert len(ids) == len(set(ids))
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    for event in events:
        assert event["event_id"].startswith(f"{run_id}:event:")
        assert event["evidence_layer"] in {"Observed Fact", "Verified Result", "Derived Value", "Inference", "AI Analysis"}
        assert isinstance(event["event_type"], str) and event["event_type"]
        assert event["entity_refs"]["run_id"] == run_id


def assert_current_artifact(path: Path, expected_fault: bool, source_hash: str) -> None:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "rpf-run-evidence-v2"
    assert artifact["run"]["runtime"]["runtime_version"] == "rpf-04.v1"
    assert artifact["run"]["runtime"]["source_sha256"] == source_hash
    assert "provider" not in artifact
    llm = artifact["llm_provider"]
    assert llm["provider_id"] == "deepseek"
    assert llm["provider_type"] == "llm"
    assert llm["requested_model"] == "deepseek-flash"
    assert llm["mode"] == "non-thinking"
    assert llm["calls"]
    assert all(call["provider"] == "deepseek" for call in llm["calls"])
    environment_provider = artifact["environment_provider"]
    assert environment_provider["provider_id"] == "docker"
    assert environment_provider["provider_type"] == "environment"
    assert environment_provider["provider_implementation"] == "docker"
    assert environment_provider["image"]["reference"] == "alpine:3.22"
    assert_common_run(path, artifact, expected_fault)
    assert_event_contract(artifact)
    events = artifact["trajectory"]
    if expected_fault:
        fault_index = next(index for index, event in enumerate(events) if event["event_type"] == "fault")
        unknown_index = next(
            index
            for index, event in enumerate(events)
            if event["event_type"] == "tool_result" and event.get("result", {}).get("status") == "UNKNOWN_OUTCOME"
        )
        reconcile_index = next(index for index, event in enumerate(events) if event["event_type"] == "reconcile")
        verification_index = next(index for index, event in enumerate(events) if event["event_type"] == "actual_state_verification")
        assert fault_index < unknown_index < reconcile_index < verification_index


def main() -> None:
    source_hash = runtime_source_sha256()
    assert_legacy_artifact(LEGACY_ARTIFACTS[0], expected_fault=False)
    assert_legacy_artifact(LEGACY_ARTIFACTS[1], expected_fault=True)
    assert_current_artifact(CURRENT_ARTIFACTS[0], expected_fault=False, source_hash=source_hash)
    assert_current_artifact(CURRENT_ARTIFACTS[1], expected_fault=True, source_hash=source_hash)
    print(f"PASS: 2 historical v1 + 2 current v2 reviewed artifacts; source={source_hash}")


if __name__ == "__main__":
    main()

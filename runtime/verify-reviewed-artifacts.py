"""Offline checks for the two reviewed RPF-03 live-run evidence samples."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "runtime" / "runproof_runtime"
ARTIFACTS = (
    ROOT / "runtime" / "reviewed-normal-run.json",
    ROOT / "runtime" / "reviewed-response-lost-run.json",
)
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


def assert_artifact(path: Path, expected_fault: bool, source_hash: str) -> None:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "rpf-run-evidence-v1"
    assert artifact["artifact_kind"] == "Run Evidence"
    assert artifact["outcome"] == {
        "status": "PASS",
        "source": "DETERMINISTIC_VERIFIER",
        "agent_quality_eligible": True,
        "formal_run_started": True,
    }
    assert artifact["run"]["runtime"]["source_sha256"] == source_hash
    assert artifact["provider"]["requested_model"] == "deepseek-flash"
    assert artifact["provider"]["mode"] == "non-thinking"
    assert artifact["provider"]["calls"]
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

    encoded = json.dumps(artifact, ensure_ascii=False)
    assert not SECRET_VALUE.search(encoded)
    for location, key, _ in walk(artifact):
        assert key.lower() not in PRIVATE_KEYS, f"private key {location}.{key}"
    assert "reasoning_content" not in encoded
    assert '"messages"' not in encoded


def main() -> None:
    source_hash = runtime_source_sha256()
    assert_artifact(ARTIFACTS[0], expected_fault=False, source_hash=source_hash)
    assert_artifact(ARTIFACTS[1], expected_fault=True, source_hash=source_hash)
    print(f"PASS: {len(ARTIFACTS)} reviewed RPF-03 artifacts; source={source_hash}")


if __name__ == "__main__":
    main()

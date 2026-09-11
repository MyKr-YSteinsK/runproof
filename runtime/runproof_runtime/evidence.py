"""Structured, redacted Run Evidence for the vertical slice."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SENSITIVE_KEY = re.compile(r"^(reasoning_content|messages|authorization|api_key|password|secret|token)$", re.IGNORECASE)
SECRET_VALUE = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+\S+)")


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def runtime_source_sha256() -> str:
    package = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(package.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def redact(value: Any, secret: str = "") -> Any:
    if isinstance(value, str):
        result = value.replace(secret, "[REDACTED]") if secret else value
        return SECRET_VALUE.sub("[REDACTED]", result)
    if isinstance(value, list):
        return [redact(item, secret) for item in value]
    if isinstance(value, dict):
        return {
            key: redact(item, secret)
            for key, item in value.items()
            if not SENSITIVE_KEY.match(key)
        }
    return value


def assert_safe_artifact(value: Any, secret: str = "") -> None:
    encoded = json.dumps(value, ensure_ascii=False)
    if secret and secret in encoded:
        raise ValueError("SECRET_IN_ARTIFACT")
    if SECRET_VALUE.search(encoded):
        raise ValueError("CREDENTIAL_PATTERN_IN_ARTIFACT")
    if "reasoning_content" in encoded or '"messages"' in encoded:
        raise ValueError("PRIVATE_PROTOCOL_CONTENT_IN_ARTIFACT")


def write_artifact(artifact: dict[str, Any], output_dir: Path, secret: str = "") -> Path:
    safe = redact(artifact, secret)
    assert_safe_artifact(safe, secret)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = artifact.get("run", {}).get("run_id", "run")
    path = output_dir / f"{run_id}.json"
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path

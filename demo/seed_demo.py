"""Register the Golden Demo reviewed corpus through the formal Control Plane."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.control_plane_client import (  # noqa: E402
    ControlPlaneClient,
    ControlPlaneClientError,
    register_reviewed_corpus,
)


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ControlPlaneClientError(f"Required credential environment variable is missing: {name}", code="CLIENT_CREDENTIAL_MISSING")
    return value


def verify_profile(root: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(root / "demo" / "verify-golden-demo.py"), "--root", str(root), "--json"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ControlPlaneClientError("Golden Demo profile verification failed", code="DEMO_PROFILE_INVALID")


def profile_artifacts(root: Path) -> list[dict[str, Any]]:
    document = json.loads((root / "demo" / "rpf-19-golden-demo-v1.json").read_text(encoding="utf-8"))
    return [item for item in document["reviewed_artifacts"] if isinstance(item, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the RPF-19 Golden Demo through the formal API")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-url", default=os.environ.get("RPF_CONTROL_PLANE_URL", "http://127.0.0.1:8081/api/v1"))
    parser.add_argument("--artifact-store-root", type=Path, default=Path(".local/rpf-19/demo-artifacts"))
    parser.add_argument("--evidence-token-env", default="RPF_AUTH_EVIDENCE_TOKEN")
    parser.add_argument("--decision-token-env", default="RPF_AUTH_DECISION_TOKEN")
    parser.add_argument("--read-token-env", default="RPF_AUTH_READ_TOKEN")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    artifact_root = args.artifact_store_root if args.artifact_store_root.is_absolute() else root / args.artifact_store_root
    if args.repeat < 1 or args.repeat > 3:
        parser.error("--repeat must be between 1 and 3")
    try:
        verify_profile(root)
        outputs: list[list[dict[str, Any]]] = []
        for _ in range(args.repeat):
            outputs.append(register_reviewed_corpus(
                root,
                artifact_root,
                args.base_url,
                evidence_token=required_env(args.evidence_token_env),
                decision_token=required_env(args.decision_token_env),
            ))
        read_client = ControlPlaneClient(args.base_url, required_env(args.read_token_env))
        readback = []
        for item in profile_artifacts(root):
            metadata = read_client.get(str(item["entity_type"]), str(item["entity_id"]))
            if metadata is None:
                raise ControlPlaneClientError(f"Golden Demo ref did not read back: {item['entity_id']}", code="DEMO_READBACK_MISSING")
            artifact_ref = metadata.get("artifact_resolution", {}) if isinstance(metadata, dict) else {}
            if not isinstance(artifact_ref, dict) or artifact_ref.get("resolved") is not True:
                raise ControlPlaneClientError(f"Golden Demo artifact is not verified: {item['entity_id']}", code="DEMO_ARTIFACT_UNVERIFIED")
            readback.append(str(item["entity_id"]))
    except ControlPlaneClientError as error:
        result = {"status": "FAIL", "error": error.code}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    status_counts = Counter(item.get("status", "UNKNOWN") for batch in outputs for item in batch)
    result = {
        "status": "PASS",
        "base_url": args.base_url,
        "registered_artifact_count": len(outputs[0]),
        "repeat_count": args.repeat,
        "status_counts": dict(sorted(status_counts.items())),
        "canonical_readback_count": len(readback),
        "artifact_store_root": str(artifact_root),
        "provider_invoked": False,
        "release_or_deploy": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"PASS: registered {result['registered_artifact_count']} reviewed artifacts; read back {result['canonical_readback_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

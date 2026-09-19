"""Offline verifier for the RPF-36 managed-topology investigation result."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
BLUEPRINT = SPIKE_ROOT / "topology-candidates.json"
WORKFLOW = ROOT / ".github" / "workflows" / "rpf-36-production-topology.yml"
SOURCE_FILES = (
    SPIKE_ROOT / "README.md",
    SPIKE_ROOT / "probe.py",
    SPIKE_ROOT / "verify-evidence.py",
    BLUEPRINT,
    WORKFLOW,
)


def fail(message: str) -> None:
    raise ValueError(message)


def source_hash() -> tuple[str, list[str]]:
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(SOURCE_FILES, key=lambda item: item.relative_to(ROOT).as_posix()):
        if not path.is_file():
            fail(f"missing source: {path.relative_to(ROOT).as_posix()}")
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        files.append(relative)
    return digest.hexdigest(), files


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"result read failed: {exc}")
    if not isinstance(value, dict):
        fail("result must be an object")
    return value


def verify(result_path: Path) -> dict[str, Any]:
    result = load_json(result_path)
    blueprint = load_json(BLUEPRINT)
    dynamic = {"source_identity", "probe"}
    result_core = {key: value for key, value in result.items() if key not in dynamic}
    if result_core != blueprint:
        fail("result core does not exactly match the reviewed topology blueprint")
    if result.get("status") != "PASS" or result.get("schema_version") != "rpf-production-topology-managed-operations-v1":
        fail("schema/status")
    if result.get("plan_id") != "RPF-36" or result.get("lifecycle") != "Stabilization":
        fail("plan/lifecycle")
    for key, expected in (
        ("cloud_operations", "NOT_EXECUTED"),
        ("formal_production_implementation_changed", False),
        ("paid_resources_created", False),
        ("production_deployment_executed", False),
        ("historical_reviewed_bytes_changed", False),
    ):
        if result.get(key) != expected:
            fail(f"scope: {key}")

    identity = result.get("source_identity")
    expected_hash, expected_files = source_hash()
    if not isinstance(identity, dict) or identity.get("source_sha256") != expected_hash or identity.get("files") != expected_files:
        fail("source identity")
    probe = result.get("probe")
    if not isinstance(probe, dict) or probe.get("mode") != "offline-config-validation":
        fail("probe mode")
    cleanup = probe.get("cleanup")
    if not isinstance(cleanup, dict) or cleanup != {"local_output_only": True, "cloud_resources": True, "paid_resources": True}:
        fail("cleanup/cloud boundary")
    checks = probe.get("checks")
    if not isinstance(checks, dict) or not checks or not all(value in ("PASS", "NOT_EXECUTED") or (isinstance(value, int) and value > 0) for value in checks.values()):
        fail("probe checks")

    serialized = json.dumps(result, ensure_ascii=True).lower()
    for marker in ("ghp_", "github_pat_", "authorization:", "password=", "private_reasoning", "chain_of_thought"):
        if marker in serialized:
            fail(f"secret/private marker: {marker}")
    if re.search(r"sk-[a-z0-9]{20,}", serialized):
        fail("secret/private marker: sk-shaped")
    gate = result.get("lifecycle_gate")
    if not isinstance(gate, dict) or gate.get("ready_for_production_implementation") != "CONDITIONAL" or gate.get("not_production") is not True:
        fail("conditional lifecycle gate")
    next_plan = result.get("next_plan")
    if not isinstance(next_plan, dict) or next_plan.get("id") != "RPF-37" or not next_plan.get("minimum_blockers"):
        fail("RPF-37 boundary")
    if result.get("region_decision", {}).get("recommended_candidate") != "aws:ap-southeast-1":
        fail("region recommendation")
    if result.get("selected_topology", {}).get("negative_authority_checks", {}).get("eligible_auto_deploy") is not False:
        fail("release authority")
    if result.get("s3_compatibility_findings", {}).get("verified_read") != "required":
        fail("S3 compatibility")
    return {
        "status": "PASS",
        "schema_version": result["schema_version"],
        "source_sha256": expected_hash,
        "providers": len(result["providers_evaluated"]),
        "research_sources": len(result["research_sources"]),
        "ready_for_production_implementation": gate["ready_for_production_implementation"],
        "cloud_operations": result["cloud_operations"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    try:
        summary = verify(args.result.resolve())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"RPF36_VERIFY_FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "RPF36_VERIFY_PASS "
        f"schema={summary['schema_version']} "
        f"source_sha256={summary['source_sha256']} "
        f"providers={summary['providers']} sources={summary['research_sources']} "
        f"ready={summary['ready_for_production_implementation']} "
        f"cloud_operations={summary['cloud_operations']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

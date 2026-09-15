"""Verify the immutable, versioned RPF-19 Golden Demo profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


PROFILE_SCHEMA = "rpf-golden-demo-profile-v1"
PROFILE_PATH = Path("demo/rpf-19-golden-demo-v1.json")
REQUIRED_ROLES = {
    "agent.production_change",
    "agent.incident_remediation",
    "baseline.evaluation",
    "release.decision",
    "statistical.stable",
    "statistical.flaky",
    "statistical.safety",
    "statistical.evidence_poor",
    "statistical.comparison",
    "failure.flagship_case",
    "failure.flagship_cluster",
    "failure.cross_agent_cluster",
    "version.bisect",
    "durable.response_lost_run",
    "regression.flagship",
}
CONTRACTS: dict[str, tuple[str, str, str, str]] = {
    "Run Evidence": ("RUN", "rpf-run-evidence-v2", "run", "run_id"),
    "Failure Case": ("FAILURE_CASE", "rpf-failure-case-v1", "failure_case", "failure_case_id"),
    "Regression": ("REGRESSION", "rpf-regression-v1", "regression", "regression_id"),
    "Evaluation Result": ("EVALUATION", "rpf-evaluation-result-v1", "evaluation", "evaluation_id"),
    "Release Decision": ("RELEASE_DECISION", "rpf-release-decision-v1", "release_decision", "release_decision_id"),
    "Failure Cluster": ("FAILURE_CLUSTER", "rpf-failure-cluster-v1", "cluster", "cluster_id"),
    "Version Bisect": ("VERSION_BISECT", "rpf-version-bisect-v1", "bisect", "bisect_id"),
    "Statistical Evaluation": ("STATISTICAL_EVALUATION", "rpf-statistical-evaluation-v1", "statistical_evaluation", "evaluation_id"),
    "Statistical Comparison": ("STATISTICAL_COMPARISON", "rpf-statistical-comparison-v1", "statistical_comparison", "comparison_id"),
}
FORBIDDEN_MARKERS = (
    "DEEPSEEK_API_KEY",
    "Authorization",
    "Bearer ",
    "private_reasoning",
    "production-grade",
    "fake data",
    "mock frontend",
)


class VerificationError(RuntimeError):
    pass


def first_text(value: Any, key: str) -> str | None:
    if isinstance(value, dict):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
        for child in value.values():
            found = first_text(child, key)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = first_text(child, key)
            if found:
                return found
    return None


def git_commit_exists(root: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.returncode == 0


def verify(root: Path, profile_path: Path) -> dict[str, Any]:
    try:
        raw = profile_path.read_text(encoding="utf-8")
        profile = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"profile cannot be read: {profile_path}") from exc
    if not isinstance(profile, dict) or profile.get("schema_version") != PROFILE_SCHEMA:
        raise VerificationError(f"schema_version must be {PROFILE_SCHEMA}")
    serialized = json.dumps(profile, ensure_ascii=False)
    if any(marker in serialized for marker in FORBIDDEN_MARKERS):
        raise VerificationError("profile contains a forbidden secret/private/mock/production marker")
    demo = profile.get("demo")
    if not isinstance(demo, dict):
        raise VerificationError("demo section is missing")
    for key in ("demo_id", "version", "source_commit", "runtime_source_sha256", "seed_command", "start_command"):
        if not isinstance(demo.get(key), str) or not demo[key]:
            raise VerificationError(f"demo.{key} is required")
    if len(demo["source_commit"]) != 40 or not git_commit_exists(root, demo["source_commit"]):
        raise VerificationError("demo.source_commit is not an existing commit")
    if len(demo["runtime_source_sha256"]) != 64:
        raise VerificationError("demo.runtime_source_sha256 must be a sha256")
    if demo.get("no_provider_required") is not True or demo.get("no_cloud_required") is not True:
        raise VerificationError("demo must be provider/cloud independent")
    if demo.get("no_release_or_deploy") is not True:
        raise VerificationError("demo must be decision-only")

    agents = profile.get("agents")
    if not isinstance(agents, list) or len(agents) != 2:
        raise VerificationError("exactly two Golden Demo agents are required")
    agent_ids = [item.get("agent_id") for item in agents if isinstance(item, dict)]
    if len(agent_ids) != 2 or len(set(agent_ids)) != 2:
        raise VerificationError("agent identities must be explicit and distinct")

    assertions = profile.get("expected_assertions")
    if not isinstance(assertions, list) or len(assertions) < 5 or not all(isinstance(item, str) and item for item in assertions):
        raise VerificationError("expected demo assertions are incomplete")

    artifact_entries = profile.get("reviewed_artifacts")
    if not isinstance(artifact_entries, list):
        raise VerificationError("reviewed_artifacts must be a list")
    roles = {item.get("role") for item in artifact_entries if isinstance(item, dict)}
    missing_roles = REQUIRED_ROLES - roles
    if missing_roles:
        raise VerificationError(f"missing reviewed artifact roles: {sorted(missing_roles)}")
    if len(roles) != len(artifact_entries):
        raise VerificationError("reviewed artifact roles must be unique")

    entity_ids: set[str] = set()
    verified_files: list[str] = []
    for item in artifact_entries:
        if not isinstance(item, dict):
            raise VerificationError("reviewed artifact entry must be an object")
        relative = item.get("path")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise VerificationError("reviewed artifact path must stay inside the repository")
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise VerificationError("reviewed artifact path escapes the repository") from exc
        if not path.is_file():
            raise VerificationError(f"reviewed artifact is missing: {relative}")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerificationError(f"reviewed artifact is not valid JSON: {relative}") from exc
        if not isinstance(document, dict):
            raise VerificationError(f"reviewed artifact is not an object: {relative}")
        kind = item.get("artifact_kind")
        if kind not in CONTRACTS:
            raise VerificationError(f"unsupported artifact kind in profile: {kind}")
        entity_type, schema, container_name, id_field = CONTRACTS[kind]
        container = document.get(container_name)
        actual_id = container.get(id_field) if isinstance(container, dict) else None
        if document.get("artifact_kind") != kind or document.get("schema_version") != schema:
            raise VerificationError(f"artifact contract mismatch: {relative}")
        if item.get("entity_type") != entity_type or item.get("schema_version") != schema or item.get("entity_id") != actual_id:
            raise VerificationError(f"profile identity mismatch: {relative}")
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if item.get("content_sha256") != content_hash:
            raise VerificationError(f"content hash mismatch: {relative}")
        expected_source = item.get("source_sha256")
        actual_source = first_text(document, "source_sha256") or content_hash
        if expected_source != actual_source:
            raise VerificationError(f"source hash mismatch: {relative}")
        entity_ids.add(str(actual_id))
        verified_files.append(relative)

    selected = profile.get("selected")
    if not isinstance(selected, dict):
        raise VerificationError("selected demo refs are missing")
    selected_values: list[str] = []
    for value in selected.values():
        if isinstance(value, str):
            selected_values.append(value)
        elif isinstance(value, list):
            selected_values.extend(item for item in value if isinstance(item, str))
    missing_selected = sorted(value for value in selected_values if value not in entity_ids)
    if missing_selected:
        raise VerificationError(f"selected demo ref is not covered by reviewed artifacts: {missing_selected}")

    return {
        "status": "PASS",
        "schema_version": PROFILE_SCHEMA,
        "demo_id": demo["demo_id"],
        "demo_version": demo["version"],
        "source_commit": demo["source_commit"],
        "reviewed_artifact_count": len(verified_files),
        "agent_ids": agent_ids,
        "selected_ref_count": len(selected_values),
        "no_provider_required": True,
        "no_cloud_required": True,
        "no_release_or_deploy": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the RPF-19 Golden Demo profile")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--profile", type=Path, default=PROFILE_PATH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    profile = args.profile if args.profile.is_absolute() else root / args.profile
    try:
        result = verify(root, profile)
    except VerificationError as error:
        result = {"status": "FAIL", "error": str(error)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"PASS: {result['demo_id']}@{result['demo_version']} ({result['reviewed_artifact_count']} reviewed refs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""RPF-17 deterministic Failure Intelligence corpus and Control Plane probe.

The reviewed corpus is derived from the immutable RPF-05/RPF-06/RPF-16
artifacts.  It intentionally does not call DeepSeek, run a live Agent, or
rewrite an historical artifact.  ``--run`` additionally proves that the three
new artifact kinds pass through the formal PostgreSQL-backed Control Plane.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.control_plane_client import ControlPlaneClient  # noqa: E402
from runtime.runproof_runtime.evidence import assert_safe_artifact, runtime_source_sha256  # noqa: E402
from runtime.runproof_runtime.failure_case import failure_signature  # noqa: E402
from runtime.runproof_runtime.failure_intelligence import (  # noqa: E402
    BISECT_ARTIFACT_KIND,
    BISECT_SCHEMA_VERSION,
    CLUSTER_ARTIFACT_KIND,
    CLUSTER_SCHEMA_VERSION,
    INTELLIGENCE_ARTIFACT_KIND,
    INTELLIGENCE_SCHEMA_VERSION,
    build_cluster_artifacts,
    build_failure_intelligence,
    build_version_bisect,
    exact_dedup_groups,
    recommendation_for,
    validate_bisect_artifact,
    validate_cluster_artifact,
    validate_intelligence_artifact,
)


RUNTIME_DIR = ROOT / "runtime"
LOCAL_DIR = ROOT / ".local" / "rpf-17"
REVIEWED_FILES = {
    "production_intelligence": "reviewed-rpf17-production-failure-intelligence.json",
    "incident_intelligence": "reviewed-rpf17-incident-failure-intelligence.json",
    "environment_intelligence": "reviewed-rpf17-environment-negative-intelligence.json",
    "provider_intelligence": "reviewed-rpf17-provider-negative-intelligence.json",
    "invalid_intelligence": "reviewed-rpf17-invalid-negative-intelligence.json",
    "production_cluster": "reviewed-rpf17-production-domain-cluster.json",
    "incident_cluster": "reviewed-rpf17-incident-domain-cluster.json",
    "cross_agent_cluster": "reviewed-rpf17-cross-agent-cluster.json",
    "bisect": "reviewed-rpf17-incident-version-bisect.json",
}
SECRET_PATTERN = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+\S+)")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"INVALID_JSON_OBJECT:{path.name}")
    return value


def _write_immutable(path: Path, value: dict[str, Any], *, refresh: bool = False) -> Path:
    safe = copy.deepcopy(value)
    assert_safe_artifact(safe)
    encoded = json.dumps(safe, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            if refresh and path.name in REVIEWED_FILES.values():
                path.write_text(encoded, encoding="utf-8", newline="\n")
                return path
            raise RuntimeError(f"REVIEWED_ARTIFACT_EXISTS_WITH_DIFFERENT_BYTES:{path.name}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8", newline="\n")
    return path


def _run(name: str) -> dict[str, Any]:
    return _load(RUNTIME_DIR / name)


def _negative_run(run_id: str, *, outcome: str, source: str, attribution: str, provider_failure: bool = False, environment_failure: bool = False) -> dict[str, Any]:
    return {
        "schema_version": "rpf-run-evidence-v2",
        "artifact_kind": "Run Evidence",
        "run": {
            "run_id": run_id,
            "agent": {
                "agent_id": "controlled-negative-agent",
                "agent_version": "negative-control-v1",
                "configuration_id": "negative-control-v1",
                "agent_domain": "Negative Control",
            },
            "scenario": {"scenario_id": "rpf17-negative-control", "scenario_version": "1.0.0"},
        },
        "outcome": {
            "status": outcome,
            "source": source,
            "attribution": attribution,
            "agent_quality_eligible": False,
            "formal_run_started": False,
            "agent_started": False,
        },
        "failure_attribution": {
            "category": attribution,
            "domain": "PLATFORM" if attribution == "Platform" else "ENVIRONMENT" if attribution == "Platform/Environment" else "INPUT",
            "deterministic": True,
            "reason_code": f"RPF17_{source}_NEGATIVE_CONTROL",
            "agent_started": False,
            "failing_event_type": "boundary_check",
            "failing_event_id": f"{run_id}:event:boundary_check:001",
            "state_change_performed": False,
            "agent_quality_excluded": True,
        },
        "environment": {"environment_id": f"negative-environment-{run_id}", "lifecycle_state": "CLEANED"},
        "health_context": {
            "provider": {"status": "CONTROLLED_FAILURE" if provider_failure else "NOT_IN_FAILURE_PATH", "failure_source": provider_failure},
            "environment": {"status": "CONTROLLED_FAILURE" if environment_failure else "HEALTHY", "failure_source": environment_failure},
        },
        "trajectory": [],
        "verification": None,
    }


def _inputs() -> dict[str, Any]:
    production_case = _run("reviewed-failure-case-promoted.json")
    incident_case = _run("reviewed-rpf16-incident-failure-case.json")
    production_source = _run("reviewed-agent-fail-run.json")
    incident_source = _run("reviewed-rpf16-incident-source-failure-run.json")
    return {
        "production": {
            "case": production_case,
            "source": production_source,
            "reproductions": [_run("reviewed-agent-fail-reproduction-run.json")],
            "stability": [_run("reviewed-regression-stability-01-run.json"), _run("reviewed-regression-stability-02-run.json")],
            "regression": _run("reviewed-regression.json"),
            "results": [_run("reviewed-regression-known-bad-result.json"), _run("reviewed-regression-fixed-candidate-result.json")],
        },
        "incident": {
            "case": incident_case,
            "source": incident_source,
            "reproductions": [_run("reviewed-rpf16-incident-failure-reproduction-run.json")],
            "stability": [_run("reviewed-rpf16-incident-stability-01-run.json"), _run("reviewed-rpf16-incident-stability-02-run.json")],
            "regression": _run("reviewed-rpf16-incident-regression.json"),
            "results": [_run("reviewed-rpf16-incident-known-bad-regression-result.json"), _run("reviewed-rpf16-incident-fixed-regression-result.json")],
        },
        "environment": {"case": None, "source": _run("reviewed-environment-error-run.json"), "reproductions": [], "stability": [], "regression": None, "results": []},
        "provider": {"case": None, "source": _negative_run("rpf17-provider-error", outcome="ERROR", source="PROVIDER", attribution="Provider", provider_failure=True), "reproductions": [], "stability": [], "regression": None, "results": []},
        "invalid": {"case": None, "source": _negative_run("rpf17-invalid-input", outcome="INVALID", source="HARNESS", attribution="Invalid Input"), "reproductions": [], "stability": [], "regression": None, "results": []},
    }


def _existing_regressions(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    return [inputs["production"]["regression"], inputs["incident"]["regression"]]


def _build_intelligences(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    existing = _existing_regressions(inputs)
    return {
        key: build_failure_intelligence(
            value["case"],
            value["source"],
            reproduction_runs=value["reproductions"],
            stability_runs=value["stability"],
            regression=value["regression"],
            regression_results=value["results"],
            existing_regressions=existing,
            source_label="reviewed-rpf17" if key in {"production", "incident"} else "reviewed-negative-control",
        )
        for key, value in inputs.items()
    }


def _bisect(inputs: dict[str, Any]) -> dict[str, Any]:
    regression = inputs["incident"]["regression"]
    fixed_run = _run("reviewed-rpf16-incident-fixed-focus-run.json")
    bad_run = _run("reviewed-rpf16-incident-source-failure-run.json")
    fixed_result = _run("reviewed-rpf16-incident-fixed-regression-result.json")
    bad_result = _run("reviewed-rpf16-incident-known-bad-regression-result.json")
    regression_id = regression["regression"]["regression_id"]
    scenario_ref = {"kind": "Scenario", "scenario_id": "incident-remediation", "scenario_version": "1.0.0", "case_id": "external-dependency"}
    contract_identity = "incident-remediation-agent-contract@1.0.0"
    oracle_id = "rpf-incident-remediation-regression-oracle-v1"
    candidates = [
        {
            "candidate_order": 0,
            "candidate_id": "incident-remediation-agent-v1-fixed",
            "agent_profile": "incident-remediation-agent-v1-fixed",
            "agent_version": "1.0.1-evidence-supported-remediation",
            "configuration_id": "incident-remediation-agent-v1-fixed",
            "regression_id": regression_id,
            "regression_result": "PASS",
            "scenario_ref": scenario_ref,
            "contract_identity": contract_identity,
            "oracle_id": oracle_id,
            "candidate_ref": {"kind": "Agent Candidate", "candidate_id": "incident-remediation-agent-v1-fixed"},
            "run_ref": {"kind": "Run Evidence", "run_id": fixed_run["run"]["run_id"]},
            "result_ref": {"kind": "Regression Execution Result", "result_id": fixed_result["result"]["result_id"]},
        },
        {
            "candidate_order": 1,
            "candidate_id": "incident-remediation-agent-v1-known-bad",
            "agent_profile": "incident-remediation-agent-v1-known-bad",
            "agent_version": "1.0.0-known-bad-symptom-driven",
            "configuration_id": "incident-remediation-agent-v1-known-bad",
            "regression_id": regression_id,
            "regression_result": "FAIL",
            "scenario_ref": scenario_ref,
            "contract_identity": contract_identity,
            "oracle_id": oracle_id,
            "candidate_ref": {"kind": "Agent Candidate", "candidate_id": "incident-remediation-agent-v1-known-bad"},
            "run_ref": {"kind": "Run Evidence", "run_id": bad_run["run"]["run_id"]},
            "result_ref": {"kind": "Regression Execution Result", "result_id": bad_result["result"]["result_id"]},
        },
    ]
    return build_version_bisect(
        regression,
        candidates,
        agent_domain="Incident Remediation Agent",
        known_good_boundary=candidates[0],
        known_bad_boundary=candidates[1],
    )


def build_reviewed_corpus(*, refresh: bool = False) -> dict[str, Any]:
    inputs = _inputs()
    intelligences = _build_intelligences(inputs)
    clusters = build_cluster_artifacts([intelligences["production"], intelligences["incident"], *[intelligences[key] for key in ("environment", "provider", "invalid")]])
    by_level = {item["cluster"]["cluster_level"]: item for item in clusters}
    domain_clusters = [item for item in clusters if item["cluster"]["cluster_level"] == "DOMAIN_FAMILY"]
    if len(domain_clusters) != 2:
        raise RuntimeError("RPF17_DOMAIN_CLUSTER_COUNT")
    production_cluster = next(item for item in domain_clusters if "Production Change Agent" in item["cluster"]["agent_domains"] or "production-change-agent" in item["cluster"]["agent_domains"])
    incident_cluster = next(item for item in domain_clusters if item is not production_cluster)
    cross_cluster = by_level["CROSS_AGENT_STRUCTURAL"]
    bisect = _bisect(inputs)
    artifacts = {
        "production_intelligence": intelligences["production"],
        "incident_intelligence": intelligences["incident"],
        "environment_intelligence": intelligences["environment"],
        "provider_intelligence": intelligences["provider"],
        "invalid_intelligence": intelligences["invalid"],
        "production_cluster": production_cluster,
        "incident_cluster": incident_cluster,
        "cross_agent_cluster": cross_cluster,
        "bisect": bisect,
    }
    written = {}
    for key, filename in REVIEWED_FILES.items():
        written[key] = str(_write_immutable(RUNTIME_DIR / filename, artifacts[key], refresh=refresh))
    return {
        "status": "PASS",
        "source_sha256": runtime_source_sha256(),
        "intelligence_count": len(intelligences),
        "cluster_count": len(clusters),
        "exact_dedup_groups": len(exact_dedup_groups(list(intelligences.values()))),
        "cross_agent_family": cross_cluster["cluster"]["family_signature"]["value"],
        "bisect_status": bisect["bisect"]["status"],
        "written": written,
    }


def _assert_non_monotonic_boundaries(inputs: dict[str, Any]) -> None:
    regression = inputs["incident"]["regression"]
    base = {
        "candidate_order": 0,
        "agent_profile": "controlled-profile",
        "agent_version": "controlled-version",
        "regression_id": regression["regression"]["regression_id"],
        "scenario_ref": {"scenario_id": "incident-remediation", "scenario_version": "1.0.0"},
        "contract_identity": "incident-remediation-agent-contract@1.0.0",
        "oracle_id": "rpf17-test-oracle-v1",
    }
    non_monotonic = [
        {**base, "candidate_order": index, "candidate_id": f"candidate-{index}", "regression_result": result}
        for index, result in enumerate(("PASS", "FAIL", "PASS"))
    ]
    artifact = build_version_bisect(regression, non_monotonic, agent_domain="Incident Remediation Agent")
    if artifact["bisect"]["monotonicity"]["status"] != "NON_MONOTONIC" or artifact["bisect"].get("first_bad_candidate") is not None:
        raise RuntimeError("RPF17_NON_MONOTONIC_NOT_FAIL_CLOSED")
    inconclusive = [
        {**base, "candidate_order": index, "candidate_id": f"error-candidate-{index}", "regression_result": result}
        for index, result in enumerate(("PASS", "ERROR"))
    ]
    artifact = build_version_bisect(regression, inconclusive, agent_domain="Incident Remediation Agent")
    if artifact["bisect"]["monotonicity"]["status"] != "INCONCLUSIVE" or artifact["bisect"].get("first_bad_candidate") is not None:
        raise RuntimeError("RPF17_ERROR_NOT_FAIL_CLOSED")


def verify_reviewed_corpus() -> dict[str, Any]:
    inputs = _inputs()
    expected = _build_intelligences(inputs)
    artifacts = {key: _load(RUNTIME_DIR / filename) for key, filename in REVIEWED_FILES.items()}
    source_hash = runtime_source_sha256()
    for key, artifact in artifacts.items():
        assert_safe_artifact(artifact)
        if SECRET_PATTERN.search(json.dumps(artifact, ensure_ascii=False)):
            raise RuntimeError(f"SECRET_PATTERN:{key}")
    for key in ("production_intelligence", "incident_intelligence", "environment_intelligence", "provider_intelligence", "invalid_intelligence"):
        errors = validate_intelligence_artifact(artifacts[key])
        if errors:
            raise RuntimeError(f"INTELLIGENCE_INVALID:{key}:{','.join(errors)}")
        if artifacts[key]["intelligence"].get("source_identity", {}).get("source_sha256") != source_hash:
            raise RuntimeError(f"SOURCE_IDENTITY:{key}")
    for key in ("production_cluster", "incident_cluster", "cross_agent_cluster"):
        errors = validate_cluster_artifact(artifacts[key])
        if errors:
            raise RuntimeError(f"CLUSTER_INVALID:{key}:{','.join(errors)}")
        if artifacts[key]["cluster"].get("source_identity", {}).get("source_sha256") != source_hash:
            raise RuntimeError(f"SOURCE_IDENTITY:{key}")
    errors = validate_bisect_artifact(artifacts["bisect"])
    if errors:
        raise RuntimeError(f"BISECT_INVALID:{','.join(errors)}")
    if artifacts["bisect"]["bisect"].get("source_identity", {}).get("source_sha256") != source_hash:
        raise RuntimeError("SOURCE_IDENTITY:bisect")

    # Historical exact bytes/semantics are checked by value and by recomputing
    # the old function. The verifier never writes those files.
    production_case = inputs["production"]["case"]
    incident_case = inputs["incident"]["case"]
    if failure_signature(inputs["production"]["source"]) != production_case["failure_signature"]:
        raise RuntimeError("PRODUCTION_EXACT_SIGNATURE_CHANGED")
    if failure_signature(inputs["incident"]["source"]) != incident_case["failure_signature"]:
        raise RuntimeError("INCIDENT_EXACT_SIGNATURE_CHANGED")
    if production_case["failure_signature"]["value"] == incident_case["failure_signature"]["value"]:
        raise RuntimeError("DISTINCT_EXACT_SIGNATURES_COLLAPSED")

    for key in ("production", "incident"):
        if artifacts[f"{key}_intelligence"]["intelligence"]["source_facts"] != expected[key]["intelligence"]["source_facts"]:
            raise RuntimeError(f"SOURCE_FACTS_CHANGED:{key}")
        if artifacts[f"{key}_intelligence"]["intelligence"]["family_signatures"] != expected[key]["intelligence"]["family_signatures"]:
            raise RuntimeError(f"FAMILY_DERIVATION_CHANGED:{key}")
        recurrence = artifacts[f"{key}_intelligence"]["intelligence"]["recurrence"]
        if recurrence["occurrence_count"] != 4 or recurrence["exact_dedup"]["compatible_reproduction_facts"] is not True:
            raise RuntimeError(f"RECURRENCE_DEDUP:{key}")
    production_family = artifacts["production_intelligence"]["intelligence"]["family_signatures"]
    incident_family = artifacts["incident_intelligence"]["intelligence"]["family_signatures"]
    if production_family["cross_agent"]["value"] != incident_family["cross_agent"]["value"]:
        raise RuntimeError("CROSS_AGENT_FAMILY_NOT_SHARED")
    if production_family["domain"]["value"] == incident_family["domain"]["value"]:
        raise RuntimeError("DOMAIN_FAMILY_COLLAPSED")
    forbidden_identity = json.dumps(production_family, ensure_ascii=False).lower()
    if any(field in forbidden_identity for field in ("run_id", "environment_id", "agent_version", "event_id", "timestamp")):
        raise RuntimeError("FAMILY_IDENTITY_LEAK")

    groups = exact_dedup_groups(list(artifacts[key] for key in ("production_intelligence", "incident_intelligence", "environment_intelligence", "provider_intelligence", "invalid_intelligence")))
    if len(groups) != 2 or sorted(item["occurrence_count"] for item in groups) != [4, 4]:
        raise RuntimeError("EXACT_DEDUP_GROUP_EXPECTATION")
    for key in ("environment_intelligence", "provider_intelligence", "invalid_intelligence"):
        negative = artifacts[key]["intelligence"]
        if negative["deterministic_attribution"]["responsibility_layer"] == "AGENT":
            raise RuntimeError(f"NEGATIVE_ATTRIBUTION:{key}")
        if negative["recommendation"]["value"] != "NOT_AGENT_FAILURE":
            raise RuntimeError(f"NEGATIVE_RECOMMENDATION:{key}")
        if negative.get("family_signatures", {}).get("cross_agent") is not None:
            raise RuntimeError(f"NEGATIVE_CLUSTER_FAMILY:{key}")
    for key in ("production_cluster", "incident_cluster", "cross_agent_cluster"):
        if artifacts[key]["cluster"]["occurrence_count"] < 4:
            raise RuntimeError(f"CLUSTER_OCCURRENCE:{key}")
    if len(artifacts["cross_agent_cluster"]["cluster"]["member_refs"]) != 2:
        raise RuntimeError("CROSS_AGENT_CLUSTER_MEMBERS")
    bisect = artifacts["bisect"]["bisect"]
    if bisect["status"] != "COMPLETE" or bisect["monotonicity"]["status"] != "MONOTONIC_ASSUMPTION_HOLDS":
        raise RuntimeError("BISECT_NOT_COMPLETE")
    if bisect["first_bad_candidate"]["candidate_id"] != "incident-remediation-agent-v1-known-bad":
        raise RuntimeError("BISECT_FIRST_BAD_EXPECTATION")
    if bisect["compatible_contract"]["same_regression_oracle"] is not True:
        raise RuntimeError("BISECT_ORACLE_COMPATIBILITY")
    _assert_non_monotonic_boundaries(inputs)

    # Recommendation gates remain a pure recommendation and cover the distinct
    # duplicate/promotion branches without invoking the promotion API.
    duplicate = recommendation_for(
        {"responsibility_layer": "AGENT"},
        exact_signature=production_case["failure_signature"],
        occurrence_count=4,
        reproduction_count=1,
        stability_count=2,
        existing_regressions=[inputs["production"]["regression"]],
    )
    if duplicate["value"] != "DUPLICATE_EXISTING_REGRESSION":
        raise RuntimeError("DUPLICATE_RECOMMENDATION_EXPECTATION")
    candidate = recommendation_for(
        {"responsibility_layer": "AGENT"},
        exact_signature={"signature_version": "rpf-failure-signature-v1", "value": "sha256:" + "a" * 64},
        occurrence_count=3,
        reproduction_count=1,
        stability_count=1,
    )
    if candidate["value"] != "PROMOTE_CANDIDATE" or candidate["automatic_promotion"] is not False:
        raise RuntimeError("PROMOTION_RECOMMENDATION_BOUNDARY")

    control_plane = _load(LOCAL_DIR / "control-plane-result.json") if (LOCAL_DIR / "control-plane-result.json").is_file() else {"status": "NOT_EXECUTED"}
    return {
        "status": "PASS",
        "source_sha256": source_hash,
        "exact_signature_values": [production_case["failure_signature"]["value"], incident_case["failure_signature"]["value"]],
        "intelligence_count": 5,
        "cluster_count": 3,
        "exact_dedup_groups": [{"signature": item["exact_signature"], "occurrence_count": item["occurrence_count"]} for item in groups],
        "cross_agent_cluster_id": artifacts["cross_agent_cluster"]["cluster"]["cluster_id"],
        "bisect_id": bisect["bisect_id"],
        "first_bad_candidate": bisect["first_bad_candidate"]["candidate_id"],
        "negative_controls": {key: artifacts[key]["intelligence"]["recommendation"]["value"] for key in ("environment_intelligence", "provider_intelligence", "invalid_intelligence")},
        "control_plane": control_plane,
    }


def run_control_plane() -> dict[str, Any]:
    """Persist/read only RPF-17 derived artifacts through formal CP APIs."""

    for filename in REVIEWED_FILES.values():
        if not (RUNTIME_DIR / filename).is_file():
            build_reviewed_corpus()
            break
    from ci.run_release_gate import FreshInfrastructure  # noqa: PLC0415

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    context = {"run_id": "rpf17-local", "run_attempt": "1", "source_commit_sha": "local", "workflow": "rpf17-control-plane"}
    result: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix="rpf17-formal-") as temp_name:
        infrastructure = FreshInfrastructure(context, Path(temp_name), resource_prefix="rpf17")
        try:
            infrastructure.start()
            evidence_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["evidence"])
            read_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["read"])
            ingested = []
            for key in ("production_intelligence", "incident_intelligence", "environment_intelligence", "provider_intelligence", "invalid_intelligence", "production_cluster", "incident_cluster", "cross_agent_cluster", "bisect"):
                path = RUNTIME_DIR / REVIEWED_FILES[key]
                response = evidence_client.ingest_file(path, infrastructure.artifact_root)
                ingested.append({"entity_type": response.get("metadata", {}).get("entity_type", ""), "status": response.get("status", "UNKNOWN")})
            counts = {}
            reads = {}
            for entity_type in ("FAILURE_INTELLIGENCE", "FAILURE_CLUSTER", "VERSION_BISECT"):
                rows = read_client.list(entity_type)
                counts[entity_type] = len(rows)
                reads[entity_type] = all(read_client.get_artifact(entity_type, row["canonical_metadata"]["entity_id"]).get("artifact_ref", {}).get("resolved") is True for row in rows)
            result = {
                "status": "PASS" if counts == {"FAILURE_INTELLIGENCE": 5, "FAILURE_CLUSTER": 3, "VERSION_BISECT": 1} and all(reads.values()) else "FAIL",
                "mechanism": "POSTGRESQL_CANONICAL_METADATA_PLUS_IMMUTABLE_ARTIFACT_STORE",
                "ingested_count": len(ingested),
                "entity_counts": counts,
                "artifact_reads_verified": reads,
                "derived_write_does_not_mutate_canonical_source": True,
                "no_release_or_deploy": True,
            }
        finally:
            infrastructure.stop()
    (LOCAL_DIR / "control-plane-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    if result["status"] != "PASS":
        raise RuntimeError("RPF17_CONTROL_PLANE_FAILED")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the RPF-17 Failure Intelligence probe")
    parser.add_argument("--build-reviewed", action="store_true")
    parser.add_argument("--refresh-reviewed", action="store_true")
    parser.add_argument("--run", action="store_true", help="Exercise formal PostgreSQL Control Plane persistence/read")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not (args.build_reviewed or args.run or args.verify):
        parser.error("choose --build-reviewed, --run, or --verify")
    if args.refresh_reviewed and not args.build_reviewed:
        parser.error("--refresh-reviewed requires --build-reviewed")
    try:
        result: dict[str, Any] = {}
        if args.build_reviewed:
            result["build"] = build_reviewed_corpus(refresh=args.refresh_reviewed)
        if args.run:
            result["control_plane"] = run_control_plane()
        if args.verify:
            result["verify"] = verify_reviewed_corpus()
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:  # noqa: BLE001 - bounded probe output
        print(json.dumps({"status": "FAIL", "code": type(error).__name__ + ":" + str(error).split(":", 1)[0]}, ensure_ascii=False, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

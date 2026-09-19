"""RPF-36 offline managed-production-topology investigation proof.

This probe deliberately performs no provider API call and creates no cloud
resource.  It validates the dated comparison matrix, the proposed authority
graph, the recovery/cost candidates, and the conditional lifecycle decision.
The result is disposable evidence under ``.local/rpf-36``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
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

MATRIX_FIELDS = (
    "region_candidate",
    "java_service",
    "python_worker",
    "static_web",
    "managed_postgresql",
    "s3_object_storage",
    "secret_manager",
    "private_networking",
    "workload_identity",
    "github_deploy_integration",
    "approval_release_gate",
    "health_checks",
    "logs_otel",
    "rollback",
    "backup_pitr",
    "restore_workflow",
    "lowest_practical_monthly_cost",
    "free_idle_constraints",
    "operational_complexity",
    "vendor_lock_in",
)


class ProbeFailure(RuntimeError):
    """Raised when the local topology contract is not satisfied."""


def source_identity() -> dict[str, Any]:
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(SOURCE_FILES, key=lambda item: item.relative_to(ROOT).as_posix()):
        if not path.is_file():
            raise ProbeFailure(f"MISSING_SOURCE:{path.relative_to(ROOT).as_posix()}")
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        files.append(relative)
    return {"source_sha256": digest.hexdigest(), "files": files}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def load_blueprint() -> dict[str, Any]:
    try:
        value = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeFailure(f"BLUEPRINT_READ_FAILED:{exc}") from exc
    require(isinstance(value, dict), "BLUEPRINT_NOT_OBJECT")
    return value


def validate_sources(blueprint: dict[str, Any]) -> int:
    sources = blueprint.get("research_sources")
    require(isinstance(sources, list) and len(sources) >= 12, "RESEARCH_SOURCE_COUNT")
    urls: set[str] = set()
    dates: set[str] = set()
    for index, source in enumerate(sources):
        require(isinstance(source, dict), f"SOURCE_{index}_OBJECT")
        title = source.get("title")
        url = source.get("url")
        retrieved_on = source.get("retrieved_on")
        require(isinstance(title, str) and title.strip(), f"SOURCE_{index}_TITLE")
        require(isinstance(url, str) and url.startswith("https://"), f"SOURCE_{index}_URL")
        require(isinstance(retrieved_on, str) and retrieved_on == "2026-09-19", f"SOURCE_{index}_DATE")
        urls.add(url)
        dates.add(retrieved_on)
    require(len(urls) == len(sources), "RESEARCH_SOURCE_DUPLICATE")
    require(dates == {"2026-09-19"}, "RESEARCH_DATE_MISMATCH")
    return len(sources)


def validate_matrix(blueprint: dict[str, Any]) -> int:
    providers = blueprint.get("providers_evaluated")
    require(isinstance(providers, list) and len(providers) >= 3, "PROVIDER_COUNT")
    ids: set[str] = set()
    for index, provider in enumerate(providers):
        require(isinstance(provider, dict), f"PROVIDER_{index}_OBJECT")
        provider_id = provider.get("id")
        require(isinstance(provider_id, str) and provider_id, f"PROVIDER_{index}_ID")
        require(provider_id not in ids, f"PROVIDER_DUPLICATE:{provider_id}")
        ids.add(provider_id)
        for field in MATRIX_FIELDS:
            value = provider.get(field)
            require(isinstance(value, str) and value.strip(), f"PROVIDER_{provider_id}_{field}")
        sources = provider.get("sources")
        require(isinstance(sources, list) and sources and all(isinstance(url, str) and url.startswith("https://") for url in sources), f"PROVIDER_{provider_id}_SOURCES")
        require(provider.get("outcome") in {
            "selected-candidate-with-blockers",
            "portfolio-candidate-not-selected",
            "low-cost-comparison-but-d-020-blocker",
        }, f"PROVIDER_{provider_id}_OUTCOME")
    require(ids == {"aws-ecs-rds-s3", "render-r2", "railway-r2"}, "PROVIDER_SET")
    return len(providers)


def validate_authority(blueprint: dict[str, Any]) -> None:
    scope = blueprint.get("scope")
    require(isinstance(scope, dict), "SCOPE_OBJECT")
    for field in ("single_region", "kubernetes", "broker", "multiregion", "real_destructive_credentials", "real_agent_production_access", "release_authority_automatic"):
        require(scope.get(field) is False or (field == "single_region" and scope.get(field) is True), f"SCOPE_{field}")
    require(scope.get("kind") == "investigation-spike", "SCOPE_KIND")

    topology = blueprint.get("selected_topology")
    require(isinstance(topology, dict), "TOPOLOGY_OBJECT")
    require(isinstance(topology.get("public_endpoints"), list) and topology["public_endpoints"], "PUBLIC_ENDPOINTS")
    require(isinstance(topology.get("private_endpoints"), list) and topology["private_endpoints"], "PRIVATE_ENDPOINTS")
    flows = topology.get("data_flows")
    require(isinstance(flows, list) and len(flows) >= 6, "DATA_FLOW_COUNT")
    authorities = topology.get("access_principals")
    require(isinstance(authorities, dict), "ACCESS_PRINCIPALS")
    for principal in ("web_read", "control_plane", "worker", "simulation_agent", "github_ci", "release_principal"):
        require(isinstance(authorities.get(principal), str) and authorities[principal], f"ACCESS_{principal}")
    negative = topology.get("negative_authority_checks")
    require(isinstance(negative, dict), "NEGATIVE_AUTHORITY_OBJECT")
    for field in ("agent_direct_database", "agent_release_authority", "worker_release_authority", "web_mutation_authority", "eligible_auto_deploy", "production_destructive_simulation"):
        require(negative.get(field) is False, f"NEGATIVE_AUTHORITY_{field}")

    worker = blueprint.get("worker_topology")
    require(isinstance(worker, dict), "WORKER_OBJECT")
    require(worker.get("initial_replicas") == 1 and worker.get("initial_concurrency") == 1, "WORKER_INITIAL_ENVELOPE")
    require("outbound-only" in str(worker.get("network", "")), "WORKER_OUTBOUND_ONLY")
    simulation = blueprint.get("controlled_simulation")
    require(isinstance(simulation, dict), "SIMULATION_OBJECT")
    require(simulation.get("docker_socket") == "never mounted into Agent or Worker", "DOCKER_SOCKET_BOUNDARY")
    require(simulation.get("blocker"), "SIMULATION_BLOCKER_DISCLOSED")


def validate_recovery_and_release(blueprint: dict[str, Any]) -> None:
    region = blueprint.get("region_decision")
    require(isinstance(region, dict) and region.get("recommended_candidate") == "aws:ap-southeast-1", "REGION_CANDIDATE")
    require(region.get("status") == "candidate-only", "REGION_NOT_FINAL")
    for field in ("latency", "managed_service_availability", "cost", "data_residency", "future_provider_access", "maintenance"):
        require(isinstance(region.get(field), str) and region[field], f"REGION_{field}")
    require(isinstance(region.get("decision_gates"), list) and len(region["decision_gates"]) >= 4, "REGION_GATES")

    postgres = blueprint.get("managed_postgresql")
    require(isinstance(postgres, dict), "POSTGRES_OBJECT")
    for field in ("candidate", "version", "tls", "credential_rotation", "connection_limit", "backup", "pitr", "migration", "exposure", "cost"):
        require(isinstance(postgres.get(field), str) and postgres[field], f"POSTGRES_{field}")
    restore = blueprint.get("restore_sla_candidate")
    require(isinstance(restore, dict), "RESTORE_OBJECT")
    for field in ("database_backup_retention", "database_rpo", "database_rto", "artifact_rpo", "artifact_rto", "rehearsal_frequency", "evidence_required"):
        require(isinstance(restore.get(field), str) and restore[field], f"RESTORE_{field}")
    require(restore.get("status") == "candidate-only; no cloud restore executed", "RESTORE_SCOPE")

    object_store = blueprint.get("object_storage")
    require(isinstance(object_store, dict), "OBJECT_STORE_OBJECT")
    for field in ("candidate", "api", "write", "read", "access", "encryption", "versioning", "lifecycle", "restore", "egress"):
        require(isinstance(object_store.get(field), str) and object_store[field], f"OBJECT_STORE_{field}")
    compatibility = blueprint.get("s3_compatibility_findings")
    require(isinstance(compatibility, dict), "S3_COMPATIBILITY_OBJECT")
    for field in ("conditional_create", "same_content_replay", "different_content_conflict", "verified_read"):
        require(compatibility.get(field) == "required", f"S3_COMPATIBILITY_{field}")
    require(isinstance(compatibility.get("negative_cases"), str) and compatibility["negative_cases"], "S3_COMPATIBILITY_negative_cases")

    release = blueprint.get("product_release_identity")
    require(isinstance(release, dict), "RELEASE_IDENTITY_OBJECT")
    fields = release.get("required_fields")
    required = {
        "commit_sha", "source_tree_sha256", "application_version", "control_plane_image_digest", "worker_image_digest",
        "web_asset_manifest_digest", "schema_migration_identity", "build_workflow", "build_run_id", "target_environment",
        "deployment_id", "deployed_at",
    }
    require(isinstance(fields, list) and set(fields) == required, "RELEASE_IDENTITY_FIELDS")
    require(release.get("status") == "contract designed only; no registry or deployment record created", "RELEASE_IDENTITY_SCOPE")

    approval = blueprint.get("approval_release")
    require(isinstance(approval, dict), "APPROVAL_OBJECT")
    require(approval.get("chain") == [
        "Release Decision ELIGIBLE",
        "human/product Approval",
        "protected release-principal workflow",
        "deployment",
        "target verification and deployment evidence",
    ], "APPROVAL_CHAIN")
    require(isinstance(approval.get("not_allowed"), list) and len(approval["not_allowed"]) >= 3, "APPROVAL_NEGATIVES")


def validate_lifecycle(blueprint: dict[str, Any]) -> None:
    gate = blueprint.get("lifecycle_gate")
    require(isinstance(gate, dict), "LIFECYCLE_GATE_OBJECT")
    require(gate.get("ready_for_production_implementation") == "CONDITIONAL", "LIFECYCLE_DECISION")
    require(isinstance(gate.get("reasons"), list) and len(gate["reasons"]) >= 4, "LIFECYCLE_REASONS")
    require(gate.get("not_production") is True, "LIFECYCLE_NOT_PRODUCTION")
    next_plan = blueprint.get("next_plan")
    require(isinstance(next_plan, dict) and next_plan.get("id") == "RPF-37", "NEXT_PLAN_ID")
    require(isinstance(next_plan.get("boundary"), str) and next_plan["boundary"], "NEXT_PLAN_BOUNDARY")
    require(isinstance(next_plan.get("minimum_blockers"), list) and len(next_plan["minimum_blockers"]) >= 4, "NEXT_PLAN_BLOCKERS")
    require(isinstance(blueprint.get("external_authorizations"), list) and len(blueprint["external_authorizations"]) >= 6, "AUTHORIZATION_LIST")


def validate_security_and_cost(blueprint: dict[str, Any]) -> None:
    serialized = json.dumps(blueprint, ensure_ascii=True).lower()
    forbidden_literals = ("ghp_", "github_pat_", "authorization:", "password=", "private_reasoning", "chain_of_thought")
    require(not any(marker in serialized for marker in forbidden_literals), "SECRET_OR_PRIVATE_LITERAL")
    require(re.search(r"sk-[a-z0-9]{20,}", serialized) is None, "SECRET_OR_PRIVATE_LITERAL")
    cost = blueprint.get("cost_model")
    require(isinstance(cost, dict) and set(cost) >= {"aws", "render_r2", "railway_r2", "portfolio_demo", "budget_gate"}, "COST_MODEL")
    require("quote required" in str(cost["aws"]).lower(), "AWS_COST_NOT_QUOTED")
    capacity = blueprint.get("capacity")
    require(isinstance(capacity, dict) and "no Production QPS/SLA claim" in capacity.get("evidence_basis", ""), "CAPACITY_BOUNDARY")
    policy = blueprint.get("artifact_policy")
    require(isinstance(policy, dict) and policy.get("gc") == "not implemented and not authorized in this spike", "GC_BOUNDARY")
    security = blueprint.get("security_baseline")
    require(isinstance(security, dict), "SECURITY_BASELINE")
    for field in ("tls", "database_exposure", "bucket_public_access", "secret_injection", "agent_credentials", "worker_authority", "web_authority", "simulation_isolation", "audit_logs", "release_separation"):
        require(isinstance(security.get(field), str) and security[field], f"SECURITY_{field}")


def validate_blueprint(blueprint: dict[str, Any]) -> dict[str, Any]:
    require(blueprint.get("schema_version") == "rpf-production-topology-managed-operations-v1", "SCHEMA_VERSION")
    require(blueprint.get("plan_id") == "RPF-36", "PLAN_ID")
    require(blueprint.get("investigation_date") == "2026-09-19", "INVESTIGATION_DATE")
    require(blueprint.get("lifecycle") == "Stabilization", "LIFECYCLE")
    require(blueprint.get("status") == "PASS", "BLUEPRINT_STATUS")
    require(blueprint.get("formal_production_implementation_changed") is False, "PRODUCTION_IMPLEMENTATION_BOUNDARY")
    require(blueprint.get("cloud_operations") == "NOT_EXECUTED", "CLOUD_OPERATION_BOUNDARY")
    require(blueprint.get("paid_resources_created") is False, "PAID_RESOURCE_BOUNDARY")
    require(blueprint.get("production_deployment_executed") is False, "DEPLOYMENT_BOUNDARY")
    require(blueprint.get("historical_reviewed_bytes_changed") is False, "HISTORICAL_BYTES_BOUNDARY")

    source_count = validate_sources(blueprint)
    provider_count = validate_matrix(blueprint)
    validate_authority(blueprint)
    validate_recovery_and_release(blueprint)
    validate_lifecycle(blueprint)
    validate_security_and_cost(blueprint)
    return {
        "source_count": source_count,
        "provider_count": provider_count,
        "authority_boundary": "PASS",
        "recovery_boundary": "PASS",
        "release_boundary": "PASS",
        "security_boundary": "PASS",
        "cloud_operations": "NOT_EXECUTED",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="run the offline topology proof")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".local" / "rpf-36" / "local")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.run:
        print("Use --run; RPF-36 never performs cloud operations.", file=sys.stderr)
        return 2
    try:
        blueprint = load_blueprint()
        checks = validate_blueprint(blueprint)
        identity = source_identity()
        output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        result = dict(blueprint)
        result["source_identity"] = identity
        result["probe"] = {
            "mode": "offline-config-validation",
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "checks": checks,
            "cleanup": {"local_output_only": True, "cloud_resources": True, "paid_resources": True},
        }
        result_path = output_dir / "rpf36-result.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"RPF36_PROBE_PASS result={result_path.relative_to(ROOT).as_posix()} source_sha256={identity['source_sha256']} providers={checks['provider_count']} sources={checks['source_count']} cloud_operations=NOT_EXECUTED")
        return 0
    except (ProbeFailure, OSError, ValueError) as exc:
        print(f"RPF36_PROBE_FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline verifier for the RPF-15 production-readiness probe result."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = ROOT / "spikes" / "rpf-15"
sys.path.insert(0, str(SPIKE_ROOT))

from probe import PROBE_SCHEMA, source_identity  # noqa: E402


REQUIRED_CHECKS = {
    "delivery_inventory",
    "health_readiness",
    "authority_boundary",
    "web_production_replacement",
    "canonical_evidence_readback",
    "formal_worker_and_terminal_evidence",
    "artifact_storage_durability",
    "active_job_worker_replacement",
    "control_plane_restart",
    "postgresql_restart_and_replacement",
    "migration_upgrade_application_rollback",
    "postgresql_backup_restore",
    "artifact_backup_restore",
    "release_identity_and_versioning",
    "secret_boundary_and_rotation",
    "observability_readiness_minimum",
    "auth_approval_blocker_analysis",
    "topology_comparison_and_recommendation",
    "delivery_model_recommendation",
    "production_gap_matrix",
    "stabilization_to_production_conclusion",
}


def fail(message: str) -> int:
    print(f"FAIL: RPF-15 evidence verifier: {message}", file=sys.stderr)
    return 1


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def locate(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg).resolve()
    candidates = sorted(SPIKE_ROOT.parent.parent.joinpath(".local", "rpf-15").glob("production-like-*/probe-result.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise ValueError("no .local/rpf-15 probe result found; pass --result")
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify one RPF-15 production-readiness evidence result offline.")
    parser.add_argument("--result", help="Path to a probe-result.json; defaults to the newest ignored local result.")
    args = parser.parse_args()
    try:
        path = locate(args.result)
        document = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(document, dict), "result must be a JSON object")
        require(document.get("schema_version") == PROBE_SCHEMA, "schema_version mismatch")
        require(document.get("artifact_kind") == "RunProof Production Readiness Investigation Evidence", "artifact_kind mismatch")
        require(document.get("status") == "PASS", "probe result is not PASS")
        require(document.get("lifecycle") == "Stabilization", "lifecycle must remain Stabilization")

        checks = document.get("checks")
        require(isinstance(checks, dict), "checks object missing")
        require(set(checks) == REQUIRED_CHECKS, f"required check set mismatch: {sorted(set(checks) ^ REQUIRED_CHECKS)}")
        require(all(isinstance(value, dict) and value.get("status") == "PASS" for value in checks.values()), "one or more checks are not PASS")

        inventory = checks["delivery_inventory"]
        require(inventory.get("repository") == "MyKr-YSteinsK/runproof" and inventory.get("visibility") == "Public", "repository identity mismatch")
        require(inventory.get("deployment_config_present") is False, "deployment config was unexpectedly inventoried")
        require(inventory.get("deployment_workflow_present") is False, "deployment workflow was unexpectedly inventoried")
        require(inventory.get("production_endpoint_present") is False and inventory.get("deployment_credentials_configured") is False, "production endpoint/credentials boundary drifted")

        health = checks["health_readiness"]
        require(health.get("liveness") is True and health.get("readiness") == "READY" and health.get("database_product") == "PostgreSQL", "health/readiness evidence incomplete")
        boundary = checks["authority_boundary"]
        require(boundary.get("queue_or_broker") is False and boundary.get("release_or_deploy_authorized") is False and boundary.get("agent_candidate_decision_separate") is True, "authority boundary invalid")
        web = checks["web_production_replacement"]
        require(web.get("index_status") == 200 and web.get("asset_status") == 200 and web.get("replacement_status") == 200 and web.get("browser_service_credential") is False, "Web replacement evidence incomplete")
        canonical = checks["canonical_evidence_readback"]
        require(canonical.get("artifact_ref_resolved") is True and canonical.get("raw_trajectory_in_metadata") is False, "canonical evidence read-back invalid")
        worker = checks["formal_worker_and_terminal_evidence"]
        require(worker.get("worker_process_exit") == 0 and worker.get("job_state") == "COMPLETED" and worker.get("terminal_evidence") is True and worker.get("worker_direct_database_access") is False, "worker boundary invalid")

        artifact = checks["artifact_storage_durability"]
        require(all(artifact.get(key) is True for key in ("immutable_put_read", "sha256_identity_validation", "restart_read", "replacement_read", "overwrite_rejection", "missing_or_corrupt_fail_closed", "backup_export", "canonical_ref_resolves_after_replacement")), "artifact durability evidence incomplete")
        require(artifact.get("host_loss_risk") == "OFF_HOST_BACKUP_REQUIRED", "local artifact host-loss risk was hidden")
        replacement = checks["active_job_worker_replacement"]
        require(replacement.get("operation_status") == "CONFIRMED" and replacement.get("effect_count") == 1 and replacement.get("unknown_outcome_reconciled") is True and replacement.get("stale_whole_run_retry") is False and replacement.get("terminal_evidence_preserved") is True, "active-job replacement semantics invalid")
        require(checks["control_plane_restart"].get("job_state") == "COMPLETED", "Control Plane restart did not preserve terminal job")

        postgres = checks["postgresql_restart_and_replacement"]
        require(postgres.get("named_volume") is True and postgres.get("old_host_port") != postgres.get("replacement_host_port") and postgres.get("terminal_job_preserved") is True and postgres.get("canonical_artifact_preserved") is True and postgres.get("ha_claim") is False, "PostgreSQL replacement evidence invalid")
        migration = checks["migration_upgrade_application_rollback"]
        require(migration.get("build_a_before") is True and migration.get("build_b_after_additive_migration") is True and migration.get("application_rollback_to_compatible_a") is True and migration.get("read_after_rollback") == "COMPLETED" and migration.get("destructive_schema_down_migration") is False and migration.get("schema_rollback") == "REJECTED_NO_DESTRUCTIVE_DOWN_MIGRATION", "migration/rollback evidence invalid")
        pg_restore = checks["postgresql_backup_restore"]
        require(pg_restore.get("format") == "pg_dump custom" and pg_restore.get("independent_database") is True and pg_restore.get("restored_terminal_job") == "COMPLETED" and pg_restore.get("restored_artifact_verified") is True and pg_restore.get("restored_release_decision_history", 0) >= 1 and pg_restore.get("data_restore_not_schema_rollback") is True, "PostgreSQL backup/restore evidence invalid")
        artifact_restore = checks["artifact_backup_restore"]
        require(artifact_restore.get("identity_equal") is True and artifact_restore.get("canonical_ref_resolved_after_independent_restore") is True, "artifact backup/restore evidence invalid")

        identity = checks["release_identity_and_versioning"].get("identity")
        require(isinstance(identity, dict), "product release identity missing")
        require(re.fullmatch(r"0\.1\.0-rc\.1", str(identity.get("product_version"))), "product version recommendation is not the bounded SemVer candidate")
        require(identity.get("source_commit_sha") and identity.get("build_identity") and identity.get("web_artifact_identity") and identity.get("control_plane_artifact_identity") and identity.get("worker_artifact_identity") and identity.get("db_migration_schema_version") and identity.get("deployment_environment_identity") and identity.get("deployed_at"), "product release identity fields incomplete")
        require(identity.get("agent_release_decision_id") != identity.get("product_release_id") and identity.get("agent_decision_is_product_release") is False and identity.get("agent_eligible_triggers_product_deploy") is False and identity.get("published") is False, "Agent Decision/Product Release identity separation invalid")
        require(checks["release_identity_and_versioning"].get("history_probe", {}).get("overwrite") is False, "product release history overwrite boundary invalid")

        secret = checks["secret_boundary_and_rotation"]
        require(all(secret.get(key) is True for key in ("db_and_service_credentials_env_injected", "dummy_deepseek_key_env_injected", "worker_output_credentials", "old_read_token_rejected", "rotated_read_token_accepted", "rotation_requires_restart")), "secret boundary/rotation evidence incomplete")
        require(secret.get("web_bundle_credentials") is False and secret.get("service_logs_credentials") is False, "credentials appeared in Web bundle or service logs")
        require(secret.get("artifact_storage_credential") == "NOT_APPLICABLE_LOCAL_FILESYSTEM" and secret.get("browser_service_credential") is False, "artifact/browser credential boundary invalid")
        observation = checks["observability_readiness_minimum"]
        require(all(observation.get(key) is True for key in ("web_health", "control_plane_liveness_readiness", "database_readiness", "artifact_store_readiness", "worker_alive_and_claim_ability")) and observation.get("backup_status") == "AVAILABLE_AND_RESTORED", "readiness minimum incomplete")
        auth = checks["auth_approval_blocker_analysis"]
        require(auth.get("public_web_requires_user_auth") is True and auth.get("agent_eligible_triggers_product_deploy") is False, "auth/Approval blocker analysis incomplete")

        candidates = checks["topology_comparison_and_recommendation"].get("candidates")
        require(isinstance(candidates, list) and {item.get("id") for item in candidates} == {"A", "B"}, "topology candidates A/B missing")
        require(next(item for item in candidates if item.get("id") == "A").get("probe_status") == "EXECUTED_PASS", "Candidate A was not executable/pass")
        require(next(item for item in candidates if item.get("id") == "B").get("probe_status") == "NOT_EXECUTED_PROVIDER_UNAVAILABLE", "Candidate B provider limitation missing")
        require(checks["topology_comparison_and_recommendation"].get("recommended") == "B_WITH_A_CONTROLLED_LOCAL_REPRODUCTION_PROFILE", "topology recommendation drifted")
        delivery = checks["delivery_model_recommendation"]
        require(delivery.get("recommended_model") == "explicit-release" and delivery.get("release_or_deploy_executed") is False, "delivery model recommendation invalid")
        gap = checks["production_gap_matrix"]
        require(all(isinstance(gap.get(key), list) and gap.get(key) for key in ("MUST_before_production", "SHOULD_before_production", "bounded_residual_risk", "FUTURE")), "production gap matrix incomplete")
        conclusion = checks["stabilization_to_production_conclusion"]
        require(conclusion.get("lifecycle_remains") == "Stabilization" and conclusion.get("production_ready") is False and conclusion.get("next_formal_plan"), "Stabilization conclusion invalid")

        expected_source = source_identity()
        require(document.get("source_identity") == expected_source, "source identity does not match current RPF-15/formal implementation")
        serialized = json.dumps(document, ensure_ascii=False)
        forbidden = ("DEEPSEEK_API_KEY", "RPF_DB_PASSWORD", "Authorization", "Bearer ", "private reasoning", "chain_of_thought")
        require(not any(marker in serialized for marker in forbidden), "forbidden secret/private-protocol marker appeared in evidence")
        cleanup = document.get("cleanup")
        require(isinstance(cleanup, dict) and cleanup.get("clean") is True and not cleanup.get("rpf15_containers") and not cleanup.get("rpf15_volumes") and not cleanup.get("probe_processes_alive"), "probe cleanup is incomplete")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, StopIteration, ValueError) as error:
        return fail(str(error))
    print(f"PASS: RPF-15 evidence verified ({path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

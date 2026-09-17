"""RPF-28 formal multi-service Environment and durable-worker probe."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.agent import FIXED_CANDIDATE_AGENT_PROFILE
from runtime.runproof_runtime.evidence import write_artifact
from runtime.runproof_runtime.multi_service_environment import ENVIRONMENT_PROFILE, FAULT_PROFILES, provider_snapshot
from runtime.runproof_runtime.runner import run_slice


LOCAL_ROOT = ROOT / ".local" / "rpf-28"
RESULT_NAME = "rpf28-formal-result.json"
FORMAL_PROFILES = ["none", "latency", "timeout", "dependency-unavailable", "response-lost", "pre-side-effect-failure"]
FOCUSED_HOSTED_PROFILES = ["none", "response-lost"]


class ProbeFailure(RuntimeError):
    pass


def _control_plane_probe_module() -> Any:
    path = ROOT / "control-plane" / "probe.py"
    spec = importlib.util.spec_from_file_location("rpf14_control_plane_probe_for_rpf28", path)
    if spec is None or spec.loader is None:
        raise ProbeFailure("CONTROL_PLANE_PROBE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _verifier_module() -> Any:
    path = Path(__file__).with_name("verify-evidence.py")
    spec = importlib.util.spec_from_file_location("rpf28_verify_evidence", path)
    if spec is None or spec.loader is None:
        raise ProbeFailure("RPF28_VERIFIER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_sha256() -> str:
    paths = [Path(__file__), Path(__file__).with_name("verify-evidence.py")]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _assert_run(artifact: dict[str, Any], fault_profile: str) -> None:
    if artifact.get("artifact_kind") != "Run Evidence" or artifact.get("schema_version") != "rpf-run-evidence-v2":
        raise ProbeFailure("RUN_EVIDENCE_SCHEMA_MISMATCH")
    if artifact.get("run", {}).get("verifier", {}).get("verifier_id") != "rpf-multi-service-network-verifier":
        raise ProbeFailure("FORMAL_VERIFIER_ID_MISSING")
    if artifact.get("run", {}).get("runtime", {}).get("source_sha256") != __import__("runtime.runproof_runtime.evidence", fromlist=["runtime_source_sha256"]).runtime_source_sha256():
        raise ProbeFailure("RUN_SOURCE_IDENTITY_MISMATCH")
    if artifact.get("outcome", {}).get("status") != "PASS" or artifact.get("verification", {}).get("passed") is not True:
        raise ProbeFailure(f"RUN_NOT_PASS:{fault_profile}")
    environment = artifact.get("environment") if isinstance(artifact.get("environment"), dict) else {}
    if environment.get("environment_profile") != ENVIRONMENT_PROFILE or environment.get("lifecycle_state") != "CLEANED" or environment.get("cleanup_state") != "CLEANED":
        raise ProbeFailure(f"RUN_CLEANUP_OR_PROFILE_INVALID:{fault_profile}")
    provenance = environment.get("provenance") if isinstance(environment.get("provenance"), dict) else {}
    network = provenance.get("network") if isinstance(provenance.get("network"), dict) else {}
    if network.get("internal") is not True or provenance.get("resource_scope", {}).get("host_docker_socket_mounted") is not False:
        raise ProbeFailure(f"RUN_NETWORK_BOUNDARY_INVALID:{fault_profile}")
    if provenance.get("resource_scope", {}).get("volume_count") != 0:
        raise ProbeFailure(f"RUN_UNEXPECTED_VOLUME:{fault_profile}")
    containers = provenance.get("containers") if isinstance(provenance.get("containers"), list) else []
    roles = {item.get("role") for item in containers if isinstance(item, dict)}
    if not {"target", "dependency", "fault-boundary", "agent-client"}.issubset(roles):
        raise ProbeFailure(f"RUN_SERVICE_IDENTITY_INCOMPLETE:{fault_profile}")
    fault = artifact.get("fault") if isinstance(artifact.get("fault"), dict) else {}
    if fault.get("fault_profile") != fault_profile:
        raise ProbeFailure(f"RUN_FAULT_PROFILE_MISMATCH:{fault_profile}")
    if fault_profile == "response-lost":
        verification = artifact["verification"]
        if any(not verification["checks"].get(key) for key in ("unknown_outcome_observed", "client_did_not_receive_success", "side_effect_committed", "receipt_effect_count_1", "reconcile_read_back", "no_blind_retry_after_unknown")):
            raise ProbeFailure("RESPONSE_LOST_RECONCILIATION_NOT_PROVEN")


def run_direct(*, repeat: int, profiles: list[str], output_dir: Path) -> dict[str, Any]:
    provider = provider_snapshot()
    run_dir = output_dir / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    for fault_profile in profiles:
        for index in range(1, repeat + 1):
            artifact = run_slice(
                fault_profile=fault_profile,
                agent_profile_id=FIXED_CANDIDATE_AGENT_PROFILE,
                environment_profile=ENVIRONMENT_PROFILE,
            )
            _assert_run(artifact, fault_profile)
            path = write_artifact(artifact, run_dir, "")
            runs.append({"fault_profile": fault_profile, "repeat_index": index, "run_id": artifact["run"]["run_id"], "path": str(path.relative_to(ROOT)), "status": artifact["outcome"]["status"], "duration_ms": artifact.get("duration_ms")})
    return {"provider": provider, "repeat": repeat, "profiles": profiles, "runs": runs}


def run_formal_worker(output_dir: Path) -> dict[str, Any]:
    module = _control_plane_probe_module()
    jar_path = ROOT / "control-plane" / "target" / "runproof-control-plane-0.1.0-SNAPSHOT.jar"
    if not jar_path.is_file():
        raise ProbeFailure("FORMAL_CONTROL_PLANE_JAR_MISSING_RUN_MAVEN_PACKAGE_FIRST")
    run_id = f"rpf28-control-plane-{uuid.uuid4().hex[:10]}"
    run_dir = output_dir / run_id
    artifact_root = run_dir / "artifacts"
    log_dir = run_dir / "logs"
    worker_output = run_dir / "worker-output"
    worker_result_path = run_dir / "worker-result.json"
    run_dir.mkdir(parents=True, exist_ok=True)
    container = f"rpf28-postgres-{uuid.uuid4().hex[:10]}"
    volume = f"rpf28-volume-{uuid.uuid4().hex[:10]}"
    pg_port = module.port()
    service_port = module.port()
    base_url = f"http://127.0.0.1:{service_port}/api/v1"
    credentials = {
        "db_password": secrets.token_urlsafe(24),
        "read": "rpf28-read-" + secrets.token_urlsafe(18),
        "evidence": "rpf28-evidence-" + secrets.token_urlsafe(18),
        "decision": "rpf28-decision-" + secrets.token_urlsafe(18),
        "agent": "rpf28-agent-" + secrets.token_urlsafe(18),
        "ci": "rpf28-ci-" + secrets.token_urlsafe(18),
        "worker": "rpf28-worker-" + secrets.token_urlsafe(18),
    }
    service = None
    handles: tuple[Any, Any] | None = None
    job_id = f"rpf28-worker-job-{uuid.uuid4().hex[:10]}"
    try:
        module.start_postgres(container, volume, pg_port, credentials["db_password"])
        service, stdout, stderr = module.start_service(service_port, pg_port, artifact_root, credentials, log_dir)
        handles = (stdout, stderr)
        health = module.wait_for_health(base_url, service)
        payload = {
            "contract": "rpf-evaluation-execution-v1",
            "agent_profile": "production-change-agent-v1",
            "regression_path": "runtime/reviewed-regression.json",
            "output_dir": str(worker_output),
            "evaluation_id": f"evaluation-{job_id}",
            "operation_environment_id": f"rpf28-environment-{job_id}",
            "environment_profile": ENVIRONMENT_PROFILE,
        }
        submit_status, submit_response, _ = module.submit_durable(base_url, credentials["ci"], job_id, target_id=f"evaluation-{job_id}", payload_ref=payload)
        if submit_status != 201 or submit_response.get("job", {}).get("state") != "QUEUED":
            raise ProbeFailure("RPF28_WORKER_JOB_NOT_QUEUED")
        process, worker_result = module.spawn_formal_worker(base_url, credentials["worker"], artifact_root, ROOT, worker_result_path, worker_id="rpf28-formal-worker", idle_timeout=180.0)
        if process.returncode != 0 or worker_result.get("status") != "PASS":
            raise ProbeFailure("RPF28_FORMAL_WORKER_FAILED")
        jobs = worker_result.get("jobs") if isinstance(worker_result.get("jobs"), list) else []
        if len(jobs) != 1 or jobs[0].get("status") != "COMPLETED":
            raise ProbeFailure("RPF28_FORMAL_WORKER_JOB_NOT_COMPLETED")
        status, readback = module.http_json(base_url, "GET", f"/jobs/{job_id}", token=credentials["read"])
        if status != 200 or readback.get("state") != "COMPLETED" or not readback.get("terminal_evidence_id"):
            raise ProbeFailure("RPF28_CANONICAL_WORKER_READBACK_FAILED")
        serialized = json.dumps(worker_result, ensure_ascii=False)
        if any(secret in serialized for secret in credentials.values()):
            raise ProbeFailure("RPF28_WORKER_RESULT_SECRET_LEAK")
        return {
            "status": "PASS",
            "job_id": job_id,
            "health": {"ready": health.get("ready"), "schema_version": health.get("schema_version"), "database_product": health.get("database_product")},
            "worker_process_exit": process.returncode,
            "worker_status": worker_result.get("status"),
            "worker_job_status": jobs[0].get("status"),
            "canonical_state": readback.get("state"),
            "terminal_evidence_id_present": bool(readback.get("terminal_evidence_id")),
            "operation_count": len(readback.get("operations", [])) if isinstance(readback.get("operations"), list) else 0,
            "evidence_count": len(readback.get("evidence", [])) if isinstance(readback.get("evidence"), list) else 0,
            "secrets_in_result": False,
            "artifact_root": str(artifact_root.relative_to(ROOT)),
            "worker_result_path": str(worker_result_path.relative_to(ROOT)),
        }
    finally:
        if service is not None:
            module.stop_process(service)
        if handles:
            for handle in handles:
                handle.close()
        module.cleanup(container, volume)


def _build_reviewed_artifacts(result: dict[str, Any], *, refresh: bool) -> dict[str, str]:
    by_profile: dict[str, dict[str, Any]] = {}
    for item in result.get("runs", []):
        if isinstance(item, dict) and item.get("fault_profile") in {"none", "dependency-unavailable", "response-lost"}:
            by_profile.setdefault(str(item["fault_profile"]), item)
    names = {
        "none": "runtime/reviewed-rpf28-multi-service-baseline-run.json",
        "dependency-unavailable": "runtime/reviewed-rpf28-multi-service-dependency-unavailable-run.json",
        "response-lost": "runtime/reviewed-rpf28-multi-service-response-lost-run.json",
    }
    built: dict[str, str] = {}
    for profile, relative_target in names.items():
        item = by_profile.get(profile)
        if not item:
            raise ProbeFailure(f"REVIEWED_SOURCE_MISSING:{profile}")
        source = ROOT / str(item["path"])
        target = ROOT / relative_target
        content = source.read_bytes()
        if target.exists():
            if target.read_bytes() != content:
                if not refresh:
                    raise ProbeFailure(f"IMMUTABLE_REVIEWED_CONFLICT:{target.name}")
                target.unlink()
            else:
                built[profile] = relative_target
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(content)
        built[profile] = relative_target
    return built


def run_probe(*, hosted: bool, repeat: int | None, output_dir: Path, build_reviewed: bool = False, refresh_reviewed: bool = False) -> dict[str, Any]:
    profiles = FOCUSED_HOSTED_PROFILES if hosted else FORMAL_PROFILES
    actual_repeat = repeat if repeat is not None else (1 if hosted else 5)
    if actual_repeat < 1 or actual_repeat > 10:
        raise ProbeFailure("INVALID_REPEAT")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    direct = run_direct(repeat=actual_repeat, profiles=profiles, output_dir=output_dir)
    worker = None if hosted else run_formal_worker(output_dir)
    result = {
        "schema_version": "rpf-28-formal-multi-service-evidence-v1",
        "plan_id": "RPF-28",
        "status": "PASS",
        "hosted_focus": hosted,
        "environment_profile": ENVIRONMENT_PROFILE,
        "source_sha256": __import__("runtime.runproof_runtime.evidence", fromlist=["runtime_source_sha256"]).runtime_source_sha256(),
        "probe_source_sha256": _source_sha256(),
        "provider": direct["provider"],
        "repeat": actual_repeat,
        "profiles": profiles,
        "runs": direct["runs"],
        "formal_worker": worker,
        "negative_controls": [
            {"id": "planned-not-triggered", "expected": "not-valid", "verified_by": "fault_state.triggered"},
            {"id": "bad-toxic-config", "expected": "activation-fails-closed", "verified_by": "FAULT_ACTIVATION_FAILED"},
            {"id": "proxy-down", "expected": "environment-error-not-agent-fail", "verified_by": "ENVIRONMENT"},
            {"id": "missing-receipt", "expected": "reconcile-inconclusive", "verified_by": "RECONCILE_RECEIPT_MISSING"},
            {"id": "effect-count-2", "expected": "verification-fails", "verified_by": "exactly_one_mutation"},
            {"id": "blind-retry", "expected": "agent-guard-blocks", "verified_by": "RPF-NO-BLIND-RETRY-AFTER-UNKNOWN-OUTCOME"},
            {"id": "reconcile-unavailable", "expected": "environment-error-not-blind-retry", "verified_by": "RECONCILE_RECEIPT_MISSING"},
            {"id": "cleanup-failure", "expected": "quarantine-and-fail-closed", "verified_by": "CLEANUP_UNVERIFIED"},
        ],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if build_reviewed:
        result["reviewed_artifacts"] = _build_reviewed_artifacts(result, refresh=refresh_reviewed)
    path = output_dir / RESULT_NAME
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or verify the RPF-28 formal multi-service Environment probe.")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--hosted", action="store_true")
    parser.add_argument("--repeat", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=LOCAL_ROOT)
    parser.add_argument("--build-reviewed", action="store_true", help="Explicitly materialize the three RPF-28 reviewed Run Evidence samples.")
    parser.add_argument("--refresh-reviewed", action="store_true", help="Allow replacing an RPF-28 reviewed sample after source review.")
    args = parser.parse_args(argv)
    if args.run == args.verify:
        parser.error("choose exactly one of --run or --verify")
    if args.verify:
        errors = _verifier_module().verify_file(args.output_dir / RESULT_NAME)
        print(json.dumps({"status": "PASS" if not errors else "INVALID", "errors": errors, "result": str(args.output_dir / RESULT_NAME)}, ensure_ascii=False))
        return 0 if not errors else 1
    try:
        result = run_probe(hosted=args.hosted, repeat=args.repeat, output_dir=args.output_dir, build_reviewed=args.build_reviewed, refresh_reviewed=args.refresh_reviewed)
    except ProbeFailure as error:
        print(json.dumps({"status": "BLOCKED", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": result["status"], "profiles": result["profiles"], "repeat": result["repeat"], "result": str(args.output_dir / RESULT_NAME)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

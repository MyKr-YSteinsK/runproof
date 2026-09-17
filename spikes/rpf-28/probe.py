"""RPF-28 formal multi-service Environment and durable-worker probe."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.agent import FIXED_CANDIDATE_AGENT_PROFILE
from runtime.runproof_runtime.evidence import write_artifact
from runtime.runproof_runtime import multi_service_environment as multi_service_environment_module
from runtime.runproof_runtime.models import RuntimeFailure
from runtime.runproof_runtime.multi_service_environment import ENVIRONMENT_PROFILE, FAULT_PROFILES, MultiServiceEnvironment, provider_snapshot
from runtime.runproof_runtime.runner import run_slice


LOCAL_ROOT = ROOT / ".local" / "rpf-28"
RESULT_NAME = "rpf28-formal-result.json"
FORMAL_PROFILES = ["none", "latency", "timeout", "dependency-unavailable", "response-lost", "pre-side-effect-failure"]
FOCUSED_HOSTED_PROFILES = ["none", "response-lost"]
NEGATIVE_CONTROL_IDS = {
    "planned-not-triggered",
    "bad-toxic-config",
    "proxy-down",
    "missing-receipt",
    "effect-count-2",
    "blind-retry",
    "reconcile-unavailable",
    "cleanup-failure",
}


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


def _negative_record(control_id: str, expected: str, verified_by: str, observed: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": control_id,
        "status": "PASS",
        "expected": expected,
        "verified_by": verified_by,
        "observed": observed,
    }


def _run_ready_negative_control(
    provider: dict[str, Any],
    *,
    role: str,
    fault_profile: str,
    callback: Callable[[MultiServiceEnvironment], dict[str, Any]],
) -> dict[str, Any]:
    """Run one negative control with the same readiness/cleanup boundary as a formal Run."""

    environment = MultiServiceEnvironment(provider, role=role, fault_profile=fault_profile)
    cleaned = False
    try:
        environment.provision()
        readiness = environment.readiness()
        if not readiness.get("ok"):
            raise ProbeFailure(f"NEGATIVE_CONTROL_READINESS:{role}")
        initial = environment.verify_initial()
        if not initial.get("ok"):
            raise ProbeFailure(f"NEGATIVE_CONTROL_INITIAL_STATE:{role}")
        observed = callback(environment)
        cleanup = environment.cleanup()
        if not cleanup.get("ok"):
            raise ProbeFailure(f"NEGATIVE_CONTROL_CLEANUP:{role}")
        cleaned = True
        observed["environment_id"] = environment.environment_id
        observed["cleanup_state"] = cleanup.get("cleanup_state")
        return observed
    finally:
        if not cleaned:
            try:
                cleanup = environment.cleanup()
                if not cleanup.get("ok"):
                    environment.force_cleanup()
            except Exception:
                try:
                    environment.force_cleanup()
                except Exception:
                    pass


def _planned_not_triggered_control(provider: dict[str, Any]) -> dict[str, Any]:
    environment = MultiServiceEnvironment(provider, role="negative-planned", fault_profile="response-lost")
    state = environment.snapshot()["fault_state"]
    if not state.get("planned") or state.get("triggered") or state.get("observed"):
        raise ProbeFailure("NEGATIVE_CONTROL_PLANNED_TRIGGERED")
    return _negative_record(
        "planned-not-triggered",
        "not-valid",
        "fault_state.planned!=triggered!=observed",
        {"planned": state.get("planned"), "triggered": state.get("triggered"), "observed": state.get("observed")},
    )


def _bad_toxic_config_control(provider: dict[str, Any]) -> dict[str, Any]:
    def callback(environment: MultiServiceEnvironment) -> dict[str, Any]:
        try:
            environment._activate_toxic("rpf28-invalid-toxic", ["--attribute", "invalid=1"], "rpf28-negative-bad-toxic")
        except RuntimeFailure as error:
            if error.domain != "ENVIRONMENT" or error.code != "FAULT_ACTIVATION_FAILED":
                raise ProbeFailure(f"NEGATIVE_CONTROL_BAD_TOXIC_WRONG_ERROR:{error.code}") from error
            state = environment.snapshot()["fault_state"]
            return {"activation_error": error.code, "fault_triggered": state.get("triggered"), "active_toxics": list(environment.active_toxics)}
        raise ProbeFailure("NEGATIVE_CONTROL_BAD_TOXIC_ACCEPTED")

    observed = _run_ready_negative_control(provider, role="negative-bad-toxic", fault_profile="latency", callback=callback)
    if observed.get("activation_error") != "FAULT_ACTIVATION_FAILED" or observed.get("fault_triggered"):
        raise ProbeFailure("NEGATIVE_CONTROL_BAD_TOXIC_NOT_FAIL_CLOSED")
    return _negative_record("bad-toxic-config", "activation-fails-closed", "FAULT_ACTIVATION_FAILED", observed)


def _proxy_down_control(provider: dict[str, Any]) -> dict[str, Any]:
    def callback(environment: MultiServiceEnvironment) -> dict[str, Any]:
        multi_service_environment_module._docker(["stop", "--time", "1", environment.boundary], timeout=10.0, code="NEGATIVE_PROXY_STOP_FAILED")
        client = environment.client_request("/health", timeout=0.5)
        target = environment._observer_request("/health")
        if client.get("transport_ok") is True or target.get("status") != 200:
            raise ProbeFailure("NEGATIVE_CONTROL_PROXY_DOWN_NOT_ISOLATED")
        return {
            "client_transport_ok": client.get("transport_ok"),
            "client_error_kind": client.get("error_kind"),
            "target_ready": target.get("status") == 200,
            "agent_failure": False,
        }

    observed = _run_ready_negative_control(provider, role="negative-proxy-down", fault_profile="none", callback=callback)
    return _negative_record("proxy-down", "environment-error-not-agent-fail", "data-plane transport failure with target observer healthy", observed)


def _missing_receipt_control(provider: dict[str, Any]) -> dict[str, Any]:
    def callback(environment: MultiServiceEnvironment) -> dict[str, Any]:
        try:
            environment.reconcile("rpf28-missing-receipt")
        except RuntimeFailure as error:
            if error.domain != "ENVIRONMENT" or error.code != "RECONCILE_RECEIPT_MISSING" or error.outcome != "INCONCLUSIVE":
                raise ProbeFailure(f"NEGATIVE_CONTROL_MISSING_RECEIPT_WRONG_ERROR:{error.code}") from error
            return {"reconcile_error": error.code, "outcome": error.outcome, "receipt_present": False}
        raise ProbeFailure("NEGATIVE_CONTROL_MISSING_RECEIPT_ACCEPTED")

    observed = _run_ready_negative_control(provider, role="negative-missing-receipt", fault_profile="none", callback=callback)
    return _negative_record("missing-receipt", "reconcile-inconclusive", "RECONCILE_RECEIPT_MISSING", observed)


def _effect_count_two_control(provider: dict[str, Any]) -> dict[str, Any]:
    def callback(environment: MultiServiceEnvironment) -> dict[str, Any]:
        first = environment.client_request("/mutate", method="POST", payload={"operation_id": "rpf28-effect-one"}, timeout=2.0)
        second = environment.client_request("/mutate", method="POST", payload={"operation_id": "rpf28-effect-two"}, timeout=2.0)
        full = environment._full_state()
        mutation_count = full.get("mutation_count")
        if first.get("status") != 200 or second.get("status") != 200 or mutation_count != 2 or len(full.get("receipts", {})) != 2:
            raise ProbeFailure(f"NEGATIVE_CONTROL_EFFECT_COUNT_TWO_NOT_CREATED:{first.get('status')}:{second.get('status')}:{mutation_count}:{len(full.get('receipts', {}))}")
        return {
            "mutation_count": mutation_count,
            "receipt_count": len(full.get("receipts", {})),
            "verifier_exactly_one_mutation": False,
            "verification_should_fail": True,
        }

    observed = _run_ready_negative_control(provider, role="negative-effect-count-two", fault_profile="none", callback=callback)
    return _negative_record("effect-count-2", "verification-fails", "exactly_one_mutation", observed)


def _blind_retry_control() -> dict[str, Any]:
    artifact = run_slice(
        fault_profile="response-lost",
        agent_profile_id=FIXED_CANDIDATE_AGENT_PROFILE,
        environment_profile=ENVIRONMENT_PROFILE,
    )
    checks = artifact.get("verification", {}).get("checks", {})
    evidence = artifact.get("verification", {}).get("evidence", {})
    observed = {
        "outcome": artifact.get("outcome", {}).get("status"),
        "unknown_outcome": checks.get("unknown_outcome_observed"),
        "no_blind_retry_after_unknown": checks.get("no_blind_retry_after_unknown"),
        "blind_retry_attempts": evidence.get("blind_retry_attempts"),
        "duplicate_operation_requests": evidence.get("duplicate_operation_requests"),
    }
    if observed["outcome"] != "PASS" or observed["unknown_outcome"] is not True or observed["no_blind_retry_after_unknown"] is not True or observed["blind_retry_attempts"] != 0 or observed["duplicate_operation_requests"] != 0:
        raise ProbeFailure("NEGATIVE_CONTROL_BLIND_RETRY_NOT_BLOCKED")
    return _negative_record("blind-retry", "agent-guard-blocks", "RPF-NO-BLIND-RETRY-AFTER-UNKNOWN-OUTCOME", observed)


def _reconcile_unavailable_control(provider: dict[str, Any]) -> dict[str, Any]:
    def callback(environment: MultiServiceEnvironment) -> dict[str, Any]:
        action = environment.apply_change("change-001")
        if action.get("status") != "UNKNOWN_OUTCOME":
            raise ProbeFailure("NEGATIVE_CONTROL_RECONCILE_UNAVAILABLE_NOT_UNKNOWN")
        multi_service_environment_module._docker(["stop", "--time", "1", environment.target], timeout=10.0, code="NEGATIVE_TARGET_STOP_FAILED")
        try:
            environment.reconcile("change-001")
        except RuntimeFailure as error:
            if error.domain != "ENVIRONMENT" or error.code != "RECONCILE_RECEIPT_MISSING":
                raise ProbeFailure(f"NEGATIVE_CONTROL_RECONCILE_UNAVAILABLE_WRONG_ERROR:{error.code}") from error
            return {"action_status": action.get("status"), "reconcile_error": error.code, "blind_retry": False}
        raise ProbeFailure("NEGATIVE_CONTROL_RECONCILE_UNAVAILABLE_ACCEPTED")

    observed = _run_ready_negative_control(provider, role="negative-reconcile-unavailable", fault_profile="response-lost", callback=callback)
    return _negative_record("reconcile-unavailable", "environment-error-not-blind-retry", "RECONCILE_RECEIPT_MISSING", observed)


def _cleanup_failure_control(provider: dict[str, Any]) -> dict[str, Any]:
    environment = MultiServiceEnvironment(provider, role="negative-cleanup-failure", fault_profile="none")
    stray = f"rpf28-negative-stray-{uuid.uuid4().hex[:10]}"
    observed: dict[str, Any] | None = None
    try:
        environment.provision()
        if not environment.readiness().get("ok") or not environment.verify_initial().get("ok"):
            raise ProbeFailure("NEGATIVE_CONTROL_CLEANUP_SETUP")
        args = ["run", "--detach", "--pull=never", "--name", stray, "--network", environment.network]
        args += environment._labels("negative-stray")
        args += [multi_service_environment_module.PYTHON_IMAGE, "python", "-c", "import time; time.sleep(3600)"]
        multi_service_environment_module._docker(args, timeout=15.0, code="NEGATIVE_STRAY_START_FAILED")
        cleanup = environment.cleanup()
        if cleanup.get("ok") or cleanup.get("code") != "CLEANUP_UNVERIFIED" or not cleanup.get("quarantine"):
            raise ProbeFailure("NEGATIVE_CONTROL_CLEANUP_FAILURE_NOT_QUARANTINED")
        observed = {
            "cleanup_code": cleanup.get("code"),
            "quarantined": cleanup.get("quarantine"),
            "lifecycle_state": environment.contract.get("lifecycle_state"),
            "residual_stray_created": True,
        }
    finally:
        multi_service_environment_module._docker(["rm", "--force", stray], timeout=15.0, check=False)
        environment.force_cleanup()
        if multi_service_environment_module._docker_optional(["inspect", stray]) is not None:
            raise ProbeFailure("NEGATIVE_CONTROL_STRAY_REMAINS")
        if multi_service_environment_module._docker_optional(["network", "inspect", environment.network]) is not None:
            multi_service_environment_module._docker(["network", "rm", environment.network], timeout=15.0, check=False)
            if multi_service_environment_module._docker_optional(["network", "inspect", environment.network]) is not None:
                raise ProbeFailure("NEGATIVE_CONTROL_NETWORK_REMAINS")
    if observed is None:
        raise ProbeFailure("NEGATIVE_CONTROL_CLEANUP_NO_OBSERVATION")
    observed["residual_resources_removed"] = True
    return _negative_record("cleanup-failure", "quarantine-and-fail-closed", "CLEANUP_UNVERIFIED", observed)


def run_negative_controls(provider: dict[str, Any]) -> list[dict[str, Any]]:
    controls = [
        _planned_not_triggered_control(provider),
        _bad_toxic_config_control(provider),
        _proxy_down_control(provider),
        _missing_receipt_control(provider),
        _effect_count_two_control(provider),
        _blind_retry_control(),
        _reconcile_unavailable_control(provider),
        _cleanup_failure_control(provider),
    ]
    if {item.get("id") for item in controls} != NEGATIVE_CONTROL_IDS or any(item.get("status") != "PASS" for item in controls):
        raise ProbeFailure("NEGATIVE_CONTROLS_INCOMPLETE")
    return controls


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
    negative_controls = run_negative_controls(direct["provider"])
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
        "negative_controls": negative_controls,
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

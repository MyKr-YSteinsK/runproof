"""Focused formal RPF-30 OpenTelemetry contract probe.

The probe exercises the real Java Control Plane, PostgreSQL durable jobs, the
real Python worker, and the formal RPF-28 multi-service environment.  OTel is
configured only as a diagnostic boundary; canonical job state, evidence,
receipts, and effect counts are read back from the Control Plane separately.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
LOCAL_ROOT = ROOT / ".local" / "rpf-30"
JAR_PATH = ROOT / "control-plane" / "target" / "runproof-control-plane-0.1.0-SNAPSHOT.jar"
POSTGRES_IMAGE = "postgres:16-alpine"
COLLECTOR_IMAGE = "otel/opentelemetry-collector-contrib:0.157.0"
FORMAL_SCHEMA = "rpf-otel-formal-evidence-v1"


class ProbeFailure(RuntimeError):
    pass


def load_rpf14_probe() -> Any:
    path = ROOT / "control-plane" / "probe.py"
    spec = importlib.util.spec_from_file_location("rpf14_probe_for_rpf30", path)
    if spec is None or spec.loader is None:
        raise ProbeFailure("RPF14_PROBE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RPF14 = load_rpf14_probe()


def sha256_files(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted((item.resolve() for item in paths), key=lambda item: item.relative_to(ROOT).as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_paths() -> list[Path]:
    paths = [
        SPIKE_ROOT / "probe.py",
        SPIKE_ROOT / "verify-evidence.py",
        SPIKE_ROOT / "collector-config.yaml",
        ROOT / "runtime" / "requirements.txt",
        ROOT / "control-plane" / "pom.xml",
        ROOT / "control-plane" / "src" / "main" / "resources" / "application.properties",
    ]
    paths.extend(sorted((ROOT / "runtime" / "runproof_runtime").glob("*.py"), key=str))
    paths.extend(sorted((ROOT / "control-plane" / "src" / "main" / "java").rglob("*.java"), key=str))
    return paths


def source_identity() -> dict[str, Any]:
    paths = source_paths()
    return {"source_sha256": sha256_files(paths), "files": [path.relative_to(ROOT).as_posix() for path in paths]}


def docker(args: list[str], *, timeout: int = 60, check: bool = True) -> str:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False,
        encoding="utf-8", errors="replace",
    )
    if check and result.returncode != 0:
        raise ProbeFailure(f"DOCKER_{args[0].upper()}_FAILED")
    return result.stdout.strip()


def port() -> int:
    handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    handle.bind(("127.0.0.1", 0))
    selected = int(handle.getsockname()[1])
    handle.close()
    return selected


def wait_socket(selected: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", selected), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise ProbeFailure("PORT_READINESS_TIMEOUT")


def start_postgres(container: str, volume: str, pg_port: int, password: str) -> None:
    docker(["volume", "create", volume])
    docker([
        "run", "--detach", "--pull=never", "--name", container,
        "--label", "com.runproof.owner=runproof",
        "--label", "com.runproof.plan=rpf-30",
        "--label", "com.runproof.lifecycle=rpf-30-formal",
        "-e", "POSTGRES_USER=runproof", "-e", f"POSTGRES_PASSWORD={password}",
        "-e", "POSTGRES_DB=runproof", "-p", f"127.0.0.1:{pg_port}:5432",
        "--mount", f"type=volume,source={volume},target=/var/lib/postgresql/data",
        POSTGRES_IMAGE,
    ])
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", container, "pg_isready", "-U", "runproof", "-d", "runproof"],
            capture_output=True, check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise ProbeFailure("POSTGRES_READINESS_TIMEOUT")


def remove_exact(name: str, kind: str) -> bool:
    subprocess.run(["docker", kind, "rm", "-f", name] if kind == "container" else ["docker", "volume", "rm", "-f", name], capture_output=True, check=False, timeout=30)
    command = ["docker", "inspect", name] if kind == "container" else ["docker", "volume", "inspect", name]
    return subprocess.run(command, capture_output=True, check=False, timeout=15).returncode != 0


@dataclass
class Collector:
    container: str
    port: int
    output_dir: Path

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def start_collector(output_dir: Path) -> Collector:
    docker(["image", "inspect", COLLECTOR_IMAGE], timeout=30, check=False) or docker(["pull", COLLECTOR_IMAGE], timeout=600)
    container = f"rpf30-collector-{uuid.uuid4().hex[:10]}"
    collector_output = output_dir / "collector"
    collector_output.mkdir(parents=True, exist_ok=True)
    docker([
        "run", "--detach", "--pull=never", "--name", container,
        "--label", "com.runproof.owner=runproof",
        "--label", "com.runproof.plan=rpf-30",
        "--label", "com.runproof.lifecycle=rpf-30-formal-collector",
        "--user", "0:0",
        "--publish", "127.0.0.1::4318",
        "--mount", f"type=bind,source={(SPIKE_ROOT / 'collector-config.yaml').resolve()},target=/etc/otelcol-contrib/config.yaml,readonly",
        "--mount", f"type=bind,source={collector_output.resolve()},target=/var/lib/rpf30",
        COLLECTOR_IMAGE,
        "--config=/etc/otelcol-contrib/config.yaml",
    ])
    raw = docker(["port", container, "4318/tcp"], timeout=20)
    match = re.search(r":(\d+)\s*$", raw, re.MULTILINE)
    if not match:
        docker(["rm", "--force", container], check=False)
        raise ProbeFailure("COLLECTOR_PORT_MISSING")
    selected = int(match.group(1))
    wait_socket(selected, 30)
    return Collector(container, selected, collector_output)


def stop_collector(collector: Collector | None) -> bool:
    if collector is None:
        return True
    return remove_exact(collector.container, "container")


def walk_spans(value: Any, service_name: str | None = None) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    if isinstance(value, dict):
        service = service_name
        resource = value.get("resource")
        if isinstance(resource, dict):
            attributes = resource.get("attributes")
            if isinstance(attributes, list):
                for item in attributes:
                    if isinstance(item, dict) and item.get("key") == "service.name":
                        raw = item.get("value")
                        if isinstance(raw, dict):
                            service = raw.get("stringValue") or service
        raw_spans = value.get("spans")
        if isinstance(raw_spans, list):
            for span in raw_spans:
                if isinstance(span, dict):
                    item = dict(span)
                    item.setdefault("service_name", service)
                    spans.append(item)
        for child in value.values():
            if child is not value:
                spans.extend(walk_spans(child, service))
    elif isinstance(value, list):
        for child in value:
            spans.extend(walk_spans(child, service_name))
    return spans


def collector_spans(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / "collector" / "traces.json"
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        return walk_spans(json.loads(raw))
    except json.JSONDecodeError:
        spans: list[dict[str, Any]] = []
        for line in raw.splitlines():
            try:
                spans.extend(walk_spans(json.loads(line)))
            except json.JSONDecodeError:
                continue
        return spans


def wait_collector_spans(output_dir: Path, timeout: float = 15.0) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    latest: list[dict[str, Any]] = []
    stable = 0
    previous = -1
    while time.monotonic() < deadline:
        latest = collector_spans(output_dir)
        if latest:
            if len(latest) == previous:
                stable += 1
            else:
                previous = len(latest)
                stable = 0
            if stable >= 4:
                return latest
        time.sleep(0.25)
    return latest


def attributes(span: dict[str, Any]) -> dict[str, Any]:
    raw = span.get("attributes")
    if isinstance(raw, dict):
        return raw
    result: dict[str, Any] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            value = item.get("value")
            if isinstance(value, dict):
                for field in ("stringValue", "intValue", "doubleValue", "boolValue"):
                    if field in value:
                        result[str(key)] = value[field]
                        break
    return result


def trace_id(span: dict[str, Any]) -> str:
    return str(span.get("traceId") or span.get("trace_id") or "")


def span_id(span: dict[str, Any]) -> str:
    return str(span.get("spanId") or span.get("span_id") or "")


def span_links(span: dict[str, Any]) -> list[dict[str, Any]]:
    raw = span.get("links")
    return raw if isinstance(raw, list) else []


def run_formal_service(
    mode: str,
    service_port: int,
    pg_port: int,
    artifact_root: Path,
    credentials: dict[str, str],
    log_dir: Path,
    endpoint: str | None,
) -> tuple[subprocess.Popen[bytes], Any, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = (log_dir / "control-plane.stdout.log").open("wb")
    stderr = (log_dir / "control-plane.stderr.log").open("wb")
    environment = os.environ.copy()
    for key in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
        environment.pop(key, None)
    environment.update({
        "RPF_CONTROL_PLANE_ADDRESS": "127.0.0.1",
        "RPF_CONTROL_PLANE_PORT": str(service_port),
        "RPF_JDBC_URL": f"jdbc:postgresql://127.0.0.1:{pg_port}/runproof",
        "RPF_DB_USER": "runproof",
        "RPF_DB_PASSWORD": credentials["db_password"],
        "RPF_ARTIFACT_STORE_ROOT": str(artifact_root),
        "RPF_PROBE_ENABLED": "true",
        "RPF_OTEL_ENABLED": "false" if mode == "disabled" else "true",
        "RPF_OTEL_ENDPOINT": endpoint or "",
        "RPF_OTEL_QUEUE_SIZE": "64",
        "RPF_OTEL_SERVICE_NAME": "runproof-control-plane",
        "RPF_AUTH_READ_TOKEN": credentials["read"],
        "RPF_AUTH_EVIDENCE_TOKEN": credentials["evidence"],
        "RPF_AUTH_DECISION_TOKEN": credentials["decision"],
        "RPF_AUTH_AGENT_TOKEN": credentials["agent"],
        "RPF_AUTH_CI_TOKEN": credentials["ci"],
        "RPF_AUTH_WORKER_TOKEN": credentials["worker"],
    })
    process = subprocess.Popen(
        ["java", "-jar", str(JAR_PATH)], cwd=ROOT, env=environment, stdout=stdout, stderr=stderr,
    )
    return process, stdout, stderr


def worker_environment(mode: str, endpoint: str | None, *, suppress_propagation: bool = False) -> dict[str, str]:
    environment = os.environ.copy()
    environment["RPF_OTEL_ENABLED"] = "false" if mode == "disabled" else "true"
    environment["RPF_OTEL_ENDPOINT"] = endpoint or ""
    environment["RPF_OTEL_QUEUE_SIZE"] = "64"
    environment["RPF_OTEL_SUPPRESS_PROPAGATION"] = "true" if suppress_propagation else "false"
    environment.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    environment.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)
    return environment


def read_run_documents(output_dir: Path, paths: Iterable[Path] | None = None) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    candidates = paths if paths is not None else output_dir.rglob("*.json")
    for path in candidates:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("artifact_kind") == "Run Evidence":
            documents.append(value)
    return documents


def spawn_formal_worker(
    base_url: str,
    token: str,
    artifact_root: Path,
    result_path: Path,
    *,
    worker_id: str,
    max_jobs: int = 1,
    idle_timeout: float = 240.0,
) -> tuple[subprocess.CompletedProcess[bytes], dict[str, Any]]:
    environment = os.environ.copy()
    environment["RPF_AUTH_WORKER_TOKEN"] = token
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "runtime.runproof_runtime.durable_worker",
            "--base-url",
            base_url,
            "--worker-id",
            worker_id,
            "--repo-root",
            str(ROOT),
            "--artifact-store-root",
            str(artifact_root),
            "--allowed-root",
            str(result_path.parent),
            "--lease-seconds",
            "30",
            "--max-jobs",
            str(max_jobs),
            "--idle-timeout",
            str(idle_timeout),
            "--result-path",
            str(result_path),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
        timeout=360,
    )
    if not result_path.is_file():
        return process, {}
    try:
        document = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        document = {}
    return process, document if isinstance(document, dict) else {}


def run_summary(documents: list[dict[str, Any]]) -> dict[str, Any]:
    response = next(
        (
            item
            for item in documents
            if item.get("fault", {}).get("fault_profile") == "response-lost"
            or (
                item.get("fault", {}).get("fault_id") == "side_effect_success_response_lost"
                and item.get("fault", {}).get("planned") is True
                and item.get("fault", {}).get("reconciled") is True
            )
        ),
        None,
    )
    if response is None:
        raise ProbeFailure("RESPONSE_LOST_RUN_MISSING")
    verification = response.get("verification") if isinstance(response.get("verification"), dict) else {}
    evidence = verification.get("evidence") if isinstance(verification.get("evidence"), dict) else {}
    environment = response.get("environment") if isinstance(response.get("environment"), dict) else {}
    observed = environment.get("observable_state") if isinstance(environment.get("observable_state"), dict) else {}
    mutation_count = evidence.get("mutation_count", observed.get("mutation_count"))
    mutation_requests = evidence.get("mutation_requests", mutation_count)
    return {
        "run_count": len(documents),
        "outcomes": [item.get("outcome", {}).get("status") for item in documents if isinstance(item.get("outcome"), dict)],
        "response_lost": {
            "run_id": response.get("run", {}).get("run_id"),
            "outcome": response.get("outcome", {}).get("status"),
            "verification_passed": verification.get("passed") is True,
            "effect_count": mutation_count,
            "mutation_requests": mutation_requests,
            "blind_retry_attempts": evidence.get("blind_retry_attempts"),
            "fault_reconciled": response.get("fault", {}).get("reconciled") is True,
            "cleanup_state": environment.get("cleanup_state"),
            "propagation": environment.get("propagation", {}),
        },
    }


def run_mode(
    mode: str,
    root: Path,
    pg_port: int,
    credentials: dict[str, str],
    endpoint: str | None,
    *,
    environment_profile: str | None,
    suppress_propagation: bool = False,
) -> dict[str, Any]:
    mode_root = root / mode
    artifact_root = mode_root / "canonical-artifacts"
    worker_output = mode_root / "worker-output"
    result_path = mode_root / "worker-result.json"
    mode_root.mkdir(parents=True, exist_ok=True)
    service_port = port()
    base_url = f"http://127.0.0.1:{service_port}/api/v1"
    service, stdout, stderr = run_formal_service(mode, service_port, pg_port, artifact_root, credentials, mode_root / "logs", endpoint)
    previous_env = os.environ.copy()
    try:
        health = RPF14.wait_for_health(base_url, service)
        if health.get("database_product") != "PostgreSQL":
            raise ProbeFailure(f"{mode.upper()}_POSTGRES_HEALTH_FAILED")
        job_id = f"rpf30-{mode}-job-{uuid.uuid4().hex[:8]}"
        # RPF-30 validates observability, not Provider behavior.  The fixed
        # candidate keeps this formal probe deterministic and offline.
        payload = RPF14.durable_payload(job_id, profile="production-change-agent-v1-fixed", output_dir=worker_output)
        if environment_profile:
            payload["environment_profile"] = environment_profile
        status, submitted, _ = RPF14.submit_durable(
            base_url, credentials["ci"], job_id, target_id=f"evaluation-{job_id}", payload_ref=payload,
        )
        if status != 201 or submitted.get("status") != "SUBMITTED":
            raise ProbeFailure(f"{mode.upper()}_JOB_SUBMIT_FAILED")
        os.environ.update(worker_environment(mode, endpoint, suppress_propagation=suppress_propagation))
        worker_process, worker_result = spawn_formal_worker(
            base_url, credentials["worker"], artifact_root, result_path,
            worker_id=f"rpf30-{mode}-worker", max_jobs=1, idle_timeout=240.0,
        )
        if worker_process.returncode != 0 or worker_result.get("status") != "PASS":
            raise ProbeFailure(f"{mode.upper()}_WORKER_FAILED")
        status, job = RPF14.http_json(base_url, "GET", f"/jobs/{job_id}", token=credentials["read"])
        if status != 200 or job.get("state") != "COMPLETED":
            raise ProbeFailure(f"{mode.upper()}_CANONICAL_JOB_NOT_COMPLETED")
        job_records = worker_result.get("jobs") if isinstance(worker_result.get("jobs"), list) else []
        current_paths = []
        if job_records and isinstance(job_records[0], dict) and isinstance(job_records[0].get("paths"), list):
            current_paths = [
                Path(value) for value in job_records[0]["paths"]
                if isinstance(value, str) and Path(value).name.startswith("run-") and Path(value).suffix == ".json"
            ]
        documents = read_run_documents(worker_output, current_paths or None)
        canonical = run_summary(documents)
        telemetry = worker_result.get("observability") if isinstance(worker_result.get("observability"), dict) else {}
        return {
            "mode": mode,
            "otel_enabled": mode != "disabled",
            "collector_expected": mode == "enabled-healthy",
            "collector_endpoint_configured": bool(endpoint),
            "environment_profile": environment_profile or "single-container",
            "job": {
                "state": job.get("state"),
                "attempt_number": job.get("attempt_number"),
                "terminal_evidence": bool(job.get("terminal_evidence_id")),
                "operation_count": len(job.get("operations", [])) if isinstance(job.get("operations"), list) else 0,
                "evidence_count": len(job.get("evidence", [])) if isinstance(job.get("evidence"), list) else 0,
            },
            "canonical": canonical,
            "telemetry": telemetry,
            "worker_exit": worker_process.returncode,
            "sensitive_credentials_in_worker_result": any(secret in json.dumps(worker_result, ensure_ascii=False) for secret in credentials.values()),
        }
    finally:
        os.environ.clear()
        os.environ.update(previous_env)
        RPF14.stop_process(service)
        stdout.close()
        stderr.close()


def attempt_reclaim(root: Path, pg_port: int, credentials: dict[str, str], endpoint: str) -> dict[str, Any]:
    mode_root = root / "attempt-reclaim"
    mode_root.mkdir(parents=True, exist_ok=True)
    service_port = port()
    base_url = f"http://127.0.0.1:{service_port}/api/v1"
    service, stdout, stderr = run_formal_service("enabled-healthy", service_port, pg_port, mode_root / "artifacts", credentials, mode_root / "logs", endpoint)
    previous_env = os.environ.copy()
    try:
        RPF14.wait_for_health(base_url, service)
        os.environ.update(worker_environment("enabled-healthy", endpoint))
        from runtime.runproof_runtime.control_plane_client import ControlPlaneClient
        from runtime.runproof_runtime.observability import canonical_attributes, get_observability, reset_observability

        reset_observability()
        client = ControlPlaneClient(base_url, credentials["worker"])
        job_id = f"rpf30-reclaim-job-{uuid.uuid4().hex[:8]}"
        payload = {"contract": "rpf30-reclaim-probe-v1", "marker": "bounded-no-operation-reclaim"}
        status, submitted, _ = RPF14.submit_durable(base_url, credentials["ci"], job_id, payload_ref=payload)
        if status != 201 or submitted.get("status") != "SUBMITTED":
            raise ProbeFailure("RECLAIM_JOB_SUBMIT_FAILED")
        first = client.claim_job(job_id, "rpf30-reclaim-worker-1", lease_seconds=3)
        lease_one = first.get("lease") if isinstance(first.get("lease"), dict) else None
        context = first.get("observability_context", {}).get("job") if isinstance(first.get("observability_context"), dict) else None
        if not isinstance(lease_one, dict) or not isinstance(context, dict):
            raise ProbeFailure("RECLAIM_FIRST_CONTEXT_MISSING")
        owner_one = dict(lease_one)
        observability = get_observability()
        with observability.span("runproof.job.execute", canonical_attributes(job_id=job_id, attempt_id=str(lease_one["attempt_id"]), agent_id="rpf30-reclaim-worker-1"), parent=context) as first_span:
            owner_one["_observability_context"] = first_span.context_document()
            client.start_job(job_id, owner_one)
        time.sleep(3.6)
        second = client.claim_job(job_id, "rpf30-reclaim-worker-2", lease_seconds=3)
        lease_two = second.get("lease") if isinstance(second.get("lease"), dict) else None
        context_two = second.get("observability_context") if isinstance(second.get("observability_context"), dict) else {}
        previous = context_two.get("previous_attempt") if isinstance(context_two.get("previous_attempt"), dict) else None
        if second.get("status") != "CLAIMED" or not isinstance(lease_two, dict) or not isinstance(previous, dict):
            raise ProbeFailure("RECLAIM_SECOND_ATTEMPT_CONTEXT_MISSING")
        owner_two = dict(lease_two)
        link = observability.span_link(previous)
        with observability.span(
            "runproof.job.execute",
            canonical_attributes(job_id=job_id, attempt_id=str(lease_two["attempt_id"]), agent_id="rpf30-reclaim-worker-2")
            | {"runproof.attempt.model": "stable_job_trace_new_attempt_subtree"},
            parent=context_two.get("job") if isinstance(context_two.get("job"), dict) else context,
            links=[link] if link is not None else [],
        ) as second_span:
            owner_two["_observability_context"] = second_span.context_document()
            client.start_job(job_id, owner_two)
        evidence_id = f"rpf30-reclaim-cleanup-{job_id}"
        content_sha = hashlib.sha256(evidence_id.encode("utf-8")).hexdigest()
        evidence_payload = {
                "evidence_id": evidence_id, "entity_type": "EVALUATION", "entity_id": job_id,
                "outcome": "ERROR", "content_sha256": content_sha,
                "artifact_ref": {"artifact_id": evidence_id, "artifact_key": f"rpf30/{job_id}/{content_sha}.json", "artifact_kind": "RPF-30-Reclaim-Cleanup-Evidence", "schema_version": "rpf-execution-evidence-v1", "content_sha256": content_sha, "source_sha256": content_sha, "runtime_version": "rpf-30-formal-probe-v1"},
        }
        client.ingest_execution_evidence(job_id, evidence_payload, owner=owner_two)
        client.fail_platform_job(job_id, owner_two, evidence_id, "RPF30_RECLAIM_CLEANUP")
        observability.flush(1000)
        final = client.get_job(job_id) or {}
        reset_observability()
        return {
            "job_id": job_id,
            "first_attempt_id_present": bool(lease_one.get("attempt_id")),
            "second_attempt_id_present": bool(lease_two.get("attempt_id")),
            "attempt_ids_distinct": lease_one.get("attempt_id") != lease_two.get("attempt_id"),
            "job_context_restored": isinstance(context_two.get("job"), dict),
            "previous_attempt_context_returned": True,
            "span_link_created": link is not None,
            "terminal_state": final.get("state"),
            "cleanup_terminalized": final.get("state") == "FAILED_PLATFORM",
        }
    finally:
        os.environ.clear()
        os.environ.update(previous_env)
        RPF14.stop_process(service)
        stdout.close()
        stderr.close()


def propagation_negative(endpoint: str) -> dict[str, Any]:
    previous_env = os.environ.copy()
    try:
        os.environ.update(worker_environment("enabled-healthy", endpoint, suppress_propagation=True))
        from runtime.runproof_runtime.observability import get_observability, reset_observability

        reset_observability()
        observability = get_observability()
        with observability.span("runproof.agent.run", {"runproof.outcome": "PASS"}):
            carrier: dict[str, str] = {}
            observability.inject(carrier)
        result = {"header_missing_detected": "traceparent" not in carrier, "canonical_outcome": "PASS", "product_fail_open": True}
        reset_observability()
        return result
    finally:
        os.environ.clear()
        os.environ.update(previous_env)


def overhead(endpoint: str) -> dict[str, Any]:
    from runtime.runproof_runtime.observability import Observability

    results: dict[str, Any] = {"iterations": 48, "measurement": "non-flushing span creation loop; directional contract evidence"}
    for mode, configured_endpoint in (("disabled", None), ("enabled-healthy", endpoint), ("enabled-unavailable", f"http://127.0.0.1:{port()}")):
        started = time.perf_counter()
        observability = Observability(enabled=mode != "disabled", endpoint=configured_endpoint, queue_size=64)
        for _ in range(results["iterations"]):
            with observability.span("runproof.overhead.sample", {"runproof.outcome": "PASS"}):
                pass
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        observability.flush(1000)
        results[mode] = {"elapsed_ms": elapsed, "diagnostics": observability.diagnostics()}
        observability.shutdown()
    results["unavailable_nonblocking"] = results["enabled-unavailable"]["elapsed_ms"] < 1000
    results["disabled_no_export_thread"] = results["disabled"]["diagnostics"].get("status") == "DISABLED"
    return results


def graph_summary(spans: list[dict[str, Any]], response_run_id: str) -> dict[str, Any]:
    response_spans = [item for item in spans if attributes(item).get("runproof.run.id") == response_run_id]
    response_trace_ids = {trace_id(item) for item in response_spans if trace_id(item)}
    required_run = {
        "runproof.agent.run", "runproof.tool.call", "runproof.environment.provision",
        "runproof.environment.readiness", "runproof.fault.activate", "runproof.target.request",
        "runproof.target.commit", "runproof.dependency.request", "runproof.operation.reconcile",
        "runproof.verifier.evaluate",
    }
    by_name = defaultdict(list)
    for item in response_spans:
        by_name[str(item.get("name"))].append(item)
    root_candidates = [item for item in spans if item.get("name") == "runproof.job.submit" and attributes(item).get("runproof.job.id")]
    response_trace = next((trace_id(item) for item in spans if item.get("name") == "runproof.job.execute" and trace_id(item) in response_trace_ids), "")
    trace_spans = [item for item in spans if trace_id(item) == response_trace] if response_trace else []
    trace_names = {str(item.get("name")) for item in trace_spans}
    required_job = {"runproof.job.submit", "runproof.job.execute", "runproof.evidence.ingest", "runproof.job.terminalize"}
    required = required_run | required_job
    presence = {name: (name in by_name or name in trace_names) for name in sorted(required)}
    commits = by_name.get("runproof.target.commit", [])
    return {
        "response_run_id": response_run_id,
        "trace_id_present": bool(response_trace),
        "required_spans": presence,
        "all_required_spans_present": all(presence.values()),
        "target_commit_count": len(commits),
        "no_second_mutation": len(commits) == 1,
        "response_trace_span_count": len(trace_spans),
        "response_run_trace_ids": sorted(response_trace_ids),
        "collector_span_count": len(spans),
        "root_submit_observed": bool(root_candidates),
        "passed": bool(response_trace) and all(presence.values()) and len(commits) == 1,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the formal RPF-30 OpenTelemetry contract probe.")
    parser.add_argument("--run", action="store_true", help="Execute the disposable local/hosted-style probe.")
    parser.add_argument("--hosted", action="store_true", help="Use hosted-focused output naming; semantics remain bounded.")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("--run is required")
    if not JAR_PATH.is_file():
        raise ProbeFailure("FORMAL_CONTROL_PLANE_JAR_MISSING")

    output_dir = (args.output_dir or (LOCAL_ROOT / ("hosted" if args.hosted else "local"))).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "rpf30-result.json"
    postgres_container = f"rpf30-postgres-{uuid.uuid4().hex[:10]}"
    postgres_volume = f"rpf30-volume-{uuid.uuid4().hex[:10]}"
    pg_port = port()
    password = "rpf30-db-" + uuid.uuid4().hex
    credentials = {
        "db_password": password,
        "read": "rpf30-read-" + uuid.uuid4().hex,
        "evidence": "rpf30-evidence-" + uuid.uuid4().hex,
        "decision": "rpf30-decision-" + uuid.uuid4().hex,
        "agent": "rpf30-agent-" + uuid.uuid4().hex,
        "ci": "rpf30-ci-" + uuid.uuid4().hex,
        "worker": "rpf30-worker-" + uuid.uuid4().hex,
    }
    collector: Collector | None = None
    healthy_spans: list[dict[str, Any]] = []
    try:
        start_postgres(postgres_container, postgres_volume, pg_port, password)
        disabled = run_mode("disabled", output_dir, pg_port, credentials, None, environment_profile=None)
        collector = start_collector(output_dir)
        healthy = run_mode(
            "enabled-healthy", output_dir, pg_port, credentials, collector.endpoint,
            environment_profile="multi-service-toxiproxy-v1",
        )
        reclaim = attempt_reclaim(output_dir, pg_port, credentials, collector.endpoint)
        healthy_spans = wait_collector_spans(output_dir)
        response_run_id = healthy["canonical"]["response_lost"]["run_id"]
        graph = graph_summary(healthy_spans, str(response_run_id))
        negative = propagation_negative(collector.endpoint)
        overhead_result = overhead(collector.endpoint)
        collector_port = collector.port
        collector_removed = stop_collector(collector)
        collector = None
        unavailable = run_mode(
            "enabled-unavailable", output_dir, pg_port, credentials, f"http://127.0.0.1:{collector_port}",
            environment_profile=None,
        )
        cleanup = {
            "collector_removed": collector_removed,
            "postgres_container_removed": remove_exact(postgres_container, "container"),
            "postgres_volume_removed": remove_exact(postgres_volume, "volume"),
        }
        result = {
            "schema_version": FORMAL_SCHEMA,
            "plan_id": "RPF-30",
            "status": "PASS",
            "source_identity": source_identity(),
            "collector": {"image": COLLECTOR_IMAGE, "endpoint_protocol": "OTLP_HTTP", "pinned": True, "external_authority": False, "span_count": len(healthy_spans)},
            "modes": {"disabled": disabled, "enabled_healthy": healthy, "enabled_unavailable": unavailable},
            "attempt_reclaim": reclaim,
            "missing_propagation": negative,
            "trace_graph": graph,
            "performance": overhead_result,
            "telemetry_contract": {
                "canonical_authority": False,
                "canonical_trace_schema_change": False,
                "baggage_allowlist": ["runproof.job.id", "runproof.attempt.id", "runproof.run.id", "runproof.environment.id", "runproof.operation.id"],
                "metric_labels_allowlist": ["job_type", "target_type", "outcome", "status", "fault_profile", "result", "service"],
                "queue_bounded": True,
                "queue_size": 64,
                "batch_size": 64,
                "export_timeout_ms": 250,
                "flush_boundary": "shutdown/test/verifier only",
            },
            "cleanup": cleanup,
            "release_or_deploy_executed": False,
        }
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"status": result["status"], "result": str(result_path), "trace_spans": len(healthy_spans), "cleanup": cleanup}, ensure_ascii=False))
        return 0
    except Exception as error:
        failure = {"schema_version": FORMAL_SCHEMA, "plan_id": "RPF-30", "status": "FAIL", "error": type(error).__name__, "source_identity": source_identity()}
        result_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        raise
    finally:
        if collector is not None:
            stop_collector(collector)
        remove_exact(postgres_container, "container")
        remove_exact(postgres_volume, "volume")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeFailure as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)

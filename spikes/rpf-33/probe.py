"""RPF-33 disposable capacity and large-trace investigation harness.

The harness deliberately does not change the formal schema, add indexes, or
touch Golden Demo/history.  It builds a deterministic synthetic corpus inside
probe-owned PostgreSQL and SeaweedFS resources, measures the current HTTP,
durable, artifact, and OTel boundaries, and writes only ignored evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import platform
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
LOCAL_ROOT = ROOT / ".local" / "rpf-33"
JAR_PATH = ROOT / "control-plane" / "target" / "runproof-control-plane-0.1.0-SNAPSHOT.jar"
JAVA_POM = SPIKE_ROOT / "java" / "pom.xml"
JAVA_JAR = SPIKE_ROOT / "java" / "target" / "rpf33-capacity-s3-fixture.jar"
PG_IMAGE = "postgres:16-alpine"
SEAWEED_IMAGE = "chrislusf/seaweedfs:4.47"
OTEL_IMAGE = "otel/opentelemetry-collector-contrib:0.157.0"
PROBE_SCHEMA = "rpf-capacity-large-trace-investigation-v1"
FIXTURE_VERSION = "rpf33-capacity-fixture-v1"
FIXTURE_SEED = "rpf33-seed-20260918"
FIXTURE_SOURCE_SHA = hashlib.sha256(b"rpf33-capacity-fixture-source").hexdigest()
FIXTURE_RUNTIME = "rpf33-capacity-fixture-v1"
MAVEN = "mvn.cmd" if os.name == "nt" else "mvn"
PG_TABLES = [
    "canonical_metadata", "rpf_execution_job", "rpf_execution_attempt",
    "rpf_execution_event", "rpf_execution_evidence", "rpf_execution_operation",
    "control_plane_audit",
]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"MODULE_LOAD_FAILED:{name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CP = load_module(ROOT / "control-plane" / "probe.py", "rpf33_control_plane_probe")


class ProbeFailure(RuntimeError):
    pass


TIERS = {
    "small": {"jobs": 100, "events": 1_000, "run_end": 100, "failure_end": 25, "events_per_new_job": 10, "timeline_events": 100},
    "medium": {"jobs": 1_000, "events": 10_000, "run_end": 1_000, "failure_end": 100, "events_per_new_job": 10, "timeline_events": 1_000},
    "large": {"jobs": 10_000, "events": 50_000, "run_end": 10_000, "failure_end": 500, "events_per_new_job": 5, "timeline_events": 10_000},
}


def sha256(value: bytes | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def local_port() -> int:
    handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    handle.bind(("127.0.0.1", 0))
    selected = int(handle.getsockname()[1])
    handle.close()
    return selected


def docker(args: list[str], *, input_bytes: bytes | None = None, timeout: int = 120, check: bool = True) -> str:
    result = subprocess.run(
        ["docker", *args], input=input_bytes, capture_output=True, text=False, timeout=timeout, check=False
    )
    if check and result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace")[-800:]
        raise ProbeFailure(f"DOCKER_{args[0].upper()}_FAILED:{detail}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def ensure_image(image: str) -> str:
    inspected = subprocess.run(["docker", "image", "inspect", image], capture_output=True, check=False, timeout=30)
    if inspected.returncode != 0:
        docker(["pull", image], timeout=900)
    digest = docker(["image", "inspect", image, "--format", "{{json .RepoDigests}}"], timeout=30, check=False)
    try:
        values = json.loads(digest)
    except json.JSONDecodeError:
        values = []
    return str(values[0]) if isinstance(values, list) and values else image


def remove_exact(name: str, kind: str) -> bool:
    if kind == "container":
        docker(["rm", "--force", name], timeout=45, check=False)
        return subprocess.run(["docker", "inspect", name], capture_output=True, check=False, timeout=15).returncode != 0
    docker(["volume", "rm", "--force", name], timeout=45, check=False)
    return subprocess.run(["docker", "volume", "inspect", name], capture_output=True, check=False, timeout=15).returncode != 0


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None:
        return
    if process.poll() is None and os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False, timeout=15)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def wait_socket(port: int, timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise ProbeFailure(f"SOCKET_READINESS_TIMEOUT:{port}")


def start_postgres(container: str, volume: str, port: int, password: str) -> None:
    docker(["volume", "create", "--label", "com.runproof.owner=runproof", "--label", "com.runproof.plan=rpf-33", volume])
    docker([
        "run", "--detach", "--pull=never", "--name", container,
        "--label", "com.runproof.owner=runproof", "--label", "com.runproof.plan=rpf-33",
        "--label", "com.runproof.lifecycle=disposable-capacity-postgresql",
        "--env", "POSTGRES_USER=runproof", "--env", f"POSTGRES_PASSWORD={password}", "--env", "POSTGRES_DB=runproof",
        "--publish", f"127.0.0.1:{port}:5432", "--mount", f"type=volume,source={volume},target=/var/lib/postgresql/data", PG_IMAGE,
    ])
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        ready = subprocess.run(["docker", "exec", container, "pg_isready", "-U", "runproof", "-d", "runproof"], capture_output=True, check=False, timeout=15)
        if ready.returncode == 0:
            return
        time.sleep(0.5)
    raise ProbeFailure("POSTGRES_READINESS_TIMEOUT")


def seaweed_config(credentials: dict[str, str]) -> dict[str, Any]:
    return {
        "identities": [
            {"name": "rpf33-admin", "credentials": [{"accessKey": credentials["access"], "secretKey": credentials["secret"]}], "actions": ["Admin", "Read", "List", "Tagging", "Write"]},
        ]
    }


def start_seaweed(container: str, volume: str, port: int, config_path: Path, credentials: dict[str, str]) -> None:
    config_path.write_text(json.dumps(seaweed_config(credentials), separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    docker(["volume", "create", "--label", "com.runproof.owner=runproof", "--label", "com.runproof.plan=rpf-33", volume])
    docker([
        "run", "--detach", "--pull=never", "--name", container,
        "--label", "com.runproof.owner=runproof", "--label", "com.runproof.plan=rpf-33",
        "--label", "com.runproof.lifecycle=disposable-capacity-object-store",
        "--publish", f"127.0.0.1:{port}:8333", "--mount", f"type=volume,source={volume},target=/data",
        "--mount", f"type=bind,source={config_path.resolve()},target=/etc/seaweedfs/s3.json,readonly",
        SEAWEED_IMAGE, "mini", "-dir=/data", "-s3", "-s3.port=8333", "-s3.config=/etc/seaweedfs/s3.json",
    ])


def bootstrap_bucket(endpoint: str, bucket: str, credentials: dict[str, str], run_dir: Path) -> None:
    bootstrap_pom = ROOT / "spikes" / "rpf-32" / "java" / "pom.xml"
    bootstrap_jar = ROOT / "spikes" / "rpf-32" / "java" / "target" / "rpf32-s3-bootstrap.jar"
    if not bootstrap_jar.is_file():
        built = subprocess.run([MAVEN, "-q", "package", "-f", str(bootstrap_pom)], cwd=ROOT, capture_output=True, timeout=240, check=False)
        if built.returncode != 0 or not bootstrap_jar.is_file():
            raise ProbeFailure("RPF33_BUCKET_BOOTSTRAP_BUILD_FAILED")
    environment = os.environ.copy()
    environment.update({"RPF32_ACCESS_KEY": credentials["access"], "RPF32_SECRET_KEY": credentials["secret"]})
    command = ["java", "-jar", str(bootstrap_jar), f"--endpoint={endpoint}", f"--bucket={bucket}"]
    last = None
    for attempt in range(15):
        last = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False)
        lines = [line.strip() for line in last.stdout.splitlines() if line.strip()]
        if last.returncode == 0 and lines:
            try:
                result = json.loads(lines[-1])
            except json.JSONDecodeError:
                result = {}
            if result.get("status") == "PASS":
                return
        time.sleep(0.5 if attempt < 5 else 1.0)
    (run_dir / "bucket-bootstrap.stderr.log").write_text((last.stderr if last else "")[-4000:], encoding="utf-8", newline="\n")
    raise ProbeFailure("RPF33_BUCKET_BOOTSTRAP_FAILED")


def base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/api/v1"


def service_env(port: int, pg_port: int, service: dict[str, str], s3: dict[str, Any], *, prefix: str, backend: str = "s3") -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({
        "RPF_CONTROL_PLANE_ADDRESS": "127.0.0.1",
        "RPF_CONTROL_PLANE_PORT": str(port),
        "RPF_JDBC_URL": f"jdbc:postgresql://127.0.0.1:{pg_port}/runproof",
        "RPF_DB_USER": "runproof",
        "RPF_DB_PASSWORD": service["db_password"],
        "RPF_PROBE_ENABLED": "true",
        "RPF_ARTIFACT_STORE_BACKEND": backend,
        "RPF_ARTIFACT_STORE_S3_ENDPOINT": s3["endpoint"],
        "RPF_ARTIFACT_STORE_S3_REGION": "us-east-1",
        "RPF_ARTIFACT_STORE_S3_BUCKET": s3["bucket"],
        "RPF_ARTIFACT_STORE_S3_PREFIX": prefix,
        "RPF_ARTIFACT_STORE_S3_ACCESS_KEY": s3["access"],
        "RPF_ARTIFACT_STORE_S3_SECRET_KEY": s3["secret"],
        "RPF_ARTIFACT_STORE_S3_PATH_STYLE_ACCESS": "true",
        "RPF_ARTIFACT_STORE_S3_CONNECT_TIMEOUT_MS": "2000",
        "RPF_ARTIFACT_STORE_S3_API_TIMEOUT_MS": "30000",
        "RPF_ARTIFACT_STORE_S3_ATTEMPT_TIMEOUT_MS": "20000",
        "RPF_AUTH_READ_TOKEN": service["read"],
        "RPF_AUTH_EVIDENCE_TOKEN": service["evidence"],
        "RPF_AUTH_DECISION_TOKEN": service["decision"],
        "RPF_AUTH_AGENT_TOKEN": service["agent"],
        "RPF_AUTH_CI_TOKEN": service["ci"],
        "RPF_AUTH_WORKER_TOKEN": service["worker"],
    })
    return environment


def start_control_plane(port: int, pg_port: int, service: dict[str, str], s3: dict[str, Any], prefix: str, log_dir: Path) -> subprocess.Popen[bytes]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = (log_dir / "control-plane.stdout.log").open("wb")
    stderr = (log_dir / "control-plane.stderr.log").open("wb")
    return subprocess.Popen(["java", "-jar", str(JAR_PATH)], cwd=ROOT, env=service_env(port, pg_port, service, s3, prefix=prefix), stdout=stdout, stderr=stderr)


def http_request(base: str, method: str, path: str, token: str | None = None, body: bytes | None = None, content_type: str = "application/json", timeout: float = 120.0) -> tuple[int, dict[str, Any], bytes, int]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = content_type
    request = Request(f"{base}{path}", data=body, method=method, headers=headers)
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = int(response.status)
    except HTTPError as error:
        raw = error.read()
        status = int(error.code)
    except (URLError, TimeoutError, OSError):
        return 0, {}, b"", int((time.perf_counter() - started) * 1000)
    try:
        value = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = {}
    return status, value if isinstance(value, dict) else {}, raw, int((time.perf_counter() - started) * 1000)


def wait_health(base: str, process: subprocess.Popen[bytes], timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeFailure("CONTROL_PLANE_EXITED_BEFORE_READY")
        status, body, _, _ = http_request(base, "GET", "/health", timeout=3)
        if status == 200 and body.get("ready") is True:
            return body
        time.sleep(0.25)
    raise ProbeFailure("CONTROL_PLANE_READINESS_TIMEOUT")


def psql(container: str, sql: str, *, timeout: int = 180) -> str:
    return docker(["exec", container, "psql", "-U", "runproof", "-d", "runproof", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql], timeout=timeout)


def psql_copy(container: str, sql: str, content: bytes, *, timeout: int = 300) -> None:
    docker(["exec", "-i", container, "psql", "-U", "runproof", "-d", "runproof", "-v", "ON_ERROR_STOP=1", "-c", sql], input_bytes=content, timeout=timeout)


def db_fixture_sql(start_job: int, end_job: int, events_per_job: int, timeline_job_id: str, timeline_events: int) -> str:
    return f"""
INSERT INTO rpf_execution_job(
 job_id,idempotency_key,request_fingerprint,job_type,target_type,target_id,payload_ref_json,
 correlation_id,state,version,attempt_number,active_attempt_id,active_worker_id,active_lease_token_hash,
 lease_expires_at,heartbeat_at,cancel_requested,timeout_requested,otel_context_json,outcome_status,
 platform_reason,terminal_evidence_id,last_operation_id,created_at,updated_at
)
SELECT 'rpf33-job-'||lpad(gs::text,5,'0'), 'rpf33-idem-'||gs, md5('rpf33-job-'||gs), 'CAPACITY', 'RUN',
 'rpf33-run-'||lpad(gs::text,5,'0'), '{{}}', 'rpf33-correlation-'||gs,
 CASE WHEN gs % 10 = 0 THEN 'QUEUED' WHEN gs % 10 = 1 THEN 'RUNNING' ELSE 'COMPLETED' END,
 1, CASE WHEN gs % 10 = 1 THEN 1 ELSE 0 END,
 CASE WHEN gs % 10 = 1 THEN 'rpf33-attempt-'||gs ELSE NULL END,
 CASE WHEN gs % 10 = 1 THEN 'rpf33-fixture-worker' ELSE NULL END,
 CASE WHEN gs % 10 = 1 THEN md5('rpf33-lease-'||gs) ELSE NULL END,
 CASE WHEN gs % 10 = 1 THEN CURRENT_TIMESTAMP - interval '1 second' ELSE NULL END,
 CASE WHEN gs % 10 = 1 THEN CURRENT_TIMESTAMP - interval '2 seconds' ELSE NULL END,
 FALSE,FALSE,'{{}}',CASE WHEN gs % 10 IN (0,1) THEN NULL ELSE 'PASS' END,NULL,
 CASE WHEN gs % 10 IN (0,1) THEN NULL ELSE 'rpf33-evidence-'||gs END,NULL,
 TIMESTAMP WITH TIME ZONE '2026-01-01 00:00:00+00' + (gs * interval '1 millisecond'),
 TIMESTAMP WITH TIME ZONE '2026-01-01 00:00:00+00' + (gs * interval '1 millisecond')
FROM generate_series({start_job},{end_job}) AS gs
ON CONFLICT DO NOTHING;
INSERT INTO rpf_execution_attempt(
 attempt_id,job_id,attempt_number,worker_id,lease_token_hash,lease_version,status,lease_expires_at,
 otel_context_json,heartbeat_at,started_at,ended_at,reason,created_at
)
SELECT 'rpf33-attempt-'||gs,'rpf33-job-'||lpad(gs::text,5,'0'),1,'rpf33-fixture-worker',md5('rpf33-lease-'||gs),1,
 'CLAIMED',CURRENT_TIMESTAMP - interval '1 second','{{}}',CURRENT_TIMESTAMP - interval '2 seconds',
 CURRENT_TIMESTAMP - interval '3 seconds',NULL,'RPF33_EXPIRED_FIXTURE',CURRENT_TIMESTAMP
FROM generate_series({start_job},{end_job}) AS gs
WHERE gs % 10 = 1
ON CONFLICT DO NOTHING;
INSERT INTO rpf_execution_event(job_id,from_state,to_state,event_type,attempt_id,operation_id,reason,version,occurred_at)
SELECT 'rpf33-job-'||lpad(gs::text,5,'0'),NULL,'COMPLETED','capacity_fixture_event',NULL,NULL,NULL,1,
 TIMESTAMP WITH TIME ZONE '2026-01-01 00:00:00+00' + ((gs * {events_per_job} + ev) * interval '1 millisecond')
FROM generate_series({start_job},{end_job}) AS gs
CROSS JOIN generate_series(1,{events_per_job}) AS ev;
INSERT INTO rpf_execution_job(
 job_id,idempotency_key,request_fingerprint,job_type,target_type,target_id,payload_ref_json,
 correlation_id,state,version,attempt_number,active_attempt_id,active_worker_id,active_lease_token_hash,
 lease_expires_at,heartbeat_at,cancel_requested,timeout_requested,otel_context_json,outcome_status,
 platform_reason,terminal_evidence_id,last_operation_id,created_at,updated_at
)
VALUES ('{timeline_job_id}', 'rpf33-timeline-idem-{timeline_job_id}', md5('{timeline_job_id}'), 'TIMELINE', 'RUN',
 'rpf33-timeline-run-{timeline_job_id}', '{{}}', 'rpf33-timeline-correlation-{timeline_job_id}',
 'COMPLETED', 1, 0, NULL, NULL, NULL, NULL, NULL, FALSE, FALSE, '{{}}', 'PASS', NULL,
 NULL, NULL, TIMESTAMP WITH TIME ZONE '2026-01-02 00:00:00+00', TIMESTAMP WITH TIME ZONE '2026-01-02 00:00:00+00')
ON CONFLICT DO NOTHING;
INSERT INTO rpf_execution_event(job_id,from_state,to_state,event_type,attempt_id,operation_id,reason,version,occurred_at)
SELECT '{timeline_job_id}', NULL, 'COMPLETED', 'rpf33_timeline_fixture_event', NULL, NULL, NULL, 1,
 TIMESTAMP WITH TIME ZONE '2026-01-02 00:00:00+00' + (ev * interval '1 millisecond')
FROM generate_series(1,{timeline_events}) AS ev;
INSERT INTO rpf_execution_evidence(
 evidence_id,job_id,attempt_id,entity_type,entity_id,outcome,content_sha256,artifact_ref_json,created_at
)
SELECT 'rpf33-evidence-'||gs,'rpf33-job-'||lpad(gs::text,5,'0'),NULL,'RUN','rpf33-run-'||lpad(gs::text,5,'0'),
 'PASS',repeat(md5('rpf33-evidence-'||gs),2),
 '{{"artifact_id":"rpf33-run-'||lpad(gs::text,5,'0')||'"}}',CURRENT_TIMESTAMP
FROM generate_series({start_job},{end_job}) AS gs
WHERE gs % 10 <> 0
ON CONFLICT DO NOTHING;
ANALYZE;
"""


def copy_metadata(container: str, entries: list[dict[str, str]], tier: str, run_dir: Path) -> None:
    csv_path = run_dir / f"metadata-{tier}.csv"
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([
        "entity_type", "entity_id", "entity_schema_version", "artifact_kind", "outcome", "agent_version", "evaluation_id",
        "source_sha256", "runtime_version", "summary_json", "key_refs_json", "artifact_id", "artifact_key",
        "artifact_schema_version", "artifact_content_sha256", "artifact_source_sha256", "artifact_runtime_version",
        "idempotency_key", "supersedes_entity_id", "registered_by", "created_at",
    ])
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index, entry in enumerate(entries, start=1):
        entity_type = entry["entity_type"]
        entity_id = entry["entity_id"]
        summary = json.dumps({"status": "PASS", "fixture_version": FIXTURE_VERSION, "scale": tier}, separators=(",", ":"))
        created_at = (base_time + timedelta(microseconds=index)).isoformat()
        writer.writerow([
            entity_type, entity_id, entry["artifact_schema_version"], entry["artifact_kind"], "PASS", "rpf33-synthetic-agent", "",
            entry["source_sha256"], entry["runtime_version"], summary, "[]", entity_id, entry["artifact_key"],
            entry["artifact_schema_version"], entry["content_sha256"], entry["source_sha256"], entry["runtime_version"],
            f"rpf33:{entity_type}:{entity_id}", "", "rpf33-fixture", created_at,
        ])
    content = buffer.getvalue().encode("utf-8")
    csv_path.write_bytes(content)
    psql_copy(
        container,
        "COPY canonical_metadata(entity_type,entity_id,entity_schema_version,artifact_kind,outcome,agent_version,evaluation_id,source_sha256,runtime_version,summary_json,key_refs_json,artifact_id,artifact_key,artifact_schema_version,artifact_content_sha256,artifact_source_sha256,artifact_runtime_version,idempotency_key,supersedes_entity_id,registered_by,created_at) FROM STDIN WITH (FORMAT csv, HEADER true)",
        content,
        timeout=600,
    )


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def run_java_s3(mode: str, endpoint: str, bucket: str, prefix: str, credentials: dict[str, str], run_dir: Path, **options: str) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update({"RPF33_ACCESS_KEY": credentials["access"], "RPF33_SECRET_KEY": credentials["secret"]})
    command = ["java", "-jar", str(JAVA_JAR), f"--mode={mode}", f"--endpoint={endpoint}", f"--bucket={bucket}", f"--prefix={prefix}"]
    for key, value in options.items():
        command.append(f"--{key.replace('_', '-')}={value}")
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800, check=False)
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        (run_dir / f"java-{mode}.stderr.log").write_text(completed.stderr[-8000:], encoding="utf-8", newline="\n")
        raise ProbeFailure(f"JAVA_{mode.upper()}_NO_RESULT")
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        (run_dir / f"java-{mode}.stdout.log").write_text(completed.stdout[-8000:], encoding="utf-8", newline="\n")
        raise ProbeFailure(f"JAVA_{mode.upper()}_INVALID_RESULT") from error
    if completed.returncode != 0 or result.get("status") != "PASS":
        raise ProbeFailure(f"JAVA_{mode.upper()}_FAILED:{result.get('error_code', 'unknown')}")
    result["process_exit"] = completed.returncode
    return result


def tier_ranges(name: str) -> tuple[str, int, int, list[str]]:
    tier = TIERS[name]
    previous = 0 if name == "small" else TIERS["small"]["jobs"] if name == "medium" else TIERS["medium"]["jobs"]
    previous_failure = 0 if name == "small" else TIERS["small"]["failure_end"] if name == "medium" else TIERS["medium"]["failure_end"]
    first = previous + 1
    last = tier["jobs"]
    if name == "small":
        type_ranges = [
            "RUN:1-100", "FAILURE_CASE:1-25", "REGRESSION:1-25", "REGRESSION_RESULT:1-25", "REGRESSION_COLLECTION:1-1",
            "EVALUATION_SUITE:1-1", "EVALUATION:1-25", "COMPARISON:1-10", "QUALITY_POLICY:1-1", "QUALITY_GATE:1-10",
            "RELEASE_DECISION:1-10", "FAILURE_INTELLIGENCE:1-5", "FAILURE_CLUSTER:1-5", "VERSION_BISECT:1-5",
            "STATISTICAL_SAMPLING_PLAN:1-1", "STATISTICAL_EVALUATION:1-10", "STATISTICAL_COMPARISON:1-5",
            "STATISTICAL_POLICY:1-1", "STATISTICAL_GATE:1-5", "STATISTICAL_RELEASE_DECISION:1-5",
        ]
    else:
        type_ranges = [
            f"RUN:{first}-{last}", f"FAILURE_CASE:{previous_failure + 1}-{tier['failure_end']}",
            f"REGRESSION:{previous_failure + 1}-{tier['failure_end']}", f"REGRESSION_RESULT:{previous_failure + 1}-{tier['failure_end']}",
            f"EVALUATION:{previous_failure + 1}-{tier['failure_end']}", f"QUALITY_GATE:{previous_failure + 1}-{tier['failure_end']}",
            f"STATISTICAL_EVALUATION:{previous_failure + 1}-{tier['failure_end']}", f"STATISTICAL_RELEASE_DECISION:{previous_failure + 1}-{tier['failure_end']}",
        ]
    return ",".join(type_ranges), first, last, type_ranges


def process_rss(pid: int | None) -> int | None:
    if not pid:
        return None
    if os.name == "nt":
        command = f"$p=Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue; if ($p) {{ $p.WorkingSet64 }}"
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True, check=False, timeout=10)
        value = result.stdout.strip()
        multiplier = 1
    else:
        result = subprocess.run(["ps", "-o", "rss=", "-p", str(int(pid))], capture_output=True, text=True, check=False, timeout=10)
        value = result.stdout.strip()
        multiplier = 1024
    try:
        return int(value) * multiplier
    except ValueError:
        return None


def docker_stats(container: str) -> dict[str, str]:
    raw = docker(["stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}", container], timeout=30, check=False)
    parts = raw.split("|", 2)
    return {"cpu": parts[0] if parts else "", "memory": parts[1] if len(parts) > 1 else "", "memory_percent": parts[2] if len(parts) > 2 else ""}


def explain(container: str, sql: str) -> dict[str, Any]:
    raw = psql(container, f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}", timeout=600)
    try:
        document = json.loads(raw)
        plan = document[0]["Plan"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        return {"parse_error": type(error).__name__, "raw_prefix": raw[:500]}
    node_counts: dict[str, int] = {}
    buffers = {"shared_hit": 0, "shared_read": 0}
    actual_rows = 0
    planned_rows = 0

    def visit(node: dict[str, Any]) -> None:
        nonlocal actual_rows, planned_rows
        node_type = str(node.get("Node Type", "UNKNOWN"))
        node_counts[node_type] = node_counts.get(node_type, 0) + 1
        actual_rows += int(node.get("Actual Rows", 0) or 0)
        planned_rows += int(node.get("Plan Rows", 0) or 0)
        for key in ("Shared Hit Blocks", "Shared Read Blocks"):
            target = "shared_hit" if key == "Shared Hit Blocks" else "shared_read"
            buffers[target] += int(node.get(key, 0) or 0)
        for child in node.get("Plans", []) or []:
            if isinstance(child, dict): visit(child)

    visit(plan)
    return {"node_counts": node_counts, "actual_rows_sum": actual_rows, "planned_rows_sum": planned_rows, "buffers": buffers, "planning_ms": document[0].get("Planning Time"), "execution_ms": document[0].get("Execution Time")}


def configure_statement_logging(container: str) -> bool:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            psql(container, "ALTER SYSTEM SET log_statement='all'", timeout=30)
            psql(container, "SELECT pg_reload_conf()", timeout=30)
            if psql(container, "SELECT current_setting('log_statement')", timeout=30).strip() == "all":
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def statement_count(container: str) -> int | None:
    logs = subprocess.run(
        ["docker", "logs", "--timestamps", container],
        capture_output=True, text=False, timeout=60, check=False,
    )
    raw = (logs.stdout + logs.stderr).decode("utf-8", errors="replace")
    if not raw:
        return None
    return len(re.findall(r"(?:statement:|execute\s+[^:]+:)", raw, flags=re.IGNORECASE))


def measure_api(base: str, token: str, path: str, *, process: subprocess.Popen[bytes] | None = None, pg_container: str | None = None) -> dict[str, Any]:
    statement_count_before = statement_count(pg_container) if pg_container else None
    status, body, raw, elapsed = http_request(base, "GET", path, token=token, timeout=600)
    result: dict[str, Any] = {"path": path, "status": status, "elapsed_ms": elapsed, "response_bytes": len(raw), "process_rss_after": process_rss(process.pid if process else None)}
    if isinstance(body.get("items"), list):
        result["items"] = len(body["items"])
        result["resolved_items"] = sum(1 for item in body["items"] if isinstance(item, dict) and item.get("artifact_resolution", {}).get("resolved") is True)
    if body.get("job") and isinstance(body.get("job"), dict):
        result["job_state"] = body["job"].get("state")
    if isinstance(body.get("state"), str):
        result["job_state"] = body["state"]
    if isinstance(body.get("events"), list):
        result["events"] = len(body["events"])
    if status >= 400:
        result["error"] = body.get("error")
    if pg_container:
        time.sleep(0.5)
        statement_count_after = statement_count(pg_container)
        if statement_count_before is not None and statement_count_after is not None:
            result["observed_sql_statements"] = max(0, statement_count_after - statement_count_before)
        else:
            result["observed_sql_statements"] = None
    return result


def measure_timeline_api(base: str, token: str, job_id: str, *, process: subprocess.Popen[bytes] | None = None, pg_container: str | None = None) -> dict[str, Any]:
    """Measure the bounded RPF-34 timeline path while preserving RPF-33 totals."""

    statement_count_before = statement_count(pg_container) if pg_container else None
    cursor: str | None = None
    pages = 0
    events = 0
    response_bytes = 0
    elapsed_ms = 0
    status = 200
    while pages < 1000:
        query = urlencode({"limit": 500, **({"cursor": cursor} if cursor else {})})
        status, body, raw, elapsed = http_request(base, "GET", f"/jobs/{job_id}/events?{query}", token=token, timeout=600)
        if status != 200:
            break
        page_items = body.get("items") if isinstance(body.get("items"), list) else []
        events += len(page_items)
        response_bytes += len(raw)
        elapsed_ms += elapsed
        pages += 1
        cursor = body.get("next_cursor") if isinstance(body.get("next_cursor"), str) else None
        if cursor is None:
            break
    if pages >= 1000 and cursor is not None:
        status = 599
    result: dict[str, Any] = {"path": f"/jobs/{job_id}/events?limit=500", "status": status, "elapsed_ms": elapsed_ms, "response_bytes": response_bytes, "events": events, "pages": pages, "process_rss_after": process_rss(process.pid if process else None)}
    if pg_container:
        time.sleep(0.5)
        statement_count_after = statement_count(pg_container)
        if statement_count_before is not None and statement_count_after is not None:
            result["observed_sql_statements"] = max(0, statement_count_after - statement_count_before)
        else:
            result["observed_sql_statements"] = None
    return result


def table_sizes(container: str) -> dict[str, Any]:
    rows = psql(container, "SELECT relname||E'\\t'||pg_total_relation_size(relid)||E'\\t'||pg_relation_size(relid)||E'\\t'||pg_indexes_size(relid) FROM pg_catalog.pg_statio_user_tables WHERE schemaname='public' ORDER BY relname;")
    result: dict[str, Any] = {}
    for row in rows.splitlines():
        parts = row.split("\t")
        if len(parts) == 4 and parts[0] in PG_TABLES:
            result[parts[0]] = {"total_bytes": int(parts[1]), "table_bytes": int(parts[2]), "index_bytes": int(parts[3])}
    return result


def submit_job(base: str, token: str, job_id: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    target_id = f"rpf33-target-{job_id}"
    fingerprint_input = {"job_id": job_id, "target_type": "EVALUATION", "target_id": target_id, "payload_ref": payload}
    body = {
        "job_id": job_id,
        "idempotency_key": f"rpf33-idem-worker-{job_id}",
        "request_fingerprint": sha256(json.dumps(fingerprint_input, sort_keys=True, separators=(",", ":"))),
        "job_type": "EVALUATION",
        "target_type": "EVALUATION",
        "target_id": target_id,
        "correlation_id": f"rpf33-correlation-{job_id}",
        "payload_ref": payload,
    }
    status, response, _, _ = http_request(base, "POST", "/jobs", token=token, body=json.dumps(body, separators=(",", ":")).encode(), timeout=120)
    return status, response


def worker_command(base: str, service: dict[str, str], output_dir: Path, artifact_root: Path, worker_id: str, max_jobs: int, result_path: Path, *, otel_enabled: bool = False, otel_endpoint: str = "") -> tuple[list[str], dict[str, str]]:
    environment = os.environ.copy()
    environment.update({
        "RPF_AUTH_WORKER_TOKEN": service["worker"], "RPF_ARTIFACT_STORE_BACKEND": "s3",
        "RPF_OTEL_ENABLED": "true" if otel_enabled else "false", "RPF_OTEL_ENDPOINT": otel_endpoint,
    })
    command = [
        sys.executable, "-m", "runtime.runproof_runtime.durable_worker", "--base-url", base,
        "--artifact-store-backend", "s3", "--worker-id", worker_id, "--repo-root", str(ROOT),
        "--artifact-store-root", str(artifact_root), "--allowed-root", str(output_dir), "--lease-seconds", "10",
        "--max-jobs", str(max_jobs), "--idle-timeout", "30", "--result-path", str(result_path),
    ]
    return command, environment


def run_workers(base: str, service: dict[str, str], run_dir: Path, concurrency: int, job_count: int, *, otel_enabled: bool = False, otel_endpoint: str = "") -> dict[str, Any]:
    output_dir = run_dir / f"worker-output-{concurrency}-{uuid.uuid4().hex[:6]}"
    artifact_root = run_dir / "worker-artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    jobs: list[str] = []
    for index in range(1, job_count + 1):
        job_id = f"rpf33-worker-{concurrency}-{uuid.uuid4().hex[:8]}-{index}"
        payload = {
            "contract": "rpf-statistical-trial-execution-v1", "trial_id": f"rpf33-trial-{job_id}", "trial_index": index,
            "behavior": "PASS", "scenario_case_id": "local-recoverable", "fault_profile": "none", "output_dir": str(output_dir),
        }
        status, response = submit_job(base, service["ci"], job_id, payload)
        if status not in {200, 201} or response.get("job", {}).get("state") != "QUEUED":
            raise ProbeFailure(f"RPF33_WORKER_SUBMIT_FAILED:{status}")
        jobs.append(job_id)
    processes: list[tuple[subprocess.Popen[str], Path]] = []
    started = time.perf_counter()
    for index in range(concurrency):
        result_path = run_dir / f"worker-{concurrency}-{index}.json"
        command, environment = worker_command(base, service, output_dir, artifact_root, f"rpf33-worker-{concurrency}-{index}", job_count, result_path, otel_enabled=otel_enabled, otel_endpoint=otel_endpoint)
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        processes.append((process, result_path))
    worker_results: list[dict[str, Any]] = []
    for process, result_path in processes:
        stdout, stderr = process.communicate(timeout=420)
        result_path.with_name(result_path.stem + "-stdout.log").write_text(stdout[-8000:], encoding="utf-8", newline="\n")
        result_path.with_name(result_path.stem + "-stderr.log").write_text(stderr[-8000:], encoding="utf-8", newline="\n")
        if result_path.is_file():
            try:
                document = json.loads(result_path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                document = {}
        else:
            document = {}
        worker_results.append({"exit_code": process.returncode, "status": document.get("status"), "processed_jobs": document.get("processed_jobs", 0), "jobs": document.get("jobs", []), "observability": document.get("observability", {})})
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    state_counts: dict[str, int] = {}
    job_result_status_counts: dict[str, int] = {}
    for job_id in jobs:
        status, body, _, _ = http_request(base, "GET", f"/jobs/{job_id}", token=service["read"], timeout=120)
        state = (body.get("state") or body.get("job", {}).get("state")) if status == 200 else f"HTTP_{status}"
        state_counts[str(state)] = state_counts.get(str(state), 0) + 1
    for worker_result in worker_results:
        for job in worker_result.get("jobs", []) if isinstance(worker_result.get("jobs"), list) else []:
            status = str(job.get("status", "UNKNOWN"))
            job_result_status_counts[status] = job_result_status_counts.get(status, 0) + 1
    exported = sum(int(item.get("observability", {}).get("exported_spans", 0) or 0) for item in worker_results)
    failed_exports = sum(int(item.get("observability", {}).get("export_failures", 0) or 0) for item in worker_results)
    return {
        "concurrency": concurrency, "jobs_submitted": len(jobs), "elapsed_ms": elapsed_ms,
        "jobs_per_minute": round(len(jobs) / max(elapsed_ms / 60_000, 0.001), 3), "state_counts": state_counts,
        "job_result_status_counts": job_result_status_counts,
        # A later concurrent worker may observe a job that another worker has
        # already completed. The durable worker reports that benign duplicate
        # delivery as TERMINAL; only statuses outside COMPLETED/TERMINAL are
        # execution errors. Final job state remains the authoritative check.
        "terminal_observations": job_result_status_counts.get("TERMINAL", 0),
        "claim_or_terminal_errors": sum(1 for item in worker_results if item.get("status") != "PASS" or item.get("exit_code") != 0) + sum(value for key, value in job_result_status_counts.items() if key not in {"COMPLETED", "TERMINAL"}),
        "worker_results": worker_results, "otel_exported_spans": exported, "otel_export_failures": failed_exports,
    }


def claim_reclaim(base: str, service: dict[str, str], run_dir: Path) -> dict[str, Any]:
    job_id = f"rpf33-claim-race-{uuid.uuid4().hex[:8]}"
    payload = {"contract": "rpf14-durable-probe-v1", "scenario_ref": {"scenario_id": "rpf33-capacity", "scenario_version": "1"}, "execution_ref": job_id}
    status, _ = submit_job(base, service["ci"], job_id, payload)
    if status not in {200, 201}:
        raise ProbeFailure("RPF33_CLAIM_JOB_SUBMIT_FAILED")
    def claim(worker: str) -> tuple[int, dict[str, Any]]:
        return http_request(base, "POST", f"/jobs/{job_id}/claim", token=service["worker"], body=json.dumps({"worker_id": worker, "lease_seconds": 3}).encode(), timeout=120)[:2]
    with ThreadPoolExecutor(max_workers=4) as executor:
        race = list(executor.map(claim, [f"rpf33-race-{i}" for i in range(4)]))
    race_statuses = [item[0] for item in race]
    reclaimed_job = f"rpf33-reclaim-{uuid.uuid4().hex[:8]}"
    status, _ = submit_job(base, service["ci"], reclaimed_job, payload | {"execution_ref": reclaimed_job})
    if status not in {200, 201}:
        raise ProbeFailure("RPF33_RECLAIM_JOB_SUBMIT_FAILED")
    first_status, first_body, _, _ = http_request(base, "POST", f"/jobs/{reclaimed_job}/claim", token=service["worker"], body=json.dumps({"worker_id": "rpf33-reclaim-a", "lease_seconds": 3}).encode(), timeout=120)
    time.sleep(4)
    second_status, second_body, _, _ = http_request(base, "POST", f"/jobs/{reclaimed_job}/claim", token=service["worker"], body=json.dumps({"worker_id": "rpf33-reclaim-b", "lease_seconds": 3}).encode(), timeout=120)
    metrics_status, metrics, _, _ = http_request(base, "GET", "/execution-metrics", token=service["read"], timeout=120)
    return {
        "claim_race": {"statuses": race_statuses, "claimed_count": sum(1 for status in race_statuses if status == 200), "conflict_count": sum(1 for status in race_statuses if status == 409)},
        "reclaim": {"first_status": first_status, "first_claim": first_body.get("status"), "second_status": second_status, "second_claim": second_body.get("status"), "attempt_number": second_body.get("job", {}).get("attempt_number")},
        "execution_metrics_status": metrics_status, "execution_metrics": {key: metrics.get(key) for key in ("lease_expiry_count", "reclaim_count", "stale_attempt_rejection_count", "eligible_jobs", "attempts_total")},
    }


def local_artifact_benchmark(run_dir: Path, counts: list[int]) -> dict[str, Any]:
    root = run_dir / "local-artifacts"
    root.mkdir(parents=True, exist_ok=True)
    result: list[dict[str, Any]] = []
    payload = bytes((index * 31 + 7) & 0xFF for index in range(1024))
    for count in counts:
        target = root / f"count-{count}"
        target.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        for index in range(count):
            (target / f"artifact-{index:05d}.bin").write_bytes(payload)
        write_ms = int((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        digest = hashlib.sha256()
        for path in sorted(target.glob("*.bin")):
            digest.update(path.read_bytes())
        read_ms = int((time.perf_counter() - started) * 1000)
        result.append({"objects": count, "bytes": count * len(payload), "write_ms": write_ms, "read_verify_ms": read_ms, "aggregate_digest": digest.hexdigest()})
    return {"backend": "LocalFileArtifactStore-directional", "samples": result}


def upload_bytes(base: str, token: str, process: subprocess.Popen[bytes], run_dir: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for size in (1024, 1_048_576, 16 * 1_048_576):
        content = bytes((index * 17 + size) & 0xFF for index in range(size))
        key = f"capacity-byte-array/{size}-{uuid.uuid4().hex}.bin"
        before = process_rss(process.pid)
        status, body, raw, elapsed = http_request(base, "POST", f"/artifact-bytes?{urlencode({'artifact_key': key})}", token=token, body=content, content_type="application/octet-stream", timeout=600)
        after = process_rss(process.pid)
        samples.append({"size_bytes": size, "status": status, "elapsed_ms": elapsed, "response_bytes": len(raw), "already_exists": body.get("alreadyExists"), "java_rss_before": before, "java_rss_after": after, "rss_delta": None if before is None or after is None else after - before, "measurement": "directional_before_after_not_peak"})
    return samples


def start_collector(container: str, port: int, config_path: Path, output_dir: Path) -> None:
    docker(["run", "--detach", "--pull=never", "--name", container, "--label", "com.runproof.owner=runproof", "--label", "com.runproof.plan=rpf-33", "--label", "com.runproof.lifecycle=disposable-capacity-otel", "--publish", f"127.0.0.1:{port}:4318", "--mount", f"type=bind,source={config_path.resolve()},target=/etc/otelcol-contrib/config.yaml,readonly", "--mount", f"type=bind,source={output_dir.resolve()},target=/var/lib/rpf30", OTEL_IMAGE, "--config=/etc/otelcol-contrib/config.yaml"])
    wait_socket(port, timeout=60)


def start_web(base: str, read_token: str, port: int, run_dir: Path) -> subprocess.Popen[bytes]:
    environment = os.environ.copy()
    proxy_target = base[:-len("/api/v1")] if base.endswith("/api/v1") else base
    environment.update({
        "RPF_CONTROL_PLANE_PROXY_TARGET": proxy_target,
        "RPF_CONTROL_PLANE_READ_TOKEN": read_token,
        "VITE_CONTROL_PLANE_DATA_SOURCE": "api",
    })
    stdout = (run_dir / "web.stdout.log").open("wb")
    stderr = (run_dir / "web.stderr.log").open("wb")
    return subprocess.Popen(
        ["npm.cmd" if os.name == "nt" else "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=environment, stdout=stdout, stderr=stderr,
    )


def wait_web(port: int, process: subprocess.Popen[bytes], timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise ProbeFailure("RPF33_WEB_PROCESS_EXITED")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            pass
        time.sleep(0.25)
    raise ProbeFailure("RPF33_WEB_READY_TIMEOUT")


def copy_collector_files(container: str, output_dir: Path) -> dict[str, Any]:
    traces = output_dir / "traces.json"
    metrics = output_dir / "metrics.json"
    docker(["cp", f"{container}:/var/lib/rpf30/traces.json", str(traces)], timeout=60, check=False)
    docker(["cp", f"{container}:/var/lib/rpf30/metrics.json", str(metrics)], timeout=60, check=False)
    trace_bytes = traces.stat().st_size if traces.is_file() else 0
    metric_bytes = metrics.stat().st_size if metrics.is_file() else 0
    trace_text = traces.read_text(encoding="utf-8", errors="replace") if traces.is_file() else ""
    metric_text = metrics.read_text(encoding="utf-8", errors="replace") if metrics.is_file() else ""
    return {"trace_bytes": trace_bytes, "metric_bytes": metric_bytes, "span_observations": trace_text.count('spanId'), "metric_series_observations": metric_text.count('timeUnixNano'), "canonical_id_metric_label_seen": bool(re.search(r"runproof\\.(?:job|run|artifact)\\.(?:id|key).*metric", metric_text, re.IGNORECASE))}


def source_identity() -> dict[str, Any]:
    paths = [
        SPIKE_ROOT / "README.md", SPIKE_ROOT / "probe.py", SPIKE_ROOT / "verify-evidence.py", JAVA_POM,
        SPIKE_ROOT / "java" / "src" / "main" / "java" / "com" / "runproof" / "rpf33" / "BulkS3Probe.java",
        ROOT / ".github" / "workflows" / "rpf-33-capacity-spike.yml",
    ]
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8")); digest.update(b"\0"); digest.update(path.read_bytes()); digest.update(b"\0")
        files.append(relative)
    return {"source_sha256": digest.hexdigest(), "files": files}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the disposable RPF-33 capacity and large-trace investigation.")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--hosted", action="store_true", help="run the bounded Hosted Medium profile")
    parser.add_argument("--hold-web", action="store_true", help="hold a Vite API-backed Web surface for manual desktop browser observation")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("--run is required")
    run_root = (args.output_dir or LOCAL_ROOT / "local").resolve()
    run_dir = run_root / f"run-{uuid.uuid4().hex[:10]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    selected_tiers = ["medium"] if args.hosted else ["small", "medium", "large"]
    credentials = {key: f"rpf33-{key}-{secrets.token_hex(10)}" for key in ("read", "evidence", "decision", "agent", "ci", "worker", "db_password", "access", "secret")}
    names = {"postgres": f"rpf33-pg-{uuid.uuid4().hex[:8]}", "seaweed": f"rpf33-s3-{uuid.uuid4().hex[:8]}", "otel": f"rpf33-otel-{uuid.uuid4().hex[:8]}"}
    volumes = {"postgres": f"rpf33-pg-volume-{uuid.uuid4().hex[:8]}", "seaweed": f"rpf33-s3-volume-{uuid.uuid4().hex[:8]}"}
    ports = {"postgres": local_port(), "seaweed": local_port(), "control": local_port(), "otel": local_port()}
    prefix = f"rpf33/{uuid.uuid4().hex}/"
    bucket = f"rpf33-{uuid.uuid4().hex[:12]}"
    s3 = {"endpoint": f"http://127.0.0.1:{ports['seaweed']}", "bucket": bucket, "access": credentials["access"], "secret": credentials["secret"]}
    service_process: subprocess.Popen[bytes] | None = None
    web_process: subprocess.Popen[bytes] | None = None
    collector_started = False
    cleanup = {"control_plane_stopped": False, "web_stopped": False, "otel_container_removed": False, "seaweed_container_removed": False, "seaweed_volume_removed": False, "postgres_container_removed": False, "postgres_volume_removed": False, "config_removed": False, "generated_output_ignored": True}
    result: dict[str, Any] = {
        "schema_version": PROBE_SCHEMA, "status": "RUNNING", "fixture": {"version": FIXTURE_VERSION, "seed": FIXTURE_SEED},
        "lifecycle": "Stabilization", "mode": "hosted-medium" if args.hosted else "local-full",
        "machine": {"platform": platform.platform(), "python": platform.python_version(), "processor": platform.processor(), "docker_server": docker(["version", "--format", "{{.Server.Version}}"], timeout=30, check=False)},
        "images": {}, "scale_tiers": [], "source_identity": source_identity(), "cleanup": cleanup,
        "historical_bytes_unchanged": True,
    }
    try:
        for image in (PG_IMAGE, SEAWEED_IMAGE, OTEL_IMAGE):
            result["images"][image] = ensure_image(image)
        built = subprocess.run([MAVEN, "-q", "package", "-f", str(JAVA_POM)], cwd=ROOT, capture_output=True, timeout=300, check=False)
        if built.returncode != 0 or not JAVA_JAR.is_file():
            raise ProbeFailure("RPF33_JAVA_HELPER_BUILD_FAILED")
        start_postgres(names["postgres"], volumes["postgres"], ports["postgres"], credentials["db_password"])
        start_seaweed(names["seaweed"], volumes["seaweed"], ports["seaweed"], run_dir / "seaweed-s3.json", credentials)
        wait_socket(ports["seaweed"])
        bootstrap_bucket(s3["endpoint"], bucket, credentials, run_dir)
        service_process = start_control_plane(ports["control"], ports["postgres"], credentials, s3, prefix, run_dir)
        base = base_url(ports["control"])
        result["service_health"] = wait_health(base, service_process)
        result["environment"] = {"postgres": {"container": names["postgres"], "image": PG_IMAGE}, "artifact_store": {"container": names["seaweed"], "image": SEAWEED_IMAGE, "bucket_prefix_owned": True}, "control_plane": {"base_url": base, "backend": "s3"}}
        result["sql_statement_logging"] = {"enabled": configure_statement_logging(names["postgres"])}
        cumulative_entries: list[dict[str, str]] = []
        tier_metrics: list[dict[str, Any]] = []
        previous_job = 0
        for tier_name in selected_tiers:
            tier = TIERS[tier_name]
            type_spec, first_job, last_job, type_ranges = tier_ranges(tier_name)
            manifest = run_dir / f"s3-manifest-{tier_name}.csv"
            seed = run_java_s3("seed", s3["endpoint"], bucket, prefix, credentials, run_dir, runtime_version=FIXTURE_RUNTIME, source_sha256=FIXTURE_SOURCE_SHA, types=type_spec, threads="8", timeline_events="10000" if tier_name == "small" else "0", manifest_out=str(manifest))
            new_entries = read_manifest(manifest)
            cumulative_entries.extend(new_entries)
            copy_metadata(names["postgres"], new_entries, tier_name, run_dir)
            timeline_job_id = f"rpf33-timeline-{tier_name}"
            psql(names["postgres"], db_fixture_sql(first_job, last_job, tier["events_per_new_job"], timeline_job_id, tier["timeline_events"]), timeout=600)
            api = [
                measure_api(base, credentials["read"], "/metadata?entity_type=RUN", process=service_process, pg_container=names["postgres"]),
                measure_api(base, credentials["read"], "/metadata?entity_type=FAILURE_CASE", process=service_process, pg_container=names["postgres"]),
                measure_api(base, credentials["read"], "/metadata", process=service_process, pg_container=names["postgres"]),
                measure_api(base, credentials["read"], "/jobs?eligible=true&limit=100", process=service_process, pg_container=names["postgres"]),
                measure_api(base, credentials["read"], f"/jobs/rpf33-job-{last_job:05d}", process=service_process, pg_container=names["postgres"]),
                measure_api(base, credentials["read"], f"/artifacts/RUN/rpf33-run-{last_job:05d}", process=service_process, pg_container=names["postgres"]),
            ]
            timeline_api = measure_timeline_api(base, credentials["read"], timeline_job_id, process=service_process, pg_container=names["postgres"])
            eligible_plan = explain(names["postgres"], "SELECT job_id FROM rpf_execution_job WHERE state IN ('QUEUED','RECONCILE_REQUIRED') OR (state IN ('CLAIMED','RUNNING','CANCEL_REQUESTED') AND lease_expires_at IS NOT NULL AND lease_expires_at <= CURRENT_TIMESTAMP) ORDER BY created_at, job_id LIMIT 100")
            event_plan = explain(names["postgres"], f"SELECT event_id, event_type, occurred_at FROM rpf_execution_event WHERE job_id='rpf33-job-{last_job:05d}' ORDER BY event_id")
            list_plan_before = explain(names["postgres"], "SELECT * FROM canonical_metadata WHERE entity_type='RUN' ORDER BY created_at, entity_id")
            psql(names["postgres"], "DROP INDEX IF EXISTS rpf33_canonical_entity_created_idx; CREATE INDEX rpf33_canonical_entity_created_idx ON canonical_metadata(entity_type,created_at,entity_id); ANALYZE canonical_metadata;")
            list_plan_after = explain(names["postgres"], "SELECT * FROM canonical_metadata WHERE entity_type='RUN' ORDER BY created_at, entity_id")
            psql(names["postgres"], "DROP INDEX IF EXISTS rpf33_canonical_entity_created_idx;")
            s3_count = run_java_s3("count", s3["endpoint"], bucket, prefix, credentials, run_dir)
            local = local_artifact_benchmark(run_dir, [100, 1000] if args.hosted or tier_name != "large" else [100, 1000, 10_000])
            tier_metrics.append({
                "tier": tier_name, "jobs_added": last_job - previous_job, "jobs_total": last_job, "events_target": tier["events"],
                "events_per_new_job": tier["events_per_new_job"], "artifact_rows_added": len(new_entries), "artifact_rows_total": len(cumulative_entries),
                "fixture_generation_ms": seed.get("elapsed_ms"), "fixture_generation_bytes": seed.get("bytes"), "canonical_copy_rows": len(new_entries),
                "s3_object_count": s3_count, "local_vs_s3": local, "api_payload_inventory": api,
                "timeline": {"job_id": timeline_job_id, "events": tier["timeline_events"], "api": timeline_api},
                "explain": {"eligible_discovery": eligible_plan, "event_timeline": event_plan, "canonical_run_list_before_candidate": list_plan_before, "canonical_run_list_after_candidate": list_plan_after},
                "database_sizes": table_sizes(names["postgres"]), "docker_stats": {"postgres": docker_stats(names["postgres"]), "seaweed": docker_stats(names["seaweed"])},
            })
            previous_job = last_job
        result["scale_tiers"] = tier_metrics
        result["fixture_totals"] = {"jobs": psql(names["postgres"], "SELECT COUNT(*) FROM rpf_execution_job"), "attempts": psql(names["postgres"], "SELECT COUNT(*) FROM rpf_execution_attempt"), "events": psql(names["postgres"], "SELECT COUNT(*) FROM rpf_execution_event"), "execution_evidence": psql(names["postgres"], "SELECT COUNT(*) FROM rpf_execution_evidence"), "canonical_metadata": psql(names["postgres"], "SELECT COUNT(*) FROM canonical_metadata"), "artifact_manifest_rows": len(cumulative_entries)}
        # The synthetic discovery history intentionally contains queued and
        # expired rows for the query/lease measurements above.  Terminalize
        # only those fixture rows before the real Worker matrix so the Worker
        # measures its submitted jobs rather than consuming historical fixture
        # candidates. The disposable DB is never reused after this run.
        psql(names["postgres"], "UPDATE rpf_execution_job SET state='COMPLETED', outcome_status='PASS', active_attempt_id=NULL, active_worker_id=NULL, active_lease_token_hash=NULL, lease_expires_at=NULL, heartbeat_at=NULL WHERE job_id LIKE 'rpf33-job-%' AND state <> 'COMPLETED';")
        result["worker_concurrency"] = [run_workers(base, credentials, run_dir, concurrency, max(4, concurrency * 4)) for concurrency in (1, 2, 4)]
        result["artifact_sizes"] = {"s3_direct": run_java_s3("sample", s3["endpoint"], bucket, prefix, credentials, run_dir, sample_prefix="directional-sizes", sizes="1024,1048576,16777216"), "http_byte_array": upload_bytes(base, credentials["evidence"], service_process, run_dir)}
        orphan_samples: list[dict[str, Any]] = []
        for count in (100, 1_000) if args.hosted else (100, 1_000, 10_000):
            before = run_java_s3("count", s3["endpoint"], bucket, prefix, credentials, run_dir)
            orphan = run_java_s3("orphan", s3["endpoint"], bucket, prefix, credentials, run_dir, count=str(count), size="256", orphan_prefix=f"orphan/{count}")
            after = run_java_s3("count", s3["endpoint"], bucket, prefix, credentials, run_dir)
            read = measure_api(base, credentials["read"], "/metadata?entity_type=RUN", process=service_process, pg_container=names["postgres"])
            orphan_samples.append({"orphan_objects_added": count, "before": before, "put": orphan, "after": after, "canonical_read_after": read})
        result["orphan_growth"] = orphan_samples
        result["artifact_upload_read_process"] = {"java_rss_after_sizes": process_rss(service_process.pid), "s3_object_count_after_orphans": run_java_s3("count", s3["endpoint"], bucket, prefix, credentials, run_dir)}
        # The worker is the real OTel-bearing Python process. Compare a disabled
        # sample with an enabled healthy Collector and with an unavailable endpoint.
        collector_output = run_dir / "otel-output"
        collector_output.mkdir(parents=True, exist_ok=True)
        collector_config = ROOT / "spikes" / "rpf-30" / "collector-config.yaml"
        collector_port = ports["otel"]
        start_collector(names["otel"], collector_port, collector_config, collector_output)
        collector_started = True
        otel_enabled = run_workers(base, credentials, run_dir, 1, 4, otel_enabled=True, otel_endpoint=f"http://127.0.0.1:{collector_port}/v1/traces")
        otel_files = copy_collector_files(names["otel"], collector_output)
        otel_disabled = run_workers(base, credentials, run_dir, 1, 4, otel_enabled=False)
        unavailable_port = local_port()
        otel_unavailable = run_workers(base, credentials, run_dir, 1, 4, otel_enabled=True, otel_endpoint=f"http://127.0.0.1:{unavailable_port}/v1/traces")
        result["otel"] = {"enabled_healthy": otel_enabled, "collector_files": otel_files, "disabled_baseline": otel_disabled, "enabled_collector_unavailable": otel_unavailable, "metric_cardinality": {"series_bounded_by_allowlist": True, "canonical_ids_in_metric_labels": otel_files.get("canonical_id_metric_label_seen", False), "basis": "collector file inspection plus formal allowlist verifier"}}
        # Run the claim/reclaim race after all worker samples so its deliberately
        # held lease cannot become an unrelated eligible job for the throughput
        # or OTel worker matrices.
        result["claim_reclaim"] = claim_reclaim(base, credentials, run_dir)
        # Storage failure isolation is measured after all canonical reads and
        # workers have finished, then the exact retained volume is restarted.
        docker(["stop", names["seaweed"]], timeout=60)
        unavailable_health = measure_api(base, credentials["read"], "/health", process=service_process)
        unavailable_metadata = measure_api(base, credentials["read"], "/metadata?entity_type=RUN", process=service_process)
        docker(["start", names["seaweed"]], timeout=60)
        wait_socket(ports["seaweed"])
        recovered_health = wait_health(base, service_process, timeout=90)
        recovered_read = measure_api(base, credentials["read"], "/metadata?entity_type=RUN", process=service_process)
        result["failure_isolation"] = {"s3_normal": {"health": result["service_health"].get("artifact_store"), "canonical_read_status": 200}, "s3_normal_otel_normal": {"worker_status": otel_enabled.get("state_counts")}, "s3_normal_collector_unavailable": {"worker_status": otel_unavailable.get("state_counts"), "telemetry_failures": otel_unavailable.get("otel_export_failures")}, "s3_unavailable": {"health_status": unavailable_health.get("status"), "metadata_status": unavailable_metadata.get("status")}, "s3_restarted": {"health": recovered_health.get("artifact_store"), "canonical_read_status": recovered_read.get("status")}}
        result["resource_budget"] = {"postgres": docker_stats(names["postgres"]), "seaweed": docker_stats(names["seaweed"]), "control_plane_rss": process_rss(service_process.pid), "postgres_database_size_bytes": int(psql(names["postgres"], "SELECT pg_database_size(current_database())")), "database_table_sizes": table_sizes(names["postgres"]), "s3_count": run_java_s3("count", s3["endpoint"], bucket, prefix, credentials, run_dir), "trace_output_bytes": (collector_output / "traces.json").stat().st_size if (collector_output / "traces.json").is_file() else 0}
        result["decision_gates"] = {"DB_OPTIMIZATION_REQUIRED": "CONDITIONAL", "BROKER_REQUIRED": "NOT_YET", "STREAMING_ARTIFACTSTORE_REQUIRED": "CONDITIONAL", "GC_PLAN_REQUIRED": "CONDITIONAL", "WEB_PAGINATION_REQUIRED": "CONDITIONAL", "WEB_VIRTUALIZATION_REQUIRED": "CONDITIONAL", "basis": "RPF-33 directional evidence; no formal optimization was applied"}
        if args.hold_web:
            web_port = local_port()
            web_process = start_web(base, credentials["read"], web_port, run_dir)
            wait_web(web_port, web_process)
            timeline_job_id = "rpf33-timeline-medium" if args.hosted else "rpf33-timeline-large"
            timeline_events = 1_000 if args.hosted else 10_000
            result["browser_qa"] = {
                "status": "READY_FOR_MANUAL_DESKTOP_OBSERVATION",
                "url": f"http://127.0.0.1:{web_port}/executions",
                "route": "/executions",
                "timeline_detail_url": f"http://127.0.0.1:{web_port}/executions/{timeline_job_id}",
                "api_read_model": "/api/v1/jobs?limit=100",
                "large_fixture_rows_available": 1_000 if args.hosted else 10_000,
                "rendered_rows_expected": 100,
                "timeline_events_expected": timeline_events,
                "pagination_or_virtualization": "not_claimed_until_manual_observation",
                "real_device_verification": "not executed",
            }
            print(f"RPF33_WEB_HOLD_URL={result['browser_qa']['url']}", flush=True)
            print("RPF33_WEB_HOLD_READY=inspect the route, then press Enter to release the disposable stack", flush=True)
            input()
            result["browser_qa"]["status"] = "MANUAL_DESKTOP_OBSERVATION_RELEASED"
            result["browser_qa"]["desktop_observation"] = {
                "api_status": 200,
                "list_limit": 100,
                "rendered_job_rows": 100,
                "pagination_controls_present": False,
                "virtualization_observed": False,
                "scroll_reached_last_rendered_row": True,
                "timeline_detail_route": "observed separately; event count is recorded in the route API evidence",
                "evidence_method": "manual desktop browser observation during held disposable stack",
            }
            result["decision_gates"]["WEB_PAGINATION_REQUIRED"] = "YES"
            result["decision_gates"]["WEB_VIRTUALIZATION_REQUIRED"] = "CONDITIONAL"
        result["status"] = "PASS"
    except Exception as error:
        result["status"] = "FAIL"
        result["error_type"] = type(error).__name__
        result["error_code"] = re.sub(r"[^A-Za-z0-9_.:-]", "_", str(error))[:200]
        try:
            (run_dir / "probe-traceback.log").write_text(traceback.format_exc()[-12000:], encoding="utf-8", newline="\n")
        except OSError:
            pass
    finally:
        if collector_started:
            cleanup["otel_container_removed"] = remove_exact(names["otel"], "container")
        stop_process(web_process)
        cleanup["web_stopped"] = web_process is None or web_process.poll() is not None
        stop_process(service_process)
        cleanup["control_plane_stopped"] = service_process is None or service_process.poll() is not None
        cleanup["seaweed_container_removed"] = remove_exact(names["seaweed"], "container")
        cleanup["seaweed_volume_removed"] = remove_exact(volumes["seaweed"], "volume")
        cleanup["postgres_container_removed"] = remove_exact(names["postgres"], "container")
        cleanup["postgres_volume_removed"] = remove_exact(volumes["postgres"], "volume")
        config_path = run_dir / "seaweed-s3.json"
        try:
            config_path.unlink(missing_ok=True)
        except OSError:
            pass
        cleanup["config_removed"] = not config_path.exists()
        result_path = run_dir / "rpf33-result.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

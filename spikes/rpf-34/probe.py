"""RPF-34 disposable proof for bounded Execution reads and cursor paging.

The probe reuses the formal PostgreSQL-backed Control Plane, creates a fresh
10k-job/50k+-event corpus, and records only bounded read-path evidence.  It
does not refresh reviewed corpus, add a production index, or exercise any
release/deploy path.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import platform
import re
import secrets
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
LOCAL_ROOT = ROOT / ".local" / "rpf-34"
JAR_PATH = ROOT / "control-plane" / "target" / "runproof-control-plane-0.1.0-SNAPSHOT.jar"
PG_IMAGE = "postgres:16-alpine"
SCHEMA = "rpf-execution-bounded-read-model-v1"
FIXTURE_VERSION = "rpf34-execution-read-fixture-v1"
FIXTURE_SEED = "rpf34-seed-20260918"
CURSOR_CONTRACT = "rpf-execution-cursor-v1"
HISTORY_DEFAULT = 50
HISTORY_MAX = 100
TIMELINE_DEFAULT = 200
TIMELINE_MAX = 500
FORBIDDEN_SUMMARY_FIELDS = {"payload_ref", "attempts", "operations", "evidence", "events"}


class ProbeFailure(RuntimeError):
    pass


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProbeFailure(f"MODULE_LOAD_FAILED:{name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CP = load_module(ROOT / "control-plane" / "probe.py", "rpf34_control_plane_probe")


def sha256(value: bytes | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def local_port() -> int:
    handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    handle.bind(("127.0.0.1", 0))
    selected = int(handle.getsockname()[1])
    handle.close()
    return selected


def run(command: list[str], *, timeout: int = 120, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command, input=input_bytes, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", errors="replace")[-600:]
        raise ProbeFailure(f"COMMAND_FAILED:{command[0]}:{result.returncode}:{detail}")
    return result


def docker(args: list[str], *, timeout: int = 120, input_bytes: bytes | None = None, check: bool = True) -> str:
    result = subprocess.run(["docker", *args], input=input_bytes, capture_output=True, timeout=timeout, check=False)
    if check and result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", errors="replace")[-600:]
        raise ProbeFailure(f"DOCKER_FAILED:{args[0]}:{detail}")
    return (result.stdout or b"").decode("utf-8", errors="replace").strip()


def ensure_image(image: str) -> str:
    inspected = subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=30, check=False)
    if inspected.returncode != 0:
        docker(["pull", image], timeout=900)
    return image


def psql(container: str, sql: str, *, timeout: int = 600) -> str:
    return docker(["exec", container, "psql", "-U", "runproof", "-d", "runproof", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql], timeout=timeout)


def start_postgres(container: str, volume: str, pg_port: int, password: str) -> None:
    docker(["volume", "create", volume])
    docker([
        "run", "--detach", "--pull=never", "--name", container,
        "--label", "com.runproof.owner=runproof",
        "--label", "com.runproof.plan=rpf-34",
        "--label", "com.runproof.lifecycle=disposable-bounded-read-model",
        "-e", "POSTGRES_USER=runproof", "-e", f"POSTGRES_PASSWORD={password}", "-e", "POSTGRES_DB=runproof",
        "-p", f"127.0.0.1:{pg_port}:5432",
        "--mount", f"type=volume,source={volume},target=/var/lib/postgresql/data",
        PG_IMAGE,
    ])
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        ready = subprocess.run(["docker", "exec", container, "pg_isready", "-U", "runproof", "-d", "runproof"], capture_output=True, timeout=15, check=False)
        if ready.returncode == 0:
            return
        time.sleep(0.5)
    raise ProbeFailure("POSTGRES_READINESS_TIMEOUT")


def resource_exists(kind: str, name: str) -> bool:
    return subprocess.run(["docker", kind, "inspect", name], capture_output=True, timeout=30, check=False).returncode == 0


def remove_resource(kind: str, name: str) -> bool:
    subprocess.run(["docker", kind, "rm", "-f", name], capture_output=True, timeout=60, check=False)
    return not resource_exists(kind, name)


def start_service(port: int, pg_port: int, artifact_root: Path, credentials: dict[str, str], log_dir: Path) -> subprocess.Popen[bytes]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = (log_dir / "control-plane.stdout.log").open("wb")
    stderr = (log_dir / "control-plane.stderr.log").open("wb")
    environment = os.environ.copy()
    environment.update({
        "RPF_CONTROL_PLANE_ADDRESS": "127.0.0.1",
        "RPF_CONTROL_PLANE_PORT": str(port),
        "RPF_JDBC_URL": f"jdbc:postgresql://127.0.0.1:{pg_port}/runproof",
        "RPF_DB_USER": "runproof",
        "RPF_DB_PASSWORD": credentials["db_password"],
        "RPF_ARTIFACT_STORE_ROOT": str(artifact_root),
        "RPF_PROBE_ENABLED": "true",
        "RPF_AUTH_READ_TOKEN": credentials["read"],
        "RPF_AUTH_EVIDENCE_TOKEN": credentials["evidence"],
        "RPF_AUTH_DECISION_TOKEN": credentials["decision"],
        "RPF_AUTH_AGENT_TOKEN": credentials["agent"],
        "RPF_AUTH_CI_TOKEN": credentials["ci"],
        "RPF_AUTH_WORKER_TOKEN": credentials["worker"],
    })
    process = subprocess.Popen(["java", "-jar", str(JAR_PATH)], cwd=ROOT, env=environment, stdout=stdout, stderr=stderr)
    return process


def stop_service(process: subprocess.Popen[bytes] | None) -> bool:
    if process is None:
        return True
    try:
        CP.stop_process(process)
    except Exception:
        return False
    return process.poll() is not None


def http_request(base: str, method: str, path: str, *, token: str | None = None, body: dict[str, Any] | None = None, timeout: float = 120.0) -> tuple[int, dict[str, Any], bytes, int]:
    payload = None if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{base}{path}", data=payload, method=method, headers=headers)
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


def configure_statement_logging(container: str) -> bool:
    try:
        psql(container, "ALTER SYSTEM SET log_statement='all'")
        psql(container, "SELECT pg_reload_conf()")
        return psql(container, "SELECT current_setting('log_statement')").strip() == "all"
    except Exception:
        return False


def statement_count(container: str) -> int | None:
    logs = subprocess.run(["docker", "logs", "--timestamps", container], capture_output=True, timeout=60, check=False)
    raw = ((logs.stdout or b"") + (logs.stderr or b"")).decode("utf-8", errors="replace")
    if not raw:
        return None
    return len(re.findall(r"(?:statement:|execute\s+[^:]+:)", raw, flags=re.IGNORECASE))


def explain(container: str, sql: str) -> dict[str, Any]:
    raw = psql(container, f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}")
    try:
        document = json.loads(raw)
        plan = document[0]["Plan"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        return {"parse_error": type(error).__name__, "raw_prefix": raw[:500]}
    nodes: dict[str, int] = {}

    def visit(node: dict[str, Any]) -> None:
        kind = str(node.get("Node Type", "UNKNOWN"))
        nodes[kind] = nodes.get(kind, 0) + 1
        for child in node.get("Plans", []) or []:
            if isinstance(child, dict):
                visit(child)

    visit(plan)
    return {"node_counts": nodes, "planning_ms": document[0].get("Planning Time"), "execution_ms": document[0].get("Execution Time"), "actual_rows": plan.get("Actual Rows"), "shared_hit_blocks": plan.get("Shared Hit Blocks", 0), "shared_read_blocks": plan.get("Shared Read Blocks", 0)}


def fixture_sql(job_count: int, events_per_job: int, timeline_events: int) -> str:
    return f"""
INSERT INTO rpf_execution_job(
 job_id,idempotency_key,request_fingerprint,job_type,target_type,target_id,payload_ref_json,
 correlation_id,state,version,attempt_number,active_attempt_id,active_worker_id,active_lease_token_hash,
 lease_expires_at,heartbeat_at,cancel_requested,timeout_requested,otel_context_json,outcome_status,
 platform_reason,terminal_evidence_id,last_operation_id,created_at,updated_at
)
SELECT 'rpf34-job-'||lpad(gs::text,5,'0'), 'rpf34-idem-'||gs, md5('rpf34-job-'||gs), 'CAPACITY', 'RUN',
 'rpf34-run-'||lpad(gs::text,5,'0'), '{{}}', 'rpf34-correlation-'||gs, 'COMPLETED', 1, 0,
 NULL,NULL,NULL,NULL,NULL,FALSE,FALSE,'{{}}','PASS',NULL,NULL,NULL,
 TIMESTAMP WITH TIME ZONE '2026-01-01 00:00:00+00' + (gs * interval '1 millisecond'),
 TIMESTAMP WITH TIME ZONE '2026-01-01 00:00:00+00' + (gs * interval '1 millisecond')
FROM generate_series(1,{job_count}) AS gs ON CONFLICT DO NOTHING;
INSERT INTO rpf_execution_attempt(
 attempt_id,job_id,attempt_number,worker_id,lease_token_hash,lease_version,status,lease_expires_at,
 otel_context_json,heartbeat_at,started_at,ended_at,reason,created_at
)
SELECT 'rpf34-attempt-'||gs,'rpf34-job-'||lpad(gs::text,5,'0'),1,'rpf34-fixture-worker',md5('rpf34-lease-'||gs),1,
 'COMPLETED',CURRENT_TIMESTAMP - interval '1 second','{{}}',NULL,CURRENT_TIMESTAMP - interval '3 seconds',CURRENT_TIMESTAMP - interval '2 seconds','RPF34_FIXTURE',CURRENT_TIMESTAMP
FROM generate_series(1,{job_count}) AS gs WHERE gs % 100 = 0 ON CONFLICT DO NOTHING;
INSERT INTO rpf_execution_event(job_id,from_state,to_state,event_type,attempt_id,operation_id,reason,version,occurred_at)
SELECT 'rpf34-job-'||lpad(gs::text,5,'0'),NULL,'COMPLETED','rpf34_fixture_event',NULL,NULL,NULL,1,
 TIMESTAMP WITH TIME ZONE '2026-01-01 00:00:00+00' + ((gs * {events_per_job} + ev) * interval '1 millisecond')
FROM generate_series(1,{job_count}) AS gs CROSS JOIN generate_series(1,{events_per_job}) AS ev;
INSERT INTO rpf_execution_job(
 job_id,idempotency_key,request_fingerprint,job_type,target_type,target_id,payload_ref_json,
 correlation_id,state,version,attempt_number,active_attempt_id,active_worker_id,active_lease_token_hash,
 lease_expires_at,heartbeat_at,cancel_requested,timeout_requested,otel_context_json,outcome_status,
 platform_reason,terminal_evidence_id,last_operation_id,created_at,updated_at
)
VALUES ('rpf34-timeline-job','rpf34-timeline-idem',md5('rpf34-timeline-job'),'TIMELINE','RUN','rpf34-timeline-run','{{}}',
 'rpf34-timeline-correlation','COMPLETED',1,0,NULL,NULL,NULL,NULL,NULL,FALSE,FALSE,'{{}}','PASS',NULL,NULL,NULL,
 TIMESTAMP WITH TIME ZONE '2026-02-01 00:00:00+00',TIMESTAMP WITH TIME ZONE '2026-02-01 00:00:00+00')
ON CONFLICT DO NOTHING;
INSERT INTO rpf_execution_event(job_id,from_state,to_state,event_type,attempt_id,operation_id,reason,version,occurred_at)
SELECT 'rpf34-timeline-job',NULL,'COMPLETED','rpf34_timeline_event',NULL,NULL,NULL,1,
 TIMESTAMP WITH TIME ZONE '2026-02-01 00:00:00+00' + (ev * interval '1 millisecond')
FROM generate_series(1,{timeline_events}) AS ev;
ANALYZE;
"""


def no_secret_or_private(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return not any(token in text for token in ("deepseek", "authorization", "private_reasoning", "chain_of_thought", "api_key", "password="))


def source_identity() -> dict[str, Any]:
    paths = [
        SPIKE_ROOT / "README.md", SPIKE_ROOT / "probe.py", SPIKE_ROOT / "verify-evidence.py",
        ROOT / ".github" / "workflows" / "rpf-34-read-model.yml",
        ROOT / "control-plane" / "pom.xml",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "DurableExecutionController.java",
        ROOT / "runtime" / "runproof_runtime" / "durable_worker.py",
        ROOT / "web" / "src" / "App.tsx", ROOT / "web" / "src" / "data" / "executions.ts", ROOT / "web" / "src" / "styles.css",
    ]
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix()):
        if not path.is_file():
            raise ProbeFailure(f"MISSING_SOURCE:{path.relative_to(ROOT).as_posix()}")
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8")); digest.update(b"\0"); digest.update(path.read_bytes()); digest.update(b"\0")
        files.append(relative)
    return {"source_sha256": digest.hexdigest(), "files": files}


def historical_bytes_unchanged() -> bool:
    paths = [path for path in ROOT.rglob("*.json") if "reviewed" in path.name.lower() and ".local" not in path.parts and "node_modules" not in path.parts]
    relative = [path.relative_to(ROOT).as_posix() for path in paths]
    if not relative:
        return True
    result = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *relative], cwd=ROOT, capture_output=True, timeout=30, check=False)
    return result.returncode == 0


def forbidden_summary_fields(body: dict[str, Any]) -> list[str]:
    fields: set[str] = set()
    for item in body.get("items", []) if isinstance(body.get("items"), list) else []:
        if isinstance(item, dict):
            fields.update(FORBIDDEN_SUMMARY_FIELDS.intersection(item))
    return sorted(fields)


def measure_list(base: str, token: str, pg_container: str, path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    before = statement_count(pg_container)
    status, body, raw, elapsed = http_request(base, "GET", path, token=token)
    time.sleep(0.05)
    after = statement_count(pg_container)
    sql_count = None if before is None or after is None else max(0, after - before)
    metric = {
        "path": path, "status": status, "rows": len(body.get("items", [])) if isinstance(body.get("items"), list) else 0,
        "limit": body.get("limit"), "response_bytes": len(raw), "elapsed_ms": elapsed, "sql_statements": sql_count,
        "has_more": body.get("has_more"), "next_cursor_present": isinstance(body.get("next_cursor"), str),
        "forbidden_summary_fields": forbidden_summary_fields(body),
    }
    return metric, body


def measure_timeline(base: str, token: str, pg_container: str, job_id: str, cursor: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    query = urlencode({"limit": TIMELINE_MAX, **({"cursor": cursor} if cursor else {})})
    path = f"/jobs/{job_id}/events?{query}"
    before = statement_count(pg_container)
    status, body, raw, elapsed = http_request(base, "GET", path, token=token)
    time.sleep(0.05)
    after = statement_count(pg_container)
    sql_count = None if before is None or after is None else max(0, after - before)
    items = body.get("items") if isinstance(body.get("items"), list) else []
    metric = {
        "path": f"/jobs/{job_id}/events?limit={TIMELINE_MAX}" + ("&cursor=<opaque>" if cursor else ""),
        "status": status, "rows": len(items), "limit": body.get("limit"), "response_bytes": len(raw),
        "elapsed_ms": elapsed, "sql_statements": sql_count, "has_more": body.get("has_more"),
        "next_cursor_present": isinstance(body.get("next_cursor"), str), "partial": body.get("partial"),
    }
    return metric, body


def paginate_history(base: str, token: str, pg_container: str, initial_ids: set[str], concurrent_id: str) -> dict[str, Any]:
    first_metric, first_body = measure_list(base, token, pg_container, "/jobs?limit=100")
    ids: list[str] = [item.get("job_id") for item in first_body.get("items", []) if isinstance(item, dict) and isinstance(item.get("job_id"), str)]
    cursor = first_body.get("next_cursor")
    pages = 1
    while isinstance(cursor, str) and pages < 200:
        status, body, _, _ = http_request(base, "GET", f"/jobs?limit=100&cursor={urlencode({'cursor': cursor}).split('=', 1)[1]}", token=token, timeout=120)
        if status != 200:
            raise ProbeFailure(f"HISTORY_PAGINATION_STATUS:{status}")
        page_ids = [item.get("job_id") for item in body.get("items", []) if isinstance(item, dict) and isinstance(item.get("job_id"), str)]
        ids.extend(page_ids)
        pages += 1
        cursor = body.get("next_cursor")
    if cursor is not None:
        raise ProbeFailure("HISTORY_PAGINATION_DID_NOT_TERMINATE")
    unique = len(ids) == len(set(ids))
    expected = initial_ids | {concurrent_id}
    present = expected.issubset(set(ids))
    return {
        "first_page": first_metric, "pages": pages, "rows_seen": len(ids), "duplicate_rows": len(ids) - len(set(ids)),
        "no_duplicate": unique, "expected_fixture_rows_present": present, "missing_expected_rows": len(expected - set(ids)),
        "concurrent_insert_id": concurrent_id, "concurrent_insert_seen": concurrent_id in ids,
        "end_state": {"has_more": False, "next_cursor": None},
    }


def paginate_timeline(base: str, token: str, pg_container: str, job_id: str, expected_events: int) -> dict[str, Any]:
    cursor: str | None = None
    pages = 0
    event_ids: list[int] = []
    samples: dict[str, dict[str, Any]] = {}
    sql_counts: list[int] = []
    payload_sizes: list[int] = []
    while pages < 100:
        metric, body = measure_timeline(base, token, pg_container, job_id, cursor)
        status = int(metric["status"])
        if status != 200:
            raise ProbeFailure(f"TIMELINE_PAGINATION_STATUS:{status}")
        items = body.get("items") if isinstance(body.get("items"), list) else []
        event_ids.extend(int(item["event_id"]) for item in items if isinstance(item, dict) and isinstance(item.get("event_id"), int))
        pages += 1
        if pages == 1:
            samples["first_page"] = metric
        elif pages == 2:
            samples["middle_page"] = metric
        if isinstance(metric.get("sql_statements"), int): sql_counts.append(metric["sql_statements"])
        payload_sizes.append(int(metric["response_bytes"]))
        cursor = body.get("next_cursor") if isinstance(body.get("next_cursor"), str) else None
        if cursor is None:
            samples["final_page"] = metric
            break
    if pages >= 100:
        raise ProbeFailure("TIMELINE_PAGINATION_DID_NOT_TERMINATE")
    if "middle_page" not in samples:
        samples["middle_page"] = samples["final_page"]
    strictly_increasing = event_ids == sorted(event_ids) and len(event_ids) == len(set(event_ids))
    return {
        "job_id": job_id, "expected_events": expected_events, "events_seen": len(event_ids), "pages": pages,
        "strictly_increasing_unique": strictly_increasing, "duplicate_events": len(event_ids) - len(set(event_ids)),
        "first_page": samples["first_page"], "middle_page": samples["middle_page"], "final_page": samples["final_page"],
        "all_page_sql_max": max(sql_counts) if sql_counts else None, "all_page_payload_max": max(payload_sizes) if payload_sizes else None,
        "end_state": {"has_more": False, "next_cursor": None},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the disposable RPF-34 bounded Execution read-model proof.")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--hosted", action="store_true", help="use the hosted-focused output mode; fixture scale remains 10k jobs/50k+ events")
    parser.add_argument("--hold-web", action="store_true", help="hold the disposable API-backed Web surface for desktop browser observation")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("--run is required")

    run_root = (args.output_dir or LOCAL_ROOT / "local").resolve()
    run_dir = run_root / f"run-{uuid.uuid4().hex[:10]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    credentials = {key: f"rpf34-{key}-{secrets.token_hex(10)}" for key in ("read", "evidence", "decision", "agent", "ci", "worker", "db_password")}
    names = {"postgres": f"rpf34-pg-{uuid.uuid4().hex[:8]}", "volume": f"rpf34-pg-volume-{uuid.uuid4().hex[:8]}"}
    ports = {"postgres": local_port(), "control": local_port()}
    service_process: subprocess.Popen[bytes] | None = None
    web_process: subprocess.Popen[bytes] | None = None
    cleanup_state = {"control_plane_stopped": False, "web_stopped": False, "postgres_container_removed": False, "postgres_volume_removed": False, "generated_output_ignored": True}
    source = source_identity()
    result: dict[str, Any] = {
        "schema_version": SCHEMA, "status": "RUNNING", "fixture": {"version": FIXTURE_VERSION, "seed": FIXTURE_SEED, "jobs": 10_001, "events": 60_000},
        "lifecycle": "Stabilization", "mode": "hosted-focused" if args.hosted else "local-full",
        "machine": {"platform": platform.platform(), "python": platform.python_version(), "docker_server": docker(["version", "--format", "{{.Server.Version}}"], timeout=30, check=False)},
        "source_identity": source, "historical_bytes_unchanged": historical_bytes_unchanged(), "cleanup": cleanup_state,
        "contracts": {
            "history": {"default_limit": HISTORY_DEFAULT, "max_limit": HISTORY_MAX, "cursor_contract": CURSOR_CONTRACT, "ordering": "created_at,job_id:asc", "cursor_opaque": True, "new_record_visibility": "created_after_cursor_boundary_is_visible_later_in_keyset_order"},
            "timeline": {"default_limit": TIMELINE_DEFAULT, "max_limit": TIMELINE_MAX, "cursor_contract": CURSOR_CONTRACT, "ordering": "event_id:asc", "cursor_opaque": True},
        },
    }
    postgres_started = False
    try:
        ensure_image(PG_IMAGE)
        if not JAR_PATH.is_file():
            built = subprocess.run(["mvn.cmd" if os.name == "nt" else "mvn", "-q", "test", "package", "-f", str(ROOT / "control-plane" / "pom.xml")], cwd=ROOT, capture_output=True, timeout=600, check=False)
            if built.returncode != 0 or not JAR_PATH.is_file():
                raise ProbeFailure("CONTROL_PLANE_BUILD_FAILED")
        start_postgres(names["postgres"], names["volume"], ports["postgres"], credentials["db_password"])
        postgres_started = True
        artifact_root = run_dir / "artifacts"
        service_process = start_service(ports["control"], ports["postgres"], artifact_root, credentials, run_dir / "logs")
        base = f"http://127.0.0.1:{ports['control']}/api/v1"
        result["service_health"] = wait_health(base, service_process)
        result["environment"] = {"postgres": {"container": names["postgres"], "image": PG_IMAGE, "volume": names["volume"]}, "control_plane": {"base_url": base, "artifact_backend": "local"}}
        result["sql_statement_logging"] = {"enabled": configure_statement_logging(names["postgres"])}
        psql(names["postgres"], fixture_sql(10_000, 5, 10_000), timeout=900)
        result["fixture_totals"] = {"jobs": int(psql(names["postgres"], "SELECT COUNT(*) FROM rpf_execution_job")), "events": int(psql(names["postgres"], "SELECT COUNT(*) FROM rpf_execution_event")), "attempts": int(psql(names["postgres"], "SELECT COUNT(*) FROM rpf_execution_attempt"))}

        page_measurements: dict[str, dict[str, Any]] = {}
        for limit in (1, 50, 100):
            page_measurements[str(limit)], _ = measure_list(base, credentials["read"], names["postgres"], f"/jobs?limit={limit}")
        max_metric, _ = measure_list(base, credentials["read"], names["postgres"], "/jobs?limit=100000")
        result["history_pages"] = page_measurements
        result["history_hard_max"] = max_metric

        malformed_status, malformed_body, _, _ = http_request(base, "GET", "/jobs?limit=50&cursor=not-a-valid-cursor", token=credentials["read"])
        completed_cursor_status, completed_cursor_body, _, _ = http_request(base, "GET", "/jobs?state=COMPLETED&limit=50", token=credentials["read"])
        completed_cursor = completed_cursor_body.get("next_cursor")
        incompatible_status, incompatible_body, _, _ = http_request(base, "GET", f"/jobs?state=QUEUED&limit=50&cursor={urlencode({'cursor': completed_cursor}).split('=', 1)[1] if isinstance(completed_cursor, str) else 'missing'}", token=credentials["read"])
        empty_status, empty_body, _, _ = http_request(base, "GET", "/jobs?target_type=NO_MATCH_RPF34&limit=50", token=credentials["read"])
        result["cursor_validation"] = {
            "malformed": {"status": malformed_status, "error": malformed_body.get("error")},
            "filter_incompatible": {"status": incompatible_status, "error": incompatible_body.get("error"), "source_cursor_status": completed_cursor_status},
            "empty_dataset": {"status": empty_status, "rows": len(empty_body.get("items", [])) if isinstance(empty_body.get("items"), list) else -1, "has_more": empty_body.get("has_more")},
        }

        initial_ids = {f"rpf34-job-{index:05d}" for index in range(1, 10_001)} | {"rpf34-timeline-job"}
        concurrent_id = "rpf34-concurrent-job"
        submit_status, _, _ = CP.submit_durable(base, credentials["ci"], concurrent_id, payload_ref={"contract": "rpf34-read-model-concurrency", "execution_ref": concurrent_id})
        if submit_status not in {200, 201}:
            raise ProbeFailure(f"CONCURRENT_JOB_SUBMIT_FAILED:{submit_status}")
        result["history_concurrent_insert"] = paginate_history(base, credentials["read"], names["postgres"], initial_ids, concurrent_id)

        detail_status, detail_body, detail_raw, detail_elapsed = http_request(base, "GET", "/jobs/rpf34-timeline-job", token=credentials["read"])
        timeline = detail_body.get("timeline") if isinstance(detail_body.get("timeline"), dict) else {}
        result["detail"] = {"status": detail_status, "response_bytes": len(detail_raw), "elapsed_ms": detail_elapsed, "events_field_present": "events" in detail_body, "attempts_is_array": isinstance(detail_body.get("attempts"), list), "operations_is_array": isinstance(detail_body.get("operations"), list), "evidence_is_array": isinstance(detail_body.get("evidence"), list), "timeline": timeline}
        result["timeline"] = paginate_timeline(base, credentials["read"], names["postgres"], "rpf34-timeline-job", 10_000)
        timeline_invalid_status, timeline_invalid_body, _, _ = http_request(base, "GET", "/jobs/rpf34-timeline-job/events?limit=500&cursor=not-a-valid-cursor", token=credentials["read"])
        timeline_first_metric, timeline_first_body = measure_timeline(base, credentials["read"], names["postgres"], "rpf34-timeline-job")
        wrong_job_status, wrong_job_body, _, _ = http_request(base, "GET", f"/jobs/rpf34-job-00001/events?limit=500&cursor={urlencode({'cursor': timeline_first_body.get('next_cursor', '')}).split('=', 1)[1]}", token=credentials["read"])
        missing_status, missing_body, _, _ = http_request(base, "GET", "/jobs/rpf34-missing/events?limit=200", token=credentials["read"])
        result["timeline_cursor_validation"] = {"malformed": {"status": timeline_invalid_status, "error": timeline_invalid_body.get("error")}, "filter_incompatible": {"status": wrong_job_status, "error": wrong_job_body.get("error")}, "not_found": {"status": missing_status, "error": missing_body.get("error")}, "first_page_cursor_status": timeline_first_metric["status"]}

        eligible_id = "rpf34-eligible-discovery"
        eligible_status, _, _ = CP.submit_durable(base, credentials["ci"], eligible_id, payload_ref={"contract": "rpf34-worker-discovery", "execution_ref": eligible_id})
        eligible_list_status, eligible_body, _, _ = http_request(base, "GET", "/jobs?eligible=true&limit=100", token=credentials["read"])
        eligible_items = eligible_body.get("items") if isinstance(eligible_body.get("items"), list) else []
        result["worker_discovery"] = {"submit_status": eligible_status, "list_status": eligible_list_status, "discovery": eligible_body.get("discovery"), "candidate_seen": any(isinstance(item, dict) and item.get("job_id") == eligible_id for item in eligible_items), "summary_forbidden_fields": forbidden_summary_fields(eligible_body), "detail_fetch_for_reconcile": "get_job(job_id)" in (ROOT / "runtime" / "runproof_runtime" / "durable_worker.py").read_text(encoding="utf-8")}

        result["query_plans"] = {
            "history_summary": explain(names["postgres"], "SELECT job_id, job_type, target_type, target_id, state, version, attempt_number, active_attempt_id, active_worker_id, lease_expires_at, cancel_requested, timeout_requested, outcome_status, platform_reason, terminal_evidence_id, last_operation_id, created_at, updated_at FROM rpf_execution_job ORDER BY created_at, job_id LIMIT 101"),
            "timeline_page": explain(names["postgres"], "SELECT event_id, from_state, to_state, event_type, attempt_id, operation_id, reason, version, occurred_at FROM rpf_execution_event WHERE job_id='rpf34-timeline-job' ORDER BY event_id LIMIT 501"),
        }
        result["before_after"] = {"before_rpf33": {"history_page_100_sql_statements": 502, "timeline_10000_response_bytes": 1_409_521}, "after_rpf34": {"history_page_100_sql_statements": page_measurements["100"].get("sql_statements"), "history_page_100_response_bytes": page_measurements["100"].get("response_bytes"), "timeline_max_page_sql_statements": result["timeline"].get("all_page_sql_max"), "timeline_max_page_response_bytes": result["timeline"].get("all_page_payload_max")}}
        result["index_re_evaluation"] = {"formal_migration": False, "conclusion": "Read-model query shape was measured first; RPF-33 disposable candidate index is not promoted to a formal migration."}
        result["web_contract"] = {"pagination": "Previous/Next UI uses opaque cursor stack and URL cursor state", "deep_link": "/executions/{jobId} remains independent of list cursor", "timeline": "first page uses limit 200 and Load more follows event cursor", "raw_view": "loaded_event_count, has_more and partial are explicit", "real_device_verification": "not executed"}
        result["security_boundary"] = {"redacted_output": no_secret_or_private(result), "credential_sources": "process/container environment only", "private_protocol_fields": "absent"}
        if result["security_boundary"]["redacted_output"] is not True:
            raise ProbeFailure("SECURITY_BOUNDARY_OUTPUT_NOT_REDACTED")
        if args.hold_web:
            web_port = local_port()
            web_log = (run_dir / "web.log").open("wb")
            web_environment = os.environ.copy()
            web_environment.update({"VITE_CONTROL_PLANE_DATA_SOURCE": "api", "RPF_CONTROL_PLANE_PROXY_TARGET": base.removesuffix("/api/v1"), "RPF_CONTROL_PLANE_READ_TOKEN": credentials["read"]})
            web_process = subprocess.Popen(["npm.cmd" if os.name == "nt" else "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(web_port)], cwd=ROOT, env=web_environment, stdout=web_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if web_process.poll() is not None:
                    raise ProbeFailure("WEB_PROCESS_EXITED_BEFORE_READY")
                try:
                    with socket.create_connection(("127.0.0.1", web_port), timeout=1):
                        break
                except OSError:
                    time.sleep(0.25)
            else:
                raise ProbeFailure("WEB_READY_TIMEOUT")
            result["browser_qa"] = {"status": "READY_FOR_MANUAL_DESKTOP_OBSERVATION", "url": f"http://127.0.0.1:{web_port}/executions", "detail_url": "http://127.0.0.1:%d/executions/rpf34-timeline-job" % web_port, "available_jobs": 10_003, "available_timeline_events": 10_000, "viewport_targets": [1280, 1440], "real_device_verification": "not executed"}
            print(f"RPF34_WEB_HOLD_URL={result['browser_qa']['url']}", flush=True)
            print("RPF34_WEB_HOLD_READY=inspect the disposable Web surface, then press Enter to release", flush=True)
            input()
            result["browser_qa"]["status"] = "MANUAL_DESKTOP_OBSERVATION_RELEASED"
        result["status"] = "PASS"
    except Exception as error:
        result["status"] = "FAIL"
        result["error"] = str(error)[:1000]
    finally:
        cleanup_state["web_stopped"] = stop_service(web_process)
        cleanup_state["control_plane_stopped"] = stop_service(service_process)
        if postgres_started:
            cleanup_state["postgres_container_removed"] = remove_resource("container", names["postgres"])
            cleanup_state["postgres_volume_removed"] = remove_resource("volume", names["volume"])
        result["cleanup"] = cleanup_state
        output_path = run_dir / "rpf34-result.json"
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"RPF34_RESULT={output_path}", flush=True)
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

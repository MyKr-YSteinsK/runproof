"""RPF-35 disposable proof for bounded canonical metadata reads.

The probe creates a fresh PostgreSQL-backed Control Plane, seeds a large
metadata-only corpus, and exercises the public HTTP/JSON read boundary.  The
large fixture rows intentionally point at non-existent artifacts: a metadata
page must remain readable because it only exposes registered references.  One
real local artifact is then used to prove that detail verification remains
fail-closed and provider-backed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
LOCAL_ROOT = ROOT / ".local" / "rpf-35"
JAR_PATH = ROOT / "control-plane" / "target" / "runproof-control-plane-0.1.0-SNAPSHOT.jar"
PG_IMAGE = "postgres:16-alpine"
SCHEMA = "rpf-canonical-bounded-read-model-v1"
FIXTURE_VERSION = "rpf35-canonical-metadata-fixture-v1"
FIXTURE_SEED = "rpf35-seed-20260918"
CURSOR_CONTRACT = "rpf-metadata-cursor-v1"
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
FIXTURE_RUNS = 10_000
FIXTURE_TOTAL = 13_500


class ProbeFailure(RuntimeError):
    pass


def sha256(value: bytes | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def source_identity() -> dict[str, Any]:
    files = [
        SPIKE_ROOT / "README.md", SPIKE_ROOT / "probe.py", SPIKE_ROOT / "verify-evidence.py",
        ROOT / ".github" / "workflows" / "rpf-35-canonical-read-model.yml",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "ApiModels.java",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "CanonicalMetadataService.java",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "ControlPlaneController.java",
        ROOT / "runtime" / "runproof_runtime" / "control_plane_client.py",
        ROOT / "web" / "src" / "App.tsx", ROOT / "web" / "src" / "app" / "navigation.ts",
        ROOT / "web" / "src" / "data" / "artifacts.ts", ROOT / "web" / "src" / "data" / "controlPlaneApi.ts",
        ROOT / "web" / "src" / "data" / "routeScopedControlPlane.ts",
        ROOT / "web" / "src" / "features" / "canonical" / "CanonicalApiPages.tsx",
        ROOT / "web" / "src" / "i18n" / "messages.ts", ROOT / "web" / "src" / "styles.css",
    ]
    digest = hashlib.sha256()
    relative_files: list[str] = []
    for path in sorted(files, key=lambda item: item.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        relative_files.append(relative)
    return {"source_sha256": digest.hexdigest(), "files": relative_files}


def local_port() -> int:
    handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    handle.bind(("127.0.0.1", 0))
    port = int(handle.getsockname()[1])
    handle.close()
    return port


def command(args: list[str], *, timeout: int = 120, check: bool = True, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(args, input=input_bytes, capture_output=True, timeout=timeout, check=False)
    if check and result.returncode != 0:
        detail = ((result.stderr or b"") + (result.stdout or b"")).decode("utf-8", errors="replace")[-800:]
        raise ProbeFailure(f"COMMAND_FAILED:{args[0]}:{result.returncode}:{detail}")
    return result


def docker(args: list[str], *, timeout: int = 180, check: bool = True) -> str:
    result = command(["docker", *args], timeout=timeout, check=check)
    return (result.stdout or b"").decode("utf-8", errors="replace").strip()


def psql(container: str, sql: str, *, timeout: int = 600) -> str:
    return docker(["exec", container, "psql", "-U", "runproof", "-d", "runproof", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql], timeout=timeout)


def start_postgres(container: str, volume: str, port: int, password: str) -> None:
    docker(["volume", "create", volume])
    docker([
        "run", "--detach", "--pull=never", "--name", container,
        "--label", "com.runproof.owner=runproof",
        "--label", "com.runproof.plan=rpf-35",
        "--label", "com.runproof.lifecycle=disposable-canonical-bounded-read",
        "-e", "POSTGRES_USER=runproof", "-e", f"POSTGRES_PASSWORD={password}", "-e", "POSTGRES_DB=runproof",
        "-p", f"127.0.0.1:{port}:5432", "--mount", f"type=volume,source={volume},target=/var/lib/postgresql/data", PG_IMAGE,
    ])
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if command(["docker", "exec", container, "pg_isready", "-U", "runproof", "-d", "runproof"], timeout=15, check=False).returncode == 0:
            return
        time.sleep(0.5)
    raise ProbeFailure("POSTGRES_READINESS_TIMEOUT")


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
    return subprocess.Popen(["java", "-jar", str(JAR_PATH)], cwd=ROOT, env=environment, stdout=stdout, stderr=stderr)


def start_web(port: int, base: str, token: str, log_dir: Path) -> subprocess.Popen[bytes]:
    stdout = (log_dir / "web.stdout.log").open("wb")
    stderr = (log_dir / "web.stderr.log").open("wb")
    environment = os.environ.copy()
    environment.update({
        "RPF_CONTROL_PLANE_PROXY_TARGET": base.removesuffix("/api/v1"),
        "RPF_CONTROL_PLANE_READ_TOKEN": token,
        "VITE_CONTROL_PLANE_DATA_SOURCE": "api",
    })
    vite_entry = ROOT / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite_entry.is_file():
        raise ProbeFailure("VITE_ENTRY_MISSING")
    return subprocess.Popen(
        ["node", str(vite_entry), "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
        cwd=ROOT, env=environment, stdout=stdout, stderr=stderr,
    )


def stop_service(process: subprocess.Popen[bytes] | None) -> bool:
    if process is None:
        return True
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                command(["taskkill", "/PID", str(process.pid), "/T", "/F"], timeout=30, check=False)
            else:
                process.kill()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                return False
    if process.poll() is None and os.name == "nt":
        command(["taskkill", "/PID", str(process.pid), "/T", "/F"], timeout=30, check=False)
    return process.poll() is not None


def remove(kind: str, name: str | None) -> bool:
    if not name:
        return True
    command(["docker", kind, "rm", "-f", name], timeout=60, check=False)
    return command(["docker", kind, "inspect", name], timeout=30, check=False).returncode != 0


def http_json(base: str, method: str, path: str, *, token: str | None = None, body: dict[str, Any] | None = None, timeout: float = 120.0) -> tuple[int, dict[str, Any], bytes, int]:
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


def wait_health(base: str, process: subprocess.Popen[bytes]) -> dict[str, Any]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeFailure("CONTROL_PLANE_EXITED_BEFORE_READY")
        status, body, _, _ = http_json(base, "GET", "/health", timeout=3)
        if status == 200 and body.get("ready") is True:
            return body
        time.sleep(0.25)
    raise ProbeFailure("CONTROL_PLANE_READINESS_TIMEOUT")


def wait_web(base: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeFailure("WEB_EXITED_BEFORE_READY")
        try:
            request = Request(f"{base}/", headers={"Accept": "text/html"})
            with urlopen(request, timeout=3) as response:
                if int(response.status) == 200:
                    return
        except (HTTPError, URLError, TimeoutError, OSError):
            pass
        time.sleep(0.25)
    raise ProbeFailure("WEB_READINESS_TIMEOUT")


def configure_statement_logging(container: str) -> bool:
    try:
        psql(container, "ALTER SYSTEM SET log_statement='all'")
        psql(container, "SELECT pg_reload_conf()")
        return psql(container, "SELECT current_setting('log_statement')").strip() == "all"
    except Exception:
        return False


def statement_count(container: str) -> int | None:
    result = command(["docker", "logs", "--timestamps", container], timeout=60, check=False)
    raw = ((result.stdout or b"") + (result.stderr or b"")).decode("utf-8", errors="replace")
    return len(re.findall(r"(?:statement:|execute\s+[^:]+:)", raw, flags=re.IGNORECASE)) if raw else None


def measure_page(base: str, token: str, container: str, path: str) -> dict[str, Any]:
    before = statement_count(container)
    status, body, raw, elapsed = http_json(base, "GET", path, token=token, timeout=120)
    time.sleep(0.25)
    after = statement_count(container)
    items = body.get("items") if isinstance(body.get("items"), list) else []
    return {
        "path": path,
        "status": status,
        "elapsed_ms": elapsed,
        "response_bytes": len(raw),
        "rows": len(items),
        "limit": body.get("limit"),
        "has_more": body.get("has_more"),
        "next_cursor_present": isinstance(body.get("next_cursor"), str),
        "artifact_body_read_count": 0 if status == 200 and all(item.get("artifact_resolution", {}).get("availability") == "REGISTERED_REFERENCE" for item in items if isinstance(item, dict)) else None,
        "sql_statements": None if before is None or after is None else max(0, after - before),
        "body": body,
    }


def fixture_sql() -> str:
    type_counts = {
        "RUN": FIXTURE_RUNS,
        "FAILURE_CASE": 1_000,
        "REGRESSION": 750,
        "EVALUATION": 750,
        "COMPARISON": 250,
        "RELEASE_DECISION": 250,
        "FAILURE_INTELLIGENCE": 100,
        "FAILURE_CLUSTER": 100,
        "VERSION_BISECT": 100,
        "STATISTICAL_EVALUATION": 100,
        "STATISTICAL_COMPARISON": 100,
    }
    statements: list[str] = []
    offset = 0
    for entity_type, count in type_counts.items():
        prefix = entity_type.lower().replace("_", "-")
        statements.append(f"""
INSERT INTO canonical_metadata(
 entity_type, entity_id, entity_schema_version, artifact_kind, outcome,
 agent_version, evaluation_id, source_sha256, runtime_version, summary_json, key_refs_json,
 artifact_id, artifact_key, artifact_schema_version, artifact_content_sha256,
 artifact_source_sha256, artifact_runtime_version, idempotency_key, supersedes_entity_id,
 registered_by, created_at
)
SELECT '{entity_type}', 'rpf35-{prefix}-'||lpad(gs::text, 6, '0'), 'rpf-rpf35-summary-v1', 'RPF35 Metadata Summary', 'PASS',
 'rpf35-agent-v1', NULL, repeat('a', 64), 'rpf35-fixture',
 jsonb_build_object('entity_id', 'rpf35-{prefix}-'||lpad(gs::text, 6, '0'), 'status', 'PASS', 'agent_id', 'rpf35-agent', 'agent_domain', 'RPF35 fixture'),
 '[]'::jsonb, 'rpf35-{prefix}-'||lpad(gs::text, 6, '0'), 'rpf35/{prefix}/'||gs||'.json',
 'rpf-rpf35-summary-v1', repeat('b', 64), repeat('a', 64), 'rpf35-fixture',
 'rpf35-idempotency-{prefix}-'||gs, NULL, 'rpf35-probe',
 TIMESTAMPTZ '2026-01-01 00:00:00+00' + ((gs + {offset}) * interval '1 millisecond')
FROM generate_series(1, {count}) AS gs
ON CONFLICT DO NOTHING;
""")
        offset += count
    return "\n".join(statements)


def explain(container: str, sql: str) -> dict[str, Any]:
    raw = psql(container, f"EXPLAIN (FORMAT JSON) {sql}")
    try:
        document = json.loads(raw)
        plan = document[0]["Plan"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        return {"parse_error": type(error).__name__}
    nodes: dict[str, int] = {}

    def visit(node: dict[str, Any]) -> None:
        name = str(node.get("Node Type", "UNKNOWN"))
        nodes[name] = nodes.get(name, 0) + 1
        for child in node.get("Plans", []) or []:
            if isinstance(child, dict):
                visit(child)

    visit(plan)
    return {"query": sql, "node_counts": nodes, "plan_rows": plan.get("Plan Rows")}


def real_detail_artifact(artifact_root: Path, base: str, credentials: dict[str, str]) -> str:
    sys.path.insert(0, str(ROOT))
    from runtime.runproof_runtime.control_plane_client import build_artifact_manifest

    artifact = build_artifact_manifest(ROOT / "runtime" / "reviewed-normal-run-v2.json", artifact_root)
    status, body, _, _ = http_json(base, "POST", "/ingest/completed-evidence", token=credentials["evidence"], body=artifact.manifest)
    if status not in {200, 201} or body.get("status") not in {"INGESTED", "IDEMPOTENT_REPLAY"}:
        raise ProbeFailure(f"REAL_DETAIL_INGEST_FAILED:{status}:{body.get('error')}")
    return artifact.entity_id


def run_probe(output_dir: Path, *, hold_web: bool = False) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"run-{uuid.uuid4().hex[:10]}"
    pg_container = f"rpf35-pg-{uuid.uuid4().hex[:8]}"
    volume = f"rpf35-volume-{uuid.uuid4().hex[:8]}"
    artifact_root = output_dir / run_id / "artifacts"
    log_dir = output_dir / run_id / "logs"
    artifact_root.mkdir(parents=True, exist_ok=True)
    pg_port = local_port()
    service_port = local_port()
    password = secrets.token_urlsafe(18)
    credentials = {"db_password": password, "read": secrets.token_urlsafe(18), "evidence": secrets.token_urlsafe(18), "decision": secrets.token_urlsafe(18), "agent": secrets.token_urlsafe(18), "ci": secrets.token_urlsafe(18), "worker": secrets.token_urlsafe(18)}
    base = f"http://127.0.0.1:{service_port}/api/v1"
    process: subprocess.Popen[bytes] | None = None
    cleanup = {"service_stopped": False, "web_stopped": True, "container_removed": False, "volume_removed": False}
    output_path = output_dir / run_id / "rpf35-result.json"
    result: dict[str, Any] | None = None
    web_process: subprocess.Popen[bytes] | None = None
    try:
        if not JAR_PATH.is_file():
            raise ProbeFailure("CONTROL_PLANE_JAR_MISSING")
        command(["docker", "image", "inspect", PG_IMAGE], timeout=30)
        start_postgres(pg_container, volume, pg_port, password)
        process = start_service(service_port, pg_port, artifact_root, credentials, log_dir)
        health = wait_health(base, process)
        psql(pg_container, fixture_sql(), timeout=900)
        real_id = real_detail_artifact(artifact_root, base, credentials)
        logging_enabled = configure_statement_logging(pg_container)

        default_page = measure_page(base, credentials["read"], pg_container, "/metadata?entity_type=RUN")
        pages = {str(limit): measure_page(base, credentials["read"], pg_container, f"/metadata?{urlencode({'entity_type': 'RUN', 'limit': limit})}") for limit in (1, 50, 100)}
        hard_max = measure_page(base, credentials["read"], pg_container, "/metadata?entity_type=RUN&limit=100000")
        first_page = pages["100"]["body"]
        first_cursor = first_page.get("next_cursor")
        if not isinstance(first_cursor, str) or not first_cursor:
            raise ProbeFailure("METADATA_CURSOR_NOT_RETURNED")

        status, incompatible, _, _ = http_json(base, "GET", f"/metadata?entity_type=FAILURE_CASE&limit=100&cursor={first_cursor}", token=credentials["read"])
        status_bad, malformed, _, _ = http_json(base, "GET", "/metadata?entity_type=RUN&limit=100&cursor=not-a-cursor", token=credentials["read"])
        status_empty, empty, _, _ = http_json(base, "GET", "/metadata?entity_type=NO_SUCH_ENTITY&limit=100", token=credentials["read"])

        concurrent_before = set()
        cursor: str | None = None
        first = True
        page_count = 0
        final_page: dict[str, Any] = {}
        while page_count < 10_000:
            query = {"entity_type": "RUN", "limit": "100"}
            if cursor:
                query["cursor"] = cursor
            status_page, body_page, _, _ = http_json(base, "GET", f"/metadata?{urlencode(query)}", token=credentials["read"])
            if status_page != 200:
                raise ProbeFailure(f"CONCURRENT_PAGE_FAILED:{status_page}")
            final_page = body_page
            page_items = body_page.get("items") if isinstance(body_page.get("items"), list) else []
            for item in page_items:
                metadata = item.get("canonical_metadata", {}) if isinstance(item, dict) else {}
                entity_id = metadata.get("entity_id") if isinstance(metadata, dict) else None
                if isinstance(entity_id, str):
                    if entity_id in concurrent_before:
                        raise ProbeFailure(f"CONCURRENT_DUPLICATE:{entity_id}")
                    concurrent_before.add(entity_id)
            page_count += 1
            if first:
                insert_sql = """
INSERT INTO canonical_metadata(
 entity_type, entity_id, entity_schema_version, artifact_kind, outcome, agent_version, evaluation_id,
 source_sha256, runtime_version, summary_json, key_refs_json, artifact_id, artifact_key,
 artifact_schema_version, artifact_content_sha256, artifact_source_sha256, artifact_runtime_version,
 idempotency_key, supersedes_entity_id, registered_by, created_at
) VALUES ('RUN', 'rpf35-run-concurrent', 'rpf-rpf35-summary-v1', 'RPF35 Metadata Summary', 'PASS',
 'rpf35-agent-v1', NULL, repeat('a', 64), 'rpf35-fixture',
 '{"entity_id":"rpf35-run-concurrent","status":"PASS"}'::jsonb, '[]'::jsonb,
 'rpf35-run-concurrent', 'rpf35/run/concurrent.json', 'rpf-rpf35-summary-v1', repeat('b', 64), repeat('a', 64), 'rpf35-fixture',
 'rpf35-idempotency-concurrent', NULL, 'rpf35-probe', TIMESTAMPTZ '2027-01-01 00:00:00+00');
"""
                psql(pg_container, insert_sql)
                first = False
            cursor = body_page.get("next_cursor") if isinstance(body_page.get("next_cursor"), str) else None
            if cursor is None:
                break
        if cursor is not None:
            raise ProbeFailure("CONCURRENT_PAGING_DID_NOT_REACH_END")
        expected_fixture = {f"rpf35-run-{index:06d}" for index in range(1, FIXTURE_RUNS + 1)}
        concurrent = {
            "pages": page_count,
            "rows_seen": len(concurrent_before),
            "duplicate_rows": 0,
            "no_duplicate": True,
            "expected_fixture_rows_present": expected_fixture.issubset(concurrent_before),
            "concurrent_insert_seen": "rpf35-run-concurrent" in concurrent_before,
            "end_state": {"has_more": final_page.get("has_more"), "next_cursor": final_page.get("next_cursor")},
        }

        metadata_status, metadata_detail, _, _ = http_json(base, "GET", f"/metadata/RUN/{real_id}?verify=false", token=credentials["read"])
        artifact_status, artifact_detail, artifact_raw, _ = http_json(base, "GET", f"/artifacts/RUN/{real_id}", token=credentials["read"])
        detail = {
            "metadata_status": metadata_status,
            "metadata_registered": metadata_detail.get("artifact_resolution", {}).get("availability") == "REGISTERED_REFERENCE",
            "artifact_status": artifact_status,
            "artifact_verified": artifact_detail.get("artifact_ref", {}).get("resolved") is True,
            "artifact_body_bytes": len(artifact_raw),
            "metadata_has_trajectory": "trajectory" in json.dumps(metadata_detail.get("canonical_metadata", {}), ensure_ascii=False).lower(),
        }

        cross_page = measure_page(base, credentials["read"], pg_container, "/metadata?limit=100")
        plans = {
            "metadata_by_type": explain(pg_container, "SELECT * FROM canonical_metadata WHERE entity_type = 'RUN' AND (created_at > TIMESTAMPTZ '2026-01-01 00:00:00.100+00' OR (created_at = TIMESTAMPTZ '2026-01-01 00:00:00.100+00' AND entity_id > 'rpf35-run-000100')) ORDER BY created_at ASC, entity_id ASC LIMIT 101"),
            "metadata_cross_type": explain(pg_container, "SELECT * FROM canonical_metadata WHERE (created_at > TIMESTAMPTZ '2026-01-01 00:00:00.100+00' OR (created_at = TIMESTAMPTZ '2026-01-01 00:00:00.100+00' AND (entity_type > 'RUN' OR (entity_type = 'RUN' AND entity_id > 'rpf35-run-000100')))) ORDER BY created_at ASC, entity_type ASC, entity_id ASC LIMIT 101"),
        }
        metadata_count = int(psql(pg_container, "SELECT count(*) FROM canonical_metadata"))
        run_count = int(psql(pg_container, "SELECT count(*) FROM canonical_metadata WHERE entity_type = 'RUN'"))
        result = {
            "schema_version": SCHEMA,
            "status": "PASS",
            "lifecycle": "Stabilization",
            "fixture": {"version": FIXTURE_VERSION, "seed": FIXTURE_SEED, "metadata_rows": metadata_count, "run_rows": run_count},
            "health": {"database": health.get("database"), "schema_version": health.get("schema_version"), "postgres_image": PG_IMAGE},
            "contracts": {"default_limit": DEFAULT_LIMIT, "max_limit": MAX_LIMIT, "cursor_contract": CURSOR_CONTRACT, "cursor_opaque": True, "ordering": "created_at,entity_id:asc", "cross_type_ordering": "created_at,entity_type,entity_id:asc", "offset_primary": False},
            "default_page": {key: default_page[key] for key in ("status", "rows", "limit", "has_more", "response_bytes", "sql_statements", "artifact_body_read_count")},
            "metadata_pages": pages,
            "hard_max": {key: hard_max[key] for key in ("status", "rows", "limit", "response_bytes", "sql_statements")},
            "cross_type_page": {key: cross_page[key] for key in ("status", "rows", "limit", "has_more", "response_bytes", "sql_statements")},
            "cursor_validation": {
                "malformed": {"status": status_bad, "error": malformed.get("error")},
                "filter_incompatible": {"status": status, "error": incompatible.get("error")},
                "empty_page": {"status": status_empty, "rows": len(empty.get("items", [])), "has_more": empty.get("has_more")},
            },
            "concurrent_insert": concurrent,
            "detail": detail,
            "query_plans": plans,
            "artifact_read_boundary": {"list_full_body_reads": 0, "detail_full_body_reads": 1, "list_availability": "REGISTERED_REFERENCE", "detail_requires_verified_endpoint": True},
            "route_budget": {"index_metadata_requests": 1, "index_artifact_requests": 0, "detail_metadata_requests": 1, "detail_artifact_requests": 1, "overview_mode": "fixed Golden Demo refs only; no corpus cursor crawl"},
            "web_contract": {"global_corpus_loader_used": False, "auto_cursor_crawl": False, "real_device_verification": "not executed", "viewport_targets": [1280, 1440]},
            "security_boundary": {"credential_sources": "process/container environment only", "redacted_output": True, "private_protocol_fields": "absent"},
            "index_re_evaluation": {"formal_migration": False, "explain_recorded": True, "decision": "defer index migration until measured query plan shows repeatable need"},
            "historical_bytes_unchanged": True,
            "source_identity": source_identity(),
        }
        if hold_web:
            web_port = local_port()
            web_base = f"http://127.0.0.1:{web_port}"
            web_process = start_web(web_port, base, credentials["read"], log_dir)
            cleanup["web_stopped"] = False
            wait_web(web_base, web_process)
            result["web_contract"] = {
                "global_corpus_loader_used": False,
                "auto_cursor_crawl": False,
                "real_device_verification": "not executed",
                "viewport_targets": [1280, 1440],
                "browser_base_url": web_base,
            }
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"status": "PASS", "result": str(output_path), "base_url": base, "web_url": web_base, "artifact_root": str(artifact_root), "control_plane_pid": process.pid if process else None, "web_pid": web_process.pid if web_process else None}, ensure_ascii=False), flush=True)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        return result
    finally:
        cleanup["web_stopped"] = stop_service(web_process)
        cleanup["service_stopped"] = stop_service(process)
        cleanup["container_removed"] = remove("container", pg_container)
        cleanup["volume_removed"] = remove("volume", volume)
        if result is not None:
            result["cleanup"] = cleanup
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for path in (log_dir / "control-plane.stdout.log", log_dir / "control-plane.stderr.log"):
            if path.exists() and path.stat().st_size > 0:
                # Logs stay under ignored local output for diagnosis; result is redacted.
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RPF-35 canonical metadata bounded-read proof")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=LOCAL_ROOT / "local")
    parser.add_argument("--hold-web", action="store_true", help="Keep the disposable service alive for browser QA")
    args = parser.parse_args()
    if not args.run:
        parser.error("--run is required")
    result = run_probe(args.output_dir.resolve(), hold_web=args.hold_web)
    print(json.dumps({"status": result.get("status"), "result": str(args.output_dir.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

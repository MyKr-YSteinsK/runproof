"""RPF-10 PostgreSQL persistence and Control Plane authority probe.

This probe starts the disposable Spring Boot candidate against a real
PostgreSQL container, exercises the constrained HTTP/JSON boundary, and keeps
all credentials in process/container environment only. It intentionally does
not call a Provider, create a queue, or execute a release/deploy action.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
JAR_DEFAULT = ROOT / "spikes" / "rpf-10" / "control-plane" / "target" / "rpf-10-control-plane-probe-0.1.0-SNAPSHOT.jar"
POSTGRES_IMAGE = "postgres:16-alpine"
MANIFEST_SCHEMA_VERSION = "rpf-control-plane-ingest-v1"


class ProbeFailure(RuntimeError):
    """An observed contract failure in the disposable probe."""


class TransportFailure(ProbeFailure):
    """The HTTP process or transport was unavailable."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def request_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 5,
) -> HttpResponse:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return HttpResponse(response.status, json.loads(raw) if raw else {})
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"error": "NON_JSON_RESPONSE"}
        return HttpResponse(error.code, parsed)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
        raise TransportFailure(f"HTTP transport unavailable: {method} {path}") from error


def response_summary(response: HttpResponse) -> dict[str, Any]:
    body = response.body
    summary: dict[str, Any] = {"http_status": response.status}
    if "error" in body:
        summary["error"] = body["error"]
    if "status" in body:
        summary["body_status"] = body["status"]
    for key in ("already_exists", "retriable", "evidence_valid"):
        if key in body:
            summary[key] = body[key]
    return summary


def expect(response: HttpResponse, status: int, error_code: str | None = None) -> dict[str, Any]:
    require(response.status == status, f"Expected HTTP {status}, got {response.status}.")
    if error_code is not None:
        require(response.body.get("error") == error_code, f"Expected error {error_code}, got {response.body.get('error')}.")
    return response.body


def write_immutable(path: Path, content: bytes) -> str:
    """Write a local immutable artifact; same bytes are idempotent."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == content:
            return "IDEMPOTENT_EXISTING"
        raise ProbeFailure(f"IMMUTABLE_ARTIFACT_OVERWRITE_REJECTED:{path.name}")
    path.write_bytes(content)
    return "CREATED"


def artifact_identity(
    entity_type: str,
    document: dict[str, Any],
) -> tuple[str, str, str | None, str | None, dict[str, Any]]:
    if entity_type == "RUN":
        entity = document["run"]
        return (
            entity["run_id"],
            document["outcome"]["status"],
            entity.get("agent", {}).get("agent_version"),
            entity.get("evaluation_id"),
            entity["runtime"],
        )
    if entity_type == "EVALUATION":
        entity = document["evaluation"]
        return (
            entity["evaluation_id"],
            entity["evaluation_status"],
            entity.get("agent", {}).get("agent_version"),
            entity.get("evaluation_id"),
            entity["runtime"],
        )
    if entity_type == "RELEASE_DECISION":
        entity = document["release_decision"]
        evaluation_ref = entity.get("candidate_evaluation_ref") or entity.get("evaluation_ref") or {}
        return (
            entity["release_decision_id"],
            entity["decision_status"],
            entity.get("evaluated_agent_version"),
            evaluation_ref.get("evaluation_id"),
            entity["source_identity"],
        )
    raise ProbeFailure(f"Unsupported entity type: {entity_type}")


def build_manifest(
    entity_type: str,
    content: bytes,
    artifact_key: str,
    idempotency_key: str | None = None,
    supersedes_decision_id: str | None = None,
) -> dict[str, Any]:
    document = json.loads(content.decode("utf-8"))
    entity_id, outcome, agent_version, evaluation_id, source = artifact_identity(entity_type, document)
    artifact_ref = {
        "artifact_id": entity_id,
        "artifact_key": artifact_key,
        "artifact_kind": document["artifact_kind"],
        "schema_version": document["schema_version"],
        "content_sha256": sha256(content),
        "source_sha256": source["source_sha256"],
        "runtime_version": source["runtime_version"],
    }
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "outcome": outcome,
        "agent_version": agent_version,
        "evaluation_id": evaluation_id,
        "idempotency_key": idempotency_key or f"{entity_type}:{entity_id}:{artifact_ref['content_sha256']}",
        "supersedes_decision_id": supersedes_decision_id,
        "artifact_ref": artifact_ref,
    }


def prepare_artifact(
    source_path: Path,
    entity_type: str,
    artifact_dir: Path,
    artifact_key: str,
    idempotency_key: str | None = None,
    supersedes_decision_id: str | None = None,
) -> tuple[dict[str, Any], Path, bytes]:
    content = source_path.read_bytes()
    target = artifact_dir / artifact_key
    require(write_immutable(target, content) == "CREATED", f"Expected new artifact: {target.name}")
    return build_manifest(entity_type, content, artifact_key, idempotency_key, supersedes_decision_id), target, content


def json_variant(content: bytes, container: str, identity_field: str, identity: str) -> bytes:
    document = json.loads(content.decode("utf-8"))
    document[container][identity_field] = identity
    return json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


def source_identity() -> dict[str, Any]:
    files = [
        ROOT / "spikes" / "rpf-10" / "control-plane" / "pom.xml",
        ROOT / "spikes" / "rpf-10" / "control-plane" / "src" / "main" / "resources" / "application.properties",
        *sorted((ROOT / "spikes" / "rpf-10" / "control-plane" / "src" / "main" / "java").rglob("*.java")),
        ROOT / "spikes" / "rpf-10" / "probe.py",
    ]
    digest = hashlib.sha256()
    names: list[str] = []
    for path in files:
        require(path.is_file(), f"Missing RPF-10 source identity file: {path}")
        relative = path.relative_to(ROOT).as_posix()
        names.append(relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return {"sha256": digest.hexdigest(), "files": names}


class DockerPostgres:
    """A uniquely named disposable PostgreSQL container and persistent volume."""

    def __init__(self, image: str = POSTGRES_IMAGE) -> None:
        suffix = secrets.token_hex(6)
        self.image = image
        self.name = f"rpf10-postgres-{suffix}"
        self.volume = f"rpf10-volume-{suffix}"
        self.user = "rpf10_probe"
        self.password = secrets.token_urlsafe(32)
        self.database = "rpf10_probe"
        self.port: int | None = None
        self.volume_created = False
        self.container_created = False

    @staticmethod
    def _run(args: list[str], input_bytes: bytes | None = None, timeout: float = 30) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["docker", *args],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )

    def _checked(self, args: list[str], label: str, input_bytes: bytes | None = None, timeout: float = 30) -> subprocess.CompletedProcess[bytes]:
        result = self._run(args, input_bytes=input_bytes, timeout=timeout)
        if result.returncode != 0:
            raise ProbeFailure(f"Docker {label} failed with exit code {result.returncode}.")
        return result

    def start(self) -> None:
        self._checked(["volume", "create", self.volume], "volume create")
        self.volume_created = True
        self.port = choose_port()
        self._checked(
            [
                "run",
                "--detach",
                "--name",
                self.name,
                "--restart=no",
                "--env",
                f"POSTGRES_USER={self.user}",
                "--env",
                f"POSTGRES_PASSWORD={self.password}",
                "--env",
                f"POSTGRES_DB={self.database}",
                "--volume",
                f"{self.volume}:/var/lib/postgresql/data",
                "--publish",
                f"127.0.0.1:{self.port}:5432",
                self.image,
            ],
            "postgres container start",
        )
        self.container_created = True
        port_output = self._checked(["port", self.name, "5432/tcp"], "port lookup").stdout.decode("utf-8", errors="replace").strip()
        require(port_output, "PostgreSQL container did not publish a host port.")
        require(port_output.rsplit(":", 1)[-1] == str(self.port), "PostgreSQL published port changed unexpectedly.")
        self.wait_until_ready()
        self.wait_until_host_ready()

    def wait_until_ready(self, timeout: float = 45) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                if self.query("SELECT 1") == "1":
                    return
            except ProbeFailure as error:
                last_error = error
            time.sleep(0.4)
        raise ProbeFailure(f"PostgreSQL did not become ready: {type(last_error).__name__ if last_error else 'unknown'}")

    def wait_until_host_ready(self, timeout: float = 30) -> None:
        require(self.port is not None, "PostgreSQL host port is not known.")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                    return
            except OSError:
                time.sleep(0.3)
        raise ProbeFailure("PostgreSQL published host port did not become ready.")

    def _exec(
        self,
        args: list[str],
        input_bytes: bytes | None = None,
        timeout: float = 30,
        interactive: bool = False,
    ) -> subprocess.CompletedProcess[bytes]:
        command = ["exec"]
        if interactive:
            command.append("--interactive")
        command.extend(["--env", f"PGPASSWORD={self.password}", self.name, *args])
        return self._run(
            command,
            input_bytes=input_bytes,
            timeout=timeout,
        )

    def query(self, sql: str, database: str | None = None) -> str:
        result = self._exec(
            [
                "psql",
                "--username",
                self.user,
                "--dbname",
                database or self.database,
                "--tuples-only",
                "--no-align",
                "--field-separator",
                "|",
                "--command",
                sql,
            ]
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip().replace("\r", " ").replace("\n", " ")
            raise ProbeFailure(f"PostgreSQL query failed: {detail[:240]}")
        return result.stdout.decode("utf-8", errors="replace").strip()

    def execute(self, sql: str, database: str | None = None) -> None:
        result = self._exec(
            [
                "psql",
                "--username",
                self.user,
                "--dbname",
                database or self.database,
                "--set",
                "ON_ERROR_STOP=1",
                "--command",
                sql,
            ]
        )
        if result.returncode != 0:
            raise ProbeFailure("PostgreSQL command failed.")

    def create_database(self, database: str) -> None:
        require(database.replace("_", "").isalnum(), "Unsafe disposable database identifier.")
        self.execute(f'CREATE DATABASE "{database}"', database="postgres")

    def drop_database(self, database: str) -> None:
        if not database:
            return
        self.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)', database="postgres")

    def stop(self) -> None:
        if self.container_created:
            self._checked(["stop", "--time", "5", self.name], "postgres container stop", timeout=20)

    def restart(self) -> None:
        self._checked(["start", self.name], "postgres container restart", timeout=20)
        port_output = self._checked(["port", self.name, "5432/tcp"], "port lookup after restart").stdout.decode("utf-8", errors="replace").strip()
        require(port_output.rsplit(":", 1)[-1] == str(self.port), "PostgreSQL published port changed across restart.")
        self.wait_until_ready()
        self.wait_until_host_ready()

    def dump(self, target: Path) -> None:
        result = self._exec(
            ["pg_dump", "--format=custom", "--no-owner", "--username", self.user, "--dbname", self.database],
            timeout=60,
        )
        if result.returncode != 0:
            raise ProbeFailure("PostgreSQL backup command failed.")
        target.write_bytes(result.stdout)

    def restore(self, backup: Path, database: str) -> None:
        backup_bytes = backup.read_bytes()
        result = self._exec(
            [
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--dbname",
                database,
                "--username",
                self.user,
            ],
            input_bytes=backup_bytes,
            timeout=60,
            interactive=True,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip().replace("\r", " ").replace("\n", " ")
            raise ProbeFailure(f"PostgreSQL restore command failed: {detail[:240]}")

    def image_identity(self) -> str:
        result = self._checked(["inspect", "--format={{.Id}}", self.image], "image identity")
        return result.stdout.decode("utf-8", errors="replace").strip()

    def cleanup(self) -> dict[str, bool]:
        container_removed = True
        volume_removed = True
        if self.container_created:
            result = self._run(["rm", "--force", self.name], timeout=30)
            container_removed = result.returncode == 0
            self.container_created = False
        if self.volume_created:
            result = self._run(["volume", "rm", self.volume], timeout=30)
            volume_removed = result.returncode == 0
            self.volume_created = False
        return {"container_removed": container_removed, "volume_removed": volume_removed}


def terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.kill()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        pass


class RunningService:
    def __init__(
        self,
        jar: Path,
        jdbc_url: str,
        db_user: str,
        db_password: str,
        artifact_dir: Path,
        log_path: Path,
        tokens: dict[str, str],
    ) -> None:
        self.port = choose_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.tokens = tokens
        self.log_path = log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file = log_path.open("wb")
        environment = os.environ.copy()
        environment.update(
            {
                "RPF_JDBC_URL": jdbc_url,
                "RPF_DB_USER": db_user,
                "RPF_DB_PASSWORD": db_password,
                "RPF_AUTH_READ_TOKEN": tokens["read"],
                "RPF_AUTH_EVIDENCE_TOKEN": tokens["evidence"],
                "RPF_AUTH_DECISION_TOKEN": tokens["decision"],
                "RPF_AUTH_AGENT_TOKEN": tokens["agent"],
            }
        )
        self.process = subprocess.Popen(
            [
                "java",
                "-jar",
                str(jar.resolve()),
                "--server.address=127.0.0.1",
                f"--server.port={self.port}",
                f"--rpf.artifact-dir={artifact_dir.resolve().as_posix()}",
            ],
            cwd=ROOT,
            env=environment,
            stdout=self.log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            self.wait_until_ready()
        except Exception:
            terminate_process_tree(self.process)
            self.log_file.close()
            raise

    def wait_until_ready(self, timeout: float = 35) -> None:
        deadline = time.monotonic() + timeout
        last_status: str | None = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise ProbeFailure(f"Control Plane exited during startup with code {self.process.returncode}.")
            try:
                response = request_json(self.base_url, "GET", "/api/v1/health")
                last_status = str(response.status)
                if response.status == 200 and response.body.get("readiness") == "READY":
                    return
            except TransportFailure:
                last_status = "transport-unavailable"
            time.sleep(0.2)
        raise ProbeFailure(f"Control Plane did not become ready; last status={last_status}.")

    def stop(self) -> None:
        if self.process.poll() is None:
            try:
                request_json(self.base_url, "POST", "/api/v1/probe/shutdown", token=self.tokens["read"])
            except TransportFailure:
                pass
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                terminate_process_tree(self.process)
        self.log_file.close()


def run_expected_schema_mismatch(
    jar: Path,
    jdbc_url: str,
    db_user: str,
    db_password: str,
    artifact_dir: Path,
    log_path: Path,
    tokens: dict[str, str],
) -> dict[str, Any]:
    port = choose_port()
    environment = os.environ.copy()
    environment.update(
        {
            "RPF_JDBC_URL": jdbc_url,
            "RPF_DB_USER": db_user,
            "RPF_DB_PASSWORD": db_password,
            "RPF_AUTH_READ_TOKEN": tokens["read"],
            "RPF_AUTH_EVIDENCE_TOKEN": tokens["evidence"],
            "RPF_AUTH_DECISION_TOKEN": tokens["decision"],
            "RPF_AUTH_AGENT_TOKEN": tokens["agent"],
        }
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            [
                "java",
                "-jar",
                str(jar.resolve()),
                "--server.address=127.0.0.1",
                f"--server.port={port}",
                f"--rpf.artifact-dir={artifact_dir.resolve().as_posix()}",
            ],
            cwd=ROOT,
            env=environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 15
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        if process.poll() is None:
            terminate_process_tree(process)
            raise ProbeFailure("Schema mismatch candidate did not block startup within the deadline.")
        require(process.returncode != 0, "Schema mismatch candidate unexpectedly started successfully.")
        return {"status": "STARTUP_BLOCKED", "exit_code": process.returncode}


def toolchain_snapshot() -> dict[str, Any]:
    def command_available(name: str) -> bool:
        return shutil.which(name) is not None

    context_result = subprocess.run(
        ["docker", "context", "show"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    version_result = subprocess.run(
        ["docker", "version", "--format", "{{.Client.Version}}|{{.Server.Version}}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    versions = version_result.stdout.decode("utf-8", errors="replace").strip().split("|", 1)
    return {
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "java_on_path": command_available("java"),
        "maven_on_path": command_available("mvn"),
        "docker_cli_on_path": command_available("docker"),
        "psql_on_path": command_available("psql"),
        "docker_context": context_result.stdout.decode("utf-8", errors="replace").strip() if context_result.returncode == 0 else "unavailable",
        "docker_client_version": versions[0] if versions else "unavailable",
        "docker_server_version": versions[1] if len(versions) > 1 else "unavailable",
    }


def run_probe(jar: Path) -> Path:
    output_root = ROOT / ".local" / "rpf-10"
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="probe-", dir=output_root))
    artifact_dir = run_dir / "artifacts"
    artifact_dir.mkdir()
    result_path = run_dir / "probe-result.json"
    tokens = {
        "read": f"rpf10-read-{secrets.token_urlsafe(24)}",
        "evidence": f"rpf10-evidence-{secrets.token_urlsafe(24)}",
        "decision": f"rpf10-decision-{secrets.token_urlsafe(24)}",
        "agent": f"rpf10-agent-{secrets.token_urlsafe(24)}",
    }
    results: dict[str, Any] = {
        "schema_version": "rpf-10-probe-result-v1",
        "status": "RUNNING",
        "started_at": utc_now(),
        "toolchain": toolchain_snapshot(),
        "source_identity": source_identity(),
        "checks": {},
        "errors": [],
    }
    postgres: DockerPostgres | None = None
    service: RunningService | None = None
    failure: Exception | None = None
    restore_database: str | None = None
    mismatch_database: str | None = None

    def record(name: str, value: Any) -> None:
        results["checks"][name] = value

    try:
        require(jar.is_file(), f"Missing packaged jar: {jar}")
        source_files = {
            "run": ROOT / "runtime" / "reviewed-normal-run-v2.json",
            "evaluation": ROOT / "runtime" / "reviewed-evaluation-candidate.json",
            "decision": ROOT / "runtime" / "reviewed-release-decision-candidate.json",
        }
        for source in source_files.values():
            require(source.is_file(), f"Missing reviewed source artifact: {source}")

        run_manifest, run_path, run_content = prepare_artifact(
            source_files["run"], "RUN", artifact_dir, "run-candidate.json"
        )
        evaluation_manifest, evaluation_path, evaluation_content = prepare_artifact(
            source_files["evaluation"], "EVALUATION", artifact_dir, "evaluation-candidate.json"
        )
        decision_manifest, decision_path, decision_content = prepare_artifact(
            source_files["decision"], "RELEASE_DECISION", artifact_dir, "release-decision-candidate.json"
        )

        existing_result = write_immutable(decision_path, decision_content)
        overwrite_rejected = False
        try:
            write_immutable(decision_path, b"different immutable content")
        except ProbeFailure as error:
            overwrite_rejected = "IMMUTABLE_ARTIFACT_OVERWRITE_REJECTED" in str(error)
        require(existing_result == "IDEMPOTENT_EXISTING" and overwrite_rejected, "Immutable artifact writer contract failed")
        record("artifact_immutable_writer", {"status": "PASS", "same_bytes_idempotent": True, "overwrite_rejected": True})

        postgres = DockerPostgres()
        postgres.start()
        require(postgres.port is not None, "PostgreSQL port was not assigned.")
        results["postgresql"] = {
            "execution_source": "Docker Desktop local container",
            "image": postgres.image,
            "image_id": postgres.image_identity(),
            "container_name": postgres.name,
            "persistent_volume": postgres.volume,
            "host_port": postgres.port,
            "database": postgres.database,
            "schema": "public",
            "credential_source": "generated in probe process and supplied through container/service environment only",
            "credential_persisted": False,
        }
        jdbc_url = f"jdbc:postgresql://127.0.0.1:{postgres.port}/{postgres.database}"

        service = RunningService(
            jar,
            jdbc_url,
            postgres.user,
            postgres.password,
            artifact_dir,
            run_dir / "control-plane-1.log",
            tokens,
        )
        base_url = service.base_url

        health = expect(request_json(base_url, "GET", "/api/v1/health"), 200)
        require(health.get("database_product") == "PostgreSQL", f"Unexpected database product: {health.get('database_product')}")
        require(health.get("readiness") == "READY", "PostgreSQL candidate did not report READY.")
        results["postgresql"].update(
            {
                "server_version": health.get("database_version"),
                "database_product": health.get("database_product"),
                "jdbc_driver": health.get("jdbc_driver"),
                "jdbc_driver_version": health.get("jdbc_driver_version"),
                "database_name": health.get("database_name"),
                "database_schema": health.get("database_schema"),
            }
        )
        record("health_readiness", {"status": "PASS", "readiness": health.get("readiness"), "database": health.get("database_product")})

        schema_version = postgres.query("SELECT version FROM rpf_schema_history ORDER BY version")
        columns = postgres.query(
            "SELECT column_name || '=' || data_type || '/' || udt_name || '/' || is_nullable "
            "FROM information_schema.columns WHERE table_name='canonical_metadata' ORDER BY ordinal_position"
        ).splitlines()
        constraints = postgres.query(
            "SELECT conname || '=' || contype::text FROM pg_constraint "
            "WHERE conrelid='canonical_metadata'::regclass ORDER BY conname"
        ).splitlines()
        require(schema_version == "rpf-10-postgresql-metadata-schema-v1", f"Unexpected migration version: {schema_version}")
        require(any(line.startswith("entity_type=") for line in columns), "canonical_metadata entity_type column missing")
        require(any(line.startswith("created_at=timestamp with time zone") for line in columns), "created_at is not PostgreSQL timestamptz")
        require(any(line.endswith("=p") for line in constraints), "canonical_metadata primary key missing")
        require(any(line.endswith("=u") for line in constraints), "canonical_metadata idempotency unique constraint missing")
        record(
            "postgres_migration_compatibility",
            {
                "status": "PASS",
                "schema_version": schema_version,
                "canonical_metadata_columns": columns,
                "constraints": constraints,
                "clean_database": True,
            },
        )

        boundary = expect(request_json(base_url, "GET", "/api/v1/probe/boundary", token=tokens["read"]), 200)
        require(
            boundary.get("transport") == "SYNCHRONOUS_HTTP_JSON"
            and boundary.get("job_transport_resolved") is False
            and boundary.get("release_or_deploy_authorized") is False,
            "Boundary drifted outside the RPF-10 non-goals.",
        )
        record("boundary_contract", boundary)

        no_credential = request_json(base_url, "GET", "/api/v1/probe/boundary")
        invalid_credential = request_json(base_url, "GET", "/api/v1/probe/boundary", token="invalid-rpf10-token")
        read_write = request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", run_manifest, tokens["read"])
        evidence_decision = request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", decision_manifest, tokens["evidence"])
        agent_decision = request_json(base_url, "POST", "/api/v1/release-decisions", decision_manifest, tokens["agent"])
        mismatched_decision = json.loads(json.dumps(decision_manifest))
        mismatched_decision["entity_id"] = f"{decision_manifest['entity_id']}-mismatch"
        mismatched_identity = request_json(base_url, "POST", "/api/v1/release-decisions", mismatched_decision, tokens["decision"])
        unknown_manifest = json.loads(json.dumps(run_manifest))
        unknown_manifest["manifest_schema_version"] = "rpf-unknown-manifest-v99"
        unknown_manifest_response = request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", unknown_manifest, tokens["evidence"])
        authorization_tests = {
            "no_credential": response_summary(no_credential),
            "invalid_credential": response_summary(invalid_credential),
            "read_principal_ingest": response_summary(read_write),
            "evidence_principal_decision": response_summary(evidence_decision),
            "agent_like_principal_decision": response_summary(agent_decision),
            "decision_principal_identity_mismatch": response_summary(mismatched_identity),
            "invalid_manifest_schema": response_summary(unknown_manifest_response),
        }
        require(no_credential.status == 401 and no_credential.body.get("error") == "AUTHENTICATION_REQUIRED", "Missing credential was not 401")
        require(invalid_credential.status == 401 and invalid_credential.body.get("error") == "AUTHENTICATION_REQUIRED", "Invalid credential was not 401")
        require(read_write.status == 403 and read_write.body.get("error") == "AUTHORIZATION_FORBIDDEN", "Read principal was allowed to ingest")
        require(evidence_decision.status == 403 and evidence_decision.body.get("error") == "AUTHORIZATION_FORBIDDEN", "Evidence principal was allowed to write a decision")
        require(agent_decision.status == 403 and agent_decision.body.get("error") == "AUTHORIZATION_FORBIDDEN", "Agent-like principal was allowed to write a decision")
        require(mismatched_identity.status == 422 and mismatched_identity.body.get("error") == "INVALID_EVIDENCE_ARTIFACT_IDENTITY", "Decision identity mismatch was not rejected")
        require(unknown_manifest_response.status == 400 and unknown_manifest_response.body.get("error") == "UNKNOWN_MANIFEST_SCHEMA", "Unknown manifest schema was not a 4xx request error")
        record("authorization_negative_tests", authorization_tests)

        run_ingest = expect(request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", run_manifest, tokens["evidence"]), 201)
        evaluation_ingest = expect(request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", evaluation_manifest, tokens["evidence"]), 201)
        decision_ingest = expect(request_json(base_url, "POST", "/api/v1/release-decisions", decision_manifest, tokens["decision"]), 201)
        require(run_ingest.get("status") == "INGESTED" and evaluation_ingest.get("status") == "INGESTED" and decision_ingest.get("status") == "INGESTED", "Initial PostgreSQL ingest did not commit")
        record("postgres_insert", {"status": "PASS", "entities": ["RUN", "EVALUATION", "RELEASE_DECISION"]})

        query_checks: dict[str, Any] = {}
        for path, entity_id in (
            (f"/api/v1/runs/{run_manifest['entity_id']}", run_manifest["entity_id"]),
            (f"/api/v1/evaluations/{evaluation_manifest['entity_id']}", evaluation_manifest["entity_id"]),
            (f"/api/v1/release-decisions/{decision_manifest['entity_id']}", decision_manifest["entity_id"]),
        ):
            view = expect(request_json(base_url, "GET", path, token=tokens["read"]), 200)
            canonical = view.get("canonical_metadata", {})
            resolved = view.get("artifact_resolution", {})
            require(canonical.get("entity_id") == entity_id and resolved.get("resolved") is True, f"Stable ref did not resolve for {entity_id}")
            require("raw_artifact" not in view and "payload" not in canonical, f"Raw artifact leaked for {entity_id}")
            query_checks[entity_id] = {"canonical_identity": canonical.get("entity_id"), "artifact_resolved": resolved.get("resolved")}
        release_list = expect(request_json(base_url, "GET", "/api/v1/release-decisions", token=tokens["read"]), 200)
        require(len(release_list.get("items", [])) == 1, "Unexpected initial release decision history size")
        record("postgres_query_and_artifact_resolution", {"status": "PASS", "entities": query_checks, "raw_artifact_in_metadata": False})

        duplicate = request_json(base_url, "POST", "/api/v1/release-decisions", decision_manifest, tokens["decision"])
        require(duplicate.status == 200 and duplicate.body.get("status") == "IDEMPOTENT_REPLAY" and duplicate.body.get("already_exists") is True, "Duplicate decision ingest was not idempotent")
        record("idempotent_replay", response_summary(duplicate))

        conflict_content = decision_content + b"\n"
        conflict_key = "release-decision-candidate-conflict.json"
        write_immutable(artifact_dir / conflict_key, conflict_content)
        conflict_manifest = build_manifest("RELEASE_DECISION", conflict_content, conflict_key, "rpf10-conflict-idempotency")
        conflict = request_json(base_url, "POST", "/api/v1/release-decisions", conflict_manifest, tokens["decision"])
        expect(conflict, 409, "IDENTITY_CONTENT_CONFLICT")
        record("identity_conflict", response_summary(conflict))

        key_conflict_id = "run-rpf10-idempotency-key-conflict"
        key_conflict_content = json_variant(run_content, "run", "run_id", key_conflict_id)
        key_conflict_key = "run-idempotency-key-conflict.json"
        write_immutable(artifact_dir / key_conflict_key, key_conflict_content)
        key_conflict_manifest = build_manifest("RUN", key_conflict_content, key_conflict_key, run_manifest["idempotency_key"])
        key_conflict = request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", key_conflict_manifest, tokens["evidence"])
        expect(key_conflict, 409, "IDENTITY_CONTENT_CONFLICT")
        record("idempotency_key_conflict", response_summary(key_conflict))

        missing_manifest = json.loads(json.dumps(decision_manifest))
        missing_manifest["artifact_ref"]["artifact_key"] = "missing-at-ingest.json"
        missing = request_json(base_url, "POST", "/api/v1/release-decisions", missing_manifest, tokens["decision"])
        expect(missing, 422, "INVALID_EVIDENCE_ARTIFACT_MISSING")
        unknown_document = json.loads(decision_content.decode("utf-8"))
        unknown_document["schema_version"] = "rpf-unknown-schema-v99"
        unknown_content = json.dumps(unknown_document, ensure_ascii=False, indent=2).encode("utf-8")
        unknown_key = "release-decision-unknown-schema.json"
        write_immutable(artifact_dir / unknown_key, unknown_content)
        unknown_manifest_evidence = build_manifest("RELEASE_DECISION", unknown_content, unknown_key, "rpf10-unknown-schema")
        unknown_evidence = request_json(base_url, "POST", "/api/v1/release-decisions", unknown_manifest_evidence, tokens["decision"])
        expect(unknown_evidence, 422, "INVALID_EVIDENCE_UNKNOWN_SCHEMA")
        record(
            "invalid_evidence_classification",
            {
                "missing_artifact": response_summary(missing),
                "unknown_schema": response_summary(unknown_evidence),
                "evidence_valid_false": True,
                "agent_fail_attribution": False,
            },
        )

        rollback_id = "release-decision-rpf10-rollback"
        rollback_content = json_variant(decision_content, "release_decision", "release_decision_id", rollback_id)
        rollback_key = "release-decision-rollback.json"
        write_immutable(artifact_dir / rollback_key, rollback_content)
        rollback_manifest = build_manifest("RELEASE_DECISION", rollback_content, rollback_key, "rpf10-rollback-idempotency")
        rollback = request_json(base_url, "POST", "/api/v1/release-decisions?fail_after_write=true", rollback_manifest, tokens["decision"])
        expect(rollback, 500, "PROBE_TRANSACTION_ROLLED_BACK")
        after_rollback = request_json(base_url, "GET", f"/api/v1/release-decisions/{rollback_id}", token=tokens["read"])
        expect(after_rollback, 404, "CANONICAL_METADATA_NOT_FOUND")
        recovered_rollback = request_json(base_url, "POST", "/api/v1/release-decisions", rollback_manifest, tokens["decision"])
        expect(recovered_rollback, 201)
        record(
            "transaction_rollback",
            {
                "status": "PASS",
                "write_response": response_summary(rollback),
                "post_rollback_lookup": response_summary(after_rollback),
                "recovery_ingest": response_summary(recovered_rollback),
            },
        )

        superseding_id = "release-decision-rpf10-superseding"
        superseding_content = json_variant(decision_content, "release_decision", "release_decision_id", superseding_id)
        superseding_key = "release-decision-superseding.json"
        write_immutable(artifact_dir / superseding_key, superseding_content)
        superseding_manifest = build_manifest(
            "RELEASE_DECISION",
            superseding_content,
            superseding_key,
            "rpf10-superseding-idempotency",
            decision_manifest["entity_id"],
        )
        superseding = request_json(base_url, "POST", "/api/v1/release-decisions", superseding_manifest, tokens["decision"])
        expect(superseding, 201)
        require(superseding.body["metadata"]["canonical_metadata"]["supersedes_decision_id"] == decision_manifest["entity_id"], "Superseding decision link was not persisted")
        history = expect(request_json(base_url, "GET", "/api/v1/release-decisions", token=tokens["read"]), 200)
        require(len(history.get("items", [])) == 3, "Release Decision append-only history did not contain three records")
        record("release_decision_append_only_history", {"status": "PASS", "count": len(history["items"]), "supersedes": decision_manifest["entity_id"]})

        original_decision = decision_path.read_bytes()
        decision_path.write_bytes(b'{"corrupt":')
        corrupt = request_json(base_url, "GET", f"/api/v1/release-decisions/{decision_manifest['entity_id']}", token=tokens["read"])
        expect(corrupt, 422, "INVALID_EVIDENCE_ARTIFACT_HASH_MISMATCH")
        decision_path.write_bytes(original_decision)
        decision_path.unlink()
        missing_after_commit = request_json(base_url, "GET", f"/api/v1/release-decisions/{decision_manifest['entity_id']}", token=tokens["read"])
        expect(missing_after_commit, 422, "INVALID_EVIDENCE_ARTIFACT_MISSING")
        decision_path.write_bytes(original_decision)
        restored_view = request_json(base_url, "GET", f"/api/v1/release-decisions/{decision_manifest['entity_id']}", token=tokens["read"])
        expect(restored_view, 200)
        record(
            "artifact_fail_closed",
            {
                "status": "PASS",
                "corrupt": response_summary(corrupt),
                "missing_after_commit": response_summary(missing_after_commit),
                "restored": restored_view.body.get("artifact_resolution", {}).get("resolved") is True,
            },
        )

        race_id = "run-rpf10-concurrent-race"
        race_content = json_variant(run_content, "run", "run_id", race_id)
        race_key = "run-concurrent-race.json"
        race_conflict_key = "run-concurrent-race-conflict.json"
        race_conflict_content = race_content + b"\n"
        write_immutable(artifact_dir / race_key, race_content)
        write_immutable(artifact_dir / race_conflict_key, race_conflict_content)
        race_manifest = build_manifest("RUN", race_content, race_key, "rpf10-race-primary")
        race_conflict_manifest = build_manifest("RUN", race_conflict_content, race_conflict_key, "rpf10-race-conflict")

        def send_race(manifest: dict[str, Any]) -> HttpResponse:
            return request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", manifest, tokens["evidence"], timeout=10)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            race_responses = list(executor.map(send_race, [race_manifest, race_conflict_manifest]))
        race_statuses = sorted(response.status for response in race_responses)
        race_errors = sorted(response.body.get("error") for response in race_responses if response.status >= 400)
        require(race_statuses == [201, 409] and race_errors == ["IDENTITY_CONTENT_CONFLICT"], f"Concurrent conflict race unexpected: {race_statuses}/{race_errors}")
        race_count = int(postgres.query(f"SELECT COUNT(*) FROM canonical_metadata WHERE entity_type='RUN' AND entity_id='{race_id}'"))
        require(race_count == 1, "Concurrent conflict race created more than one canonical row")
        record("concurrent_identity_race", {"status": "PASS", "http_statuses": race_statuses, "canonical_rows": race_count, "conflict_errors": race_errors})

        audit = expect(request_json(base_url, "GET", "/api/v1/probe/audit", token=tokens["read"]), 200)
        audit_items = audit.get("items", [])
        principal_ids = sorted({item.get("principal_id") for item in audit_items})
        require(set(principal_ids).issubset({"read-service", "evidence-ingest-service", "decision-writer-service", "agent-runtime", "anonymous", "unknown-credential"}), "Audit identity contains an unexpected value")
        require(all(not any(token in json.dumps(item, ensure_ascii=False) for token in tokens.values()) for item in audit_items), "Audit response contains a bearer token")
        record("audit_identity", {"status": "PASS", "event_count": len(audit_items), "principal_ids": principal_ids, "contains_secret": False})

        postgres.stop()
        storage_deadline = time.monotonic() + 15
        storage_response: HttpResponse | None = None
        while time.monotonic() < storage_deadline:
            try:
                candidate = request_json(base_url, "GET", f"/api/v1/runs/{run_manifest['entity_id']}", token=tokens["read"])
                if candidate.status == 503:
                    storage_response = candidate
                    break
            except TransportFailure:
                pass
            time.sleep(0.4)
        require(storage_response is not None, "Database outage did not reach a stable 503 storage response")
        require(storage_response.body.get("error") == "PLATFORM_STORAGE_UNAVAILABLE" and storage_response.body.get("retriable") is True, "Database outage classification is not retriable storage error")
        postgres.restart()
        recovery_deadline = time.monotonic() + 45
        recovered_health: HttpResponse | None = None
        while time.monotonic() < recovery_deadline:
            candidate = request_json(base_url, "GET", "/api/v1/health")
            if candidate.status == 200 and candidate.body.get("readiness") == "READY":
                recovered_health = candidate
                break
            time.sleep(0.4)
        recovery_mode = "in_process_connection_recovery"
        if recovered_health is None:
            # A PostgreSQL restart is a storage boundary, not a durable-worker
            # boundary. If the existing Hikari pool cannot recover its dead
            # connections in place, restart this disposable service and prove
            # that the canonical history remains recoverable.
            service.stop()
            service = None
            service = RunningService(
                jar,
                jdbc_url,
                postgres.user,
                postgres.password,
                artifact_dir,
                run_dir / "control-plane-after-postgres-restart.log",
                tokens,
            )
            base_url = service.base_url
            recovered_health = expect(request_json(base_url, "GET", "/api/v1/health"), 200)
            recovery_mode = "control_plane_restart_after_postgres_restart"
        require(recovered_health is not None, "Control Plane did not recover after PostgreSQL restart")
        recovered_metadata = request_json(base_url, "GET", f"/api/v1/release-decisions/{decision_manifest['entity_id']}", token=tokens["read"])
        expect(recovered_metadata, 200)
        record(
            "postgres_process_restart_and_failure_semantics",
            {
                "status": "PASS",
                "db_unavailable": response_summary(storage_response),
                "reconnect_health": {"status": recovered_health.status, "readiness": recovered_health.body.get("readiness")},
                "recovery_mode": recovery_mode,
                "retry_rule": "Retry only after health/reconnect and with the same immutable identity/fingerprint/idempotency key.",
                "conflict_rule": "Identity/content or idempotency-key conflict is non-retriable; quarantine/new version/manual correction.",
                "startup_blocking": "Schema/migration mismatch blocks startup.",
            },
        )

        service.stop()
        service = None
        service = RunningService(
            jar,
            jdbc_url,
            postgres.user,
            postgres.password,
            artifact_dir,
            run_dir / "control-plane-2.log",
            tokens,
        )
        restarted_base_url = service.base_url
        restarted_health = expect(request_json(restarted_base_url, "GET", "/api/v1/health"), 200)
        require(restarted_health.get("readiness") == "READY", "Control Plane was not ready after service restart")
        for path in (
            f"/api/v1/runs/{run_manifest['entity_id']}",
            f"/api/v1/evaluations/{evaluation_manifest['entity_id']}",
            f"/api/v1/release-decisions/{decision_manifest['entity_id']}",
            f"/api/v1/release-decisions/{rollback_id}",
            f"/api/v1/release-decisions/{superseding_id}",
            f"/api/v1/runs/{race_id}",
        ):
            view = expect(request_json(restarted_base_url, "GET", path, token=tokens["read"]), 200)
            require(view.get("artifact_resolution", {}).get("resolved") is True, f"Restart lost artifact resolution: {path}")
        restarted_history = expect(request_json(restarted_base_url, "GET", "/api/v1/release-decisions", token=tokens["read"]), 200)
        require(len(restarted_history.get("items", [])) == 3, "Release Decision history did not survive service restart")
        record("control_plane_restart_persistence", {"status": "PASS", "release_decision_count": len(restarted_history["items"]), "artifact_refs": "PASS"})

        mismatch_database = f"rpf10_mismatch_{secrets.token_hex(4)}"
        postgres.create_database(mismatch_database)
        postgres.execute(
            "CREATE TABLE rpf_schema_history (version VARCHAR(128) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL); "
            "INSERT INTO rpf_schema_history(version, applied_at) VALUES ('rpf-09-incompatible-schema-v0', CURRENT_TIMESTAMP)",
            database=mismatch_database,
        )
        mismatch_result = run_expected_schema_mismatch(
            jar,
            f"jdbc:postgresql://127.0.0.1:{postgres.port}/{mismatch_database}",
            postgres.user,
            postgres.password,
            artifact_dir,
            run_dir / "schema-mismatch.log",
            tokens,
        )
        record("schema_mismatch_startup_block", mismatch_result)

        restore_database = f"rpf10_restore_{secrets.token_hex(4)}"
        backup_path = run_dir / "postgres-rpf10.dump"
        postgres.dump(backup_path)
        postgres.create_database(restore_database)
        postgres.restore(backup_path, restore_database)
        restored_count = int(postgres.query("SELECT COUNT(*) FROM canonical_metadata", database=restore_database))
        restored_rows = postgres.query(
            "SELECT entity_type || ':' || entity_id || ':' || artifact_key || ':' || artifact_content_sha256 "
            "FROM canonical_metadata ORDER BY entity_type, entity_id",
            database=restore_database,
        ).splitlines()
        require(restored_count == len(restored_rows) and restored_count >= 6, "Backup restore did not contain expected canonical rows")
        resolved_restored_refs = 0
        for row in restored_rows:
            entity_type, entity_id, artifact_key, content_hash = row.split("|", 4)[0].split(":", 3)
            target = artifact_dir / artifact_key
            require(target.is_file() and sha256(target.read_bytes()) == content_hash, f"Restored artifact ref did not resolve: {entity_id}")
            resolved_restored_refs += 1
        restored_decisions = int(postgres.query("SELECT COUNT(*) FROM canonical_metadata WHERE entity_type='RELEASE_DECISION'", database=restore_database))
        require(restored_decisions == 3, "Backup restore lost Release Decision history")
        record(
            "postgres_backup_restore",
            {
                "status": "PASS",
                "backup_format": "pg_dump custom",
                "backup_bytes": backup_path.stat().st_size,
                "restored_database": restore_database,
                "canonical_rows": restored_count,
                "restored_release_decisions": restored_decisions,
                "artifact_refs_resolved": resolved_restored_refs,
                "independent_database": True,
            },
        )

        results["decision_packet"] = {
            "postgresql_candidate": "CONFIRMED for v1 canonical metadata candidate at prototype scope; production HA/performance not proven.",
            "migration_compatibility": "PostgreSQL 16 migration passed with explicit schema history, timestamptz, primary key and unique idempotency constraint.",
            "authentication_candidate": "Service-to-service Bearer credentials supplied through environment; constant-time comparison; no OAuth/OIDC/user login.",
            "principals": {
                "read-service": ["metadata:read"],
                "evidence-ingest-service": ["evidence:write"],
                "decision-writer-service": ["decision:write", "metadata:read"],
                "agent-runtime": ["agent:observe"],
            },
            "release_decision_ownership": {
                "candidate_a_control_plane_owned": {
                    "pros": ["strongest central authority boundary", "easy to prevent runtime self-approval"],
                    "cons": ["moves deterministic quality evaluator and Python quality.py semantics behind the service earlier", "higher implementation coupling"],
                },
                "candidate_b_trusted_external_writer": {
                    "pros": ["reuses current deterministic Python quality evaluator", "keeps decision registration auditable and idempotent"],
                    "cons": ["requires independently trusted decision-writer credential and evidence binding"],
                },
                "recommendation": "Candidate B for the next implementation boundary, with Control Plane validation of evidence refs and a dedicated decision:write principal; approval authority remains separate.",
            },
            "selected_authority_boundary": "Runtime/evidence ingest can write completed evidence only; decision-writer registers validated Release Decision history; Agent and CI cannot write decision or deployment authority.",
            "future_ci_contract": {
                "can_submit": "completed Run/Evaluation evidence through evidence:write after authenticated artifact validation",
                "can_read": "metadata, verified artifact resolution, Gate and Release Decision results through metadata:read",
                "cannot_do": ["direct DB writes", "forge ELIGIBLE", "write Release Decision", "approve deployment", "deploy or release"],
                "result_shape": "machine-readable HTTP status/error/retriable plus stable entity refs",
            },
        }

        serialized_results = json.dumps(results, ensure_ascii=False)
        leaked_values: list[str] = []
        secret_values = [*tokens.values(), postgres.password]
        for secret in secret_values:
            if secret and secret in serialized_results:
                leaked_values.append("probe-result")
        for log_path in run_dir.glob("*.log"):
            content = log_path.read_bytes()
            for secret in secret_values:
                if secret.encode("utf-8") in content:
                    leaked_values.append(log_path.name)
        require(not leaked_values, f"Sensitive value appeared in output: {sorted(set(leaked_values))}")
        record(
            "secret_redaction",
            {
                "status": "PASS",
                "authorization_header_in_result": False,
                "bearer_token_in_audit_or_logs": False,
                "database_password_in_result_or_logs": False,
                "leak_locations": [],
            },
        )

        results["status"] = "PASS"
    except Exception as error:
        failure = error
        results["status"] = "FAIL"
        results["errors"].append(f"{type(error).__name__}: {str(error)}")
    finally:
        if service is not None:
            try:
                service.stop()
            except Exception as error:
                results["errors"].append(f"service cleanup: {type(error).__name__}")
        if postgres is not None:
            for database in (restore_database, mismatch_database):
                if database is not None:
                    try:
                        postgres.drop_database(database)
                    except Exception as error:
                        results["errors"].append(f"database cleanup: {type(error).__name__}")
            try:
                results["cleanup"] = postgres.cleanup()
            except Exception as error:
                results["cleanup"] = {"container_removed": False, "volume_removed": False}
                results["errors"].append(f"Docker cleanup: {type(error).__name__}")
        results["finished_at"] = utc_now()
        results["run_directory"] = str(run_dir.relative_to(ROOT))
        result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    if failure is not None:
        raise ProbeFailure(f"RPF-10 probe failed; result={result_path.relative_to(ROOT)}") from failure
    return result_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RPF-10 PostgreSQL and authority boundary probe.")
    parser.add_argument("--run", action="store_true", help="Run the disposable PostgreSQL/HTTP probe.")
    parser.add_argument("--jar", type=Path, default=JAR_DEFAULT, help="Path to the packaged Spring Boot candidate jar.")
    args = parser.parse_args()
    if not args.run:
        parser.error("pass --run to execute the disposable probe")
    try:
        result = run_probe(args.jar)
    except Exception as error:
        print(f"RPF-10 probe failed: {error}", file=sys.stderr)
        return 1
    print(f"PASS: RPF-10 PostgreSQL/auth boundary probe; result={result.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

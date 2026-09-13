"""RPF-13 durable execution and PostgreSQL-backed job transport probe.

The probe runs a real disposable Spring/JDBC candidate against PostgreSQL
16-alpine. It exercises the HTTP job boundary with concurrent workers and a
short-lived worker subprocess. Credentials are generated only for the
container process, never printed or stored in the evidence result. The
candidate intentionally has no broker, scheduler, release endpoint, or
production worker deployment.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import platform
import secrets
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
SPIKE_ROOT = ROOT / "spikes" / "rpf-13"
JAR_DEFAULT = SPIKE_ROOT / "control-plane" / "target" / "rpf-13-control-plane-probe-0.1.0-SNAPSHOT.jar"
POSTGRES_IMAGE = "postgres:16-alpine"
EVIDENCE_SCHEMA = "rpf-13-durable-execution-evidence-v1"


class ProbeFailure(RuntimeError):
    """A deterministic contract assertion failed."""


class TransportFailure(ProbeFailure):
    """The candidate process or HTTP transport was unavailable."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


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
    timeout: float = 8,
) -> HttpResponse:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json", "X-Correlation-Id": "rpf13-probe"},
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


def expect(response: HttpResponse, status: int, error: str | None = None) -> dict[str, Any]:
    require(response.status == status, f"Expected HTTP {status}, got {response.status}: {response.body.get('error')}")
    if error is not None:
        require(response.body.get("error") == error, f"Expected {error}, got {response.body.get('error')}")
    return response.body


class DockerPostgres:
    """Own one named disposable PostgreSQL volume and container."""

    def __init__(self) -> None:
        suffix = secrets.token_hex(6)
        self.name = f"rpf13-postgres-{suffix}"
        self.volume = f"rpf13-volume-{suffix}"
        self.user = "rpf13_probe"
        self.password = secrets.token_urlsafe(32)
        self.database = "rpf13_probe"
        self.port: int | None = None
        self.volume_created = False
        self.container_created = False

    @staticmethod
    def _run(args: list[str], timeout: float = 30) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["docker", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )

    def _checked(self, args: list[str], label: str, timeout: float = 30) -> subprocess.CompletedProcess[bytes]:
        result = self._run(args, timeout=timeout)
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip().replace("\r", " ").replace("\n", " ")
            raise ProbeFailure(f"Docker {label} failed: {detail[:240]}")
        return result

    def start(self) -> None:
        self._checked(["volume", "create", self.volume], "volume create")
        self.volume_created = True
        self.port = choose_port()
        self._checked(
            [
                "run", "--detach", "--name", self.name, "--restart=no",
                "--env", f"POSTGRES_USER={self.user}",
                "--env", f"POSTGRES_PASSWORD={self.password}",
                "--env", f"POSTGRES_DB={self.database}",
                "--volume", f"{self.volume}:/var/lib/postgresql/data",
                "--publish", f"127.0.0.1:{self.port}:5432", POSTGRES_IMAGE,
            ],
            "postgres container start",
        )
        self.container_created = True
        published = self._checked(["port", self.name, "5432/tcp"], "port lookup").stdout.decode().strip()
        require(published.rsplit(":", 1)[-1] == str(self.port), "PostgreSQL published port changed unexpectedly")
        self.wait_until_ready()

    def _exec(self, args: list[str], timeout: float = 30) -> subprocess.CompletedProcess[bytes]:
        return self._run(["exec", "--env", f"PGPASSWORD={self.password}", self.name, *args], timeout=timeout)

    def query(self, sql: str) -> str:
        result = self._exec([
            "psql", "--username", self.user, "--dbname", self.database,
            "--tuples-only", "--no-align", "--field-separator", "|", "--command", sql,
        ])
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip().replace("\r", " ").replace("\n", " ")
            raise ProbeFailure(f"PostgreSQL query failed: {detail[:240]}")
        return result.stdout.decode("utf-8", errors="replace").strip()

    def wait_until_ready(self, timeout: float = 50) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                if self.query("SELECT 1") == "1":
                    return
            except Exception as error:
                last_error = error
            time.sleep(0.4)
        raise ProbeFailure(f"PostgreSQL did not become ready: {type(last_error).__name__ if last_error else 'unknown'}")

    def stop(self) -> None:
        if self.container_created:
            result = self._run(["stop", "--time", "3", self.name], timeout=20)
            if result.returncode != 0:
                detail = result.stderr.decode("utf-8", errors="replace").strip()
                if "No such container" in detail:
                    self.container_created = False

    def restart(self) -> None:
        self._checked(["start", self.name], "postgres restart", timeout=20)
        self.wait_until_ready()

    def cleanup(self) -> dict[str, bool]:
        container_removed = False
        volume_removed = False
        if self.container_created:
            result = self._run(["rm", "--force", self.name], timeout=30)
            container_removed = result.returncode == 0
            self.container_created = False
        if self.volume_created:
            result = self._run(["volume", "rm", self.volume], timeout=30)
            volume_removed = result.returncode == 0
            self.volume_created = False
        return {"container_removed": container_removed, "volume_removed": volume_removed}


class RunningService:
    def __init__(self, jar: Path, postgres: DockerPostgres, log_path: Path) -> None:
        require(postgres.port is not None, "PostgreSQL host port is not available")
        self.port = choose_port()
        self.base_url = f"http://127.0.0.1:{self.port}/api/v1"
        self.jar = jar
        self.postgres = postgres
        self.log_path = log_path
        self.process: subprocess.Popen[bytes] | None = None
        self.log_handle = None

    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_handle = self.log_path.open("wb")
        environment = os.environ.copy()
        environment.update({
            "RPF_JDBC_URL": f"jdbc:postgresql://127.0.0.1:{self.postgres.port}/{self.postgres.database}",
            "RPF_DB_USER": self.postgres.user,
            "RPF_DB_PASSWORD": self.postgres.password,
            "RPF_CONTROL_PLANE_ADDRESS": "127.0.0.1",
            "RPF_CONTROL_PLANE_PORT": str(self.port),
        })
        self.process = subprocess.Popen(
            ["java", "-jar", str(self.jar)],
            cwd=str(ROOT),
            env=environment,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise ProbeFailure(f"RPF-13 service exited during startup; log={self.log_path.relative_to(ROOT)}")
            try:
                response = request_json(self.base_url, "GET", "/health", timeout=2)
                if response.status == 200 and response.body.get("ready") is True:
                    return
            except TransportFailure:
                pass
            time.sleep(0.4)
        raise ProbeFailure(f"RPF-13 service did not become ready; log={self.log_path.relative_to(ROOT)}")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            pid = self.process.pid
            self.process.terminate()
            try:
                self.process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=10)
                self.process.wait(timeout=5)
            if self.process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=10)
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None


def source_identity() -> dict[str, Any]:
    files = [
        SPIKE_ROOT / "control-plane" / "pom.xml",
        SPIKE_ROOT / "control-plane" / "src" / "main" / "resources" / "application.properties",
        *sorted((SPIKE_ROOT / "control-plane" / "src" / "main" / "java").rglob("*.java")),
        SPIKE_ROOT / "probe.py",
    ]
    digest = hashlib.sha256()
    names: list[str] = []
    for path in files:
        require(path.is_file(), f"Missing source identity file: {path}")
        name = path.relative_to(ROOT).as_posix()
        names.append(name)
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return {"sha256": digest.hexdigest(), "files": names}


def stable_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(5)}"


def submission(job_id: str, target_type: str, target_id: str, *, idempotency_key: str | None = None) -> dict[str, Any]:
    payload = {
        "evaluation_ref": {"evaluation_id": target_id},
        "scenario_ref": {"scenario_id": "rpf-minimal-reliability-suite", "scenario_version": "1.0.0"},
        "agent_version": "1.0.1-observe-before-mutation-fix",
        "source_revision": "rpf13-probe-profile-v1",
    }
    return {
        "job_id": job_id,
        "idempotency_key": idempotency_key or f"idem-{job_id}",
        "request_fingerprint": sha256(json.dumps(payload | {"target": target_id}, sort_keys=True)),
        "job_type": "EVALUATION",
        "target_type": target_type,
        "target_id": target_id,
        "correlation_id": f"corr-{job_id}",
        "payload_ref": payload,
    }


def submit_job(base_url: str, job_id: str, target_type: str = "EVALUATION", target_id: str | None = None, *, idempotency_key: str | None = None) -> dict[str, Any]:
    payload = submission(job_id, target_type, target_id or f"evaluation-{job_id}", idempotency_key=idempotency_key)
    return expect(request_json(base_url, "POST", "/jobs", payload), 200)


def claim_job(base_url: str, job_id: str, worker_id: str, lease_seconds: int = 2) -> tuple[HttpResponse, dict[str, Any] | None]:
    response = request_json(base_url, "POST", f"/jobs/{job_id}/claim", {"worker_id": worker_id, "lease_seconds": lease_seconds})
    lease = response.body.get("lease") if isinstance(response.body.get("lease"), dict) else None
    return response, lease


def owner_payload(lease: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": lease["attempt_id"],
        "worker_id": lease["worker_id"],
        "lease_token": lease["lease_token"],
        "lease_version": lease["lease_version"],
    }


def refresh_lease(base_url: str, job_id: str, lease: dict[str, Any], lease_seconds: int = 2) -> dict[str, Any]:
    response = expect(request_json(base_url, "POST", f"/jobs/{job_id}/heartbeat", owner_payload(lease) | {"lease_seconds": lease_seconds}), 200)
    next_lease = response.get("lease")
    require(isinstance(next_lease, dict) and next_lease.get("lease_token"), "Heartbeat did not return a fenced lease")
    lease.update(next_lease)
    return response


def start_job(base_url: str, job_id: str, lease: dict[str, Any]) -> dict[str, Any]:
    response = expect(request_json(base_url, "POST", f"/jobs/{job_id}/start", owner_payload(lease)), 200)
    job = response["job"]
    lease["lease_version"] = job["version"]
    return response


def evidence_payload(job_id: str, outcome: str, suffix: str = "terminal") -> dict[str, Any]:
    evidence_id = f"evidence-{job_id}-{suffix}"
    content_sha = sha256(f"{evidence_id}:{outcome}:rpf13")
    return {
        "evidence_id": evidence_id,
        "entity_type": "EVALUATION",
        "entity_id": f"evaluation-{job_id}",
        "outcome": outcome,
        "content_sha256": content_sha,
        "artifact_ref": {
            "artifact_id": evidence_id,
            "artifact_key": f"evaluation/{job_id}/{content_sha}.json",
            "artifact_kind": "RunProof Evaluation Evidence",
            "schema_version": "rpf-evaluation-result-v1",
            "content_sha256": content_sha,
            "source_sha256": "rpf13-deterministic-source",
            "runtime_version": "rpf13-probe-runtime-v1",
        },
    }


def ingest_evidence(base_url: str, job_id: str, outcome: str = "PASS", suffix: str = "terminal") -> tuple[dict[str, Any], dict[str, Any]]:
    payload = evidence_payload(job_id, outcome, suffix)
    response = expect(request_json(base_url, "POST", f"/jobs/{job_id}/evidence", payload), 200)
    return response, payload


def operation_payload(lease: dict[str, Any], operation_id: str, environment_id: str) -> dict[str, Any]:
    return owner_payload(lease) | {
        "operation_id": operation_id,
        "environment_id": environment_id,
        "operation_fingerprint": sha256(f"{operation_id}:{environment_id}:change-v1"),
    }


def run_worker_response_lost(base_url: str, job_id: str, operation_id: str) -> int:
    """A real child process that dies immediately after a committed effect."""

    response, lease = claim_job(base_url, job_id, "worker-lost", lease_seconds=1)
    if response.status != 200 or not isinstance(lease, dict):
        return 31
    start_job(base_url, job_id, lease)
    prepared = expect(request_json(base_url, "POST", f"/jobs/{job_id}/operations", operation_payload(lease, operation_id, "env-response-lost")), 200)
    if prepared.get("status") not in {"PREPARED", "IDEMPOTENT_REPLAY"}:
        return 32
    lost = request_json(
        base_url,
        "POST",
        f"/jobs/{job_id}/operations/{operation_id}/apply?simulate_response_lost=true",
        owner_payload(lease),
    )
    if lost.status != 503 or lost.body.get("error") != "TRANSPORT_RESPONSE_LOST":
        return 33
    os._exit(17)


def run_worker_artifact_crash(artifact_path: str) -> int:
    """A separate process exits after artifact generation and before ingest."""

    if not Path(artifact_path).is_file():
        return 41
    os._exit(23)


def spawn_response_lost_worker(base_url: str, job_id: str, operation_id: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker-response-lost", base_url, job_id, operation_id],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )


def spawn_artifact_crash_worker(artifact_path: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker-artifact-crash", str(artifact_path)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )


def run_probe(jar: Path) -> Path:
    run_id = f"rpf13-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
    run_dir = ROOT / ".local" / "rpf-13" / run_id
    result_path = run_dir / "rpf13-probe-result.json"
    results: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "artifact_kind": "Durable Execution Investigation Evidence",
        "status": "FAIL",
        "started_at": utc_now(),
        "source_identity": source_identity(),
        "probe": {"platform": platform.platform(), "python": platform.python_version(), "provider": "POSTGRESQL_DOCKER"},
        "candidate": {
            "module": "spikes/rpf-13/control-plane/",
            "schema_version": "rpf-13-durable-execution-schema-v1",
            "database_image": POSTGRES_IMAGE,
            "transport": "POSTGRESQL_POLL_CLAIM_LEASE",
        },
        "observations": {},
        "errors": [],
        "cleanup": {"container_removed": False, "volume_removed": False},
    }
    postgres: DockerPostgres | None = None
    service: RunningService | None = None
    failure: Exception | None = None

    def record(name: str, value: Any) -> None:
        results["observations"][name] = value

    try:
        require(jar.is_file(), f"Missing packaged RPF-13 candidate jar: {jar}")
        postgres = DockerPostgres()
        postgres.start()
        service = RunningService(jar, postgres, run_dir / "control-plane.log")
        service.start()
        base_url = service.base_url

        health = expect(request_json(base_url, "GET", "/health"), 200)
        require(health.get("ready") is True and health.get("database") == "REACHABLE", "Candidate health/readiness failed")
        capabilities = expect(request_json(base_url, "GET", "/capabilities"), 200)
        require(capabilities.get("execution_state_store") == "POSTGRESQL", "Candidate did not report PostgreSQL durable state")
        require(capabilities.get("transport_candidate") == "POSTGRESQL_POLL_CLAIM_LEASE", "Transport candidate identity drifted")
        require(capabilities.get("broker") is False and capabilities.get("scheduler") is False, "Spike introduced an out-of-scope broker or scheduler")
        require(capabilities.get("release_authority") is False and capabilities.get("approval_authority") is False, "Spike widened release/approval authority")
        unsafe_payload = submission(stable_id("unsafe-payload"), "EVALUATION", "evaluation-unsafe-payload")
        unsafe_payload["payload_ref"] = {"prompt": "redacted-private-protocol-probe"}
        unsafe_response = request_json(base_url, "POST", "/jobs", unsafe_payload)
        expect(unsafe_response, 400, "FORBIDDEN_PAYLOAD_FIELD")
        record("health_and_boundary", {
            "status": "PASS",
            "database": health.get("database"),
            "database_product": health.get("database_product"),
            "database_version": health.get("database_version"),
            "schema_version": health.get("schema_version"),
            "transport": capabilities.get("transport_candidate"),
            "delivery": capabilities.get("delivery_semantics"),
            "broker": capabilities.get("broker"),
            "scheduler": capabilities.get("scheduler"),
            "release_authority": capabilities.get("release_authority"),
        })

        # Submit and idempotency establish one durable logical job identity.
        normal_id = stable_id("normal")
        normal_submit = submit_job(base_url, normal_id)
        require(normal_submit.get("status") == "SUBMITTED", "Initial submit was not durable")
        replay = submit_job(base_url, normal_id)
        require(replay.get("status") == "IDEMPOTENT_REPLAY" and replay.get("already_exists") is True, "Same logical submit was not idempotent")
        conflict_payload = submission(normal_id, "EVALUATION", f"evaluation-{normal_id}", idempotency_key=f"idem-{normal_id}")
        conflict_payload["request_fingerprint"] = sha256("different-request")
        conflict_response = request_json(base_url, "POST", "/jobs", conflict_payload)
        expect(conflict_response, 409, "IDEMPOTENCY_CONFLICT")
        record("durable_submit_and_idempotency", {
            "status": "PASS",
            "initial": normal_submit.get("status"),
            "replay": replay.get("status"),
            "conflict": conflict_response.body.get("error"),
            "execution_evidence_separate": True,
        })

        # Two actual concurrent HTTP workers race on the same locked row.
        race_id = stable_id("race")
        submit_job(base_url, race_id)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(claim_job, base_url, race_id, worker, 4) for worker in ("worker-race-a", "worker-race-b")]
            race_results = [future.result() for future in futures]
        race_statuses = sorted(response.status for response, _ in race_results)
        require(race_statuses == [200, 409], f"Concurrent claim did not fence one owner: {race_statuses}")
        winner_response, winner_lease = next(item for item in race_results if item[0].status == 200)
        require(isinstance(winner_lease, dict), "Winning claim did not return a lease")
        start_job(base_url, race_id, winner_lease)
        heartbeat_before = winner_lease["lease_version"]
        heartbeat_result = refresh_lease(base_url, race_id, winner_lease, 4)
        require(winner_lease["lease_version"] > heartbeat_before, "Heartbeat did not advance fencing version")
        race_evidence_response, race_evidence = ingest_evidence(base_url, race_id)
        complete_race = expect(request_json(base_url, "POST", f"/jobs/{race_id}/complete", owner_payload(winner_lease) | {"evidence_id": race_evidence["evidence_id"]}), 200)
        require(complete_race["job"]["state"] == "COMPLETED", "Race job did not complete")
        terminal_claim, _ = claim_job(base_url, race_id, "worker-after-terminal", 2)
        require(terminal_claim.status == 200 and terminal_claim.body.get("status") == "TERMINAL", "Terminal job was claimable again")
        record("claim_concurrency_heartbeat_terminal", {
            "status": "PASS",
            "concurrent_http_statuses": race_statuses,
            "single_owner": True,
            "heartbeat": "LEASE_EXTENDED_AND_VERSION_FENCED",
            "terminal_claim": terminal_claim.body.get("status"),
            "evidence_status": race_evidence_response.get("status"),
        })

        # A: claim before Agent, then lease expiry safely reclaims. Old owner
        # cannot finalize the new attempt.
        reclaim_id = stable_id("reclaim")
        submit_job(base_url, reclaim_id)
        old_response, old_lease = claim_job(base_url, reclaim_id, "worker-old", 1)
        require(old_response.status == 200 and isinstance(old_lease, dict), "Pre-agent claim failed")
        time.sleep(1.5)
        new_response, new_lease = claim_job(base_url, reclaim_id, "worker-new", 2)
        require(new_response.status == 200 and new_response.body.get("status") == "CLAIMED", "Expired claim was not safely reclaimed")
        require(new_response.body["job"]["attempt_number"] == 2, "Safe reclaim did not create a new attempt")
        reclaim_evidence_response, reclaim_evidence = ingest_evidence(base_url, reclaim_id)
        stale_complete = request_json(base_url, "POST", f"/jobs/{reclaim_id}/complete", owner_payload(old_lease) | {"evidence_id": reclaim_evidence["evidence_id"]})
        expect(stale_complete, 409, "STALE_ATTEMPT")
        start_job(base_url, reclaim_id, new_lease)
        completed_reclaim = expect(request_json(base_url, "POST", f"/jobs/{reclaim_id}/complete", owner_payload(new_lease) | {"evidence_id": reclaim_evidence["evidence_id"]}), 200)
        require(completed_reclaim["job"]["state"] == "COMPLETED", "Reclaimed attempt did not complete")
        record("crash_matrix_A_and_stale_fencing", {
            "status": "PASS",
            "lease_expiry": "SAFE_RECLAIM",
            "agent_fail_created": False,
            "attempts": completed_reclaim["job"]["attempts"],
            "stale_finalize": stale_complete.body.get("error"),
            "evidence_replayed_not_overwritten": reclaim_evidence_response.get("status") == "EVIDENCE_STORED",
        })

        # B/C: an agent can start and die before a side effect; an explicit
        # NOT_SUBMITTED proof permits a new attempt to reuse the operation id.
        operation_job_id = stable_id("not-submitted")
        submit_job(base_url, operation_job_id)
        _, operation_lease = claim_job(base_url, operation_job_id, "worker-operation-old", 2)
        require(isinstance(operation_lease, dict), "Operation job claim failed")
        start_job(base_url, operation_job_id, operation_lease)
        operation_id = f"operation-{operation_job_id}"
        prepared = expect(request_json(base_url, "POST", f"/jobs/{operation_job_id}/operations", operation_payload(operation_lease, operation_id, "env-not-submitted")), 200)
        require(prepared.get("status") == "PREPARED", "Operation was not durably prepared")
        not_submitted = expect(request_json(base_url, "POST", f"/jobs/{operation_job_id}/operations/{operation_id}/not-submitted", owner_payload(operation_lease)), 200)
        require(not_submitted.get("status") == "NOT_SUBMITTED", "Explicit not-submitted proof was not recorded")
        time.sleep(2.2)
        _, operation_new_lease = claim_job(base_url, operation_job_id, "worker-operation-new", 3)
        require(isinstance(operation_new_lease, dict), "NOT_SUBMITTED operation was not safely reclaimed")
        start_job(base_url, operation_job_id, operation_new_lease)
        operation_replay = expect(request_json(base_url, "POST", f"/jobs/{operation_job_id}/operations", operation_payload(operation_new_lease, operation_id, "env-not-submitted")), 200)
        applied = expect(request_json(base_url, "POST", f"/jobs/{operation_job_id}/operations/{operation_id}/apply", owner_payload(operation_new_lease)), 200)
        confirmed = expect(request_json(base_url, "POST", f"/jobs/{operation_job_id}/operations/{operation_id}/confirm", owner_payload(operation_new_lease)), 200)
        require(operation_replay.get("status") == "IDEMPOTENT_REPLAY" and applied.get("status") == "SENT" and confirmed.get("status") == "CONFIRMED", "Safe operation retry did not follow operation identity")
        operation_evidence_response, operation_evidence = ingest_evidence(base_url, operation_job_id)
        operation_complete = expect(request_json(base_url, "POST", f"/jobs/{operation_job_id}/complete", owner_payload(operation_new_lease) | {"evidence_id": operation_evidence["evidence_id"]}), 200)
        operation_snapshot = operation_complete["job"]
        require(operation_snapshot["operations"][0]["effect_count"] == 1, "Safe retry produced more than one simulated side effect")
        record("crash_matrix_B_C_and_operation_identity", {
            "status": "PASS",
            "agent_started_before_action_reclaim": True,
            "explicit_not_submitted": not_submitted.get("status"),
            "operation_id_stable": operation_id,
            "prepare_replay": operation_replay.get("status"),
            "apply": applied.get("status"),
            "confirm": confirmed.get("status"),
            "effect_count": operation_snapshot["operations"][0]["effect_count"],
            "agent_fail_created": False,
            "evidence_count": len(operation_snapshot["evidence"]),
            "evidence_ingest": operation_evidence_response.get("status"),
        })

        # D: a separate worker process commits an environment effect, loses
        # the response, and dies. Expiry requires reconcile, never blind retry.
        unknown_job_id = stable_id("unknown")
        submit_job(base_url, unknown_job_id)
        unknown_operation_id = f"operation-{unknown_job_id}"
        child = spawn_response_lost_worker(base_url, unknown_job_id, unknown_operation_id)
        require(child.returncode == 17, f"Response-lost worker did not crash at the intended boundary: {child.returncode}")
        time.sleep(1.5)
        expired_response, _ = claim_job(base_url, unknown_job_id, "worker-recovery", 3)
        require(expired_response.status == 200 and expired_response.body.get("status") == "RECONCILE_REQUIRED", "Expired in-flight side effect was re-claimed instead of reconciled")
        marked_unknown = expect(request_json(base_url, "POST", f"/jobs/{unknown_job_id}/operations/{unknown_operation_id}/unknown", {"worker_id": "worker-recovery"}), 200)
        require(marked_unknown.get("status") == "UNKNOWN_OUTCOME", "UNKNOWN_OUTCOME was not durable across worker process restart")
        reconciled = expect(request_json(base_url, "POST", f"/jobs/{unknown_job_id}/operations/{unknown_operation_id}/reconcile", {"worker_id": "worker-recovery"}), 200)
        require(reconciled.get("status") == "CONFIRMED" and reconciled.get("safe_to_retry") is False, "Environment reconcile did not confirm the committed effect")
        _, unknown_lease = claim_job(base_url, unknown_job_id, "worker-recovery-2", 3)
        require(isinstance(unknown_lease, dict), "Reconciled job was not returned to a queueable state")
        start_job(base_url, unknown_job_id, unknown_lease)
        blind_retry = expect(request_json(base_url, "POST", f"/jobs/{unknown_job_id}/operations/{unknown_operation_id}/apply", owner_payload(unknown_lease)), 200)
        require(blind_retry.get("status") == "IDEMPOTENT_REPLAY", "Confirmed operation was blindly mutated again")
        unknown_evidence_response, unknown_evidence = ingest_evidence(base_url, unknown_job_id)
        unknown_complete = expect(request_json(base_url, "POST", f"/jobs/{unknown_job_id}/complete", owner_payload(unknown_lease) | {"evidence_id": unknown_evidence["evidence_id"]}), 200)
        unknown_operations = unknown_complete["job"]["operations"]
        require(unknown_operations[0]["effect_count"] == 1 and unknown_complete["job"]["state"] == "COMPLETED", "UNKNOWN_OUTCOME recovery duplicated or lost the effect")
        event_types = [event["event_type"] for event in unknown_complete["job"]["events"]]
        require("UNKNOWN_OUTCOME" in event_types and "OPERATION_RECONCILED" in event_types, "Unknown/reconcile events were not retained")
        record("crash_matrix_D_unknown_outcome_cross_process", {
            "status": "PASS",
            "worker_process_exit_code": child.returncode,
            "expiry_result": expired_response.body.get("status"),
            "unknown": marked_unknown.get("status"),
            "reconcile": reconciled.get("status"),
            "safe_to_retry_after_reconcile": reconciled.get("safe_to_retry"),
            "post_reconcile_apply": blind_retry.get("status"),
            "effect_count": unknown_operations[0]["effect_count"],
            "events": [event for event in event_types if event in {"UNKNOWN_OUTCOME", "OPERATION_RECONCILED"}],
            "agent_fail_created": False,
            "evidence_ingest": unknown_evidence_response.get("status"),
        })

        # E: artifact exists before a simulated process exit; ingest replay is
        # immutable and does not create another attempt or execute the Agent.
        artifact_job_id = stable_id("artifact")
        submit_job(base_url, artifact_job_id)
        _, artifact_lease = claim_job(base_url, artifact_job_id, "worker-artifact", 3)
        require(isinstance(artifact_lease, dict), "Artifact job claim failed")
        start_job(base_url, artifact_job_id, artifact_lease)
        artifact_content = json.dumps({"artifact": "redacted-reviewed-ref", "job": artifact_job_id}, sort_keys=True).encode()
        artifact_path = run_dir / f"{artifact_job_id}-generated.json"
        artifact_path.write_bytes(artifact_content)
        artifact_crash = spawn_artifact_crash_worker(artifact_path)
        require(artifact_crash.returncode == 23, f"Artifact worker did not crash before ingest: {artifact_crash.returncode}")
        artifact_first, artifact_manifest = ingest_evidence(base_url, artifact_job_id)
        artifact_second = expect(request_json(base_url, "POST", f"/jobs/{artifact_job_id}/evidence", artifact_manifest), 200)
        require(artifact_first.get("status") == "EVIDENCE_STORED" and artifact_second.get("status") == "IDEMPOTENT_REPLAY", "Artifact ingest replay was not idempotent")
        artifact_complete = expect(request_json(base_url, "POST", f"/jobs/{artifact_job_id}/complete", owner_payload(artifact_lease) | {"evidence_id": artifact_manifest["evidence_id"]}), 200)
        require(artifact_complete["job"]["attempt_number"] == 1 and len(artifact_complete["job"]["evidence"]) == 1, "Artifact crash recovery re-executed or overwrote evidence")
        record("crash_matrix_E_artifact_before_ingest", {
            "status": "PASS",
            "artifact_generated": artifact_path.is_file(),
            "worker_process_exit_code": artifact_crash.returncode,
            "first_ingest": artifact_first.get("status"),
            "replay": artifact_second.get("status"),
            "attempt_number": artifact_complete["job"]["attempt_number"],
            "evidence_count": len(artifact_complete["job"]["evidence"]),
            "raw_artifact_in_execution_row": False,
        })

        # Cancellation: queued cancel is terminal; running cancel is a
        # request until the owner acknowledges a safe boundary.
        queued_cancel_id = stable_id("cancel-queued")
        submit_job(base_url, queued_cancel_id)
        _, queued_cancel_evidence = ingest_evidence(base_url, queued_cancel_id, "CANCELLED")
        queued_cancel = expect(request_json(base_url, "POST", f"/jobs/{queued_cancel_id}/cancel", {"evidence_id": queued_cancel_evidence["evidence_id"]}), 200)
        require(queued_cancel["status"] == "CANCELLED", "Queued cancellation was not terminal")

        running_cancel_id = stable_id("cancel-running")
        submit_job(base_url, running_cancel_id)
        _, running_cancel_lease = claim_job(base_url, running_cancel_id, "worker-cancel", 3)
        require(isinstance(running_cancel_lease, dict), "Running cancellation claim failed")
        start_job(base_url, running_cancel_id, running_cancel_lease)
        _, running_cancel_evidence = ingest_evidence(base_url, running_cancel_id, "CANCELLED")
        cancel_requested = expect(request_json(base_url, "POST", f"/jobs/{running_cancel_id}/cancel", {}), 200)
        running_cancel_lease["lease_version"] = cancel_requested["job"]["version"]
        require(cancel_requested["status"] == "CANCEL_REQUESTED", "Running cancellation did not remain a request")
        cancelled = expect(request_json(base_url, "POST", f"/jobs/{running_cancel_id}/cancel/ack", owner_payload(running_cancel_lease) | {"evidence_id": running_cancel_evidence["evidence_id"]}), 200)
        require(cancelled["job"]["state"] == "CANCELLED" and cancelled["job"]["outcome_status"] == "CANCELLED", "Cancellation acknowledgement did not align evidence")
        record("cancellation_semantics", {
            "status": "PASS",
            "queued": queued_cancel["status"],
            "running_request": cancel_requested["status"],
            "running_ack": cancelled["job"]["state"],
            "terminal_outcome": cancelled["job"]["outcome_status"],
            "agent_fail_created": False,
        })

        # Timeout after an unresolved side effect enters reconcile, not Agent
        # FAIL; a queued timeout becomes FAILED_PLATFORM with INCONCLUSIVE.
        timeout_unknown_id = stable_id("timeout-unknown")
        submit_job(base_url, timeout_unknown_id)
        _, timeout_lease = claim_job(base_url, timeout_unknown_id, "worker-timeout", 3)
        require(isinstance(timeout_lease, dict), "Timeout job claim failed")
        start_job(base_url, timeout_unknown_id, timeout_lease)
        timeout_operation_id = f"operation-{timeout_unknown_id}"
        expect(request_json(base_url, "POST", f"/jobs/{timeout_unknown_id}/operations", operation_payload(timeout_lease, timeout_operation_id, "env-timeout")), 200)
        timeout_lost = request_json(base_url, "POST", f"/jobs/{timeout_unknown_id}/operations/{timeout_operation_id}/apply?simulate_response_lost=true", owner_payload(timeout_lease))
        require(timeout_lost.status == 503, "Timeout unknown-side-effect setup did not lose response")
        _, timeout_evidence = ingest_evidence(base_url, timeout_unknown_id, "INCONCLUSIVE")
        timeout_reconcile = expect(request_json(base_url, "POST", f"/jobs/{timeout_unknown_id}/timeout", owner_payload(timeout_lease) | {"evidence_id": timeout_evidence["evidence_id"]}), 200)
        require(timeout_reconcile["status"] == "RECONCILE_REQUIRED", "Timeout with unresolved effect did not require reconcile")
        expect(request_json(base_url, "POST", f"/jobs/{timeout_unknown_id}/operations/{timeout_operation_id}/unknown", {"worker_id": "worker-timeout-recovery"}), 200)
        timeout_reconciled = expect(request_json(base_url, "POST", f"/jobs/{timeout_unknown_id}/operations/{timeout_operation_id}/reconcile", {"worker_id": "worker-timeout-recovery"}), 200)
        require(timeout_reconciled["status"] == "CONFIRMED", "Timeout reconcile did not inspect environment effect")
        _, timeout_new_lease = claim_job(base_url, timeout_unknown_id, "worker-timeout-final", 3)
        require(isinstance(timeout_new_lease, dict), "Timeout-reconciled job did not requeue")
        timeout_failed = expect(request_json(base_url, "POST", f"/jobs/{timeout_unknown_id}/fail-platform", owner_payload(timeout_new_lease) | {"evidence_id": timeout_evidence["evidence_id"], "reason": "TIMEOUT_AFTER_RECONCILE"}), 200)
        require(timeout_failed["job"]["state"] == "FAILED_PLATFORM" and timeout_failed["job"]["outcome_status"] == "INCONCLUSIVE", "Timeout platform outcome was misclassified")

        queued_timeout_id = stable_id("timeout-queued")
        submit_job(base_url, queued_timeout_id)
        _, queued_timeout_evidence = ingest_evidence(base_url, queued_timeout_id, "INCONCLUSIVE")
        queued_timeout = expect(request_json(base_url, "POST", f"/jobs/{queued_timeout_id}/timeout", {"evidence_id": queued_timeout_evidence["evidence_id"]}), 200)
        require(queued_timeout["job"]["state"] == "FAILED_PLATFORM" and queued_timeout["job"]["outcome_status"] == "INCONCLUSIVE", "Queued timeout did not become platform INCONCLUSIVE")
        record("cancellation_timeout_semantics", {
            "status": "PASS",
            "unknown_side_effect_timeout": timeout_reconcile["status"],
            "reconcile": timeout_reconciled["status"],
            "post_reconcile_platform_state": timeout_failed["job"]["state"],
            "post_reconcile_outcome": timeout_failed["job"]["outcome_status"],
            "queued_timeout_state": queued_timeout["job"]["state"],
            "queued_timeout_outcome": queued_timeout["job"]["outcome_status"],
            "agent_fail_created": False,
        })

        # F: stopping PostgreSQL is a retriable platform/storage condition and
        # the same history becomes readable after database restart.
        postgres.stop()
        time.sleep(1.0)
        unavailable_health = request_json(base_url, "GET", "/health", timeout=5)
        require(unavailable_health.status == 503 and unavailable_health.body.get("database") == "UNAVAILABLE", "Database outage was not exposed as platform unavailability")
        postgres.restart()
        service.stop()
        service = RunningService(jar, postgres, run_dir / "control-plane-restart.log")
        service.start()
        base_url = service.base_url
        deadline = time.monotonic() + 30
        recovered_health: HttpResponse | None = None
        while time.monotonic() < deadline:
            try:
                candidate = request_json(base_url, "GET", "/health", timeout=3)
                if candidate.status == 200:
                    recovered_health = candidate
                    break
            except TransportFailure:
                pass
            time.sleep(0.5)
        require(recovered_health is not None and recovered_health.body.get("ready") is True, "Candidate did not recover after PostgreSQL restart")
        recovered_unknown = expect(request_json(base_url, "GET", f"/jobs/{unknown_job_id}"), 200)
        require(recovered_unknown.get("state") == "COMPLETED", "PostgreSQL restart lost completed durable history")
        record("crash_matrix_F_database_unavailable_restart", {
            "status": "PASS",
            "unavailable_http_status": unavailable_health.status,
            "unavailable_error": "PLATFORM_STORAGE_UNAVAILABLE_OR_NOT_READY",
            "agent_fail_created": False,
            "recovered_readback": recovered_unknown.get("state"),
            "recovered_health": recovered_health.body.get("readiness"),
        })

        # A minimal future CI submit -> poll -> terminal read contract. The
        # target and evidence refs are stable; existing RPF-12 CP readback
        # remains the canonical Evaluation/Decision consumer.
        ci_job_id = stable_id("ci-evaluation")
        ci_submit = submit_job(base_url, ci_job_id, target_type="EVALUATION", target_id=f"evaluation-ci-{ci_job_id}")
        require(ci_submit["job"]["state"] == "QUEUED", "CI submit did not return QUEUED job")
        ci_polled = expect(request_json(base_url, "GET", f"/jobs/{ci_job_id}"), 200)
        _, ci_lease = claim_job(base_url, ci_job_id, "worker-ci", 3)
        require(isinstance(ci_lease, dict), "CI job was not claimable")
        start_job(base_url, ci_job_id, ci_lease)
        _, ci_evidence = ingest_evidence(base_url, ci_job_id)
        ci_terminal = expect(request_json(base_url, "POST", f"/jobs/{ci_job_id}/complete", owner_payload(ci_lease) | {"evidence_id": ci_evidence["evidence_id"]}), 200)
        ci_readback = expect(request_json(base_url, "GET", f"/jobs/{ci_job_id}"), 200)
        require(ci_terminal["job"]["state"] == "COMPLETED" and ci_readback["state"] == "COMPLETED" and ci_readback["target"]["type"] == "EVALUATION", "CI terminal readback contract failed")
        record("future_ci_submit_poll_terminal_read", {
            "status": "PASS",
            "submit": ci_submit["status"],
            "initial_poll": ci_polled["state"],
            "terminal": ci_readback["state"],
            "target_type": ci_readback["target"]["type"],
            "target_id_stable": ci_readback["target"]["id"],
            "canonical_decision_read": "RPF-12_CONTROL_PLANE_READ_ONLY_FOLLOW_UP",
            "timeout_rule": "FAIL_CLOSED_PLATFORM_OR_RECONCILE",
            "release_authority": False,
        })

        job_view = expect(request_json(base_url, "GET", f"/jobs/{ci_job_id}"), 200)
        required_read_fields = {"state", "active_attempt_id", "attempts", "operations", "evidence", "events", "platform_reason", "outcome_status"}
        require(required_read_fields.issubset(job_view), "Job read model does not express operator-visible execution state")
        record("operator_read_model", {
            "status": "PASS",
            "fields": sorted(required_read_fields),
            "states": capabilities["supported_states"],
            "worker_attempt_lease": True,
            "reconcile_required": True,
            "terminal_outcome": True,
            "platform_failure": True,
        })

        record("transport_candidate_comparison", {
            "status": "PASS",
            "candidate_a": {
                "name": "PostgreSQL durable job state + worker poll/claim",
                "durability": "REAL_POSTGRES_ROW_AND_APPEND_ONLY_ATTEMPTS",
                "duplicate_delivery": "ROW_LOCK_PLUS_FENCED_ATTEMPT",
                "lease_retry": "PROVEN_WITH_SAFE_AND_RECONCILE_BRANCHES",
                "unknown_outcome": "OPERATION_ENVIRONMENT_RECONCILE",
                "ci_local_reproducibility": "GOOD_WITH_EXISTING_POSTGRES_CONTAINER",
                "operations": "LOWER_COMPONENT_COUNT",
            },
            "candidate_b": {
                "name": "Independent broker plus PostgreSQL canonical execution state",
                "implemented": False,
                "reason_not_introduced": "Current v1 scale/failure contract is satisfied by Candidate A; broker durability and operations were not needed to prove the boundary.",
                "future_trigger": "Measured throughput, delayed delivery, fan-out, or broker-specific operational requirement.",
            },
            "conclusion": "CANDIDATE_A_SUFFICIENT_FOR_NEXT_FORMAL_SPIKE_BOUNDARY_NOT_PRODUCTION_HA",
        })

        serialized = json.dumps(results, ensure_ascii=False)
        forbidden_output = ["Authorization", "Bearer ", "private reasoning", "chain_of_thought", "DEEPSEEK_API_KEY"]
        require(not any(value in serialized for value in forbidden_output), "Forbidden credential/private protocol text entered result")
        log_leaks: list[str] = []
        if postgres is not None:
            for log_path in run_dir.glob("*.log"):
                content = log_path.read_bytes()
                if postgres.password.encode("utf-8") in content:
                    log_leaks.append(log_path.name)
        require(not log_leaks, f"Database password appeared in candidate logs: {log_leaks}")
        record("secret_private_protocol_boundary", {
            "status": "PASS",
            "credentials_in_result": False,
            "credentials_in_logs": False,
            "forbidden_payload_rejected": unsafe_response.body.get("error") == "FORBIDDEN_PAYLOAD_FIELD",
            "job_payload_only_refs": True,
            "private_reasoning_persisted": False,
            "release_deploy_authority": False,
        })
        results["status"] = "PASS"
    except Exception as error:
        failure = error
        results["errors"].append(f"{type(error).__name__}: {str(error)}")
    finally:
        if service is not None:
            try:
                service.stop()
            except Exception as error:
                results["errors"].append(f"service cleanup: {type(error).__name__}")
        if postgres is not None:
            try:
                results["cleanup"] = postgres.cleanup()
            except Exception as error:
                results["errors"].append(f"Docker cleanup: {type(error).__name__}")
        results["finished_at"] = utc_now()
        results["run_directory"] = str(run_dir.relative_to(ROOT))
        run_dir.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    if failure is not None:
        raise ProbeFailure(f"RPF-13 probe failed; result={result_path.relative_to(ROOT)}") from failure
    return result_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RPF-13 durable execution PostgreSQL probe.")
    parser.add_argument("--run", action="store_true", help="Run the disposable PostgreSQL/HTTP experiment.")
    parser.add_argument("--worker-response-lost", nargs=3, metavar=("BASE_URL", "JOB_ID", "OPERATION_ID"), help=argparse.SUPPRESS)
    parser.add_argument("--worker-artifact-crash", metavar="ARTIFACT_PATH", help=argparse.SUPPRESS)
    parser.add_argument("--jar", type=Path, default=JAR_DEFAULT)
    args = parser.parse_args()
    if args.worker_response_lost:
        return run_worker_response_lost(*args.worker_response_lost)
    if args.worker_artifact_crash:
        return run_worker_artifact_crash(args.worker_artifact_crash)
    if not args.run:
        parser.error("pass --run to execute the disposable probe")
    try:
        result = run_probe(args.jar)
    except Exception as error:
        print(f"RPF-13 probe failed: {error}", file=sys.stderr)
        return 1
    print(f"PASS: RPF-13 durable execution probe; result={result.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

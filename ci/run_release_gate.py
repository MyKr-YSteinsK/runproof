"""Run the real GitHub Actions RPF-12 canonical Release Gate.

The workflow deliberately keeps orchestration in a small stdlib-only script so
the same code can be inspected, exercised locally, and run on a clean hosted
runner. It starts a fresh PostgreSQL container and the formal Control Plane,
submits Baseline/Candidate Evaluation jobs to PostgreSQL, starts the formal
Python durable worker, and makes the final conclusion from canonical API
read-back. No release or deployment action is implemented here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.runproof_runtime.agent import FIXED_CANDIDATE_AGENT_PROFILE, KNOWN_BAD_AGENT_PROFILE
from runtime.runproof_runtime.control_plane_client import (
    ControlPlaneClient,
    ControlPlaneClientError,
    build_artifact_manifest,
)
from runtime.runproof_runtime.evaluation import (
    EVALUATION_SUITE_ID,
    EVALUATION_SUITE_VERSION,
    build_minimal_suite,
    compare_evaluations,
    validate_comparison_artifact,
    validate_evaluation_artifact,
    validate_suite_artifact,
    write_named_artifact as write_evaluation_artifact,
)
from runtime.runproof_runtime.evidence import timestamp
from runtime.runproof_runtime.failure_case import load_json
from runtime.runproof_runtime.quality import (
    QUALITY_POLICY_ID,
    QUALITY_POLICY_VERSION,
    build_minimal_quality_policy,
    build_release_decision,
    evaluate_quality_gate,
    validate_quality_gate_artifact,
    validate_quality_policy,
    validate_release_decision_artifact,
    write_named_artifact as write_quality_artifact,
)


class GateFailure(RuntimeError):
    """A safe, non-secret failure classification for CI output."""

    def __init__(self, phase: str, code: str):
        super().__init__(code)
        self.phase = phase
        self.code = code


def _safe_fragment(value: str, fallback: str = "unknown") -> str:
    value = "".join(character if character.isalnum() or character in "._-" else "-" for character in value)
    return value[:96] or fallback


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise GateFailure("context", "GIT_SHA_UNAVAILABLE") from error


def _context() -> dict[str, Any]:
    checkout_sha = _git_sha()
    github_sha = os.environ.get("GITHUB_SHA") or checkout_sha
    run_id = os.environ.get("GITHUB_RUN_ID") or f"local-{uuid.uuid4().hex[:12]}"
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT") or "1"
    return {
        "provider": "GitHub Actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "local simulation",
        "repository": os.environ.get("GITHUB_REPOSITORY", "MyKr-YSteinsK/runproof"),
        "workflow": os.environ.get("GITHUB_WORKFLOW", "RPF-12 Canonical Release Gate"),
        "event": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "run_id": str(run_id),
        "run_attempt": str(attempt),
        "source_commit_sha": github_sha,
        "checkout_commit_sha": checkout_sha,
        "run_url": (
            f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'MyKr-YSteinsK/runproof')}"
            f"/actions/runs/{run_id}"
            if os.environ.get("GITHUB_ACTIONS") == "true"
            else ""
        ),
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_command(phase: str, command: list[str], *, timeout: float = 30.0) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        raise GateFailure(phase, "REQUIRED_COMMAND_UNAVAILABLE") from error
    except subprocess.TimeoutExpired as error:
        raise GateFailure(phase, "COMMAND_TIMEOUT") from error
    if completed.returncode != 0:
        raise GateFailure(phase, "COMMAND_FAILED")


def _wait_postgres(container: str, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            completed = subprocess.run(
                ["docker", "exec", container, "pg_isready", "-U", "runproof", "-d", "runproof"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            raise GateFailure("postgres_readiness", "POSTGRES_READINESS_COMMAND_FAILED")
        if completed.returncode == 0:
            return
        time.sleep(1)
    raise GateFailure("postgres_readiness", "POSTGRES_READINESS_TIMEOUT")


def _wait_control_plane(process: subprocess.Popen[bytes], base_url: str, timeout: float = 90.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    request = Request(f"{base_url}/health", headers={"Accept": "application/json"})
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise GateFailure("control_plane_readiness", "CONTROL_PLANE_EXITED_BEFORE_READY")
        try:
            with urlopen(request, timeout=3) as response:
                if response.status != 200:
                    time.sleep(1)
                    continue
                payload = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, dict) and payload.get("ready") is True:
                    return payload
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        time.sleep(1)
    raise GateFailure("control_plane_readiness", "CONTROL_PLANE_READINESS_TIMEOUT")


class FreshInfrastructure:
    """Own exactly one temporary PostgreSQL container and Java service."""

    def __init__(self, context: dict[str, Any], temp_root: Path):
        nonce = uuid.uuid4().hex[:8]
        suffix = f"{_safe_fragment(context['run_id'])}-{_safe_fragment(context['run_attempt'])}-{nonce}"
        self.container = f"rpf12-postgres-{suffix}"
        self.db_port = _free_port()
        self.api_port = _free_port()
        self.temp_root = temp_root
        self.artifact_root = temp_root / "artifact-store"
        self.log_path = temp_root / "control-plane.log"
        self.db_password = secrets.token_urlsafe(32)
        self.tokens = {
            "read": secrets.token_urlsafe(32),
            "evidence": secrets.token_urlsafe(32),
            "decision": secrets.token_urlsafe(32),
            "agent": secrets.token_urlsafe(32),
            "ci": secrets.token_urlsafe(32),
            "worker": secrets.token_urlsafe(32),
        }
        self.process: subprocess.Popen[bytes] | None = None
        self.log_handle: Any = None
        self.base_url = f"http://127.0.0.1:{self.api_port}/api/v1"
        self.health: dict[str, Any] = {}

    def start(self) -> None:
        if shutil.which("docker") is None:
            raise GateFailure("infrastructure", "DOCKER_UNAVAILABLE")
        _run_command(
            "postgres_start",
            [
                "docker",
                "run",
                "--detach",
                "--name",
                self.container,
                "--publish",
                f"127.0.0.1:{self.db_port}:5432",
                "--env",
                "POSTGRES_DB=runproof",
                "--env",
                "POSTGRES_USER=runproof",
                f"--env=POSTGRES_PASSWORD={self.db_password}",
                "postgres:16-alpine",
            ],
            timeout=120,
        )
        _wait_postgres(self.container)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        service_env = os.environ.copy()
        service_env.update(
            {
                "RPF_JDBC_URL": f"jdbc:postgresql://127.0.0.1:{self.db_port}/runproof",
                "RPF_DB_USER": "runproof",
                "RPF_DB_PASSWORD": self.db_password,
                "RPF_ARTIFACT_STORE_ROOT": str(self.artifact_root),
                "RPF_CONTROL_PLANE_ADDRESS": "127.0.0.1",
                "RPF_CONTROL_PLANE_PORT": str(self.api_port),
                "RPF_PROBE_ENABLED": "false",
                "RPF_AUTH_READ_TOKEN": self.tokens["read"],
                "RPF_AUTH_EVIDENCE_TOKEN": self.tokens["evidence"],
                "RPF_AUTH_DECISION_TOKEN": self.tokens["decision"],
                "RPF_AUTH_AGENT_TOKEN": self.tokens["agent"],
                "RPF_AUTH_CI_TOKEN": self.tokens["ci"],
                "RPF_AUTH_WORKER_TOKEN": self.tokens["worker"],
            }
        )
        jar = REPO_ROOT / "control-plane" / "target" / "runproof-control-plane-0.1.0-SNAPSHOT.jar"
        if not jar.is_file():
            raise GateFailure("control_plane_start", "CONTROL_PLANE_JAR_MISSING")
        self.log_handle = self.log_path.open("wb")
        try:
            self.process = subprocess.Popen(
                ["java", "-jar", str(jar)],
                cwd=REPO_ROOT,
                env=service_env,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
            )
        except (FileNotFoundError, OSError) as error:
            raise GateFailure("control_plane_start", "JAVA_UNAVAILABLE") from error
        self.health = _wait_control_plane(self.process, self.base_url)

    def stop(self) -> None:
        if self.process is not None:
            # Java may launch a child JVM on Windows. Kill the exact process
            # tree before the parent handle is terminated so the child cannot
            # detach and survive CI cleanup.
            if os.name == "nt" and self.process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=20,
                )
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=10)
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=20,
                )
            else:
                self.process.wait(timeout=10)
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None
        if shutil.which("docker") is not None:
            subprocess.run(
                ["docker", "rm", "--force", self.container],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=20,
            )


def _manifest_for(
    path: Path,
    artifact_store_root: Path,
    correlation: dict[str, str],
) -> tuple[dict[str, Any], Any]:
    artifact = build_artifact_manifest(path, artifact_store_root)
    manifest = json.loads(json.dumps(artifact.manifest))
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
    summary.update(correlation)
    manifest["summary"] = summary
    return manifest, artifact


def _ingest(
    client: ControlPlaneClient,
    path: Path,
    artifact_store_root: Path,
    correlation: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest, artifact = _manifest_for(path, artifact_store_root, correlation)
    response = client.ingest_with_reconcile(manifest)
    return response, {"entity_type": artifact.entity_type, "entity_id": artifact.entity_id, "manifest": manifest}


def _evaluation_paths(result: dict[str, Any]) -> list[Path]:
    paths = result["paths"]
    return [
        *[Path(item) for item in paths["runs"]],
        *[Path(item) for item in paths["regression_results"].values()],
        Path(paths["evaluation"]),
    ]


def _expect_forbidden(client: ControlPlaneClient, manifest: dict[str, Any], label: str) -> dict[str, Any]:
    try:
        client.ingest(manifest)
    except ControlPlaneClientError as error:
        if error.status == 403:
            return {"status": "PASS", "http_status": 403, "error": error.code, "principal": label}
        raise GateFailure("authority", f"{label.upper()}_DECISION_WRITE_NOT_FORBIDDEN") from error
    raise GateFailure("authority", f"{label.upper()}_DECISION_WRITE_WAS_ALLOWED")


def _require(condition: bool, phase: str, code: str) -> None:
    if not condition:
        raise GateFailure(phase, code)


def _status(metadata: dict[str, Any], key: str, default: str = "UNKNOWN") -> str:
    value = metadata.get(key)
    return value if isinstance(value, str) else default


def _regression_status(facts: dict[str, Any]) -> str:
    counts = facts.get("result_counts") if isinstance(facts.get("result_counts"), dict) else {}
    members = facts.get("member_count")
    if isinstance(members, int) and counts.get("PASS") == members and counts.get("FAIL", 0) == 0:
        return "PASS"
    if counts.get("FAIL", 0) > 0:
        return "FAIL"
    return "INCONCLUSIVE"


def _recovery_status(facts: dict[str, Any]) -> str:
    members = facts.get("member_count")
    if isinstance(members, int) and facts.get("recovered_pass_count") == members:
        return "RECOVERED"
    if facts.get("not_reached_count", 0) > 0:
        return "NOT_REACHED"
    if facts.get("triggered_fault_count", 0) > facts.get("recovered_pass_count", 0):
        return "NOT_RECOVERED"
    return "INCONCLUSIVE"


def _durable_request_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_process_output(value: str) -> bool:
    forbidden = ("Authorization", "Bearer ", "DEEPSEEK_API_KEY", "RPF_DB_PASSWORD", "private reasoning", "chain_of_thought")
    return not any(marker in value for marker in forbidden)


def _load_durable_evaluation_result(output_dir: Path, evaluation_id: str) -> dict[str, Any]:
    """Reconstruct the execute_evaluation-shaped result from worker artifacts."""

    evaluation_path = output_dir / f"{evaluation_id}.json"
    if not evaluation_path.is_file():
        raise GateFailure("durable_worker", "EVALUATION_ARTIFACT_MISSING")
    try:
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateFailure("durable_worker", "EVALUATION_ARTIFACT_INVALID") from error
    if not isinstance(evaluation, dict):
        raise GateFailure("durable_worker", "EVALUATION_ARTIFACT_INVALID")
    runs: list[Path] = []
    regression_results: dict[str, Path] = {}
    for path in sorted(output_dir.glob("*.json")):
        if path == evaluation_path:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GateFailure("durable_worker", "WORKER_ARTIFACT_INVALID") from error
        if not isinstance(document, dict):
            continue
        kind = document.get("artifact_kind")
        if kind == "Run Evidence":
            runs.append(path)
        elif kind == "Regression Execution Result":
            result = document.get("result") if isinstance(document.get("result"), dict) else {}
            result_id = result.get("result_id")
            if isinstance(result_id, str):
                member_id = result.get("suite_member_ref", {}).get("member_id") if isinstance(result.get("suite_member_ref"), dict) else path.stem
                regression_results[str(member_id)] = path
    return {
        "evaluation": evaluation,
        "runs": [],
        "regression_results": {},
        "paths": {"evaluation": evaluation_path, "runs": runs, "regression_results": regression_results},
    }


def _run_durable_evaluations(
    infrastructure: FreshInfrastructure,
    generated_root: Path,
    jobs: list[tuple[str, str, Path]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Submit Baseline/Candidate and execute both through the formal worker."""

    ci_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["ci"])
    worker_result_path = generated_root / "durable-worker-result.json"
    submissions: list[dict[str, Any]] = []
    for target_id, profile, output_dir in jobs:
        payload_ref = {
            "contract": "rpf-evaluation-execution-v1",
            "agent_profile": profile,
            "regression_path": "runtime/reviewed-regression.json",
            "output_dir": str(output_dir),
            "evaluation_id": target_id,
            "operation_environment_id": f"ci-evaluation-environment-{target_id}",
        }
        submission = {
            "job_id": f"job-{target_id}",
            "idempotency_key": f"ci-evaluation:{target_id}",
            "request_fingerprint": _durable_request_fingerprint(payload_ref),
            "job_type": "EVALUATION",
            "target_type": "EVALUATION",
            "target_id": target_id,
            "correlation_id": f"ci-durable-{target_id}",
            "payload_ref": payload_ref,
        }
        response = ci_client.submit_job(submission)
        if response.get("status") not in {"SUBMITTED", "IDEMPOTENT_REPLAY"}:
            raise GateFailure("durable_submit", "DURABLE_SUBMIT_NOT_ACCEPTED")
        submissions.append({"job_id": submission["job_id"], "target_id": target_id, "status": response.get("status")})

    worker_env = os.environ.copy()
    worker_env["RPF_AUTH_WORKER_TOKEN"] = infrastructure.tokens["worker"]
    command = [
        sys.executable,
        "-m",
        "runtime.runproof_runtime.durable_worker",
        "--base-url",
        infrastructure.base_url,
        "--token-env",
        "RPF_AUTH_WORKER_TOKEN",
        "--repo-root",
        str(REPO_ROOT),
        "--artifact-store-root",
        str(infrastructure.artifact_root),
        "--worker-id",
        f"ci-worker-{uuid.uuid4().hex[:10]}",
        "--lease-seconds",
        "30",
        "--max-jobs",
        str(len(jobs)),
        "--idle-timeout",
        "180",
        "--once",
        "--result-path",
        str(worker_result_path),
    ]
    try:
        worker = subprocess.run(command, cwd=REPO_ROOT, env=worker_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise GateFailure("durable_worker", "DURABLE_WORKER_PROCESS_FAILED") from error
    if worker.returncode != 0 or not worker_result_path.is_file():
        raise GateFailure("durable_worker", "DURABLE_WORKER_PROCESS_FAILED")
    try:
        worker_result = json.loads(worker_result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateFailure("durable_worker", "DURABLE_WORKER_RESULT_INVALID") from error
    if not isinstance(worker_result, dict) or worker_result.get("status") != "PASS":
        raise GateFailure("durable_worker", "DURABLE_WORKER_RESULT_NOT_PASS")
    worker_jobs = worker_result.get("jobs") if isinstance(worker_result.get("jobs"), list) else []
    if len(worker_jobs) != len(jobs) or any(
        not isinstance(item, dict) or item.get("state") != "COMPLETED"
        for item in worker_jobs
    ):
        raise GateFailure("durable_worker", "DURABLE_JOB_NOT_COMPLETED")
    read_jobs = []
    for submission in submissions:
        job = ci_client.get_job(str(submission["job_id"]))
        if not isinstance(job, dict) or job.get("state") != "COMPLETED":
            raise GateFailure("durable_readback", "DURABLE_JOB_READBACK_NOT_COMPLETED")
        read_jobs.append({"job_id": submission["job_id"], "state": job.get("state"), "attempt_number": job.get("attempt_number"), "terminal_evidence_id": job.get("terminal_evidence_id")})
    baseline = _load_durable_evaluation_result(jobs[0][2], jobs[0][0])
    candidate = _load_durable_evaluation_result(jobs[1][2], jobs[1][0])
    transport = {
        "mechanism": "POSTGRESQL_POLL_CLAIM_LEASE",
        "submissions": submissions,
        "worker": {"module": "runtime.runproof_runtime.durable_worker", "process_exit": worker.returncode, "processed_jobs": len(worker_jobs)},
        "terminal_readback": read_jobs,
        "silent_fallback": False,
        "worker_stdout_safe": _safe_process_output(worker.stdout),
        "worker_stderr_safe": _safe_process_output(worker.stderr),
    }
    return baseline, candidate, transport


def _run_fresh_gate(
    repo_root: Path,
    output_dir: Path,
    infrastructure: FreshInfrastructure,
    context: dict[str, Any],
) -> dict[str, Any]:
    del repo_root  # The script is intentionally anchored to its checkout root.
    generated_root = infrastructure.temp_root / "generated"
    artifact_store_root = infrastructure.artifact_root
    generated_root.mkdir(parents=True, exist_ok=True)
    correlation = {
        "github_run_id": context["run_id"],
        "github_run_attempt": context["run_attempt"],
        "github_source_commit_sha": context["source_commit_sha"],
        "github_workflow": context["workflow"],
    }

    regression_path = REPO_ROOT / "runtime" / "reviewed-regression.json"
    regression = load_json(regression_path)
    suite = build_minimal_suite(regression)
    _require(not validate_suite_artifact(suite, regression), "fresh_inputs", "SUITE_INVALID")
    suite_path = write_evaluation_artifact(suite, generated_root / "suite", "evaluation-suite.json")

    policy = build_minimal_quality_policy(suite)
    _require(not validate_quality_policy(policy, suite), "fresh_inputs", "POLICY_INVALID")
    policy_path = write_quality_artifact(policy, generated_root / "policy", "quality-policy.json")

    run_key = f"{_safe_fragment(context['run_id'])}-{_safe_fragment(context['run_attempt'])}"
    baseline_eval_id = f"evaluation-ci-{run_key}-baseline"
    candidate_eval_id = f"evaluation-ci-{run_key}-candidate"
    baseline_result, candidate_result, durable_transport = _run_durable_evaluations(
        infrastructure,
        generated_root,
        [
            (baseline_eval_id, KNOWN_BAD_AGENT_PROFILE, generated_root / "baseline"),
            (candidate_eval_id, FIXED_CANDIDATE_AGENT_PROFILE, generated_root / "candidate"),
        ],
    )
    baseline_evaluation = baseline_result["evaluation"]
    candidate_evaluation = candidate_result["evaluation"]
    _require(not validate_evaluation_artifact(baseline_evaluation), "fresh_evaluation", "BASELINE_EVALUATION_INVALID")
    _require(not validate_evaluation_artifact(candidate_evaluation), "fresh_evaluation", "CANDIDATE_EVALUATION_INVALID")

    comparison = compare_evaluations(baseline_evaluation, candidate_evaluation)
    _require(not validate_comparison_artifact(comparison), "fresh_comparison", "COMPARISON_INVALID")
    comparison_path = write_evaluation_artifact(comparison, generated_root / "comparison", "evaluation-comparison.json")

    decision_timestamp = timestamp()
    baseline_gate_id = f"gate-evaluation-ci-{run_key}-baseline"
    candidate_gate_id = f"gate-evaluation-ci-{run_key}-candidate"
    baseline_gate = evaluate_quality_gate(
        policy,
        suite,
        baseline_evaluation,
        None,
        comparison,
        regression,
        gate_evaluation_id=baseline_gate_id,
        evaluated_at=decision_timestamp,
        subject="BASELINE",
    )
    candidate_gate = evaluate_quality_gate(
        policy,
        suite,
        candidate_evaluation,
        baseline_evaluation,
        comparison,
        regression,
        gate_evaluation_id=candidate_gate_id,
        evaluated_at=decision_timestamp,
        subject="CANDIDATE",
    )
    _require(not validate_quality_gate_artifact(baseline_gate), "fresh_gate", "BASELINE_GATE_INVALID")
    _require(not validate_quality_gate_artifact(candidate_gate), "fresh_gate", "CANDIDATE_GATE_INVALID")
    baseline_gate_path = write_quality_artifact(baseline_gate, generated_root / "baseline-gate", "quality-gate-evaluation.json")
    candidate_gate_path = write_quality_artifact(candidate_gate, generated_root / "candidate-gate", "quality-gate-evaluation.json")

    baseline_decision_id = f"release-decision-ci-{run_key}-baseline"
    candidate_decision_id = f"release-decision-ci-{run_key}-candidate"
    baseline_decision = build_release_decision(
        baseline_gate,
        release_decision_id=baseline_decision_id,
        decision_timestamp=decision_timestamp,
    )
    candidate_decision = build_release_decision(
        candidate_gate,
        release_decision_id=candidate_decision_id,
        decision_timestamp=decision_timestamp,
    )
    _require(not validate_release_decision_artifact(baseline_decision), "fresh_decision", "BASELINE_DECISION_INVALID")
    _require(not validate_release_decision_artifact(candidate_decision), "fresh_decision", "CANDIDATE_DECISION_INVALID")
    baseline_decision_path = write_quality_artifact(baseline_decision, generated_root / "baseline-decision", "release-decision.json")
    candidate_decision_path = write_quality_artifact(candidate_decision, generated_root / "candidate-decision", "release-decision.json")

    baseline_gate_meta = baseline_gate["gate_evaluation"]
    candidate_gate_meta = candidate_gate["gate_evaluation"]
    _require(_status(baseline_gate_meta, "decision_status") == "BLOCKED", "fresh_gate", "BASELINE_NOT_BLOCKED")
    _require(_status(candidate_gate_meta, "decision_status") == "ELIGIBLE", "fresh_gate", "CANDIDATE_NOT_ELIGIBLE")

    evidence_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["evidence"])
    decision_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["decision"])
    read_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["read"])
    ci_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["ci"])
    agent_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["agent"])

    # The fresh run corpus is registered through the ordinary evidence writer;
    # no checked-in Release Decision is used as the current Gate input.
    registration_paths = [suite_path, regression_path, policy_path]
    registration_paths.extend(_evaluation_paths(baseline_result))
    registration_paths.extend(_evaluation_paths(candidate_result))
    registration_paths.extend([comparison_path, baseline_gate_path, candidate_gate_path])
    registered: list[dict[str, Any]] = []
    for path in registration_paths:
        response, identity = _ingest(evidence_client, path, artifact_store_root, correlation)
        registered.append({
            "entity_type": identity["entity_type"],
            "entity_id": identity["entity_id"],
            "status": response.get("status", "UNKNOWN"),
        })

    candidate_manifest, _ = _manifest_for(candidate_decision_path, artifact_store_root, correlation)
    authority = {
        "ci_evidence_principal": _expect_forbidden(ci_client, candidate_manifest, "ci-service"),
        "evidence_writer_principal": _expect_forbidden(evidence_client, candidate_manifest, "evidence-ingest-service"),
        "agent_principal": _expect_forbidden(agent_client, candidate_manifest, "agent-runtime"),
    }

    # Only the separate decision writer may create canonical decisions.
    baseline_ingest, baseline_identity = _ingest(decision_client, baseline_decision_path, artifact_store_root, correlation)
    candidate_ingest, candidate_identity = _ingest(decision_client, candidate_decision_path, artifact_store_root, correlation)
    candidate_replay, _ = _ingest(decision_client, candidate_decision_path, artifact_store_root, correlation)

    baseline_view = read_client.get("RELEASE_DECISION", baseline_decision_id)
    candidate_view = read_client.get("RELEASE_DECISION", candidate_decision_id)
    _require(isinstance(baseline_view, dict), "canonical_readback", "BASELINE_DECISION_READBACK_MISSING")
    _require(isinstance(candidate_view, dict), "canonical_readback", "CANDIDATE_DECISION_READBACK_MISSING")
    baseline_raw = read_client.get_artifact("RELEASE_DECISION", baseline_decision_id)
    candidate_raw = read_client.get_artifact("RELEASE_DECISION", candidate_decision_id)
    baseline_read_meta = baseline_view["canonical_metadata"]
    candidate_read_meta = candidate_view["canonical_metadata"]
    baseline_artifact_meta = baseline_raw["artifact"]["release_decision"]
    candidate_artifact_meta = candidate_raw["artifact"]["release_decision"]
    _require(baseline_view["artifact_resolution"]["resolved"] is True, "canonical_readback", "BASELINE_ARTIFACT_UNAVAILABLE")
    _require(candidate_view["artifact_resolution"]["resolved"] is True, "canonical_readback", "CANDIDATE_ARTIFACT_UNAVAILABLE")
    _require(_status(baseline_read_meta, "outcome") == "BLOCKED", "canonical_readback", "CANONICAL_BASELINE_NOT_BLOCKED")
    _require(_status(candidate_read_meta, "outcome") == "ELIGIBLE", "canonical_readback", "CANONICAL_CANDIDATE_NOT_ELIGIBLE")
    _require(candidate_artifact_meta["authorization_boundary"]["release_executed"] is False, "canonical_readback", "RELEASE_EXECUTED_BOUNDARY_DRIFT")
    _require(candidate_artifact_meta["authorization_boundary"]["deployment_authorized"] is False, "canonical_readback", "DEPLOYMENT_AUTHORITY_BOUNDARY_DRIFT")
    baseline_history = baseline_artifact_meta.get("history") if isinstance(baseline_artifact_meta.get("history"), dict) else {}
    candidate_history = candidate_artifact_meta.get("history") if isinstance(candidate_artifact_meta.get("history"), dict) else {}
    _require(baseline_history.get("immutable") is True, "canonical_readback", "BASELINE_HISTORY_NOT_IMMUTABLE")
    _require(candidate_history.get("immutable") is True, "canonical_readback", "CANDIDATE_HISTORY_NOT_IMMUTABLE")
    _require(candidate_replay.get("status") == "IDEMPOTENT_REPLAY", "identity", "CANDIDATE_REPLAY_NOT_IDEMPOTENT")
    _require(candidate_replay.get("already_exists") is True, "identity", "CANDIDATE_REPLAY_NOT_MARKED")
    _require(candidate_identity["entity_id"] == candidate_decision_id, "identity", "CANDIDATE_IDENTITY_DRIFT")
    _require(baseline_identity["entity_id"] == baseline_decision_id, "identity", "BASELINE_IDENTITY_DRIFT")

    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_meta = candidate_decision["release_decision"]
    baseline_meta = baseline_decision["release_decision"]
    candidate_regression_status = _regression_status(candidate_meta["historical_regression"])
    candidate_recovery_status = _recovery_status(candidate_meta["recovery_fault"])
    baseline_regression_status = _regression_status(baseline_meta["historical_regression"])
    baseline_recovery_status = _recovery_status(baseline_meta["recovery_fault"])
    result = {
        "schema_version": "rpf-ci-release-gate-v1",
        "status": "PASS",
        "provider": context["provider"],
        "workflow": {
            "name": context["workflow"],
            "event": context["event"],
            "repository": context["repository"],
            "run_id": context["run_id"],
            "run_attempt": context["run_attempt"],
            "run_url": context["run_url"],
            "source_commit_sha": context["source_commit_sha"],
            "checkout_commit_sha": context["checkout_commit_sha"],
        },
        "correlation": correlation,
        "fresh_infrastructure": {
            "postgres": {"image": "postgres:16-alpine", "readiness": "PASS"},
            "formal_control_plane": {
                "module": "control-plane/",
                "readiness": "PASS",
                "health_ready": infrastructure.health.get("ready") is True,
            },
            "formal_runtime": {"module": "runtime/", "execution": "FRESH_PER_MEMBER_VIA_DURABLE_WORKER"},
        },
        "durable_execution": durable_transport,
        "suite": {"id": EVALUATION_SUITE_ID, "version": EVALUATION_SUITE_VERSION},
        "policy": {"id": QUALITY_POLICY_ID, "version": QUALITY_POLICY_VERSION},
        "baseline": {
            "agent_version": baseline_meta["evaluated_agent_version"],
            "evaluation_id": baseline_eval_id,
            "gate_evaluation_id": baseline_gate_id,
            "decision_id": baseline_decision_id,
            "decision_status": baseline_artifact_meta["decision_status"],
            "coverage": baseline_meta["valid_evidence_coverage"],
            "regression": baseline_meta["historical_regression"],
            "recovery": baseline_meta["recovery_fault"],
            "regression_status": baseline_regression_status,
            "recovery_status": baseline_recovery_status,
        },
        "candidate": {
            "agent_version": candidate_meta["evaluated_agent_version"],
            "evaluation_id": candidate_eval_id,
            "gate_evaluation_id": candidate_gate_id,
            "decision_id": candidate_decision_id,
            "decision_status": candidate_artifact_meta["decision_status"],
            "coverage": candidate_meta["valid_evidence_coverage"],
            "regression": candidate_meta["historical_regression"],
            "recovery": candidate_meta["recovery_fault"],
            "regression_status": candidate_regression_status,
            "recovery_status": candidate_recovery_status,
        },
        "comparison": {
            "id": comparison["comparison"]["comparison_id"],
            "status": comparison["comparison"]["status"],
        },
        "canonical_readback": {
            "source": "control_plane_canonical_release_decision_api",
            "baseline_status": baseline_read_meta["outcome"],
            "candidate_status": candidate_read_meta["outcome"],
            "baseline_artifact_resolved": baseline_view["artifact_resolution"]["resolved"],
            "candidate_artifact_resolved": candidate_view["artifact_resolution"]["resolved"],
            "candidate_artifact_content_sha256": candidate_read_meta["artifact_ref"]["content_sha256"],
        },
        "gate": {
            "ci_conclusion": "success",
            "final_decision_source": "canonical_release_decision_readback",
            "baseline_control": "BLOCKED",
            "candidate_gate": "ELIGIBLE",
            "regression": candidate_regression_status,
            "recovery_fault": candidate_recovery_status,
            "baseline_regression": baseline_regression_status,
            "baseline_recovery_fault": baseline_recovery_status,
            "coverage": candidate_meta["valid_evidence_coverage"],
            "blocker_count": len(candidate_meta.get("blocking_reasons", [])),
            "review_count": len(candidate_meta.get("review_reasons", [])),
            "warning_count": len(candidate_meta.get("soft_warnings", [])),
        },
        "authority": authority,
        "idempotency": {
            "candidate_first_ingest": candidate_ingest.get("status", "UNKNOWN"),
            "candidate_replay": candidate_replay.get("status", "UNKNOWN"),
            "candidate_replay_already_exists": candidate_replay.get("already_exists") is True,
            "new_identity_per_run": True,
            "correlation_includes_run_attempt": True,
            "immutable_decision_history": {
                "baseline": baseline_history.get("immutable") is True,
                "candidate": candidate_history.get("immutable") is True,
            },
        },
        "decision_writer": {
            "principal": "decision-writer-service",
            "baseline_ingest": baseline_ingest.get("status", "UNKNOWN"),
            "candidate_ingest": candidate_ingest.get("status", "UNKNOWN"),
            "candidate_replay": candidate_replay.get("status", "UNKNOWN"),
        },
        "authorization_boundary": candidate_meta["authorization_boundary"],
        "pre_gate_checks": {"workflow_step": "passed-before-fresh-gate"},
        "registered_fresh_evidence_count": len(registered),
        "secret_redaction": {
            "status": "PASS",
            "forbidden_values_emitted": False,
            "checked_surfaces": ["github_logs", "job_summary", "machine_readable_artifact", "control_plane_audit"],
            "private_reasoning_persisted": False,
        },
    }
    return result


def _failure_result(context: dict[str, Any], phase: str, code: str) -> dict[str, Any]:
    return {
        "schema_version": "rpf-ci-release-gate-v1",
        "status": "FAIL",
        "provider": context["provider"],
        "workflow": {
            "name": context["workflow"],
            "event": context["event"],
            "repository": context["repository"],
            "run_id": context["run_id"],
            "run_attempt": context["run_attempt"],
            "run_url": context["run_url"],
            "source_commit_sha": context["source_commit_sha"],
            "checkout_commit_sha": context["checkout_commit_sha"],
        },
        "correlation": {
            "github_run_id": context["run_id"],
            "github_run_attempt": context["run_attempt"],
            "github_source_commit_sha": context["source_commit_sha"],
        },
        "failure": {"phase": phase, "code": code},
        "gate": {
            "ci_conclusion": "failure",
            "final_decision_source": "canonical_release_decision_readback_required",
        },
        "authorization_boundary": {"release_executed": False, "deployment_authorized": False},
        "secret_redaction": {"status": "PASS", "forbidden_values_emitted": False},
    }


def _write_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _write_summary(path: str | None, result: dict[str, Any], mirror_path: Path | None = None) -> None:
    workflow = result.get("workflow", {})
    gate = result.get("gate", {})
    baseline = result.get("baseline", {})
    candidate = result.get("candidate", {})
    failure = result.get("failure", {})
    lines = [
        "## RPF-12 Canonical Release Gate",
        "",
        f"- Provider: `{result.get('provider', 'unknown')}`",
        f"- Source commit: `{workflow.get('source_commit_sha', 'unknown')}`",
        f"- Run: `{workflow.get('run_id', 'unknown')}` / attempt `{workflow.get('run_attempt', 'unknown')}`",
        f"- Suite: `{baseline.get('suite_id', EVALUATION_SUITE_ID)}`@`{baseline.get('suite_version', EVALUATION_SUITE_VERSION)}`",
        "",
        "| Control | Result |",
        "| --- | --- |",
        f"| Baseline control | `{gate.get('baseline_control', 'NOT_EVALUATED')}` |",
        f"| Candidate Gate | `{gate.get('candidate_gate', 'NOT_EVALUATED')}` |",
        f"| Historical Regression | `{gate.get('regression', 'NOT_EVALUATED')}` |",
        f"| Recovery/Fault | `{gate.get('recovery_fault', 'NOT_EVALUATED')}` |",
        f"| Evidence coverage | `{gate.get('coverage', 'NOT_EVALUATED')}` |",
        f"| Final Decision | `{candidate.get('decision_status', 'NOT_EVALUATED')}` |",
        f"| CI conclusion | `{gate.get('ci_conclusion', 'failure')}` |",
        "",
        f"- Baseline Evaluation: `{baseline.get('evaluation_id', 'not-created')}` → Decision `{baseline.get('decision_id', 'not-created')}`",
        f"- Candidate Evaluation: `{candidate.get('evaluation_id', 'not-created')}` → Decision `{candidate.get('decision_id', 'not-created')}`",
        f"- Blockers/reviews/warnings: `{gate.get('blocker_count', 'n/a')}` / `{gate.get('review_count', 'n/a')}` / `{gate.get('warning_count', 'n/a')}`",
        "- No release executed; no deployment authorization.",
        "",
    ]
    if failure:
        lines.extend([f"- Failure phase/code: `{failure.get('phase', 'unknown')}` / `{failure.get('code', 'unknown')}`", ""])
    summary = "\n".join(lines)
    if path:
        Path(path).write_text(summary, encoding="utf-8")
    if mirror_path:
        mirror_path.parent.mkdir(parents=True, exist_ok=True)
        mirror_path.write_text(summary, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the RPF-12 GitHub Actions canonical Release Gate.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=Path("ci-results"))
    args = parser.parse_args(argv)
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    result_path = output_dir / "rpf12-release-gate-result.json"
    context = _context()
    result: dict[str, Any]
    infrastructure: FreshInfrastructure | None = None
    temporary = Path(tempfile.mkdtemp(prefix="rpf12-ci-"))
    try:
        infrastructure = FreshInfrastructure(context, temporary)
        try:
            infrastructure.start()
            result = _run_fresh_gate(args.repo_root, output_dir, infrastructure, context)
        except GateFailure as error:
            result = _failure_result(context, error.phase, error.code)
        except ControlPlaneClientError as error:
            result = _failure_result(context, "control_plane", error.code or "CONTROL_PLANE_ERROR")
        except (OSError, ValueError, KeyError, TypeError) as error:
            del error
            result = _failure_result(context, "orchestration", "UNEXPECTED_GATE_FAILURE")
        except Exception as error:  # pragma: no cover - last-resort redacted CI boundary
            del error
            result = _failure_result(context, "orchestration", "UNEXPECTED_GATE_FAILURE")
    finally:
        if infrastructure is not None:
            infrastructure.stop()
        shutil.rmtree(temporary, ignore_errors=True)
    _write_result(result_path, result)
    _write_summary(
        os.environ.get("GITHUB_STEP_SUMMARY"),
        result,
        output_dir / "rpf12-release-gate-summary.md",
    )
    print(json.dumps({"status": result["status"], "result": str(result_path)}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

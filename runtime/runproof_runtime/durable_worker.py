"""Formal PostgreSQL-polling durable Evaluation worker.

The worker is intentionally a small process boundary.  It owns no database
connection: all coordination, fencing, operation identity and evidence ingest
go through :mod:`control_plane_client`.  A worker crash therefore leaves the
Control Plane as the source of truth for the next attempt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import uuid
import re
from pathlib import Path
from typing import Any

from .agent import FIXED_CANDIDATE_AGENT_PROFILE, KNOWN_BAD_AGENT_PROFILE, NORMAL_AGENT_PROFILE
from .agent_contract import INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE, INCIDENT_KNOWN_BAD_AGENT_PROFILE
from .control_plane_client import ControlPlaneClient, ControlPlaneClientError
from .evaluation import build_minimal_suite, execute_evaluation, validate_suite_artifact
from .failure_case import load_json
from .incident import CASE_EXTERNAL, CASE_LOCAL, CASE_RESPONSE_LOST, run_incident_slice, write_incident_artifact


WORKER_RESULT_SCHEMA = "rpf-durable-worker-result-v1"
SUPPORTED_PROFILES = {
    NORMAL_AGENT_PROFILE,
    KNOWN_BAD_AGENT_PROFILE,
    FIXED_CANDIDATE_AGENT_PROFILE,
    INCIDENT_KNOWN_BAD_AGENT_PROFILE,
    INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
}
UNRESOLVED_OPERATION_STATES = {"PREPARED", "IN_FLIGHT", "UNKNOWN_OUTCOME"}


class WorkerFailure(RuntimeError):
    """A bounded, non-secret worker failure classification."""


def _safe_path(
    value: Any,
    label: str,
    base: Path | None = None,
    allowed_roots: tuple[Path, ...] = (),
) -> Path:
    if not isinstance(value, str) or not value:
        raise WorkerFailure(f"INVALID_WORKER_CONTRACT:{label}")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute() and base is not None:
        candidate = base / candidate
    resolved = candidate.resolve()
    if allowed_roots:
        roots = tuple(root.resolve() for root in allowed_roots)
        if not any(resolved == root or root in resolved.parents for root in roots):
            raise WorkerFailure(f"WORKER_PATH_OUTSIDE_ALLOWED_ROOT:{label}")
    return resolved


def _safe_contract(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload_ref")
    if not isinstance(payload, dict):
        raise WorkerFailure("INVALID_WORKER_CONTRACT:payload_ref")
    allowed = {
        "contract", "agent_profile", "regression_path", "suite_path", "output_dir", "evaluation_id", "operation_environment_id",
        "trial_id", "trial_index", "behavior", "scenario_case_id", "fault_profile", "regression_covered",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise WorkerFailure("INVALID_WORKER_CONTRACT:unknown_field")
    contract = payload.get("contract")
    if contract == "rpf-statistical-trial-execution-v1":
        if not isinstance(payload.get("trial_id"), str) or not payload["trial_id"] or not payload["trial_id"].replace("-", "").replace("_", "").isalnum():
            raise WorkerFailure("INVALID_WORKER_CONTRACT:trial_id")
        if not isinstance(payload.get("trial_index"), int) or payload["trial_index"] < 1:
            raise WorkerFailure("INVALID_WORKER_CONTRACT:trial_index")
        if payload.get("behavior") not in {"PASS", "ORDINARY_FAIL", "SAFETY_FAIL"}:
            raise WorkerFailure("INVALID_WORKER_CONTRACT:behavior")
        if payload.get("scenario_case_id") not in {CASE_LOCAL, CASE_RESPONSE_LOST, CASE_EXTERNAL}:
            raise WorkerFailure("INVALID_WORKER_CONTRACT:scenario_case_id")
        if payload.get("fault_profile") not in {"none", "response-lost"}:
            raise WorkerFailure("INVALID_WORKER_CONTRACT:fault_profile")
        if payload.get("behavior") == "SAFETY_FAIL" and payload.get("scenario_case_id") != CASE_EXTERNAL:
            raise WorkerFailure("INVALID_WORKER_CONTRACT:safety_scenario")
        if payload.get("behavior") == "ORDINARY_FAIL" and payload.get("scenario_case_id") != CASE_LOCAL:
            raise WorkerFailure("INVALID_WORKER_CONTRACT:ordinary_fail_scenario")
        for key in ("output_dir",):
            if not isinstance(payload.get(key), str) or not payload[key]:
                raise WorkerFailure(f"INVALID_WORKER_CONTRACT:{key}")
        return payload
    if contract != "rpf-evaluation-execution-v1":
        raise WorkerFailure("UNSUPPORTED_WORKER_CONTRACT")
    profile = payload.get("agent_profile")
    if profile not in SUPPORTED_PROFILES:
        raise WorkerFailure("UNKNOWN_AGENT_PROFILE")
    for key in ("regression_path", "output_dir", "evaluation_id"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise WorkerFailure(f"INVALID_WORKER_CONTRACT:{key}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", str(payload["evaluation_id"])):
        raise WorkerFailure("INVALID_WORKER_CONTRACT:evaluation_id")
    return payload


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _owner_from_claim(claim: dict[str, Any], worker_id: str) -> dict[str, Any]:
    lease = claim.get("lease")
    job = claim.get("job")
    if not isinstance(lease, dict) or not isinstance(job, dict):
        raise WorkerFailure("CLAIM_RESPONSE_MALFORMED")
    token = lease.get("lease_token")
    attempt_id = lease.get("attempt_id")
    version = lease.get("lease_version")
    if not isinstance(token, str) or not token or not isinstance(attempt_id, str) or not isinstance(version, int):
        raise WorkerFailure("CLAIM_LEASE_MALFORMED")
    if lease.get("worker_id") != worker_id or job.get("active_attempt_id") != attempt_id:
        raise WorkerFailure("CLAIM_LEASE_IDENTITY_MISMATCH")
    return {
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "lease_token": token,
        "lease_version": version,
    }


class LeaseRenewer:
    def __init__(self, client: ControlPlaneClient, job_id: str, owner: dict[str, Any], lease_seconds: int) -> None:
        self.client = client
        self.job_id = job_id
        self.owner = owner
        self.lease_seconds = lease_seconds
        self.stop_event = threading.Event()
        self.errors: list[str] = []
        self.thread = threading.Thread(target=self._run, name="rpf-durable-lease-renewer", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        interval = max(1.0, self.lease_seconds / 3)
        while not self.stop_event.wait(interval):
            try:
                response = self.client.heartbeat_job(self.job_id, self.owner, lease_seconds=self.lease_seconds)
                lease = response.get("lease") if isinstance(response, dict) else None
                if isinstance(lease, dict) and isinstance(lease.get("lease_version"), int):
                    self.owner["lease_version"] = lease["lease_version"]
            except ControlPlaneClientError as error:
                self.errors.append(error.code)
                if not error.retriable:
                    return


class DurableEvaluationWorker:
    def __init__(
        self,
        client: ControlPlaneClient,
        *,
        worker_id: str | None = None,
        repo_root: Path | None = None,
        artifact_store_root: Path | None = None,
        allowed_io_roots: tuple[Path, ...] = (),
        lease_seconds: int = 30,
    ) -> None:
        self.client = client
        self.worker_id = worker_id or f"worker-{uuid.uuid4()}"
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.artifact_store_root = (artifact_store_root or Path(os.environ.get("RPF_ARTIFACT_STORE_ROOT", ".local/control-plane/artifacts"))).resolve()
        configured_roots = [self.repo_root, self.artifact_store_root]
        configured_roots.extend(Path(root).resolve() for root in allowed_io_roots)
        self.allowed_io_roots = tuple(dict.fromkeys(configured_roots))
        self.lease_seconds = lease_seconds

    def poll(self, limit: int = 20) -> list[dict[str, Any]]:
        # Discovery is a server-side eligible predicate, not a bounded history
        # page followed by in-memory terminal-state filtering. The Control
        # Plane includes queued/reconcile rows and expired active leases, so a
        # growing terminal history cannot starve executable work.
        return self.client.list_jobs(eligible=True, limit=limit)

    def run_once(self, *, max_jobs: int = 1) -> list[dict[str, Any]]:
        processed: list[dict[str, Any]] = []
        for job in self.poll(limit=max(20, max_jobs * 4)):
            if len(processed) >= max_jobs:
                break
            state = job.get("state")
            if state in {"COMPLETED", "FAILED_PLATFORM", "CANCELLED"}:
                continue
            if state == "RECONCILE_REQUIRED":
                processed.append(self._reconcile_job(job))
                continue
            try:
                outcome = self._claim_and_execute(str(job["job_id"]))
            except ControlPlaneClientError as error:
                if error.code in {"ACTIVE_LEASE", "STALE_ATTEMPT"} or error.status == 409:
                    continue
                processed.append({"job_id": job.get("job_id"), "status": "PLATFORM_ERROR", "error": error.code})
            except WorkerFailure as error:
                processed.append({"job_id": job.get("job_id"), "status": "PLATFORM_ERROR", "error": str(error)})
            else:
                processed.append(outcome)
        return processed

    def run_until_idle(self, *, max_jobs: int = 1, idle_timeout: float = 30.0) -> list[dict[str, Any]]:
        started = time.monotonic()
        all_results: list[dict[str, Any]] = []
        while len(all_results) < max_jobs and time.monotonic() - started < idle_timeout:
            results = self.run_once(max_jobs=max_jobs - len(all_results))
            all_results.extend(results)
            if len(all_results) >= max_jobs:
                break
            time.sleep(0.2)
        return all_results

    def _claim_and_execute(self, job_id: str) -> dict[str, Any]:
        claim = self.client.claim_job(job_id, self.worker_id, lease_seconds=self.lease_seconds)
        status = claim.get("status")
        if status != "CLAIMED":
            return {"job_id": job_id, "status": status or "NOT_CLAIMED"}
        owner = _owner_from_claim(claim, self.worker_id)
        self.client.start_job(job_id, owner)
        renewer = LeaseRenewer(self.client, job_id, owner, self.lease_seconds)
        renewer.start()
        try:
            return self._execute_claimed(job_id, owner)
        except ControlPlaneClientError:
            raise
        except Exception as error:
            self._fail_platform_if_possible(job_id, owner, f"WORKER_EXCEPTION_{type(error).__name__}")
            raise WorkerFailure("WORKER_EXECUTION_FAILED") from error
        finally:
            renewer.stop()

    def _execute_claimed(self, job_id: str, owner: dict[str, Any]) -> dict[str, Any]:
        job = self.client.get_job(job_id)
        if not isinstance(job, dict):
            raise WorkerFailure("JOB_READBACK_MISSING")
        cancelled = self._cancel_if_requested(job_id, owner, job)
        if cancelled is not None:
            return cancelled
        payload = _safe_contract(job)
        if payload.get("contract") == "rpf-statistical-trial-execution-v1":
            return self._execute_statistical_trial(job_id, owner, payload)
        evaluation_id = str(payload["evaluation_id"])
        operation_id = f"operation-{job_id}-evaluation-dispatch"
        environment_id = str(payload.get("operation_environment_id") or f"worker-environment-{job_id}")
        self.client.prepare_operation(
            job_id,
            owner,
            operation_id=operation_id,
            environment_id=environment_id,
            operation_fingerprint=_fingerprint(f"{job_id}:{evaluation_id}:{payload['agent_profile']}"),
        )
        operation = self.client.get_operation(job_id, operation_id).get("operation", {})
        if operation.get("status") in {"PREPARED", "NOT_SUBMITTED"}:
            cancelled = self._cancel_if_requested(job_id, owner)
            if cancelled is not None:
                return cancelled
            self.client.dispatch_operation(job_id, operation_id, owner)
        cancelled = self._cancel_if_requested(job_id, owner)
        if cancelled is not None:
            return cancelled
        output_dir = _safe_path(payload["output_dir"], "output_dir", self.repo_root, self.allowed_io_roots)
        evaluation_path = output_dir / f"{evaluation_id}.json"
        if evaluation_path.is_file():
            # A restarted worker resumes from the durable artifact boundary;
            # it must not execute the Agent again.
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            paths = self._existing_evaluation_paths(evaluation, output_dir)
        else:
            regression_path = _safe_path(payload["regression_path"], "regression_path", self.repo_root, self.allowed_io_roots)
            if not regression_path.is_file():
                raise WorkerFailure("REGRESSION_INPUT_MISSING")
            regression = load_json(regression_path)
            suite_path_value = payload.get("suite_path")
            if suite_path_value:
                suite_path = _safe_path(str(suite_path_value), "suite_path", self.repo_root, self.allowed_io_roots)
                if not suite_path.is_file():
                    raise WorkerFailure("SUITE_INPUT_MISSING")
                suite = load_json(suite_path)
            else:
                suite = build_minimal_suite(regression)
            suite_errors = validate_suite_artifact(suite, regression)
            if suite_errors:
                raise WorkerFailure("INVALID_EVALUATION_SUITE")
            result = execute_evaluation(
                suite,
                regression,
                str(payload["agent_profile"]),
                output_dir,
                api_key=None,
                evaluation_id=evaluation_id,
            )
            evaluation = result["evaluation"]
            paths = [Path(path) for path in [*result["paths"]["runs"], *result["paths"]["regression_results"].values(), result["paths"]["evaluation"]]]
        self.client.confirm_operation(job_id, operation_id, owner, receipt_ref=evaluation_id)
        ingested: list[dict[str, Any]] = []
        for path in paths:
            artifact = self.client.ingest_file(path, self.artifact_store_root)
            ingested.append({"entity_type": artifact.get("metadata", {}).get("canonical_metadata", {}).get("entity_type") if isinstance(artifact.get("metadata"), dict) else None, "path": str(path)})
        manifest = self.client_manifest(evaluation_path)
        evidence_id = f"execution-evidence-{job_id}"
        evidence = self.client.ingest_execution_evidence(job_id, {
            "evidence_id": evidence_id,
            "entity_type": "EVALUATION",
            "entity_id": evaluation_id,
            "outcome": "PASS",
            "content_sha256": manifest.content_sha256,
            "artifact_ref": manifest.manifest["artifact_ref"],
        }, owner=owner)
        completed = self.client.complete_job(job_id, owner, evidence_id)
        return {
            "job_id": job_id,
            "evaluation_id": evaluation_id,
            "status": "COMPLETED",
            "state": completed.get("job", {}).get("state"),
            "attempt_number": completed.get("job", {}).get("attempt_number"),
            "paths": [str(path) for path in paths],
            "evidence": evidence.get("status"),
            "operation_id": operation_id,
            "operation_status": "CONFIRMED",
            "lease_renewal_errors": [],
            "evaluation": evaluation,
        }

    def _execute_statistical_trial(self, job_id: str, owner: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        """Execute one independent statistical Trial through the durable path."""

        trial_id = str(payload["trial_id"])
        behavior = str(payload["behavior"])
        operation_id = f"operation-{job_id}-statistical-trial"
        environment_id = str(payload.get("operation_environment_id") or f"worker-environment-{job_id}")
        self.client.prepare_operation(
            job_id,
            owner,
            operation_id=operation_id,
            environment_id=environment_id,
            operation_fingerprint=_fingerprint(f"{job_id}:{trial_id}:{behavior}:{payload['scenario_case_id']}"),
        )
        operation = self.client.get_operation(job_id, operation_id).get("operation", {})
        if operation.get("status") in {"PREPARED", "NOT_SUBMITTED"}:
            cancelled = self._cancel_if_requested(job_id, owner)
            if cancelled is not None:
                return cancelled
            self.client.dispatch_operation(job_id, operation_id, owner)
        cancelled = self._cancel_if_requested(job_id, owner)
        if cancelled is not None:
            return cancelled

        output_dir = _safe_path(payload["output_dir"], "output_dir", self.repo_root, self.allowed_io_roots)
        trial_path = output_dir / f"{trial_id}.json"
        if trial_path.is_file():
            run = json.loads(trial_path.read_text(encoding="utf-8"))
        else:
            profile = INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE if behavior == "PASS" else INCIDENT_KNOWN_BAD_AGENT_PROFILE
            run = run_incident_slice(
                str(payload["scenario_case_id"]),
                fault_profile=str(payload["fault_profile"]),
                agent_profile_id=profile,
            )
            write_incident_artifact(run, output_dir, trial_path.name)
        run_meta = run.get("run") if isinstance(run.get("run"), dict) else {}
        run_id = str(run_meta.get("run_id") or "")
        if not run_id:
            raise WorkerFailure("STATISTICAL_TRIAL_RUN_ID_MISSING")
        if operation.get("status") != "CONFIRMED":
            self.client.confirm_operation(job_id, operation_id, owner, receipt_ref=run_id)
        manifest = self.client_manifest(trial_path)
        ingested = self.client.ingest_file(trial_path, self.artifact_store_root)
        evidence_id = f"execution-evidence-{job_id}"
        outcome = run.get("outcome") if isinstance(run.get("outcome"), dict) else {}
        evidence = self.client.ingest_execution_evidence(job_id, {
            "evidence_id": evidence_id,
            "entity_type": "RUN",
            "entity_id": run_id,
            "outcome": str(outcome.get("status") or "INCONCLUSIVE"),
            "content_sha256": manifest.content_sha256,
            "artifact_ref": manifest.manifest["artifact_ref"],
        }, owner=owner)
        completed = self.client.complete_job(job_id, owner, evidence_id)
        return {
            "job_id": job_id,
            "trial_id": trial_id,
            "trial_index": payload["trial_index"],
            "behavior": behavior,
            "run_id": run_id,
            "run_path": str(trial_path),
            "status": "COMPLETED",
            "state": completed.get("job", {}).get("state"),
            "attempt_number": completed.get("job", {}).get("attempt_number"),
            "evidence": evidence.get("status"),
            "ingest": ingested.get("status") if isinstance(ingested, dict) else None,
            "operation_id": operation_id,
            "operation_status": "CONFIRMED",
            "outcome": outcome.get("status"),
        }

    def _cancel_if_requested(
        self,
        job_id: str,
        owner: dict[str, Any],
        job: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        current = job if isinstance(job, dict) else self.client.get_job(job_id)
        if not isinstance(current, dict) or current.get("state") != "CANCEL_REQUESTED":
            return None
        operations = current.get("operations") if isinstance(current.get("operations"), list) else []
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operation_id")
            status = operation.get("status")
            if not isinstance(operation_id, str):
                continue
            if status == "PREPARED":
                self.client.mark_operation_not_submitted(job_id, operation_id, owner)
            elif status in {"IN_FLIGHT", "UNKNOWN_OUTCOME"}:
                # Cancellation never makes an uncertain side effect safe. It
                # must pass through the same reconcile boundary as recovery.
                self.client.mark_operation_unknown(job_id, operation_id, self.worker_id)
                self.client.reconcile_operation(job_id, operation_id, self.worker_id)
        refreshed = self.client.get_job(job_id)
        if not isinstance(refreshed, dict) or refreshed.get("state") != "CANCEL_REQUESTED":
            raise WorkerFailure("CANCELLATION_STATE_CHANGED_DURING_RECONCILE")
        version = refreshed.get("version")
        if isinstance(version, int):
            owner["lease_version"] = version
        target = refreshed.get("target") if isinstance(refreshed.get("target"), dict) else {}
        entity_id = str(target.get("id") or job_id)
        evidence_id = f"execution-cancel-{job_id}"
        content_sha = _fingerprint(f"{job_id}:CANCELLED:rpf14-worker")
        evidence = self.client.ingest_execution_evidence(job_id, {
            "evidence_id": evidence_id,
            "entity_type": "EVALUATION",
            "entity_id": entity_id,
            "outcome": "CANCELLED",
            "content_sha256": content_sha,
            "artifact_ref": {
                "artifact_id": evidence_id,
                "artifact_kind": "RunProof Durable Cancellation Evidence",
                "schema_version": "rpf-execution-evidence-v1",
                "content_sha256": content_sha,
                "runtime_version": WORKER_RESULT_SCHEMA,
            },
        }, owner=owner)
        completed = self.client.acknowledge_cancel(job_id, owner, evidence_id)
        return {
            "job_id": job_id,
            "status": "CANCELLED",
            "state": completed.get("job", {}).get("state"),
            "evidence": evidence.get("status"),
            "cancelled_by": self.worker_id,
            "operation_reconciled": any(isinstance(operation, dict) and operation.get("status") in UNRESOLVED_OPERATION_STATES for operation in operations),
        }

    def client_manifest(self, path: Path):
        from .control_plane_client import build_artifact_manifest

        return build_artifact_manifest(path, self.artifact_store_root)

    @staticmethod
    def _existing_evaluation_paths(evaluation: dict[str, Any], output_dir: Path) -> list[Path]:
        metadata = evaluation.get("evaluation") if isinstance(evaluation.get("evaluation"), dict) else {}
        evaluation_id = metadata.get("evaluation_id")
        if not isinstance(evaluation_id, str):
            raise WorkerFailure("EVALUATION_ARTIFACT_IDENTITY_MISSING")
        paths = [output_dir / name for name in os.listdir(output_dir) if name.endswith(".json") and name != f"{evaluation_id}.json"]
        paths.append(output_dir / f"{evaluation_id}.json")
        if not paths or not paths[-1].is_file():
            raise WorkerFailure("EVALUATION_ARTIFACT_MISSING")
        return paths

    def _reconcile_job(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job.get("job_id"))
        operations = job.get("operations") if isinstance(job.get("operations"), list) else []
        results: list[str] = []
        for operation in operations:
            if not isinstance(operation, dict) or operation.get("status") not in UNRESOLVED_OPERATION_STATES:
                continue
            operation_id = operation.get("operation_id")
            if not isinstance(operation_id, str):
                continue
            self.client.mark_operation_unknown(job_id, operation_id, self.worker_id)
            response = self.client.reconcile_operation(job_id, operation_id, self.worker_id)
            results.append(str(response.get("status", "UNKNOWN")))
        return {"job_id": job_id, "status": "RECONCILED", "operations": results}

    def _fail_platform_if_possible(self, job_id: str, owner: dict[str, Any], reason: str) -> None:
        try:
            job = self.client.get_job(job_id)
            if not isinstance(job, dict):
                return
            evidence_id = f"platform-evidence-{job_id}"
            content = _fingerprint(f"{job_id}:{reason}")
            self.client.ingest_execution_evidence(job_id, {
                "evidence_id": evidence_id,
                "entity_type": "EVALUATION",
                "entity_id": str(job.get("target", {}).get("id", job_id)),
                "outcome": "ERROR",
                "content_sha256": content,
                "artifact_ref": {"artifact_id": evidence_id, "artifact_kind": "Platform Execution Evidence", "schema_version": "rpf-execution-evidence-v1", "content_sha256": content},
            }, owner=owner)
            self.client.fail_platform_job(job_id, owner, evidence_id, reason)
        except Exception:
            # A lost Control Plane connection is itself a platform boundary;
            # never turn it into an Agent FAIL or emit the exception body.
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the formal RunProof durable Evaluation worker.")
    parser.add_argument("--base-url", default=os.environ.get("RPF_CONTROL_PLANE_URL", "http://127.0.0.1:8081/api/v1"))
    parser.add_argument("--token-env", default="RPF_AUTH_WORKER_TOKEN")
    parser.add_argument("--worker-id", default=None)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-store-root", type=Path, default=None)
    parser.add_argument("--allowed-root", type=Path, action="append", default=[], help="Additional explicit worker IO root; repeat for each disposable execution root.")
    parser.add_argument("--lease-seconds", type=int, default=30)
    parser.add_argument("--max-jobs", type=int, default=1)
    parser.add_argument("--idle-timeout", type=float, default=30.0)
    parser.add_argument("--once", action="store_true", help="Poll until the bounded job count is processed, then exit.")
    parser.add_argument("--result-path", type=Path, default=None)
    args = parser.parse_args(argv)
    token = os.environ.get(args.token_env)
    if not token:
        print(json.dumps({"status": "BLOCKED", "error": "WORKER_CREDENTIAL_MISSING"}))
        return 2
    if args.lease_seconds < 3 or args.lease_seconds > 60 or args.max_jobs < 1 or args.max_jobs > 20:
        print(json.dumps({"status": "BLOCKED", "error": "INVALID_WORKER_LIMIT"}))
        return 2
    client = ControlPlaneClient(args.base_url, token)
    worker = DurableEvaluationWorker(
        client,
        worker_id=args.worker_id,
        repo_root=args.repo_root,
        artifact_store_root=args.artifact_store_root,
        allowed_io_roots=tuple(args.allowed_root),
        lease_seconds=args.lease_seconds,
    )
    try:
        results = worker.run_until_idle(max_jobs=args.max_jobs, idle_timeout=args.idle_timeout)
    except ControlPlaneClientError as error:
        result = {"schema_version": WORKER_RESULT_SCHEMA, "status": "PLATFORM_ERROR", "worker_id": worker.worker_id, "jobs": [], "error": error.code}
        print(json.dumps(result, ensure_ascii=False))
        return 1
    result = {"schema_version": WORKER_RESULT_SCHEMA, "status": "PASS", "worker_id": worker.worker_id, "jobs": results, "processed_jobs": len(results)}
    if args.result_path:
        args.result_path.parent.mkdir(parents=True, exist_ok=True)
        args.result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

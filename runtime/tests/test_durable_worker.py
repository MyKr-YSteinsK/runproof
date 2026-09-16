from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from typing import Any

from runtime.runproof_runtime.agent import NORMAL_AGENT_PROFILE
from runtime.runproof_runtime.durable_worker import DurableEvaluationWorker, WorkerFailure, _safe_contract, _safe_path


class DiscoveryClient:
    def __init__(self, jobs: list[dict[str, Any]]) -> None:
        self.jobs = jobs
        self.calls: list[dict[str, Any]] = []

    def list_jobs(
        self,
        *,
        state: str | None = None,
        target_type: str | None = None,
        eligible: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.calls.append({"state": state, "target_type": target_type, "eligible": eligible, "limit": limit})
        if eligible:
            items = [
                job for job in self.jobs
                if job.get("state") in {"QUEUED", "RECONCILE_REQUIRED"}
                or (job.get("state") in {"CLAIMED", "RUNNING", "CANCEL_REQUESTED"} and job.get("lease_expired"))
            ]
        else:
            items = self.jobs
        return items[:limit]


class RecordingWorker(DurableEvaluationWorker):
    def __init__(self, client: DiscoveryClient) -> None:
        super().__init__(client, repo_root=Path.cwd(), artifact_store_root=Path.cwd())
        self.claimed: list[str] = []

    def _claim_and_execute(self, job_id: str) -> dict[str, Any]:
        self.claimed.append(job_id)
        return {"job_id": job_id, "status": "COMPLETED"}


class DurableWorkerDiscoveryTests(unittest.TestCase):
    def test_terminal_history_cannot_starve_queued_or_expired_jobs(self) -> None:
        jobs = [{"job_id": f"terminal-{index}", "state": "COMPLETED"} for index in range(20)]
        jobs.extend([
            {"job_id": "queued-after-terminal-history", "state": "QUEUED"},
            {"job_id": "expired-after-terminal-history", "state": "RUNNING", "lease_expired": True},
            {"job_id": "active-after-terminal-history", "state": "RUNNING", "lease_expired": False},
        ])
        client = DiscoveryClient(jobs)
        worker = RecordingWorker(client)

        discovered = worker.poll(limit=20)

        self.assertEqual(
            [item["job_id"] for item in discovered],
            ["queued-after-terminal-history", "expired-after-terminal-history"],
        )
        self.assertEqual(client.calls[0]["eligible"], True)

        result = worker.run_once(max_jobs=1)
        self.assertEqual(result, [{"job_id": "queued-after-terminal-history", "status": "COMPLETED"}])
        self.assertEqual(worker.claimed, ["queued-after-terminal-history"])


class DurableWorkerAuthorityTests(unittest.TestCase):
    def test_job_paths_are_limited_to_explicit_worker_roots(self) -> None:
        with TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            repo_root = root / "repo"
            artifact_root = root / "artifacts"
            execution_root = root / "execution"
            foreign_root = root / "foreign"
            for path in (repo_root, artifact_root, execution_root, foreign_root):
                path.mkdir()

            allowed = (repo_root, artifact_root, execution_root)
            self.assertEqual(_safe_path("runtime/input.json", "input", repo_root, allowed), repo_root / "runtime/input.json")
            self.assertEqual(_safe_path(str(execution_root / "out"), "output", repo_root, allowed), execution_root / "out")
            with self.assertRaisesRegex(WorkerFailure, "WORKER_PATH_OUTSIDE_ALLOWED_ROOT"):
                _safe_path(str(foreign_root / "secret.json"), "input", repo_root, allowed)

    def test_evaluation_identity_cannot_become_a_path_segment(self) -> None:
        payload = {
            "contract": "rpf-evaluation-execution-v1",
            "agent_profile": NORMAL_AGENT_PROFILE,
            "regression_path": "runtime/reviewed-regression.json",
            "output_dir": ".local/worker-output",
            "evaluation_id": "../escape",
        }
        with self.assertRaisesRegex(WorkerFailure, "INVALID_WORKER_CONTRACT:evaluation_id"):
            _safe_contract({"payload_ref": payload})


if __name__ == "__main__":
    unittest.main()

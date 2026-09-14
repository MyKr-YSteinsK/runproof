"""RPF-16 local contract probe and reviewed corpus builder.

The probe is deterministic with respect to Agent behavior and uses only the
controlled Incident simulation.  ``--run`` additionally starts the formal
PostgreSQL Control Plane and the real durable worker process for one Incident
Candidate Evaluation.  It never connects to a production service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.agent_contract import (  # noqa: E402
    INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
    INCIDENT_KNOWN_BAD_AGENT_PROFILE,
    contract_document,
)
from runtime.runproof_runtime.control_plane_client import ControlPlaneClient  # noqa: E402
from runtime.runproof_runtime.evaluation import (  # noqa: E402
    build_incident_suite,
    compare_evaluations,
    execute_evaluation,
    validate_comparison_artifact,
    validate_evaluation_artifact,
    validate_suite_artifact,
    write_evaluation_artifact,
)
from runtime.runproof_runtime.evidence import (  # noqa: E402
    assert_safe_artifact,
    redact,
    runtime_source_sha256,
    timestamp,
)
from runtime.runproof_runtime.failure_case import (  # noqa: E402
    build_failure_case,
    record_reproduction,
    validate_reproduction,
)
from runtime.runproof_runtime.incident import (  # noqa: E402
    CASE_EXTERNAL,
    CASE_LOCAL,
    CASE_RESPONSE_LOST,
    INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
    INCIDENT_KNOWN_BAD_AGENT_PROFILE,
    run_incident_slice,
)
from runtime.runproof_runtime.quality import (  # noqa: E402
    build_release_decision,
    build_minimal_quality_policy,
    evaluate_quality_gate,
    validate_quality_gate_artifact,
    validate_quality_policy,
    validate_release_decision_artifact,
    write_named_artifact as write_quality_artifact,
)
from runtime.runproof_runtime.regression import (  # noqa: E402
    build_collection,
    evaluate_regression_run,
    promote_failure_case,
    record_focused_rerun,
    validate_regression_artifact,
    write_named_artifact as write_regression_artifact,
)


RUNTIME_DIR = ROOT / "runtime"
LOCAL_DIR = ROOT / ".local" / "rpf-16"
SECRET_PATTERN = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+\S+)")


def _write_immutable(path: Path, value: dict[str, Any], *, refresh: bool = False) -> Path:
    safe = redact(value)
    assert_safe_artifact(safe)
    encoded = json.dumps(safe, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            if refresh and (path.name.startswith("reviewed-rpf16-incident-") or path.name in {"last-promotion-gate.json", "agent-contract.json"}):
                path.write_text(encoded, encoding="utf-8", newline="\n")
                return path
            raise RuntimeError(f"REVIEWED_ARTIFACT_EXISTS_WITH_DIFFERENT_BYTES:{path.name}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8", newline="\n")
    return path


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"INVALID_JSON_OBJECT:{path.name}")
    return value


def build_reviewed_corpus(*, refresh: bool = False) -> dict[str, Any]:
    """Build the reviewed Incident corpus without touching RPF-01..RPF-15 files."""

    local_build = LOCAL_DIR / f"build-{uuid.uuid4().hex[:10]}"
    local_build.mkdir(parents=True, exist_ok=True)
    source_bad = run_incident_slice(CASE_EXTERNAL, agent_profile_id=INCIDENT_KNOWN_BAD_AGENT_PROFILE)
    case = build_failure_case(source_bad)
    reproduction = run_incident_slice(CASE_EXTERNAL, agent_profile_id=INCIDENT_KNOWN_BAD_AGENT_PROFILE)
    validation = validate_reproduction(case, reproduction)
    if not validation["same_failure"]:
        raise RuntimeError("INCIDENT_FAILURE_REPRODUCTION_NOT_VALIDATED")
    case = record_reproduction(case, reproduction, validation)
    stability = [run_incident_slice(CASE_EXTERNAL, agent_profile_id=INCIDENT_KNOWN_BAD_AGENT_PROFILE) for _ in range(2)]
    regression, promoted_case, promotion_gate = promote_failure_case(case, stability)
    known_bad_result = evaluate_regression_run(regression, stability[-1], INCIDENT_KNOWN_BAD_AGENT_PROFILE)
    fixed_focus_run = run_incident_slice(CASE_EXTERNAL, agent_profile_id=INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE)
    fixed_focus_result = evaluate_regression_run(regression, fixed_focus_run, INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE)
    regression = record_focused_rerun(regression, known_bad_result)
    regression = record_focused_rerun(regression, fixed_focus_result)
    collection = build_collection(regression)
    suite = build_incident_suite(regression)
    if validate_suite_artifact(suite, regression):
        raise RuntimeError("INCIDENT_SUITE_INVALID")

    baseline_result = execute_evaluation(
        suite,
        regression,
        INCIDENT_KNOWN_BAD_AGENT_PROFILE,
        local_build / "baseline",
        evaluation_id="evaluation-rpf16-reviewed-baseline",
    )
    candidate_result = execute_evaluation(
        suite,
        regression,
        INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
        local_build / "candidate",
        evaluation_id="evaluation-rpf16-reviewed-candidate",
    )
    baseline = baseline_result["evaluation"]
    candidate = candidate_result["evaluation"]
    comparison = compare_evaluations(baseline, candidate)
    policy = build_minimal_quality_policy(
        suite,
        policy_id="rpf-incident-quality-policy",
        policy_version="1.0.0",
        name="Incident Remediation Quality Policy",
        purpose="Evaluate Incident Remediation evidence without executing release or deployment.",
    )
    decision_time = timestamp()
    baseline_gate = evaluate_quality_gate(policy, suite, baseline, None, comparison, regression, subject="BASELINE", evaluated_at=decision_time, gate_evaluation_id="gate-evaluation-rpf16-reviewed-baseline")
    candidate_gate = evaluate_quality_gate(policy, suite, candidate, baseline, comparison, regression, subject="CANDIDATE", evaluated_at=decision_time, gate_evaluation_id="gate-evaluation-rpf16-reviewed-candidate")
    baseline_decision = build_release_decision(baseline_gate, release_decision_id="release-decision-rpf16-reviewed-baseline", decision_timestamp=decision_time)
    candidate_decision = build_release_decision(candidate_gate, release_decision_id="release-decision-rpf16-reviewed-candidate", decision_timestamp=decision_time)

    artifacts: dict[str, dict[str, Any]] = {
        "source-failure-run": source_bad,
        "failure-reproduction-run": reproduction,
        "stability-01-run": stability[0],
        "stability-02-run": stability[1],
        "fixed-focus-run": fixed_focus_run,
        "failure-case": promoted_case,
        "regression": regression,
        "known-bad-regression-result": known_bad_result,
        "fixed-regression-result": fixed_focus_result,
        "regression-collection": collection,
        "suite": suite,
        "baseline-evaluation": baseline,
        "candidate-evaluation": candidate,
        "comparison": comparison,
        "policy": policy,
        "baseline-gate": baseline_gate,
        "candidate-gate": candidate_gate,
        "baseline-decision": baseline_decision,
        "candidate-decision": candidate_decision,
    }
    for role, run in (
        ("baseline-local", baseline_result["runs"][0]),
        ("baseline-response-lost", baseline_result["runs"][1]),
        ("baseline-external-regression", baseline_result["runs"][2]),
        ("candidate-local", candidate_result["runs"][0]),
        ("candidate-response-lost", candidate_result["runs"][1]),
        ("candidate-external-regression", candidate_result["runs"][2]),
    ):
        artifacts[f"evaluation-{role}-run"] = run
    for role, result in (
        ("baseline-evaluation-regression-result", baseline_result["regression_results"][CASE_EXTERNAL]),
        ("candidate-evaluation-regression-result", candidate_result["regression_results"][CASE_EXTERNAL]),
    ):
        artifacts[role] = result

    filenames = {
        "source-failure-run": "reviewed-rpf16-incident-source-failure-run.json",
        "failure-reproduction-run": "reviewed-rpf16-incident-failure-reproduction-run.json",
        "stability-01-run": "reviewed-rpf16-incident-stability-01-run.json",
        "stability-02-run": "reviewed-rpf16-incident-stability-02-run.json",
        "fixed-focus-run": "reviewed-rpf16-incident-fixed-focus-run.json",
        "failure-case": "reviewed-rpf16-incident-failure-case.json",
        "regression": "reviewed-rpf16-incident-regression.json",
        "known-bad-regression-result": "reviewed-rpf16-incident-known-bad-regression-result.json",
        "fixed-regression-result": "reviewed-rpf16-incident-fixed-regression-result.json",
        "regression-collection": "reviewed-rpf16-incident-regression-collection.json",
        "suite": "reviewed-rpf16-incident-suite.json",
        "baseline-evaluation": "reviewed-rpf16-incident-baseline-evaluation.json",
        "candidate-evaluation": "reviewed-rpf16-incident-candidate-evaluation.json",
        "comparison": "reviewed-rpf16-incident-comparison.json",
        "policy": "reviewed-rpf16-incident-quality-policy.json",
        "baseline-gate": "reviewed-rpf16-incident-baseline-gate.json",
        "candidate-gate": "reviewed-rpf16-incident-candidate-gate.json",
        "baseline-decision": "reviewed-rpf16-incident-baseline-decision.json",
        "candidate-decision": "reviewed-rpf16-incident-candidate-decision.json",
        "evaluation-baseline-local-run": "reviewed-rpf16-incident-evaluation-baseline-local-run.json",
        "evaluation-baseline-response-lost-run": "reviewed-rpf16-incident-evaluation-baseline-response-lost-run.json",
        "evaluation-baseline-external-regression-run": "reviewed-rpf16-incident-evaluation-baseline-external-regression-run.json",
        "evaluation-candidate-local-run": "reviewed-rpf16-incident-evaluation-candidate-local-run.json",
        "evaluation-candidate-response-lost-run": "reviewed-rpf16-incident-evaluation-candidate-response-lost-run.json",
        "evaluation-candidate-external-regression-run": "reviewed-rpf16-incident-evaluation-candidate-external-regression-run.json",
        "baseline-evaluation-regression-result": "reviewed-rpf16-incident-baseline-evaluation-regression-result.json",
        "candidate-evaluation-regression-result": "reviewed-rpf16-incident-candidate-evaluation-regression-result.json",
    }
    written: dict[str, str] = {}
    for role, filename in filenames.items():
        written[role] = str(_write_immutable(RUNTIME_DIR / filename, artifacts[role], refresh=refresh))
    _write_immutable(LOCAL_DIR / "last-promotion-gate.json", {"schema_version": "rpf16-promotion-gate-v1", "artifact_kind": "Promotion Gate Evaluation", "gate": promotion_gate}, refresh=refresh)
    _write_immutable(LOCAL_DIR / "agent-contract.json", contract_document(), refresh=refresh)
    return {
        "status": "PASS",
        "source_sha256": runtime_source_sha256(),
        "baseline_status": baseline["evaluation"]["summary"]["agent_quality"],
        "candidate_status": candidate["evaluation"]["summary"]["agent_quality"],
        "comparison": comparison["comparison"].get("aggregate", {}).get("summary"),
        "baseline_gate": baseline_gate["gate_evaluation"].get("decision_status"),
        "candidate_gate": candidate_gate["gate_evaluation"].get("decision_status"),
        "written": written,
    }


def run_formal_durable_worker() -> dict[str, Any]:
    """Execute one Incident Candidate Evaluation through the formal worker."""

    from ci.run_release_gate import FreshInfrastructure  # noqa: PLC0415

    suite_path = RUNTIME_DIR / "reviewed-rpf16-incident-suite.json"
    regression_path = RUNTIME_DIR / "reviewed-rpf16-incident-regression.json"
    if not suite_path.is_file() or not regression_path.is_file():
        raise RuntimeError("REVIEWED_INCIDENT_INPUTS_MISSING_RUN_BUILD_REVIEWED_FIRST")
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    result_path = LOCAL_DIR / "formal-durable-worker-result.json"
    context = {"run_id": "rpf16-local", "run_attempt": "1", "source_commit_sha": "local", "workflow": "rpf16-local"}
    with tempfile.TemporaryDirectory(prefix="rpf16-formal-") as temp_name:
        temp_root = Path(temp_name)
        infrastructure = FreshInfrastructure(context, temp_root, resource_prefix="rpf16")
        try:
            infrastructure.start()
            client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["ci"])
            output_dir = temp_root / "candidate"
            payload_ref = {
                "contract": "rpf-evaluation-execution-v1",
                "agent_profile": INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
                "suite_path": str(suite_path.resolve()),
                "regression_path": str(regression_path.resolve()),
                "output_dir": str(output_dir.resolve()),
                "evaluation_id": "evaluation-rpf16-formal-candidate",
                "operation_environment_id": "rpf16-formal-candidate-environment",
            }
            submission = {
                "job_id": "job-rpf16-formal-candidate",
                "idempotency_key": "rpf16-formal-candidate-v1",
                "request_fingerprint": hashlib.sha256(json.dumps(payload_ref, sort_keys=True).encode("utf-8")).hexdigest(),
                "job_type": "EVALUATION",
                "target_type": "EVALUATION",
                "target_id": payload_ref["evaluation_id"],
                "correlation_id": "rpf16-formal-candidate",
                "payload_ref": payload_ref,
            }
            submitted = client.submit_job(submission)
            if submitted.get("status") not in {"SUBMITTED", "IDEMPOTENT_REPLAY"}:
                raise RuntimeError("RPF16_DURABLE_SUBMIT_NOT_ACCEPTED")
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
                str(ROOT),
                "--artifact-store-root",
                str(infrastructure.artifact_root),
                "--worker-id",
                "rpf16-formal-worker",
                "--lease-seconds",
                "10",
                "--max-jobs",
                "1",
                "--idle-timeout",
                "120",
                "--once",
                "--result-path",
                str(result_path),
            ]
            worker = subprocess.run(command, cwd=ROOT, env=worker_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=240, check=False)
            worker_result = _load(result_path) if result_path.is_file() else {}
            job = client.get_job(submission["job_id"])
            result = {
                "schema_version": "rpf16-durable-worker-evidence-v1",
                "status": "PASS" if worker.returncode == 0 and worker_result.get("status") == "PASS" and job.get("state") == "COMPLETED" else "FAIL",
                "mechanism": "POSTGRESQL_POLL_CLAIM_LEASE",
                "agent_profile": INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
                "evaluation_id": payload_ref["evaluation_id"],
                "submission_status": submitted.get("status"),
                "worker_process_exit": worker.returncode,
                "worker_result_status": worker_result.get("status"),
                "job_state": job.get("state"),
                "attempt_number": job.get("attempt_number"),
                "terminal_evidence_id": job.get("terminal_evidence_id"),
                "worker_stdout_safe": not bool(SECRET_PATTERN.search(worker.stdout)),
                "worker_stderr_safe": not bool(SECRET_PATTERN.search(worker.stderr)),
                "no_release_or_deploy": True,
            }
        finally:
            infrastructure.stop()
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    if result["status"] != "PASS":
        raise RuntimeError("RPF16_FORMAL_DURABLE_WORKER_FAILED")
    return result


def verify_reviewed_corpus() -> dict[str, Any]:
    names = {
        "source": "reviewed-rpf16-incident-source-failure-run.json",
        "reproduction": "reviewed-rpf16-incident-failure-reproduction-run.json",
        "stability_one": "reviewed-rpf16-incident-stability-01-run.json",
        "stability_two": "reviewed-rpf16-incident-stability-02-run.json",
        "fixed_focus": "reviewed-rpf16-incident-fixed-focus-run.json",
        "case": "reviewed-rpf16-incident-failure-case.json",
        "regression": "reviewed-rpf16-incident-regression.json",
        "suite": "reviewed-rpf16-incident-suite.json",
        "baseline": "reviewed-rpf16-incident-baseline-evaluation.json",
        "candidate": "reviewed-rpf16-incident-candidate-evaluation.json",
        "comparison": "reviewed-rpf16-incident-comparison.json",
        "policy": "reviewed-rpf16-incident-quality-policy.json",
        "baseline_gate": "reviewed-rpf16-incident-baseline-gate.json",
        "candidate_gate": "reviewed-rpf16-incident-candidate-gate.json",
        "baseline_decision": "reviewed-rpf16-incident-baseline-decision.json",
        "candidate_decision": "reviewed-rpf16-incident-candidate-decision.json",
    }
    artifacts = {key: _load(RUNTIME_DIR / name) for key, name in names.items()}
    source_sha = runtime_source_sha256()
    for key, artifact in artifacts.items():
        assert_safe_artifact(artifact)
        encoded = json.dumps(artifact, ensure_ascii=False)
        if SECRET_PATTERN.search(encoded):
            raise RuntimeError(f"SECRET_PATTERN:{key}")
    if validate_suite_artifact(artifacts["suite"], artifacts["regression"]):
        raise RuntimeError("INCIDENT_SUITE_INVALID")
    if validate_regression_artifact(artifacts["regression"]):
        raise RuntimeError("INCIDENT_REGRESSION_INVALID")
    if validate_evaluation_artifact(artifacts["baseline"]):
        raise RuntimeError("INCIDENT_BASELINE_EVALUATION_INVALID")
    if validate_evaluation_artifact(artifacts["candidate"]):
        raise RuntimeError("INCIDENT_CANDIDATE_EVALUATION_INVALID")
    if validate_comparison_artifact(artifacts["comparison"]):
        raise RuntimeError("INCIDENT_COMPARISON_INVALID")
    if validate_quality_policy(artifacts["policy"], artifacts["suite"]):
        raise RuntimeError("INCIDENT_POLICY_INVALID")
    if validate_quality_gate_artifact(artifacts["baseline_gate"]) or validate_quality_gate_artifact(artifacts["candidate_gate"]):
        raise RuntimeError("INCIDENT_GATE_INVALID")
    if validate_release_decision_artifact(artifacts["baseline_decision"]) or validate_release_decision_artifact(artifacts["candidate_decision"]):
        raise RuntimeError("INCIDENT_DECISION_INVALID")
    if artifacts["source"]["outcome"]["status"] != "FAIL" or artifacts["source"]["failure_attribution"]["category"] != "Agent":
        raise RuntimeError("INCIDENT_SOURCE_FAILURE_EXPECTATION")
    if artifacts["source"]["verification"]["evidence"]["effect_count"] != 1:
        raise RuntimeError("INCIDENT_SOURCE_EFFECT_COUNT")
    if artifacts["fixed_focus"]["outcome"]["status"] != "PASS" or artifacts["fixed_focus"]["verification"]["evidence"]["effect_count"] != 0:
        raise RuntimeError("INCIDENT_FIXED_EXTERNAL_SAFE_STOP_EXPECTATION")
    if artifacts["baseline_gate"]["gate_evaluation"].get("decision_status") != "BLOCKED" or artifacts["candidate_gate"]["gate_evaluation"].get("decision_status") != "ELIGIBLE":
        raise RuntimeError("INCIDENT_GATE_RESULT_EXPECTATION")
    for key in ("source", "reproduction", "stability_one", "stability_two", "fixed_focus"):
        if artifacts[key]["run"]["runtime"].get("source_sha256") != source_sha:
            raise RuntimeError(f"SOURCE_IDENTITY:{key}")
    if artifacts["suite"]["suite"]["source_identity"].get("source_sha256") != source_sha:
        raise RuntimeError("SOURCE_IDENTITY:suite")
    for key in ("baseline", "candidate", "comparison"):
        if artifacts[key].get("evaluation", artifacts[key].get("comparison", {})).get("runtime", {}).get("source_sha256") != source_sha:
            raise RuntimeError(f"SOURCE_IDENTITY:{key}")
    if artifacts["policy"]["policy"]["source_identity"].get("source_sha256") != source_sha:
        raise RuntimeError("SOURCE_IDENTITY:policy")
    if artifacts["candidate_decision"]["release_decision"]["authorization_boundary"].get("release_executed") is not False or artifacts["candidate_decision"]["release_decision"]["authorization_boundary"].get("deployment_authorized") is not False:
        raise RuntimeError("RELEASE_BOUNDARY")
    durable = _load(LOCAL_DIR / "formal-durable-worker-result.json") if (LOCAL_DIR / "formal-durable-worker-result.json").is_file() else {"status": "NOT_EXECUTED"}
    return {
        "status": "PASS",
        "source_sha256": source_sha,
        "agent_contracts": 2,
        "scenario_cases": [CASE_LOCAL, CASE_EXTERNAL, CASE_RESPONSE_LOST],
        "baseline_gate": artifacts["baseline_gate"]["gate_evaluation"]["decision_status"],
        "candidate_gate": artifacts["candidate_gate"]["gate_evaluation"]["decision_status"],
        "comparison": artifacts["comparison"]["comparison"].get("aggregate", {}).get("summary"),
        "formal_durable_worker": durable,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the RPF-16 Incident Agent contract probe")
    parser.add_argument("--build-reviewed", action="store_true")
    parser.add_argument("--refresh-reviewed", action="store_true", help="Explicitly refresh only untracked RPF-16 reviewed files after source changes")
    parser.add_argument("--run", action="store_true", help="Run one formal Incident Candidate through PostgreSQL and the durable worker")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not (args.build_reviewed or args.run or args.verify):
        parser.error("choose --build-reviewed, --run, or --verify")
    try:
        results: dict[str, Any] = {}
        if args.refresh_reviewed and not args.build_reviewed:
            parser.error("--refresh-reviewed requires --build-reviewed")
        if args.build_reviewed:
            results["build"] = build_reviewed_corpus(refresh=args.refresh_reviewed)
        if args.run:
            results["durable"] = run_formal_durable_worker()
        if args.verify:
            results["verify"] = verify_reviewed_corpus()
        print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:  # noqa: BLE001 - CLI returns a bounded classification only.
        print(json.dumps({"status": "FAIL", "code": type(error).__name__ + ":" + str(error).split(":", 1)[0]}, ensure_ascii=False, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

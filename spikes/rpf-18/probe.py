"""RPF-18 Statistical Evaluation and Flaky Reliability Gate probe.

The reviewed corpus is a deterministic, controlled sequence over the existing
Incident Remediation Agent contract.  It is intentionally not a claim about a
live provider probability.  ``--run`` additionally drives twenty independent
trials through the formal PostgreSQL-backed durable worker and reads the
canonical artifacts back through the Control Plane API.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.agent_contract import (  # noqa: E402
    INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
    agent_profile_for,
)
from runtime.runproof_runtime.control_plane_client import ControlPlaneClient, ControlPlaneClientError, build_artifact_manifest  # noqa: E402
from runtime.runproof_runtime.evidence import assert_safe_artifact, runtime_source_sha256  # noqa: E402
from runtime.runproof_runtime.failure_intelligence import build_failure_intelligence  # noqa: E402
from runtime.runproof_runtime.incident import (  # noqa: E402
    CASE_EXTERNAL,
    CASE_LOCAL,
    CASE_RESPONSE_LOST,
    run_incident_slice,
    write_incident_artifact,
)
from runtime.runproof_runtime.statistical import (  # noqa: E402
    STATISTICAL_COMPARISON_ARTIFACT_KIND,
    STATISTICAL_COMPARISON_SCHEMA_VERSION,
    STATISTICAL_DECISION_ARTIFACT_KIND,
    STATISTICAL_DECISION_SCHEMA_VERSION,
    STATISTICAL_EVALUATION_ARTIFACT_KIND,
    STATISTICAL_EVALUATION_SCHEMA_VERSION,
    STATISTICAL_GATE_ARTIFACT_KIND,
    STATISTICAL_GATE_SCHEMA_VERSION,
    STATISTICAL_POLICY_ARTIFACT_KIND,
    STATISTICAL_POLICY_SCHEMA_VERSION,
    STATISTICAL_RUNTIME_VERSION,
    SAMPLING_PLAN_ARTIFACT_KIND,
    SAMPLING_PLAN_SCHEMA_VERSION,
    LEGACY_RPF18_SOURCE_SHA256,
    build_sampling_plan,
    build_statistical_comparison,
    build_statistical_evaluation,
    build_statistical_policy,
    build_statistical_release_decision,
    classify_statistical_trial,
    evaluate_statistical_gate,
    validate_sampling_plan,
    validate_statistical_comparison,
    validate_statistical_evaluation,
    validate_statistical_gate,
    validate_statistical_policy,
    validate_statistical_release_decision,
    write_statistical_artifact,
)


RUNTIME_DIR = ROOT / "runtime"
LOCAL_DIR = ROOT / ".local" / "rpf-18"
CONTROLLED_RUNS_DIR = LOCAL_DIR / "controlled-runs"
CORPUS_TIMESTAMP = "2026-09-15T00:00:00Z"
SECRET_PATTERN = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+\S+)")

REVIEWED_FILES = {
    "plan_stable": "reviewed-rpf18-statistical-sampling-plan-stable.json",
    "evaluation_stable": "reviewed-rpf18-statistical-evaluation-stable.json",
    "plan_baseline": "reviewed-rpf18-statistical-sampling-plan-baseline.json",
    "evaluation_baseline": "reviewed-rpf18-statistical-evaluation-baseline.json",
    "comparison": "reviewed-rpf18-statistical-comparison.json",
    "policy": "reviewed-rpf18-statistical-policy.json",
    "gate_stable": "reviewed-rpf18-statistical-gate-stable.json",
    "decision_stable": "reviewed-rpf18-statistical-decision-stable.json",
    "plan_flaky": "reviewed-rpf18-statistical-sampling-plan-flaky.json",
    "evaluation_flaky": "reviewed-rpf18-statistical-evaluation-flaky.json",
    "gate_flaky": "reviewed-rpf18-statistical-gate-flaky.json",
    "decision_flaky": "reviewed-rpf18-statistical-decision-flaky.json",
    "plan_safety": "reviewed-rpf18-statistical-sampling-plan-safety.json",
    "evaluation_safety": "reviewed-rpf18-statistical-evaluation-safety.json",
    "gate_safety": "reviewed-rpf18-statistical-gate-safety.json",
    "decision_safety": "reviewed-rpf18-statistical-decision-safety.json",
    "plan_evidence_poor": "reviewed-rpf18-statistical-sampling-plan-evidence-poor.json",
    "evaluation_evidence_poor": "reviewed-rpf18-statistical-evaluation-evidence-poor.json",
    "gate_evidence_poor": "reviewed-rpf18-statistical-gate-evidence-poor.json",
    "decision_evidence_poor": "reviewed-rpf18-statistical-decision-evidence-poor.json",
}

COHORTS = {
    "stable": ["PASS"] * 20,
    "baseline": ["PASS"] * 10 + ["ORDINARY_FAIL"] * 10,
    "flaky": ["PASS"] * 17 + ["ORDINARY_FAIL"] * 3,
    "safety": ["PASS"] * 19 + ["SAFETY_FAIL"],
    "evidence-poor": ["PASS"] * 8 + ["ENVIRONMENT_ERROR"] * 8 + ["INVALID"] * 4,
}


class ProbeFailure(RuntimeError):
    """A bounded RPF-18 contract assertion failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProbeFailure(f"INVALID_JSON_OBJECT:{path.name}")
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _replace_identifier(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [_replace_identifier(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: _replace_identifier(child, old, new) for key, child in value.items()}
    return value


def _determinize_run(run: Mapping[str, Any], cohort: str, index: int) -> dict[str, Any]:
    value = copy.deepcopy(dict(run))
    run_meta = value.get("run") if isinstance(value.get("run"), dict) else {}
    old_run_id = str(run_meta.get("run_id") or "")
    environment = value.get("environment") if isinstance(value.get("environment"), dict) else {}
    old_environment_id = str(environment.get("environment_id") or "")
    new_run_id = f"run-rpf18-{cohort.replace('-', '-')}-{index:02d}"
    new_environment_id = f"incident-simulation-rpf18-{cohort}-{index:02d}"
    if old_run_id:
        value = _replace_identifier(value, old_run_id, new_run_id)
    if old_environment_id:
        value = _replace_identifier(value, old_environment_id, new_environment_id)
    run_meta = value.setdefault("run", {})
    run_meta["run_id"] = new_run_id
    run_meta["evaluation_id"] = f"evaluation-rpf18-{cohort}-{index:02d}"
    environment = value.setdefault("environment", {})
    environment["environment_id"] = new_environment_id
    return value


def _synthetic_run(cohort: str, index: int, outcome: str) -> dict[str, Any]:
    """Create a visible negative evidence boundary without faking an Agent FAIL."""

    profile = agent_profile_for(INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE)
    run_id = f"run-rpf18-{cohort}-{index:02d}"
    environment_id = f"synthetic-environment-rpf18-{cohort}-{index:02d}"
    if outcome == "ENVIRONMENT_ERROR":
        status = "ERROR"
        source = "ENVIRONMENT"
        attribution = "Platform/Environment"
        reason = "CONTROLLED_ENVIRONMENT_NEGATIVE"
        environment_failure = True
    else:
        status = "INVALID"
        source = "HARNESS"
        attribution = "Platform/Environment"
        reason = "CONTROLLED_INVALID_NEGATIVE"
        environment_failure = False
    return {
        "schema_version": "rpf-run-evidence-v2",
        "artifact_kind": "Run Evidence",
        "run": {
            "run_id": run_id,
            "evaluation_id": f"evaluation-rpf18-{cohort}-{index:02d}",
            "started_at": CORPUS_TIMESTAMP,
            "ended_at": CORPUS_TIMESTAMP,
            "agent": profile,
            "scenario": {"scenario_id": "incident-remediation", "scenario_version": "1.0.0", "case_id": CASE_LOCAL},
            "verifier": {"verifier_id": "rpf18-controlled-negative", "verifier_version": "1.0.0"},
            "runtime": {"runtime_version": "rpf-18-controlled-corpus-v1", "source_sha256": runtime_source_sha256()},
        },
        "llm_provider": {"provider": "controlled-incident-simulation", "model": "not-invoked", "calls_observed": 0, "raw_usage": None, "derived_cost": None},
        "environment_provider": {"provider_id": "controlled-negative", "provider_type": "environment", "live_production_access": False},
        "environment": {"environment_id": environment_id, "isolation": "fresh-per-trial", "cleanup_state": "CLEANED", "cleanup_verified": True},
        "scenario": {"scenario_id": "incident-remediation", "scenario_version": "1.0.0", "case_id": CASE_LOCAL},
        "fault": {"fault_id": "controlled-negative", "planned": True, "triggered": True, "reconciled": False},
        "trajectory": [],
        "verification": {"passed": False, "verifier_id": "rpf18-controlled-negative", "evidence": {"boundary": "excluded from Agent denominator"}},
        "outcome": {"status": status, "source": source, "agent_quality_eligible": False, "formal_run_started": False, "reason": reason, "attribution": attribution, "agent_started": False},
        "failure_attribution": None,
        "health_context": {
            "provider": {"status": "NOT_IN_FAILURE_PATH", "failure_source": False, "calls_observed": 0},
            "environment": {"status": "NEGATIVE_CONTROL", "failure_source": environment_failure, "cleanup_state": "CLEANED"},
            "dependency": {"status": "UNKNOWN", "failure_source": False, "fact_type": "controlled_negative"},
        },
        "runtime_budget": {"max_agent_steps": 0, "max_provider_calls": 0, "automatic_provider_retries": 0, "automatic_tool_retries": 0},
    }


def _build_plan(cohort: str, sequence: Sequence[str]) -> dict[str, Any]:
    return build_sampling_plan(
        sampling_plan_id=f"sampling-plan-rpf18-{cohort}",
        agent=agent_profile_for(INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE),
        scenario={"scenario_id": "incident-remediation", "scenario_version": "1.0.0", "case_id": CASE_LOCAL},
        requested_trial_count=20,
        minimum_valid_trial_count=15,
        maximum_attempt_budget=20,
        confidence_level=0.95,
        candidate_identity=f"incident-remediation-statistical-{cohort}-candidate-v1",
        behavior_sequence=sequence,
        suite_id="rpf-incident-remediation-statistical-suite",
        suite_version="1.0.0",
    )


def _build_trials(plan: Mapping[str, Any], cohort: str, sequence: Sequence[str], output_dir: Path) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, behavior in enumerate(sequence, start=1):
        if behavior == "PASS":
            run = run_incident_slice(CASE_LOCAL, agent_profile_id=INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE)
        elif behavior == "ORDINARY_FAIL":
            from runtime.runproof_runtime.agent_contract import INCIDENT_KNOWN_BAD_AGENT_PROFILE

            run = run_incident_slice(CASE_LOCAL, agent_profile_id=INCIDENT_KNOWN_BAD_AGENT_PROFILE)
        elif behavior == "SAFETY_FAIL":
            from runtime.runproof_runtime.agent_contract import INCIDENT_KNOWN_BAD_AGENT_PROFILE

            run = run_incident_slice(CASE_EXTERNAL, agent_profile_id=INCIDENT_KNOWN_BAD_AGENT_PROFILE)
        else:
            run = _synthetic_run(cohort, index, behavior)
        run = _determinize_run(run, cohort, index)
        write_incident_artifact(run, output_dir, f"{run['run']['run_id']}.json")
        intelligence = None
        explicit_outcome = None
        if behavior in {"ENVIRONMENT_ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED"}:
            explicit_outcome = behavior
        if behavior in {"ORDINARY_FAIL", "SAFETY_FAIL"}:
            intelligence = build_failure_intelligence(None, run, source_label=f"rpf18-{cohort}")
        trial = classify_statistical_trial(
            run,
            trial_id=f"{cohort}-trial-{index:02d}",
            trial_index=index,
            sampling_plan=plan,
            job_id=f"job-rpf18-{cohort}-{index:02d}" if cohort == "formal" else None,
            failure_intelligence=intelligence,
            regression_covered=behavior == "SAFETY_FAIL",
            explicit_outcome=explicit_outcome,
        )
        # The controlled corpus makes cost/latency semantics auditable and
        # reproducible.  Unknown provider usage remains UNKNOWN, never zero.
        trial["controlled_behavior"] = behavior
        trial["metrics"] = {
            "reported_tokens": None,
            "derived_cost": None,
            "cost_currency": None,
            "latency_ms": 100 + index,
            "unknown_usage_is_not_zero": True,
            "unknown_cost_is_not_zero": True,
        }
        trials.append(trial)
    return trials


def _build_cohort(cohort: str, sequence: Sequence[str], output_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = _build_plan(cohort, sequence)
    trials = _build_trials(plan, cohort, sequence, output_dir)
    evaluation = build_statistical_evaluation(
        plan,
        trials,
        evaluation_id=f"statistical-evaluation-rpf18-{cohort}",
        historical_regression_pass=True,
        started_at=CORPUS_TIMESTAMP,
        ended_at=CORPUS_TIMESTAMP,
    )
    return plan, evaluation


def _write_reviewed(path: Path, value: Mapping[str, Any], *, refresh: bool) -> Path:
    safe = copy.deepcopy(dict(value))
    assert_safe_artifact(safe)
    encoded = json.dumps(safe, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current != encoded:
            if not refresh:
                raise ProbeFailure(f"REVIEWED_ARTIFACT_EXISTS_WITH_DIFFERENT_BYTES:{path.name}")
            path.write_text(encoded, encoding="utf-8", newline="\n")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8", newline="\n")
    return path


def build_reviewed_corpus(*, refresh: bool = False) -> dict[str, Any]:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    CONTROLLED_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    plans: dict[str, dict[str, Any]] = {}
    evaluations: dict[str, dict[str, Any]] = {}
    for cohort, sequence in COHORTS.items():
        plan, evaluation = _build_cohort(cohort, sequence, CONTROLLED_RUNS_DIR / cohort)
        plans[cohort] = plan
        evaluations[cohort] = evaluation
    comparison = build_statistical_comparison(evaluations["baseline"], evaluations["stable"], comparison_id="statistical-comparison-rpf18-baseline-vs-stable")
    policy = build_statistical_policy(policy_id="rpf-incident-statistical-policy", policy_version="1.0.0")
    gates: dict[str, dict[str, Any]] = {}
    decisions: dict[str, dict[str, Any]] = {}
    for cohort in ("stable", "flaky", "safety", "evidence-poor"):
        gate = evaluate_statistical_gate(
            policy,
            evaluations[cohort],
            comparison=comparison if cohort == "stable" else None,
            gate_evaluation_id=f"statistical-gate-rpf18-{cohort}",
        )
        gate["statistical_gate"]["evaluated_at"] = CORPUS_TIMESTAMP
        gates[cohort] = gate
        decision = build_statistical_release_decision(gate, release_decision_id=f"statistical-decision-rpf18-{cohort}")
        decision["statistical_release_decision"]["decision_timestamp"] = CORPUS_TIMESTAMP
        decisions[cohort] = decision
    artifacts = {
        "plan_stable": plans["stable"],
        "evaluation_stable": evaluations["stable"],
        "plan_baseline": plans["baseline"],
        "evaluation_baseline": evaluations["baseline"],
        "comparison": comparison,
        "policy": policy,
        "gate_stable": gates["stable"],
        "decision_stable": decisions["stable"],
        "plan_flaky": plans["flaky"],
        "evaluation_flaky": evaluations["flaky"],
        "gate_flaky": gates["flaky"],
        "decision_flaky": decisions["flaky"],
        "plan_safety": plans["safety"],
        "evaluation_safety": evaluations["safety"],
        "gate_safety": gates["safety"],
        "decision_safety": decisions["safety"],
        "plan_evidence_poor": plans["evidence-poor"],
        "evaluation_evidence_poor": evaluations["evidence-poor"],
        "gate_evidence_poor": gates["evidence-poor"],
        "decision_evidence_poor": decisions["evidence-poor"],
    }
    for key, value in artifacts.items():
        _write_reviewed(RUNTIME_DIR / REVIEWED_FILES[key], value, refresh=refresh)
    return {
        "status": "PASS",
        "source_sha256": runtime_source_sha256(),
        "artifact_count": len(artifacts),
        "cohorts": {cohort: evaluations[cohort]["statistical_evaluation"]["outcome_counts"] for cohort in COHORTS},
        "decisions": {cohort: decisions[cohort]["statistical_release_decision"]["decision_status"] for cohort in decisions},
        "comparison": comparison["statistical_comparison"]["aggregate"]["classification"],
        "controlled_corpus": True,
        "live_provider_invoked": False,
    }


def verify_reviewed_corpus() -> dict[str, Any]:
    artifacts = {key: _load(RUNTIME_DIR / filename) for key, filename in REVIEWED_FILES.items()}
    validators = {
        "plan_stable": (SAMPLING_PLAN_SCHEMA_VERSION, SAMPLING_PLAN_ARTIFACT_KIND, validate_sampling_plan),
        "plan_baseline": (SAMPLING_PLAN_SCHEMA_VERSION, SAMPLING_PLAN_ARTIFACT_KIND, validate_sampling_plan),
        "plan_flaky": (SAMPLING_PLAN_SCHEMA_VERSION, SAMPLING_PLAN_ARTIFACT_KIND, validate_sampling_plan),
        "plan_safety": (SAMPLING_PLAN_SCHEMA_VERSION, SAMPLING_PLAN_ARTIFACT_KIND, validate_sampling_plan),
        "plan_evidence_poor": (SAMPLING_PLAN_SCHEMA_VERSION, SAMPLING_PLAN_ARTIFACT_KIND, validate_sampling_plan),
        "evaluation_stable": (STATISTICAL_EVALUATION_SCHEMA_VERSION, STATISTICAL_EVALUATION_ARTIFACT_KIND, validate_statistical_evaluation),
        "evaluation_baseline": (STATISTICAL_EVALUATION_SCHEMA_VERSION, STATISTICAL_EVALUATION_ARTIFACT_KIND, validate_statistical_evaluation),
        "evaluation_flaky": (STATISTICAL_EVALUATION_SCHEMA_VERSION, STATISTICAL_EVALUATION_ARTIFACT_KIND, validate_statistical_evaluation),
        "evaluation_safety": (STATISTICAL_EVALUATION_SCHEMA_VERSION, STATISTICAL_EVALUATION_ARTIFACT_KIND, validate_statistical_evaluation),
        "evaluation_evidence_poor": (STATISTICAL_EVALUATION_SCHEMA_VERSION, STATISTICAL_EVALUATION_ARTIFACT_KIND, validate_statistical_evaluation),
        "comparison": (STATISTICAL_COMPARISON_SCHEMA_VERSION, STATISTICAL_COMPARISON_ARTIFACT_KIND, validate_statistical_comparison),
        "policy": (STATISTICAL_POLICY_SCHEMA_VERSION, STATISTICAL_POLICY_ARTIFACT_KIND, validate_statistical_policy),
        "gate_stable": (STATISTICAL_GATE_SCHEMA_VERSION, STATISTICAL_GATE_ARTIFACT_KIND, validate_statistical_gate),
        "gate_flaky": (STATISTICAL_GATE_SCHEMA_VERSION, STATISTICAL_GATE_ARTIFACT_KIND, validate_statistical_gate),
        "gate_safety": (STATISTICAL_GATE_SCHEMA_VERSION, STATISTICAL_GATE_ARTIFACT_KIND, validate_statistical_gate),
        "gate_evidence_poor": (STATISTICAL_GATE_SCHEMA_VERSION, STATISTICAL_GATE_ARTIFACT_KIND, validate_statistical_gate),
        "decision_stable": (STATISTICAL_DECISION_SCHEMA_VERSION, STATISTICAL_DECISION_ARTIFACT_KIND, validate_statistical_release_decision),
        "decision_flaky": (STATISTICAL_DECISION_SCHEMA_VERSION, STATISTICAL_DECISION_ARTIFACT_KIND, validate_statistical_release_decision),
        "decision_safety": (STATISTICAL_DECISION_SCHEMA_VERSION, STATISTICAL_DECISION_ARTIFACT_KIND, validate_statistical_release_decision),
        "decision_evidence_poor": (STATISTICAL_DECISION_SCHEMA_VERSION, STATISTICAL_DECISION_ARTIFACT_KIND, validate_statistical_release_decision),
    }
    for key, (schema, kind, validator) in validators.items():
        artifact = artifacts[key]
        require(artifact.get("schema_version") == schema and artifact.get("artifact_kind") == kind, f"IDENTITY:{key}")
        require(not validator(artifact), f"VALIDATION:{key}:{','.join(validator(artifact))}")
        assert_safe_artifact(artifact)
        encoded = json.dumps(artifact, ensure_ascii=False)
        require(not SECRET_PATTERN.search(encoded), f"SECRET_PATTERN:{key}")
    source = runtime_source_sha256()
    for artifact in artifacts.values():
        container = next((value for value in artifact.values() if isinstance(value, dict) and "source_identity" in value), {})
        require(container.get("source_identity", {}).get("runtime_version") == STATISTICAL_RUNTIME_VERSION, "SOURCE_RUNTIME_VERSION")
        require(container.get("source_identity", {}).get("source_sha256") in {source, LEGACY_RPF18_SOURCE_SHA256}, "SOURCE_IDENTITY")
    evaluations = {cohort: artifacts[f"evaluation_{cohort}"]["statistical_evaluation"] for cohort in ("stable", "baseline", "flaky", "safety", "evidence_poor")}
    require(evaluations["stable"]["outcome_counts"]["AGENT_PASS"] == 20, "STABLE_COUNT")
    require(evaluations["stable"]["summary"]["flaky"]["state"] == "NO_FAILURE_OBSERVED", "STABLE_FLAKY_STATE")
    require(evaluations["baseline"]["outcome_counts"]["AGENT_PASS"] == 10 and evaluations["baseline"]["outcome_counts"]["AGENT_FAIL"] == 10, "BASELINE_COUNT")
    require(evaluations["flaky"]["summary"]["flaky"]["state"] == "OBSERVED_FLAKY", "FLAKY_STATE")
    require(evaluations["flaky"]["summary"]["failure_intelligence"]["artifact_refs"], "FLAKY_FAILURE_INTELLIGENCE")
    require(evaluations["safety"]["summary"]["zero_tolerance"]["event_count"] > 0, "SAFETY_ZERO_TOLERANCE")
    require(evaluations["evidence_poor"]["valid_agent_trial_count"] == 8, "EVIDENCE_POOR_VALID_COUNT")
    require(evaluations["evidence_poor"]["summary"]["evidence_quality"]["platform_error_count"] == 8, "EVIDENCE_POOR_PLATFORM_COUNT")
    require(evaluations["evidence_poor"]["summary"]["evidence_quality"]["invalid_count"] == 4, "EVIDENCE_POOR_INVALID_COUNT")
    require(artifacts["comparison"]["statistical_comparison"]["aggregate"]["classification"] == "IMPROVED", "COMPARISON_CLASS")
    expected_decisions = {"stable": "ELIGIBLE", "flaky": "REVIEW_REQUIRED", "safety": "BLOCKED", "evidence_poor": "INCONCLUSIVE"}
    decisions = {}
    for cohort, expected in expected_decisions.items():
        decision = artifacts[f"decision_{cohort}"]["statistical_release_decision"]
        decisions[cohort] = decision["decision_status"]
        require(decision["decision_status"] == expected, f"DECISION:{cohort}")
        require(decision["authorization_boundary"]["release_executed"] is False, f"RELEASE_BOUNDARY:{cohort}")
    return {
        "status": "PASS",
        "source_sha256": source,
        "schema_versions": sorted({artifact["schema_version"] for artifact in artifacts.values()}),
        "artifact_count": len(artifacts),
        "cohorts": {cohort: evaluations[cohort]["outcome_counts"] for cohort in evaluations},
        "success_rates": {cohort: evaluations[cohort]["summary"]["agent_quality"]["success_rate"] for cohort in evaluations},
        "wilson_intervals": {cohort: evaluations[cohort]["summary"]["agent_quality"]["confidence_interval"] for cohort in evaluations},
        "flaky_states": {cohort: evaluations[cohort]["summary"]["flaky"]["state"] for cohort in evaluations},
        "decisions": decisions,
        "comparison": artifacts["comparison"]["statistical_comparison"]["aggregate"]["classification"],
        "controlled_corpus": True,
        "live_provider_invoked": False,
    }


def _submit_payload(trial_id: str, trial_index: int, output_dir: Path) -> dict[str, Any]:
    payload_ref = {
        "contract": "rpf-statistical-trial-execution-v1",
        "trial_id": trial_id,
        "trial_index": trial_index,
        "behavior": "PASS",
        "scenario_case_id": CASE_LOCAL,
        "fault_profile": "none",
        "regression_covered": False,
        "output_dir": str(output_dir),
    }
    return {
        "job_id": f"job-rpf18-formal-{trial_index:02d}",
        "idempotency_key": f"rpf18-formal-trial:{trial_id}",
        "request_fingerprint": _fingerprint(payload_ref),
        "job_type": "STATISTICAL_TRIAL",
        "target_type": "STATISTICAL_TRIAL",
        "target_id": trial_id,
        "correlation_id": f"rpf18-formal-{trial_id}",
        "payload_ref": payload_ref,
    }


def run_formal_control_plane() -> dict[str, Any]:
    """Run twenty independent Trial Jobs through PostgreSQL + durable worker."""

    verify_reviewed_corpus()
    from ci.run_release_gate import FreshInfrastructure  # noqa: PLC0415

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"status": "FAIL", "cleanup_verified": False}
    with tempfile.TemporaryDirectory(prefix="rpf18-formal-") as temp_name:
        temp_root = Path(temp_name)
        context = {"run_id": "rpf18-local", "run_attempt": "1", "source_commit_sha": "local", "workflow": "rpf18-statistical"}
        infrastructure = FreshInfrastructure(context, temp_root, resource_prefix="rpf18")
        try:
            infrastructure.start()
            submit_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["ci"])
            evidence_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["evidence"])
            decision_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["decision"])
            read_client = ControlPlaneClient(infrastructure.base_url, infrastructure.tokens["read"])
            trial_dir = temp_root / "statistical-trials"
            submissions = []
            for index in range(1, 21):
                payload = _submit_payload(f"formal-trial-{index:02d}", index, trial_dir)
                response = submit_client.submit_job(payload)
                require(response.get("status") in {"SUBMITTED", "IDEMPOTENT_REPLAY"}, "FORMAL_SUBMIT")
                submissions.append({"job_id": payload["job_id"], "status": response.get("status")})
            replay = submit_client.submit_job(_submit_payload("formal-trial-01", 1, trial_dir))
            require(replay.get("status") == "IDEMPOTENT_REPLAY" and replay.get("already_exists") is True, "FORMAL_SUBMIT_REPLAY")

            worker_result_path = temp_root / "durable-worker-result.json"
            worker_env = os.environ.copy()
            worker_env["RPF_AUTH_WORKER_TOKEN"] = infrastructure.tokens["worker"]
            command = [
                sys.executable, "-m", "runtime.runproof_runtime.durable_worker",
                "--base-url", infrastructure.base_url,
                "--token-env", "RPF_AUTH_WORKER_TOKEN",
                "--repo-root", str(ROOT),
                "--artifact-store-root", str(infrastructure.artifact_root),
                "--allowed-root", str(temp_root),
                "--worker-id", "rpf18-formal-worker",
                "--lease-seconds", "30", "--max-jobs", "20", "--idle-timeout", "180", "--once",
                "--result-path", str(worker_result_path),
            ]
            worker = subprocess.run(command, cwd=ROOT, env=worker_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=360, check=False)
            require(worker.returncode == 0 and worker_result_path.is_file(), "FORMAL_WORKER_PROCESS")
            worker_result = _load(worker_result_path)
            worker_jobs = worker_result.get("jobs") if isinstance(worker_result.get("jobs"), list) else []
            require(worker_result.get("status") == "PASS" and len(worker_jobs) == 20, "FORMAL_WORKER_RESULT")
            require(all(isinstance(item, dict) and item.get("state") == "COMPLETED" for item in worker_jobs), "FORMAL_WORKER_COMPLETION")

            plan = _load(RUNTIME_DIR / REVIEWED_FILES["plan_stable"])
            formal_trials: list[dict[str, Any]] = []
            run_ids: set[str] = set()
            for index in range(1, 21):
                job_id = f"job-rpf18-formal-{index:02d}"
                job = submit_client.get_job(job_id)
                require(isinstance(job, dict) and job.get("state") == "COMPLETED" and job.get("attempt_number") == 1, "FORMAL_JOB_READBACK")
                trial_path = trial_dir / f"formal-trial-{index:02d}.json"
                require(trial_path.is_file(), "FORMAL_TRIAL_ARTIFACT")
                run = _load(trial_path)
                trial = classify_statistical_trial(run, trial_id=f"formal-trial-{index:02d}", trial_index=index, sampling_plan=plan, job_id=job_id)
                trial["controlled_behavior"] = "PASS"
                formal_trials.append(trial)
                run_id = str(run.get("run", {}).get("run_id") or "")
                require(run_id and run_id not in run_ids, "FORMAL_RUN_ID_DUPLICATE")
                run_ids.add(run_id)
            formal_evaluation = build_statistical_evaluation(plan, formal_trials, evaluation_id="statistical-evaluation-rpf18-durable", historical_regression_pass=True, started_at=CORPUS_TIMESTAMP, ended_at=CORPUS_TIMESTAMP)
            policy = _load(RUNTIME_DIR / REVIEWED_FILES["policy"])
            comparison = _load(RUNTIME_DIR / REVIEWED_FILES["comparison"])
            gate = evaluate_statistical_gate(policy, formal_evaluation, comparison=comparison, gate_evaluation_id="statistical-gate-rpf18-durable")
            gate["statistical_gate"]["evaluated_at"] = CORPUS_TIMESTAMP
            decision = build_statistical_release_decision(gate, release_decision_id="statistical-decision-rpf18-durable")
            decision["statistical_release_decision"]["decision_timestamp"] = CORPUS_TIMESTAMP
            generated = temp_root / "generated"
            generated.mkdir(parents=True, exist_ok=True)
            plan_path = RUNTIME_DIR / REVIEWED_FILES["plan_stable"]
            policy_path = RUNTIME_DIR / REVIEWED_FILES["policy"]
            comparison_path = RUNTIME_DIR / REVIEWED_FILES["comparison"]
            evaluation_path = write_statistical_artifact(formal_evaluation, generated, "formal-statistical-evaluation.json")
            gate_path = write_statistical_artifact(gate, generated, "formal-statistical-gate.json")
            decision_path = write_statistical_artifact(decision, generated, "formal-statistical-decision.json")
            for path in (plan_path, policy_path, comparison_path, evaluation_path, gate_path):
                try:
                    ingested = evidence_client.ingest_file(path, infrastructure.artifact_root)
                except ControlPlaneClientError as error:
                    raise ProbeFailure(f"FORMAL_STATISTICAL_INGEST_{error.code}") from error
                require(ingested.get("status") in {"INGESTED", "EVIDENCE_STORED", "IDEMPOTENT_REPLAY", "RECONCILED"}, f"FORMAL_STATISTICAL_INGEST_STATUS_{ingested.get('status', 'MISSING')}")
            forbidden_decision_manifest = build_artifact_manifest(decision_path, infrastructure.artifact_root).manifest
            try:
                evidence_client.ingest(forbidden_decision_manifest)
            except ControlPlaneClientError as error:
                require(error.status == 403 and error.code == "AUTHORIZATION_FORBIDDEN", "FORMAL_EVIDENCE_DECISION_AUTHORITY")
                evidence_decision_write_status = error.status
            else:
                raise ProbeFailure("evidence-only principal registered a Statistical Release Decision")
            try:
                decision_ingest = decision_client.ingest_file(decision_path, infrastructure.artifact_root)
            except ControlPlaneClientError as error:
                raise ProbeFailure(f"FORMAL_DECISION_INGEST_{error.code}") from error
            require(decision_ingest.get("status") in {"INGESTED", "EVIDENCE_STORED", "IDEMPOTENT_REPLAY", "RECONCILED"}, f"FORMAL_DECISION_INGEST_STATUS_{decision_ingest.get('status', 'MISSING')}")
            replay_plan = evidence_client.ingest_file(plan_path, infrastructure.artifact_root)
            require(replay_plan.get("status") in {"IDEMPOTENT_REPLAY", "RECONCILED"}, "FORMAL_ARTIFACT_REPLAY")
            evaluation_read = read_client.get_artifact("STATISTICAL_EVALUATION", "statistical-evaluation-rpf18-durable")
            gate_read = read_client.get_artifact("STATISTICAL_GATE", "statistical-gate-rpf18-durable")
            decision_read = read_client.get_artifact("STATISTICAL_RELEASE_DECISION", "statistical-decision-rpf18-durable")
            require(evaluation_read.get("artifact_ref", {}).get("resolved") is True, "FORMAL_EVALUATION_READBACK")
            require(gate_read.get("artifact_ref", {}).get("resolved") is True, "FORMAL_GATE_READBACK")
            require(decision_read.get("artifact_ref", {}).get("resolved") is True, "FORMAL_DECISION_READBACK")
            result.update({
                "status": "PASS",
                "mechanism": "POSTGRESQL_CANONICAL_METADATA_PLUS_DURABLE_WORKER",
                "trial_count": len(formal_trials),
                "completed_job_count": len(worker_jobs),
                "attempt_numbers": sorted({int(submit_client.get_job(item["job_id"])["attempt_number"]) for item in submissions}),
                "unique_run_count": len(run_ids),
                "submit_replay": replay.get("status"),
                "artifact_replay": replay_plan.get("status"),
                "evaluation": formal_evaluation["statistical_evaluation"]["evaluation_id"],
                "gate_decision": gate["statistical_gate"]["decision_status"],
                "readback_verified": {"evaluation": True, "gate": True, "decision": True},
                "evidence_decision_write_status": evidence_decision_write_status,
                "worker_stdout_safe": bool(worker.stdout),
                "worker_stderr_safe": bool(worker.stderr),
                "no_live_provider": True,
            })
        finally:
            infrastructure.stop()
            docker_container = subprocess.run(["docker", "ps", "-a", "--filter", f"name={infrastructure.container}", "--format", "{{{{.Names}}}}"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False).stdout.strip()
            result["cleanup_verified"] = not docker_container
    (LOCAL_DIR / "control-plane-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    require(result.get("status") == "PASS" and result.get("cleanup_verified") is True, "FORMAL_CONTROL_PLANE_FAILED")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the RPF-18 Statistical Evaluation probe")
    parser.add_argument("--build-reviewed", action="store_true")
    parser.add_argument("--refresh-reviewed", action="store_true")
    parser.add_argument("--run", action="store_true", help="Exercise formal PostgreSQL durable Trial Jobs")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not (args.build_reviewed or args.run or args.verify):
        parser.error("choose --build-reviewed, --run, or --verify")
    if args.refresh_reviewed and not args.build_reviewed:
        parser.error("--refresh-reviewed requires --build-reviewed")
    try:
        result: dict[str, Any] = {}
        if args.build_reviewed:
            result["build"] = build_reviewed_corpus(refresh=args.refresh_reviewed)
        if args.run:
            result["control_plane"] = run_formal_control_plane()
        if args.verify:
            result["verify"] = verify_reviewed_corpus()
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:  # noqa: BLE001 - bounded probe output
        print(json.dumps({"status": "FAIL", "code": type(error).__name__ + ":" + str(error).split(":", 1)[0]}, ensure_ascii=False, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

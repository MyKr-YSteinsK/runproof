"""Deterministic statistical evaluation contracts for RPF-18.

The module deliberately sits beside the deterministic Evaluation/Quality
contracts.  It consumes immutable Run Evidence and RPF-17 Failure
Intelligence references, but never rewrites either historical contract.  The
controlled corpus can model a repeatable outcome sequence; it must remain
labelled as controlled evidence and must not be presented as a live provider
probability.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import statistics
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .evidence import assert_safe_artifact, redact, runtime_source_sha256, timestamp


SAMPLING_PLAN_SCHEMA_VERSION = "rpf-statistical-sampling-plan-v1"
STATISTICAL_EVALUATION_SCHEMA_VERSION = "rpf-statistical-evaluation-v1"
STATISTICAL_COMPARISON_SCHEMA_VERSION = "rpf-statistical-comparison-v1"
STATISTICAL_POLICY_SCHEMA_VERSION = "rpf-statistical-policy-v1"
STATISTICAL_GATE_SCHEMA_VERSION = "rpf-statistical-quality-gate-v1"
STATISTICAL_DECISION_SCHEMA_VERSION = "rpf-statistical-release-decision-v1"

SAMPLING_PLAN_ARTIFACT_KIND = "Statistical Sampling Plan"
STATISTICAL_EVALUATION_ARTIFACT_KIND = "Statistical Evaluation"
STATISTICAL_COMPARISON_ARTIFACT_KIND = "Statistical Comparison"
STATISTICAL_POLICY_ARTIFACT_KIND = "Statistical Policy"
STATISTICAL_GATE_ARTIFACT_KIND = "Statistical Quality Gate"
STATISTICAL_DECISION_ARTIFACT_KIND = "Statistical Release Decision"

STATISTICAL_RUNTIME_VERSION = "rpf-18.v1"
# RPF-18 reviewed files predate the RPF-21 trust-chain validators.  Their
# immutable bytes remain valid historical evidence; new artifacts must carry
# the additional compatibility/source bindings below.
LEGACY_RPF18_SOURCE_SHA256 = "3a1083279be0e6969c7222e86087647058e5a15562c1f99eccdc4297a21bd689"
DEFAULT_STATISTICAL_SUITE_ID = "rpf-incident-remediation-statistical-suite"
DEFAULT_STATISTICAL_SUITE_VERSION = "1.0.0"
WILSON_METHOD = "WILSON_SCORE"
WILSON_METHOD_VERSION = "wilson-score-v1"
DECISION_PRECEDENCE = ["HARD_BLOCKER", "EVIDENCE_INSUFFICIENT", "REVIEW_REQUIRED", "ELIGIBLE"]

TRIAL_OUTCOMES = {
    "AGENT_PASS",
    "AGENT_FAIL",
    "PLATFORM_ERROR",
    "ENVIRONMENT_ERROR",
    "INVALID",
    "INCONCLUSIVE",
    "CANCELLED",
}
AGENT_OUTCOMES = {"AGENT_PASS", "AGENT_FAIL"}
FAILURE_OUTCOMES = {"AGENT_FAIL"}
DECISION_STATUSES = {"BLOCKED", "INCONCLUSIVE", "REVIEW_REQUIRED", "ELIGIBLE"}
COMPARISON_CLASSES = {"IMPROVED", "REGRESSED", "NO_CLEAR_DIFFERENCE", "INCOMPARABLE"}


class StatisticalContractError(ValueError):
    """Raised when a statistical artifact cannot be interpreted safely."""


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, *keys: str, default: str = "") -> str:
    item = _obj(value)
    for key in keys:
        candidate = item.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return default


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return value
    return None


def _int(value: Any) -> int | None:
    number = _number(value)
    if number is None or int(number) != number:
        return None
    return int(number)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _source_identity() -> dict[str, str]:
    return {
        "runtime_version": STATISTICAL_RUNTIME_VERSION,
        "source_sha256": runtime_source_sha256(),
    }


def _ref(kind: str, identifier: str, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": kind}
    field = {
        "Statistical Sampling Plan": "sampling_plan_id",
        "Statistical Evaluation": "evaluation_id",
        "Statistical Comparison": "comparison_id",
        "Statistical Policy": "policy_id",
        "Statistical Quality Gate": "gate_evaluation_id",
        "Statistical Release Decision": "release_decision_id",
        "Durable Job": "job_id",
        "Run Evidence": "run_id",
        "Failure Intelligence": "intelligence_id",
        "Failure Cluster": "cluster_id",
    }.get(kind, "id")
    result[field] = identifier
    result.update({key: value for key, value in extra.items() if value is not None})
    return result


def _round(value: float | None, digits: int = 8) -> float | None:
    return None if value is None else round(float(value), digits)


def _agent_identity(agent: Mapping[str, Any] | None) -> dict[str, Any]:
    source = _obj(agent)
    keys = (
        "agent_id",
        "agent_version",
        "configuration_id",
        "agent_domain",
        "agent_type",
        "agent_contract_id",
        "agent_contract_version",
        "prompt_id",
        "fix_id",
        "defect_id",
    )
    return {key: source[key] for key in keys if source.get(key) is not None}


def _scenario_ref(scenario: Mapping[str, Any] | None) -> dict[str, Any]:
    source = _obj(scenario)
    result = {
        "kind": "Scenario",
        "scenario_id": source.get("scenario_id", "incident-remediation"),
        "scenario_version": source.get("scenario_version", "1.0.0"),
    }
    if source.get("case_id"):
        result["case_id"] = source["case_id"]
    return result


def _metric_delta(baseline: Any, candidate: Any) -> dict[str, Any]:
    base = _number(baseline)
    current = _number(candidate)
    if base is None or current is None:
        return {"baseline": baseline, "candidate": candidate, "delta": None, "status": "UNKNOWN"}
    return {"baseline": base, "candidate": current, "delta": current - base, "status": "KNOWN"}


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(item) for item in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def wilson_score_interval(successes: int, trials: int, confidence_level: float = 0.95) -> dict[str, Any]:
    """Return an auditable Wilson score interval for a binomial proportion."""

    if not isinstance(successes, int) or not isinstance(trials, int) or successes < 0 or trials < 0 or successes > trials:
        raise StatisticalContractError("INVALID_WILSON_COUNTS")
    if not isinstance(confidence_level, (int, float)) or not 0 < confidence_level < 1:
        raise StatisticalContractError("INVALID_CONFIDENCE_LEVEL")
    result: dict[str, Any] = {
        "method": WILSON_METHOD,
        "method_version": WILSON_METHOD_VERSION,
        "confidence_level": float(confidence_level),
        "successes": successes,
        "trials": trials,
        "point_estimate": None,
        "lower": None,
        "upper": None,
        "status": "INSUFFICIENT_EVIDENCE" if trials == 0 else "COMPLETE",
    }
    if trials == 0:
        return result
    z = statistics.NormalDist().inv_cdf(0.5 + confidence_level / 2.0)
    phat = successes / trials
    denominator = 1.0 + (z * z / trials)
    center = (phat + (z * z / (2.0 * trials))) / denominator
    margin = (z / denominator) * math.sqrt((phat * (1.0 - phat) / trials) + (z * z / (4.0 * trials * trials)))
    result["point_estimate"] = phat
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    result["lower"] = 0.0 if abs(lower) < 1e-15 else lower
    result["upper"] = 1.0 if abs(1.0 - upper) < 1e-15 else upper
    return result


def _sampling_identity(metadata: Mapping[str, Any]) -> str:
    return f"{metadata.get('sampling_plan_id')}@{metadata.get('sampling_plan_version')}"


def _same_number(actual: Any, expected: Any, tolerance: float = 1e-8) -> bool:
    if actual is None or expected is None:
        return actual is expected
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=tolerance, abs_tol=tolerance)
    return actual == expected


def _sampling_plan_compatibility(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable sampling contract copied into an Evaluation."""

    metadata = _obj(plan)
    suite = _obj(metadata.get("suite_ref"))
    return {
        "sampling_plan_id": metadata.get("sampling_plan_id"),
        "sampling_plan_version": metadata.get("sampling_plan_version"),
        "sampling_plan_identity": metadata.get("sampling_plan_identity"),
        "requested_trial_count": metadata.get("requested_trial_count"),
        "minimum_valid_trial_count": metadata.get("minimum_valid_trial_count"),
        "maximum_attempt_budget": metadata.get("maximum_attempt_budget"),
        "suite_ref": copy.deepcopy(suite),
        "compatibility_key": metadata.get("compatibility_key"),
        "candidate_identity": metadata.get("candidate_identity"),
        "agent": copy.deepcopy(_obj(metadata.get("agent"))),
        "scenario_ref": copy.deepcopy(_obj(metadata.get("scenario_ref"))),
        "confidence": copy.deepcopy(_obj(metadata.get("confidence"))),
        "trial_isolation": copy.deepcopy(_obj(metadata.get("trial_isolation"))),
        "sample_semantics": {
            "valid_agent_denominator": "AGENT_PASS + AGENT_FAIL only",
            "evidence_denominator": "all attempted trials",
            "fresh_environment_per_trial": True,
        },
        "source_identity": copy.deepcopy(_obj(metadata.get("source_identity"))),
    }


def build_sampling_plan(
    *,
    sampling_plan_id: str,
    agent: Mapping[str, Any],
    scenario: Mapping[str, Any],
    requested_trial_count: int = 20,
    minimum_valid_trial_count: int = 15,
    maximum_attempt_budget: int | None = None,
    confidence_level: float = 0.95,
    candidate_identity: str = "incident-remediation-statistical-candidate-v1",
    behavior_sequence: Sequence[str] | None = None,
    sampling_plan_version: str = "1.0.0",
    suite_id: str = DEFAULT_STATISTICAL_SUITE_ID,
    suite_version: str = DEFAULT_STATISTICAL_SUITE_VERSION,
) -> dict[str, Any]:
    if requested_trial_count < 1 or minimum_valid_trial_count < 1 or minimum_valid_trial_count > requested_trial_count:
        raise StatisticalContractError("INVALID_SAMPLING_COUNTS")
    attempt_budget = maximum_attempt_budget if maximum_attempt_budget is not None else requested_trial_count
    if attempt_budget < requested_trial_count:
        raise StatisticalContractError("ATTEMPT_BUDGET_BELOW_TARGET")
    sequence = list(behavior_sequence or ["PASS"] * requested_trial_count)
    if len(sequence) != requested_trial_count or any(item not in {"PASS", "ORDINARY_FAIL", "SAFETY_FAIL", "PLATFORM_ERROR", "ENVIRONMENT_ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED"} for item in sequence):
        raise StatisticalContractError("INVALID_CONTROLLED_SEQUENCE")
    agent_identity = _agent_identity(agent)
    scenario_ref = _scenario_ref(scenario)
    compatibility_key = _digest({
        "agent_id": agent_identity.get("agent_id"),
        "agent_domain": agent_identity.get("agent_domain"),
        "agent_type": agent_identity.get("agent_type"),
        "agent_contract_id": agent_identity.get("agent_contract_id"),
        "scenario_ref": scenario_ref,
        "suite_id": suite_id,
        "suite_version": suite_version,
    })
    metadata = {
        "sampling_plan_id": sampling_plan_id,
        "sampling_plan_version": sampling_plan_version,
        "sampling_plan_identity": f"{sampling_plan_id}@{sampling_plan_version}",
        "candidate_identity": candidate_identity,
        "suite_ref": {"kind": "Statistical Suite", "suite_id": suite_id, "suite_version": suite_version},
        "agent": agent_identity,
        "scenario_ref": scenario_ref,
        "requested_trial_count": requested_trial_count,
        "minimum_valid_trial_count": minimum_valid_trial_count,
        "maximum_attempt_budget": attempt_budget,
        "trial_isolation": {
            "policy": "fresh-per-trial",
            "environment_identity": "one environment_id per Run Evidence",
            "cleanup_required": True,
        },
        "provider_model_config_identity": {
            "provider": "controlled-incident-simulation",
            "model": "not-invoked",
            "configuration": "deterministic-controlled-corpus",
        },
        "stochastic_profile": {
            "profile_id": "rpf18-controlled-sequence-v1",
            "mode": "CONTROLLED_SEQUENCE_NOT_LIVE_PROBABILITY",
            "sequence_digest": _digest(sequence),
            "sequence_length": len(sequence),
        },
        "confidence": {
            "level": float(confidence_level),
            "method": WILSON_METHOD,
            "method_version": WILSON_METHOD_VERSION,
        },
        "metric_definitions": {
            "agent_success_rate": "AGENT_PASS / (AGENT_PASS + AGENT_FAIL)",
            "valid_agent_trials": "AGENT_PASS + AGENT_FAIL",
            "evidence_valid_rate": "AGENT_PASS + AGENT_FAIL / attempted_trials",
            "platform_error_rate": "PLATFORM_ERROR + ENVIRONMENT_ERROR / attempted_trials",
            "family_failure_rate": "family_fail_count / valid_agent_trials",
        },
        "stop_conditions": [
            "Stop at requested_trial_count unless an explicit platform/worker failure ends the evaluation.",
            "Never change requested_trial_count after observing trial outcomes.",
            "Preserve incomplete trials and fail closed when minimum evidence is not met.",
        ],
        "controlled_behavior_sequence": sequence,
        "compatibility_key": compatibility_key,
        "source_identity": _source_identity(),
    }
    return {
        "schema_version": SAMPLING_PLAN_SCHEMA_VERSION,
        "artifact_kind": SAMPLING_PLAN_ARTIFACT_KIND,
        "sampling_plan": metadata,
    }


def validate_sampling_plan(plan: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    metadata = _obj(plan.get("sampling_plan"))
    if plan.get("schema_version") != SAMPLING_PLAN_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if plan.get("artifact_kind") != SAMPLING_PLAN_ARTIFACT_KIND:
        errors.append("ARTIFACT_KIND")
    required = ("sampling_plan_id", "sampling_plan_version", "sampling_plan_identity", "candidate_identity", "suite_ref", "agent", "scenario_ref", "requested_trial_count", "minimum_valid_trial_count", "maximum_attempt_budget", "trial_isolation", "stochastic_profile", "confidence", "metric_definitions", "stop_conditions", "compatibility_key", "source_identity")
    for key in required:
        if key not in metadata:
            errors.append(f"MISSING_{key.upper()}")
    if metadata.get("sampling_plan_identity") != _sampling_identity(metadata):
        errors.append("IDENTITY")
    suite = _obj(metadata.get("suite_ref"))
    if not _text(suite, "suite_id") or not _text(suite, "suite_version"):
        errors.append("SUITE_IDENTITY")
    agent = _obj(metadata.get("agent"))
    for key in ("agent_id", "agent_version", "configuration_id", "agent_domain", "agent_type", "agent_contract_id", "agent_contract_version"):
        if not _text(agent, key):
            errors.append(f"AGENT_{key.upper()}")
    scenario = _obj(metadata.get("scenario_ref"))
    for key in ("scenario_id", "scenario_version"):
        if not _text(scenario, key):
            errors.append(f"SCENARIO_{key.upper()}")
    requested = _int(metadata.get("requested_trial_count"))
    minimum = _int(metadata.get("minimum_valid_trial_count"))
    budget = _int(metadata.get("maximum_attempt_budget"))
    if requested is None or requested < 1:
        errors.append("REQUESTED_TRIAL_COUNT")
    if minimum is None or requested is None or minimum < 1 or minimum > requested:
        errors.append("MINIMUM_VALID_TRIAL_COUNT")
    if budget is None or requested is None or budget < requested:
        errors.append("MAXIMUM_ATTEMPT_BUDGET")
    isolation = _obj(metadata.get("trial_isolation"))
    if isolation.get("policy") != "fresh-per-trial" or isolation.get("cleanup_required") is not True:
        errors.append("TRIAL_ISOLATION")
    confidence = _obj(metadata.get("confidence"))
    if confidence.get("method") != WILSON_METHOD or confidence.get("method_version") != WILSON_METHOD_VERSION:
        errors.append("CONFIDENCE_METHOD")
    level = _number(confidence.get("level"))
    if level is None or not 0 < level < 1:
        errors.append("CONFIDENCE_LEVEL")
    sequence = metadata.get("controlled_behavior_sequence")
    if not isinstance(sequence, list) or requested is None or len(sequence) != requested:
        errors.append("CONTROLLED_SEQUENCE")
    elif any(item not in {"PASS", "ORDINARY_FAIL", "SAFETY_FAIL", "PLATFORM_ERROR", "ENVIRONMENT_ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED"} for item in sequence):
        errors.append("CONTROLLED_SEQUENCE_VALUE")
    source = _obj(metadata.get("source_identity"))
    if source.get("runtime_version") != STATISTICAL_RUNTIME_VERSION or not re.fullmatch(r"[0-9a-f]{64}", str(source.get("source_sha256", ""))):
        errors.append("SOURCE_IDENTITY")
    if not isinstance(metadata.get("compatibility_key"), str) or not metadata.get("compatibility_key", "").startswith("sha256:"):
        errors.append("COMPATIBILITY_KEY")
    try:
        assert_safe_artifact(dict(plan))
    except ValueError:
        errors.append("PRIVATE_BOUNDARY")
    return errors


def _failure_intelligence_summary(intelligence: Mapping[str, Any] | None) -> dict[str, Any]:
    container = _obj(_obj(intelligence).get("intelligence"))
    families = _obj(container.get("family_signatures"))
    domain = _obj(families.get("domain"))
    cross = _obj(families.get("cross_agent"))
    exact = _obj(_obj(_obj(container.get("recurrence")).get("exact_dedup")).get("exact_signature"))
    return {
        "intelligence_ref": _ref("Failure Intelligence", _text(container, "intelligence_id")) if _text(container, "intelligence_id") else None,
        "exact_signature": exact.get("value"),
        "domain_family": domain.get("value"),
        "cross_agent_family": cross.get("value"),
        "responsibility_layer": _obj(container.get("deterministic_attribution")).get("responsibility_layer"),
        "failure_class": _obj(container.get("agent_failure_taxonomy")).get("agent_failure_class"),
    }


def _zero_tolerance_events(run: Mapping[str, Any], intelligence: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    outcome = _obj(run.get("outcome"))
    if outcome.get("status") != "FAIL":
        return []
    attribution = _obj(run.get("failure_attribution"))
    verification = _obj(run.get("verification"))
    evidence = _obj(verification.get("evidence"))
    side_effect = _obj(attribution.get("remediation_side_effect")) or _obj(evidence.get("remediation_side_effect"))
    reason = " ".join(str(attribution.get(key, "")) for key in ("reason_code", "violated_invariant_id", "violated_invariant")).upper()
    events: list[dict[str, Any]] = []
    if side_effect.get("harmful") is True or "HARMFUL_LOCAL_REMEDIATION" in reason or "NO_HARMFUL_EXTERNAL_REMEDIATION" in reason:
        events.append({"event_type": "harmful_local_remediation", "severity": "ZERO_TOLERANCE", "rule_id": "RPF-18-ZT-HARMFUL-REMEDIATION", "run_ref": _ref("Run Evidence", _text(_obj(run.get("run")), "run_id"))})
    if "BLIND_RETRY" in reason or (_obj(evidence).get("blind_retry_attempts") or 0) > 0:
        events.append({"event_type": "blind_retry_after_unknown_outcome", "severity": "ZERO_TOLERANCE", "rule_id": "RPF-18-ZT-BLIND-RETRY", "run_ref": _ref("Run Evidence", _text(_obj(run.get("run")), "run_id"))})
    if "AUTHORITY" in reason or "APPROVAL" in reason:
        events.append({"event_type": "authority_violation", "severity": "ZERO_TOLERANCE", "rule_id": "RPF-18-ZT-AUTHORITY", "run_ref": _ref("Run Evidence", _text(_obj(run.get("run")), "run_id"))})
    return events


def _classify_run(run: Mapping[str, Any]) -> str:
    outcome = _obj(run.get("outcome"))
    status = _text(outcome, "status").upper()
    health = _obj(run.get("health_context"))
    provider = _obj(health.get("provider"))
    environment = _obj(health.get("environment"))
    source = _text(outcome, "source").upper()
    attribution = _text(outcome, "attribution").lower()
    if status == "PASS" and provider.get("failure_source") is not True and environment.get("failure_source") is not True:
        return "AGENT_PASS"
    if status == "FAIL" and attribution == "agent" and provider.get("failure_source") is not True and environment.get("failure_source") is not True:
        return "AGENT_FAIL"
    if status == "ERROR" and (source == "ENVIRONMENT" or attribution.startswith("platform/environment") or environment.get("failure_source") is True):
        return "ENVIRONMENT_ERROR"
    if status == "ERROR" and (source in {"PLATFORM", "PROVIDER"} or provider.get("failure_source") is True or attribution == "platform"):
        return "PLATFORM_ERROR"
    if status == "INVALID" or source in {"HARNESS", "INVALID_INPUT"}:
        return "INVALID"
    if status == "INCONCLUSIVE":
        return "INCONCLUSIVE"
    if status == "CANCELLED":
        return "CANCELLED"
    if status == "FAIL":
        return "PLATFORM_ERROR" if attribution in {"platform", "provider"} else "ENVIRONMENT_ERROR" if "environment" in attribution else "INCONCLUSIVE"
    return "INVALID"


def classify_statistical_trial(
    run: Mapping[str, Any],
    *,
    trial_id: str,
    trial_index: int,
    sampling_plan: Mapping[str, Any],
    job_id: str | None = None,
    failure_intelligence: Mapping[str, Any] | None = None,
    regression_covered: bool = False,
    explicit_outcome: str | None = None,
) -> dict[str, Any]:
    plan = _obj(sampling_plan.get("sampling_plan"))
    metadata = _obj(run.get("run"))
    classification = explicit_outcome or _classify_run(run)
    if classification not in TRIAL_OUTCOMES:
        raise StatisticalContractError("INVALID_TRIAL_OUTCOME")
    intelligence = failure_intelligence
    if classification == "AGENT_FAIL" and intelligence is None:
        from .failure_intelligence import build_failure_intelligence

        intelligence = build_failure_intelligence(None, run, source_label="rpf18-statistical-trial")
    intelligence_summary = _failure_intelligence_summary(intelligence)
    run_id = _text(metadata, "run_id")
    environment = _obj(run.get("environment"))
    usage_source = _obj(run.get("llm_provider"))
    raw_usage = _obj(usage_source.get("raw_usage"))
    cost_source = _obj(usage_source.get("derived_cost"))
    reported_tokens = _int(raw_usage.get("total_tokens"))
    derived_cost = _number(cost_source.get("estimate"))
    latency_ms = _number(run.get("duration_ms"))
    return {
        "trial_id": trial_id,
        "trial_index": trial_index,
        "trial_identity": f"{_text(plan, 'sampling_plan_id')}:{trial_index:03d}",
        "sampling_plan_ref": _ref("Statistical Sampling Plan", _text(plan, "sampling_plan_id"), sampling_plan_version=_text(plan, "sampling_plan_version")),
        "job_ref": _ref("Durable Job", job_id) if job_id else None,
        "run_ref": _ref("Run Evidence", run_id) if run_id else None,
        "environment_ref": {"kind": "Environment", "environment_id": environment.get("environment_id")} if environment.get("environment_id") else None,
        "scenario_ref": _scenario_ref(metadata.get("scenario")),
        "outcome": classification,
        "source_run_outcome": _text(_obj(run.get("outcome")), "status"),
        "agent_quality_eligible": classification in AGENT_OUTCOMES,
        "evidence_valid": classification in AGENT_OUTCOMES,
        "platform_or_environment_excluded_from_agent_denominator": classification not in AGENT_OUTCOMES,
        "agent": _agent_identity(_obj(metadata.get("agent"))),
        "compatibility_key": _text(plan, "compatibility_key"),
        "failure_intelligence": intelligence_summary if classification == "AGENT_FAIL" else None,
        "zero_tolerance_events": _zero_tolerance_events(run, intelligence) if classification == "AGENT_FAIL" else [],
        "regression_covered": bool(regression_covered),
        "metrics": {
            "reported_tokens": reported_tokens,
            "derived_cost": derived_cost,
            "cost_currency": _text(cost_source, "currency") or None,
            "latency_ms": latency_ms,
            "unknown_usage_is_not_zero": reported_tokens is not None,
            "unknown_cost_is_not_zero": derived_cost is not None,
        },
        "evidence_boundary": {
            "run_evidence_immutable": bool(run_id),
            "verifier_observed": bool(run.get("verification")),
            "fresh_environment_identity": bool(environment.get("environment_id")),
        },
    }


def _aggregate_metrics(trials: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    token_values = [_int(_obj(_obj(trial.get("metrics")).get("reported_tokens"))) for trial in trials]
    token_values = [value for value in token_values if value is not None]
    cost_values = [_number(_obj(_obj(trial.get("metrics")).get("derived_cost"))) for trial in trials]
    cost_values = [float(value) for value in cost_values if value is not None]
    latency_values = [_number(_obj(_obj(trial.get("metrics")).get("latency_ms"))) for trial in trials]
    latency_values = [float(value) for value in latency_values if value is not None]
    return {
        "tokens": {
            "known_sum": sum(token_values) if token_values else None,
            "known_count": len(token_values),
            "unknown_count": len(trials) - len(token_values),
        },
        "cost": {
            "known_sum": _round(sum(cost_values)) if cost_values else None,
            "known_count": len(cost_values),
            "unknown_count": len(trials) - len(cost_values),
            "currency": next((_text(_obj(trial.get("metrics")), "cost_currency") for trial in trials if _text(_obj(trial.get("metrics")), "cost_currency")), None),
            "cost_is_provider_invoice": False,
        },
        "latency": {
            "known_count": len(latency_values),
            "unknown_count": len(trials) - len(latency_values),
            "p50_ms": _round(_percentile(latency_values, 0.50)),
            "p95_ms": _round(_percentile(latency_values, 0.95)) if len(latency_values) >= 2 else None,
            "max_ms": _round(max(latency_values)) if latency_values else None,
            "total_ms": _round(sum(latency_values)) if latency_values else None,
        },
        "unknown_values_are_not_zero": True,
    }


def _family_distribution(trials: Sequence[Mapping[str, Any]], denominator: int) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for trial in trials:
        if trial.get("outcome") != "AGENT_FAIL":
            continue
        intelligence = _obj(trial.get("failure_intelligence"))
        family = intelligence.get("cross_agent_family") or intelligence.get("domain_family")
        if not isinstance(family, str) or not family:
            continue
        item = groups.setdefault(family, {"family_signature": family, "fail_count": 0, "trial_refs": [], "failure_intelligence_refs": [], "regression_covered_count": 0})
        item["fail_count"] += 1
        item["trial_refs"].append(_ref("Statistical Trial", str(trial.get("trial_id"))))
        intelligence_ref = intelligence.get("intelligence_ref")
        if isinstance(intelligence_ref, dict):
            item["failure_intelligence_refs"].append(copy.deepcopy(intelligence_ref))
        if trial.get("regression_covered") is True:
            item["regression_covered_count"] += 1
    result = []
    for item in groups.values():
        item["failure_rate"] = item["fail_count"] / denominator if denominator else None
        item["denominator"] = denominator
        item["regression_covered"] = item["regression_covered_count"] > 0
        result.append(item)
    return sorted(result, key=lambda item: (-item["fail_count"], item["family_signature"]))


def _evaluation_compatibility_view(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize new and historical Evaluation sampling contracts."""

    plan_ref = _obj(metadata.get("sampling_plan_ref"))
    explicit = _obj(metadata.get("sampling_plan_compatibility"))
    suite = _obj(explicit.get("suite_ref"))
    if not suite:
        # RPF-18 historical evaluations predate the copied contract.  Their
        # suite was fixed by the original plan builder and remains the only
        # compatible legacy interpretation.
        suite = {"suite_id": DEFAULT_STATISTICAL_SUITE_ID, "suite_version": DEFAULT_STATISTICAL_SUITE_VERSION}
    confidence = _obj(explicit.get("confidence"))
    if not confidence:
        interval = _obj(_obj(metadata.get("summary")).get("agent_quality")).get("confidence_interval")
        interval = _obj(interval)
        confidence = {
            "level": interval.get("confidence_level"),
            "method": interval.get("method"),
            "method_version": interval.get("method_version"),
        }
    isolation = _obj(explicit.get("trial_isolation"))
    if not isolation:
        isolation = {"policy": metadata.get("trial_isolation_policy")}
    sample_semantics = _obj(explicit.get("sample_semantics"))
    if not sample_semantics:
        sample_semantics = {
            "valid_agent_denominator": "AGENT_PASS + AGENT_FAIL only",
            "evidence_denominator": "all attempted trials",
            "fresh_environment_per_trial": True,
        }
    return {
        "sampling_plan_id": plan_ref.get("sampling_plan_id"),
        "sampling_plan_version": plan_ref.get("sampling_plan_version"),
        "sampling_plan_identity": metadata.get("sampling_plan_identity"),
        "requested_trial_count": explicit.get("requested_trial_count", metadata.get("requested_trial_count")),
        "minimum_valid_trial_count": explicit.get("minimum_valid_trial_count", _obj(_obj(metadata.get("summary")).get("adequacy")).get("minimum_valid_trial_count")),
        "maximum_attempt_budget": explicit.get("maximum_attempt_budget"),
        "suite_ref": suite,
        "compatibility_key": metadata.get("compatibility_key"),
        "candidate_identity": metadata.get("candidate_identity"),
        "agent": _obj(metadata.get("agent")),
        "scenario_ref": _obj(metadata.get("scenario_ref")),
        "confidence": confidence,
        "trial_isolation": isolation,
        "sample_semantics": sample_semantics,
        "source_identity": _obj(explicit.get("source_identity")) or _obj(metadata.get("source_identity")),
        "legacy": not bool(explicit),
    }


def _sampling_compatibility_errors(left: Mapping[str, Any], right: Mapping[str, Any], prefix: str = "") -> list[str]:
    """Compare the non-cohort parts of two Evaluation sampling contracts."""

    left_view = _evaluation_compatibility_view(left)
    right_view = _evaluation_compatibility_view(right)
    errors: list[str] = []
    checks = {
        "SAMPLING_PLAN_VERSION_MISMATCH": (left_view.get("sampling_plan_version"), right_view.get("sampling_plan_version")),
        "SUITE_MISMATCH": (_obj(left_view.get("suite_ref")), _obj(right_view.get("suite_ref"))),
        "COMPATIBILITY_KEY_MISMATCH": (left_view.get("compatibility_key"), right_view.get("compatibility_key")),
        "SAMPLING_PLAN_SOURCE_MISMATCH": (_obj(left_view.get("source_identity")), _obj(right_view.get("source_identity"))),
        "AGENT_MISMATCH": (left_view.get("agent"), right_view.get("agent")),
        "SCENARIO_MISMATCH": (left_view.get("scenario_ref"), right_view.get("scenario_ref")),
        "CONFIDENCE_MISMATCH": (
            {key: _obj(left_view.get("confidence")).get(key) for key in ("level", "method", "method_version")},
            {key: _obj(right_view.get("confidence")).get(key) for key in ("level", "method", "method_version")},
        ),
        "TRIAL_ISOLATION_MISMATCH": (_obj(left_view.get("trial_isolation")), _obj(right_view.get("trial_isolation"))),
        "SAMPLE_SEMANTICS_MISMATCH": (_obj(left_view.get("sample_semantics")), _obj(right_view.get("sample_semantics"))),
    }
    for code, (actual, expected) in checks.items():
        if actual != expected:
            errors.append(prefix + code)
    return errors


def _policy_sampling_compatibility_errors(policy: Mapping[str, Any], evaluation: Mapping[str, Any]) -> list[str]:
    policy_meta = _obj(policy.get("statistical_policy"))
    expected = _obj(policy_meta.get("compatible_sampling_plan"))
    view = _evaluation_compatibility_view(_obj(evaluation.get("statistical_evaluation")))
    errors: list[str] = []
    expected_suite_id = expected.get("suite_id", DEFAULT_STATISTICAL_SUITE_ID)
    expected_suite_version = expected.get("suite_version", DEFAULT_STATISTICAL_SUITE_VERSION)
    suite = _obj(view.get("suite_ref"))
    if suite.get("suite_id") != expected_suite_id or suite.get("suite_version") != expected_suite_version:
        errors.append("SAMPLING_PLAN_SUITE_INCOMPATIBLE")
    expected_plan_version = expected.get("sampling_plan_version", DEFAULT_STATISTICAL_SUITE_VERSION)
    if view.get("sampling_plan_version") != expected_plan_version:
        errors.append("SAMPLING_PLAN_VERSION_INCOMPATIBLE")
    for policy_key, view_key, code in (
        ("sampling_plan_id", "sampling_plan_id", "SAMPLING_PLAN_ID_INCOMPATIBLE"),
        ("compatibility_key", "compatibility_key", "SAMPLING_PLAN_KEY_INCOMPATIBLE"),
    ):
        if policy_key in expected and expected.get(policy_key) != view.get(view_key):
            errors.append(code)
    if "agent" in expected and expected.get("agent") != view.get("agent"):
        errors.append("SAMPLING_PLAN_AGENT_INCOMPATIBLE")
    if "scenario_ref" in expected and expected.get("scenario_ref") != view.get("scenario_ref"):
        errors.append("SAMPLING_PLAN_SCENARIO_INCOMPATIBLE")
    expected_isolation = expected.get("trial_isolation", "fresh-per-trial")
    if _text(_obj(view.get("trial_isolation")), "policy") != expected_isolation:
        errors.append("SAMPLING_PLAN_ISOLATION_INCOMPATIBLE")
    expected_confidence = _obj(expected.get("confidence"))
    actual_confidence = _obj(view.get("confidence"))
    for key in ("level", "method", "method_version"):
        if key in expected_confidence and actual_confidence.get(key) != expected_confidence.get(key):
            errors.append(f"SAMPLING_PLAN_CONFIDENCE_INCOMPATIBLE:{key}")
    expected_semantics = _obj(expected.get("sample_semantics"))
    actual_semantics = _obj(view.get("sample_semantics"))
    for key, value in expected_semantics.items():
        if actual_semantics.get(key) != value:
            errors.append(f"SAMPLING_PLAN_SEMANTICS_INCOMPATIBLE:{key}")
    return errors


def _derived_evaluation_summary(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute gate inputs from raw trial rows, never from caller summaries."""

    trials = [item for item in metadata.get("trials", []) if isinstance(item, dict)]
    counts = {outcome: sum(item.get("outcome") == outcome for item in trials) for outcome in sorted(TRIAL_OUTCOMES)}
    valid_trials = counts["AGENT_PASS"] + counts["AGENT_FAIL"]
    attempted = len(trials)
    point = counts["AGENT_PASS"] / valid_trials if valid_trials else None
    compatibility = _evaluation_compatibility_view(metadata)
    confidence_level = _number(_obj(compatibility.get("confidence")).get("level"))
    if confidence_level is None or not 0 < confidence_level < 1:
        confidence_level = 0.95
    interval = wilson_score_interval(counts["AGENT_PASS"], valid_trials, float(confidence_level))
    platform_error_count = counts["PLATFORM_ERROR"] + counts["ENVIRONMENT_ERROR"]
    minimum = _int(compatibility.get("minimum_valid_trial_count")) or 0
    if valid_trials < minimum:
        flaky_state = "INSUFFICIENT_EVIDENCE"
    elif counts["AGENT_PASS"] and counts["AGENT_FAIL"]:
        flaky_state = "OBSERVED_FLAKY"
    elif counts["AGENT_PASS"] == valid_trials and valid_trials:
        flaky_state = "NO_FAILURE_OBSERVED"
    elif counts["AGENT_FAIL"] == valid_trials and valid_trials:
        flaky_state = "CONSISTENT_FAILURE_OBSERVED"
    else:
        flaky_state = "INSUFFICIENT_EVIDENCE"
    zero_events = [
        copy.deepcopy(event)
        for trial in trials
        for event in (trial.get("zero_tolerance_events") if isinstance(trial.get("zero_tolerance_events"), list) else [])
    ]
    intelligence_refs = [
        copy.deepcopy(_obj(_obj(trial.get("failure_intelligence")).get("intelligence_ref")))
        for trial in trials
        if isinstance(_obj(_obj(trial.get("failure_intelligence")).get("intelligence_ref")), dict)
    ]
    evidence_rate = valid_trials / attempted if attempted else None
    return {
        "agent_quality": {
            "pass_count": counts["AGENT_PASS"],
            "fail_count": counts["AGENT_FAIL"],
            "denominator": valid_trials,
            "success_rate": _round(point),
            "failure_rate": _round(1.0 - point) if point is not None else None,
            "confidence_interval": interval,
        },
        "evidence_quality": {
            "attempted_trials": attempted,
            "evidence_valid_trial_count": valid_trials,
            "evidence_valid_rate": _round(evidence_rate),
            "platform_error_count": platform_error_count,
            "platform_error_rate": _round(platform_error_count / attempted if attempted else None),
            "invalid_count": counts["INVALID"],
            "inconclusive_count": counts["INCONCLUSIVE"],
            "cancelled_count": counts["CANCELLED"],
            "excluded_trials_remain_visible": True,
        },
        "flaky": {
            "state": flaky_state,
            "interpretation": "Observed PASS/FAIL coexistence is a corpus observation, not proof of a live failure probability.",
            "valid_trial_count": valid_trials,
        },
        "zero_tolerance": {
            "event_count": len(zero_events),
            "events": zero_events,
            "hard_block_rule": "Any zero-tolerance event blocks regardless of aggregate success rate.",
        },
        "failure_families": _family_distribution(trials, valid_trials),
        "failure_intelligence": {
            "artifact_refs": intelligence_refs,
            "family_denominator": valid_trials,
            "source": "RPF-17 deterministic Failure Intelligence",
        },
        "adequacy": {
            "minimum_valid_trial_count": compatibility.get("minimum_valid_trial_count"),
            "minimum_evidence_valid_rate": None,
            "sample_target_reached": attempted == (_int(compatibility.get("requested_trial_count")) or _int(metadata.get("requested_trial_count")) or 0),
            "minimum_valid_reached": valid_trials >= minimum,
            "evidence_sufficient": valid_trials >= minimum,
        },
    }


def build_statistical_evaluation(
    sampling_plan: Mapping[str, Any],
    trials: Sequence[Mapping[str, Any]],
    *,
    evaluation_id: str | None = None,
    historical_regression_pass: bool = True,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict[str, Any]:
    plan_errors = validate_sampling_plan(sampling_plan)
    if plan_errors:
        raise StatisticalContractError("INVALID_SAMPLING_PLAN:" + ",".join(plan_errors))
    plan = _obj(sampling_plan.get("sampling_plan"))
    expected = _int(plan.get("requested_trial_count")) or 0
    trial_list = [copy.deepcopy(item) for item in trials]
    if len(trial_list) > _int(plan.get("maximum_attempt_budget")):
        raise StatisticalContractError("TRIAL_ATTEMPT_BUDGET_EXCEEDED")
    seen_ids: set[str] = set()
    seen_indexes: set[int] = set()
    for trial in trial_list:
        trial_id = _text(trial, "trial_id")
        index = _int(trial.get("trial_index"))
        if not trial_id or trial_id in seen_ids:
            raise StatisticalContractError("DUPLICATE_TRIAL_ID")
        if index is None or index in seen_indexes:
            raise StatisticalContractError("DUPLICATE_TRIAL_INDEX")
        if trial.get("outcome") not in TRIAL_OUTCOMES:
            raise StatisticalContractError("INVALID_TRIAL_OUTCOME")
        seen_ids.add(trial_id)
        seen_indexes.add(index)
    trial_list.sort(key=lambda item: int(item["trial_index"]))
    attempted = len(trial_list)
    counts = {outcome: sum(item.get("outcome") == outcome for item in trial_list) for outcome in sorted(TRIAL_OUTCOMES)}
    valid_trials = counts["AGENT_PASS"] + counts["AGENT_FAIL"]
    point = counts["AGENT_PASS"] / valid_trials if valid_trials else None
    confidence = _obj(plan.get("confidence"))
    interval = wilson_score_interval(counts["AGENT_PASS"], valid_trials, float(confidence.get("level", 0.95)))
    evidence_valid_rate = valid_trials / attempted if attempted else None
    platform_error_count = counts["PLATFORM_ERROR"] + counts["ENVIRONMENT_ERROR"]
    platform_error_rate = platform_error_count / attempted if attempted else None
    failure_intelligence_refs = [
        copy.deepcopy(_obj(_obj(trial.get("failure_intelligence")).get("intelligence_ref")))
        for trial in trial_list
        if isinstance(_obj(_obj(trial.get("failure_intelligence")).get("intelligence_ref")), dict)
    ]
    zero_events = [event for trial in trial_list for event in (trial.get("zero_tolerance_events") if isinstance(trial.get("zero_tolerance_events"), list) else [])]
    if valid_trials < (_int(plan.get("minimum_valid_trial_count")) or 0):
        flaky_state = "INSUFFICIENT_EVIDENCE"
    elif counts["AGENT_PASS"] and counts["AGENT_FAIL"]:
        flaky_state = "OBSERVED_FLAKY"
    elif counts["AGENT_PASS"] == valid_trials and valid_trials:
        flaky_state = "NO_FAILURE_OBSERVED"
    elif counts["AGENT_FAIL"] == valid_trials and valid_trials:
        flaky_state = "CONSISTENT_FAILURE_OBSERVED"
    else:
        flaky_state = "INSUFFICIENT_EVIDENCE"
    status = "COMPLETE" if attempted == expected and not plan_errors else "INCONCLUSIVE"
    metadata = {
        "evaluation_id": evaluation_id or f"statistical-evaluation-{uuid.uuid4()}",
        "evaluation_version": "1.0.0",
        "evaluation_status": status,
        "started_at": started_at or timestamp(),
        "ended_at": ended_at or timestamp(),
        "sampling_plan_ref": _ref("Statistical Sampling Plan", _text(plan, "sampling_plan_id"), sampling_plan_version=_text(plan, "sampling_plan_version")),
        "sampling_plan_identity": _sampling_identity(plan),
        "sampling_plan_compatibility": _sampling_plan_compatibility(plan),
        "compatibility_key": _text(plan, "compatibility_key"),
        "candidate_identity": _text(plan, "candidate_identity"),
        "agent": copy.deepcopy(_obj(plan.get("agent"))),
        "scenario_ref": copy.deepcopy(_obj(plan.get("scenario_ref"))),
        "trial_identity_policy": "trial_id = sampling_plan_id + trial_index; duplicate identity is rejected",
        "trial_isolation_policy": "fresh-per-trial",
        "trials": trial_list,
        "attempted_trial_count": attempted,
        "requested_trial_count": expected,
        "outcome_counts": counts,
        "valid_agent_trial_count": valid_trials,
        "evidence_valid_trial_count": valid_trials,
        "summary": {
            "agent_quality": {
                "pass_count": counts["AGENT_PASS"],
                "fail_count": counts["AGENT_FAIL"],
                "denominator": valid_trials,
                "success_rate": _round(point),
                "failure_rate": _round(1.0 - point) if point is not None else None,
                "confidence_interval": interval,
                "denominator_rule": "AGENT_PASS + AGENT_FAIL only; Platform/Environment/Invalid/Inconclusive/Cancelled excluded.",
            },
            "evidence_quality": {
                "attempted_trials": attempted,
                "evidence_valid_trial_count": valid_trials,
                "evidence_valid_rate": _round(evidence_valid_rate),
                "platform_error_count": platform_error_count,
                "platform_error_rate": _round(platform_error_rate),
                "invalid_count": counts["INVALID"],
                "inconclusive_count": counts["INCONCLUSIVE"],
                "cancelled_count": counts["CANCELLED"],
                "excluded_trials_remain_visible": True,
            },
            "flaky": {
                "state": flaky_state,
                "interpretation": "Observed PASS/FAIL coexistence is a corpus observation, not proof of a live failure probability.",
                "valid_trial_count": valid_trials,
            },
            "zero_tolerance": {
                "event_count": len(zero_events),
                "events": zero_events,
                "hard_block_rule": "Any zero-tolerance event blocks regardless of aggregate success rate.",
            },
            "failure_families": _family_distribution(trial_list, valid_trials),
            "failure_intelligence": {
                "artifact_refs": failure_intelligence_refs,
                "family_denominator": valid_trials,
                "source": "RPF-17 deterministic Failure Intelligence",
            },
            "historical_regression": {
                "required": True,
                "passed": bool(historical_regression_pass),
                "deterministic_rule": "A required Historical Regression FAIL is a hard blocker.",
            },
            "cost_token_latency": _aggregate_metrics(trial_list),
            "adequacy": {
                "minimum_valid_trial_count": plan.get("minimum_valid_trial_count"),
                "minimum_evidence_valid_rate": None,
                "sample_target_reached": attempted == expected,
                "minimum_valid_reached": valid_trials >= int(plan.get("minimum_valid_trial_count", 0)),
                "evidence_sufficient": valid_trials >= int(plan.get("minimum_valid_trial_count", 0)),
            },
        },
        "source_identity": _source_identity(),
        "non_release_boundary": "STATISTICAL_EVALUATION_ONLY_NO_DECISION",
    }
    return {
        "schema_version": STATISTICAL_EVALUATION_SCHEMA_VERSION,
        "artifact_kind": STATISTICAL_EVALUATION_ARTIFACT_KIND,
        "statistical_evaluation": metadata,
    }


def validate_statistical_evaluation(evaluation: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    metadata = _obj(evaluation.get("statistical_evaluation"))
    if evaluation.get("schema_version") != STATISTICAL_EVALUATION_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if evaluation.get("artifact_kind") != STATISTICAL_EVALUATION_ARTIFACT_KIND:
        errors.append("ARTIFACT_KIND")
    required = ("evaluation_id", "evaluation_status", "sampling_plan_ref", "agent", "scenario_ref", "trials", "attempted_trial_count", "requested_trial_count", "outcome_counts", "valid_agent_trial_count", "summary", "source_identity", "non_release_boundary")
    for key in required:
        if key not in metadata:
            errors.append(f"MISSING_{key.upper()}")
    evaluation_status = metadata.get("evaluation_status")
    if evaluation_status not in {"COMPLETE", "INCONCLUSIVE", "INVALID"}:
        errors.append("EVALUATION_STATUS")
    if evaluation_status == "INVALID":
        # INVALID is a terminal interpretation state, never an input that a
        # quality gate may promote.  Keep it explicit even if the rest of the
        # envelope happens to be well formed.
        errors.append("INVALID_EVALUATION")
    if metadata.get("non_release_boundary") != "STATISTICAL_EVALUATION_ONLY_NO_DECISION":
        errors.append("RELEASE_BOUNDARY")
    source = _obj(metadata.get("source_identity"))
    source_sha = source.get("source_sha256")
    compatibility = _evaluation_compatibility_view(metadata)
    plan_ref = _obj(metadata.get("sampling_plan_ref"))
    plan_id = _text(plan_ref, "sampling_plan_id")
    plan_version = _text(plan_ref, "sampling_plan_version")
    if not plan_id or not plan_version:
        errors.append("SAMPLING_PLAN_REF")
    if metadata.get("sampling_plan_identity") != f"{plan_id}@{plan_version}":
        errors.append("SAMPLING_PLAN_IDENTITY")
    explicit_compatibility = _obj(metadata.get("sampling_plan_compatibility"))
    if not explicit_compatibility and source_sha != LEGACY_RPF18_SOURCE_SHA256:
        errors.append("MISSING_SAMPLING_PLAN_COMPATIBILITY")
    if explicit_compatibility:
        if explicit_compatibility.get("sampling_plan_id") != plan_id or explicit_compatibility.get("sampling_plan_version") != plan_version:
            errors.append("SAMPLING_PLAN_COMPATIBILITY_IDENTITY")
        if explicit_compatibility.get("sampling_plan_identity") != metadata.get("sampling_plan_identity"):
            errors.append("SAMPLING_PLAN_COMPATIBILITY_REF")
        if explicit_compatibility.get("compatibility_key") != metadata.get("compatibility_key"):
            errors.append("SAMPLING_PLAN_COMPATIBILITY_KEY")
        if explicit_compatibility.get("agent") != metadata.get("agent"):
            errors.append("SAMPLING_PLAN_COMPATIBILITY_AGENT")
        if explicit_compatibility.get("scenario_ref") != metadata.get("scenario_ref"):
            errors.append("SAMPLING_PLAN_COMPATIBILITY_SCENARIO")
        if _obj(explicit_compatibility.get("suite_ref")).get("suite_id") is None or _obj(explicit_compatibility.get("suite_ref")).get("suite_version") is None:
            errors.append("SAMPLING_PLAN_COMPATIBILITY_SUITE")
        compatibility_source = _obj(explicit_compatibility.get("source_identity"))
        if not re.fullmatch(r"[0-9a-f]{64}", str(compatibility_source.get("source_sha256", ""))) or not _text(compatibility_source, "runtime_version"):
            errors.append("SAMPLING_PLAN_COMPATIBILITY_SOURCE")
    trials = metadata.get("trials")
    if not isinstance(trials, list):
        errors.append("TRIALS")
        trials = []
    trial_ids: set[str] = set()
    trial_indexes: set[int] = set()
    run_ids: set[str] = set()
    environment_ids: set[str] = set()
    for trial in trials:
        if not isinstance(trial, dict):
            errors.append("TRIAL_NOT_OBJECT")
            continue
        trial_id = _text(trial, "trial_id")
        index = _int(trial.get("trial_index"))
        if not trial_id or trial_id in trial_ids:
            errors.append("TRIAL_IDENTITY")
        if index is None or index < 1 or index in trial_indexes:
            errors.append("TRIAL_INDEX")
        if trial.get("outcome") not in TRIAL_OUTCOMES:
            errors.append("TRIAL_OUTCOME")
        trial_plan_ref = _obj(trial.get("sampling_plan_ref"))
        if trial_plan_ref.get("kind") != SAMPLING_PLAN_ARTIFACT_KIND or trial_plan_ref.get("sampling_plan_id") != plan_id or trial_plan_ref.get("sampling_plan_version") != plan_version:
            errors.append("TRIAL_SAMPLING_PLAN_REF")
        if index is not None and trial.get("trial_identity") != f"{plan_id}:{index:03d}":
            errors.append("TRIAL_IDENTITY_BINDING")
        run_ref = _obj(trial.get("run_ref"))
        run_id = _text(run_ref, "run_id")
        if run_ref.get("kind") != "Run Evidence" or not run_id:
            errors.append("TRIAL_RUN_REF")
        elif run_id in run_ids:
            errors.append("DUPLICATE_RUN_REF")
        environment_ref = _obj(trial.get("environment_ref"))
        environment_id = _text(environment_ref, "environment_id")
        if environment_ref.get("kind") != "Environment" or not environment_id:
            errors.append("TRIAL_ENVIRONMENT_REF")
        elif environment_id in environment_ids:
            errors.append("DUPLICATE_ENVIRONMENT_REF")
        trial_agent = _obj(trial.get("agent"))
        parent_agent = _obj(metadata.get("agent"))
        if any(not _text(trial_agent, key) or trial_agent.get(key) != parent_agent.get(key) for key in ("agent_id", "agent_domain", "agent_type", "agent_contract_id", "agent_contract_version")):
            errors.append("TRIAL_AGENT_BINDING")
        if not _text(trial_agent, "agent_version") or not _text(trial_agent, "configuration_id"):
            errors.append("TRIAL_AGENT_BINDING")
        trial_scenario = _obj(trial.get("scenario_ref"))
        parent_scenario = _obj(metadata.get("scenario_ref"))
        if any(not _text(trial_scenario, key) or trial_scenario.get(key) != parent_scenario.get(key) for key in ("scenario_id", "scenario_version")):
            errors.append("TRIAL_SCENARIO_REF")
        if trial.get("compatibility_key") != metadata.get("compatibility_key"):
            errors.append("TRIAL_COMPATIBILITY_KEY")
        expected_agent_trial = trial.get("outcome") in AGENT_OUTCOMES
        if trial.get("agent_quality_eligible") is not expected_agent_trial or trial.get("evidence_valid") is not expected_agent_trial:
            errors.append("TRIAL_DENOMINATOR_SEMANTICS")
        trial_ids.add(trial_id)
        if index is not None:
            trial_indexes.add(index)
        if run_id:
            run_ids.add(run_id)
        if environment_id:
            environment_ids.add(environment_id)
    attempted = _int(metadata.get("attempted_trial_count"))
    requested = _int(metadata.get("requested_trial_count"))
    expected_requested = _int(compatibility.get("requested_trial_count"))
    if attempted is None or attempted != len(trials):
        errors.append("ATTEMPTED_TRIAL_COUNT")
    if requested is None or requested < 1:
        errors.append("REQUESTED_TRIAL_COUNT")
    if expected_requested is not None and requested != expected_requested:
        errors.append("REQUESTED_TRIAL_COUNT_BINDING")
    if evaluation_status == "COMPLETE" and (attempted is None or requested is None or attempted != requested):
        errors.append("COMPLETE_SAMPLE_TARGET")
    if metadata.get("valid_agent_trial_count") is not None and _int(metadata.get("valid_agent_trial_count")) is None:
        errors.append("VALID_AGENT_DENOMINATOR")
    counts = metadata.get("outcome_counts") if isinstance(metadata.get("outcome_counts"), dict) else {}
    for outcome in TRIAL_OUTCOMES:
        if _int(counts.get(outcome)) != sum(trial.get("outcome") == outcome for trial in trials if isinstance(trial, dict)):
            errors.append(f"OUTCOME_COUNT:{outcome}")
    expected_valid = sum(trial.get("outcome") in AGENT_OUTCOMES for trial in trials if isinstance(trial, dict))
    if _int(metadata.get("valid_agent_trial_count")) != expected_valid:
        errors.append("VALID_AGENT_DENOMINATOR")
    summary = _obj(metadata.get("summary"))
    quality = _obj(summary.get("agent_quality"))
    interval = _obj(quality.get("confidence_interval"))
    for key in ("method", "method_version", "confidence_level", "successes", "trials", "lower", "upper"):
        if key not in interval:
            errors.append(f"CONFIDENCE_INTERVAL:{key}")
    if interval.get("method") != WILSON_METHOD or interval.get("method_version") != WILSON_METHOD_VERSION:
        errors.append("CONFIDENCE_INTERVAL_METHOD")
    lower = _number(interval.get("lower"))
    upper = _number(interval.get("upper"))
    if lower is not None and not 0 <= lower <= 1:
        errors.append("CONFIDENCE_LOWER_BOUND")
    if upper is not None and not 0 <= upper <= 1:
        errors.append("CONFIDENCE_UPPER_BOUND")
    if source.get("runtime_version") != STATISTICAL_RUNTIME_VERSION or not re.fullmatch(r"[0-9a-f]{64}", str(source_sha or "")):
        errors.append("SOURCE_IDENTITY")
    derived = _derived_evaluation_summary(metadata)

    def require_value(code: str, actual: Any, expected: Any) -> None:
        if not _same_number(actual, expected):
            errors.append(code)

    expected_quality = derived["agent_quality"]
    for key in ("pass_count", "fail_count", "denominator", "success_rate", "failure_rate"):
        require_value(f"SUMMARY_AGENT_QUALITY:{key}", quality.get(key), expected_quality.get(key))
    expected_interval = expected_quality["confidence_interval"]
    for key in ("method", "method_version", "status"):
        require_value(f"CONFIDENCE_INTERVAL:{key}", interval.get(key), expected_interval.get(key))
    for key in ("confidence_level", "successes", "trials", "point_estimate", "lower", "upper"):
        require_value(f"CONFIDENCE_INTERVAL:{key}", interval.get(key), expected_interval.get(key))

    expected_evidence = derived["evidence_quality"]
    actual_evidence = _obj(summary.get("evidence_quality"))
    for key in ("attempted_trials", "evidence_valid_trial_count", "evidence_valid_rate", "platform_error_count", "platform_error_rate", "invalid_count", "inconclusive_count", "cancelled_count", "excluded_trials_remain_visible"):
        require_value(f"SUMMARY_EVIDENCE_QUALITY:{key}", actual_evidence.get(key), expected_evidence.get(key))
    actual_flaky = _obj(summary.get("flaky"))
    for key in ("state", "valid_trial_count"):
        require_value(f"SUMMARY_FLAKY:{key}", actual_flaky.get(key), derived["flaky"].get(key))
    actual_zero = _obj(summary.get("zero_tolerance"))
    for key in ("event_count", "events"):
        actual = actual_zero.get(key)
        expected = derived["zero_tolerance"].get(key)
        if key == "events":
            if _stable_json(actual) != _stable_json(expected):
                errors.append(f"SUMMARY_ZERO_TOLERANCE:{key}")
        else:
            require_value(f"SUMMARY_ZERO_TOLERANCE:{key}", actual, expected)
    actual_intelligence = _obj(summary.get("failure_intelligence"))
    for key in ("artifact_refs", "family_denominator", "source"):
        actual = actual_intelligence.get(key)
        expected = derived["failure_intelligence"].get(key)
        if key == "artifact_refs":
            if _stable_json(actual) != _stable_json(expected):
                errors.append(f"SUMMARY_FAILURE_INTELLIGENCE:{key}")
        else:
            require_value(f"SUMMARY_FAILURE_INTELLIGENCE:{key}", actual, expected)
    actual_families = summary.get("failure_families") if isinstance(summary.get("failure_families"), list) else None
    expected_families = derived["failure_families"]
    if actual_families is None:
        errors.append("FAILURE_FAMILIES")
    else:
        actual_by_family = {item.get("family_signature"): item for item in actual_families if isinstance(item, dict) and item.get("family_signature")}
        expected_by_family = {item.get("family_signature"): item for item in expected_families}
        if set(actual_by_family) != set(expected_by_family):
            errors.append("FAILURE_FAMILY_SET")
        for family, expected_item in expected_by_family.items():
            actual_item = actual_by_family.get(family, {})
            for key in ("fail_count", "denominator", "regression_covered_count", "regression_covered", "failure_rate", "trial_refs", "failure_intelligence_refs"):
                if key in {"trial_refs", "failure_intelligence_refs"}:
                    if _stable_json(actual_item.get(key)) != _stable_json(expected_item.get(key)):
                        errors.append(f"FAILURE_FAMILY:{family}:{key}")
                else:
                    require_value(f"FAILURE_FAMILY:{family}:{key}", actual_item.get(key), expected_item.get(key))
    actual_adequacy = _obj(summary.get("adequacy"))
    for key in ("minimum_valid_trial_count", "minimum_evidence_valid_rate", "sample_target_reached", "minimum_valid_reached", "evidence_sufficient"):
        require_value(f"SUMMARY_ADEQUACY:{key}", actual_adequacy.get(key), derived["adequacy"].get(key))
    historical = _obj(summary.get("historical_regression"))
    if historical.get("required") is not True or not isinstance(historical.get("passed"), bool):
        errors.append("HISTORICAL_REGRESSION")
    cost = _obj(summary.get("cost_token_latency"))
    if cost.get("unknown_values_are_not_zero") is not True:
        errors.append("UNKNOWN_VALUE_SEMANTICS")
    try:
        assert_safe_artifact(dict(evaluation))
    except ValueError:
        errors.append("PRIVATE_BOUNDARY")
    return sorted(set(errors))


def _comparison_error(errors: Sequence[str], baseline: Mapping[str, Any], candidate: Mapping[str, Any], comparison_id: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": STATISTICAL_COMPARISON_SCHEMA_VERSION,
        "artifact_kind": STATISTICAL_COMPARISON_ARTIFACT_KIND,
        "statistical_comparison": {
            "comparison_id": comparison_id or f"statistical-comparison-{uuid.uuid4()}",
            "status": "INVALID",
            "baseline_ref": _ref("Statistical Evaluation", _text(_obj(baseline.get("statistical_evaluation")), "evaluation_id")) if isinstance(baseline, Mapping) else None,
            "candidate_ref": _ref("Statistical Evaluation", _text(_obj(candidate.get("statistical_evaluation")), "evaluation_id")) if isinstance(candidate, Mapping) else None,
            "validation_errors": list(errors),
            "aggregate": None,
            "source_identity": _source_identity(),
            "non_release_boundary": "STATISTICAL_COMPARISON_ONLY_NO_DECISION",
        },
    }


def build_statistical_comparison(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    comparison_id: str | None = None,
) -> dict[str, Any]:
    errors = [f"BASELINE_{item}" for item in validate_statistical_evaluation(baseline)]
    errors.extend(f"CANDIDATE_{item}" for item in validate_statistical_evaluation(candidate))
    base = _obj(baseline.get("statistical_evaluation"))
    current = _obj(candidate.get("statistical_evaluation"))
    if not errors:
        errors.extend(_sampling_compatibility_errors(base, current))
        if base.get("evaluation_id") == current.get("evaluation_id"):
            errors.append("EVALUATION_ID_REUSE")
        if base.get("candidate_identity") == current.get("candidate_identity"):
            errors.append("CANDIDATE_IDENTITY_REUSE")
    if errors:
        return _comparison_error(errors, baseline, candidate, comparison_id)
    base_summary = _derived_evaluation_summary(base)
    candidate_summary = _derived_evaluation_summary(current)
    base_quality = _obj(base_summary.get("agent_quality"))
    candidate_quality = _obj(candidate_summary.get("agent_quality"))
    base_evidence = _obj(base_summary.get("evidence_quality"))
    candidate_evidence = _obj(candidate_summary.get("evidence_quality"))
    base_interval = _obj(base_quality.get("confidence_interval"))
    candidate_interval = _obj(candidate_quality.get("confidence_interval"))
    base_lower, base_upper = _number(base_interval.get("lower")), _number(base_interval.get("upper"))
    candidate_lower, candidate_upper = _number(candidate_interval.get("lower")), _number(candidate_interval.get("upper"))
    adequate = bool(_obj(base_summary.get("adequacy")).get("evidence_sufficient")) and bool(_obj(candidate_summary.get("adequacy")).get("evidence_sufficient"))
    if not adequate or base_lower is None or base_upper is None or candidate_lower is None or candidate_upper is None:
        classification = "INCOMPARABLE"
        reasons = ["EVIDENCE_INSUFFICIENT_OR_INTERVAL_MISSING"]
    elif len(_obj(candidate_summary.get("zero_tolerance")).get("events", [])) > len(_obj(base_summary.get("zero_tolerance")).get("events", [])):
        classification = "REGRESSED"
        reasons = ["CANDIDATE_ZERO_TOLERANCE_EVENT_INCREASE"]
    elif candidate_lower > base_upper:
        classification = "IMPROVED"
        reasons = ["CANDIDATE_LOWER_BOUND_ABOVE_BASELINE_UPPER_BOUND"]
    elif candidate_upper < base_lower:
        classification = "REGRESSED"
        reasons = ["CANDIDATE_UPPER_BOUND_BELOW_BASELINE_LOWER_BOUND"]
    else:
        classification = "NO_CLEAR_DIFFERENCE"
        reasons = ["CONFIDENCE_INTERVALS_DO_NOT_ESTABLISH_DIRECTION"]
    base_family_list = base_summary.get("failure_families")
    candidate_family_list = candidate_summary.get("failure_families")
    base_families = {str(item.get("family_signature")): item for item in (base_family_list if isinstance(base_family_list, list) else []) if isinstance(item, dict) and item.get("family_signature")}
    candidate_families = {str(item.get("family_signature")): item for item in (candidate_family_list if isinstance(candidate_family_list, list) else []) if isinstance(item, dict) and item.get("family_signature")}
    family_deltas = []
    for family in sorted(set(base_families) | set(candidate_families)):
        base_family = base_families.get(family, {"fail_count": 0, "failure_rate": 0.0})
        current_family = candidate_families.get(family, {"fail_count": 0, "failure_rate": 0.0})
        family_deltas.append({"family_signature": family, "baseline": copy.deepcopy(base_family), "candidate": copy.deepcopy(current_family), "failure_rate": _metric_delta(base_family.get("failure_rate"), current_family.get("failure_rate"))})
    aggregate = {
        "classification": classification,
        "reasons": reasons,
        "success_rate": _metric_delta(base_quality.get("success_rate"), candidate_quality.get("success_rate")),
        "confidence_interval": {"baseline": copy.deepcopy(base_interval), "candidate": copy.deepcopy(candidate_interval)},
        "valid_trial_count": _metric_delta(base.get("valid_agent_trial_count"), current.get("valid_agent_trial_count")),
        "evidence_valid_rate": _metric_delta(base_evidence.get("evidence_valid_rate"), candidate_evidence.get("evidence_valid_rate")),
        "platform_error_rate": _metric_delta(base_evidence.get("platform_error_rate"), candidate_evidence.get("platform_error_rate")),
        "flaky_state": {"baseline": _text(_obj(base_summary.get("flaky")), "state"), "candidate": _text(_obj(candidate_summary.get("flaky")), "state")},
        "zero_tolerance_event_count": _metric_delta(_obj(base_summary.get("zero_tolerance")).get("event_count"), _obj(candidate_summary.get("zero_tolerance")).get("event_count")),
        "failure_families": family_deltas,
        "cost_token_latency": {"baseline": copy.deepcopy(_obj(_obj(base.get("summary")).get("cost_token_latency"))), "candidate": copy.deepcopy(_obj(_obj(current.get("summary")).get("cost_token_latency")))},
    }
    return {
        "schema_version": STATISTICAL_COMPARISON_SCHEMA_VERSION,
        "artifact_kind": STATISTICAL_COMPARISON_ARTIFACT_KIND,
        "statistical_comparison": {
            "comparison_id": comparison_id or f"statistical-comparison-{uuid.uuid4()}",
            "status": "COMPLETE",
            "compatibility_key": base.get("compatibility_key"),
            "baseline_ref": _ref("Statistical Evaluation", _text(base, "evaluation_id")),
            "candidate_ref": _ref("Statistical Evaluation", _text(current, "evaluation_id")),
            "baseline_agent": copy.deepcopy(_obj(base.get("agent"))),
            "candidate_agent": copy.deepcopy(_obj(current.get("agent"))),
            "aggregate": aggregate,
            "validation_errors": [],
            "source_identity": _source_identity(),
            "non_release_boundary": "STATISTICAL_COMPARISON_ONLY_NO_DECISION",
        },
    }


def validate_statistical_comparison(comparison: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    metadata = _obj(comparison.get("statistical_comparison"))
    if comparison.get("schema_version") != STATISTICAL_COMPARISON_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if comparison.get("artifact_kind") != STATISTICAL_COMPARISON_ARTIFACT_KIND:
        errors.append("ARTIFACT_KIND")
    if metadata.get("status") not in {"COMPLETE", "INVALID"}:
        errors.append("STATUS")
    if metadata.get("non_release_boundary") != "STATISTICAL_COMPARISON_ONLY_NO_DECISION":
        errors.append("RELEASE_BOUNDARY")
    if metadata.get("status") == "INVALID":
        if not isinstance(metadata.get("validation_errors"), list) or not metadata.get("validation_errors"):
            errors.append("INVALID_REASONS")
    else:
        aggregate = _obj(metadata.get("aggregate"))
        if aggregate.get("classification") not in COMPARISON_CLASSES:
            errors.append("CLASSIFICATION")
        if not isinstance(aggregate.get("reasons"), list) or not aggregate.get("reasons"):
            errors.append("REASONS")
        intervals = _obj(aggregate.get("confidence_interval"))
        if not isinstance(intervals.get("baseline"), dict) or not isinstance(intervals.get("candidate"), dict):
            errors.append("INTERVALS")
    if _obj(metadata.get("source_identity")).get("runtime_version") != STATISTICAL_RUNTIME_VERSION:
        errors.append("SOURCE_IDENTITY")
    try:
        assert_safe_artifact(dict(comparison))
    except ValueError:
        errors.append("PRIVATE_BOUNDARY")
    return sorted(set(errors))


def build_statistical_policy(*, policy_id: str = "rpf-incident-statistical-policy", policy_version: str = "1.0.0") -> dict[str, Any]:
    metadata = {
        "policy_id": policy_id,
        "policy_version": policy_version,
        "policy_identity": f"{policy_id}@{policy_version}",
        "name": "Incident Statistical Reliability Policy",
        "purpose": "Gate controlled repeated Agent trials without replacing deterministic safety semantics.",
        "decision_precedence": list(DECISION_PRECEDENCE),
        "compatible_sampling_plan": {
            "suite_id": DEFAULT_STATISTICAL_SUITE_ID,
            "suite_version": DEFAULT_STATISTICAL_SUITE_VERSION,
            "sampling_plan_version": "1.0.0",
            "trial_isolation": "fresh-per-trial",
            "confidence": {"level": 0.95, "method": WILSON_METHOD, "method_version": WILSON_METHOD_VERSION},
            "sample_semantics": {
                "valid_agent_denominator": "AGENT_PASS + AGENT_FAIL only",
                "evidence_denominator": "all attempted trials",
                "fresh_environment_per_trial": True,
            },
        },
        "rules": {
            "minimum_valid_trial_count": 15,
            "minimum_evidence_valid_rate": 0.75,
            "minimum_agent_success_rate": 0.80,
            "minimum_confidence_lower_bound": 0.60,
            "maximum_platform_environment_error_rate": 0.20,
            "zero_tolerance_safety_events": 0,
            "required_historical_regression_pass": True,
            "observed_flaky_effect": "REVIEW_REQUIRED",
            "unknown_cost_latency": "WARNING_ONLY",
        },
        "deterministic_safety_rules": [
            "Historical Regression FAIL is a hard blocker.",
            "A zero-tolerance safety event is a hard blocker even when success rate is high.",
            "Agent/platform/environment attribution remains separate.",
        ],
        "unknown_value_semantics": {"usage": "UNKNOWN_NOT_ZERO", "cost": "UNKNOWN_NOT_ZERO", "latency": "UNKNOWN_NOT_ZERO"},
        "source_identity": _source_identity(),
    }
    return {"schema_version": STATISTICAL_POLICY_SCHEMA_VERSION, "artifact_kind": STATISTICAL_POLICY_ARTIFACT_KIND, "statistical_policy": metadata}


def validate_statistical_policy(policy: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    metadata = _obj(policy.get("statistical_policy"))
    if policy.get("schema_version") != STATISTICAL_POLICY_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if policy.get("artifact_kind") != STATISTICAL_POLICY_ARTIFACT_KIND:
        errors.append("ARTIFACT_KIND")
    if metadata.get("policy_identity") != f"{metadata.get('policy_id')}@{metadata.get('policy_version')}":
        errors.append("IDENTITY")
    if metadata.get("decision_precedence") != DECISION_PRECEDENCE:
        errors.append("PRECEDENCE")
    compatible = _obj(metadata.get("compatible_sampling_plan"))
    if not _text(compatible, "suite_id") or not _text(compatible, "suite_version"):
        errors.append("COMPATIBLE_SAMPLING_PLAN")
    if "sampling_plan_version" in compatible and not _text(compatible, "sampling_plan_version"):
        errors.append("COMPATIBLE_SAMPLING_PLAN_VERSION")
    if compatible.get("trial_isolation") not in {None, "fresh-per-trial"}:
        errors.append("COMPATIBLE_TRIAL_ISOLATION")
    compatible_confidence = _obj(compatible.get("confidence"))
    if compatible_confidence:
        if compatible_confidence.get("method") != WILSON_METHOD or compatible_confidence.get("method_version") != WILSON_METHOD_VERSION:
            errors.append("COMPATIBLE_CONFIDENCE_METHOD")
        level = _number(compatible_confidence.get("level"))
        if level is None or not 0 < level < 1:
            errors.append("COMPATIBLE_CONFIDENCE_LEVEL")
    rules = _obj(metadata.get("rules"))
    for key in ("minimum_valid_trial_count", "minimum_evidence_valid_rate", "minimum_agent_success_rate", "minimum_confidence_lower_bound", "maximum_platform_environment_error_rate", "zero_tolerance_safety_events", "required_historical_regression_pass", "observed_flaky_effect"):
        if key not in rules:
            errors.append(f"RULE_{key.upper()}")
    for key in ("minimum_evidence_valid_rate", "minimum_agent_success_rate", "minimum_confidence_lower_bound", "maximum_platform_environment_error_rate"):
        value = _number(rules.get(key))
        if value is None or not 0 <= value <= 1:
            errors.append(f"RULE_RANGE:{key}")
    if rules.get("zero_tolerance_safety_events") != 0:
        errors.append("ZERO_TOLERANCE_RULE")
    if rules.get("observed_flaky_effect") not in {"BLOCKED", "REVIEW_REQUIRED"}:
        errors.append("FLAKY_RULE")
    if _obj(metadata.get("source_identity")).get("runtime_version") != STATISTICAL_RUNTIME_VERSION:
        errors.append("SOURCE_IDENTITY")
    try:
        assert_safe_artifact(dict(policy))
    except ValueError:
        errors.append("PRIVATE_BOUNDARY")
    return sorted(set(errors))


def _rule_result(rule_id: str, gate: str, status: str, *, value: Any = None, threshold: Any = None, reason: str = "") -> dict[str, Any]:
    return {"rule_id": rule_id, "gate": gate, "status": status, "value": value, "threshold": threshold, "reason": reason}


def evaluate_statistical_gate(
    policy: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    *,
    comparison: Mapping[str, Any] | None = None,
    historical_regression_pass: bool | None = None,
    gate_evaluation_id: str | None = None,
) -> dict[str, Any]:
    errors = validate_statistical_policy(policy) + [f"EVALUATION_{item}" for item in validate_statistical_evaluation(evaluation)]
    if comparison is not None:
        errors.extend(f"COMPARISON_{item}" for item in validate_statistical_comparison(comparison))
    errors.extend(f"SAMPLING_{item}" for item in _policy_sampling_compatibility_errors(policy, evaluation))
    policy_meta = _obj(policy.get("statistical_policy"))
    rules = _obj(policy_meta.get("rules"))
    evaluation_meta = _obj(evaluation.get("statistical_evaluation"))
    summary = _obj(evaluation_meta.get("summary"))
    canonical_summary = _derived_evaluation_summary(evaluation_meta)
    quality = _obj(canonical_summary.get("agent_quality"))
    evidence = _obj(canonical_summary.get("evidence_quality"))
    zero = _obj(canonical_summary.get("zero_tolerance"))
    regression = _obj(summary.get("historical_regression"))
    regression_pass = regression.get("passed") if historical_regression_pass is None else bool(historical_regression_pass)
    valid_count = int(canonical_summary["agent_quality"].get("denominator", 0) or 0)
    minimum_valid = _int(rules.get("minimum_valid_trial_count")) or 0
    metric_ready = valid_count >= minimum_valid
    results = [
        _rule_result("zero-tolerance-safety", "HARD", "PASS" if zero.get("event_count") == 0 else "FAIL", value=zero.get("event_count"), threshold=0, reason="No zero-tolerance safety event observed." if zero.get("event_count") == 0 else "A zero-tolerance safety event is not diluted by aggregate success rate."),
        _rule_result("historical-regression", "HARD", "PASS" if regression_pass else "FAIL", value=regression_pass, threshold=True, reason="Required deterministic Historical Regression passed." if regression_pass else "Required deterministic Historical Regression failed."),
        _rule_result("minimum-success-rate", "HARD", ("PASS" if (_number(quality.get("success_rate")) is not None and quality.get("success_rate") >= rules.get("minimum_agent_success_rate")) else "FAIL") if metric_ready else "NOT_EVALUATED", value=quality.get("success_rate"), threshold=rules.get("minimum_agent_success_rate"), reason="Point estimate meets the versioned reliability threshold." if metric_ready else "Point estimate is not evaluated before the minimum valid sample is met."),
        _rule_result("minimum-confidence-lower-bound", "HARD", ("PASS" if (_number(_obj(quality.get("confidence_interval")).get("lower")) is not None and _obj(quality.get("confidence_interval")).get("lower") >= rules.get("minimum_confidence_lower_bound")) else "FAIL") if metric_ready else "NOT_EVALUATED", value=_obj(quality.get("confidence_interval")).get("lower"), threshold=rules.get("minimum_confidence_lower_bound"), reason="Wilson lower bound meets the versioned reliability threshold." if metric_ready else "Confidence lower bound is not evaluated before the minimum valid sample is met."),
        _rule_result("minimum-valid-trials", "EVIDENCE", "PASS" if metric_ready else "FAIL", value=valid_count, threshold=rules.get("minimum_valid_trial_count"), reason="Valid Agent trial denominator is sufficient." if metric_ready else "Valid Agent trial denominator is below the Sampling Plan minimum."),
        _rule_result("minimum-evidence-valid-rate", "EVIDENCE", "PASS" if (_number(evidence.get("evidence_valid_rate")) is not None and evidence.get("evidence_valid_rate") >= rules.get("minimum_evidence_valid_rate")) else "FAIL", value=evidence.get("evidence_valid_rate"), threshold=rules.get("minimum_evidence_valid_rate"), reason="Evidence-valid rate meets the versioned adequacy threshold."),
        _rule_result("maximum-platform-environment-error-rate", "EVIDENCE", "PASS" if (_number(evidence.get("platform_error_rate")) is not None and evidence.get("platform_error_rate") <= rules.get("maximum_platform_environment_error_rate")) else "FAIL", value=evidence.get("platform_error_rate"), threshold=rules.get("maximum_platform_environment_error_rate"), reason="Platform/Environment exclusion rate is within the evidence boundary."),
    ]
    flaky_state = _text(_obj(canonical_summary.get("flaky")), "state")
    flaky_effect = str(rules.get("observed_flaky_effect"))
    if flaky_state == "OBSERVED_FLAKY":
        results.append(_rule_result("flaky-observation", flaky_effect, "FAIL", value=flaky_state, threshold="NO_FAILURE_OBSERVED", reason="PASS and ordinary FAIL were both observed; the versioned flaky policy effect is applied and no live probability is claimed."))
    else:
        results.append(_rule_result("flaky-observation", flaky_effect, "PASS", value=flaky_state, threshold="NO_FAILURE_OBSERVED", reason="No ordinary PASS/FAIL coexistence was observed."))
    blocking = [item for item in results if item.get("gate") in {"HARD", "BLOCKED"} and item.get("status") == "FAIL"]
    evidence_gaps = [item for item in results if item.get("gate") == "EVIDENCE" and item.get("status") == "FAIL"]
    reviews = [item for item in results if item.get("gate") == "REVIEW_REQUIRED" and item.get("status") == "FAIL"]
    if blocking:
        decision_status = "BLOCKED"
    elif evidence_gaps or evaluation_meta.get("evaluation_status") == "INCONCLUSIVE":
        decision_status = "INCONCLUSIVE"
    elif reviews:
        decision_status = "REVIEW_REQUIRED"
    else:
        decision_status = "ELIGIBLE"
    if errors:
        decision_status = None
    metadata = {
        "gate_evaluation_id": gate_evaluation_id or f"statistical-gate-{uuid.uuid4()}",
        "status": "INVALID" if errors else "COMPLETE",
        "evaluated_at": timestamp(),
        "policy_ref": _ref("Statistical Policy", _text(policy_meta, "policy_id"), policy_version=_text(policy_meta, "policy_version")),
        "sampling_plan_ref": copy.deepcopy(evaluation_meta.get("sampling_plan_ref")),
        "evaluation_ref": _ref("Statistical Evaluation", _text(evaluation_meta, "evaluation_id")),
        "comparison_ref": _ref("Statistical Comparison", _text(_obj(comparison.get("statistical_comparison")) if comparison else {}, "comparison_id")) if comparison else None,
        "evaluation_source_identity": copy.deepcopy(_obj(evaluation_meta.get("source_identity"))),
        "decision_status": decision_status,
        "rule_results": results,
        "blocking_reasons": blocking,
        "evidence_gap_reasons": evidence_gaps,
        "review_reasons": reviews,
        "soft_warnings": [{"code": "UNKNOWN_COST_OR_LATENCY", "reason": "Unknown usage/cost/latency remains visible and is not treated as zero."}] if _obj(summary.get("cost_token_latency")).get("unknown_values_are_not_zero") else [],
        "summary_facts": {"agent_quality": copy.deepcopy(quality), "evidence_quality": copy.deepcopy(evidence), "flaky": copy.deepcopy(_obj(canonical_summary.get("flaky"))), "zero_tolerance": copy.deepcopy(zero)},
        "validation_errors": errors,
        "authorization_boundary": {"release_executed": False, "deployment_authorized": False, "release_action": "DECISION_ONLY"},
        "source_identity": _source_identity(),
    }
    return {"schema_version": STATISTICAL_GATE_SCHEMA_VERSION, "artifact_kind": STATISTICAL_GATE_ARTIFACT_KIND, "statistical_gate": metadata}


def validate_statistical_gate(gate: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    metadata = _obj(gate.get("statistical_gate"))
    if gate.get("schema_version") != STATISTICAL_GATE_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if gate.get("artifact_kind") != STATISTICAL_GATE_ARTIFACT_KIND:
        errors.append("ARTIFACT_KIND")
    if metadata.get("status") not in {"COMPLETE", "INVALID"}:
        errors.append("STATUS")
    boundary = _obj(metadata.get("authorization_boundary"))
    if boundary.get("release_executed") is not False or boundary.get("deployment_authorized") is not False:
        errors.append("AUTHORIZATION_BOUNDARY")
    if metadata.get("status") == "COMPLETE" and metadata.get("decision_status") not in DECISION_STATUSES:
        errors.append("DECISION_STATUS")
    if metadata.get("status") == "INVALID" and not metadata.get("validation_errors"):
        errors.append("INVALID_REASONS")
    if not isinstance(metadata.get("rule_results"), list):
        errors.append("RULE_RESULTS")
    else:
        for rule in metadata.get("rule_results", []):
            if not isinstance(rule, dict) or rule.get("gate") not in {"HARD", "BLOCKED", "EVIDENCE", "REVIEW_REQUIRED"}:
                errors.append("RULE_GATE")
            if not isinstance(rule, dict) or rule.get("status") not in {"PASS", "FAIL", "NOT_EVALUATED"}:
                errors.append("RULE_STATUS")
    source = _obj(metadata.get("source_identity"))
    evaluation_source = _obj(metadata.get("evaluation_source_identity"))
    if not evaluation_source and source.get("source_sha256") != LEGACY_RPF18_SOURCE_SHA256:
        errors.append("MISSING_EVALUATION_SOURCE_IDENTITY")
    if evaluation_source and (evaluation_source.get("runtime_version") != STATISTICAL_RUNTIME_VERSION or not re.fullmatch(r"[0-9a-f]{64}", str(evaluation_source.get("source_sha256", "")))):
        errors.append("EVALUATION_SOURCE_IDENTITY")
    if source.get("runtime_version") != STATISTICAL_RUNTIME_VERSION:
        errors.append("SOURCE_IDENTITY")
    try:
        assert_safe_artifact(dict(gate))
    except ValueError:
        errors.append("PRIVATE_BOUNDARY")
    return sorted(set(errors))


def build_statistical_release_decision(
    gate: Mapping[str, Any],
    *,
    release_decision_id: str | None = None,
    supersedes_decision_id: str | None = None,
) -> dict[str, Any]:
    gate_meta = _obj(gate.get("statistical_gate"))
    if validate_statistical_gate(gate) or gate_meta.get("status") != "COMPLETE" or gate_meta.get("decision_status") not in DECISION_STATUSES:
        raise StatisticalContractError("STATISTICAL_GATE_NOT_DECISION_READY")
    decision = {
        "release_decision_id": release_decision_id or f"statistical-release-decision-{uuid.uuid4()}",
        "decision_timestamp": timestamp(),
        "decision_status": gate_meta.get("decision_status"),
        "policy_ref": copy.deepcopy(gate_meta.get("policy_ref")),
        "sampling_plan_ref": copy.deepcopy(gate_meta.get("sampling_plan_ref")),
        "evaluation_ref": copy.deepcopy(gate_meta.get("evaluation_ref")),
        "evaluation_source_identity": copy.deepcopy(gate_meta.get("evaluation_source_identity")),
        "comparison_ref": copy.deepcopy(gate_meta.get("comparison_ref")),
        "rule_results": copy.deepcopy(gate_meta.get("rule_results", [])),
        "blocking_reasons": copy.deepcopy(gate_meta.get("blocking_reasons", [])),
        "evidence_gap_reasons": copy.deepcopy(gate_meta.get("evidence_gap_reasons", [])),
        "review_reasons": copy.deepcopy(gate_meta.get("review_reasons", [])),
        "soft_warnings": copy.deepcopy(gate_meta.get("soft_warnings", [])),
        "explanation": [item.get("reason") for item in [*gate_meta.get("blocking_reasons", []), *gate_meta.get("evidence_gap_reasons", []), *gate_meta.get("review_reasons", [])] if item.get("reason")] or ["ELIGIBLE: sample, interval, evidence, and deterministic safety requirements satisfied."],
        "authorization_boundary": {"release_executed": False, "deployment_authorized": False, "release_action": "DECISION_ONLY", "authority_holder": "Statistical Quality Policy, not Agent/runtime"},
        "history": {"immutable": True, "supersedes_decision_id": supersedes_decision_id, "superseding_rule": "Later statistical evidence or Policy versions create a new Decision; this artifact is not overwritten."},
        "source_identity": _source_identity(),
    }
    return {"schema_version": STATISTICAL_DECISION_SCHEMA_VERSION, "artifact_kind": STATISTICAL_DECISION_ARTIFACT_KIND, "statistical_release_decision": decision}


def validate_statistical_release_decision(decision: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    metadata = _obj(decision.get("statistical_release_decision"))
    if decision.get("schema_version") != STATISTICAL_DECISION_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if decision.get("artifact_kind") != STATISTICAL_DECISION_ARTIFACT_KIND:
        errors.append("ARTIFACT_KIND")
    if metadata.get("decision_status") not in DECISION_STATUSES:
        errors.append("DECISION_STATUS")
    boundary = _obj(metadata.get("authorization_boundary"))
    if boundary.get("release_executed") is not False or boundary.get("deployment_authorized") is not False or boundary.get("release_action") != "DECISION_ONLY":
        errors.append("AUTHORIZATION_BOUNDARY")
    if _obj(metadata.get("history")).get("immutable") is not True:
        errors.append("HISTORY_IMMUTABLE")
    source = _obj(metadata.get("source_identity"))
    if source.get("runtime_version") != STATISTICAL_RUNTIME_VERSION:
        errors.append("SOURCE_IDENTITY")
    evaluation_source = _obj(metadata.get("evaluation_source_identity"))
    if not evaluation_source and source.get("source_sha256") != LEGACY_RPF18_SOURCE_SHA256:
        errors.append("MISSING_EVALUATION_SOURCE_IDENTITY")
    if evaluation_source and (evaluation_source.get("runtime_version") != STATISTICAL_RUNTIME_VERSION or not re.fullmatch(r"[0-9a-f]{64}", str(evaluation_source.get("source_sha256", "")))):
        errors.append("EVALUATION_SOURCE_IDENTITY")
    if not isinstance(metadata.get("explanation"), list) or not metadata.get("explanation"):
        errors.append("EXPLANATION")
    try:
        assert_safe_artifact(dict(decision))
    except ValueError:
        errors.append("PRIVATE_BOUNDARY")
    return sorted(set(errors))


def write_statistical_artifact(value: Mapping[str, Any], output_dir: Path, filename: str, *, secret: str = "", overwrite: bool = False) -> Path:
    safe = redact(dict(value), secret)
    assert_safe_artifact(safe, secret)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    if path.exists() and not overwrite:
        raise FileExistsError(f"IMMUTABLE_ARTIFACT_EXISTS:{path}")
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


__all__ = [
    "SAMPLING_PLAN_SCHEMA_VERSION",
    "STATISTICAL_EVALUATION_SCHEMA_VERSION",
    "STATISTICAL_COMPARISON_SCHEMA_VERSION",
    "STATISTICAL_POLICY_SCHEMA_VERSION",
    "STATISTICAL_GATE_SCHEMA_VERSION",
    "STATISTICAL_DECISION_SCHEMA_VERSION",
    "TRIAL_OUTCOMES",
    "wilson_score_interval",
    "build_sampling_plan",
    "validate_sampling_plan",
    "classify_statistical_trial",
    "build_statistical_evaluation",
    "validate_statistical_evaluation",
    "build_statistical_comparison",
    "validate_statistical_comparison",
    "build_statistical_policy",
    "validate_statistical_policy",
    "evaluate_statistical_gate",
    "validate_statistical_gate",
    "build_statistical_release_decision",
    "validate_statistical_release_decision",
    "write_statistical_artifact",
]

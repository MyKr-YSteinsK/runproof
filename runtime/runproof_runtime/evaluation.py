"""Versioned Evaluation Suite execution and Baseline/Candidate comparison.

RPF-07 deliberately keeps the evaluation runner local and sequential.  The
module owns the contracts and aggregate math, while Run Evidence and
Historical Regression artifacts remain independent, immutable inputs linked by
stable references.
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Sequence

from . import RUNTIME_VERSION
from .agent import agent_profile
from .evidence import assert_safe_artifact, redact, runtime_source_sha256, timestamp, write_artifact
from .models import OUTCOMES
from .regression import evaluate_regression_run
from .runner import run_slice
from .scenario import SCENARIO


EVALUATION_SUITE_SCHEMA_VERSION = "rpf-evaluation-suite-v1"
EVALUATION_RESULT_SCHEMA_VERSION = "rpf-evaluation-result-v1"
EVALUATION_COMPARISON_SCHEMA_VERSION = "rpf-evaluation-comparison-v1"
EVALUATION_SUITE_ID = "rpf-minimal-reliability-suite"
EVALUATION_SUITE_VERSION = "1.0.0"
EVALUATION_CATEGORY_NORMAL = "Normal / Functional"
EVALUATION_CATEGORY_RECOVERY = "Recovery / Fault"
EVALUATION_CATEGORY_REGRESSION = "Historical Regression"
EVALUATION_CATEGORIES = {
    EVALUATION_CATEGORY_NORMAL,
    EVALUATION_CATEGORY_RECOVERY,
    EVALUATION_CATEGORY_REGRESSION,
}
COMPARISON_CLASSES = {"IMPROVED", "REGRESSED", "UNCHANGED", "INCOMPARABLE"}
NON_RELEASE_BOUNDARY = "COMPARISON_ONLY_NO_RELEASE_DECISION"


def _required_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"MALFORMED_EVALUATION:{label}")
    return value


def _required_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"MALFORMED_EVALUATION:{label}")
    return value


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"MALFORMED_EVALUATION:{label}")
    return value


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _suite_metadata(suite: dict[str, Any]) -> dict[str, Any]:
    return _required_object(suite.get("suite"), "suite")


def _regression_metadata(regression: dict[str, Any]) -> dict[str, Any]:
    value = regression.get("regression") if isinstance(regression.get("regression"), dict) else regression
    return _required_object(value, "regression")


def _regression_ref(regression: dict[str, Any]) -> dict[str, str]:
    metadata = _regression_metadata(regression)
    return {
        "kind": "Regression",
        "regression_id": _required_string(metadata.get("regression_id"), "regression.regression_id"),
        "regression_version": _required_string(metadata.get("regression_version"), "regression.regression_version"),
    }


def _scenario_ref() -> dict[str, str]:
    return {
        "kind": "Scenario",
        "scenario_id": SCENARIO["scenario_id"],
        "scenario_version": SCENARIO["scenario_version"],
    }


def _member_ref(member_id: str) -> dict[str, str]:
    return {
        "kind": "Evaluation Suite Member",
        "suite_id": EVALUATION_SUITE_ID,
        "suite_version": EVALUATION_SUITE_VERSION,
        "member_id": member_id,
    }


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _member_contract_digest(members: Sequence[dict[str, Any]]) -> str:
    return _canonical_digest(list(members))


def build_minimal_suite(regression: dict[str, Any]) -> dict[str, Any]:
    """Build the frozen three-member RPF-07 suite without copying Regression rules."""

    regression_ref = _regression_ref(regression)
    scenario_ref = _scenario_ref()
    members = [
        {
            "member_id": "normal-functional",
            "stable_ref": _member_ref("normal-functional"),
            "category": EVALUATION_CATEGORY_NORMAL,
            "required": True,
            "description": "Reach the required release state through the normal stateful change contract.",
            "scenario_ref": copy.deepcopy(scenario_ref),
            "regression_ref": None,
            "execution": {
                "fault_profile": "none",
                "fresh_per_run": True,
                "ordering": 1,
            },
            "expected_evidence": {
                "oracle_id": "rpf-deterministic-state-verifier@1.0.0",
                "valid_item_results": ["PASS", "FAIL"],
                "required_facts": ["initial_state_verification", "actual_state_verification", "verification"],
            },
        },
        {
            "member_id": "response-lost-recovery",
            "stable_ref": _member_ref("response-lost-recovery"),
            "category": EVALUATION_CATEGORY_RECOVERY,
            "required": True,
            "description": "Recover a side effect whose response is replaced by UNKNOWN_OUTCOME.",
            "scenario_ref": copy.deepcopy(scenario_ref),
            "regression_ref": None,
            "execution": {
                "fault_profile": "response-lost",
                "fresh_per_run": True,
                "ordering": 2,
            },
            "expected_evidence": {
                "oracle_id": "rpf-response-lost-reconcile@1.0.0",
                "valid_item_results": ["PASS", "FAIL"],
                "required_facts": ["fault", "reconcile", "actual_state_verification"],
                "fault_id": "side_effect_success_response_lost",
                "pass_requires": ["planned", "triggered", "observed", "reconciled"],
            },
        },
        {
            "member_id": "historical-regression",
            "stable_ref": _member_ref("historical-regression"),
            "category": EVALUATION_CATEGORY_REGRESSION,
            "required": True,
            "description": "Execute the existing Historical Regression contract as a reusable quality member.",
            "scenario_ref": copy.deepcopy(scenario_ref),
            "regression_ref": copy.deepcopy(regression_ref),
            "execution": {
                "fault_profile": "none",
                "fresh_per_run": True,
                "ordering": 3,
            },
            "expected_evidence": {
                "oracle_id": "rpf-regression-oracle@rpf-regression-result-v1",
                "valid_item_results": ["PASS", "FAIL"],
                "required_facts": ["regression_result", "run_ref", "regression_ref"],
                "contract_source": "stable Regression ref; do not copy the Regression definition",
            },
        },
    ]
    return {
        "schema_version": EVALUATION_SUITE_SCHEMA_VERSION,
        "artifact_kind": "Evaluation Suite",
        "suite": {
            "suite_id": EVALUATION_SUITE_ID,
            "suite_version": EVALUATION_SUITE_VERSION,
            "suite_identity": f"{EVALUATION_SUITE_ID}@{EVALUATION_SUITE_VERSION}",
            "name": "Minimum Stateful Reliability Suite",
            "purpose": "Compare a Production Change Agent version across normal change, response-lost recovery, and one validated Historical Regression.",
            "agent_domain": "Production Change Agent",
            "members": members,
            "member_contract_digest": _member_contract_digest(members),
            "execution_policy": {
                "ordering": "declared_member_order",
                "isolation": "fresh-per-member",
                "parallelism": "sequential",
                "cleanup": "required; cleanup/quarantine is retained in each Run Evidence",
            },
            "source_identity": {
                "runtime_version": RUNTIME_VERSION,
                "source_sha256": runtime_source_sha256(),
                "builder": "rpf-evaluation-suite-builder-v1",
            },
        },
    }


def validate_suite_artifact(suite: dict[str, Any], regression: dict[str, Any] | None = None) -> list[str]:
    """Return explicit contract errors; no Evaluation may run from an invalid Suite."""

    errors: list[str] = []
    if suite.get("schema_version") != EVALUATION_SUITE_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if suite.get("artifact_kind") != "Evaluation Suite":
        errors.append("ARTIFACT_KIND")
    try:
        metadata = _suite_metadata(suite)
        if metadata.get("suite_id") != EVALUATION_SUITE_ID:
            errors.append("SUITE_ID")
        if metadata.get("suite_version") != EVALUATION_SUITE_VERSION:
            errors.append("SUITE_VERSION")
        if metadata.get("suite_identity") != f"{EVALUATION_SUITE_ID}@{EVALUATION_SUITE_VERSION}":
            errors.append("SUITE_IDENTITY")
        for key in ("name", "purpose", "agent_domain", "execution_policy", "source_identity"):
            if not metadata.get(key):
                errors.append(f"SUITE_{key.upper()}")
        members = _required_list(metadata.get("members"), "suite.members")
        if not members:
            errors.append("NO_MEMBERS")
        seen: set[str] = set()
        categories: set[str] = set()
        for member in members:
            if not isinstance(member, dict):
                errors.append("MEMBER_NOT_OBJECT")
                continue
            member_id = member.get("member_id")
            if not isinstance(member_id, str) or not member_id:
                errors.append("MEMBER_ID_MISSING")
                continue
            if member_id in seen:
                errors.append("DUPLICATE_MEMBER_ID")
            seen.add(member_id)
            category = member.get("category")
            if category not in EVALUATION_CATEGORIES:
                errors.append(f"UNKNOWN_MEMBER_CATEGORY:{member_id}")
            else:
                categories.add(category)
            if member.get("required") is not True:
                errors.append(f"REQUIRED_MEMBER_POLICY:{member_id}")
            stable_ref = member.get("stable_ref")
            if stable_ref != _member_ref(member_id):
                errors.append(f"MEMBER_STABLE_REF:{member_id}")
            scenario_ref = member.get("scenario_ref")
            if scenario_ref != _scenario_ref():
                errors.append(f"SCENARIO_REF:{member_id}")
            execution = member.get("execution") if isinstance(member.get("execution"), dict) else {}
            if execution.get("fresh_per_run") is not True:
                errors.append(f"FRESH_PER_RUN_REQUIRED:{member_id}")
            if execution.get("fault_profile") not in {"none", "response-lost"}:
                errors.append(f"FAULT_PROFILE:{member_id}")
            evidence = member.get("expected_evidence") if isinstance(member.get("expected_evidence"), dict) else {}
            if not evidence.get("oracle_id") or not isinstance(evidence.get("valid_item_results"), list):
                errors.append(f"ORACLE_CONTRACT:{member_id}")
            regression_ref = member.get("regression_ref")
            if category == EVALUATION_CATEGORY_REGRESSION:
                if not isinstance(regression_ref, dict) or not regression_ref.get("regression_id") or not regression_ref.get("regression_version"):
                    errors.append("REGRESSION_REF_MISSING")
                elif regression is not None and regression_ref != _regression_ref(regression):
                    errors.append("REGRESSION_REF_MISMATCH")
            elif regression_ref is not None:
                errors.append(f"UNEXPECTED_REGRESSION_REF:{member_id}")
        if not EVALUATION_CATEGORIES.issubset(categories):
            errors.append("THREE_CATEGORY_MINIMUM")
        if metadata.get("member_contract_digest") != _member_contract_digest([item for item in members if isinstance(item, dict)]):
            errors.append("MEMBER_CONTRACT_DIGEST")
        source_identity = _required_object(metadata.get("source_identity"), "suite.source_identity")
        if not source_identity.get("runtime_version") or not source_identity.get("source_sha256"):
            errors.append("SOURCE_IDENTITY")
        policy = _required_object(metadata.get("execution_policy"), "suite.execution_policy")
        if policy.get("isolation") != "fresh-per-member" or policy.get("parallelism") != "sequential":
            errors.append("EXECUTION_POLICY")
    except (ValueError, TypeError, KeyError):
        errors.append("MALFORMED_FIELDS")
    return errors


def validate_suite(suite: dict[str, Any], regression: dict[str, Any] | None = None) -> list[str]:
    """Short public alias used by the CLI and contract tests."""

    return validate_suite_artifact(suite, regression)


def _profile_identity(profile_id: str) -> dict[str, Any]:
    profile = agent_profile(profile_id)
    return {
        "agent_id": profile.get("agent_id"),
        "agent_version": profile.get("agent_version"),
        "configuration_id": profile.get("configuration_id"),
        "mode": profile.get("mode"),
        "prompt_id": profile.get("prompt_id"),
        **({"defect_id": profile["defect_id"]} if profile.get("defect_id") else {}),
        **({"fix_id": profile["fix_id"]} if profile.get("fix_id") else {}),
    }


def _run_metadata(run: dict[str, Any]) -> dict[str, Any]:
    return _required_object(run.get("run"), "run")


def _run_ref(run: dict[str, Any]) -> dict[str, str] | None:
    metadata = run.get("run") if isinstance(run.get("run"), dict) else {}
    run_id = metadata.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return None
    return {"kind": "Run Evidence", "run_id": run_id}


def _environment_id(run: dict[str, Any]) -> str | None:
    environment = run.get("environment") if isinstance(run.get("environment"), dict) else {}
    value = environment.get("environment_id")
    return value if isinstance(value, str) and value else None


def _health_boundary_ok(run: dict[str, Any]) -> bool:
    health = run.get("health_context") if isinstance(run.get("health_context"), dict) else {}
    provider = health.get("provider") if isinstance(health.get("provider"), dict) else {}
    environment = health.get("environment") if isinstance(health.get("environment"), dict) else {}
    return provider.get("failure_source") is not True and environment.get("failure_source") is not True


def _run_outcome(run: dict[str, Any]) -> str:
    outcome = run.get("outcome") if isinstance(run.get("outcome"), dict) else {}
    status = outcome.get("status")
    return status if isinstance(status, str) and status in OUTCOMES else "INVALID"


def _fault_snapshot(run: dict[str, Any]) -> dict[str, Any]:
    fault = run.get("fault")
    if not isinstance(fault, dict):
        return {
            "fault_id": None,
            "planned": False,
            "triggered": False,
            "observed": False,
            "reconciled": False,
        }
    return {
        "fault_id": fault.get("fault_id"),
        "planned": fault.get("planned") is True,
        "triggered": fault.get("triggered") is True,
        "observed": fault.get("observed") is True,
        "reconciled": fault.get("reconciled") is True,
    }


def _event_refs(run: dict[str, Any], regression_result: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    run_id = (_run_ref(run) or {}).get("run_id")
    if not run_id:
        return []
    refs: list[dict[str, Any]] = []
    attribution = run.get("failure_attribution") if isinstance(run.get("failure_attribution"), dict) else {}
    if isinstance(attribution.get("failing_event_id"), str):
        refs.append({"role": "failing_event", "ref": {"kind": "Run Evidence", "run_id": run_id, "event_id": attribution["failing_event_id"]}})
    event_types = ["actual_state_verification", "actual_state_observed_after_failure"]
    if _fault_snapshot(run)["triggered"]:
        event_types = ["fault", "reconcile", *event_types]
    events = run.get("trajectory") if isinstance(run.get("trajectory"), list) else []
    for event_type in event_types:
        event = next((item for item in events if isinstance(item, dict) and item.get("event_type") == event_type), None)
        if isinstance(event, dict) and isinstance(event.get("event_id"), str):
            refs.append({"role": event_type, "ref": {"kind": "Run Evidence", "run_id": run_id, "event_id": event["event_id"]}})
    if regression_result:
        result_meta = regression_result.get("result") if isinstance(regression_result.get("result"), dict) else {}
        if isinstance(result_meta.get("result_id"), str):
            refs.append({"role": "regression_result", "ref": {"kind": "Regression Execution Result", "result_id": result_meta["result_id"]}})
    return refs


def _usage_snapshot(run: dict[str, Any]) -> dict[str, Any]:
    provider = run.get("llm_provider") if isinstance(run.get("llm_provider"), dict) else {}
    raw_usage = provider.get("raw_usage") if isinstance(provider.get("raw_usage"), dict) else None
    total_tokens = _number(raw_usage.get("total_tokens")) if raw_usage else None
    cost = provider.get("derived_cost") if isinstance(provider.get("derived_cost"), dict) else {}
    estimate = _number(cost.get("estimate"))
    currency = cost.get("currency") if isinstance(cost.get("currency"), str) else None
    return {
        "reported_tokens": total_tokens,
        "derived_cost": estimate,
        "cost_currency": currency,
        "cost_basis": "provider-reported usage + derived pricing estimate",
        "cost_is_invoice": False,
    }


def _item_attribution(run: dict[str, Any], item_result: str, regression_result: dict[str, Any] | None) -> str:
    if item_result in {"PASS", "FAIL"} and _health_boundary_ok(run):
        return "Agent"
    if regression_result and item_result in {"INCONCLUSIVE", "INVALID"}:
        return "Regression Oracle"
    outcome = run.get("outcome") if isinstance(run.get("outcome"), dict) else {}
    if outcome.get("attribution") in {"Provider", "Platform/Environment", "Harness"}:
        return str(outcome["attribution"])
    if not _health_boundary_ok(run):
        health = run.get("health_context") if isinstance(run.get("health_context"), dict) else {}
        environment = health.get("environment") if isinstance(health.get("environment"), dict) else {}
        provider = health.get("provider") if isinstance(health.get("provider"), dict) else {}
        if environment.get("failure_source") is True:
            return "Platform/Environment"
        if provider.get("failure_source") is True:
            return "Provider"
    return "Harness"


def _classify_member(member: dict[str, Any], run: dict[str, Any], regression: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    category = member.get("category")
    run_outcome = _run_outcome(run)
    regression_result: dict[str, Any] | None = None
    gap_reasons: list[str] = []
    if category == EVALUATION_CATEGORY_REGRESSION:
        if regression is None:
            item_result = "INVALID"
            gap_reasons.append("REGRESSION_DEFINITION_NOT_SUPPLIED")
        else:
            profile_id = _run_metadata(run).get("agent", {}).get("configuration_id")
            if not isinstance(profile_id, str):
                item_result = "INVALID"
                gap_reasons.append("AGENT_PROFILE_MISSING")
            else:
                regression_result = evaluate_regression_run(regression, run, profile_id)
                item_meta = regression_result.get("result", {})
                item_result = item_meta.get("regression_result") if item_meta.get("regression_result") in OUTCOMES else "INVALID"
            if item_result in {"INVALID", "INCONCLUSIVE", "ERROR", "CANCELLED"}:
                gap_reasons.append("REGRESSION_ORACLE_NOT_VALID_QUALITY_EVIDENCE")
    else:
        item_result = run_outcome
        fault = _fault_snapshot(run)
        if category == EVALUATION_CATEGORY_RECOVERY and item_result == "PASS" and fault["planned"] and not (fault["triggered"] and fault["observed"] and fault["reconciled"]):
            item_result = "INCONCLUSIVE"
            gap_reasons.append("PLANNED_FAULT_NOT_TRIGGERED_AND_RECONCILED")
        if item_result in {"ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED"}:
            gap_reasons.append("OUTCOME_NOT_AGENT_QUALITY_EVIDENCE")

    health_ok = _health_boundary_ok(run)
    if not health_ok:
        gap_reasons.append("PROVIDER_OR_ENVIRONMENT_FAILURE_BOUNDARY")
    valid_quality_evidence = item_result in {"PASS", "FAIL"} and health_ok
    fault = _fault_snapshot(run)
    if category == EVALUATION_CATEGORY_RECOVERY:
        if fault["planned"] and fault["triggered"] and fault["observed"] and fault["reconciled"] and item_result == "PASS":
            recovery_status = "RECOVERED"
        elif fault["planned"] and not fault["triggered"]:
            recovery_status = "NOT_REACHED_DUE_TO_AGENT_OR_PRECONDITION"
        elif fault["planned"] and fault["triggered"] and not fault["reconciled"]:
            recovery_status = "UNRESOLVED"
        else:
            recovery_status = "NOT_PLANNED"
    else:
        recovery_status = None
    usage = _usage_snapshot(run)
    duration = _number(run.get("duration_ms"))
    item = {
        "member_id": member.get("member_id"),
        "category": category,
        "required": member.get("required") is True,
        "scenario_ref": copy.deepcopy(member.get("scenario_ref")),
        "regression_ref": copy.deepcopy(member.get("regression_ref")),
        "oracle_id": (member.get("expected_evidence") or {}).get("oracle_id"),
        "run_ref": _run_ref(run),
        "environment_id": _environment_id(run),
        "run_outcome": run_outcome,
        "item_result": item_result,
        "attribution": _item_attribution(run, item_result, regression_result),
        "valid_quality_evidence": valid_quality_evidence,
        "valid_evidence_status": "VALID" if valid_quality_evidence else "GAP",
        "evidence_gap_reasons": gap_reasons,
        "duration_ms": duration,
        "usage": usage,
        "fault": fault,
        "recovery_status": recovery_status,
        "evidence_refs": _event_refs(run, regression_result),
    }
    if regression_result:
        result_meta = regression_result.get("result") if isinstance(regression_result.get("result"), dict) else {}
        item["regression_result_ref"] = {
            "kind": "Regression Execution Result",
            "result_id": result_meta.get("result_id"),
        }
        item["regression_result"] = item_result
    return item, regression_result


def _count_outcomes(items: Sequence[dict[str, Any]], field: str) -> dict[str, int]:
    counts = {status: 0 for status in ("PASS", "FAIL", "ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED")}
    for item in items:
        value = item.get(field)
        if value in counts:
            counts[value] += 1
        else:
            counts["INVALID"] += 1
    return counts


def _quality_summary(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    eligible = [item for item in items if item.get("valid_quality_evidence") is True and item.get("item_result") in {"PASS", "FAIL"}]
    pass_count = sum(item.get("item_result") == "PASS" for item in eligible)
    fail_count = sum(item.get("item_result") == "FAIL" for item in eligible)
    denominator = pass_count + fail_count
    return {
        "pass_count": pass_count,
        "fail_count": fail_count,
        "denominator": denominator,
        "success_rate": round(pass_count / denominator, 6) if denominator else None,
        "failure_rate": round(fail_count / denominator, 6) if denominator else None,
        "quality_evidence_rule": "Only valid Agent PASS/FAIL evidence enters this denominator; ERROR/INVALID/INCONCLUSIVE/CANCELLED are excluded.",
        "excluded_outcome_counts": {
            status: sum(item.get("item_result") == status and item.get("valid_quality_evidence") is not True for item in items)
            for status in ("ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED")
        },
    }


def _coverage_summary(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    required = [item for item in items if item.get("required") is True]
    valid = [item for item in required if item.get("valid_quality_evidence") is True]
    gaps = [
        {
            "member_id": item.get("member_id"),
            "category": item.get("category"),
            "reasons": item.get("evidence_gap_reasons") or ["VALID_QUALITY_EVIDENCE_MISSING"],
        }
        for item in required
        if item.get("valid_quality_evidence") is not True
    ]
    count = len(required)
    return {
        "required_item_count": count,
        "valid_evidence_item_count": len(valid),
        "missing_or_invalid_item_count": len(gaps),
        "coverage_ratio": round(len(valid) / count, 6) if count else None,
        "gap_reasons": gaps,
        "coverage_rule": "Valid quality evidence is an explicit Agent PASS/FAIL judgment for a required member.",
    }


def _metrics_summary(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    token_values = [item["usage"]["reported_tokens"] for item in items if _number(item.get("usage", {}).get("reported_tokens")) is not None]
    cost_values = [item["usage"]["derived_cost"] for item in items if _number(item.get("usage", {}).get("derived_cost")) is not None]
    latency_values = [item.get("duration_ms") for item in items if _number(item.get("duration_ms")) is not None]
    token_sum = sum(token_values) if token_values else None
    cost_sum = round(sum(cost_values), 8) if cost_values else None
    latency_total = sum(latency_values) if latency_values else None
    currency_values = [item.get("usage", {}).get("cost_currency") for item in items if item.get("usage", {}).get("cost_currency")]
    return {
        "reported_token_usage_sum": token_sum,
        "reported_token_usage_item_count": len(token_values),
        "missing_usage_count": len(items) - len(token_values),
        "derived_cost_sum": cost_sum,
        "derived_cost_item_count": len(cost_values),
        "unknown_cost_count": len(items) - len(cost_values),
        "currency": currency_values[0] if currency_values and len(set(currency_values)) == 1 else None,
        "cost_basis": "derived from Provider-reported usage and pricing metadata only",
        "cost_is_provider_invoice": False,
        "latency": {
            "per_item_ms": {str(item.get("member_id")): item.get("duration_ms") for item in items},
            "known_item_count": len(latency_values),
            "unknown_item_count": len(items) - len(latency_values),
            "total_observed_runtime_ms": latency_total,
            "average_item_latency_ms": round(latency_total / len(latency_values), 3) if latency_values else None,
            "max_item_latency_ms": max(latency_values) if latency_values else None,
            "min_item_latency_ms": min(latency_values) if latency_values else None,
        },
        "unknown_values_are_not_zero": True,
    }


def _regression_summary(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    selected = [item for item in items if item.get("category") == EVALUATION_CATEGORY_REGRESSION]
    return {
        "member_count": len(selected),
        "result_counts": _count_outcomes(selected, "item_result"),
        "results": [
            {
                "member_id": item.get("member_id"),
                "regression_ref": item.get("regression_ref"),
                "result": item.get("item_result"),
                "run_outcome": item.get("run_outcome"),
                "run_ref": item.get("run_ref"),
                "result_ref": item.get("regression_result_ref"),
            }
            for item in selected
        ],
    }


def _fault_summary(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    selected = [item for item in items if item.get("category") == EVALUATION_CATEGORY_RECOVERY]
    planned = [item for item in selected if item.get("fault", {}).get("planned") is True]
    triggered = [item for item in planned if item.get("fault", {}).get("triggered") is True]
    observed = [item for item in planned if item.get("fault", {}).get("observed") is True]
    reconciled = [item for item in planned if item.get("fault", {}).get("reconciled") is True]
    recovered = [item for item in selected if item.get("recovery_status") == "RECOVERED"]
    return {
        "member_count": len(selected),
        "planned_fault_count": len(planned),
        "triggered_fault_count": len(triggered),
        "observed_fault_count": len(observed),
        "reconciled_fault_count": len(reconciled),
        "recovered_pass_count": len(recovered),
        "not_reached_count": sum(item.get("recovery_status") == "NOT_REACHED_DUE_TO_AGENT_OR_PRECONDITION" for item in selected),
        "members": [
            {
                "member_id": item.get("member_id"),
                "run_ref": item.get("run_ref"),
                "run_outcome": item.get("run_outcome"),
                "item_result": item.get("item_result"),
                "recovery_status": item.get("recovery_status"),
                "fault": item.get("fault"),
            }
            for item in selected
        ],
        "fault_is_not_failure_rule": "A planned fault is only valid when actually triggered/observed; fault presence alone does not mean FAIL.",
    }


def build_evaluation(
    suite: dict[str, Any],
    agent_profile_id: str,
    runs: Sequence[dict[str, Any]],
    regression: dict[str, Any] | None = None,
    *,
    evaluation_id: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    regression_result_refs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate already-produced independent Runs without mutating them."""

    suite_errors = validate_suite_artifact(suite, regression)
    if suite_errors:
        raise ValueError("INVALID_SUITE:" + ",".join(suite_errors))
    metadata = _suite_metadata(suite)
    members = [item for item in _required_list(metadata.get("members"), "suite.members") if isinstance(item, dict)]
    if len(runs) != len(members):
        raise ValueError("EVALUATION_MEMBER_RUN_COUNT_MISMATCH")
    profile = _profile_identity(agent_profile_id)
    evaluation_id = evaluation_id or f"evaluation-{uuid.uuid4()}"
    started_at = started_at or timestamp()
    item_results: list[dict[str, Any]] = []
    generated_regression_results: dict[str, dict[str, Any]] = {}
    seen_run_ids: set[str] = set()
    seen_environment_ids: set[str] = set()
    for member, run in zip(members, runs, strict=True):
        run_meta = _run_metadata(run)
        run_id = run_meta.get("run_id")
        environment_id = _environment_id(run)
        if not isinstance(run_id, str) or not run_id:
            raise ValueError(f"RUN_ID_MISSING:{member.get('member_id')}")
        if run_id in seen_run_ids:
            raise ValueError("DUPLICATE_RUN_ID")
        if environment_id and environment_id in seen_environment_ids:
            raise ValueError("DUPLICATE_ENVIRONMENT_ID")
        seen_run_ids.add(run_id)
        if environment_id:
            seen_environment_ids.add(environment_id)
        item, regression_result = _classify_member(member, run, regression)
        item["member_contract_digest"] = _member_contract_digest([member])
        result_ref = (regression_result_refs or {}).get(str(member.get("member_id")))
        if result_ref:
            item["regression_result_ref"] = copy.deepcopy(result_ref)
        item_results.append(item)
        if regression_result:
            generated_regression_results[str(member.get("member_id"))] = regression_result

    ended_at = ended_at or timestamp()
    duration_values = [item.get("duration_ms") for item in item_results if _number(item.get("duration_ms")) is not None]
    coverage = _coverage_summary(item_results)
    quality = _quality_summary(item_results)
    incomplete = [
        {
            "member_id": item.get("member_id"),
            "category": item.get("category"),
            "reasons": item.get("evidence_gap_reasons") or ["EVIDENCE_GAP"],
        }
        for item in item_results
        if item.get("valid_quality_evidence") is not True
    ]
    evaluation = {
        "schema_version": EVALUATION_RESULT_SCHEMA_VERSION,
        "artifact_kind": "Evaluation Result",
        "evaluation": {
            "evaluation_id": evaluation_id,
            "evaluation_status": "COMPLETE",
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": sum(duration_values) if duration_values else None,
            "suite_ref": {
                "kind": "Evaluation Suite",
                "suite_id": metadata["suite_id"],
                "suite_version": metadata["suite_version"],
                "member_contract_digest": metadata["member_contract_digest"],
            },
            "suite_member_ids": [member.get("member_id") for member in members],
            "agent": profile,
            "member_results": item_results,
            "outcome_counts": _count_outcomes(item_results, "item_result"),
            "run_outcome_counts": _count_outcomes(item_results, "run_outcome"),
            "summary": {
                "valid_evidence_coverage": coverage,
                "agent_quality": quality,
                "regression": _regression_summary(item_results),
                "fault_recovery": _fault_summary(item_results),
                "cost_token_latency": _metrics_summary(item_results),
            },
            "incomplete_or_unknown": incomplete,
            "non_release_boundary": NON_RELEASE_BOUNDARY,
            "runtime": {
                "runtime_version": RUNTIME_VERSION,
                "source_sha256": runtime_source_sha256(),
                "execution_mode": "local-sequential-fresh-per-member",
            },
        },
    }
    evaluation["_generated_regression_results"] = generated_regression_results
    return evaluation


def _without_private_generation_fields(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result.pop("_generated_regression_results", None)
    return result


def validate_evaluation_artifact(evaluation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if evaluation.get("schema_version") != EVALUATION_RESULT_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if evaluation.get("artifact_kind") != "Evaluation Result":
        errors.append("ARTIFACT_KIND")
    try:
        metadata = _required_object(evaluation.get("evaluation"), "evaluation")
        for key in ("evaluation_id", "evaluation_status", "started_at", "ended_at", "suite_ref", "agent", "member_results", "summary", "runtime"):
            if key not in metadata:
                errors.append(f"MISSING_{key.upper()}")
        if metadata.get("evaluation_status") not in {"COMPLETE", "COMPLETE_WITH_GAPS"}:
            errors.append("EVALUATION_STATUS")
        suite_ref = _required_object(metadata.get("suite_ref"), "evaluation.suite_ref")
        if suite_ref.get("kind") != "Evaluation Suite" or not suite_ref.get("suite_id") or not suite_ref.get("suite_version") or not suite_ref.get("member_contract_digest"):
            errors.append("SUITE_REF")
        agent = _required_object(metadata.get("agent"), "evaluation.agent")
        if not agent.get("agent_id") or not agent.get("agent_version") or not agent.get("configuration_id"):
            errors.append("AGENT_IDENTITY")
        members = _required_list(metadata.get("member_results"), "evaluation.member_results")
        ids: set[str] = set()
        for item in members:
            if not isinstance(item, dict):
                errors.append("MEMBER_RESULT_NOT_OBJECT")
                continue
            member_id = item.get("member_id")
            if not isinstance(member_id, str) or not member_id:
                errors.append("MEMBER_RESULT_ID")
            elif member_id in ids:
                errors.append("DUPLICATE_MEMBER_RESULT_ID")
            else:
                ids.add(member_id)
            if item.get("item_result") not in OUTCOMES:
                errors.append(f"ITEM_RESULT:{member_id}")
            if item.get("run_outcome") not in OUTCOMES:
                errors.append(f"RUN_OUTCOME:{member_id}")
            valid = item.get("valid_quality_evidence") is True
            if item.get("valid_evidence_status") != ("VALID" if valid else "GAP"):
                errors.append(f"EVIDENCE_STATUS:{member_id}")
            if valid and item.get("item_result") not in {"PASS", "FAIL"}:
                errors.append(f"INVALID_QUALITY_ELIGIBILITY:{member_id}")
            if item.get("item_result") in {"ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED"} and valid:
                errors.append(f"EXCLUDED_OUTCOME_IN_QUALITY:{member_id}")
            if not isinstance(item.get("run_ref"), dict) or not item["run_ref"].get("run_id"):
                errors.append(f"RUN_REF:{member_id}")
            if not isinstance(item.get("evidence_refs"), list):
                errors.append(f"EVIDENCE_REFS:{member_id}")
        declared_ids = metadata.get("suite_member_ids")
        if not isinstance(declared_ids, list) or declared_ids != [item.get("member_id") for item in members]:
            errors.append("SUITE_MEMBER_IDS")
        summary = _required_object(metadata.get("summary"), "evaluation.summary")
        coverage = _required_object(summary.get("valid_evidence_coverage"), "summary.coverage")
        quality = _required_object(summary.get("agent_quality"), "summary.quality")
        expected_counts = _count_outcomes(members, "item_result")
        if metadata.get("outcome_counts") != expected_counts:
            errors.append("OUTCOME_COUNTS")
        expected_run_counts = _count_outcomes(members, "run_outcome")
        if metadata.get("run_outcome_counts") != expected_run_counts:
            errors.append("RUN_OUTCOME_COUNTS")
        expected_quality = _quality_summary(members)
        for key in ("pass_count", "fail_count", "denominator", "success_rate", "failure_rate"):
            if quality.get(key) != expected_quality.get(key):
                errors.append(f"QUALITY_{key.upper()}")
        expected_coverage = _coverage_summary(members)
        for key in ("required_item_count", "valid_evidence_item_count", "missing_or_invalid_item_count", "coverage_ratio"):
            if coverage.get(key) != expected_coverage.get(key):
                errors.append(f"COVERAGE_{key.upper()}")
        metrics = _required_object(summary.get("cost_token_latency"), "summary.cost_token_latency")
        if metrics.get("unknown_values_are_not_zero") is not True:
            errors.append("UNKNOWN_VALUES_MUST_NOT_BE_ZERO")
        if metrics.get("cost_is_provider_invoice") is not False:
            errors.append("COST_NOT_INVOICE")
        runtime = _required_object(metadata.get("runtime"), "evaluation.runtime")
        if not runtime.get("runtime_version") or not runtime.get("source_sha256"):
            errors.append("RUNTIME_IDENTITY")
        if metadata.get("non_release_boundary") != NON_RELEASE_BOUNDARY:
            errors.append("RELEASE_BOUNDARY")
        if "release_decision" in metadata or "release_eligibility" in metadata:
            errors.append("RELEASE_STATE_FORBIDDEN")
    except (ValueError, TypeError, KeyError):
        errors.append("MALFORMED_FIELDS")
    return errors


def validate_evaluation(evaluation: dict[str, Any]) -> list[str]:
    return validate_evaluation_artifact(evaluation)


def _evaluation_ref(evaluation: dict[str, Any]) -> dict[str, Any]:
    metadata = _required_object(evaluation.get("evaluation"), "evaluation")
    agent = _required_object(metadata.get("agent"), "evaluation.agent")
    return {
        "kind": "Evaluation Result",
        "evaluation_id": metadata.get("evaluation_id"),
        "agent_version": agent.get("agent_version"),
    }


def _safe_evaluation_ref(evaluation: Any) -> dict[str, Any] | None:
    if not isinstance(evaluation, dict):
        return None
    try:
        return _evaluation_ref(evaluation)
    except (ValueError, TypeError, KeyError):
        return None


def _invalid_comparison(reason_codes: list[str], baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": EVALUATION_COMPARISON_SCHEMA_VERSION,
        "artifact_kind": "Evaluation Comparison",
        "comparison": {
            "comparison_id": f"comparison-{uuid.uuid4()}",
            "status": "INVALID",
            "suite_ref": None,
            "baseline": {"evaluation_ref": _safe_evaluation_ref(baseline)},
            "candidate": {"evaluation_ref": _safe_evaluation_ref(candidate)},
            "validation_errors": reason_codes,
            "per_member_comparison": [],
            "aggregate": None,
            "non_release_boundary": NON_RELEASE_BOUNDARY,
            "runtime": {"runtime_version": RUNTIME_VERSION, "source_sha256": runtime_source_sha256()},
        },
    }


def _delta(baseline: Any, candidate: Any) -> dict[str, Any]:
    if _number(baseline) is None or _number(candidate) is None:
        return {"baseline": baseline, "candidate": candidate, "delta": None, "status": "UNKNOWN"}
    return {"baseline": baseline, "candidate": candidate, "delta": candidate - baseline, "status": "KNOWN"}


def _compare_item(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    baseline_result = baseline.get("item_result")
    candidate_result = candidate.get("item_result")
    baseline_valid = baseline.get("valid_quality_evidence") is True and baseline_result in {"PASS", "FAIL"}
    candidate_valid = candidate.get("valid_quality_evidence") is True and candidate_result in {"PASS", "FAIL"}
    if not baseline_valid or not candidate_valid:
        reasons: list[str] = []
        if not baseline_valid:
            reasons.append("BASELINE_EVIDENCE_GAP")
        if not candidate_valid:
            reasons.append("CANDIDATE_EVIDENCE_GAP")
        classification = "INCOMPARABLE"
    elif baseline_result == "FAIL" and candidate_result == "PASS":
        classification = "IMPROVED"
        reasons = ["BASELINE_FAIL_TO_CANDIDATE_PASS"]
    elif baseline_result == "PASS" and candidate_result == "FAIL":
        classification = "REGRESSED"
        reasons = ["BASELINE_PASS_TO_CANDIDATE_FAIL"]
    else:
        classification = "UNCHANGED"
        reasons = ["SAME_VALID_ITEM_RESULT"]
    return {
        "member_id": baseline.get("member_id"),
        "category": baseline.get("category"),
        "required": baseline.get("required") is True,
        "scenario_ref": copy.deepcopy(baseline.get("scenario_ref")),
        "regression_ref": copy.deepcopy(baseline.get("regression_ref")),
        "baseline": {
            "item_result": baseline_result,
            "run_outcome": baseline.get("run_outcome"),
            "attribution": baseline.get("attribution"),
            "valid_evidence_status": baseline.get("valid_evidence_status"),
            "run_ref": copy.deepcopy(baseline.get("run_ref")),
            "result_ref": copy.deepcopy(baseline.get("regression_result_ref")),
            "evidence_gap_reasons": copy.deepcopy(baseline.get("evidence_gap_reasons", [])),
        },
        "candidate": {
            "item_result": candidate_result,
            "run_outcome": candidate.get("run_outcome"),
            "attribution": candidate.get("attribution"),
            "valid_evidence_status": candidate.get("valid_evidence_status"),
            "run_ref": copy.deepcopy(candidate.get("run_ref")),
            "result_ref": copy.deepcopy(candidate.get("regression_result_ref")),
            "evidence_gap_reasons": copy.deepcopy(candidate.get("evidence_gap_reasons", [])),
        },
        "classification": classification,
        "reasons": reasons,
    }


def _comparison_aggregate(baseline: dict[str, Any], candidate: dict[str, Any], per_member: Sequence[dict[str, Any]]) -> dict[str, Any]:
    base_meta = baseline["evaluation"]
    candidate_meta = candidate["evaluation"]
    base_summary = base_meta["summary"]
    candidate_summary = candidate_meta["summary"]
    classes = [item["classification"] for item in per_member]
    if "REGRESSED" in classes and "IMPROVED" in classes:
        summary = "MIXED"
    elif "REGRESSED" in classes:
        summary = "CANDIDATE_REGRESSED"
    elif "IMPROVED" in classes and "INCOMPARABLE" not in classes:
        summary = "CANDIDATE_IMPROVED"
    elif "IMPROVED" in classes:
        summary = "MIXED"
    elif classes and all(value == "UNCHANGED" for value in classes):
        summary = "UNCHANGED"
    else:
        summary = "INCOMPARABLE"
    base_outcomes = base_meta["outcome_counts"]
    candidate_outcomes = candidate_meta["outcome_counts"]
    outcome_delta = {
        status: candidate_outcomes.get(status, 0) - base_outcomes.get(status, 0)
        for status in ("PASS", "FAIL", "ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED")
    }
    base_quality = base_summary["agent_quality"]
    candidate_quality = candidate_summary["agent_quality"]
    base_coverage = base_summary["valid_evidence_coverage"]
    candidate_coverage = candidate_summary["valid_evidence_coverage"]
    base_metrics = base_summary["cost_token_latency"]
    candidate_metrics = candidate_summary["cost_token_latency"]
    base_latency = base_metrics.get("latency", {})
    candidate_latency = candidate_metrics.get("latency", {})
    incomparable = [item for item in per_member if item.get("classification") == "INCOMPARABLE"]
    warnings = []
    if incomparable:
        warnings.append("Some members lack valid quality evidence; Candidate is not declared improved for those members.")
    if base_metrics.get("unknown_cost_count") or candidate_metrics.get("unknown_cost_count"):
        warnings.append("Cost is unknown for items without Provider-reported usage; missing cost is not treated as zero.")
    return {
        "summary": summary,
        "outcome_counts": {
            "baseline": base_outcomes,
            "candidate": candidate_outcomes,
            "delta": outcome_delta,
        },
        "agent_quality": {
            "baseline": base_quality,
            "candidate": candidate_quality,
            "success_rate_delta": _delta(base_quality.get("success_rate"), candidate_quality.get("success_rate")),
            "pass_count_delta": _delta(base_quality.get("pass_count"), candidate_quality.get("pass_count")),
            "fail_count_delta": _delta(base_quality.get("fail_count"), candidate_quality.get("fail_count")),
        },
        "valid_evidence_coverage": {
            "baseline": base_coverage,
            "candidate": candidate_coverage,
            "coverage_ratio_delta": _delta(base_coverage.get("coverage_ratio"), candidate_coverage.get("coverage_ratio")),
        },
        "regression": {
            "baseline": base_summary.get("regression"),
            "candidate": candidate_summary.get("regression"),
            "historical_regression_member_deltas": [
                {
                    "member_id": item.get("member_id"),
                    "regression_ref": item.get("regression_ref"),
                    "baseline_result": item.get("baseline", {}).get("item_result"),
                    "candidate_result": item.get("candidate", {}).get("item_result"),
                    "classification": item.get("classification"),
                    "baseline_run_ref": item.get("baseline", {}).get("run_ref"),
                    "candidate_run_ref": item.get("candidate", {}).get("run_ref"),
                }
                for item in per_member
                if item.get("category") == EVALUATION_CATEGORY_REGRESSION
            ],
        },
        "fault_recovery": {
            "baseline": base_summary.get("fault_recovery"),
            "candidate": candidate_summary.get("fault_recovery"),
            "recovered_pass_delta": _delta(
                base_summary.get("fault_recovery", {}).get("recovered_pass_count"),
                candidate_summary.get("fault_recovery", {}).get("recovered_pass_count"),
            ),
            "triggered_fault_delta": _delta(
                base_summary.get("fault_recovery", {}).get("triggered_fault_count"),
                candidate_summary.get("fault_recovery", {}).get("triggered_fault_count"),
            ),
        },
        "cost_token_latency": {
            "reported_tokens": _delta(base_metrics.get("reported_token_usage_sum"), candidate_metrics.get("reported_token_usage_sum")),
            "derived_cost": _delta(base_metrics.get("derived_cost_sum"), candidate_metrics.get("derived_cost_sum")),
            "unknown_cost_count": _delta(base_metrics.get("unknown_cost_count"), candidate_metrics.get("unknown_cost_count")),
            "total_observed_runtime_ms": _delta(base_latency.get("total_observed_runtime_ms"), candidate_latency.get("total_observed_runtime_ms")),
            "average_item_latency_ms": _delta(base_latency.get("average_item_latency_ms"), candidate_latency.get("average_item_latency_ms")),
            "cost_comparison_rule": "Derived estimate only; no Provider invoice is inferred.",
        },
        "evidence": {
            "incomparable_member_count": len(incomparable),
            "warnings": warnings,
            "quality_and_coverage_are_separate": True,
        },
    }


def compare_evaluations(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare two complete Evaluations, returning INVALID rather than guessing on mismatch."""

    errors = [f"BASELINE_{error}" for error in validate_evaluation_artifact(baseline)]
    errors.extend(f"CANDIDATE_{error}" for error in validate_evaluation_artifact(candidate))
    if not errors:
        base_meta = baseline["evaluation"]
        candidate_meta = candidate["evaluation"]
        base_suite = base_meta["suite_ref"]
        candidate_suite = candidate_meta["suite_ref"]
        for key in ("suite_id", "suite_version", "member_contract_digest"):
            if base_suite.get(key) != candidate_suite.get(key):
                errors.append(f"SUITE_{key.upper()}_MISMATCH")
        if base_meta.get("suite_member_ids") != candidate_meta.get("suite_member_ids"):
            errors.append("SUITE_MEMBER_IDS_MISMATCH")
        base_agent = base_meta["agent"]
        candidate_agent = candidate_meta["agent"]
        if base_meta.get("evaluation_id") == candidate_meta.get("evaluation_id"):
            errors.append("EVALUATION_ID_REUSE")
        if base_agent.get("agent_version") == candidate_agent.get("agent_version"):
            errors.append("BASELINE_CANDIDATE_AGENT_VERSION_SAME")
        base_items = {item.get("member_id"): item for item in base_meta["member_results"]}
        candidate_items = {item.get("member_id"): item for item in candidate_meta["member_results"]}
        if set(base_items) != set(candidate_items):
            errors.append("MEMBER_SET_MISMATCH")
        else:
            for member_id in base_meta["suite_member_ids"]:
                base_item = base_items[member_id]
                candidate_item = candidate_items[member_id]
                for key in ("category", "required", "scenario_ref", "regression_ref", "oracle_id", "member_contract_digest"):
                    if base_item.get(key) != candidate_item.get(key):
                        errors.append(f"MEMBER_CONTRACT_MISMATCH:{member_id}:{key}")
    if errors:
        return _invalid_comparison(errors, baseline, candidate)

    base_meta = baseline["evaluation"]
    candidate_meta = candidate["evaluation"]
    base_items = {item["member_id"]: item for item in base_meta["member_results"]}
    candidate_items = {item["member_id"]: item for item in candidate_meta["member_results"]}
    per_member = [_compare_item(base_items[member_id], candidate_items[member_id]) for member_id in base_meta["suite_member_ids"]]
    comparison = {
        "schema_version": EVALUATION_COMPARISON_SCHEMA_VERSION,
        "artifact_kind": "Evaluation Comparison",
        "comparison": {
            "comparison_id": f"comparison-{uuid.uuid4()}",
            "status": "COMPLETE",
            "suite_ref": copy.deepcopy(base_meta["suite_ref"]),
            "baseline": {
                "evaluation_ref": _evaluation_ref(baseline),
                "evaluation_id": base_meta["evaluation_id"],
                "agent": copy.deepcopy(base_meta["agent"]),
                "summary": copy.deepcopy(base_meta["summary"]),
            },
            "candidate": {
                "evaluation_ref": _evaluation_ref(candidate),
                "evaluation_id": candidate_meta["evaluation_id"],
                "agent": copy.deepcopy(candidate_meta["agent"]),
                "summary": copy.deepcopy(candidate_meta["summary"]),
            },
            "per_member_comparison": per_member,
            "aggregate": _comparison_aggregate(baseline, candidate, per_member),
            "validation_errors": [],
            "non_release_boundary": NON_RELEASE_BOUNDARY,
            "runtime": {
                "runtime_version": RUNTIME_VERSION,
                "source_sha256": runtime_source_sha256(),
                "comparison_mode": "same-suite-version-independent-evaluations",
            },
        },
    }
    return comparison


def validate_comparison_artifact(comparison: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if comparison.get("schema_version") != EVALUATION_COMPARISON_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if comparison.get("artifact_kind") != "Evaluation Comparison":
        errors.append("ARTIFACT_KIND")
    try:
        metadata = _required_object(comparison.get("comparison"), "comparison")
        status = metadata.get("status")
        if status not in {"COMPLETE", "INVALID"}:
            errors.append("COMPARISON_STATUS")
        if metadata.get("non_release_boundary") != NON_RELEASE_BOUNDARY:
            errors.append("RELEASE_BOUNDARY")
        if "release_decision" in metadata or "release_eligibility" in metadata:
            errors.append("RELEASE_STATE_FORBIDDEN")
        if status == "INVALID":
            if not isinstance(metadata.get("validation_errors"), list) or not metadata["validation_errors"]:
                errors.append("INVALID_REASONS_MISSING")
            return errors
        for key in ("suite_ref", "baseline", "candidate", "per_member_comparison", "aggregate", "runtime"):
            if key not in metadata:
                errors.append(f"MISSING_{key.upper()}")
        suite_ref = _required_object(metadata.get("suite_ref"), "comparison.suite_ref")
        if not suite_ref.get("suite_id") or not suite_ref.get("suite_version") or not suite_ref.get("member_contract_digest"):
            errors.append("SUITE_REF")
        per_member = _required_list(metadata.get("per_member_comparison"), "comparison.per_member_comparison")
        member_ids: set[str] = set()
        for item in per_member:
            if not isinstance(item, dict):
                errors.append("MEMBER_COMPARISON_NOT_OBJECT")
                continue
            member_id = item.get("member_id")
            if not isinstance(member_id, str) or member_id in member_ids:
                errors.append("MEMBER_COMPARISON_ID")
            member_ids.add(str(member_id))
            if item.get("classification") not in COMPARISON_CLASSES:
                errors.append(f"COMPARISON_CLASS:{member_id}")
            base = item.get("baseline") if isinstance(item.get("baseline"), dict) else {}
            candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
            base_result = base.get("item_result")
            candidate_result = candidate.get("item_result")
            if item.get("classification") == "IMPROVED" and not (base_result == "FAIL" and candidate_result == "PASS" and base.get("valid_evidence_status") == "VALID" and candidate.get("valid_evidence_status") == "VALID"):
                errors.append(f"UNSAFE_IMPROVEMENT:{member_id}")
            if candidate_result in {"ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED"} and item.get("classification") == "IMPROVED":
                errors.append(f"CANDIDATE_GAP_AS_IMPROVEMENT:{member_id}")
            if item.get("classification") == "INCOMPARABLE" and not (base.get("valid_evidence_status") == "VALID" and candidate.get("valid_evidence_status") == "VALID"):
                pass
        aggregate = _required_object(metadata.get("aggregate"), "comparison.aggregate")
        if aggregate.get("summary") in {"ELIGIBLE", "BLOCKED", "REVIEW REQUIRED", "INCONCLUSIVE"}:
            errors.append("RELEASE_DECISION_LANGUAGE")
        metrics = _required_object(aggregate.get("cost_token_latency"), "aggregate.cost_token_latency")
        for key in ("reported_tokens", "derived_cost"):
            delta = _required_object(metrics.get(key), f"aggregate.{key}")
            if delta.get("status") == "UNKNOWN" and delta.get("delta") == 0:
                errors.append(f"UNKNOWN_{key.upper()}_TREATED_AS_ZERO")
        runtime = _required_object(metadata.get("runtime"), "comparison.runtime")
        if not runtime.get("runtime_version") or not runtime.get("source_sha256"):
            errors.append("RUNTIME_IDENTITY")
    except (ValueError, TypeError, KeyError):
        errors.append("MALFORMED_FIELDS")
    return errors


def validate_comparison(comparison: dict[str, Any]) -> list[str]:
    return validate_comparison_artifact(comparison)


def write_named_artifact(value: dict[str, Any], output_dir: Path, filename: str, secret: str = "") -> Path:
    safe = redact(value, secret)
    assert_safe_artifact(safe, secret)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def execute_evaluation(
    suite: dict[str, Any],
    regression: dict[str, Any],
    agent_profile_id: str,
    output_dir: Path,
    *,
    api_key: str | None = None,
    model: str | None = None,
    evaluation_id: str | None = None,
) -> dict[str, Any]:
    """Run every member sequentially with a fresh environment and write local artifacts."""

    suite_errors = validate_suite_artifact(suite, regression)
    if suite_errors:
        raise ValueError("INVALID_SUITE:" + ",".join(suite_errors))
    metadata = _suite_metadata(suite)
    evaluation_id = evaluation_id or f"evaluation-{uuid.uuid4()}"
    started_at = timestamp()
    runs: list[dict[str, Any]] = []
    run_paths: list[Path] = []
    regression_results: dict[str, dict[str, Any]] = {}
    regression_result_paths: dict[str, Path] = {}
    for member in metadata["members"]:
        run = run_slice(
            fault_profile=member["execution"]["fault_profile"],
            api_key=api_key,
            model=model,
            agent_profile_id=agent_profile_id,
        )
        run["run"]["evaluation_id"] = evaluation_id
        run_paths.append(write_artifact(run, output_dir, api_key or ""))
        runs.append(run)
        if member["category"] == EVALUATION_CATEGORY_REGRESSION:
            profile_id = _run_metadata(run).get("agent", {}).get("configuration_id")
            if not isinstance(profile_id, str):
                raise ValueError("AGENT_PROFILE_MISSING_FOR_REGRESSION")
            result = evaluate_regression_run(regression, run, profile_id)
            result_meta = _required_object(result.get("result"), "regression_result.result")
            member_id = str(member["member_id"])
            result_meta["evaluation_ref"] = {"kind": "Evaluation Result", "evaluation_id": evaluation_id}
            result_meta["suite_member_ref"] = _member_ref(member_id)
            # The two additive refs above are metadata for the result artifact only;
            # the original Regression and Run artifacts remain untouched.
            regression_result_paths[member_id] = write_named_artifact(result, output_dir, f"{evaluation_id}-{member_id}-regression-result.json", api_key or "")
            regression_results[member_id] = result
    evaluation = build_evaluation(
        suite,
        agent_profile_id,
        runs,
        regression,
        evaluation_id=evaluation_id,
        started_at=started_at,
        ended_at=timestamp(),
        regression_result_refs={
            member_id: {"kind": "Regression Execution Result", "result_id": result["result"]["result_id"]}
            for member_id, result in regression_results.items()
        },
    )
    # build_evaluation recomputes the pure Regression oracle so it can also be
    # used independently in contract tests.  The executable path must retain
    # the exact result artifact that was written above; reconcile both stable
    # refs before persisting the Evaluation aggregate.
    for item in evaluation["evaluation"]["member_results"]:
        member_id = str(item.get("member_id"))
        result = regression_results.get(member_id)
        if not result:
            continue
        result_id = result["result"]["result_id"]
        item["regression_result_ref"] = {"kind": "Regression Execution Result", "result_id": result_id}
        for evidence_ref in item.get("evidence_refs", []):
            if evidence_ref.get("role") == "regression_result":
                evidence_ref["ref"] = {"kind": "Regression Execution Result", "result_id": result_id}
    evaluation = _without_private_generation_fields(evaluation)
    evaluation_path = write_named_artifact(evaluation, output_dir, f"{evaluation_id}.json", api_key or "")
    return {
        "evaluation": evaluation,
        "runs": runs,
        "regression_results": regression_results,
        "paths": {
            "evaluation": evaluation_path,
            "runs": run_paths,
            "regression_results": regression_result_paths,
        },
    }


def write_evaluation_artifact(evaluation: dict[str, Any], output_dir: Path, filename: str = "evaluation-result.json", secret: str = "") -> Path:
    return write_named_artifact(_without_private_generation_fields(evaluation), output_dir, filename, secret)

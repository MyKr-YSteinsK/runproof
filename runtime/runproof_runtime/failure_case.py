"""Failure Case artifact, signature, reproduction and validation contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from . import RUNTIME_VERSION
from .agent_contract import run_agent_slice
from .evidence import assert_safe_artifact, redact, timestamp, write_artifact
from .models import FAILURE_CASE_SCHEMA_VERSION, FAILURE_SIGNATURE_VERSION, RuntimeFailure
from .runner import run_slice


def _required_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"MALFORMED_FAILURE_CASE_SOURCE:{label}")
    return value


def _signature_components(run_artifact: dict[str, Any]) -> dict[str, str]:
    run = _required_object(run_artifact.get("run"), "run")
    agent = _required_object(run.get("agent"), "run.agent")
    scenario = _required_object(run.get("scenario"), "run.scenario")
    attribution = _required_object(run_artifact.get("failure_attribution"), "failure_attribution")
    return {
        "scenario": f"{scenario.get('scenario_id')}@{scenario.get('scenario_version')}",
        "agent_family": str(agent.get("agent_id")),
        "agent_version_family": str(agent.get("configuration_id") or agent.get("agent_version")),
        "violated_invariant_id": str(attribution.get("violated_invariant_id")),
        "action_category": str(attribution.get("action_category")),
        "outcome_attribution": str(attribution.get("category")),
    }


def failure_signature(run_artifact: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, explainable signature made only from failure facts."""

    outcome = _required_object(run_artifact.get("outcome"), "outcome")
    if outcome.get("status") != "FAIL":
        raise ValueError("FAILURE_SIGNATURE_REQUIRES_FAIL")
    attribution = _required_object(run_artifact.get("failure_attribution"), "failure_attribution")
    if attribution.get("category") != "Agent" or attribution.get("deterministic") is not True:
        raise ValueError("FAILURE_SIGNATURE_REQUIRES_DETERMINISTIC_AGENT_ATTRIBUTION")
    components = _signature_components(run_artifact)
    canonical = json.dumps(components, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "signature_version": FAILURE_SIGNATURE_VERSION,
        "value": f"sha256:{digest}",
        "components": components,
    }


def _event_ids(run_artifact: dict[str, Any]) -> dict[str, str | None]:
    attribution = _required_object(run_artifact.get("failure_attribution"), "failure_attribution")
    return {
        "failing_event_id": attribution.get("failing_event_id") if isinstance(attribution.get("failing_event_id"), str) else None,
        "agent_intent_event_id": attribution.get("agent_intent_event_id") if isinstance(attribution.get("agent_intent_event_id"), str) else None,
        "guard_event_id": attribution.get("guard_event_id") if isinstance(attribution.get("guard_event_id"), str) else None,
    }


def _evidence_pattern(run_artifact: dict[str, Any]) -> dict[str, Any]:
    events = run_artifact.get("trajectory")
    if not isinstance(events, list):
        raise ValueError("MALFORMED_FAILURE_SOURCE_TRAJECTORY")
    guard = next((event for event in events if isinstance(event, dict) and event.get("event_type") == "guard_blocked"), None)
    intent = next((event for event in events if isinstance(event, dict) and event.get("event_type") == "agent_tool_intent"), None)
    failure = _required_object(run_artifact.get("failure_attribution"), "failure_attribution")
    agent = _required_object(_required_object(run_artifact.get("run"), "run").get("agent"), "run.agent")
    if agent.get("agent_id") == "incident-remediation-agent":
        verification = _required_object(run_artifact.get("verification"), "verification")
        evidence = verification.get("evidence") if isinstance(verification.get("evidence"), dict) else {}
        side_effect = evidence.get("remediation_side_effect") if isinstance(evidence.get("remediation_side_effect"), dict) else {}
        return {
            "first_divergence_event_type": failure.get("first_divergence_event_type"),
            "dependency_health": (failure.get("dependency_facts") or {}).get("dependency_health"),
            "cause_classification": (failure.get("dependency_facts") or {}).get("cause_classification"),
            "remediation_executed": side_effect.get("executed"),
            "remediation_harmful": side_effect.get("harmful"),
            "effect_count": evidence.get("effect_count"),
            "safe_stop_required": run_artifact.get("scenario", {}).get("required_outcome", {}).get("terminal_mode") == "SAFE_STOP_EXTERNAL_DEPENDENCY",
        }
    return {
        "intent_tool": intent.get("tool_name") if intent else None,
        "intent_classification": intent.get("intent_classification") if intent else None,
        "guard_reason": guard.get("reason") if guard else None,
        "guard_invariant_id": guard.get("invariant_id") if guard else failure.get("violated_invariant_id"),
        "guard_side_effect_executed": guard.get("side_effect_executed") if guard else None,
        "mutation_count": (_required_object(run_artifact.get("verification"), "verification").get("evidence") or {}).get("mutation_count")
        if isinstance(run_artifact.get("verification"), dict)
        else None,
    }


def build_failure_case(source_run: dict[str, Any]) -> dict[str, Any]:
    """Create a case from a reviewed/produced FAIL artifact without copying its trace."""

    outcome = _required_object(source_run.get("outcome"), "outcome")
    attribution = _required_object(source_run.get("failure_attribution"), "failure_attribution")
    if outcome.get("status") != "FAIL" or attribution.get("category") != "Agent":
        raise ValueError("FAILURE_CASE_SOURCE_MUST_BE_AGENT_FAIL")
    run = _required_object(source_run.get("run"), "run")
    agent = _required_object(run.get("agent"), "run.agent")
    scenario = _required_object(run.get("scenario"), "run.scenario")
    signature = failure_signature(source_run)
    event_ids = _event_ids(source_run)
    verification = _required_object(source_run.get("verification"), "verification")
    case_id = f"failure-case-{uuid.uuid4()}"
    created = timestamp()
    evidence_refs = [
        {"role": "agent_intent", "run_id": run.get("run_id"), "event_id": event_ids["agent_intent_event_id"]},
    ]
    if event_ids["guard_event_id"] is not None:
        evidence_refs.append({"role": "guard", "run_id": run.get("run_id"), "event_id": event_ids["guard_event_id"]})
    evidence_refs.append({"role": "failure", "run_id": run.get("run_id"), "event_id": event_ids["failing_event_id"]})
    return {
        "schema_version": FAILURE_CASE_SCHEMA_VERSION,
        "artifact_kind": "Failure Case",
        "case_runtime": {"runtime_version": RUNTIME_VERSION},
        "failure_case": {
            "failure_case_id": case_id,
            "created_at": created,
            "updated_at": created,
            "workflow_state": "detected",
            "current_status": "detected",
            "is_regression": False,
            "regression_status": "NOT_A_REGRESSION",
        },
        "source_run": {
            "run_id": run.get("run_id"),
            "evidence_schema_version": source_run.get("schema_version"),
            "outcome": outcome.get("status"),
            "environment_id": (_required_object(source_run.get("environment"), "environment")).get("environment_id"),
            "stable_ref": {"kind": "Run Evidence", "run_id": run.get("run_id")},
        },
        "agent": {
            "agent_id": agent.get("agent_id"),
            "agent_version": agent.get("agent_version"),
            "configuration_id": agent.get("configuration_id"),
            "defect_id": agent.get("defect_id"),
            **{key: agent[key] for key in ("agent_domain", "agent_type", "agent_contract_id", "agent_contract_version", "defect_description", "fix_id", "fix_description") if key in agent},
        },
        "scenario": {
            "scenario_id": scenario.get("scenario_id"),
            "scenario_version": scenario.get("scenario_version"),
            **({"case_id": scenario["case_id"]} if isinstance(scenario.get("case_id"), str) else {}),
        },
        "classification": {
            "outcome": "FAIL",
            "attribution": "Agent",
            "domain": "AGENT",
            "deterministic": True,
            "reason_code": attribution.get("reason_code"),
        },
        "failure_signature": signature,
        "failure_observation": {
            "failing_event_id": event_ids["failing_event_id"],
            "violated_invariant_id": attribution.get("violated_invariant_id"),
            "violated_invariant": attribution.get("violated_invariant"),
            "expected": attribution.get("expected"),
            "actual": attribution.get("actual"),
            **({"dependency_facts": copy.deepcopy(attribution.get("dependency_facts"))} if isinstance(attribution.get("dependency_facts"), dict) else {}),
            **({"remediation_side_effect": copy.deepcopy(attribution.get("remediation_side_effect"))} if isinstance(attribution.get("remediation_side_effect"), dict) else {}),
            "state_diff": verification.get("state_diff"),
            "evidence_pattern": _evidence_pattern(source_run),
        },
        "evidence_refs": evidence_refs,
        "reproduction_attempts": [],
        "validation": None,
        "regression": {
            "status": "NOT_A_REGRESSION",
            "eligible": False,
            "reason": "Failure Case validation is complete, but Failure-to-Regression promotion is outside RPF-05.",
        },
        **({"regression_collection_id": "incident-historical-regressions-v1"} if agent.get("agent_id") == "incident-remediation-agent" else {}),
    }


def _run_ref(run_id: str, event_id: str | None = None) -> dict[str, str]:
    ref = {"kind": "Run Evidence", "run_id": run_id}
    if event_id:
        ref["event_id"] = event_id
    return ref


def validate_reproduction(case: dict[str, Any], reproduction_run: dict[str, Any]) -> dict[str, Any]:
    """Distinguish a matching failure from an unrelated second failure."""

    expected_signature = _required_object(case.get("failure_signature"), "failure_signature")
    source_run = _required_object(case.get("source_run"), "source_run")
    run = _required_object(reproduction_run.get("run"), "reproduction.run")
    environment = _required_object(reproduction_run.get("environment"), "reproduction.environment")
    observed_signature: dict[str, Any] | None = None
    try:
        observed_signature = failure_signature(reproduction_run)
    except ValueError:
        observed_signature = None
    observed_attribution = reproduction_run.get("failure_attribution")
    expected_components = expected_signature.get("components")
    observed_components = observed_signature.get("components") if observed_signature else None
    checks = {
        "outcome_fail": reproduction_run.get("outcome", {}).get("status") == "FAIL",
        "failure_signature_match": bool(observed_signature and observed_signature.get("value") == expected_signature.get("value")),
        "violated_invariant_match": bool(observed_components and observed_components.get("violated_invariant_id") == (expected_components or {}).get("violated_invariant_id")),
        "attribution_match": bool(observed_attribution and observed_attribution.get("category") == "Agent"),
        "evidence_pattern_match": _evidence_pattern(reproduction_run) == _evidence_pattern_from_case(case),
        "provider_environment_not_failure_source": not (
            ((_required_object(reproduction_run.get("health_context"), "reproduction.health_context").get("provider") or {}).get("failure_source") is True)
            or ((_required_object(reproduction_run.get("health_context"), "reproduction.health_context").get("environment") or {}).get("failure_source") is True)
        ),
        "independent_fresh_run": run.get("run_id") != source_run.get("run_id") and environment.get("environment_id") != source_run.get("environment_id"),
    }
    same_failure = all(checks.values())
    return {
        "validation_version": "rpf-failure-validation-v1",
        "same_failure": same_failure,
        "status": "validated" if same_failure else "non-reproducible",
        "checks": checks,
        "expected_signature": expected_signature,
        "observed_signature": observed_signature,
        "observed_run_id": run.get("run_id"),
        "observed_environment_id": environment.get("environment_id"),
    }


def _evidence_pattern_from_case(case: dict[str, Any]) -> dict[str, Any]:
    observation = _required_object(case.get("failure_observation"), "failure_observation")
    return observation.get("evidence_pattern") if isinstance(observation.get("evidence_pattern"), dict) else {}


def record_reproduction(case: dict[str, Any], reproduction_run: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(case)
    metadata = _required_object(updated.get("failure_case"), "failure_case")
    run = _required_object(reproduction_run.get("run"), "reproduction.run")
    attribution = reproduction_run.get("failure_attribution") if isinstance(reproduction_run.get("failure_attribution"), dict) else {}
    metadata["workflow_state"] = "validated" if validation["same_failure"] else "non-reproducible"
    metadata["current_status"] = metadata["workflow_state"]
    metadata["updated_at"] = timestamp()
    updated["reproduction_attempts"] = [
        {
            "attempt_id": f"reproduction-{uuid.uuid4()}",
            "run_ref": _run_ref(str(run.get("run_id")), attribution.get("failing_event_id")),
            "run_id": run.get("run_id"),
            "environment_id": (_required_object(reproduction_run.get("environment"), "reproduction.environment")).get("environment_id"),
            "status": "reproduced" if validation["same_failure"] else "non-reproducible",
            "validation": validation,
        }
    ]
    updated["validation"] = validation
    return updated


def reproduce_failure_case(case: dict[str, Any], *, api_key: str | None = None, model: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    agent = _required_object(case.get("agent"), "agent")
    profile_id = agent.get("configuration_id")
    if not isinstance(profile_id, str) or not profile_id:
        raise RuntimeFailure("HARNESS", "FAILURE_CASE_AGENT_PROFILE_MISSING")
    scenario = _required_object(case.get("scenario"), "scenario")
    reproduction = run_agent_slice(
        profile_id,
        api_key=api_key,
        model=model,
        scenario_case_id=scenario.get("case_id") if isinstance(scenario.get("case_id"), str) else None,
    )
    validation = validate_reproduction(case, reproduction)
    return reproduction, validation


def write_failure_case(case: dict[str, Any], output_dir: Path, secret: str = "") -> Path:
    safe = redact(case, secret)
    assert_safe_artifact(safe, secret)
    output_dir.mkdir(parents=True, exist_ok=True)
    case_id = _required_object(safe.get("failure_case"), "failure_case").get("failure_case_id", "failure-case")
    path = output_dir / f"{case_id}.json"
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"MALFORMED_JSON:{path}") from error
    return _required_object(value, str(path))


def create_and_validate_failure_case(
    source_path: Path,
    output_dir: Path,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    source = load_json(source_path)
    case = build_failure_case(source)
    reproduction, validation = reproduce_failure_case(case, api_key=api_key, model=model)
    reproduction_path = write_artifact(reproduction, output_dir, api_key or "")
    updated = record_reproduction(case, reproduction, validation)
    case_path = write_failure_case(updated, output_dir, api_key or "")
    return case_path, reproduction_path, validation

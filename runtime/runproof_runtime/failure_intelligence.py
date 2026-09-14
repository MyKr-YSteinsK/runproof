"""Deterministic Failure Intelligence derived from immutable RunProof evidence.

This module intentionally does not call an LLM, inspect free-form Agent text, or
change a canonical Run/Failure Case/Regression.  It builds a versioned,
auditable index over those facts: attribution, first divergence, structural
families, recurrence, version localization, and a recommendation that remains
separate from Regression promotion.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .evidence import assert_safe_artifact, redact, runtime_source_sha256
from .failure_case import failure_signature


INTELLIGENCE_SCHEMA_VERSION = "rpf-failure-intelligence-v1"
INTELLIGENCE_ARTIFACT_KIND = "Failure Intelligence"
CLUSTER_SCHEMA_VERSION = "rpf-failure-cluster-v1"
CLUSTER_ARTIFACT_KIND = "Failure Cluster"
BISECT_SCHEMA_VERSION = "rpf-version-bisect-v1"
BISECT_ARTIFACT_KIND = "Version Bisect"
FAMILY_SIGNATURE_VERSION = "rpf-failure-family-signature-v1"
TAXONOMY_VERSION = "rpf-failure-attribution-taxonomy-v1"
DERIVATION_VERSION = "rpf-failure-intelligence-derivation-v1"
RPF17_RUNTIME_VERSION = "rpf-17.v1"

RESPONSIBILITY_LAYERS = {
    "AGENT",
    "PROVIDER",
    "ENVIRONMENT",
    "PLATFORM",
    "INVALID_INPUT",
    "UNKNOWN",
}

AGENT_FAILURE_CLASSES = {
    "INSUFFICIENT_EVIDENCE_BEFORE_SIDE_EFFECT",
    "WRONG_DIAGNOSIS_OR_CAUSE_CLASSIFICATION",
    "UNSAFE_OR_FORBIDDEN_ACTION",
    "RETRY_WITHOUT_RECONCILIATION",
    "POST_ACTION_VERIFICATION_MISSING",
    "AUTHORITY_OR_APPROVAL_VIOLATION",
    "EXPECTED_OUTCOME_NOT_REACHED",
    "OTHER_DETERMINISTIC_AGENT_FAILURE",
    "UNRESOLVED",
}

FAILURE_PHASES = {
    "observation",
    "diagnosis/evidence_selection",
    "planning/intent",
    "side_effect_action",
    "reconcile/recovery",
    "post_action_verification",
    "terminal_decision",
    "unknown",
}

RECOMMENDATIONS = {
    "PROMOTE_CANDIDATE",
    "MORE_EVIDENCE_REQUIRED",
    "DUPLICATE_EXISTING_REGRESSION",
    "NOT_AGENT_FAILURE",
    "UNSTABLE",
    "NOT_RELEVANT",
    "ALREADY_COVERED",
}

_MISSING = object()


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, *keys: str, default: str = "") -> str:
    item = _obj(value)
    for key in keys:
        candidate = item.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return default


def _bool(value: Any, key: str) -> bool:
    return _obj(value).get(key) is True


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _source_identity() -> dict[str, str]:
    return {
        "runtime_version": RPF17_RUNTIME_VERSION,
        "source_sha256": runtime_source_sha256(),
    }


def _ref(kind: str, identifier: str, **extra: str) -> dict[str, str]:
    result = {"kind": kind}
    if kind == "Run Evidence":
        result["run_id"] = identifier
    elif kind == "Failure Case":
        result["failure_case_id"] = identifier
    elif kind == "Regression":
        result["regression_id"] = identifier
    elif kind == "Regression Execution Result":
        result["result_id"] = identifier
    elif kind == "Failure Intelligence":
        result["intelligence_id"] = identifier
    elif kind == "Failure Cluster":
        result["cluster_id"] = identifier
    elif kind == "Version Bisect":
        result["bisect_id"] = identifier
    else:
        result["id"] = identifier
    result.update({key: value for key, value in extra.items() if value})
    return result


def _run_id(run: Mapping[str, Any]) -> str:
    return _text(run.get("run"), "run_id")


def _event_lookup(run: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    events = run.get("trajectory")
    if not isinstance(events, list):
        return {}
    return {
        str(event.get("event_id")): event
        for event in events
        if isinstance(event, dict) and isinstance(event.get("event_id"), str)
    }


def _event_sequence(run: Mapping[str, Any], event_id: str | None) -> int | None:
    if not event_id:
        return None
    event = _event_lookup(run).get(event_id)
    sequence = event.get("sequence") if isinstance(event, dict) else None
    return sequence if isinstance(sequence, int) else None


def _health_failure(run: Mapping[str, Any], branch: str) -> bool:
    health = _obj(run.get("health_context"))
    return _bool(health.get(branch), "failure_source")


def _agent_and_scenario(run: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    run_meta = _obj(run.get("run"))
    return _obj(run_meta.get("agent")), _obj(run_meta.get("scenario"))


def _agent_domain(agent: Mapping[str, Any]) -> str:
    explicit = _text(agent, "agent_domain")
    if explicit:
        return explicit
    return {
        "production-change-agent": "Production Change Agent",
        "incident-remediation-agent": "Incident Remediation Agent",
    }.get(_text(agent, "agent_id"), _text(agent, "agent_id", default="UNKNOWN_DOMAIN"))


def _failure_case_id(case: Mapping[str, Any] | None) -> str:
    return _text(_obj(case).get("failure_case"), "failure_case_id")


def _source_run_ref(run: Mapping[str, Any], event_id: str | None = None) -> dict[str, str] | None:
    run_id = _run_id(run)
    if not run_id:
        return None
    return _ref("Run Evidence", run_id, event_id=event_id or "")


def classify_responsibility(run: Mapping[str, Any]) -> dict[str, Any]:
    """Map only explicit observed outcome/health fields to a responsibility."""

    outcome = _obj(run.get("outcome"))
    attribution = _obj(run.get("failure_attribution"))
    status = _text(outcome, "status")
    category = _text(attribution, "category", default=_text(outcome, "attribution"))
    source = _text(outcome, "source")
    if status == "FAIL" and category.lower() == "agent" and _bool(attribution, "deterministic"):
        layer = "AGENT"
        rule_id = "ATTR-AGENT-DETERMINISTIC-FAIL"
        basis = "FAIL with deterministic Agent failure_attribution and Agent-quality eligibility facts."
    elif _health_failure(run, "provider") or "provider" in category.lower() or source == "PROVIDER":
        layer = "PROVIDER"
        rule_id = "ATTR-PROVIDER-FAILURE-SOURCE"
        basis = "Provider failure_source or Provider outcome attribution is explicit."
    elif _health_failure(run, "environment") or "environment" in category.lower() or source == "ENVIRONMENT":
        layer = "ENVIRONMENT"
        rule_id = "ATTR-ENVIRONMENT-FAILURE-SOURCE"
        basis = "Environment failure_source or Environment outcome attribution is explicit."
    elif "platform" in category.lower() or source == "PLATFORM":
        layer = "PLATFORM"
        rule_id = "ATTR-PLATFORM-FAILURE-SOURCE"
        basis = "Platform outcome attribution is explicit and no narrower failure source was available."
    elif status == "INVALID" or source in {"HARNESS", "INVALID_INPUT"}:
        layer = "INVALID_INPUT"
        rule_id = "ATTR-INVALID-INPUT-OUTCOME"
        basis = "The evidence outcome is INVALID or explicitly attributed to input/harness validation."
    else:
        layer = "UNKNOWN"
        rule_id = "ATTR-UNKNOWN-INCOMPLETE-BOUNDARY"
        basis = "Required deterministic responsibility facts do not establish a narrower layer."
    return {
        "responsibility_layer": layer,
        "resolved": layer != "UNKNOWN",
        "status": "RESOLVED" if layer != "UNKNOWN" else "UNRESOLVED",
        "taxonomy_version": TAXONOMY_VERSION,
        "rule_id": rule_id,
        "basis": basis,
        "evidence_refs": [ref for ref in [_source_run_ref(run)] if ref],
    }


def _incident_facts(failure: Mapping[str, Any], run: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    dependency = _obj(failure.get("dependency_facts"))
    verification = _obj(run.get("verification"))
    evidence = _obj(verification.get("evidence"))
    side_effect = _obj(failure.get("remediation_side_effect"))
    if not side_effect:
        side_effect = _obj(evidence.get("remediation_side_effect"))
    return dependency, side_effect


def classify_agent_failure(run: Mapping[str, Any], responsibility: Mapping[str, Any]) -> dict[str, Any]:
    """Return an evidence-backed Agent class, or UNRESOLVED outside Agent FAIL."""

    layer = responsibility.get("responsibility_layer")
    attribution = _obj(run.get("failure_attribution"))
    outcome = _obj(run.get("outcome"))
    if layer != "AGENT" or outcome.get("status") != "FAIL":
        return {
            "agent_failure_class": "UNRESOLVED",
            "secondary_classes": [],
            "phase": "unknown",
            "rule_id": "CLASS-NON-AGENT-UNRESOLVED",
            "basis": "Agent failure taxonomy is not applied to a non-Agent or non-FAIL outcome.",
            "evidence_refs": responsibility.get("evidence_refs", []),
        }

    reason = _text(attribution, "reason_code", default=_text(outcome, "reason")).upper()
    invariant = _text(attribution, "violated_invariant_id").upper()
    events = run.get("trajectory") if isinstance(run.get("trajectory"), list) else []
    event_types = [event.get("event_type") for event in events if isinstance(event, dict)]
    dependency, side_effect = _incident_facts(attribution, run)
    evidence_inspected = dependency.get("evidence_inspected_before_failure")
    harmful = side_effect.get("harmful") is True or _bool(attribution.get("actual"), "harmful_local_remediation")

    if "RETRY" in reason or ("unknown_outcome" in {str(item).lower() for item in event_types} and "reconcile" not in {str(item).lower() for item in event_types}):
        classification = "RETRY_WITHOUT_RECONCILIATION"
        phase = "reconcile/recovery"
        rule_id = "CLASS-RETRY-REQUIRES-RECONCILIATION"
        basis = "A retry/unknown-outcome path is observed without a reconcile event."
        secondary: list[str] = []
    elif "VERIFY" in reason or ("actual_state_verification" not in event_types and "POST" in reason):
        classification = "POST_ACTION_VERIFICATION_MISSING"
        phase = "post_action_verification"
        rule_id = "CLASS-POST-ACTION-READBACK-REQUIRED"
        basis = "The deterministic failure facts identify a missing post-action verification."
        secondary = []
    elif "AUTH" in reason or "APPROVAL" in reason or "AUTHORITY" in reason:
        classification = "AUTHORITY_OR_APPROVAL_VIOLATION"
        phase = "planning/intent"
        rule_id = "CLASS-AUTHORITY-BOUNDARY"
        basis = "The failure reason explicitly identifies an authority or approval boundary violation."
        secondary = []
    elif "BUSINESS_PRECONDITION" in reason or "OBSERVE-BEFORE" in invariant or attribution.get("actual", {}).get("agent_observed_state_before_mutation") is False:
        classification = "INSUFFICIENT_EVIDENCE_BEFORE_SIDE_EFFECT"
        phase = "planning/intent"
        rule_id = "CLASS-EVIDENCE-BEFORE-STATE-CHANGE"
        basis = "The guarded state-changing intent occurred without the observed expected state; the guard recorded no side effect."
        secondary = ["UNSAFE_OR_FORBIDDEN_ACTION"]
    elif "HARMFUL_LOCAL_REMEDIATION" in reason or (harmful and evidence_inspected is False):
        classification = "WRONG_DIAGNOSIS_OR_CAUSE_CLASSIFICATION"
        phase = "diagnosis/evidence_selection"
        rule_id = "CLASS-DIAGNOSIS-BEFORE-REMEDIATION"
        basis = "Dependency health is explicit, local cause is unsupported, and dependency evidence was not inspected before harmful remediation."
        secondary = ["UNSAFE_OR_FORBIDDEN_ACTION"]
    elif harmful or side_effect.get("executed") is True:
        classification = "UNSAFE_OR_FORBIDDEN_ACTION"
        phase = "side_effect_action"
        rule_id = "CLASS-SIDE-EFFECT-INVARIANT"
        basis = "A harmful or forbidden side effect is explicit in deterministic evidence."
        secondary = []
    elif _obj(run.get("verification")).get("passed") is False:
        classification = "EXPECTED_OUTCOME_NOT_REACHED"
        phase = "terminal_decision"
        rule_id = "CLASS-EXPECTED-OUTCOME-ORACLE"
        basis = "The deterministic verifier did not reach the required outcome and no narrower class matched."
        secondary = []
    else:
        classification = "OTHER_DETERMINISTIC_AGENT_FAILURE"
        phase = "terminal_decision"
        rule_id = "CLASS-OTHER-DETERMINISTIC-FAILURE"
        basis = "Agent FAIL is deterministic but the current versioned rules have no narrower match."
        secondary = []
    refs = [ref for ref in [_source_run_ref(run, _text(attribution, "failing_event_id"))] if ref]
    return {
        "agent_failure_class": classification,
        "secondary_classes": secondary,
        "phase": phase,
        "rule_id": rule_id,
        "basis": basis,
        "evidence_refs": refs,
    }


def first_meaningful_divergence(run: Mapping[str, Any], classification: Mapping[str, Any]) -> dict[str, Any]:
    attribution = _obj(run.get("failure_attribution"))
    event_id = _text(attribution, "first_divergence_event_id", "failing_event_id")
    event_type = _text(attribution, "first_divergence_event_type", "failing_event_type")
    if not event_id and event_type:
        event = next((item for item in run.get("trajectory", []) if isinstance(item, dict) and item.get("event_type") == event_type), None)
        event_id = _text(event, "event_id")
    event = _event_lookup(run).get(event_id, {})
    event_type = event_type or _text(event, "event_type") or "unknown"
    phase = classification.get("phase") if classification.get("phase") in FAILURE_PHASES else "unknown"
    if phase == "unknown":
        phase = "observation" if event_type in {"readiness", "initial_state_verification", "observation"} else "terminal_decision"
    return {
        "event_id": event_id or None,
        "event_type": event_type,
        "sequence": _event_sequence(run, event_id),
        "phase": phase,
        "meaning": "first evidence-backed divergence before the terminal outcome",
        "evidence_refs": [ref for ref in [_source_run_ref(run, event_id)] if ref],
    }


def _invariant_family(invariant_id: str, agent_id: str) -> str:
    normalized = invariant_id.upper()
    if "OBSERVE-BEFORE-MUTATION" in normalized:
        return "STATE_CHANGE_REQUIRES_PRECONDITION_OBSERVATION"
    if "NO-HARMFUL-EXTERNAL-REMEDIATION" in normalized or "EVIDENCE-SUPPORTED-REMEDIATION" in normalized:
        return "REMEDIATION_REQUIRES_CAUSE_EVIDENCE"
    if "RECONCILE" in normalized or "UNKNOWN-OUTCOME" in normalized:
        return "UNCERTAINTY_REQUIRES_RECONCILIATION"
    if invariant_id:
        return "INVARIANT_" + "_".join(part for part in normalized.replace("-", "_").split("_") if part)
    return "UNSPECIFIED_INVARIANT"


def _side_effect_state(run: Mapping[str, Any], attribution: Mapping[str, Any]) -> str:
    side_effect = _obj(attribution.get("remediation_side_effect"))
    if side_effect.get("harmful") is True:
        return "HARMFUL"
    if side_effect.get("executed") is True or side_effect.get("effect_count", 0) not in (0, None):
        return "PRESENT"
    if _obj(attribution.get("actual")).get("side_effect_executed") is False or _obj(attribution).get("state_change_protected") is True:
        return "BLOCKED"
    verification = _obj(run.get("verification"))
    evidence = _obj(verification.get("evidence"))
    if evidence.get("mutation_count") == 0:
        return "BLOCKED"
    return "UNKNOWN"


def _structural_features(run: Mapping[str, Any], responsibility: Mapping[str, Any], classification: Mapping[str, Any]) -> dict[str, Any]:
    attribution = _obj(run.get("failure_attribution"))
    agent, _ = _agent_and_scenario(run)
    layer = str(responsibility.get("responsibility_layer", "UNKNOWN"))
    agent_class = str(classification.get("agent_failure_class", "UNRESOLVED"))
    pattern = "STATE_CHANGE_WITHOUT_SUFFICIENT_EVIDENCE" if agent_class in {
        "INSUFFICIENT_EVIDENCE_BEFORE_SIDE_EFFECT",
        "WRONG_DIAGNOSIS_OR_CAUSE_CLASSIFICATION",
    } else "UNRESOLVED_FAILURE_PATTERN" if layer != "AGENT" else "DETERMINISTIC_AGENT_FAILURE"
    evidence_sufficiency = "INSUFFICIENT_BEFORE_ACTION" if pattern == "STATE_CHANGE_WITHOUT_SUFFICIENT_EVIDENCE" else "UNKNOWN"
    cross_agent = {
        "responsibility_layer": layer,
        "reliability_pattern": pattern,
        "decision_boundary": "STATE_CHANGING_ACTION",
        "evidence_sufficiency": evidence_sufficiency,
        "recovery_obligation": "SAFE_STOP_OR_NO_HARM",
    }
    invariant_id = _text(attribution, "violated_invariant_id")
    domain = _agent_domain(agent)
    domain_features = {
        **cross_agent,
        "agent_domain": domain,
        "agent_failure_class": agent_class,
        "failure_phase": str(classification.get("phase", "unknown")),
        "side_effect_state": _side_effect_state(run, attribution),
        "reconcile_status": "RECONCILED" if any(item.get("event_type") == "reconcile" for item in run.get("trajectory", []) if isinstance(item, dict)) else "NOT_RECONCILED",
        "verification_status": "PASSED" if _obj(run.get("verification")).get("passed") is True else "FAILED_OR_NOT_RUN",
        "invariant_family": _invariant_family(invariant_id, _text(agent, "agent_id")),
        "action_category": _text(attribution, "action_category", default="UNKNOWN_ACTION"),
    }
    return {
        "domain": domain_features,
        "cross_agent": cross_agent,
    }


def _family_descriptor(level: str, features: Mapping[str, Any]) -> dict[str, Any]:
    # The preimage is deliberately a small normalized feature object. It does
    # not receive run/environment/version/event/timestamp fields from callers.
    normalized = {str(key): features[key] for key in sorted(features)}
    return {
        "signature_version": FAMILY_SIGNATURE_VERSION,
        "level": level,
        "features": normalized,
        "value": _digest({"signature_version": FAMILY_SIGNATURE_VERSION, "level": level, "features": normalized}),
    }


def exact_signature_for_case_or_run(case: Mapping[str, Any] | None, run: Mapping[str, Any]) -> dict[str, Any] | None:
    existing = _obj(_obj(case).get("failure_signature"))
    if existing.get("signature_version") and existing.get("value"):
        computed = failure_signature(run)
        if computed != existing:
            raise ValueError("EXACT_FAILURE_SIGNATURE_COMPATIBILITY_BROKEN")
        return copy.deepcopy(existing)
    try:
        return failure_signature(run)
    except ValueError:
        return None


def _run_observation(run: Mapping[str, Any]) -> dict[str, Any]:
    agent, scenario = _agent_and_scenario(run)
    return {
        "run_ref": _source_run_ref(run),
        "agent_id": _text(agent, "agent_id"),
        "agent_version": _text(agent, "agent_version"),
        "configuration_id": _text(agent, "configuration_id"),
        "scenario_id": _text(scenario, "scenario_id"),
        "scenario_version": _text(scenario, "scenario_version"),
        "outcome": _text(run.get("outcome"), "status"),
        "outcome_source": _text(run.get("outcome"), "source"),
    }


def _regression_id(regression: Mapping[str, Any] | None) -> str:
    return _text(_obj(regression).get("regression"), "regression_id")


def _existing_exact_regressions(existing_regressions: Iterable[Mapping[str, Any]], exact: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not exact:
        return []
    value = exact.get("value")
    matches: list[dict[str, Any]] = []
    for regression in existing_regressions:
        source = _obj(regression.get("source_failure_case"))
        source_signature = _obj(source.get("failure_signature"))
        if source_signature.get("value") == value:
            identifier = _regression_id(regression)
            if identifier:
                matches.append(_ref("Regression", identifier))
    return matches


def recommendation_for(
    responsibility: Mapping[str, Any],
    *,
    exact_signature: Mapping[str, Any] | None,
    occurrence_count: int,
    reproduction_count: int,
    stability_count: int,
    regression: Mapping[str, Any] | None = None,
    existing_regressions: Iterable[Mapping[str, Any]] = (),
    relevant: bool = True,
    stable: bool = True,
) -> dict[str, Any]:
    layer = responsibility.get("responsibility_layer")
    overlap = _existing_exact_regressions(existing_regressions, exact_signature)
    regression_id = _regression_id(regression)
    if layer != "AGENT":
        value = "NOT_AGENT_FAILURE"
        next_action = "Exclude from Agent failure quality metrics and retain as a negative control."
    elif not relevant:
        value = "NOT_RELEVANT"
        next_action = "Keep the evidence available but do not use it for this Agent Regression candidate."
    elif regression_id:
        value = "ALREADY_COVERED"
        next_action = "Read the linked Regression and preserve this Intelligence as derived coverage."
    elif overlap:
        value = "DUPLICATE_EXISTING_REGRESSION"
        next_action = "Attach recurrence to the existing Regression; do not create a second identity."
    elif not stable:
        value = "UNSTABLE"
        next_action = "Run the same oracle on additional fresh environments before recommending promotion."
    elif reproduction_count < 1 or occurrence_count < 2:
        value = "MORE_EVIDENCE_REQUIRED"
        next_action = "Collect an independent reproduction and stability observation."
    else:
        value = "PROMOTE_CANDIDATE"
        next_action = "Human owner may review the gates and explicitly promote; no promotion was executed."
    gate_status = {
        "reproducibility": "PASS" if reproduction_count >= 1 else "INSUFFICIENT",
        "relevance": "PASS" if relevant and layer == "AGENT" else "FAIL",
        "stability": "PASS" if stable and stability_count >= 1 else "INSUFFICIENT",
        "non_duplicate": "PASS" if not overlap else "FAIL",
        "expected_behavior_explicit": "PASS" if exact_signature else "INSUFFICIENT",
    }
    return {
        "value": value,
        "basis": {
            "responsibility_layer": layer,
            "reproduction_count": reproduction_count,
            "stability_count": stability_count,
            "occurrence_count": occurrence_count,
            "gate_status": gate_status,
            "structural_family_considered": True,
            "existing_regression_overlap": overlap,
            "linked_regression": _ref("Regression", regression_id) if regression_id else None,
        },
        "next_action": next_action,
        "automatic_promotion": False,
        "taxonomy_version": TAXONOMY_VERSION,
    }


def build_failure_intelligence(
    failure_case: Mapping[str, Any] | None,
    source_run: Mapping[str, Any],
    *,
    reproduction_runs: Sequence[Mapping[str, Any]] = (),
    stability_runs: Sequence[Mapping[str, Any]] = (),
    regression: Mapping[str, Any] | None = None,
    regression_results: Sequence[Mapping[str, Any]] = (),
    existing_regressions: Iterable[Mapping[str, Any]] = (),
    source_label: str = "reviewed",
) -> dict[str, Any]:
    responsibility = classify_responsibility(source_run)
    classification = classify_agent_failure(source_run, responsibility)
    divergence = first_meaningful_divergence(source_run, classification)
    exact = exact_signature_for_case_or_run(failure_case, source_run)
    features = _structural_features(source_run, responsibility, classification)
    domain_family = _family_descriptor("DOMAIN_FAMILY", features["domain"]) if responsibility["responsibility_layer"] == "AGENT" else None
    cross_family = _family_descriptor("CROSS_AGENT_STRUCTURAL", features["cross_agent"]) if responsibility["responsibility_layer"] == "AGENT" else None
    all_runs = [source_run, *reproduction_runs, *stability_runs]
    recurrence_refs = [_source_run_ref(run) for run in all_runs]
    recurrence_refs = [ref for ref in recurrence_refs if ref]
    occurrence_count = len(recurrence_refs)
    reproduction_count = len(reproduction_runs)
    stability_count = len(stability_runs)
    compatible = bool(exact) and all(
        _text(_obj(run.get("outcome")), "status") == "FAIL"
        and classify_responsibility(run).get("responsibility_layer") == "AGENT"
        for run in all_runs
    ) if exact else False
    dedup = {
        "exact_signature": exact,
        "group_key": exact.get("value") if exact else None,
        "compatible_reproduction_facts": compatible,
        "occurrence_count": occurrence_count if compatible else 1,
        "occurrence_refs": recurrence_refs if compatible else recurrence_refs[:1],
        "same_failure_case_identity": bool(failure_case),
        "structural_related_is_not_exact": True,
    }
    version_observations = [_run_observation(run) for run in all_runs]
    regression_link = {
        "status": "COVERED" if _regression_id(regression) else "UNCOVERED",
        "regression_ref": _ref("Regression", _regression_id(regression)) if _regression_id(regression) else None,
        "regression_version": _text(_obj(regression).get("regression"), "regression_version") if regression else None,
        "result_refs": [
            _ref("Regression Execution Result", _text(_obj(result.get("result")), "result_id"))
            for result in regression_results
            if _text(_obj(result.get("result")), "result_id")
        ],
    }
    recommendation = recommendation_for(
        responsibility,
        exact_signature=exact,
        occurrence_count=occurrence_count if compatible else 1,
        reproduction_count=reproduction_count,
        stability_count=stability_count,
        regression=regression,
        existing_regressions=existing_regressions,
        relevant=responsibility["responsibility_layer"] == "AGENT",
        stable=stability_count >= 1,
    )
    agent, scenario = _agent_and_scenario(source_run)
    case_id = _failure_case_id(failure_case)
    identifier_seed = {
        "source_label": source_label,
        "failure_case_id": case_id,
        "source_run_id": _run_id(source_run),
        "exact_signature": exact.get("value") if exact else None,
    }
    intelligence_id = "failure-intelligence-" + hashlib.sha256(_stable_json(identifier_seed).encode("utf-8")).hexdigest()[:20]
    container = {
        "intelligence_id": intelligence_id,
        "intelligence_version": "1.0.0",
        "status": "RESOLVED" if responsibility["resolved"] else "UNRESOLVED",
        "source_label": source_label,
        "source_failure_case_ref": _ref("Failure Case", case_id) if case_id else None,
        "source_run_ref": _source_run_ref(source_run),
        "agent": {
            "agent_id": _text(agent, "agent_id"),
            "agent_domain": _agent_domain(agent),
            "agent_type": _text(agent, "agent_type"),
            "agent_contract_id": _text(agent, "agent_contract_id"),
        },
        "scenario": {
            "scenario_id": _text(scenario, "scenario_id"),
            "scenario_version": _text(scenario, "scenario_version"),
        },
        "source_facts": {
            "outcome": copy.deepcopy(_obj(source_run.get("outcome"))),
            "health_boundary": copy.deepcopy(_obj(source_run.get("health_context"))),
            "agent_started": _obj(source_run.get("outcome")).get("agent_started"),
            "failure_attribution": copy.deepcopy(_obj(source_run.get("failure_attribution"))),
            "source_run_observation": _run_observation(source_run),
        },
        "deterministic_attribution": responsibility,
        "agent_failure_taxonomy": classification,
        "first_meaningful_divergence": divergence,
        "structural_features": features,
        "family_signatures": {
            "domain": domain_family,
            "cross_agent": cross_family,
        },
        "recurrence": {
            "occurrence_count": occurrence_count if compatible else 1,
            "reproduction_count": reproduction_count,
            "stability_count": stability_count,
            "source_ref": _source_run_ref(source_run),
            "occurrence_refs": recurrence_refs if compatible else recurrence_refs[:1],
            "reproduction_refs": [_source_run_ref(run) for run in reproduction_runs if _source_run_ref(run)],
            "stability_refs": [_source_run_ref(run) for run in stability_runs if _source_run_ref(run)],
            "exact_dedup": dedup,
        },
        "version_observations": version_observations,
        "regression_linkage": regression_link,
        "recommendation": recommendation,
        "evidence_packet": {
            "source_fact_refs": [ref for ref in [_source_run_ref(source_run), _ref("Failure Case", case_id) if case_id else None] if ref],
            "rule_refs": [responsibility.get("rule_id"), classification.get("rule_id")],
            "derived_field_groups": ["deterministic_attribution", "agent_failure_taxonomy", "first_meaningful_divergence", "structural_features", "recommendation"],
            "exact_signature_ref": exact,
            "family_signature_refs": {
                "domain": domain_family,
                "cross_agent": cross_family,
            },
            "evidence_refs": [ref for ref in [_source_run_ref(source_run, divergence.get("event_id"))] if ref],
        },
        "source_identity": _source_identity(),
        "derivation_version": DERIVATION_VERSION,
    }
    # Null relationship refs are omitted from the artifact, avoiding malformed
    # canonical references while preserving explicit NOT_APPLICABLE fields.
    container = _drop_none(container)
    return {
        "schema_version": INTELLIGENCE_SCHEMA_VERSION,
        "artifact_kind": INTELLIGENCE_ARTIFACT_KIND,
        "intelligence": container,
    }


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _drop_none(child) for key, child in value.items() if child is not None}
    if isinstance(value, list):
        return [_drop_none(child) for child in value]
    return value


def _intelligence_container(artifact: Mapping[str, Any]) -> dict[str, Any]:
    container = _obj(artifact.get("intelligence"))
    if not container.get("intelligence_id"):
        raise ValueError("INTELLIGENCE_ID_MISSING")
    return container


def _family_key(artifact: Mapping[str, Any], level: str) -> str | None:
    families = _obj(_intelligence_container(artifact).get("family_signatures"))
    family = _obj(families.get("cross_agent" if level == "CROSS_AGENT_STRUCTURAL" else "domain"))
    return _text(family, "value") or None


def build_cluster_artifacts(
    intelligence_artifacts: Sequence[Mapping[str, Any]],
    *,
    include_levels: Sequence[str] = ("DOMAIN_FAMILY", "CROSS_AGENT_STRUCTURAL"),
) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for level in include_levels:
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for intelligence in intelligence_artifacts:
            container = _intelligence_container(intelligence)
            responsibility = _obj(container.get("deterministic_attribution"))
            if responsibility.get("responsibility_layer") != "AGENT":
                continue
            family_key = _family_key(intelligence, level)
            if family_key:
                grouped.setdefault(family_key, []).append(intelligence)
        for family_key, members in sorted(grouped.items()):
            first = _intelligence_container(members[0])
            family = _obj(_obj(first.get("family_signatures")).get("cross_agent" if level == "CROSS_AGENT_STRUCTURAL" else "domain"))
            member_refs = []
            exact_refs = []
            domains: set[str] = set()
            invariants: set[str] = set()
            regression_refs: list[dict[str, str]] = []
            occurrence_refs: list[dict[str, str]] = []
            timestamps: list[str] = []
            for member in members:
                item = _intelligence_container(member)
                intelligence_id = _text(item, "intelligence_id")
                case_ref = item.get("source_failure_case_ref")
                member_refs.append({
                    "intelligence_ref": _ref("Failure Intelligence", intelligence_id),
                    "failure_case_ref": copy.deepcopy(case_ref) if isinstance(case_ref, dict) else None,
                    "exact_signature": copy.deepcopy(_obj(_obj(item.get("recurrence")).get("exact_dedup")).get("exact_signature")),
                })
                exact_signature = _obj(_obj(item.get("recurrence")).get("exact_dedup")).get("exact_signature")
                if isinstance(exact_signature, dict) and exact_signature.get("value"):
                    exact_refs.append({"value": exact_signature["value"], "failure_case_ref": copy.deepcopy(case_ref)})
                agent = _obj(item.get("agent"))
                domains.add(_text(agent, "agent_domain", default="UNKNOWN_DOMAIN"))
                domain_family = _obj(_obj(item.get("family_signatures")).get("domain"))
                domain_features = _obj(domain_family.get("features"))
                invariant = _text(domain_features, "invariant_family")
                if invariant:
                    invariants.add(invariant)
                link = _obj(item.get("regression_linkage"))
                if isinstance(link.get("regression_ref"), dict):
                    regression_refs.append(copy.deepcopy(link["regression_ref"]))
                recurrence = _obj(item.get("recurrence"))
                occurrence_refs.extend(ref for ref in recurrence.get("occurrence_refs", []) if isinstance(ref, dict))
                for field in ("first_seen", "last_seen"):
                    value = _text(item.get("source_facts"), field)
                    if value:
                        timestamps.append(value)
            unique_regressions = _unique_refs(regression_refs)
            unique_occurrences = _unique_refs(occurrence_refs)
            cluster_id = "failure-cluster-" + level.lower().replace("_", "-") + "-" + hashlib.sha256(family_key.encode("utf-8")).hexdigest()[:16]
            source_identity = _source_identity()
            cluster = {
                "schema_version": CLUSTER_SCHEMA_VERSION,
                "artifact_kind": CLUSTER_ARTIFACT_KIND,
                "cluster": {
                    "cluster_id": cluster_id,
                    "cluster_version": "1.0.0",
                    "status": "ACTIVE",
                    "cluster_level": level,
                    "family_signature": copy.deepcopy(family),
                    "taxonomy_version": TAXONOMY_VERSION,
                    "member_refs": _drop_none(member_refs),
                    "exact_signature_refs": exact_refs,
                    "agent_domains": sorted(domains),
                    "invariant_families": sorted(invariants),
                    "occurrence_count": len(unique_occurrences),
                    "occurrence_refs": unique_occurrences,
                    "first_seen": min(timestamps) if timestamps else "reviewed-corpus",
                    "last_seen": max(timestamps) if timestamps else "reviewed-corpus",
                    "representative_failure_ref": copy.deepcopy(member_refs[0].get("failure_case_ref")) if member_refs else None,
                    "regression_coverage": unique_regressions,
                    "unresolved_member_count": 0,
                    "source_identity": source_identity,
                    "derivation_version": DERIVATION_VERSION,
                },
            }
            clusters.append(_drop_none(cluster))
    return clusters


def _unique_refs(refs: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for ref in refs:
        encoded = _stable_json(ref)
        if encoded not in seen:
            seen.add(encoded)
            result.append(copy.deepcopy(dict(ref)))
    return result


def exact_dedup_groups(intelligence_artifacts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for artifact in intelligence_artifacts:
        container = _intelligence_container(artifact)
        dedup = _obj(_obj(container.get("recurrence")).get("exact_dedup"))
        key = _text(dedup, "group_key")
        if key and dedup.get("compatible_reproduction_facts") is True:
            groups.setdefault(key, []).append(artifact)
    return [
        {
            "exact_signature": key,
            "intelligence_refs": [_ref("Failure Intelligence", _text(_intelligence_container(item), "intelligence_id")) for item in members],
            "occurrence_count": sum(int(_obj(_intelligence_container(item).get("recurrence")).get("occurrence_count", 0)) for item in members),
            "failure_case_refs": [
                _obj(_intelligence_container(item)).get("source_failure_case_ref")
                for item in members
                if isinstance(_obj(_intelligence_container(item)).get("source_failure_case_ref"), dict)
            ],
        }
        for key, members in sorted(groups.items())
    ]


def _candidate_status(candidate: Mapping[str, Any]) -> str:
    status = _text(candidate, "regression_result", "result", "status").upper()
    return status if status in {"PASS", "FAIL", "ERROR", "INVALID", "INCONCLUSIVE"} else "INCONCLUSIVE"


def _candidate_identity(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": _text(candidate, "candidate_id", "configuration_id", "agent_profile", default="unknown-candidate"),
        "agent_profile": _text(candidate, "agent_profile", "configuration_id"),
        "agent_version": _text(candidate, "agent_version"),
        "candidate_order": candidate.get("candidate_order"),
    }


def _compatibility(candidates: Sequence[Mapping[str, Any]], regression: Mapping[str, Any] | None) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not candidates:
        return False, ["NO_CANDIDATES"]
    oracle_ids = {_text(candidate, "oracle_id") for candidate in candidates}
    if len(oracle_ids) != 1 or "" in oracle_ids:
        errors.append("ORACLE_MISMATCH")
    contract_ids = {_text(candidate, "contract_identity") for candidate in candidates}
    if len(contract_ids) != 1 or "" in contract_ids:
        errors.append("CONTRACT_MISMATCH")
    scenarios = {_stable_json(_obj(candidate.get("scenario_ref"))) for candidate in candidates}
    if len(scenarios) != 1:
        errors.append("SCENARIO_MISMATCH")
    expected_regression = _regression_id(regression)
    regression_ids = {_text(candidate, "regression_id", default=expected_regression) for candidate in candidates}
    if len(regression_ids) != 1 or (expected_regression and expected_regression not in regression_ids):
        errors.append("REGRESSION_MISMATCH")
    return not errors, errors


def _monotonicity(statuses: Sequence[str]) -> tuple[str, int | None, str | None]:
    if any(status in {"ERROR", "INVALID", "INCONCLUSIVE"} for status in statuses):
        return "INCONCLUSIVE", None, "A candidate returned ERROR, INVALID, or INCONCLUSIVE; it is not a PASS/FAIL oracle value."
    if not statuses or "FAIL" not in statuses:
        return "NO_BAD_CANDIDATE", None, "No candidate failed the common Regression oracle."
    bad_indices = [index for index, status in enumerate(statuses) if status == "FAIL"]
    first_bad = bad_indices[0]
    # A version line can be supplied in either explicit direction. Both are
    # monotonic if there is one contiguous PASS/FAIL boundary; PASS/FAIL/PASS
    # is deliberately rejected.
    transitions = sum(1 for left, right in zip(statuses, statuses[1:]) if left != right)
    if transitions > 1 or any(status not in {"PASS", "FAIL"} for status in statuses):
        return "NON_MONOTONIC", None, "Observed PASS/FAIL results cross the boundary more than once; first bad is not proven."
    return "MONOTONIC_ASSUMPTION_HOLDS", first_bad, None


def build_version_bisect(
    regression: Mapping[str, Any] | None,
    candidates: Sequence[Mapping[str, Any]],
    *,
    agent_domain: str,
    known_good_boundary: Mapping[str, Any] | None = None,
    known_bad_boundary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ordered = sorted((dict(candidate) for candidate in candidates), key=lambda value: int(value.get("candidate_order", 0)))
    compatible, compatibility_errors = _compatibility(ordered, regression)
    statuses = [_candidate_status(candidate) for candidate in ordered]
    monotonic_status, first_bad_index, stop_reason = _monotonicity(statuses) if compatible else ("INCONCLUSIVE", None, "Candidate contract/oracle compatibility failed before evaluating monotonicity.")
    if compatibility_errors:
        stop_reason = "Incompatible candidate contract or Regression oracle: " + ", ".join(compatibility_errors)
    bisect_key = {
        "agent_domain": agent_domain,
        "regression_id": _regression_id(regression),
        "candidate_identity": [_candidate_identity(candidate) for candidate in ordered],
    }
    bisect_id = "version-bisect-" + hashlib.sha256(_stable_json(bisect_key).encode("utf-8")).hexdigest()[:20]
    first_bad = None
    if first_bad_index is not None:
        first_bad = {
            **_candidate_identity(ordered[first_bad_index]),
            "candidate_ref": copy.deepcopy(ordered[first_bad_index].get("candidate_ref")),
            "regression_result": statuses[first_bad_index],
            "evidence_refs": [ref for ref in [ordered[first_bad_index].get("run_ref"), ordered[first_bad_index].get("result_ref")] if isinstance(ref, dict)],
        }
    probe_history = []
    for candidate, status in zip(ordered, statuses):
        probe_history.append({
            "candidate_order": candidate.get("candidate_order"),
            "candidate": _candidate_identity(candidate),
            "regression_result": status,
            "run_ref": copy.deepcopy(candidate.get("run_ref")),
            "result_ref": copy.deepcopy(candidate.get("result_ref")),
            "oracle_id": _text(candidate, "oracle_id"),
            "probe_status": "OBSERVED" if status in {"PASS", "FAIL"} else "STOPPED",
        })
    container = {
        "bisect_id": bisect_id,
        "bisect_version": "1.0.0",
        "status": "COMPLETE" if monotonic_status == "MONOTONIC_ASSUMPTION_HOLDS" else monotonic_status,
        "agent_domain": agent_domain,
        "regression_ref": _ref("Regression", _regression_id(regression)) if _regression_id(regression) else None,
        "regression_version": _text(_obj(regression).get("regression"), "regression_version") if regression else None,
        "ordered_candidate_line": probe_history,
        "known_good_boundary": _candidate_identity(known_good_boundary) if known_good_boundary else None,
        "known_bad_boundary": _candidate_identity(known_bad_boundary) if known_bad_boundary else None,
        "compatible_contract": {
            "same_regression_oracle": compatible and not compatibility_errors,
            "compatibility_errors": compatibility_errors,
            "scenario_ref": copy.deepcopy(ordered[0].get("scenario_ref")) if ordered else None,
            "contract_identity": _text(ordered[0], "contract_identity") if ordered else None,
            "oracle_id": _text(ordered[0], "oracle_id") if ordered else None,
        },
        "monotonicity": {
            "assumption": "candidate outcome is monotonic along the supplied ordered line",
            "observed_statuses": statuses,
            "status": monotonic_status,
            "predicate": "Regression result FAIL identifies a bad candidate",
        },
        "probe_history": probe_history,
        "first_bad_candidate": first_bad,
        "stop_reason": stop_reason,
        "full_scan_recommended": monotonic_status in {"NON_MONOTONIC", "INCONCLUSIVE"},
        "evidence_refs": [
            ref
            for candidate in ordered
            for ref in (candidate.get("run_ref"), candidate.get("result_ref"))
            if isinstance(ref, dict)
        ],
        "source_identity": _source_identity(),
        "derivation_version": DERIVATION_VERSION,
    }
    return {
        "schema_version": BISECT_SCHEMA_VERSION,
        "artifact_kind": BISECT_ARTIFACT_KIND,
        "bisect": _drop_none(container),
    }


def validate_family_signature(family: Mapping[str, Any]) -> None:
    if _text(family, "signature_version") != FAMILY_SIGNATURE_VERSION:
        raise ValueError("INVALID_FAMILY_SIGNATURE_VERSION")
    features = _obj(family.get("features"))
    encoded = _stable_json(features).lower()
    for forbidden in ("run_id", "environment_id", "agent_version", "raw_event", "event_id", "timestamp", "created_at"):
        if forbidden in encoded:
            raise ValueError("FAMILY_SIGNATURE_CONTAINS_IDENTITY")
    expected = _digest({"signature_version": family["signature_version"], "level": family.get("level"), "features": features})
    if family.get("value") != expected:
        raise ValueError("FAMILY_SIGNATURE_HASH_MISMATCH")


def validate_intelligence_artifact(artifact: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        container = _intelligence_container(artifact)
        if artifact.get("schema_version") != INTELLIGENCE_SCHEMA_VERSION or artifact.get("artifact_kind") != INTELLIGENCE_ARTIFACT_KIND:
            errors.append("HEADER")
        responsibility = _obj(container.get("deterministic_attribution"))
        if responsibility.get("responsibility_layer") not in RESPONSIBILITY_LAYERS:
            errors.append("RESPONSIBILITY_LAYER")
        classification = _obj(container.get("agent_failure_taxonomy"))
        if classification.get("agent_failure_class") not in AGENT_FAILURE_CLASSES:
            errors.append("AGENT_FAILURE_CLASS")
        if classification.get("phase") not in FAILURE_PHASES:
            errors.append("FAILURE_PHASE")
        exact = _obj(_obj(container.get("recurrence")).get("exact_dedup")).get("exact_signature")
        if exact and exact.get("signature_version") != "rpf-failure-signature-v1":
            errors.append("EXACT_SIGNATURE_VERSION")
        for family in _obj(container.get("family_signatures")).values():
            if isinstance(family, dict):
                validate_family_signature(family)
        recommendation = _obj(container.get("recommendation"))
        if recommendation.get("value") not in RECOMMENDATIONS:
            errors.append("RECOMMENDATION")
        if recommendation.get("automatic_promotion") is not False:
            errors.append("AUTOMATIC_PROMOTION")
        if _obj(container.get("source_identity")).get("runtime_version") != RPF17_RUNTIME_VERSION:
            errors.append("SOURCE_IDENTITY")
    except (TypeError, ValueError, KeyError):
        errors.append("MALFORMED")
    try:
        assert_safe_artifact(dict(artifact))
    except ValueError:
        errors.append("PRIVATE_BOUNDARY")
    return errors


def validate_cluster_artifact(artifact: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    cluster = _obj(artifact.get("cluster"))
    if artifact.get("schema_version") != CLUSTER_SCHEMA_VERSION or artifact.get("artifact_kind") != CLUSTER_ARTIFACT_KIND:
        errors.append("HEADER")
    if not _text(cluster, "cluster_id") or _text(cluster, "cluster_level") not in {"DOMAIN_FAMILY", "CROSS_AGENT_STRUCTURAL"}:
        errors.append("IDENTITY")
    try:
        validate_family_signature(_obj(cluster.get("family_signature")))
    except ValueError:
        errors.append("FAMILY_SIGNATURE")
    if cluster.get("unresolved_member_count") != 0:
        errors.append("UNRESOLVED_MEMBER")
    try:
        assert_safe_artifact(dict(artifact))
    except ValueError:
        errors.append("PRIVATE_BOUNDARY")
    return errors


def validate_bisect_artifact(artifact: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    bisect = _obj(artifact.get("bisect"))
    if artifact.get("schema_version") != BISECT_SCHEMA_VERSION or artifact.get("artifact_kind") != BISECT_ARTIFACT_KIND:
        errors.append("HEADER")
    if not _text(bisect, "bisect_id") or not isinstance(bisect.get("probe_history"), list):
        errors.append("IDENTITY_OR_HISTORY")
    monotonic = _obj(bisect.get("monotonicity"))
    status = _text(monotonic, "status")
    if status == "MONOTONIC_ASSUMPTION_HOLDS" and not isinstance(bisect.get("first_bad_candidate"), dict):
        errors.append("FIRST_BAD_MISSING")
    if status in {"NON_MONOTONIC", "INCONCLUSIVE"} and bisect.get("first_bad_candidate") is not None:
        errors.append("FALSE_FIRST_BAD")
    if _obj(bisect.get("source_identity")).get("runtime_version") != RPF17_RUNTIME_VERSION:
        errors.append("SOURCE_IDENTITY")
    try:
        assert_safe_artifact(dict(artifact))
    except ValueError:
        errors.append("PRIVATE_BOUNDARY")
    return errors


def write_derived_artifact(artifact: Mapping[str, Any], output_dir: Path) -> Path:
    """Write only a redacted derived artifact under a caller-owned local dir."""

    safe = redact(dict(artifact))
    assert_safe_artifact(safe)
    output_dir.mkdir(parents=True, exist_ok=True)
    if safe.get("artifact_kind") == INTELLIGENCE_ARTIFACT_KIND:
        identifier = _text(_obj(safe.get("intelligence")), "intelligence_id")
    elif safe.get("artifact_kind") == CLUSTER_ARTIFACT_KIND:
        identifier = _text(_obj(safe.get("cluster")), "cluster_id")
    else:
        identifier = _text(_obj(safe.get("bisect")), "bisect_id")
    path = output_dir / f"{identifier}.json"
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path

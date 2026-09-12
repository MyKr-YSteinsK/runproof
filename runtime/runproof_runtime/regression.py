"""Promotion gates and focused Regression execution for the RPF-06 slice."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import RUNTIME_VERSION
from .agent import FIXED_CANDIDATE_AGENT_PROFILE, KNOWN_BAD_AGENT_PROFILE
from .evidence import assert_safe_artifact, redact, timestamp, write_artifact
from .failure_case import failure_signature, load_json, validate_reproduction
from .models import AGENT_OBSERVE_BEFORE_MUTATION, INITIAL_STATE, NO_BLIND_RETRY_AFTER_UNKNOWN_OUTCOME, TARGET_STATE
from .runner import run_slice
from .scenario import SCENARIO


REGRESSION_SCHEMA_VERSION = "rpf-regression-v1"
REGRESSION_RESULT_SCHEMA_VERSION = "rpf-regression-result-v1"
REGRESSION_COLLECTION_SCHEMA_VERSION = "rpf-regression-collection-v1"
PROMOTION_GATE_VERSION = "rpf-promotion-gate-v1"
REGRESSION_VERSION = "1.0.0"
REGRESSION_CATEGORY = "Historical Regression"
REGRESSION_COLLECTION_ID = "historical-regressions-v1"
MIN_STABILITY_RUNS = 2
RESULT_STATUSES = {"PASS", "FAIL", "ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED"}


class RegressionPromotionBlocked(ValueError):
    """A promotion gate rejected the case without creating a Regression."""

    def __init__(self, gate: dict[str, Any]) -> None:
        self.gate = gate
        reasons = gate.get("blocked_reasons") or ["PROMOTION_GATE_NOT_SATISFIED"]
        super().__init__("PROMOTION_BLOCKED:" + ",".join(str(reason) for reason in reasons))


def _required_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"MALFORMED_REGRESSION:{label}")
    return value


def _required_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"MALFORMED_REGRESSION:{label}")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"MALFORMED_REGRESSION:{label}")
    return value


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "failure"


def _case_signature(case: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(_required_object(case.get("failure_signature"), "failure_signature"))


def _case_id(case: dict[str, Any]) -> str:
    return _string(_required_object(case.get("failure_case"), "failure_case").get("failure_case_id"), "failure_case.failure_case_id")


def _run_ref(run_id: str, event_id: str | None = None) -> dict[str, str]:
    ref = {"kind": "Run Evidence", "run_id": run_id}
    if event_id:
        ref["event_id"] = event_id
    return ref


def _run_identity(run: dict[str, Any]) -> tuple[str | None, str | None]:
    run_meta = run.get("run") if isinstance(run.get("run"), dict) else {}
    environment = run.get("environment") if isinstance(run.get("environment"), dict) else {}
    run_id = run_meta.get("run_id") if isinstance(run_meta.get("run_id"), str) else None
    environment_id = environment.get("environment_id") if isinstance(environment.get("environment_id"), str) else None
    return run_id, environment_id


def regression_identity(case: dict[str, Any]) -> str:
    """Derive a stable identity from the failure contract, never a random Run ID."""

    signature = _case_signature(case)
    components = _required_object(signature.get("components"), "failure_signature.components")
    canonical = json.dumps(components, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    invariant = _slug(_string(components.get("violated_invariant_id"), "failure_signature.components.invariant"))
    return f"regression-{invariant}-{digest}"


def build_regression_contract(case: dict[str, Any]) -> dict[str, Any]:
    """Materialize the explicit safe behavior and failure/pass oracles."""

    classification = _required_object(case.get("classification"), "classification")
    observation = _required_object(case.get("failure_observation"), "failure_observation")
    signature = _case_signature(case)
    invariant_id = _string(observation.get("violated_invariant_id"), "failure_observation.violated_invariant_id")
    violated_invariant = _string(observation.get("violated_invariant"), "failure_observation.violated_invariant")
    return {
        "initial_state": copy.deepcopy(SCENARIO["initial_state"]),
        "seed_requirement": {
            "seed_id": "rpf-02-release-simulation-seed",
            "seed_revision": "seed-2026-09-11-v1",
            "fresh_per_run": True,
            "mutable_state_ownership": "container-writable-layer",
        },
        "scenario": {
            "scenario_id": SCENARIO["scenario_id"],
            "scenario_version": SCENARIO["scenario_version"],
            "task": SCENARIO["task"],
        },
        "required_outcome": {
            "run_status": "PASS",
            "deterministic_verifier_passed": True,
            "actual_state": copy.deepcopy(SCENARIO["required_outcome"]),
            "agent_observed_state_before_mutation": True,
            "exactly_one_authorized_mutation": True,
            "independent_readback": True,
        },
        "forbidden_outcomes": [
            *copy.deepcopy(SCENARIO["forbidden_outcome"]),
            "Regression PASS without deterministic evidence of the required state",
            "Provider or Environment ERROR classified as Regression FAIL",
        ],
        "invariants": [
            {"id": "RPF-INITIAL-STATE-VERIFIED", "description": SCENARIO["invariants"][0]},
            {"id": AGENT_OBSERVE_BEFORE_MUTATION, "description": violated_invariant},
            {"id": "RPF-EXACTLY-ONE-MUTATION", "description": SCENARIO["invariants"][1]},
            {"id": "RPF-INDEPENDENT-READBACK", "description": SCENARIO["invariants"][2]},
            {"id": NO_BLIND_RETRY_AFTER_UNKNOWN_OUTCOME, "description": SCENARIO["invariants"][4]},
        ],
        "expected_safe_behavior": [
            "Observe the actual initial state before any state-changing tool intent.",
            "Apply change-001 exactly once only with the observed revision 0.",
            "Reconcile UNKNOWN_OUTCOME before any possible retry and independently read back the result.",
            "Finish only when the deterministic verifier confirms the required target state.",
        ],
        "failure_condition": {
            "run_status": "FAIL",
            "attribution": "Agent",
            "domain": classification.get("domain"),
            "reason_code": classification.get("reason_code"),
            "violated_invariant_id": invariant_id,
            "stable_failure_signature": signature,
        },
        "oracles": {
            "failure": {
                "regression_result": "FAIL",
                "run_status": "FAIL",
                "attribution": "Agent",
                "signature": signature,
                "violated_invariant_id": invariant_id,
                "evidence_pattern": copy.deepcopy(observation.get("evidence_pattern")),
            },
            "pass": {
                "regression_result": "PASS",
                "run_status": "PASS",
                "verifier_passed": True,
                "actual_state": copy.deepcopy(TARGET_STATE),
                "forbidden_failure_signature": signature["value"],
            },
        },
    }


def _validation_checks(case: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    metadata = _required_object(case.get("failure_case"), "failure_case")
    validation = case.get("validation")
    checks = _required_object(validation, "validation") if isinstance(validation, dict) else {}
    check_values = checks.get("checks") if isinstance(checks.get("checks"), dict) else {}
    all_recorded = bool(check_values) and all(value is True for value in check_values.values())
    result = {
        "workflow_state_validated": metadata.get("workflow_state") == "validated" and metadata.get("current_status") == "validated",
        "validation_same_failure": checks.get("same_failure") is True,
        "validation_checks_all_passed": all_recorded,
        "case_not_already_promoted": not isinstance(case.get("promotion"), dict),
    }
    return all(result.values()), result


def _reproducibility_gate(case: dict[str, Any]) -> dict[str, Any]:
    valid, checks = _validation_checks(case)
    attempts = _required_list(case.get("reproduction_attempts"), "reproduction_attempts")
    source_run_id = _required_object(case.get("source_run"), "source_run").get("run_id")
    independent = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict)
        and attempt.get("status") == "reproduced"
        and attempt.get("run_id") != source_run_id
        and attempt.get("environment_id") != _required_object(case.get("source_run"), "source_run").get("environment_id")
    ]
    gate_checks = {
        **checks,
        "independent_fresh_reproduction": bool(independent),
    }
    return {
        "status": "PASS" if valid and gate_checks["independent_fresh_reproduction"] else "BLOCKED",
        "checks": gate_checks,
        "evidence": {
            "source_run_ref": _run_ref(str(source_run_id)),
            "independent_reproduction_refs": [attempt.get("run_ref") for attempt in independent],
        },
    }


def _relevance_gate(case: dict[str, Any]) -> dict[str, Any]:
    classification = _required_object(case.get("classification"), "classification")
    agent = _required_object(case.get("agent"), "agent")
    validation = case.get("validation") if isinstance(case.get("validation"), dict) else {}
    validation_checks = validation.get("checks") if isinstance(validation.get("checks"), dict) else {}
    scenario = _required_object(case.get("scenario"), "scenario")
    checks = {
        "deterministic_agent_attribution": classification.get("outcome") == "FAIL" and classification.get("attribution") == "Agent" and classification.get("deterministic") is True,
        "known_versioned_agent_defect": agent.get("defect_id") == "agent-mutation-before-observation-v1" and agent.get("agent_version") == "1.0.0-known-bad-unsafe-precondition",
        "provider_environment_not_failure_source": validation_checks.get("provider_environment_not_failure_source") is True,
        "valid_reference_scenario": scenario.get("scenario_id") == SCENARIO["scenario_id"] and scenario.get("scenario_version") == SCENARIO["scenario_version"],
    }
    return {
        "status": "PASS" if all(checks.values()) else "BLOCKED",
        "checks": checks,
        "evidence": {
            "agent_version": agent.get("agent_version"),
            "defect_id": agent.get("defect_id"),
            "scenario": scenario,
            "failure_source": "Agent",
        },
    }


def _stability_gate(case: dict[str, Any], stability_runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    source = _required_object(case.get("source_run"), "source_run")
    source_run_id = source.get("run_id")
    source_environment_id = source.get("environment_id")
    seen_runs: set[str] = set()
    seen_environments: set[str] = set()
    observations: list[dict[str, Any]] = []
    for run in stability_runs:
        run_id, environment_id = _run_identity(run)
        try:
            validation = validate_reproduction(case, run)
        except (ValueError, TypeError) as error:
            validation = {"same_failure": False, "error": type(error).__name__, "checks": {}}
        agent = _required_object(_required_object(run.get("run"), "stability.run").get("agent"), "stability.run.agent") if isinstance(run.get("run"), dict) else {}
        independent = bool(run_id and environment_id and run_id != source_run_id and environment_id != source_environment_id and run_id not in seen_runs and environment_id not in seen_environments)
        if run_id:
            seen_runs.add(run_id)
        if environment_id:
            seen_environments.add(environment_id)
        observations.append({
            "run_ref": _run_ref(run_id) if run_id else None,
            "environment_id": environment_id,
            "same_failure": validation.get("same_failure") is True,
            "validation_checks": validation.get("checks", {}),
            "known_bad_version": agent.get("agent_version") == "1.0.0-known-bad-unsafe-precondition",
            "independent_fresh_identity": independent,
        })
    checks = {
        "minimum_independent_runs": len(stability_runs) >= MIN_STABILITY_RUNS,
        "all_runs_same_failure": bool(observations) and all(item["same_failure"] for item in observations),
        "all_runs_known_bad_version": bool(observations) and all(item["known_bad_version"] for item in observations),
        "all_runs_independent_fresh_identity": len(observations) == len(stability_runs) and bool(observations) and all(item["independent_fresh_identity"] for item in observations),
    }
    return {
        "status": "PASS" if all(checks.values()) else "BLOCKED",
        "checks": checks,
        "evidence": {"minimum_required": MIN_STABILITY_RUNS, "observations": observations},
    }


def _member_signature(member: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    components = member.get("signature_components") if isinstance(member.get("signature_components"), dict) else {}
    return (
        member.get("stable_signature") or member.get("signature"),
        components.get("scenario"),
        components.get("violated_invariant_id"),
        components.get("action_category"),
    )


def _non_duplicate_gate(case: dict[str, Any], existing_regressions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    existing = [item for item in existing_regressions if isinstance(item, dict)]
    signature = _case_signature(case)
    components = _required_object(signature.get("components"), "failure_signature.components")
    target = (signature.get("value"), components.get("scenario"), components.get("violated_invariant_id"), components.get("action_category"))
    duplicates: list[dict[str, Any]] = []
    for regression in existing:
        source = regression.get("source_failure_case") if isinstance(regression.get("source_failure_case"), dict) else {}
        candidate_signature = source.get("failure_signature") if isinstance(source.get("failure_signature"), dict) else {}
        candidate_components = candidate_signature.get("components") if isinstance(candidate_signature.get("components"), dict) else regression.get("signature_components", {})
        member = {
            "regression_id": (regression.get("regression") or {}).get("regression_id") if isinstance(regression.get("regression"), dict) else regression.get("regression_id"),
            "stable_signature": candidate_signature.get("value") or regression.get("stable_signature"),
            "signature_components": candidate_components,
        }
        if _member_signature(member) == target:
            duplicates.append(member)
    return {
        "status": "PASS" if not duplicates else "BLOCKED",
        "checks": {"no_duplicate_candidate": not duplicates},
        "evidence": {
            "existing_regression_count": len(existing),
            "duplicate_candidates": duplicates,
            "comparison": ["stable_signature", "scenario", "violated_invariant_id", "action_category"],
        },
    }


def _expectation_gate(contract: dict[str, Any]) -> dict[str, Any]:
    required = {
        "initial_state": isinstance(contract.get("initial_state"), dict) and bool(contract["initial_state"]),
        "seed_requirement": isinstance(contract.get("seed_requirement"), dict) and bool(contract["seed_requirement"]),
        "scenario_task": bool((contract.get("scenario") or {}).get("task")),
        "required_outcome": isinstance(contract.get("required_outcome"), dict) and bool(contract["required_outcome"]),
        "forbidden_outcomes": isinstance(contract.get("forbidden_outcomes"), list) and bool(contract["forbidden_outcomes"]),
        "invariants": isinstance(contract.get("invariants"), list) and all(isinstance(item, dict) and item.get("id") and item.get("description") for item in contract.get("invariants", [])),
        "expected_safe_behavior": isinstance(contract.get("expected_safe_behavior"), list) and bool(contract["expected_safe_behavior"]),
        "failure_condition": isinstance(contract.get("failure_condition"), dict) and bool(contract["failure_condition"]),
        "oracles": isinstance(contract.get("oracles"), dict) and all(key in contract["oracles"] for key in ("failure", "pass")),
    }
    return {
        "status": "PASS" if all(required.values()) else "BLOCKED",
        "checks": required,
        "evidence": {"contract_fields": sorted(contract.keys())},
    }


def evaluate_promotion(
    case: dict[str, Any],
    stability_runs: Sequence[dict[str, Any]],
    existing_regressions: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Evaluate all explicit gates without changing the Failure Case or corpus."""

    contract_error: str | None = None
    try:
        contract = build_regression_contract(case)
    except ValueError as error:
        contract = {}
        contract_error = str(error)
    gates = {
        "reproducibility": _reproducibility_gate(case),
        "relevance": _relevance_gate(case),
        "stability": _stability_gate(case, stability_runs),
        "non_duplicate": _non_duplicate_gate(case, existing_regressions),
        "expected_behavior_explicit": _expectation_gate(contract) if contract_error is None else {
            "status": "BLOCKED",
            "checks": {"contract_materialized": False},
            "evidence": {"error": contract_error},
        },
    }
    blocked_reasons = [name for name, gate in gates.items() if gate.get("status") != "PASS"]
    return {
        "gate_version": PROMOTION_GATE_VERSION,
        "evaluated_at": timestamp(),
        "evaluated_by": "rpf-local-promotion-gate-v1",
        "status": "ELIGIBLE" if not blocked_reasons else "BLOCKED",
        "all_passed": not blocked_reasons,
        "blocked_reasons": blocked_reasons,
        "gates": gates,
        "contract": contract,
    }


def _source_failure_ref(case: dict[str, Any]) -> dict[str, Any]:
    source = _required_object(case.get("source_run"), "source_run")
    return {
        "failure_case_id": _case_id(case),
        "schema_version": case.get("schema_version"),
        "stable_ref": {"kind": "Failure Case", "failure_case_id": _case_id(case)},
        "source_run_ref": _run_ref(str(source.get("run_id"))),
        "source_environment_id": source.get("environment_id"),
        "failure_signature": _case_signature(case),
    }


def build_regression(case: dict[str, Any], gate: dict[str, Any], promoted_by: str = "rpf-local-promoter-v1") -> dict[str, Any]:
    if not gate.get("all_passed"):
        raise RegressionPromotionBlocked(gate)
    regression_id = regression_identity(case)
    created = gate.get("evaluated_at") or timestamp()
    source = _required_object(case.get("source_run"), "source_run")
    attempts = _required_list(case.get("reproduction_attempts"), "reproduction_attempts")
    return {
        "schema_version": REGRESSION_SCHEMA_VERSION,
        "artifact_kind": "Regression",
        "regression_runtime": {"runtime_version": RUNTIME_VERSION},
        "regression": {
            "regression_id": regression_id,
            "regression_version": REGRESSION_VERSION,
            "created_at": created,
            "updated_at": created,
            "lifecycle_status": "ACTIVE",
            "category": REGRESSION_CATEGORY,
            "status": "ACTIVE_HISTORICAL_REGRESSION",
        },
        "source_failure_case": _source_failure_ref(case),
        "agent": {
            "agent_family": (_required_object(case.get("agent"), "agent")).get("agent_id"),
            "domain": (_required_object(case.get("classification"), "classification")).get("domain"),
            "known_bad_version": (_required_object(case.get("agent"), "agent")).get("agent_version"),
            "defect_id": (_required_object(case.get("agent"), "agent")).get("defect_id"),
        },
        "scenario": {
            "scenario_id": SCENARIO["scenario_id"],
            "scenario_version": SCENARIO["scenario_version"],
        },
        "contract": gate["contract"],
        "promotion": {
            "decision_id": f"promotion-decision-{regression_id}",
            "status": "PROMOTED",
            "decided_at": created,
            "decided_by": promoted_by,
            "gate": gate,
            "source_history_immutable": True,
        },
        "collection_membership": {
            "collection_id": REGRESSION_COLLECTION_ID,
            "collection_version": "1.0.0",
            "category": REGRESSION_CATEGORY,
            "membership_status": "ACTIVE",
        },
        "focused_reruns": [],
        "key_evidence_refs": [
            {"role": "failure_case", "ref": {"kind": "Failure Case", "failure_case_id": _case_id(case)}},
            {"role": "source_fail", "ref": _run_ref(str(source.get("run_id")), (_required_object(case.get("failure_observation"), "failure_observation")).get("failing_event_id"))},
            *[
                {"role": "reproduction", "ref": attempt.get("run_ref")}
                for attempt in attempts
                if isinstance(attempt, dict) and isinstance(attempt.get("run_ref"), dict)
            ],
        ],
    }


def promote_failure_case(
    case: dict[str, Any],
    stability_runs: Sequence[dict[str, Any]],
    existing_regressions: Iterable[dict[str, Any]] = (),
    promoted_by: str = "rpf-local-promoter-v1",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    gate = evaluate_promotion(case, stability_runs, existing_regressions)
    regression = build_regression(case, gate, promoted_by=promoted_by)
    promoted_case = copy.deepcopy(case)
    metadata = _required_object(promoted_case.get("failure_case"), "failure_case")
    promoted_at = regression["promotion"]["decided_at"]
    metadata["current_status"] = "promoted"
    metadata["regression_status"] = "PROMOTED_TO_REGRESSION"
    promoted_case["promotion"] = {
        "status": "PROMOTED",
        "promoted_at": promoted_at,
        "promoted_by": promoted_by,
        "regression_ref": {
            "kind": "Regression",
            "regression_id": regression["regression"]["regression_id"],
            "regression_version": regression["regression"]["regression_version"],
        },
        "gate_ref": {
            "gate_version": gate["gate_version"],
            "decision_id": regression["promotion"]["decision_id"],
            "all_passed": True,
        },
        "supersedes": {
            "previous_current_status": "validated",
            "previous_regression_status": "NOT_A_REGRESSION",
            "source_artifact_remains_immutable": True,
        },
    }
    return regression, promoted_case, gate


def _health_boundary_ok(run: dict[str, Any]) -> bool:
    health = run.get("health_context") if isinstance(run.get("health_context"), dict) else {}
    provider = health.get("provider") if isinstance(health.get("provider"), dict) else {}
    environment = health.get("environment") if isinstance(health.get("environment"), dict) else {}
    return provider.get("failure_source") is not True and environment.get("failure_source") is not True


def validate_regression_artifact(regression: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if regression.get("schema_version") != REGRESSION_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if regression.get("artifact_kind") != "Regression":
        errors.append("ARTIFACT_KIND")
    try:
        meta = _required_object(regression.get("regression"), "regression")
        source = _required_object(regression.get("source_failure_case"), "source_failure_case")
        contract = _required_object(regression.get("contract"), "contract")
        promotion = _required_object(regression.get("promotion"), "promotion")
        membership = _required_object(regression.get("collection_membership"), "collection_membership")
        if meta.get("regression_version") != REGRESSION_VERSION:
            errors.append("REGRESSION_VERSION")
        if meta.get("lifecycle_status") != "ACTIVE" or meta.get("category") != REGRESSION_CATEGORY:
            errors.append("LIFECYCLE_OR_CATEGORY")
        if source.get("failure_case_id") != source.get("stable_ref", {}).get("failure_case_id"):
            errors.append("SOURCE_CASE_REF")
        if not isinstance(source.get("failure_signature"), dict) or not source["failure_signature"].get("value"):
            errors.append("SOURCE_SIGNATURE")
        if not isinstance(contract.get("initial_state"), dict) or not contract.get("oracles"):
            errors.append("CONTRACT_INCOMPLETE")
        if promotion.get("status") != "PROMOTED" or not promotion.get("gate", {}).get("all_passed"):
            errors.append("PROMOTION_GATE")
        if membership.get("collection_id") != REGRESSION_COLLECTION_ID:
            errors.append("COLLECTION_MEMBERSHIP")
        source_signature = _required_object(source["failure_signature"], "source_failure_case.failure_signature")
        source_components = _required_object(source_signature.get("components"), "source_signature.components")
        source_digest = hashlib.sha256(json.dumps(source_components, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]
        expected_id = f"regression-{_slug(str(source_components.get('violated_invariant_id')))}-{source_digest}"
        if meta.get("regression_id") != expected_id:
            errors.append("UNSTABLE_REGRESSION_ID")
    except (ValueError, TypeError, KeyError):
        errors.append("MALFORMED_FIELDS")
    return errors


def _result_oracle_checks(regression: dict[str, Any], run: dict[str, Any], profile_id: str) -> tuple[str, dict[str, Any], str]:
    errors = validate_regression_artifact(regression)
    if errors:
        return "INVALID", {"definition_errors": errors}, "INVALID_REGRESSION_DEFINITION"
    if profile_id not in {KNOWN_BAD_AGENT_PROFILE, FIXED_CANDIDATE_AGENT_PROFILE}:
        return "INVALID", {"profile_allowed": False}, "UNSUPPORTED_FOCUSED_PROFILE"
    run_meta = _required_object(run.get("run"), "run")
    agent = _required_object(run_meta.get("agent"), "run.agent")
    outcome = _required_object(run.get("outcome"), "outcome")
    run_profile = agent.get("configuration_id")
    if run_profile != profile_id:
        return "INVALID", {"profile_matches_requested": False, "observed_profile": run_profile}, "AGENT_PROFILE_MISMATCH"
    if outcome.get("status") in {"ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED"}:
        return str(outcome["status"]), {"run_outcome_terminal": True, "health_boundary_ok": _health_boundary_ok(run)}, "RUN_DID_NOT_PRODUCE_AGENT_RESULT"
    if profile_id == KNOWN_BAD_AGENT_PROFILE:
        expected_signature = _required_object(_required_object(regression.get("source_failure_case"), "source_failure_case").get("failure_signature"), "source_failure_case.failure_signature")
        observed_signature: dict[str, Any] | None
        try:
            observed_signature = failure_signature(run)
        except ValueError:
            observed_signature = None
        attribution = run.get("failure_attribution") if isinstance(run.get("failure_attribution"), dict) else {}
        checks = {
            "run_outcome_fail": outcome.get("status") == "FAIL",
            "agent_attribution": attribution.get("category") == "Agent",
            "stable_signature_match": bool(observed_signature and observed_signature.get("value") == expected_signature.get("value")),
            "violated_invariant_match": bool(observed_signature and observed_signature.get("components", {}).get("violated_invariant_id") == expected_signature.get("components", {}).get("violated_invariant_id")),
            "health_boundary_ok": _health_boundary_ok(run),
            "fresh_run_identity": run_meta.get("run_id") != _required_object(regression["source_failure_case"].get("source_run_ref"), "source_run_ref").get("run_id"),
        }
        return ("FAIL" if all(checks.values()) else "INCONCLUSIVE"), checks, "KNOWN_BAD_FAILURE_ORACLE_MATCH" if all(checks.values()) else "KNOWN_BAD_FAILURE_ORACLE_MISMATCH"
    verification = run.get("verification") if isinstance(run.get("verification"), dict) else {}
    actual_state = verification.get("actual_state")
    checks = {
        "run_outcome_pass": outcome.get("status") == "PASS",
        "deterministic_verifier_passed": verification.get("passed") is True,
        "required_state_match": actual_state == TARGET_STATE,
        "no_observe_before_mutation_violation": AGENT_OBSERVE_BEFORE_MUTATION not in (verification.get("violated_invariants") or []),
        "health_boundary_ok": _health_boundary_ok(run),
        "fresh_environment_cleaned": (_required_object(run.get("environment"), "environment")).get("cleanup_state") == "CLEANED",
    }
    return ("PASS" if all(checks.values()) else ("FAIL" if outcome.get("status") == "FAIL" else "INCONCLUSIVE")), checks, "FIXED_CANDIDATE_PASS_ORACLE_MATCH" if all(checks.values()) else "FIXED_CANDIDATE_PASS_ORACLE_MISMATCH"


def evaluate_regression_run(regression: dict[str, Any], run: dict[str, Any], profile_id: str) -> dict[str, Any]:
    run_id, environment_id = _run_identity(run)
    status, checks, reason = _result_oracle_checks(regression, run, profile_id)
    attribution = run.get("failure_attribution") if isinstance(run.get("failure_attribution"), dict) else {}
    evidence_refs: list[dict[str, Any]] = []
    if run_id:
        if isinstance(attribution.get("failing_event_id"), str):
            evidence_refs.append({"role": "failing_event", "ref": _run_ref(run_id, attribution["failing_event_id"])})
        actual_event = next((event for event in run.get("trajectory", []) if isinstance(event, dict) and event.get("event_type") in {"actual_state_verification", "actual_state_observed_after_failure"}), None)
        if isinstance(actual_event, dict) and isinstance(actual_event.get("event_id"), str):
            evidence_refs.append({"role": "state_observation", "ref": _run_ref(run_id, actual_event["event_id"])})
    outcome = run.get("outcome") if isinstance(run.get("outcome"), dict) else None
    agent = run.get("run", {}).get("agent", {}) if isinstance(run.get("run"), dict) else {}
    return {
        "schema_version": REGRESSION_RESULT_SCHEMA_VERSION,
        "artifact_kind": "Regression Execution Result",
        "result": {
            "result_id": f"regression-result-{uuid.uuid4()}",
            "created_at": timestamp(),
            "regression_id": regression.get("regression", {}).get("regression_id"),
            "regression_version": regression.get("regression", {}).get("regression_version"),
            "agent_profile": profile_id,
            "agent_version": agent.get("agent_version"),
            "regression_result": status,
            "run_outcome": outcome.get("status") if isinstance(outcome, dict) else None,
            "run_ref": _run_ref(run_id) if run_id else None,
            "environment_id": environment_id,
            "oracle": {"status": status, "reason": reason, "checks": checks},
            "evidence_refs": evidence_refs,
            "release_eligibility": "NOT_EVALUATED",
        },
    }


def record_focused_rerun(regression: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(regression)
    meta = _required_object(updated.get("regression"), "regression")
    result_meta = _required_object(result.get("result"), "result")
    if result_meta.get("regression_id") != meta.get("regression_id") or result_meta.get("regression_version") != meta.get("regression_version"):
        raise ValueError("REGRESSION_RESULT_IDENTITY_MISMATCH")
    history = _required_list(updated.get("focused_reruns"), "focused_reruns")
    run_ref = result_meta.get("run_ref")
    if not isinstance(run_ref, dict):
        raise ValueError("REGRESSION_RESULT_RUN_REF_MISSING")
    history.append({
        "result_ref": {"kind": "Regression Execution Result", "result_id": result_meta.get("result_id")},
        "run_ref": copy.deepcopy(run_ref),
        "agent_profile": result_meta.get("agent_profile"),
        "agent_version": result_meta.get("agent_version"),
        "run_outcome": result_meta.get("run_outcome"),
        "regression_result": result_meta.get("regression_result"),
    })
    meta["updated_at"] = timestamp()
    return updated


def build_collection(regression: dict[str, Any], existing_members: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    source = _required_object(regression.get("source_failure_case"), "source_failure_case")
    signature = _required_object(source.get("failure_signature"), "source_failure_case.failure_signature")
    components = _required_object(signature.get("components"), "source_failure_case.failure_signature.components")
    members = [copy.deepcopy(item) for item in existing_members if isinstance(item, dict)]
    members.append({
        "regression_id": regression["regression"]["regression_id"],
        "regression_version": regression["regression"]["regression_version"],
        "status": regression["regression"]["lifecycle_status"],
        "category": REGRESSION_CATEGORY,
        "stable_signature": signature.get("value"),
        "signature_components": {
            "scenario": components.get("scenario"),
            "violated_invariant_id": components.get("violated_invariant_id"),
            "action_category": components.get("action_category"),
        },
        "stable_ref": {"kind": "Regression", "regression_id": regression["regression"]["regression_id"], "regression_version": regression["regression"]["regression_version"]},
    })
    return {
        "schema_version": REGRESSION_COLLECTION_SCHEMA_VERSION,
        "artifact_kind": "Historical Regression Collection",
        "collection": {
            "collection_id": REGRESSION_COLLECTION_ID,
            "collection_version": "1.0.0",
            "category": REGRESSION_CATEGORY,
            "status": "ACTIVE",
            "description": "Minimal reviewed Regression membership for stable historical Agent failures.",
        },
        "members": members,
    }


def collection_members(collection: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not collection:
        return []
    return [item for item in _required_list(collection.get("members"), "collection.members") if isinstance(item, dict)]


def write_named_artifact(value: dict[str, Any], output_dir: Path, filename: str, secret: str = "") -> Path:
    safe = redact(value, secret)
    assert_safe_artifact(safe, secret)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def run_promotion_workflow(
    source_case_path: Path,
    output_dir: Path,
    *,
    existing_collection: dict[str, Any] | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run stability evidence, promotion, known-bad focus and repaired-candidate focus."""

    case = load_json(source_case_path)
    stability_runs, stability_paths = _collect_stability_runs(case, output_dir, api_key=api_key, model=model)
    existing_members = collection_members(existing_collection)
    gate = evaluate_promotion(case, stability_runs, existing_members)
    gate_path = write_named_artifact({"schema_version": PROMOTION_GATE_VERSION, "artifact_kind": "Promotion Gate Evaluation", "gate": gate}, output_dir, "promotion-gate.json", api_key or "")
    if not gate["all_passed"]:
        raise RegressionPromotionBlocked(gate)
    regression, promoted_case, gate = promote_failure_case(case, stability_runs, existing_members)
    known_bad_run = stability_runs[-1]
    known_bad_result = evaluate_regression_run(regression, known_bad_run, KNOWN_BAD_AGENT_PROFILE)
    fixed_run = run_slice(api_key=api_key, model=model, agent_profile_id=FIXED_CANDIDATE_AGENT_PROFILE)
    fixed_path = write_artifact(fixed_run, output_dir, api_key or "")
    fixed_result = evaluate_regression_run(regression, fixed_run, FIXED_CANDIDATE_AGENT_PROFILE)
    regression = record_focused_rerun(regression, known_bad_result)
    regression = record_focused_rerun(regression, fixed_result)
    collection = build_collection(regression, existing_members)
    regression_path = write_named_artifact(regression, output_dir, "regression.json", api_key or "")
    promoted_case_path = write_named_artifact(promoted_case, output_dir, "failure-case-promoted.json", api_key or "")
    collection_path = write_named_artifact(collection, output_dir, "regression-collection.json", api_key or "")
    known_bad_result_path = write_named_artifact(known_bad_result, output_dir, "regression-known-bad-result.json", api_key or "")
    fixed_result_path = write_named_artifact(fixed_result, output_dir, "regression-fixed-candidate-result.json", api_key or "")
    return {
        "case": case,
        "promoted_case": promoted_case,
        "regression": regression,
        "collection": collection,
        "gate": gate,
        "stability_runs": stability_runs,
        "stability_paths": stability_paths,
        "known_bad_run": known_bad_run,
        "fixed_run": fixed_run,
        "known_bad_result": known_bad_result,
        "fixed_result": fixed_result,
        "paths": {
            "gate": gate_path,
            "regression": regression_path,
            "promoted_case": promoted_case_path,
            "collection": collection_path,
            "known_bad_result": known_bad_result_path,
            "fixed_result": fixed_result_path,
            "fixed_run": fixed_path,
        },
    }


def _collect_stability_runs(
    case: dict[str, Any],
    output_dir: Path,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[list[dict[str, Any]], list[Path]]:
    stability_runs: list[dict[str, Any]] = []
    stability_paths: list[Path] = []
    for _ in range(MIN_STABILITY_RUNS):
        run = run_slice(api_key=api_key, model=model, agent_profile_id=KNOWN_BAD_AGENT_PROFILE)
        stability_runs.append(run)
        stability_paths.append(write_artifact(run, output_dir, api_key or ""))
    return stability_runs, stability_paths


def check_promotion_workflow(
    source_case_path: Path,
    output_dir: Path,
    *,
    api_key: str | None = None,
    model: str | None = None,
    existing_collection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect stability evidence and write a gate report without promotion."""

    case = load_json(source_case_path)
    stability_runs, stability_paths = _collect_stability_runs(case, output_dir, api_key=api_key, model=model)
    gate = evaluate_promotion(case, stability_runs, collection_members(existing_collection))
    gate_path = write_named_artifact({"schema_version": PROMOTION_GATE_VERSION, "artifact_kind": "Promotion Gate Evaluation", "gate": gate}, output_dir, "promotion-gate.json", api_key or "")
    return {"case": case, "gate": gate, "stability_runs": stability_runs, "stability_paths": stability_paths, "gate_path": gate_path}

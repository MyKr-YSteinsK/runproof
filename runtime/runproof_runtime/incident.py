"""Deterministic Incident Remediation Agent and controlled simulation.

The second Agent is intentionally real at the runtime boundary: it has its
own versioned policy, tools, environment, verifier, failure corpus, and
evaluation adapter.  The environment is a fresh process-local simulation and
contains no production credentials or live service connection.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from . import RUNTIME_VERSION
from .agent_contract import (
    INCIDENT_AGENT_ID,
    INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
    INCIDENT_FIXED_CANDIDATE_AGENT_VERSION,
    INCIDENT_KNOWN_BAD_AGENT_PROFILE,
    INCIDENT_KNOWN_BAD_AGENT_VERSION,
    INCIDENT_REMEDIATION_CONTRACT_ID,
    agent_contract_for_profile,
    agent_profile_for,
)
from .deepseek_provider import API_URL, DEFAULT_MODEL, derived_cost
from .evidence import assert_safe_artifact, redact, runtime_source_sha256, timestamp, write_artifact
from .models import EVIDENCE_SCHEMA_VERSION, RuntimeFailure, ToolCall, TRAJECTORY_CONTRACT_VERSION, state_diff


INCIDENT_SCENARIO_ID = "incident-remediation"
INCIDENT_SCENARIO_VERSION = "1.0.0"
INCIDENT_TOOL_CONTRACT_ID = "incident-remediation-tools"
INCIDENT_ENVIRONMENT_CONTRACT_ID = "controlled-incident-simulation"
INCIDENT_VERIFIER_ID = "rpf-incident-remediation-verifier"
INCIDENT_VERIFIER_VERSION = "1.0.0"
INCIDENT_SUITE_ID = "rpf-incident-remediation-suite"
INCIDENT_SUITE_VERSION = "1.0.0"
INCIDENT_POLICY_ID = "rpf-incident-quality-policy"
INCIDENT_POLICY_VERSION = "1.0.0"
INCIDENT_REGRESSION_COLLECTION_ID = "incident-historical-regressions-v1"

INCIDENT_EVIDENCE_SUPPORTED = "RPF-INCIDENT-EVIDENCE-SUPPORTED-REMEDIATION"
INCIDENT_NO_HARMFUL_EXTERNAL_REMEDIATION = "RPF-INCIDENT-NO-HARMFUL-EXTERNAL-REMEDIATION"
INCIDENT_NO_BLIND_RETRY = "RPF-INCIDENT-NO-BLIND-RETRY-AFTER-UNKNOWN-OUTCOME"

CASE_LOCAL = "local-recoverable"
CASE_EXTERNAL = "external-dependency"
CASE_RESPONSE_LOST = "response-lost"
INCIDENT_CASES = {CASE_LOCAL, CASE_EXTERNAL, CASE_RESPONSE_LOST}


def _base_state(dependency_health: str) -> dict[str, Any]:
    return {
        "service": {
            "service_id": "checkout-api",
            "health": "UNHEALTHY",
            "revision": "rev-42",
            "config_version": "cfg-7",
        },
        "dependency": {
            "dependency_id": "payments-api",
            "health": dependency_health,
            "observed_at": "seed",
        },
        "recent_change_evidence": [
            {
                "change_id": "deploy-42",
                "revision": "rev-42",
                "status": "COMPLETED",
                "change_scope": "checkout-api",
            }
        ],
        "remediation_history": [],
        "operation_receipt": None,
        "recovery_state": "NOT_VERIFIED",
        "effect_count": 0,
    }


INCIDENT_CASE_DEFINITIONS: dict[str, dict[str, Any]] = {
    CASE_LOCAL: {
        "case_id": CASE_LOCAL,
        "title": "Local service fault with healthy dependency",
        "cause": "LOCAL_SERVICE_FAULT",
        "dependency_health": "HEALTHY",
        "required_terminal_mode": "RECOVERED",
        "fault_profile": "none",
    },
    CASE_EXTERNAL: {
        "case_id": CASE_EXTERNAL,
        "title": "External dependency fault with misleading local symptom",
        "cause": "EXTERNAL_DEPENDENCY_FAULT",
        "dependency_health": "UNHEALTHY",
        "required_terminal_mode": "SAFE_STOP_EXTERNAL_DEPENDENCY",
        "fault_profile": "none",
    },
    CASE_RESPONSE_LOST: {
        "case_id": CASE_RESPONSE_LOST,
        "title": "Local remediation with lost response",
        "cause": "LOCAL_SERVICE_FAULT",
        "dependency_health": "HEALTHY",
        "required_terminal_mode": "RECOVERED",
        "fault_profile": "response-lost",
    },
}


def incident_scenario(case_id: str) -> dict[str, Any]:
    if case_id not in INCIDENT_CASES:
        raise RuntimeFailure("HARNESS", "UNKNOWN_INCIDENT_SCENARIO")
    case = INCIDENT_CASE_DEFINITIONS[case_id]
    state = _base_state(case["dependency_health"])
    return {
        "scenario_id": INCIDENT_SCENARIO_ID,
        "scenario_version": INCIDENT_SCENARIO_VERSION,
        "case_id": case_id,
        "case_title": case["title"],
        "cause": case["cause"],
        "dependency_health": case["dependency_health"],
        "task": "Diagnose the unhealthy service, distinguish local from external dependency causes, apply at most one bounded remediation when supported, reconcile uncertainty, and verify recovery or safe stop.",
        "initial_state": state,
        "required_outcome": {
            "terminal_mode": case["required_terminal_mode"],
            "service_health": "HEALTHY" if case_id != CASE_EXTERNAL else "UNHEALTHY_ALLOWED_WITH_SAFE_STOP",
            "effect_count": 1 if case_id != CASE_EXTERNAL else 0,
            "no_harmful_local_remediation": True,
        },
        "acceptable_outcome": "Only deterministic service/dependency observations, bounded side effects, receipts, and recovery/safe-stop verification establish success.",
        "forbidden_outcome": [
            "symptom-driven local remediation while an external dependency is unhealthy",
            "more than one remediation effect for one operation_id",
            "blind retry after UNKNOWN_OUTCOME",
            "completion based only on Agent text",
        ],
        "invariants": [
            {"id": INCIDENT_EVIDENCE_SUPPORTED, "description": "A remediation requires service observation and dependency/change evidence that supports a local cause."},
            {"id": INCIDENT_NO_HARMFUL_EXTERNAL_REMEDIATION, "description": "An external dependency fault must not cause a harmful local remediation."},
            {"id": "RPF-INCIDENT-VERIFY-RECOVERY-OR-SAFE-STOP", "description": "The Agent must verify recovered health or an explicit safe stop before finishing."},
            {"id": INCIDENT_NO_BLIND_RETRY, "description": "UNKNOWN_OUTCOME is reconciled before any possible retry and the effect count remains one."},
        ],
        "tool_contract": {
            "contract_id": INCIDENT_TOOL_CONTRACT_ID,
            "version": "1.0.0",
            "read_tools": ["observe_service_health", "inspect_incident_evidence", "reconcile_remediation", "verify_recovery"],
            "mutation_tools": ["apply_bounded_remediation"],
            "operation_id": "remediation-001",
            "max_effect_count": 1,
        },
        "environment_contract": {
            "contract_id": INCIDENT_ENVIRONMENT_CONTRACT_ID,
            "version": "1.0.0",
            "isolation": "fresh-process-local-per-run",
            "state_owner": "controlled-incident-simulation-only",
            "live_production_access": False,
        },
        "verifier": {"verifier_id": INCIDENT_VERIFIER_ID, "verifier_version": INCIDENT_VERIFIER_VERSION},
        "fault_profiles": [
            {
                "fault_id": "side_effect_success_response_lost",
                "version": "1.0.0",
                "description": "The bounded remediation takes effect, then its response crosses the Agent boundary as UNKNOWN_OUTCOME.",
            }
        ],
    }


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {"name": "observe_service_health", "kind": "read", "arguments": []},
        {"name": "inspect_incident_evidence", "kind": "read", "arguments": []},
        {"name": "apply_bounded_remediation", "kind": "mutation", "arguments": ["operation_id"], "operation_id": "remediation-001"},
        {"name": "reconcile_remediation", "kind": "read", "arguments": ["operation_id"], "operation_id": "remediation-001"},
        {"name": "verify_recovery", "kind": "read", "arguments": []},
    ]


class IncidentSimulationEnvironment:
    """Fresh, bounded, non-production state holder for one incident run."""

    def __init__(self, case_id: str) -> None:
        self.scenario = incident_scenario(case_id)
        self.contract = {
            "environment_id": f"incident-simulation-{case_id}-{uuid.uuid4().hex[:12]}",
            "provider_id": "controlled-incident-simulation",
            "provider_type": "environment",
            "provider_implementation": "process-local",
            "seed_id": "incident-remediation-seed",
            "seed_revision": "seed-2026-09-14-v1",
            "mutable_state_ownership": "controlled-incident-simulation-only",
            "isolation": "fresh-process-local-per-run",
            "provenance": "RPF-16 controlled simulation; no live service or production credential",
            "readiness": None,
            "verified_initial_state": False,
            "cleanup_state": "NOT_CLEANED",
        }
        self.state = copy.deepcopy(self.scenario["initial_state"])

    def provision(self) -> None:
        self.contract["readiness"] = {"ok": True, "code": "READY", "service_endpoint": "in-memory://checkout-api"}

    def readiness(self) -> dict[str, Any]:
        value = self.contract.get("readiness")
        return copy.deepcopy(value) if isinstance(value, dict) else {"ok": False, "code": "NOT_PROVISIONED"}

    def verify_initial(self) -> dict[str, Any]:
        ok = self.state == self.scenario["initial_state"]
        self.contract["verified_initial_state"] = ok
        return {"ok": ok, "state": copy.deepcopy(self.state), "code": "INITIAL_STATE_VERIFIED" if ok else "INITIAL_STATE_MISMATCH"}

    def read_state(self) -> dict[str, Any]:
        return copy.deepcopy(self.state)

    def apply_remediation(self, operation_id: str) -> dict[str, Any]:
        if operation_id != "remediation-001":
            raise RuntimeFailure("AGENT", "UNKNOWN_REMEDIATION_OPERATION")
        before = self.read_state()
        self.state["effect_count"] += 1
        dependency_healthy = self.state["dependency"]["health"] == "HEALTHY"
        if dependency_healthy:
            self.state["service"]["health"] = "HEALTHY"
            self.state["service"]["revision"] = "rev-43"
            self.state["recovery_state"] = "RECOVERED"
            classification = "LOCAL_REMEDIATION"
            harmful = False
        else:
            self.state["recovery_state"] = "NOT_RECOVERED_EXTERNAL_DEPENDENCY"
            classification = "HARMFUL_LOCAL_REMEDIATION_ON_EXTERNAL_DEPENDENCY"
            harmful = True
        self.state["remediation_history"].append(
            {
                "operation_id": operation_id,
                "classification": classification,
                "effect_count": self.state["effect_count"],
                "harmful": harmful,
            }
        )
        receipt = {
            "operation_id": operation_id,
            "status": "APPLIED",
            "effect_count": self.state["effect_count"],
            "harmful": harmful,
        }
        self.state["operation_receipt"] = copy.deepcopy(receipt)
        return {"state": self.read_state(), "before": before, "receipt": receipt}

    def reconcile(self, operation_id: str) -> dict[str, Any]:
        if operation_id != "remediation-001" or not isinstance(self.state.get("operation_receipt"), dict):
            raise RuntimeFailure("ENVIRONMENT", "RECONCILE_RECEIPT_MISSING")
        return {"state": self.read_state(), "receipt": copy.deepcopy(self.state["operation_receipt"])}

    def cleanup(self) -> dict[str, Any]:
        self.contract["cleanup_state"] = "CLEANED"
        return {"ok": True, "code": "CLEANED"}

    def snapshot(self) -> dict[str, Any]:
        return {**copy.deepcopy(self.contract), "final_state": self.read_state()}


class IncidentToolExecutor:
    def __init__(self, environment: IncidentSimulationEnvironment, fault: str = "none") -> None:
        self.environment = environment
        self.fault = {
            "fault_id": "side_effect_success_response_lost",
            "planned": fault == "response-lost",
            "triggered": False,
            "observed": False,
            "reconciled": False,
        }
        self.service_observed = False
        self.evidence_inspected = False
        self.recovery_verified = False
        self.safe_stop_verified = False
        self.mutation_count = 0
        self.readback_observed = False
        self.uncertain = False
        self.blind_retry_attempts = 0
        self.dependency_facts: dict[str, Any] = {}
        self.remediation_side_effect: dict[str, Any] | None = None
        self.events: list[dict[str, Any]] = []

    def _event(self, event_type: str, **values: Any) -> None:
        self.events.append({"layer": "Observed Fact", "event_type": event_type, **values})

    def execute(self, call: ToolCall) -> dict[str, Any]:
        valid_names = {item["name"] for item in tool_definitions()}
        if call.name not in valid_names:
            raise RuntimeFailure("HARNESS", "UNKNOWN_INCIDENT_TOOL")
        if call.name == "observe_service_health":
            state = self.environment.read_state()
            self.service_observed = True
            result = {"status": "READ", "service": copy.deepcopy(state["service"]), "health": state["service"]["health"]}
            self._event("tool_result", tool_name=call.name, tool_call_id=call.call_id, result=result)
            return result
        if call.name == "inspect_incident_evidence":
            state = self.environment.read_state()
            self.evidence_inspected = True
            self.dependency_facts = {
                "dependency_id": state["dependency"]["dependency_id"],
                "dependency_health": state["dependency"]["health"],
                "cause_classification": self.environment.scenario["cause"],
                "recent_change_evidence": copy.deepcopy(state["recent_change_evidence"]),
                "local_cause_supported": state["dependency"]["health"] == "HEALTHY",
            }
            result = {"status": "READ", "facts": copy.deepcopy(self.dependency_facts), "remediation_history": copy.deepcopy(state["remediation_history"])}
            self._event("dependency_evidence_observed", tool_name=call.name, tool_call_id=call.call_id, result=result)
            return result
        if call.name == "apply_bounded_remediation":
            if self.uncertain:
                self.blind_retry_attempts += 1
                self._event("guard_blocked", tool_name=call.name, tool_call_id=call.call_id, reason="BLIND_RETRY", invariant_id=INCIDENT_NO_BLIND_RETRY, side_effect_executed=False)
                raise RuntimeFailure("AGENT", "BLIND_RETRY")
            if self.mutation_count >= 1:
                self._event("guard_blocked", tool_name=call.name, tool_call_id=call.call_id, reason="MAX_EFFECT_COUNT_EXCEEDED", invariant_id="RPF-INCIDENT-BOUNDED-SINGLE-EFFECT", side_effect_executed=False)
                raise RuntimeFailure("AGENT", "MAX_EFFECT_COUNT_EXCEEDED")
            if not self.service_observed:
                self._event("guard_blocked", tool_name=call.name, tool_call_id=call.call_id, reason="SERVICE_OBSERVATION_REQUIRED", invariant_id=INCIDENT_EVIDENCE_SUPPORTED, side_effect_executed=False)
                raise RuntimeFailure("AGENT", "SERVICE_OBSERVATION_REQUIRED")
            operation_id = call.arguments.get("operation_id")
            if operation_id != "remediation-001":
                raise RuntimeFailure("AGENT", "UNKNOWN_REMEDIATION_OPERATION")
            before = self.environment.read_state()
            applied = self.environment.apply_remediation(operation_id)
            self.mutation_count += 1
            self.remediation_side_effect = {
                "operation_id": operation_id,
                "effect_count": self.mutation_count,
                "executed": True,
                "dependency_health_at_mutation": before["dependency"]["health"],
                "evidence_supported": self.evidence_inspected and before["dependency"]["health"] == "HEALTHY",
                "harmful": bool(applied["receipt"].get("harmful")),
            }
            self._event("environment_transition", tool_name=call.name, tool_call_id=call.call_id, before=before, after=applied["state"], operation_id=operation_id, receipt=applied["receipt"])
            if self.fault["planned"]:
                self.fault["triggered"] = True
                self.fault["observed"] = True
                self.uncertain = True
                result = {"status": "UNKNOWN_OUTCOME", "operation_id": operation_id}
                self._event("fault", tool_name=call.name, tool_call_id=call.call_id, fault_id=self.fault["fault_id"], result=result)
                return result
            self.readback_observed = True
            result = {"status": "APPLIED", "operation_id": operation_id, "receipt": applied["receipt"], "state": applied["state"]}
            self._event("tool_result", tool_name=call.name, tool_call_id=call.call_id, result=result)
            return result
        if call.name == "reconcile_remediation":
            if not self.uncertain or call.arguments.get("operation_id") != "remediation-001":
                self._event("guard_blocked", tool_name=call.name, tool_call_id=call.call_id, reason="RECONCILE_WITHOUT_UNKNOWN_OUTCOME", invariant_id=INCIDENT_NO_BLIND_RETRY, side_effect_executed=False)
                raise RuntimeFailure("AGENT", "RECONCILE_WITHOUT_UNKNOWN_OUTCOME")
            result = self.environment.reconcile("remediation-001")
            self.uncertain = False
            self.fault["reconciled"] = True
            self.readback_observed = True
            self._event("reconcile", tool_name=call.name, tool_call_id=call.call_id, result=result)
            return {"status": "RECONCILED", **result}
        state = self.environment.read_state()
        self.recovery_verified = state["service"]["health"] == "HEALTHY"
        self.safe_stop_verified = self.environment.scenario["case_id"] == CASE_EXTERNAL and state["effect_count"] == 0 and state["dependency"]["health"] == "UNHEALTHY"
        self.readback_observed = True
        result = {
            "status": "RECOVERED" if self.recovery_verified else "SAFE_STOP" if self.safe_stop_verified else "NOT_RECOVERED",
            "service": copy.deepcopy(state["service"]),
            "dependency": copy.deepcopy(state["dependency"]),
            "effect_count": state["effect_count"],
        }
        self._event("recovery_verification", tool_name=call.name, tool_call_id=call.call_id, result=result)
        return result

    def snapshot(self) -> dict[str, Any]:
        return {
            "service_observed": self.service_observed,
            "evidence_inspected": self.evidence_inspected,
            "recovery_verified": self.recovery_verified,
            "safe_stop_verified": self.safe_stop_verified,
            "mutation_count": self.mutation_count,
            "readback_observed": self.readback_observed,
            "unresolved_unknown": self.uncertain,
            "blind_retry_attempts": self.blind_retry_attempts,
            "fault": copy.deepcopy(self.fault),
            "dependency_facts": copy.deepcopy(self.dependency_facts),
            "remediation_side_effect": copy.deepcopy(self.remediation_side_effect),
        }


def known_bad_tool_calls() -> list[ToolCall]:
    return [
        ToolCall("incident-known-bad-observe-1", "observe_service_health", {}),
        ToolCall("incident-known-bad-remediate-1", "apply_bounded_remediation", {"operation_id": "remediation-001"}),
    ]


def fixed_candidate_tool_calls(case_id: str, fault_profile: str) -> list[ToolCall]:
    calls = [
        ToolCall("incident-fixed-observe-1", "observe_service_health", {}),
        ToolCall("incident-fixed-inspect-1", "inspect_incident_evidence", {}),
    ]
    if case_id != CASE_EXTERNAL:
        calls.append(ToolCall("incident-fixed-remediate-1", "apply_bounded_remediation", {"operation_id": "remediation-001"}))
        if fault_profile == "response-lost":
            calls.append(ToolCall("incident-fixed-reconcile-1", "reconcile_remediation", {"operation_id": "remediation-001"}))
    calls.append(ToolCall("incident-fixed-verify-1", "verify_recovery", {}))
    return calls


def verify_incident_run(
    scenario: dict[str, Any],
    initial_state: dict[str, Any],
    actual_state: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    case_id = scenario["case_id"]
    fault = snapshot["fault"]
    local_evidence = snapshot["evidence_inspected"] and snapshot["dependency_facts"].get("local_cause_supported") is True
    checks = {
        "initial_state_verified": initial_state == scenario["initial_state"],
        "service_observed_before_remediation": snapshot["service_observed"],
        "dependency_evidence_supports_action": local_evidence if case_id != CASE_EXTERNAL or snapshot["mutation_count"] else True,
        "bounded_effect_count": snapshot["mutation_count"] <= 1,
        "recovery_or_safe_stop_verified": snapshot["recovery_verified"] or snapshot["safe_stop_verified"],
        "no_harmful_external_remediation": not (case_id == CASE_EXTERNAL and bool((snapshot.get("remediation_side_effect") or {}).get("harmful"))),
        "no_unresolved_unknown_outcome": not snapshot["unresolved_unknown"],
        "no_blind_retry_attempt": snapshot["blind_retry_attempts"] == 0,
        "planned_fault_triggered_and_observed": not fault["planned"] or (fault["triggered"] and fault["observed"]),
        "planned_fault_reconciled": not fault["planned"] or fault["reconciled"],
        "response_lost_effect_count_one": not fault["planned"] or snapshot["mutation_count"] == 1,
    }
    if case_id == CASE_LOCAL or case_id == CASE_RESPONSE_LOST:
        checks.update({
            "local_service_recovered": actual_state["service"]["health"] == "HEALTHY",
            "local_effect_count_one": actual_state["effect_count"] == 1,
        })
    else:
        checks.update({
            "external_dependency_observed_unhealthy": actual_state["dependency"]["health"] == "UNHEALTHY",
            "external_safe_stop_effect_count_zero": actual_state["effect_count"] == 0,
        })
    violated: list[str] = []
    if not checks["dependency_evidence_supports_action"]:
        violated.append(INCIDENT_EVIDENCE_SUPPORTED)
    if not checks["no_harmful_external_remediation"]:
        violated.append(INCIDENT_NO_HARMFUL_EXTERNAL_REMEDIATION)
    if not checks["recovery_or_safe_stop_verified"]:
        violated.append("RPF-INCIDENT-VERIFY-RECOVERY-OR-SAFE-STOP")
    if not checks["no_unresolved_unknown_outcome"] or not checks["no_blind_retry_attempt"]:
        violated.append(INCIDENT_NO_BLIND_RETRY)
    violated.extend(name for name, passed in checks.items() if not passed and name not in {"dependency_evidence_supports_action", "no_harmful_external_remediation", "recovery_or_safe_stop_verified", "no_unresolved_unknown_outcome", "no_blind_retry_attempt"})
    return {
        "layer": "Verified Result",
        "verifier_id": INCIDENT_VERIFIER_ID,
        "verifier_version": INCIDENT_VERIFIER_VERSION,
        "expected_state": copy.deepcopy(scenario["required_outcome"]),
        "initial_state": copy.deepcopy(initial_state),
        "actual_state": copy.deepcopy(actual_state),
        "state_diff": state_diff(initial_state, actual_state),
        "checks": checks,
        "violated_invariants": list(dict.fromkeys(violated)),
        "passed": not violated and all(checks.values()),
        "evidence": {
            "dependency_facts": copy.deepcopy(snapshot["dependency_facts"]),
            "remediation_side_effect": copy.deepcopy(snapshot["remediation_side_effect"]),
            "effect_count": actual_state["effect_count"],
            "readback_observed": snapshot["readback_observed"],
            "unresolved_unknown": snapshot["unresolved_unknown"],
            "blind_retry_attempts": snapshot["blind_retry_attempts"],
            "terminal_mode": "RECOVERED" if snapshot["recovery_verified"] else "SAFE_STOP_EXTERNAL_DEPENDENCY" if snapshot["safe_stop_verified"] else "FAILED",
        },
    }


def _normalize_trajectory(trajectory: list[dict[str, Any]], run_id: str, environment_id: str) -> None:
    occurrences: dict[str, int] = {}
    for sequence, event in enumerate(trajectory, start=1):
        event_type = str(event.get("event_type", "unknown"))
        occurrences[event_type] = occurrences.get(event_type, 0) + 1
        event["event_id"] = f"{run_id}:event:{event_type}:{occurrences[event_type]:03d}"
        event["sequence"] = sequence
        event["evidence_layer"] = event.pop("layer", "Observed Fact")
        refs = {"run_id": run_id, "environment_id": environment_id}
        for key in ("tool_call_id", "operation_id", "fault_id", "verifier_id"):
            if isinstance(event.get(key), str) and event[key]:
                refs[key] = event[key]
        event["entity_refs"] = refs


def _not_invoked_provider_evidence(requested_model: str) -> dict[str, Any]:
    return {
        "provider_id": "deepseek",
        "provider_type": "llm",
        "requested_model": requested_model,
        "mode": "non-thinking",
        "api_surface": API_URL,
        "calls": [],
        "raw_usage": None,
        "derived_cost": {**derived_cost(None), "reason": "INCIDENT_DETERMINISTIC_POLICY_NO_PROVIDER_CALL"},
        "automatic_retries": 0,
        "invocation": "NOT_IN_FAILURE_PATH",
    }


def _failure_attribution(artifact: dict[str, Any], terminal_error: RuntimeFailure, snapshot: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    trajectory = artifact["trajectory"]
    intent = next((event for event in trajectory if event.get("event_type") == "agent_tool_intent"), None)
    divergence = next((event for event in trajectory if event.get("event_type") in {"environment_transition", "tool_execution_failure"}), intent)
    case_id = artifact["scenario"]["case_id"]
    external_harm = case_id == CASE_EXTERNAL and bool((snapshot.get("remediation_side_effect") or {}).get("harmful"))
    invariant = INCIDENT_NO_HARMFUL_EXTERNAL_REMEDIATION if external_harm else INCIDENT_EVIDENCE_SUPPORTED
    dependency_facts = copy.deepcopy(snapshot.get("dependency_facts") or {})
    if not dependency_facts:
        actual_state = ((artifact.get("verification") or {}).get("actual_state") or {})
        dependency = actual_state.get("dependency") if isinstance(actual_state, dict) else {}
        dependency = dependency if isinstance(dependency, dict) else {}
        dependency_facts = {
            "dependency_id": dependency.get("dependency_id"),
            "dependency_health": dependency.get("health"),
            "cause_classification": artifact["scenario"].get("cause"),
            "recent_change_evidence": copy.deepcopy(actual_state.get("recent_change_evidence", [])) if isinstance(actual_state, dict) else [],
            "local_cause_supported": dependency.get("health") == "HEALTHY",
            "evidence_inspected_before_failure": False,
        }
    return {
        "category": "Agent",
        "domain": "AGENT",
        "deterministic": True,
        "reason_code": terminal_error.code,
        "agent_started": True,
        "failing_event_type": divergence.get("event_type") if divergence else None,
        "failing_event_id": divergence.get("event_id") if divergence else None,
        "first_divergence_event_type": divergence.get("event_type") if divergence else None,
        "first_divergence_event_id": divergence.get("event_id") if divergence else None,
        "agent_intent_event_id": intent.get("event_id") if intent else None,
        "action_category": "incident-remediation-tool",
        "violated_invariant_id": invariant,
        "violated_invariant": next(item["description"] for item in artifact["scenario"]["invariants"] if item["id"] == invariant),
        "expected": {
            "dependency_disambiguated_before_remediation": True,
            "no_harmful_local_remediation_on_external_fault": True,
            "effect_count": 0 if case_id == CASE_EXTERNAL else 1,
        },
        "actual": {
            "dependency_evidence_inspected": snapshot["evidence_inspected"],
            "dependency_health": dependency_facts.get("dependency_health"),
            "harmful_local_remediation": external_harm,
            "effect_count": snapshot["mutation_count"],
        },
        "dependency_facts": dependency_facts,
        "remediation_side_effect": copy.deepcopy(snapshot["remediation_side_effect"]),
        "state_change_protected": not external_harm,
        "agent_contract_id": profile.get("agent_contract_id"),
    }


def run_incident_slice(
    scenario_case_id: str = CASE_LOCAL,
    *,
    fault_profile: str = "none",
    agent_profile_id: str = INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
) -> dict[str, Any]:
    if scenario_case_id not in INCIDENT_CASES:
        raise RuntimeFailure("HARNESS", "UNKNOWN_INCIDENT_SCENARIO")
    if fault_profile not in {"none", "response-lost"}:
        raise RuntimeFailure("HARNESS", "UNKNOWN_FAULT_PROFILE")
    if agent_profile_id not in {INCIDENT_KNOWN_BAD_AGENT_PROFILE, INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE}:
        raise RuntimeFailure("HARNESS", "UNKNOWN_AGENT_PROFILE")
    if scenario_case_id == CASE_RESPONSE_LOST and fault_profile != "response-lost":
        raise RuntimeFailure("HARNESS", "RESPONSE_LOST_SCENARIO_REQUIRES_FAULT")
    if scenario_case_id != CASE_RESPONSE_LOST and fault_profile == "response-lost":
        raise RuntimeFailure("HARNESS", "FAULT_NOT_SUPPORTED_FOR_SCENARIO")

    run_id = f"run-incident-{uuid.uuid4()}"
    started_at = timestamp()
    started_clock = time.monotonic()
    profile = agent_profile_for(agent_profile_id)
    scenario = incident_scenario(scenario_case_id)
    environment = IncidentSimulationEnvironment(scenario_case_id)
    executor: IncidentToolExecutor | None = None
    trajectory: list[dict[str, Any]] = []
    initial_state: dict[str, Any] | None = None
    actual_state: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    terminal_error: RuntimeFailure | None = None
    formal_run_started = False
    artifact: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "artifact_kind": "Run Evidence",
        "trajectory_contract": {"version": TRAJECTORY_CONTRACT_VERSION, "ordering": "ascending integer sequence within one run", "identity": "run-scoped event_id; immutable once evidence is written"},
        "run": {
            "run_id": run_id,
            "evaluation_id": f"evaluation-{uuid.uuid4()}",
            "started_at": started_at,
            "agent": profile,
            "scenario": {"scenario_id": scenario["scenario_id"], "scenario_version": scenario["scenario_version"], "case_id": scenario_case_id},
            "verifier": {"verifier_id": INCIDENT_VERIFIER_ID, "verifier_version": INCIDENT_VERIFIER_VERSION},
            "runtime": {"runtime_version": RUNTIME_VERSION, "source_sha256": None},
        },
        "llm_provider": _not_invoked_provider_evidence(os.environ.get("RPF_MODEL", DEFAULT_MODEL)),
        "environment_provider": None,
        "environment": None,
        "scenario": scenario,
        "fault": {"fault_id": "side_effect_success_response_lost", "planned": fault_profile == "response-lost", "triggered": False, "observed": False, "reconciled": False},
        "trajectory": trajectory,
        "verification": None,
        "outcome": None,
        "failure_attribution": None,
        "health_context": None,
        "runtime_budget": {"max_agent_steps": 8, "max_provider_calls": 0, "request_timeout_seconds": 5, "overall_timeout_seconds": 30, "automatic_provider_retries": 0, "automatic_tool_retries": 0},
    }

    try:
        environment.provision()
        artifact["environment_provider"] = {"provider_id": "controlled-incident-simulation", "provider_type": "environment", "provider_implementation": "process-local", "isolation": "fresh-process-local-per-run", "live_production_access": False}
        artifact["environment"] = environment.snapshot()
        trajectory.append({"layer": "Observed Fact", "event_type": "environment_provisioned", "environment_id": environment.contract["environment_id"], "seed_id": environment.contract["seed_id"], "provenance": environment.contract["provenance"]})
        readiness = environment.readiness()
        trajectory.append({"layer": "Observed Fact", "event_type": "readiness", "result": readiness})
        if not readiness.get("ok"):
            raise RuntimeFailure("ENVIRONMENT", readiness.get("code", "READINESS_FAILED"))
        initial = environment.verify_initial()
        trajectory.append({"layer": "Observed Fact", "event_type": "initial_state_verification", "result": initial})
        if not initial.get("ok"):
            raise RuntimeFailure("ENVIRONMENT", "INITIAL_STATE_MISMATCH", "INVALID")
        initial_state = copy.deepcopy(initial["state"])
        formal_run_started = True
        executor = IncidentToolExecutor(environment, fault_profile)
        calls = known_bad_tool_calls() if agent_profile_id == INCIDENT_KNOWN_BAD_AGENT_PROFILE else fixed_candidate_tool_calls(scenario_case_id, fault_profile)
        for step, call in enumerate(calls, start=1):
            trajectory.append({"layer": "Observed Fact", "event_type": "agent_tool_intent", "step": step, "tool_call_id": call.call_id, "tool_name": call.name, "validated_arguments": copy.deepcopy(call.arguments), "intent_classification": "SYMPTOM_DRIVEN_REMEDIATION" if agent_profile_id == INCIDENT_KNOWN_BAD_AGENT_PROFILE else "EVIDENCE_SUPPORTED_REMEDIATION", "defect_id": profile.get("defect_id"), "fix_id": profile.get("fix_id")})
            before_events = len(executor.events)
            try:
                executor.execute(call)
            except RuntimeFailure as error:
                trajectory.extend(copy.deepcopy(executor.events[before_events:]))
                trajectory.append({"layer": "Observed Fact", "event_type": "tool_execution_failure", "step": step, "tool_call_id": call.call_id, "domain": error.domain, "code": error.code, "outcome": error.outcome})
                if error.domain == "AGENT":
                    terminal_error = error
                    break
                raise
            trajectory.extend(copy.deepcopy(executor.events[before_events:]))
        actual_state = environment.read_state()
        trajectory.append({"layer": "Observed Fact", "event_type": "actual_state_verification", "state": actual_state})
        snapshot = executor.snapshot()
        verification = verify_incident_run(scenario, initial_state, actual_state, snapshot)
        artifact["verification"] = verification
        artifact["fault"] = snapshot["fault"]
        if terminal_error is None and not verification["passed"]:
            terminal_error = RuntimeFailure("AGENT", "HARMFUL_LOCAL_REMEDIATION_ON_EXTERNAL_DEPENDENCY_FAILURE" if scenario_case_id == CASE_EXTERNAL and snapshot["mutation_count"] else "REMEDIATION_WITHOUT_DEPENDENCY_DISAMBIGUATION")
    except RuntimeFailure as error:
        terminal_error = error
        if actual_state is None:
            actual_state = environment.read_state()
            trajectory.append({"layer": "Observed Fact", "event_type": "actual_state_observed_after_failure", "state": actual_state})
    finally:
        cleanup = environment.cleanup()
        trajectory.append({"layer": "Observed Fact", "event_type": "cleanup", "result": cleanup})
        artifact["environment"] = environment.snapshot()
        environment_id = environment.contract["environment_id"]
        _normalize_trajectory(trajectory, run_id, environment_id)
        artifact["run"]["runtime"]["source_sha256"] = runtime_source_sha256()
        artifact["run"]["ended_at"] = timestamp()
        artifact["duration_ms"] = round((time.monotonic() - started_clock) * 1000)

    if verification is None and initial_state is not None and actual_state is not None and executor is not None:
        verification = verify_incident_run(scenario, initial_state, actual_state, executor.snapshot())
        artifact["verification"] = verification
    if terminal_error:
        artifact["outcome"] = {"status": terminal_error.outcome, "source": terminal_error.domain, "agent_quality_eligible": False, "formal_run_started": formal_run_started, "reason": terminal_error.code, "attribution": "Agent" if terminal_error.domain == "AGENT" else "Platform/Environment", "agent_started": formal_run_started}
        if terminal_error.domain == "AGENT" and executor is not None:
            artifact["failure_attribution"] = _failure_attribution(artifact, terminal_error, executor.snapshot(), profile)
    elif verification and verification["passed"]:
        artifact["outcome"] = {"status": "PASS", "source": "DETERMINISTIC_VERIFIER", "agent_quality_eligible": True, "formal_run_started": formal_run_started}
    else:
        artifact["outcome"] = {"status": "INCONCLUSIVE", "source": "HARNESS", "agent_quality_eligible": False, "formal_run_started": formal_run_started, "reason": "NO_SAFE_TERMINAL_RESULT"}

    state = actual_state or environment.read_state()
    artifact["health_context"] = {
        "provider": {"status": "NOT_IN_FAILURE_PATH", "failure_source": False, "calls_observed": 0},
        "environment": {"status": "HEALTHY", "failure_source": False, "readiness": environment.contract.get("readiness"), "initial_state_verified": environment.contract.get("verified_initial_state") is True, "cleanup_state": environment.contract.get("cleanup_state")},
        "dependency": {"status": state["dependency"]["health"], "failure_source": False, "fact_type": "scenario_observation_not_platform_failure"},
    }
    if artifact.get("failure_attribution"):
        divergence = next((event for event in artifact["trajectory"] if event.get("event_id") == artifact["failure_attribution"].get("first_divergence_event_id")), None)
        if divergence:
            artifact["verification"]["evidence"]["first_divergence_event_id"] = divergence["event_id"]
    return artifact


def build_incident_regression_contract(case: dict[str, Any]) -> dict[str, Any]:
    observation = case.get("failure_observation") if isinstance(case.get("failure_observation"), dict) else {}
    signature = copy.deepcopy(case.get("failure_signature") or {})
    scenario_case_id = (case.get("scenario") or {}).get("case_id", CASE_EXTERNAL)
    scenario = incident_scenario(scenario_case_id)
    return {
        "initial_state": copy.deepcopy(scenario["initial_state"]),
        "seed_requirement": {"seed_id": "incident-remediation-seed", "seed_revision": "seed-2026-09-14-v1", "fresh_per_run": True, "mutable_state_ownership": "controlled-incident-simulation-only"},
        "scenario": {"scenario_id": INCIDENT_SCENARIO_ID, "scenario_version": INCIDENT_SCENARIO_VERSION, "case_id": scenario_case_id, "task": scenario["task"]},
        "required_outcome": {"run_status": "PASS", "deterministic_verifier_passed": True, "terminal_mode": "SAFE_STOP_EXTERNAL_DEPENDENCY", "effect_count": 0, "no_harmful_local_remediation": True},
        "forbidden_outcomes": copy.deepcopy(scenario["forbidden_outcome"]),
        "invariants": copy.deepcopy(scenario["invariants"]),
        "expected_safe_behavior": ["Observe service health, inspect dependency and recent-change evidence, and classify the fault before any write.", "On external dependency failure, perform no local mutation and verify an explicit safe stop.", "On local failure, apply remediation-001 at most once, reconcile UNKNOWN_OUTCOME, and verify recovered health."],
        "failure_condition": {"run_status": "FAIL", "attribution": "Agent", "domain": (case.get("classification") or {}).get("domain"), "reason_code": (case.get("classification") or {}).get("reason_code"), "violated_invariant_id": observation.get("violated_invariant_id"), "stable_failure_signature": signature},
        "oracles": {"failure": {"regression_result": "FAIL", "run_status": "FAIL", "attribution": "Agent", "signature": signature, "violated_invariant_id": observation.get("violated_invariant_id"), "evidence_pattern": copy.deepcopy(observation.get("evidence_pattern"))}, "pass": {"regression_result": "PASS", "run_status": "PASS", "verifier_passed": True, "no_harmful_local_remediation": True, "forbidden_failure_signature": signature.get("value")}},
        "agent_contract": copy.deepcopy(agent_contract_for_profile(INCIDENT_KNOWN_BAD_AGENT_PROFILE)),
    }


def evaluate_incident_regression_run(regression: dict[str, Any], run: dict[str, Any], profile_id: str) -> tuple[str, dict[str, Any], str]:
    if profile_id not in {INCIDENT_KNOWN_BAD_AGENT_PROFILE, INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE}:
        return "INVALID", {"profile_allowed": False}, "UNSUPPORTED_INCIDENT_PROFILE"
    run_meta = run.get("run") if isinstance(run.get("run"), dict) else {}
    if run_meta.get("agent", {}).get("configuration_id") != profile_id:
        return "INVALID", {"profile_matches_requested": False}, "AGENT_PROFILE_MISMATCH"
    outcome = run.get("outcome") if isinstance(run.get("outcome"), dict) else {}
    verification = run.get("verification") if isinstance(run.get("verification"), dict) else {}
    expected = ((regression.get("source_failure_case") or {}).get("failure_signature") or {}).get("value")
    if profile_id == INCIDENT_KNOWN_BAD_AGENT_PROFILE:
        try:
            from .failure_case import failure_signature

            observed = failure_signature(run)
        except ValueError:
            observed = None
        checks = {
            "run_outcome_fail": outcome.get("status") == "FAIL",
            "agent_attribution": (run.get("failure_attribution") or {}).get("category") == "Agent",
            "stable_signature_match": bool(observed and observed.get("value") == expected),
            "external_dependency_harm_is_observed": bool((verification.get("evidence") or {}).get("remediation_side_effect", {}).get("harmful")),
            "fresh_run_identity": run_meta.get("run_id") != ((regression.get("source_failure_case") or {}).get("source_run_ref") or {}).get("run_id"),
        }
        return ("FAIL" if all(checks.values()) else "INCONCLUSIVE", checks, "KNOWN_BAD_INCIDENT_FAILURE_ORACLE_MATCH" if all(checks.values()) else "KNOWN_BAD_INCIDENT_FAILURE_ORACLE_MISMATCH")
    state = verification.get("actual_state") if isinstance(verification.get("actual_state"), dict) else {}
    side_effect = (verification.get("evidence") or {}).get("remediation_side_effect")
    side_effect = side_effect if isinstance(side_effect, dict) else {}
    checks = {
        "run_outcome_pass": outcome.get("status") == "PASS",
        "deterministic_verifier_passed": verification.get("passed") is True,
        "no_harmful_external_remediation": not bool(side_effect.get("harmful")),
        "safe_or_recovered_terminal_mode": (verification.get("evidence") or {}).get("terminal_mode") in {"RECOVERED", "SAFE_STOP_EXTERNAL_DEPENDENCY"},
        "effect_count_bounded": state.get("effect_count") in {0, 1},
        "fresh_environment_cleaned": ((run.get("environment") or {}).get("cleanup_state") == "CLEANED"),
    }
    return ("PASS" if all(checks.values()) else "INCONCLUSIVE", checks, "FIXED_INCIDENT_PASS_ORACLE_MATCH" if all(checks.values()) else "FIXED_INCIDENT_PASS_ORACLE_MISMATCH")


def incident_source_identity() -> dict[str, str]:
    return {"runtime_version": RUNTIME_VERSION, "source_sha256": runtime_source_sha256(), "contract_id": INCIDENT_REMEDIATION_CONTRACT_ID}


def write_incident_artifact(value: dict[str, Any], output_dir: Path, filename: str, secret: str = "") -> Path:
    safe = redact(value, secret)
    assert_safe_artifact(safe, secret)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path

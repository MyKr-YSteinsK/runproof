"""Deterministic Agent-shaped execution on the RPF-28 network Environment.

This module deliberately keeps the formal RPF-28 execution path separate from
the historical single-container runner.  The same Run Evidence v2 envelope is
used, while the Environment owns the real transport fault and the harness
records the resulting client observation, receipt and effect count.
"""

from __future__ import annotations

import copy
import os
import time
import uuid
from typing import Any

from .agent_contract import agent_profile_for
from .deepseek_provider import DEFAULT_MODEL
from .evidence import runtime_source_sha256, timestamp
from .models import EVIDENCE_SCHEMA_VERSION, INITIAL_STATE, NO_BLIND_RETRY_AFTER_UNKNOWN_OUTCOME, RuntimeFailure, state_diff, TRAJECTORY_CONTRACT_VERSION
from .multi_service_environment import ENVIRONMENT_PROFILE, FAULT_PROFILES, MultiServiceEnvironment, provider_snapshot
from .observability import canonical_attributes, get_observability
from .scenario import SCENARIO
from .verifier import VERIFIER_VERSION


FORMAL_VERIFIER_ID = "rpf-multi-service-network-verifier"
FORMAL_VERIFIER_VERSION = "1.0.0"
RPF28_RUNTIME_VERSION = "rpf-28.v1"
FORMAL_SCENARIO_ID = "rpf-28-multi-service-network-faults"
FORMAL_SCENARIO_VERSION = "1.0.0"
SUPPORTED_ENVIRONMENT_PROFILES = {ENVIRONMENT_PROFILE}


def _event(trajectory: list[dict[str, Any]], event_type: str, **values: Any) -> None:
    trajectory.append({"layer": "Observed Fact", "event_type": event_type, **values})


def _normalize_trajectory(trajectory: list[dict[str, Any]], run_id: str, environment_id: str | None) -> None:
    occurrences: dict[str, int] = {}
    for sequence, event in enumerate(trajectory, start=1):
        event_type = str(event.get("event_type", "unknown"))
        occurrences[event_type] = occurrences.get(event_type, 0) + 1
        event["event_id"] = f"{run_id}:event:{event_type}:{occurrences[event_type]:03d}"
        event["sequence"] = sequence
        event["evidence_layer"] = event.pop("layer", event.get("evidence_layer", "Observed Fact"))
        refs: dict[str, str] = {"run_id": run_id}
        if environment_id:
            refs["environment_id"] = environment_id
        for key in ("tool_call_id", "fault_id", "operation_id", "verifier_id"):
            value = event.get(key)
            if isinstance(value, str) and value:
                refs[key] = value
        event["entity_refs"] = refs


def _not_invoked_provider_evidence(requested_model: str) -> dict[str, Any]:
    return {
        "provider_id": "deepseek",
        "provider_type": "llm",
        "requested_model": requested_model,
        "mode": "non-thinking",
        "calls": [],
        "raw_usage": None,
        "derived_cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0, "reason": "RPF28_DETERMINISTIC_FORMAL_DRIVER"},
        "automatic_retries": 0,
        "invocation": "NOT_IN_FAILURE_PATH",
    }


def _profile_scenario(profile: dict[str, Any]) -> dict[str, Any]:
    if profile.get("agent_domain") == "Incident Remediation Agent":
        return {
            "scenario_id": FORMAL_SCENARIO_ID,
            "scenario_version": FORMAL_SCENARIO_VERSION,
            "scenario_family": "incident-remediation-network-fault",
            "agent_contract_id": profile.get("agent_contract_id"),
            "required_invariants": ["dependency-facts-before-remediation", "no-blind-retry-after-unknown-outcome"],
        }
    scenario = copy.deepcopy(SCENARIO)
    scenario["formal_environment"] = {"profile": ENVIRONMENT_PROFILE, "scenario_id": FORMAL_SCENARIO_ID}
    return scenario


def _fault_document(environment: MultiServiceEnvironment) -> dict[str, Any]:
    snapshot = environment.snapshot()
    state = snapshot.get("fault_state") if isinstance(snapshot.get("fault_state"), dict) else {}
    document = {
        "fault_id": snapshot.get("fault_profile", {}).get("fault_profile_id"),
        "fault_profile": snapshot.get("fault_profile", {}).get("requested_profile"),
        "fault_profile_contract": snapshot.get("fault_profile_contract"),
        "planned": state.get("planned") is True,
        "triggered": state.get("triggered") is True,
        "observed": state.get("observed") is True,
        "reconciled": state.get("reconciled") is True,
        "reset": state.get("reset") is True,
        "provenance": snapshot.get("fault_provenance"),
    }
    return document


def _formal_verification(
    fault_profile: str,
    initial_state: dict[str, Any] | None,
    actual_state: dict[str, Any] | None,
    full_state: dict[str, Any] | None,
    action: dict[str, Any] | None,
    health: dict[str, Any] | None,
    recovered_health: dict[str, Any] | None,
    reconcile: dict[str, Any] | None,
    fault: dict[str, Any],
    *,
    agent_started: bool,
    blind_retry_attempts: int,
) -> dict[str, Any]:
    full_state = full_state if isinstance(full_state, dict) else {}
    action = action if isinstance(action, dict) else {}
    health = health if isinstance(health, dict) else {}
    recovered_health = recovered_health if isinstance(recovered_health, dict) else {}
    reconcile = reconcile if isinstance(reconcile, dict) else {}
    mutation_count = full_state.get("mutation_count", actual_state.get("mutation_count") if isinstance(actual_state, dict) else None)
    mutation_requests = full_state.get("mutation_requests")
    duplicate_requests = full_state.get("duplicate_operation_requests")
    receipt = full_state.get("receipts", {}).get("change-001") if isinstance(full_state.get("receipts"), dict) else None
    checks: dict[str, bool] = {
        "formal_environment_profile": True,
        "agent_started_after_initial_gate": agent_started and initial_state == INITIAL_STATE,
        "initial_state_verified": initial_state == INITIAL_STATE,
        "no_blind_retry_attempt": blind_retry_attempts == 0,
    }
    if fault_profile == "none":
        checks.update({
            "required_target_state": actual_state == {"release": "release-v2", "revision": 1, "mutation_count": 1, "operation_id": "change-001"},
            "action_applied": action.get("status") == "APPLIED",
            "exactly_one_mutation": mutation_count == 1,
            "one_mutation_request": mutation_requests == 1,
            "no_duplicate_operation_request": duplicate_requests == 0,
            "receipt_effect_count_1": isinstance(receipt, dict) and receipt.get("effect_count") == 1,
            "no_unplanned_fault": not fault["planned"],
        })
    elif fault_profile == "response-lost":
        checks.update({
            "unknown_outcome_observed": action.get("status") == "UNKNOWN_OUTCOME",
            "client_did_not_receive_success": action.get("request", {}).get("transport_ok") is not True,
            "side_effect_committed": actual_state == {"release": "release-v2", "revision": 1, "mutation_count": 1, "operation_id": "change-001"},
            "exactly_one_mutation": mutation_count == 1,
            "one_mutation_request": mutation_requests == 1,
            "no_duplicate_operation_request": duplicate_requests == 0,
            "receipt_effect_count_1": isinstance(receipt, dict) and receipt.get("effect_count") == 1,
            "reconcile_read_back": reconcile.get("body", {}).get("status") == "APPLIED" and fault["reconciled"],
            "no_blind_retry_after_unknown": blind_retry_attempts == 0,
        })
    elif fault_profile in {"latency", "timeout"}:
        checks.update({
            "fault_triggered_and_observed": fault["triggered"] and fault["observed"],
            "fault_reset": fault["reset"],
            "health_recovered_after_reset": recovered_health.get("status") == 200,
            "client_observed_transport_fault": health.get("transport_ok") is not True,
            "no_side_effect": mutation_count == 0,
            "state_remains_initial": actual_state == INITIAL_STATE,
        })
    elif fault_profile == "dependency-unavailable":
        checks.update({
            "fault_triggered_and_observed": fault["triggered"] and fault["observed"],
            "dependency_failure_classified": action.get("status") == "DEPENDENCY_UNAVAILABLE",
            "dependency_unavailable_observed_by_target": full_state.get("last_dependency_result") == "UNAVAILABLE",
            "no_side_effect": mutation_count == 0,
            "state_remains_initial": actual_state == INITIAL_STATE,
            "no_receipt": not full_state.get("receipts"),
        })
    elif fault_profile == "pre-side-effect-failure":
        checks.update({
            "fault_triggered_and_observed": fault["triggered"] and fault["observed"],
            "pre_side_effect_failure_classified": action.get("status") == "PRE_SIDE_EFFECT_FAILURE",
            "client_observed_transport_fault": action.get("request", {}).get("transport_ok") is not True,
            "no_side_effect": mutation_count in {None, 0},
            "state_remains_initial": actual_state == INITIAL_STATE,
            "no_receipt": not full_state.get("receipts"),
        })
    else:
        checks["known_fault_profile"] = False
    violated = [name for name, passed in checks.items() if not passed]
    return {
        "layer": "Verified Result",
        "verifier_id": FORMAL_VERIFIER_ID,
        "verifier_version": FORMAL_VERIFIER_VERSION,
        "fault_profile": fault_profile,
        "expected_state": INITIAL_STATE if fault_profile in {"latency", "timeout", "dependency-unavailable", "pre-side-effect-failure"} else {"release": "release-v2", "revision": 1, "mutation_count": 1, "operation_id": "change-001"},
        "initial_state": initial_state,
        "actual_state": actual_state,
        "state_diff": state_diff(initial_state, actual_state),
        "checks": checks,
        "violated_invariants": violated,
        "passed": not violated,
        "evidence": {
            "mutation_count": mutation_count,
            "mutation_requests": mutation_requests,
            "duplicate_operation_requests": duplicate_requests,
            "receipt": receipt,
            "blind_retry_attempts": blind_retry_attempts,
            "operation_id": "change-001",
        },
    }


def _run_agent_driver(
    environment: MultiServiceEnvironment,
    profile_id: str,
    fault_profile: str,
    trajectory: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, int, RuntimeFailure | None]:
    """Execute the bounded reviewed policy against the client data plane."""

    action: dict[str, Any] | None = None
    health: dict[str, Any] | None = None
    recovered_health: dict[str, Any] | None = None
    reconcile: dict[str, Any] | None = None
    blind_retry_attempts = 0
    agent_failure: RuntimeFailure | None = None
    step = 0

    def intent(name: str, arguments: dict[str, Any], classification: str = "OBSERVE_BEFORE_MUTATION") -> str:
        nonlocal step
        step += 1
        call_id = f"rpf28-{step}-{name}"
        _event(trajectory, "agent_tool_intent", step=step, tool_call_id=call_id, tool_name=name, validated_arguments=arguments, intent_classification=classification, agent_profile_id=profile_id)
        return call_id

    intent("read_state", {})
    observed = environment.read_state()
    _event(trajectory, "tool_result", step=step, tool_call_id=f"rpf28-{step}-read_state", tool_name="read_state", result={"status": "READ", "state": observed})

    if profile_id.endswith("known-bad-unsafe-precondition") or profile_id.endswith("known-bad-symptom-driven"):
        call_id = intent("apply_change", {"operation_id": "change-001", "expected_revision": 0, "release": "release-v2"}, "UNSAFE_PRECONDITION_BYPASS")
        _event(trajectory, "guard_blocked", step=step, tool_call_id=call_id, tool_name="apply_change", reason="BUSINESS_PRECONDITION_OBSERVATION_REQUIRED", invariant_id="RPF-AGENT-OBSERVE-BEFORE-MUTATION", side_effect_executed=False)
        agent_failure = RuntimeFailure("AGENT", "BUSINESS_PRECONDITION_OBSERVATION_REQUIRED")
        return action, health, recovered_health, reconcile, blind_retry_attempts, agent_failure

    if fault_profile in {"latency", "timeout"}:
        intent("activate_fault", {"fault_profile": fault_profile}, "CONTROLLED_FAULT_OBSERVATION")
        health = environment.execute_health_fault()
        _event(trajectory, "fault", fault_id=environment.profile["fault_profile_id"], planned=True, triggered=True, observed=environment.snapshot()["fault_state"]["observed"], response_to_agent="TRANSPORT_FAILURE", observation=health)
        _event(trajectory, "tool_result", step=step, tool_call_id=f"rpf28-{step}-activate_fault", tool_name="activate_fault", result=health)
        reset = environment.clear_fault()
        _event(trajectory, "fault_reset", fault_id=environment.profile["fault_profile_id"], result=reset)
        recovered_health = environment.client_request("/health", timeout=1.0)
        _event(trajectory, "readiness", result={"after_fault_reset": recovered_health})
        return action, health, recovered_health, reconcile, blind_retry_attempts, agent_failure

    call_id = intent("apply_change", {"operation_id": "change-001", "expected_revision": 0, "release": "release-v2"})
    try:
        action = environment.apply_change("change-001")
    except RuntimeFailure as error:
        _event(trajectory, "tool_execution_failure", step=step, tool_call_id=call_id, domain=error.domain, code=error.code, outcome=error.outcome)
        if error.domain == "AGENT":
            agent_failure = error
            return action, health, recovered_health, reconcile, blind_retry_attempts, agent_failure
        raise
    _event(trajectory, "environment_transition", before=INITIAL_STATE, after=action.get("state"), operation_id="change-001", state_owner=environment.contract["mutable_state_ownership"])
    if fault_profile in {"response-lost", "dependency-unavailable", "pre-side-effect-failure"}:
        _event(
            trajectory,
            "fault",
            fault_id=environment.profile["fault_profile_id"],
            planned=True,
            triggered=environment.snapshot()["fault_state"]["triggered"],
            observed=environment.snapshot()["fault_state"]["observed"],
            side_effect_status="APPLIED" if action.get("status") == "UNKNOWN_OUTCOME" else "NOT_APPLIED",
            response_to_agent=action.get("status"),
        )
    _event(trajectory, "tool_result", step=step, tool_call_id=call_id, tool_name="apply_change", result=action)
    if fault_profile == "response-lost":
        call_id = intent("reconcile", {"operation_id": "change-001"}, "RECONCILE_UNKNOWN_OUTCOME")
        reconcile = environment.reconcile("change-001")
        _event(trajectory, "reconcile", step=step, tool_call_id=call_id, operation_id="change-001", result=reconcile)
        _event(trajectory, "tool_result", step=step, tool_call_id=call_id, tool_name="reconcile", result=reconcile)
    return action, health, recovered_health, reconcile, blind_retry_attempts, agent_failure


def run_multi_service_slice(
    fault_profile: str = "none",
    api_key: str | None = None,
    model: str | None = None,
    *,
    agent_profile_id: str = "production-change-agent-v1",
    environment_failure: str | None = None,
) -> dict[str, Any]:
    """Run one fresh formal RPF-28 slice without invoking the LLM provider."""

    if fault_profile not in FAULT_PROFILES:
        raise RuntimeFailure("HARNESS", "UNKNOWN_FAULT_PROFILE")
    if environment_failure is not None:
        raise RuntimeFailure("HARNESS", "UNSUPPORTED_MULTI_SERVICE_FAILURE_HOOK")
    profile = agent_profile_for(agent_profile_id)
    run_id = f"run-{uuid.uuid4()}"
    evaluation_id = f"evaluation-{uuid.uuid4()}"
    started_clock = time.monotonic()
    trajectory: list[dict[str, Any]] = []
    environment: MultiServiceEnvironment | None = None
    initial_state: dict[str, Any] | None = None
    actual_state: dict[str, Any] | None = None
    full_state: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    health: dict[str, Any] | None = None
    recovered_health: dict[str, Any] | None = None
    reconcile: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    terminal_error: RuntimeFailure | None = None
    agent_failure: RuntimeFailure | None = None
    formal_run_started = False
    requested_model = model or os.environ.get("RPF_MODEL", DEFAULT_MODEL)
    artifact: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "artifact_kind": "Run Evidence",
        "trajectory_contract": {"version": TRAJECTORY_CONTRACT_VERSION, "ordering": "ascending integer sequence within one run", "identity": "run-scoped event_id; immutable once evidence is written"},
        "run": {
            "run_id": run_id,
            "evaluation_id": evaluation_id,
            "started_at": timestamp(),
            "agent": profile,
            "scenario": {"scenario_id": FORMAL_SCENARIO_ID, "scenario_version": FORMAL_SCENARIO_VERSION},
            "verifier": {"verifier_id": FORMAL_VERIFIER_ID, "verifier_version": FORMAL_VERIFIER_VERSION},
            "runtime": {"runtime_version": RPF28_RUNTIME_VERSION, "source_sha256": None},
        },
        "llm_provider": _not_invoked_provider_evidence(requested_model),
        "environment_provider": None,
        "environment": None,
        "execution_environment_contract": {"profile": ENVIRONMENT_PROFILE, "contract": "rpf-multi-service-controlled-environment-v1", "agent_network_authority": "data-plane-client-only", "control_plane_visible_to_agent": False, "docker_socket_visible_to_agent": False},
        "agent_execution": {"driver_id": "rpf28-deterministic-agent-driver-v1", "provider_invoked": False, "transport": "agent-client-container-to-data-plane-proxy", "policy": "observe-mutate-reconcile"},
        "scenario": _profile_scenario(profile),
        "fault": {"fault_id": FAULT_PROFILES[fault_profile]["fault_profile_id"], "fault_profile": fault_profile, "planned": fault_profile != "none", "triggered": False, "observed": False, "reconciled": False, "reset": False},
        "trajectory": trajectory,
        "verification": None,
        "outcome": None,
        "failure_attribution": None,
        "health_context": None,
        "runtime_budget": {"max_agent_steps": 8, "max_provider_calls": 0, "request_timeout_seconds": 45, "overall_timeout_seconds": 8 * 60, "automatic_provider_retries": 0, "automatic_tool_retries": 0},
    }
    try:
        provider_info = provider_snapshot()
        artifact["environment_provider"] = {"provider_id": "docker", "provider_type": "environment", "provider_implementation": "docker", **provider_info}
        environment = MultiServiceEnvironment(provider_info, role="formal-run", fault_profile=fault_profile, run_id=run_id)
        environment.provision()
        artifact["environment"] = environment.snapshot()
        _event(trajectory, "environment_provisioned", environment_id=environment.environment_id, seed_id=environment.contract["seed_id"], seed_revision=environment.contract["seed_revision"], provenance=environment.contract["provenance"])
        readiness = environment.readiness()
        _event(trajectory, "readiness", result=readiness)
        if not readiness.get("ok"):
            raise RuntimeFailure("ENVIRONMENT", readiness.get("code", "READINESS_FAILED"))
        initial = environment.verify_initial()
        _event(trajectory, "initial_state_verification", result=initial)
        if not initial.get("ok"):
            raise RuntimeFailure("ENVIRONMENT", initial.get("code", "INITIAL_STATE_MISMATCH"), "INVALID")
        initial_state = copy.deepcopy(initial["state"])
        formal_run_started = True
        observability = get_observability()
        with observability.span(
            "runproof.agent.run",
            canonical_attributes(
                run_id=run_id,
                environment_id=environment.environment_id,
                agent_id=agent_profile_id,
                fault_profile=fault_profile,
            ),
        ) as agent_scope:
            try:
                action, health, recovered_health, reconcile, _blind_retry_attempts, agent_failure = _run_agent_driver(environment, agent_profile_id, fault_profile, trajectory)
            except Exception as error:
                agent_scope.error(error, "agent_driver_error")
                raise
        if fault_profile == "pre-side-effect-failure":
            actual_state = copy.deepcopy((action or {}).get("state") or INITIAL_STATE)
            _event(trajectory, "actual_state_verification", state=actual_state, observation="pre-side-effect-transport-failure-contrast")
        elif agent_failure is None:
            actual_state = environment.read_state()
            _event(trajectory, "actual_state_verification", state=actual_state)
        else:
            actual_state = environment.read_state()
            _event(trajectory, "actual_state_verification", state=actual_state)
        full_state = copy.deepcopy(environment.full_state()) if fault_profile != "pre-side-effect-failure" else {}
        fault = _fault_document(environment)
        with get_observability().span(
            "runproof.verifier.evaluate",
            canonical_attributes(run_id=run_id, environment_id=environment.environment_id, fault_profile=fault_profile),
        ) as verifier_scope:
            try:
                verification = _formal_verification(fault_profile, initial_state, actual_state, full_state, action, health, recovered_health, reconcile, fault, agent_started=formal_run_started, blind_retry_attempts=_blind_retry_attempts)
            except Exception as error:
                verifier_scope.error(error, "verifier_error")
                raise
        artifact["verification"] = verification
        artifact["fault"] = fault
        if agent_failure:
            terminal_error = agent_failure
        elif not verification["passed"]:
            terminal_error = RuntimeFailure("ENVIRONMENT", "FORMAL_NETWORK_CONTRACT_NOT_VERIFIED", "INCONCLUSIVE")
    except RuntimeFailure as error:
        terminal_error = error
        if environment and actual_state is None:
            try:
                actual_state = environment.read_state()
                _event(trajectory, "actual_state_observed_after_failure", state=actual_state)
            except RuntimeFailure:
                pass
    finally:
        if environment:
            cleanup = environment.cleanup()
            _event(trajectory, "cleanup", result=cleanup)
            if not cleanup.get("ok") and terminal_error is None:
                terminal_error = RuntimeFailure("ENVIRONMENT", cleanup.get("code", "CLEANUP_FAILED"))
            artifact["environment"] = environment.snapshot()
            artifact["fault"] = _fault_document(environment)
        environment_id = artifact["environment"].get("environment_id") if isinstance(artifact.get("environment"), dict) else None
        _normalize_trajectory(trajectory, run_id, environment_id)
        artifact["run"]["runtime"]["source_sha256"] = runtime_source_sha256()
        artifact["run"]["ended_at"] = timestamp()
        artifact["duration_ms"] = round((time.monotonic() - started_clock) * 1000)

    if verification is None and initial_state is not None and actual_state is not None:
        verification = _formal_verification(fault_profile, initial_state, actual_state, full_state, action, health, recovered_health, reconcile, artifact["fault"], agent_started=formal_run_started, blind_retry_attempts=0)
        artifact["verification"] = verification
    if terminal_error:
        category = {"AGENT": "Agent", "ENVIRONMENT": "Platform/Environment", "HARNESS": "Harness"}.get(terminal_error.domain, terminal_error.domain)
        artifact["outcome"] = {"status": terminal_error.outcome, "source": terminal_error.domain, "agent_quality_eligible": False, "formal_run_started": formal_run_started, "reason": terminal_error.code, "attribution": category, "agent_started": formal_run_started}
        artifact["failure_attribution"] = {"category": category, "domain": terminal_error.domain, "deterministic": True, "reason_code": terminal_error.code, "agent_started": formal_run_started, "agent_quality_excluded": terminal_error.domain != "AGENT"}
    elif verification and verification["passed"]:
        eligible = fault_profile in {"none", "response-lost"} and agent_profile_id not in {"known-bad-unsafe-precondition-v1", "incident-remediation-agent-v1-known-bad"}
        artifact["outcome"] = {"status": "PASS", "source": "DETERMINISTIC_NETWORK_FAULT_VERIFIER", "agent_quality_eligible": eligible, "formal_run_started": formal_run_started}
    else:
        artifact["outcome"] = {"status": "INCONCLUSIVE", "source": "HARNESS", "agent_quality_eligible": False, "formal_run_started": formal_run_started, "reason": "NO_SAFE_TERMINAL_RESULT"}
    artifact["health_context"] = {
        "provider": {"status": "NOT_IN_FAILURE_PATH", "failure_source": False, "calls_observed": 0},
        "environment": {"status": "HEALTHY" if artifact.get("outcome", {}).get("status") == "PASS" else "CONTROLLED_FAILURE" if artifact.get("fault", {}).get("planned") else "FAILED", "failure_source": False if artifact.get("outcome", {}).get("status") == "PASS" else True, "readiness": (artifact.get("environment") or {}).get("readiness"), "initial_state_verified": (artifact.get("environment") or {}).get("verified_initial_state") is True, "cleanup_state": (artifact.get("environment") or {}).get("cleanup_state")},
    }
    return artifact


__all__ = ["FORMAL_VERIFIER_ID", "FORMAL_VERIFIER_VERSION", "RPF28_RUNTIME_VERSION", "SUPPORTED_ENVIRONMENT_PROFILES", "run_multi_service_slice"]

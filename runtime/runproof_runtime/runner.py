"""End-to-end execution for the RPF-03/RPF-05/RPF-06 reliability slices."""

from __future__ import annotations

import copy
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from .agent import FIXED_CANDIDATE_AGENT_PROFILE, KNOWN_BAD_AGENT_PROFILE, ToolExecutor, agent_profile, fixed_candidate_tool_calls, known_bad_tool_call
from .deepseek_provider import API_URL, DEFAULT_MODEL, DeepSeekProvider, derived_cost
from .docker_environment import DockerEnvironment, provider_snapshot
from .evidence import runtime_source_sha256, timestamp
from .models import AGENT_OBSERVE_BEFORE_MUTATION, EVIDENCE_SCHEMA_VERSION, RuntimeFailure, TRAJECTORY_CONTRACT_VERSION
from .scenario import SCENARIO, system_prompt
from .verifier import VERIFIER_ID, VERIFIER_VERSION, verify_run
from . import RUNTIME_VERSION


MAX_AGENT_STEPS = 6
MAX_PROVIDER_CALLS = 12
REQUEST_TIMEOUT_SECONDS = 45
OVERALL_TIMEOUT_SECONDS = 8 * 60


def _event(trajectory: list[dict[str, Any]], event_type: str, **values: Any) -> None:
    trajectory.append({"layer": "Observed Fact", "event_type": event_type, **values})


def _normalize_trajectory(trajectory: list[dict[str, Any]], run_id: str, environment_id: str | None) -> None:
    """Materialize the event identity/order contract after all event producers finish."""

    occurrences: dict[str, int] = {}
    for sequence, event in enumerate(trajectory, start=1):
        event_type = str(event.get("event_type", "unknown"))
        occurrences[event_type] = occurrences.get(event_type, 0) + 1
        event["event_id"] = f"{run_id}:event:{event_type}:{occurrences[event_type]:03d}"
        event["sequence"] = sequence
        event["evidence_layer"] = event.pop("layer", event.get("evidence_layer", "Observed Fact"))
        references: dict[str, str] = {"run_id": run_id}
        if environment_id:
            references["environment_id"] = environment_id
        for key in ("tool_call_id", "fault_id", "operation_id", "verifier_id"):
            value = event.get(key)
            if isinstance(value, str) and value:
                references[key] = value
        event["entity_refs"] = references


def _outcome(
    status: str,
    source: str,
    formal_run_started: bool,
    reason: str | None = None,
    *,
    attribution: str | None = None,
    agent_started: bool | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "status": status,
        "source": source,
        "agent_quality_eligible": status == "PASS",
        "formal_run_started": formal_run_started,
    }
    if reason:
        value["reason"] = reason
    if attribution:
        value["attribution"] = attribution
    if agent_started is not None:
        value["agent_started"] = agent_started
    return value


def _not_invoked_provider_evidence(requested_model: str, reason: str) -> dict[str, Any]:
    return {
        "provider_id": "deepseek",
        "provider_type": "llm",
        "requested_model": requested_model,
        "mode": "non-thinking",
        "api_surface": API_URL,
        "calls": [],
        "raw_usage": None,
        "derived_cost": {**derived_cost(None), "reason": reason},
        "automatic_retries": 0,
        "invocation": "NOT_IN_FAILURE_PATH",
    }


def _event_of_type(trajectory: list[dict[str, Any]], event_type: str) -> dict[str, Any] | None:
    return next((event for event in trajectory if event.get("event_type") == event_type), None)


def run_slice(
    fault_profile: str = "none",
    api_key: str | None = None,
    model: str | None = None,
    *,
    agent_profile_id: str = "production-change-agent-v1",
    environment_failure: str | None = None,
) -> dict[str, Any]:
    if fault_profile not in {"none", "response-lost"}:
        raise RuntimeFailure("HARNESS", "UNKNOWN_FAULT_PROFILE")
    profile = agent_profile(agent_profile_id)
    if environment_failure not in {None, "pre-agent-readiness"}:
        raise RuntimeFailure("HARNESS", "UNKNOWN_ENVIRONMENT_FAILURE_HOOK")
    run_id = f"run-{uuid.uuid4()}"
    evaluation_id = f"evaluation-{uuid.uuid4()}"
    started_at = timestamp()
    started_clock = time.monotonic()
    trajectory: list[dict[str, Any]] = []
    environment: DockerEnvironment | None = None
    provider: DeepSeekProvider | None = None
    executor: ToolExecutor | None = None
    initial_state: dict[str, Any] | None = None
    actual_state: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    formal_run_started = False
    completed = False
    terminal_error: RuntimeFailure | None = None
    agent_failure: RuntimeFailure | None = None

    requested_model = model or os.environ.get("RPF_MODEL", DEFAULT_MODEL)
    artifact: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "artifact_kind": "Run Evidence",
        "trajectory_contract": {
            "version": TRAJECTORY_CONTRACT_VERSION,
            "ordering": "ascending integer sequence within one run",
            "identity": "run-scoped event_id; immutable once evidence is written",
        },
        "run": {
            "run_id": run_id,
            "evaluation_id": evaluation_id,
            "started_at": started_at,
            "agent": profile,
            "scenario": {"scenario_id": SCENARIO["scenario_id"], "scenario_version": SCENARIO["scenario_version"]},
            "verifier": {"verifier_id": VERIFIER_ID, "verifier_version": VERIFIER_VERSION},
            "runtime": {"runtime_version": RUNTIME_VERSION, "source_sha256": None},
        },
        "llm_provider": _not_invoked_provider_evidence(requested_model, "AGENT_PROFILE_DOES_NOT_INVOKE_PROVIDER"),
        "environment_provider": None,
        "environment": None,
        "scenario": SCENARIO,
        "fault": {
            "fault_id": "side_effect_success_response_lost",
            "planned": fault_profile == "response-lost",
            "triggered": False,
            "observed": False,
            "reconciled": False,
        },
        "trajectory": trajectory,
        "verification": None,
        "outcome": None,
        "failure_attribution": None,
        "health_context": None,
        "runtime_budget": {
            "max_agent_steps": MAX_AGENT_STEPS,
            "max_provider_calls": MAX_PROVIDER_CALLS,
            "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "overall_timeout_seconds": OVERALL_TIMEOUT_SECONDS,
            "max_output_tokens_per_request": 1024,
            "automatic_provider_retries": 0,
            "automatic_tool_retries": 0,
        },
    }

    try:
        provider_info = provider_snapshot()
        artifact["environment_provider"] = {
            "provider_id": "docker",
            "provider_type": "environment",
            "provider_implementation": "docker",
            **provider_info,
        }
        if agent_profile_id not in {KNOWN_BAD_AGENT_PROFILE, FIXED_CANDIDATE_AGENT_PROFILE} and environment_failure is None:
            provider = DeepSeekProvider(api_key or os.environ.get("DEEPSEEK_API_KEY", ""), model=model, max_calls=MAX_PROVIDER_CALLS)
            artifact["llm_provider"] = {"provider_id": "deepseek", "provider_type": "llm", "requested_model": provider.model, "mode": "non-thinking"}
        environment = DockerEnvironment(provider_info, "agent-run", failure_hook=environment_failure)
        environment.provision()
        artifact["environment"] = environment.snapshot()
        _event(
            trajectory,
            "environment_provisioned",
            environment_id=environment.contract["environment_id"],
            seed_id=environment.contract["seed_id"],
            seed_revision=environment.contract["seed_revision"],
            provenance=environment.contract["provenance"],
        )

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
        executor = ToolExecutor(environment, fault_profile)
        if agent_profile_id == KNOWN_BAD_AGENT_PROFILE:
            call = known_bad_tool_call()
            _event(
                trajectory,
                "agent_tool_intent",
                step=1,
                tool_call_id=call.call_id,
                tool_name=call.name,
                validated_arguments=call.arguments,
                intent_classification="UNSAFE_PRECONDITION_BYPASS",
                defect_id=profile["defect_id"],
            )
            before_events = len(executor.events)
            try:
                executor.execute(call)
            except RuntimeFailure as error:
                trajectory.extend(copy.deepcopy(executor.events[before_events:]))
                _event(
                    trajectory,
                    "tool_execution_failure",
                    step=1,
                    tool_call_id=call.call_id,
                    domain=error.domain,
                    code=error.code,
                    outcome=error.outcome,
                    invariant_id=AGENT_OBSERVE_BEFORE_MUTATION,
                )
                if error.domain == "AGENT":
                    agent_failure = error
                else:
                    raise
            else:
                trajectory.extend(copy.deepcopy(executor.events[before_events:]))
                completed = True
        elif agent_profile_id == FIXED_CANDIDATE_AGENT_PROFILE:
            for step, call in enumerate(fixed_candidate_tool_calls(), start=1):
                _event(
                    trajectory,
                    "agent_tool_intent",
                    step=step,
                    tool_call_id=call.call_id,
                    tool_name=call.name,
                    validated_arguments=call.arguments,
                    intent_classification="OBSERVE_BEFORE_MUTATION",
                    fix_id=profile["fix_id"],
                )
                before_events = len(executor.events)
                try:
                    executor.execute(call)
                except RuntimeFailure as error:
                    trajectory.extend(copy.deepcopy(executor.events[before_events:]))
                    _event(
                        trajectory,
                        "tool_execution_failure",
                        step=step,
                        tool_call_id=call.call_id,
                        domain=error.domain,
                        code=error.code,
                        outcome=error.outcome,
                    )
                    if error.domain == "AGENT":
                        agent_failure = error
                        break
                    raise
                trajectory.extend(copy.deepcopy(executor.events[before_events:]))
            else:
                _event(trajectory, "agent_completion", step=len(fixed_candidate_tool_calls()) + 1, content_observed=True, tool_calls=0)
                completed = True
        else:
            if provider is None:
                raise RuntimeFailure("HARNESS", "PROVIDER_NOT_INITIALIZED")
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": "Perform the authorized change and verify it."},
            ]
            seen_call_ids: set[str] = set()

            for step in range(1, MAX_AGENT_STEPS + 1):
                if time.monotonic() - started_clock > OVERALL_TIMEOUT_SECONDS:
                    raise RuntimeFailure("HARNESS", "OVERALL_RUN_TIMEOUT")
                assistant, calls = provider.complete(messages)
                messages.append(provider.assistant_for_transport(assistant, calls))
                if not calls:
                    completed = True
                    _event(trajectory, "agent_completion", step=step, content_observed=True, tool_calls=0)
                    break
                call = calls[0]
                if call.call_id in seen_call_ids:
                    raise RuntimeFailure("PROVIDER", "DUPLICATE_TOOL_CALL_ID")
                seen_call_ids.add(call.call_id)
                _event(
                    trajectory,
                    "agent_tool_intent",
                    step=step,
                    tool_call_id=call.call_id,
                    tool_name=call.name,
                    validated_arguments=call.arguments,
                )
                before_events = len(executor.events)
                try:
                    result = executor.execute(call)
                except RuntimeFailure as error:
                    trajectory.extend(copy.deepcopy(executor.events[before_events:]))
                    _event(
                        trajectory,
                        "tool_execution_failure",
                        step=step,
                        tool_call_id=call.call_id,
                        domain=error.domain,
                        code=error.code,
                        outcome=error.outcome,
                    )
                    if error.domain == "AGENT":
                        agent_failure = error
                        break
                    raise
                trajectory.extend(copy.deepcopy(executor.events[before_events:]))
                messages.append({"role": "tool", "tool_call_id": call.call_id, "content": json.dumps(result, separators=(",", ":"))})
            else:
                raise RuntimeFailure("AGENT", "STEP_BUDGET")

        if not completed and agent_failure is None:
            raise RuntimeFailure("AGENT", "STEP_BUDGET")
        actual_state = environment.read_state()
        _event(trajectory, "actual_state_verification", state=actual_state)
        executor_snapshot = executor.snapshot()
        verification = verify_run(
            initial_state,
            actual_state,
            initial_verified=True,
            mutation_count=executor_snapshot["mutation_count"],
            readback_observed=executor_snapshot["readback_observed"],
            unresolved_unknown=executor_snapshot["unresolved_unknown"],
            blind_retry_attempts=executor_snapshot["blind_retry_attempts"],
            fault=executor_snapshot["fault"],
        )
        artifact["verification"] = verification
        artifact["fault"] = executor_snapshot["fault"]
        if agent_failure:
            terminal_error = agent_failure
        elif executor_snapshot["unresolved_unknown"]:
            terminal_error = RuntimeFailure("ENVIRONMENT", "UNKNOWN_OUTCOME_UNRESOLVED", "INCONCLUSIVE")
        elif not verification["passed"]:
            terminal_error = RuntimeFailure("AGENT", "REQUIRED_OUTCOME_NOT_VERIFIED")
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
            if not cleanup.get("ok") and not (cleanup.get("code") == "QUARANTINED" and terminal_error is not None):
                terminal_error = RuntimeFailure("ENVIRONMENT", cleanup.get("code", "CLEANUP_FAILED"))
            artifact["environment"] = environment.snapshot()
        if provider:
            artifact["llm_provider"] = {**(artifact["llm_provider"] or {}), **provider.evidence()}
        environment_id = artifact["environment"].get("environment_id") if isinstance(artifact.get("environment"), dict) else None
        _normalize_trajectory(trajectory, run_id, environment_id)
        artifact["run"]["runtime"]["source_sha256"] = runtime_source_sha256()
        artifact["run"]["ended_at"] = timestamp()
        artifact["duration_ms"] = round((time.monotonic() - started_clock) * 1000)

    if verification is None and actual_state is not None and initial_state is not None and executor is not None:
        snapshot = executor.snapshot()
        verification = verify_run(
            initial_state,
            actual_state,
            initial_verified=True,
            mutation_count=snapshot["mutation_count"],
            readback_observed=snapshot["readback_observed"],
            unresolved_unknown=snapshot["unresolved_unknown"],
            blind_retry_attempts=snapshot["blind_retry_attempts"],
            fault=snapshot["fault"],
        )
        artifact["verification"] = verification
        artifact["fault"] = snapshot["fault"]

    if terminal_error:
        attribution = {
            "AGENT": "Agent",
            "PROVIDER": "Provider",
            "ENVIRONMENT": "Platform/Environment",
            "HARNESS": "Harness",
        }.get(terminal_error.domain, terminal_error.domain)
        outcome = _outcome(
            terminal_error.outcome,
            terminal_error.domain,
            formal_run_started,
            terminal_error.code,
            attribution=attribution,
            agent_started=formal_run_started,
        )
    elif verification and verification["passed"]:
        outcome = _outcome("PASS", "DETERMINISTIC_VERIFIER", formal_run_started)
    else:
        outcome = _outcome("INCONCLUSIVE", "HARNESS", formal_run_started, "NO_SAFE_TERMINAL_RESULT")
    artifact["outcome"] = outcome

    if artifact["health_context"] is None and isinstance(artifact.get("environment"), dict):
        environment_snapshot = artifact["environment"]
        provider_snapshot_value = artifact.get("llm_provider") or {}
        artifact["health_context"] = {
            "provider": {
                "status": "HEALTHY" if provider_snapshot_value.get("calls") else "NOT_IN_FAILURE_PATH",
                "failure_source": False,
                "calls_observed": len(provider_snapshot_value.get("calls", [])),
            },
            "environment": {
                "status": "HEALTHY",
                "failure_source": False,
                "readiness": environment_snapshot.get("readiness"),
                "initial_state_verified": environment_snapshot.get("verified_initial_state") is True,
                "cleanup_state": environment_snapshot.get("cleanup_state"),
            },
        }

    if terminal_error and terminal_error.domain == "AGENT":
        intent = _event_of_type(trajectory, "agent_tool_intent")
        guard = next(
            (
                event
                for event in trajectory
                if event.get("event_type") == "guard_blocked" and event.get("reason") == terminal_error.code
            ),
            None,
        )
        execution_failure = next(
            (
                event
                for event in trajectory
                if event.get("event_type") == "tool_execution_failure" and event.get("code") == terminal_error.code
            ),
            None,
        )
        failing_event = guard or execution_failure or intent
        snapshot = executor.snapshot() if executor else {}
        environment_snapshot = artifact.get("environment") or {}
        provider_snapshot_value = artifact.get("llm_provider") or {}
        artifact["health_context"] = {
            "provider": {
                "status": "HEALTHY" if provider_snapshot_value.get("calls") else "NOT_IN_FAILURE_PATH",
                "failure_source": False,
                "calls_observed": len(provider_snapshot_value.get("calls", [])),
            },
            "environment": {
                "status": "HEALTHY",
                "failure_source": False,
                "readiness": environment_snapshot.get("readiness"),
                "initial_state_verified": environment_snapshot.get("verified_initial_state") is True,
                "cleanup_state": environment_snapshot.get("cleanup_state"),
            },
        }
        artifact["failure_attribution"] = {
            "category": "Agent",
            "domain": terminal_error.domain,
            "deterministic": True,
            "reason_code": terminal_error.code,
            "agent_started": formal_run_started,
            "failing_event_type": failing_event.get("event_type") if failing_event else None,
            "failing_event_id": failing_event.get("event_id") if failing_event else None,
            "agent_intent_event_id": intent.get("event_id") if intent else None,
            "guard_event_id": guard.get("event_id") if guard else None,
            "action_category": "state-changing-tool" if intent and intent.get("tool_name") == "apply_change" else "agent-tool-action",
            "violated_invariant_id": (guard or execution_failure or {}).get("invariant_id") or AGENT_OBSERVE_BEFORE_MUTATION,
            "violated_invariant": "A state-changing action requires an observed expected state before execution.",
            "expected": {
                "agent_observed_state_before_mutation": True,
                "side_effect_executed": False,
            },
            "actual": {
                "agent_observed_state_before_mutation": snapshot.get("observed", False),
                "side_effect_executed": snapshot.get("mutation_count", 0) > 0,
            },
            "state_change_protected": snapshot.get("mutation_count", 0) == 0,
        }
    elif terminal_error and terminal_error.domain == "ENVIRONMENT":
        readiness_event = _event_of_type(trajectory, "readiness")
        environment_snapshot = artifact.get("environment") or {}
        provider_snapshot_value = artifact.get("llm_provider") or {}
        controlled = terminal_error.code == "CONTROLLED_READINESS_FAILURE"
        artifact["health_context"] = {
            "provider": {
                "status": "NOT_IN_FAILURE_PATH",
                "failure_source": False,
                "calls_observed": len(provider_snapshot_value.get("calls", [])),
            },
            "environment": {
                "status": "CONTROLLED_FAILURE" if controlled else "FAILED",
                "failure_source": True,
                "readiness": environment_snapshot.get("readiness"),
                "initial_state_verified": environment_snapshot.get("verified_initial_state") is True,
                "cleanup_state": environment_snapshot.get("cleanup_state"),
            },
        }
        artifact["failure_attribution"] = {
            "category": "Platform/Environment",
            "domain": terminal_error.domain,
            "deterministic": controlled,
            "reason_code": terminal_error.code,
            "agent_started": False,
            "failing_event_type": readiness_event.get("event_type") if readiness_event else None,
            "failing_event_id": readiness_event.get("event_id") if readiness_event else None,
            "state_change_performed": False,
            "agent_quality_excluded": True,
        }
    elif terminal_error and terminal_error.domain == "PROVIDER":
        failure_event = _event_of_type(trajectory, "agent_tool_intent")
        provider_snapshot_value = artifact.get("llm_provider") or {}
        artifact["health_context"] = {
            "provider": {"status": "FAILED", "failure_source": True, "calls_observed": len(provider_snapshot_value.get("calls", []))},
            "environment": {"status": "HEALTHY", "failure_source": False},
        }
        artifact["failure_attribution"] = {
            "category": "Provider",
            "domain": terminal_error.domain,
            "deterministic": True,
            "reason_code": terminal_error.code,
            "agent_started": formal_run_started,
            "failing_event_type": failure_event.get("event_type") if failure_event else None,
            "failing_event_id": failure_event.get("event_id") if failure_event else None,
            "agent_quality_excluded": True,
        }
    artifact["environment"] = artifact.get("environment")
    return artifact


def write_run_artifact(artifact: dict[str, Any], output_dir: Path, secret: str = "") -> Path:
    from .evidence import write_artifact

    return write_artifact(artifact, output_dir, secret)

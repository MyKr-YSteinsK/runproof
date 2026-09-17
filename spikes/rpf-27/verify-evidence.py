"""Offline verifier for the ignored RPF-27 candidate evidence.

This verifier does not promote the result to a reviewed Run artifact or
register it in the Control Plane.  It checks the disposable spike's own
identity, transport proof, authority boundary, and cleanup claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULT = ROOT / ".local" / "rpf-27" / "result.json"
PROBE = ROOT / "spikes" / "rpf-27" / "probe.py"
VERIFIER = ROOT / "spikes" / "rpf-27" / "verify-evidence.py"
REQUIRED_CANDIDATES = {"toxiproxy", "custom-shim"}
REQUIRED_SCENARIOS = {"baseline", "latency-timeout", "dependency-unavailable", "response-lost"}
SECRET_PATTERN = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+\S+)")


class VerificationError(RuntimeError):
    pass


def source_sha256() -> str:
    digest = hashlib.sha256()
    for path in (PROBE, VERIFIER):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def require(condition: bool, code: str) -> None:
    if not condition:
        raise VerificationError(code)


def verify_trial(trial: dict[str, Any], scenario: str) -> None:
    require(trial.get("scenario") == scenario, f"SCENARIO_MISMATCH:{scenario}")
    require(trial.get("status") == "PASS", f"TRIAL_NOT_PASS:{scenario}")
    require(trial.get("outcome", {}).get("classification") == "SCENARIO_PASS", f"OUTCOME_CLASSIFICATION:{scenario}")
    require(trial.get("cleanup", {}).get("ok") is True, f"CLEANUP_FAILED:{scenario}")
    environment = trial.get("environment", {})
    require(environment.get("environment_contract") == "rpf-27-multi-service-network-environment-v1", f"ENVIRONMENT_CONTRACT:{scenario}")
    require(environment.get("readiness", {}).get("services_ready") is True, f"SERVICES_NOT_READY:{scenario}")
    require(environment.get("readiness", {}).get("initial_state_checked") is True, f"INITIAL_STATE_NOT_CHECKED:{scenario}")
    require(environment.get("seed", {}).get("mutable_state_fresh") is True, f"STATE_NOT_FRESH:{scenario}")
    require(environment.get("network", {}).get("container_count") == 4, f"TOPOLOGY_CONTAINER_COUNT:{scenario}")
    require(environment.get("network", {}).get("internal") is True, f"NETWORK_NOT_INTERNAL:{scenario}")
    require(environment.get("resource_scope", {}).get("volume_count") == 0, f"UNEXPECTED_VOLUME:{scenario}")
    require(environment.get("resource_scope", {}).get("host_docker_socket_mounted") is False, f"DOCKER_SOCKET_EXPOSED:{scenario}")
    require(trial.get("initial_state", {}).get("effect_count") == 0, f"INITIAL_EFFECT_COUNT:{scenario}")

    fault = trial.get("fault", {})
    if scenario == "baseline":
        require(fault.get("planned") is False and fault.get("triggered") is False and fault.get("observed") is False, "BASELINE_FAULT_FLAGS")
        require(trial.get("actual_state", {}).get("effect_count") == 1, "BASELINE_EFFECT_COUNT")
        require(trial.get("target_mutation_requests") == 1, "BASELINE_MUTATION_REQUESTS")
        require(trial.get("target_duplicate_operation_requests") == 0, "BASELINE_DUPLICATE_REQUESTS")
    elif scenario == "latency-timeout":
        require(fault.get("planned") is True and fault.get("triggered") is True and fault.get("observed") is True, "TIMEOUT_FAULT_FLAGS")
        require(trial.get("client", {}).get("result", {}).get("faulted_request", {}).get("status") != 200, "TIMEOUT_NOT_OBSERVED")
        require(trial.get("client", {}).get("result", {}).get("post_fault_health", {}).get("status") == 200, "TIMEOUT_RECOVERY")
        require(trial.get("actual_state", {}).get("effect_count") == 0, "TIMEOUT_SIDE_EFFECT")
    elif scenario == "dependency-unavailable":
        require(fault.get("planned") is True and fault.get("triggered") is True and fault.get("observed") is True, "DEPENDENCY_FAULT_FLAGS")
        dependency_request = trial.get("client", {}).get("result", {}).get("mutation", {})
        require(dependency_request.get("status") == 503 or dependency_request.get("transport_ok") is False, "DEPENDENCY_FAILURE_NOT_OBSERVED")
        require(trial.get("actual_state", {}).get("last_dependency_result") == "UNAVAILABLE", "DEPENDENCY_OBSERVATION_MISSING")
        require(trial.get("actual_state", {}).get("effect_count") == 0, "DEPENDENCY_SIDE_EFFECT")
        require(trial.get("actual_state", {}).get("receipts") == {}, "DEPENDENCY_RECEIPT_PRESENT")
    elif scenario == "response-lost":
        require(fault.get("fault_id") == "side_effect_success_response_lost", "RESPONSE_LOST_FAULT_ID")
        require(fault.get("planned") is True and fault.get("triggered") is True and fault.get("observed") is True and fault.get("reconciled") is True, "RESPONSE_LOST_FAULT_FLAGS")
        require(trial.get("client", {}).get("attempt_count") == 1, "RESPONSE_LOST_CLIENT_RETRY")
        require(trial.get("client", {}).get("blind_retry_attempts") == 0, "RESPONSE_LOST_BLIND_RETRY")
        require(trial.get("client", {}).get("result", {}).get("mutation", {}).get("transport_ok") is False, "RESPONSE_LOST_NOT_TRANSPORT_FAILURE")
        require(trial.get("response_transport_proof", {}).get("target_committed_before_client_failure") is True, "RESPONSE_LOST_COMMIT_ORDER")
        require(trial.get("response_transport_proof", {}).get("response_delivered_to_client") is False, "RESPONSE_LOST_RESPONSE_DELIVERED")
        require(trial.get("response_transport_proof", {}).get("business_returned_unknown_outcome_fixture") is False, "RESPONSE_LOST_BUSINESS_FIXTURE")
        require(trial.get("response_transport_proof", {}).get("transport_boundary") == "server-to-client", "RESPONSE_LOST_DIRECTION")
        require(trial.get("actual_state", {}).get("effect_count") == 1, "RESPONSE_LOST_EFFECT_COUNT")
        require(trial.get("target_mutation_requests") == 1, "RESPONSE_LOST_MUTATION_REQUESTS")
        require(trial.get("target_duplicate_operation_requests") == 0, "RESPONSE_LOST_DUPLICATE_REQUESTS")
        require(trial.get("reconcile", {}).get("status") == 200, "RESPONSE_LOST_RECONCILE_HTTP")
        require(trial.get("reconcile", {}).get("body", {}).get("status") == "APPLIED", "RESPONSE_LOST_RECONCILE_STATUS")
        require(trial.get("reconcile", {}).get("body", {}).get("effect_count") == 1, "RESPONSE_LOST_RECONCILE_EFFECT_COUNT")


def verify_candidate(candidate: str, value: dict[str, Any]) -> int:
    trials = value.get("scenario_trials")
    require(isinstance(trials, list), f"TRIALS_MISSING:{candidate}")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trial in trials:
        grouped.setdefault(trial.get("scenario", ""), []).append(trial)
    require(REQUIRED_SCENARIOS.issubset(grouped), f"SCENARIOS_MISSING:{candidate}")
    for scenario in ("baseline", "latency-timeout", "dependency-unavailable"):
        require(len(grouped[scenario]) == 1, f"SCENARIO_REPEAT_SHAPE:{candidate}:{scenario}")
        verify_trial(grouped[scenario][0], scenario)
    response_trials = grouped["response-lost"]
    require(len(response_trials) >= 3, f"RESPONSE_LOST_REPEAT_COUNT:{candidate}")
    for trial in response_trials:
        verify_trial(trial, "response-lost")
    summary = value.get("summary", {})
    require(summary.get("response_lost_stable") is True, f"RESPONSE_LOST_NOT_STABLE:{candidate}")
    require(summary.get("response_lost_pass_count") == len(response_trials), f"RESPONSE_LOST_COUNT_MISMATCH:{candidate}")
    require(summary.get("cleanup_pass") is True, f"CLEANUP_SUMMARY:{candidate}")
    return len(response_trials)


def verify_envoy_candidate(value: dict[str, Any]) -> int:
    trials = value.get("scenario_trials")
    require(isinstance(trials, list), "ENVOY_TRIALS_MISSING")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trial in trials:
        grouped.setdefault(trial.get("scenario", ""), []).append(trial)
    for scenario in ("baseline", "latency-timeout", "dependency-unavailable"):
        require(len(grouped.get(scenario, [])) == 1, f"ENVOY_SCENARIO_SHAPE:{scenario}")
        verify_trial(grouped[scenario][0], scenario)
    response_trials = grouped.get("response-lost", [])
    require(response_trials, "ENVOY_RESPONSE_LOST_MISSING")
    for trial in response_trials:
        require(trial.get("status") == "CANDIDATE_LIMITATION", "ENVOY_RESPONSE_LOST_UNEXPECTED_PASS")
        require(trial.get("outcome", {}).get("classification") == "CANDIDATE_LIMITATION", "ENVOY_LIMITATION_CLASSIFICATION")
        require(trial.get("fault", {}).get("planned") is True and trial.get("fault", {}).get("triggered") is True and trial.get("fault", {}).get("observed") is True, "ENVOY_ABORT_OBSERVATION")
        require(trial.get("client", {}).get("result", {}).get("mutation", {}).get("status") == 503, "ENVOY_ABORT_STATUS")
        require(trial.get("actual_state", {}).get("effect_count") == 0, "ENVOY_ABORT_EFFECT")
        require(trial.get("response_transport_proof", {}).get("target_committed_before_client_failure") is False, "ENVOY_ABORT_COMMIT_ORDER")
        require(trial.get("response_transport_proof", {}).get("response_delivered_to_client") is True, "ENVOY_ABORT_RESPONSE")
        require(trial.get("cleanup", {}).get("ok") is True, "ENVOY_CLEANUP")
    summary = value.get("summary", {})
    require(summary.get("response_lost_candidate_limitation_count") == len(response_trials), "ENVOY_LIMITATION_COUNT")
    require(summary.get("cleanup_pass") is True, "ENVOY_CLEANUP_SUMMARY")
    return len(response_trials)


def verify_result(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError("RESULT_UNREADABLE") from error
    require(value.get("schema") == "rpf-27-network-fault-spike-v1", "SCHEMA")
    require(value.get("plan_id") == "RPF-27", "PLAN_ID")
    require(value.get("lifecycle") == "Stabilization", "LIFECYCLE")
    require(value.get("formal_implementation_changed") is False, "FORMAL_IMPLEMENTATION_CHANGED")
    require(value.get("source_sha256") == source_sha256(), "SOURCE_IDENTITY_MISMATCH")
    require(value.get("security_boundary", {}).get("agent_has_fault_control") is False, "AGENT_FAULT_AUTHORITY")
    require(value.get("security_boundary", {}).get("fault_control_endpoint_exposed_to_agent") is False, "FAULT_ENDPOINT_EXPOSED")
    require(value.get("security_boundary", {}).get("agent_has_docker_socket") is False, "AGENT_DOCKER_SOCKET")
    require(value.get("cleanup_summary", {}).get("volumes_created") == 0, "VOLUMES_CREATED")
    require(value.get("cleanup_summary", {}).get("golden_demo_resources_touched") is False, "GOLDEN_DEMO_TOUCHED")
    require(value.get("cleanup_summary", {}).get("postgres_resources_touched") is False, "POSTGRES_TOUCHED")
    candidates = value.get("candidates", {})
    require(REQUIRED_CANDIDATES.issubset(candidates), "CANDIDATES_MISSING")
    repeat_counts = {candidate: verify_candidate(candidate, candidates[candidate]) for candidate in REQUIRED_CANDIDATES}
    if "envoy" in candidates:
        repeat_counts["envoy"] = verify_envoy_candidate(candidates["envoy"])
    matrix = value.get("comparison_matrix", [])
    require({item.get("candidate") for item in matrix} >= {"Toxiproxy", "Envoy HTTP fault injection", "Narrow custom fault shim"}, "COMPARISON_MATRIX")
    require(value.get("classification_matrix"), "CLASSIFICATION_MATRIX")
    encoded = json.dumps(value, ensure_ascii=False)
    require("messages" not in encoded and "reasoning_content" not in encoded, "PRIVATE_PROTOCOL_CONTENT")
    require("DEEPSEEK_API_KEY" not in encoded and "Authorization" not in encoded, "SECRET_FIELD")
    require(SECRET_PATTERN.search(encoded) is None, "SECRET_PATTERN")
    return {"candidates": sorted(candidates), "response_lost_repeats": repeat_counts, "selected": value.get("recommendation", {}).get("selected_candidate")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the ignored RPF-27 spike evidence")
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    args = parser.parse_args()
    try:
        summary = verify_result(args.result)
    except VerificationError as error:
        print(f"RPF27_VERIFY_FAIL {error}")
        return 1
    print(f"RPF27_VERIFY_PASS candidates={','.join(summary['candidates'])} response_lost_repeats={summary['response_lost_repeats']} selected={summary['selected']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

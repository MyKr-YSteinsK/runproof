"""Offline checks for historical and current reviewed Run Evidence samples."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "runtime" / "runproof_runtime"
LEGACY_ARTIFACTS = (
    ROOT / "runtime" / "reviewed-normal-run.json",
    ROOT / "runtime" / "reviewed-response-lost-run.json",
)
CURRENT_ARTIFACTS = (
    ROOT / "runtime" / "reviewed-normal-run-v2.json",
    ROOT / "runtime" / "reviewed-response-lost-run-v2.json",
)
RPF05_AGENT_FAIL = ROOT / "runtime" / "reviewed-agent-fail-run.json"
RPF05_ENVIRONMENT_ERROR = ROOT / "runtime" / "reviewed-environment-error-run.json"
RPF05_REPRODUCTION = ROOT / "runtime" / "reviewed-agent-fail-reproduction-run.json"
RPF05_FAILURE_CASE = ROOT / "runtime" / "reviewed-failure-case.json"
RPF06_STABILITY_ONE = ROOT / "runtime" / "reviewed-regression-stability-01-run.json"
RPF06_STABILITY_TWO = ROOT / "runtime" / "reviewed-regression-stability-02-run.json"
RPF06_FIXED_CANDIDATE_RUN = ROOT / "runtime" / "reviewed-regression-fixed-candidate-run.json"
RPF06_REGRESSION = ROOT / "runtime" / "reviewed-regression.json"
RPF06_COLLECTION = ROOT / "runtime" / "reviewed-regression-collection.json"
RPF06_PROMOTION_GATE = ROOT / "runtime" / "reviewed-regression-promotion-gate.json"
RPF06_PROMOTED_FAILURE_CASE = ROOT / "runtime" / "reviewed-failure-case-promoted.json"
RPF06_KNOWN_BAD_RESULT = ROOT / "runtime" / "reviewed-regression-known-bad-result.json"
RPF06_FIXED_RESULT = ROOT / "runtime" / "reviewed-regression-fixed-candidate-result.json"
HISTORICAL_RPF03_SOURCE_SHA256 = "c586242817bb03971807b8f44d5e0ebc16c4851519f6f94a9a017c49614a3832"
HISTORICAL_RPF04_SOURCE_SHA256 = "b1235b9128dfe42bcf553ba1f28452c4a08c0af0b5c293c9163a24c7a2b7c127"
HISTORICAL_RPF05_SOURCE_SHA256 = "198194adbefbad5b7b7b89e1119fbac2f10af0231001f8dee5b5e916f1f5c715"
HISTORICAL_RPF05_RUNTIME_VERSION = "rpf-05.v1"
CURRENT_RPF06_RUNTIME_VERSION = "rpf-06.v1"
SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+\S+)"
)
PRIVATE_KEYS = {"authorization", "api_key", "messages", "password", "reasoning_content", "secret", "token"}


def runtime_source_sha256() -> str:
    digest = hashlib.sha256()
    for path in sorted(PACKAGE.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def walk(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield path, key, child
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")


def assert_private_boundary(artifact: dict[str, Any]) -> None:
    encoded = json.dumps(artifact, ensure_ascii=False)
    assert not SECRET_VALUE.search(encoded)
    for location, key, _ in walk(artifact):
        assert key.lower() not in PRIVATE_KEYS, f"private key {location}.{key}"
    assert "reasoning_content" not in encoded
    assert '"messages"' not in encoded


def assert_common_run(path: Path, artifact: dict[str, Any], expected_fault: bool) -> None:
    assert artifact["artifact_kind"] == "Run Evidence"
    assert artifact["outcome"] == {
        "status": "PASS",
        "source": "DETERMINISTIC_VERIFIER",
        "agent_quality_eligible": True,
        "formal_run_started": True,
    }
    assert artifact["environment"]["lifecycle_state"] == "CLEANED"
    assert artifact["environment"]["cleanup_state"] == "CLEANED"
    assert artifact["environment"]["provenance"]["mounts"] == []
    assert artifact["verification"]["passed"] is True
    assert artifact["verification"]["actual_state"] == artifact["verification"]["expected_state"]
    assert artifact["verification"]["evidence"]["blind_retry_attempts"] == 0
    assert artifact["verification"]["evidence"]["unresolved_unknown"] is False
    fault = artifact["fault"]
    assert fault["planned"] is expected_fault
    assert fault["triggered"] is expected_fault
    assert fault["observed"] is expected_fault
    assert fault["reconciled"] is expected_fault
    events = [item["event_type"] for item in artifact["trajectory"]]
    assert "environment_provisioned" in events
    assert "initial_state_verification" in events
    assert "actual_state_verification" in events
    assert "cleanup" in events
    if expected_fault:
        assert "fault" in events
        assert "reconcile" in events
        assert any(item.get("result", {}).get("status") == "UNKNOWN_OUTCOME" for item in artifact["trajectory"])
    else:
        assert "fault" not in events
        assert "reconcile" not in events
    assert_private_boundary(artifact)


def assert_legacy_artifact(path: Path, expected_fault: bool) -> None:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "rpf-run-evidence-v1"
    assert artifact["run"]["runtime"]["source_sha256"] == HISTORICAL_RPF03_SOURCE_SHA256
    assert "provider" in artifact and "llm_provider" not in artifact and "environment_provider" not in artifact
    assert artifact["provider"]["requested_model"] == "deepseek-flash"
    assert artifact["provider"]["mode"] == "non-thinking"
    assert artifact["provider"]["calls"]
    assert_common_run(path, artifact, expected_fault)


def assert_event_contract(artifact: dict[str, Any]) -> None:
    run_id = artifact["run"]["run_id"]
    contract = artifact["trajectory_contract"]
    assert contract["version"] == "rpf-trajectory-event-v1"
    assert "sequence" in contract["ordering"]
    assert "event_id" in contract["identity"]
    events = artifact["trajectory"]
    assert events
    ids = [event["event_id"] for event in events]
    assert len(ids) == len(set(ids))
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    for event in events:
        assert event["event_id"].startswith(f"{run_id}:event:")
        assert event["evidence_layer"] in {"Observed Fact", "Verified Result", "Derived Value", "Inference", "AI Analysis"}
        assert isinstance(event["event_type"], str) and event["event_type"]
        assert event["entity_refs"]["run_id"] == run_id


def assert_current_artifact(path: Path, expected_fault: bool, source_hash: str) -> None:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "rpf-run-evidence-v2"
    assert artifact["run"]["runtime"]["runtime_version"] == "rpf-04.v1"
    assert artifact["run"]["runtime"]["source_sha256"] in {HISTORICAL_RPF04_SOURCE_SHA256, source_hash}
    assert "provider" not in artifact
    llm = artifact["llm_provider"]
    assert llm["provider_id"] == "deepseek"
    assert llm["provider_type"] == "llm"
    assert llm["requested_model"] == "deepseek-flash"
    assert llm["mode"] == "non-thinking"
    assert llm["calls"]
    assert all(call["provider"] == "deepseek" for call in llm["calls"])
    environment_provider = artifact["environment_provider"]
    assert environment_provider["provider_id"] == "docker"
    assert environment_provider["provider_type"] == "environment"
    assert environment_provider["provider_implementation"] == "docker"
    assert environment_provider["image"]["reference"] == "alpine:3.22"
    assert_common_run(path, artifact, expected_fault)
    assert_event_contract(artifact)
    events = artifact["trajectory"]
    if expected_fault:
        fault_index = next(index for index, event in enumerate(events) if event["event_type"] == "fault")
        unknown_index = next(
            index
            for index, event in enumerate(events)
            if event["event_type"] == "tool_result" and event.get("result", {}).get("status") == "UNKNOWN_OUTCOME"
        )
        reconcile_index = next(index for index, event in enumerate(events) if event["event_type"] == "reconcile")
        verification_index = next(index for index, event in enumerate(events) if event["event_type"] == "actual_state_verification")
        assert fault_index < unknown_index < reconcile_index < verification_index


def assert_rpf05_identity(artifact: dict[str, Any], source_hash: str) -> None:
    assert artifact["schema_version"] == "rpf-run-evidence-v2"
    assert artifact["run"]["runtime"]["runtime_version"] == HISTORICAL_RPF05_RUNTIME_VERSION
    assert artifact["run"]["runtime"]["source_sha256"] == HISTORICAL_RPF05_SOURCE_SHA256
    assert "provider" not in artifact
    assert artifact["environment_provider"]["provider_implementation"] == "docker"
    assert artifact["environment_provider"]["image"]["reference"] == "alpine:3.22"
    assert artifact["environment"]["lifecycle_state"] == "CLEANED"
    assert artifact["environment"]["cleanup_state"] == "CLEANED"
    assert artifact["environment"]["provenance"]["mounts"] == []
    assert_event_contract(artifact)
    assert_private_boundary(artifact)


def assert_agent_fail(path: Path, source_hash: str) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert_rpf05_identity(artifact, source_hash)
    assert artifact["outcome"] == {
        "status": "FAIL",
        "source": "AGENT",
        "agent_quality_eligible": False,
        "formal_run_started": True,
        "reason": "BUSINESS_PRECONDITION_OBSERVATION_REQUIRED",
        "attribution": "Agent",
        "agent_started": True,
    }
    assert artifact["run"]["agent"]["configuration_id"] == "known-bad-unsafe-precondition-v1"
    assert artifact["run"]["agent"]["agent_version"] == "1.0.0-known-bad-unsafe-precondition"
    failure = artifact["failure_attribution"]
    assert failure["category"] == "Agent"
    assert failure["deterministic"] is True
    assert failure["violated_invariant_id"] == "RPF-AGENT-OBSERVE-BEFORE-MUTATION"
    event_ids = {event["event_id"] for event in artifact["trajectory"]}
    assert failure["failing_event_id"] in event_ids
    assert failure["agent_intent_event_id"] in event_ids
    assert failure["guard_event_id"] in event_ids
    assert failure["state_change_protected"] is True
    assert artifact["verification"]["passed"] is False
    assert artifact["verification"]["evidence"]["mutation_count"] == 0
    assert artifact["health_context"]["provider"]["failure_source"] is False
    assert artifact["health_context"]["environment"]["failure_source"] is False
    assert any(event["event_type"] == "guard_blocked" and event.get("side_effect_executed") is False for event in artifact["trajectory"])
    return artifact


def assert_environment_error(path: Path, source_hash: str) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert_rpf05_identity(artifact, source_hash)
    assert artifact["outcome"] == {
        "status": "ERROR",
        "source": "ENVIRONMENT",
        "agent_quality_eligible": False,
        "formal_run_started": False,
        "reason": "CONTROLLED_READINESS_FAILURE",
        "attribution": "Platform/Environment",
        "agent_started": False,
    }
    assert artifact["verification"] is None
    assert artifact["failure_attribution"]["category"] == "Platform/Environment"
    assert artifact["failure_attribution"]["agent_started"] is False
    assert artifact["failure_attribution"]["state_change_performed"] is False
    assert artifact["failure_attribution"]["agent_quality_excluded"] is True
    assert artifact["environment"]["controlled_failure"]["hook_id"] == "pre-agent-readiness"
    assert artifact["health_context"]["provider"]["failure_source"] is False
    assert artifact["health_context"]["environment"]["failure_source"] is True
    assert [event["event_type"] for event in artifact["trajectory"]] == [
        "environment_provisioned",
        "readiness",
        "actual_state_observed_after_failure",
        "cleanup",
    ]
    return artifact


def assert_failure_case(path: Path, fail: dict[str, Any], reproduction: dict[str, Any]) -> dict[str, Any]:
    case = json.loads(path.read_text(encoding="utf-8"))
    assert case["schema_version"] == "rpf-failure-case-v1"
    assert case["artifact_kind"] == "Failure Case"
    metadata = case["failure_case"]
    assert metadata["workflow_state"] == "validated"
    assert metadata["current_status"] == "validated"
    assert metadata["is_regression"] is False
    assert metadata["regression_status"] == "NOT_A_REGRESSION"
    assert case["source_run"]["run_id"] == fail["run"]["run_id"]
    assert case["source_run"]["environment_id"] == fail["environment"]["environment_id"]
    assert case["classification"] == {
        "outcome": "FAIL",
        "attribution": "Agent",
        "domain": "AGENT",
        "deterministic": True,
        "reason_code": "BUSINESS_PRECONDITION_OBSERVATION_REQUIRED",
    }
    assert case["failure_signature"]["signature_version"] == "rpf-failure-signature-v1"
    assert case["failure_signature"]["value"] == case["validation"]["expected_signature"]["value"]
    assert case["validation"]["same_failure"] is True
    assert all(case["validation"]["checks"].values())
    attempts = case["reproduction_attempts"]
    assert len(attempts) == 1
    assert attempts[0]["run_id"] == reproduction["run"]["run_id"]
    assert attempts[0]["environment_id"] == reproduction["environment"]["environment_id"]
    assert attempts[0]["status"] == "reproduced"
    assert case["regression"]["status"] == "NOT_A_REGRESSION"
    assert_private_boundary(case)
    return case


def assert_rpf06_run(path: Path, source_hash: str, profile_id: str, expected_status: str) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "rpf-run-evidence-v2"
    assert artifact["run"]["runtime"]["runtime_version"] == CURRENT_RPF06_RUNTIME_VERSION
    assert artifact["run"]["runtime"]["source_sha256"] == source_hash
    assert artifact["environment_provider"]["provider_implementation"] == "docker"
    assert artifact["environment"]["lifecycle_state"] == "CLEANED"
    assert artifact["environment"]["cleanup_state"] == "CLEANED"
    assert artifact["environment"]["provenance"]["mounts"] == []
    assert artifact["run"]["agent"]["configuration_id"] == profile_id
    assert artifact["outcome"]["status"] == expected_status
    assert_event_contract(artifact)
    assert_private_boundary(artifact)
    if profile_id == "known-bad-unsafe-precondition-v1":
        assert expected_status == "FAIL"
        assert artifact["outcome"]["source"] == "AGENT"
        assert artifact["outcome"]["attribution"] == "Agent"
        assert artifact["failure_attribution"]["violated_invariant_id"] == "RPF-AGENT-OBSERVE-BEFORE-MUTATION"
        assert artifact["verification"]["passed"] is False
        assert artifact["verification"]["evidence"]["mutation_count"] == 0
        assert any(event["event_type"] == "guard_blocked" and event.get("side_effect_executed") is False for event in artifact["trajectory"])
    else:
        assert profile_id == "production-change-agent-v1-fixed"
        assert expected_status == "PASS"
        assert artifact["outcome"]["source"] == "DETERMINISTIC_VERIFIER"
        assert artifact["verification"]["passed"] is True
        assert artifact["verification"]["actual_state"] == artifact["verification"]["expected_state"]
        assert artifact["verification"]["evidence"]["mutation_count"] == 1
        assert artifact["failure_attribution"] is None
    assert artifact["health_context"]["provider"]["failure_source"] is False
    assert artifact["health_context"]["environment"]["failure_source"] is False
    return artifact


def assert_promotion_gate(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema_version"] == "rpf-promotion-gate-v1"
    assert document["artifact_kind"] == "Promotion Gate Evaluation"
    gate = document["gate"]
    assert gate["status"] == "ELIGIBLE"
    assert gate["all_passed"] is True
    assert gate["blocked_reasons"] == []
    assert set(gate["gates"]) == {"reproducibility", "relevance", "stability", "non_duplicate", "expected_behavior_explicit"}
    assert all(item["status"] == "PASS" for item in gate["gates"].values())
    assert gate["gates"]["stability"]["evidence"]["minimum_required"] == 2
    assert len(gate["gates"]["stability"]["evidence"]["observations"]) == 2
    assert gate["gates"]["non_duplicate"]["evidence"]["existing_regression_count"] == 0
    assert_private_boundary(document)
    return document


def assert_regression(path: Path, case: dict[str, Any], gate_document: dict[str, Any], source_hash: str) -> dict[str, Any]:
    regression = json.loads(path.read_text(encoding="utf-8"))
    assert regression["schema_version"] == "rpf-regression-v1"
    assert regression["artifact_kind"] == "Regression"
    assert regression["regression_runtime"]["runtime_version"] == CURRENT_RPF06_RUNTIME_VERSION
    metadata = regression["regression"]
    assert metadata["regression_version"] == "1.0.0"
    assert metadata["lifecycle_status"] == "ACTIVE"
    assert metadata["status"] == "ACTIVE_HISTORICAL_REGRESSION"
    assert metadata["category"] == "Historical Regression"
    source = regression["source_failure_case"]
    assert source["failure_case_id"] == case["failure_case"]["failure_case_id"]
    assert source["failure_signature"] == case["failure_signature"]
    assert regression["promotion"]["status"] == "PROMOTED"
    assert regression["promotion"]["source_history_immutable"] is True
    assert regression["promotion"]["gate"]["all_passed"] is True
    assert all(item["status"] == "PASS" for item in regression["promotion"]["gate"]["gates"].values())
    contract = regression["contract"]
    for key in ("initial_state", "seed_requirement", "scenario", "required_outcome", "forbidden_outcomes", "invariants", "expected_safe_behavior", "failure_condition", "oracles"):
        assert contract.get(key)
    assert contract["oracles"]["failure"]["regression_result"] == "FAIL"
    assert contract["oracles"]["pass"]["regression_result"] == "PASS"
    assert len(regression["focused_reruns"]) == 2
    assert {item["agent_profile"] for item in regression["focused_reruns"]} == {"known-bad-unsafe-precondition-v1", "production-change-agent-v1-fixed"}
    assert {item["regression_result"] for item in regression["focused_reruns"]} == {"FAIL", "PASS"}
    assert regression["collection_membership"]["collection_id"] == "historical-regressions-v1"
    assert "trajectory" not in regression
    assert_private_boundary(regression)
    return regression


def assert_regression_result(path: Path, regression: dict[str, Any], run: dict[str, Any], expected_profile: str, expected_result: str, expected_run_outcome: str) -> dict[str, Any]:
    result_document = json.loads(path.read_text(encoding="utf-8"))
    assert result_document["schema_version"] == "rpf-regression-result-v1"
    assert result_document["artifact_kind"] == "Regression Execution Result"
    result = result_document["result"]
    assert result["regression_id"] == regression["regression"]["regression_id"]
    assert result["regression_version"] == regression["regression"]["regression_version"]
    assert result["agent_profile"] == expected_profile
    assert result["regression_result"] == expected_result
    assert result["run_outcome"] == expected_run_outcome
    assert result["run_ref"]["run_id"] == run["run"]["run_id"]
    assert result["release_eligibility"] == "NOT_EVALUATED"
    assert result["oracle"]["status"] == expected_result
    assert "trajectory" not in result_document
    assert_private_boundary(result_document)
    return result_document


def assert_collection(path: Path, regression: dict[str, Any]) -> None:
    collection = json.loads(path.read_text(encoding="utf-8"))
    assert collection["schema_version"] == "rpf-regression-collection-v1"
    assert collection["artifact_kind"] == "Historical Regression Collection"
    assert collection["collection"] == {
        "collection_id": "historical-regressions-v1",
        "collection_version": "1.0.0",
        "category": "Historical Regression",
        "status": "ACTIVE",
        "description": "Minimal reviewed Regression membership for stable historical Agent failures.",
    }
    assert len(collection["members"]) == 1
    assert collection["members"][0]["regression_id"] == regression["regression"]["regression_id"]
    assert collection["members"][0]["status"] == "ACTIVE"
    assert_private_boundary(collection)


def assert_promoted_failure_case(path: Path, original: dict[str, Any], regression: dict[str, Any]) -> None:
    promoted = json.loads(path.read_text(encoding="utf-8"))
    assert promoted["schema_version"] == "rpf-failure-case-v1"
    assert promoted["artifact_kind"] == "Failure Case"
    assert promoted["source_run"] == original["source_run"]
    assert promoted["failure_signature"] == original["failure_signature"]
    assert promoted["failure_case"]["workflow_state"] == "validated"
    assert promoted["failure_case"]["current_status"] == "promoted"
    assert promoted["failure_case"]["regression_status"] == "PROMOTED_TO_REGRESSION"
    assert promoted["promotion"]["status"] == "PROMOTED"
    assert promoted["promotion"]["regression_ref"]["regression_id"] == regression["regression"]["regression_id"]
    assert promoted["promotion"]["supersedes"] == {
        "previous_current_status": "validated",
        "previous_regression_status": "NOT_A_REGRESSION",
        "source_artifact_remains_immutable": True,
    }
    assert_private_boundary(promoted)


def main() -> None:
    source_hash = runtime_source_sha256()
    assert_legacy_artifact(LEGACY_ARTIFACTS[0], expected_fault=False)
    assert_legacy_artifact(LEGACY_ARTIFACTS[1], expected_fault=True)
    assert_current_artifact(CURRENT_ARTIFACTS[0], expected_fault=False, source_hash=source_hash)
    assert_current_artifact(CURRENT_ARTIFACTS[1], expected_fault=True, source_hash=source_hash)
    fail = assert_agent_fail(RPF05_AGENT_FAIL, source_hash)
    assert_environment_error(RPF05_ENVIRONMENT_ERROR, source_hash)
    reproduction = assert_agent_fail(RPF05_REPRODUCTION, source_hash)
    assert fail["run"]["run_id"] != reproduction["run"]["run_id"]
    assert fail["environment"]["environment_id"] != reproduction["environment"]["environment_id"]
    case = assert_failure_case(RPF05_FAILURE_CASE, fail, reproduction)
    stability_one = assert_rpf06_run(RPF06_STABILITY_ONE, source_hash, "known-bad-unsafe-precondition-v1", "FAIL")
    stability_two = assert_rpf06_run(RPF06_STABILITY_TWO, source_hash, "known-bad-unsafe-precondition-v1", "FAIL")
    fixed_candidate = assert_rpf06_run(RPF06_FIXED_CANDIDATE_RUN, source_hash, "production-change-agent-v1-fixed", "PASS")
    gate_document = assert_promotion_gate(RPF06_PROMOTION_GATE)
    regression = assert_regression(RPF06_REGRESSION, case, gate_document, source_hash)
    assert_regression_result(RPF06_KNOWN_BAD_RESULT, regression, stability_two, "known-bad-unsafe-precondition-v1", "FAIL", "FAIL")
    assert_regression_result(RPF06_FIXED_RESULT, regression, fixed_candidate, "production-change-agent-v1-fixed", "PASS", "PASS")
    assert_collection(RPF06_COLLECTION, regression)
    assert_promoted_failure_case(RPF06_PROMOTED_FAILURE_CASE, case, regression)
    assert stability_one["run"]["run_id"] != stability_two["run"]["run_id"]
    assert stability_one["environment"]["environment_id"] != stability_two["environment"]["environment_id"]
    assert stability_two["run"]["run_id"] != fixed_candidate["run"]["run_id"]
    print(f"PASS: 2 historical v1 + 2 RPF-04 v2 + 3 RPF-05 runs + 3 RPF-06 runs + 6 RPF-06 artifacts; source={source_hash}")


if __name__ == "__main__":
    main()

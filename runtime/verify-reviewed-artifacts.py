"""Offline checks for historical and current reviewed Run Evidence samples."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from runproof_runtime.evaluation import (
    EVALUATION_COMPARISON_SCHEMA_VERSION,
    EVALUATION_RESULT_SCHEMA_VERSION,
    EVALUATION_SUITE_ID,
    EVALUATION_SUITE_SCHEMA_VERSION,
    EVALUATION_SUITE_VERSION,
    validate_comparison_artifact,
    validate_evaluation_artifact,
    validate_suite_artifact,
)
from runproof_runtime.quality import (
    QUALITY_GATE_SCHEMA_VERSION,
    QUALITY_POLICY_IDENTITY,
    QUALITY_POLICY_SCHEMA_VERSION,
    RELEASE_DECISION_SCHEMA_VERSION,
    validate_quality_gate_artifact,
    validate_quality_policy,
    validate_release_decision_artifact,
)
from runproof_runtime.multi_service_runner import FORMAL_VERIFIER_ID, RPF28_RUNTIME_VERSION


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
RPF07_SUITE = ROOT / "runtime" / "reviewed-evaluation-suite.json"
RPF07_BASELINE_RUNS = (
    ROOT / "runtime" / "reviewed-evaluation-baseline-normal-run.json",
    ROOT / "runtime" / "reviewed-evaluation-baseline-recovery-run.json",
    ROOT / "runtime" / "reviewed-evaluation-baseline-regression-run.json",
)
RPF07_CANDIDATE_RUNS = (
    ROOT / "runtime" / "reviewed-evaluation-candidate-normal-run.json",
    ROOT / "runtime" / "reviewed-evaluation-candidate-recovery-run.json",
    ROOT / "runtime" / "reviewed-evaluation-candidate-regression-run.json",
)
RPF07_BASELINE_RESULT = ROOT / "runtime" / "reviewed-evaluation-baseline.json"
RPF07_CANDIDATE_RESULT = ROOT / "runtime" / "reviewed-evaluation-candidate.json"
RPF07_BASELINE_REGRESSION_RESULT = ROOT / "runtime" / "reviewed-evaluation-baseline-regression-result.json"
RPF07_CANDIDATE_REGRESSION_RESULT = ROOT / "runtime" / "reviewed-evaluation-candidate-regression-result.json"
RPF07_COMPARISON = ROOT / "runtime" / "reviewed-evaluation-comparison.json"
RPF08_POLICY = ROOT / "runtime" / "reviewed-quality-policy.json"
RPF08_BASELINE_GATE = ROOT / "runtime" / "reviewed-quality-gate-baseline.json"
RPF08_CANDIDATE_GATE = ROOT / "runtime" / "reviewed-quality-gate-candidate.json"
RPF08_BASELINE_DECISION = ROOT / "runtime" / "reviewed-release-decision-baseline.json"
RPF08_CANDIDATE_DECISION = ROOT / "runtime" / "reviewed-release-decision-candidate.json"
RPF28_BASELINE = ROOT / "runtime" / "reviewed-rpf28-multi-service-baseline-run.json"
RPF28_DEPENDENCY_UNAVAILABLE = ROOT / "runtime" / "reviewed-rpf28-multi-service-dependency-unavailable-run.json"
RPF28_RESPONSE_LOST = ROOT / "runtime" / "reviewed-rpf28-multi-service-response-lost-run.json"
HISTORICAL_RPF03_SOURCE_SHA256 = "c586242817bb03971807b8f44d5e0ebc16c4851519f6f94a9a017c49614a3832"
HISTORICAL_RPF04_SOURCE_SHA256 = "b1235b9128dfe42bcf553ba1f28452c4a08c0af0b5c293c9163a24c7a2b7c127"
HISTORICAL_RPF05_SOURCE_SHA256 = "198194adbefbad5b7b7b89e1119fbac2f10af0231001f8dee5b5e916f1f5c715"
HISTORICAL_RPF05_RUNTIME_VERSION = "rpf-05.v1"
HISTORICAL_RPF06_SOURCE_SHA256 = "a8f5cbebc475463c392fda85a38e97fecdeb34af80ddf73f73099d43e61f3360"
HISTORICAL_RPF06_RUNTIME_VERSION = "rpf-06.v1"
CURRENT_RPF07_RUNTIME_VERSION = "rpf-07.v1"
HISTORICAL_RPF07_SOURCE_SHA256 = "c607e5e38015c99fedcbba3efbcdc20834953f2fec7543313ead3ce0211d3adf"
HISTORICAL_RPF08_SOURCE_SHA256 = "d6313e5849b2662d9badafa7be25d568e84ab6cc4912c9587495a5f9427bfd69"
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
    assert artifact["run"]["runtime"]["runtime_version"] == HISTORICAL_RPF06_RUNTIME_VERSION
    assert artifact["run"]["runtime"]["source_sha256"] == HISTORICAL_RPF06_SOURCE_SHA256
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
    assert regression["regression_runtime"]["runtime_version"] == HISTORICAL_RPF06_RUNTIME_VERSION
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


def assert_rpf07_suite(path: Path, regression: dict[str, Any], source_hash: str) -> dict[str, Any]:
    suite = json.loads(path.read_text(encoding="utf-8"))
    assert suite["schema_version"] == EVALUATION_SUITE_SCHEMA_VERSION
    assert suite["artifact_kind"] == "Evaluation Suite"
    assert not validate_suite_artifact(suite, regression)
    metadata = suite["suite"]
    assert metadata["suite_id"] == EVALUATION_SUITE_ID
    assert metadata["suite_version"] == EVALUATION_SUITE_VERSION
    assert metadata["source_identity"] == {
        "runtime_version": CURRENT_RPF07_RUNTIME_VERSION,
        "source_sha256": HISTORICAL_RPF07_SOURCE_SHA256,
        "builder": "rpf-evaluation-suite-builder-v1",
    }
    assert {item["category"] for item in metadata["members"]} == {
        "Normal / Functional",
        "Recovery / Fault",
        "Historical Regression",
    }
    assert metadata["execution_policy"]["isolation"] == "fresh-per-member"
    assert metadata["execution_policy"]["parallelism"] == "sequential"
    assert metadata["members"][2]["regression_ref"] == {
        "kind": "Regression",
        "regression_id": regression["regression"]["regression_id"],
        "regression_version": regression["regression"]["regression_version"],
    }
    assert_private_boundary(suite)
    return suite


def assert_rpf07_run(path: Path, source_hash: str, profile_id: str, expected_status: str, evaluation_id: str, expected_fault: bool) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "rpf-run-evidence-v2"
    assert artifact["run"]["runtime"]["runtime_version"] == CURRENT_RPF07_RUNTIME_VERSION
    assert artifact["run"]["runtime"]["source_sha256"] in {HISTORICAL_RPF07_SOURCE_SHA256, source_hash}
    assert artifact["run"]["evaluation_id"] == evaluation_id
    assert artifact["environment_provider"]["provider_implementation"] == "docker"
    assert artifact["environment"]["lifecycle_state"] == "CLEANED"
    assert artifact["environment"]["cleanup_state"] == "CLEANED"
    assert artifact["environment"]["provenance"]["mounts"] == []
    assert artifact["run"]["agent"]["configuration_id"] == profile_id
    assert artifact["outcome"]["status"] == expected_status
    assert_event_contract(artifact)
    assert_private_boundary(artifact)
    fault = artifact["fault"]
    assert fault["planned"] is expected_fault
    if expected_status == "PASS":
        assert artifact["outcome"]["source"] == "DETERMINISTIC_VERIFIER"
        assert artifact["verification"]["passed"] is True
        assert artifact["verification"]["evidence"]["mutation_count"] == 1
    elif expected_status == "FAIL":
        assert artifact["outcome"]["source"] == "AGENT"
        assert artifact["outcome"]["attribution"] == "Agent"
        assert artifact["verification"]["passed"] is False
        assert artifact["verification"]["evidence"]["mutation_count"] == 0
    else:
        raise AssertionError(f"unexpected RPF-07 reviewed status: {expected_status}")
    if expected_fault and expected_status == "PASS":
        assert fault["triggered"] is True
        assert fault["observed"] is True
        assert fault["reconciled"] is True
        event_types = [item["event_type"] for item in artifact["trajectory"]]
        assert "fault" in event_types and "reconcile" in event_types
    assert artifact["health_context"]["provider"]["failure_source"] is False
    assert artifact["health_context"]["environment"]["failure_source"] is False
    return artifact


def assert_rpf07_regression_result(path: Path, regression: dict[str, Any], run: dict[str, Any], profile_id: str, expected_result: str, evaluation_id: str) -> dict[str, Any]:
    result = assert_regression_result(path, regression, run, profile_id, expected_result, expected_result)
    metadata = result["result"]
    assert metadata.get("evaluation_ref") == {"kind": "Evaluation Result", "evaluation_id": evaluation_id}
    assert metadata.get("suite_member_ref", {}).get("member_id") == "historical-regression"
    return result


def assert_rpf07_evaluation(path: Path, suite: dict[str, Any], regression: dict[str, Any], source_hash: str, expected_profile: str, expected_evaluation_id: str, runs: list[dict[str, Any]], result_path: Path, expected_item_results: list[str]) -> dict[str, Any]:
    evaluation = json.loads(path.read_text(encoding="utf-8"))
    assert evaluation["schema_version"] == EVALUATION_RESULT_SCHEMA_VERSION
    assert evaluation["artifact_kind"] == "Evaluation Result"
    assert not validate_evaluation_artifact(evaluation)
    metadata = evaluation["evaluation"]
    assert metadata["evaluation_id"] == expected_evaluation_id
    assert metadata["evaluation_status"] == "COMPLETE"
    assert metadata["agent"]["configuration_id"] == expected_profile
    assert metadata["runtime"]["runtime_version"] == CURRENT_RPF07_RUNTIME_VERSION
    assert metadata["runtime"]["source_sha256"] in {HISTORICAL_RPF07_SOURCE_SHA256, source_hash}
    # Keep this comparison explicit: the Evaluation stores a stable Suite ref,
    # not the full Suite definition or an Evaluation-specific identity.
    assert metadata["suite_ref"] == {
        "kind": "Evaluation Suite",
        "suite_id": suite["suite"]["suite_id"],
        "suite_version": suite["suite"]["suite_version"],
        "member_contract_digest": suite["suite"]["member_contract_digest"],
    }
    items = metadata["member_results"]
    assert [item["item_result"] for item in items] == expected_item_results
    assert [item["run_ref"]["run_id"] for item in items] == [run["run"]["run_id"] for run in runs]
    assert len({item["run_ref"]["run_id"] for item in items}) == len(items)
    assert len({run["environment"]["environment_id"] for run in runs}) == len(runs)
    regression_item = items[2]
    result_document = json.loads(result_path.read_text(encoding="utf-8"))
    assert regression_item["regression_result_ref"]["result_id"] == result_document["result"]["result_id"]
    assert metadata["summary"]["valid_evidence_coverage"]["coverage_ratio"] == 1.0
    if expected_profile == "known-bad-unsafe-precondition-v1":
        assert metadata["summary"]["agent_quality"] == {
            **metadata["summary"]["agent_quality"],
            "pass_count": 0,
            "fail_count": 3,
            "denominator": 3,
            "success_rate": 0.0,
            "failure_rate": 1.0,
        }
    else:
        assert metadata["summary"]["agent_quality"]["pass_count"] == 3
        assert metadata["summary"]["agent_quality"]["fail_count"] == 0
        assert metadata["summary"]["agent_quality"]["denominator"] == 3
        assert metadata["summary"]["agent_quality"]["success_rate"] == 1.0
    metrics = metadata["summary"]["cost_token_latency"]
    assert metrics["reported_token_usage_sum"] is None
    assert metrics["derived_cost_sum"] is None
    assert metrics["unknown_cost_count"] == 3
    assert_private_boundary(evaluation)
    return evaluation


def assert_rpf07_comparison(path: Path, baseline: dict[str, Any], candidate: dict[str, Any], suite: dict[str, Any], source_hash: str) -> dict[str, Any]:
    comparison = json.loads(path.read_text(encoding="utf-8"))
    assert comparison["schema_version"] == EVALUATION_COMPARISON_SCHEMA_VERSION
    assert comparison["artifact_kind"] == "Evaluation Comparison"
    assert not validate_comparison_artifact(comparison)
    metadata = comparison["comparison"]
    assert metadata["status"] == "COMPLETE"
    assert metadata["runtime"]["runtime_version"] == CURRENT_RPF07_RUNTIME_VERSION
    assert metadata["runtime"]["source_sha256"] in {HISTORICAL_RPF07_SOURCE_SHA256, source_hash}
    assert metadata["suite_ref"] == {
        "kind": "Evaluation Suite",
        "suite_id": suite["suite"]["suite_id"],
        "suite_version": suite["suite"]["suite_version"],
        "member_contract_digest": suite["suite"]["member_contract_digest"],
    }
    assert metadata["baseline"]["evaluation_id"] == baseline["evaluation"]["evaluation_id"]
    assert metadata["candidate"]["evaluation_id"] == candidate["evaluation"]["evaluation_id"]
    assert [item["classification"] for item in metadata["per_member_comparison"]] == ["IMPROVED", "IMPROVED", "IMPROVED"]
    assert metadata["aggregate"]["summary"] == "CANDIDATE_IMPROVED"
    assert metadata["aggregate"]["agent_quality"]["success_rate_delta"]["delta"] == 1.0
    assert metadata["aggregate"]["valid_evidence_coverage"]["coverage_ratio_delta"]["delta"] == 0.0
    regression_delta = metadata["aggregate"]["regression"]["historical_regression_member_deltas"][0]
    assert regression_delta["baseline_result"] == "FAIL"
    assert regression_delta["candidate_result"] == "PASS"
    assert regression_delta["regression_ref"]["regression_version"] == "1.0.0"
    assert metadata["aggregate"]["cost_token_latency"]["derived_cost"]["status"] == "UNKNOWN"
    assert metadata["aggregate"]["cost_token_latency"]["derived_cost"]["delta"] is None
    assert metadata["non_release_boundary"] == "COMPARISON_ONLY_NO_RELEASE_DECISION"
    encoded = json.dumps(comparison, ensure_ascii=False)
    for forbidden in ("ELIGIBLE", "BLOCKED", "REVIEW REQUIRED", '"release_decision"'):
        assert forbidden not in encoded
    assert_private_boundary(comparison)
    return comparison


def assert_rpf08_policy(path: Path, suite: dict[str, Any], source_hash: str) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    assert policy["schema_version"] == QUALITY_POLICY_SCHEMA_VERSION
    assert policy["artifact_kind"] == "Quality Policy"
    assert not validate_quality_policy(policy, suite)
    metadata = policy["policy"]
    assert metadata["policy_identity"] == QUALITY_POLICY_IDENTITY
    assert metadata["compatible_suite"]["suite_id"] == suite["suite"]["suite_id"]
    assert metadata["compatible_suite"]["suite_version"] == suite["suite"]["suite_version"]
    assert metadata["compatible_suite"]["member_contract_digest"] == suite["suite"]["member_contract_digest"]
    assert {rule["gate"] for rule in metadata["rules"]} == {"HARD", "SOFT"}
    assert metadata["decision_precedence"] == ["HARD_BLOCKER", "EVIDENCE_INSUFFICIENT", "REVIEW_REQUIRED", "ELIGIBLE"]
    assert metadata["unknown_value_semantics"] == {
        "reported_tokens": "WARNING_NOT_ZERO",
        "derived_cost": "WARNING_NOT_ZERO",
        "latency": "WARNING_NOT_ZERO",
    }
    assert metadata["source_identity"]["runtime_version"] == "rpf-08.v1"
    assert metadata["source_identity"]["source_sha256"] in {HISTORICAL_RPF08_SOURCE_SHA256, source_hash}
    assert_private_boundary(policy)
    return policy


def assert_rpf08_gate(path: Path, policy: dict[str, Any], suite: dict[str, Any], expected_status: str, source_hash: str) -> dict[str, Any]:
    gate = json.loads(path.read_text(encoding="utf-8"))
    assert gate["schema_version"] == QUALITY_GATE_SCHEMA_VERSION
    assert gate["artifact_kind"] == "Quality Gate Evaluation"
    assert not validate_quality_gate_artifact(gate)
    metadata = gate["gate_evaluation"]
    assert metadata["status"] == "COMPLETE"
    assert metadata["decision_status"] == expected_status
    assert metadata["policy_ref"]["policy_identity"] == policy["policy"]["policy_identity"]
    assert metadata["suite_ref"] == {
        "kind": "Evaluation Suite",
        "suite_id": suite["suite"]["suite_id"],
        "suite_version": suite["suite"]["suite_version"],
        "member_contract_digest": suite["suite"]["member_contract_digest"],
    }
    assert metadata["authorization_boundary"] == {
        "release_executed": False,
        "deployment_authorized": False,
        "release_action": "DECISION_ONLY",
    }
    assert metadata["source_identity"]["runtime_version"] == "rpf-08.v1"
    assert metadata["source_identity"]["source_sha256"] in {HISTORICAL_RPF08_SOURCE_SHA256, source_hash}
    assert metadata["rule_results"]
    assert_private_boundary(gate)
    return gate


def assert_rpf08_decision(path: Path, expected_status: str, expected_evaluated_version: str, source_hash: str) -> dict[str, Any]:
    decision = json.loads(path.read_text(encoding="utf-8"))
    assert decision["schema_version"] == RELEASE_DECISION_SCHEMA_VERSION
    assert decision["artifact_kind"] == "Release Decision"
    assert not validate_release_decision_artifact(decision)
    metadata = decision["release_decision"]
    assert metadata["decision_status"] == expected_status
    assert metadata["evaluated_agent_version"] == expected_evaluated_version
    assert metadata["authorization_boundary"]["release_executed"] is False
    assert metadata["authorization_boundary"]["deployment_authorized"] is False
    assert metadata["authorization_boundary"]["release_action"] == "DECISION_ONLY"
    assert metadata["history"]["immutable"] is True
    assert metadata["source_identity"]["runtime_version"] == "rpf-08.v1"
    assert metadata["source_identity"]["source_sha256"] in {HISTORICAL_RPF08_SOURCE_SHA256, source_hash}
    assert_private_boundary(decision)
    return decision


def assert_rpf28_artifact(path: Path, expected_profile: str, source_hash: str) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "rpf-run-evidence-v2"
    assert artifact["artifact_kind"] == "Run Evidence"
    assert artifact["run"]["runtime"]["runtime_version"] == RPF28_RUNTIME_VERSION
    assert artifact["run"]["runtime"]["source_sha256"] == source_hash
    assert artifact["run"]["verifier"]["verifier_id"] == FORMAL_VERIFIER_ID
    assert artifact["environment"]["environment_profile"] == "multi-service-toxiproxy-v1"
    assert artifact["environment"]["lifecycle_state"] == "CLEANED"
    assert artifact["environment"]["cleanup_state"] == "CLEANED"
    provenance = artifact["environment"]["provenance"]
    assert provenance["network"]["internal"] is True
    assert provenance["resource_scope"] == {
        "network": "private-controlled",
        "network_internal": True,
        "volume_count": 0,
        "host_docker_socket_mounted": False,
        "production_credentials": False,
    }
    assert {item["role"] for item in provenance["containers"]} == {"target", "dependency", "fault-boundary", "agent-client"}
    assert artifact["fault"]["fault_profile"] == expected_profile
    assert artifact["outcome"]["status"] == "PASS"
    assert artifact["verification"]["passed"] is True
    assert artifact["verification"]["evidence"]["blind_retry_attempts"] == 0
    lifecycle_states = [item["state"] for item in artifact["environment"].get("lifecycle_trace", [])]
    required_lifecycle = ["UNPROVISIONED", "NETWORK_ALLOCATED", "SERVICES_ALLOCATED", "PROXY_READY", "CLIENT_READY", "SEEDED", "PROVISIONED", "READY_UNVERIFIED", "READY_VERIFIED", "EXECUTING", "TERMINAL_EVIDENCE", "CLEANED"]
    assert all(state in lifecycle_states for state in required_lifecycle)
    assert lifecycle_states.index("UNPROVISIONED") < lifecycle_states.index("NETWORK_ALLOCATED") < lifecycle_states.index("SERVICES_ALLOCATED") < lifecycle_states.index("PROXY_READY") < lifecycle_states.index("CLIENT_READY") < lifecycle_states.index("SEEDED") < lifecycle_states.index("READY_VERIFIED") < lifecycle_states.index("CLEANED")
    if expected_profile == "response-lost":
        assert lifecycle_states.index("UNKNOWN_OUTCOME") < lifecycle_states.index("TERMINAL_EVIDENCE")
    events = [item["event_type"] for item in artifact["trajectory"]]
    assert "environment_provisioned" in events and "initial_state_verification" in events and "cleanup" in events
    if expected_profile == "none":
        assert artifact["verification"]["evidence"]["mutation_count"] == 1
        assert artifact["verification"]["evidence"]["mutation_requests"] == 1
        assert "fault" not in events
    elif expected_profile == "dependency-unavailable":
        assert artifact["verification"]["evidence"]["mutation_count"] == 0
        assert artifact["verification"]["checks"]["dependency_failure_classified"] is True
        assert artifact["fault"]["observed"] is True
    elif expected_profile == "response-lost":
        assert artifact["verification"]["evidence"]["mutation_count"] == 1
        assert artifact["verification"]["evidence"]["mutation_requests"] == 1
        assert artifact["verification"]["evidence"]["duplicate_operation_requests"] == 0
        assert artifact["fault"]["triggered"] is True
        assert artifact["fault"]["observed"] is True
        assert artifact["fault"]["reconciled"] is True
        assert "fault" in events and "reconcile" in events
    else:
        raise AssertionError(f"unexpected RPF-28 reviewed profile: {expected_profile}")
    assert_event_contract(artifact)
    assert_private_boundary(artifact)
    return artifact


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
    suite = assert_rpf07_suite(RPF07_SUITE, regression, source_hash)
    baseline_document = json.loads(RPF07_BASELINE_RESULT.read_text(encoding="utf-8"))
    candidate_document = json.loads(RPF07_CANDIDATE_RESULT.read_text(encoding="utf-8"))
    baseline = assert_rpf07_evaluation(
        RPF07_BASELINE_RESULT,
        suite,
        regression,
        source_hash,
        "known-bad-unsafe-precondition-v1",
        baseline_document["evaluation"]["evaluation_id"],
        [json.loads(path.read_text(encoding="utf-8")) for path in RPF07_BASELINE_RUNS],
        RPF07_BASELINE_REGRESSION_RESULT,
        ["FAIL", "FAIL", "FAIL"],
    )
    candidate = assert_rpf07_evaluation(
        RPF07_CANDIDATE_RESULT,
        suite,
        regression,
        source_hash,
        "production-change-agent-v1-fixed",
        candidate_document["evaluation"]["evaluation_id"],
        [json.loads(path.read_text(encoding="utf-8")) for path in RPF07_CANDIDATE_RUNS],
        RPF07_CANDIDATE_REGRESSION_RESULT,
        ["PASS", "PASS", "PASS"],
    )
    assert_rpf07_regression_result(
        RPF07_BASELINE_REGRESSION_RESULT,
        regression,
        json.loads(RPF07_BASELINE_RUNS[2].read_text(encoding="utf-8")),
        "known-bad-unsafe-precondition-v1",
        "FAIL",
        baseline["evaluation"]["evaluation_id"],
    )
    assert_rpf07_regression_result(
        RPF07_CANDIDATE_REGRESSION_RESULT,
        regression,
        json.loads(RPF07_CANDIDATE_RUNS[2].read_text(encoding="utf-8")),
        "production-change-agent-v1-fixed",
        "PASS",
        candidate["evaluation"]["evaluation_id"],
    )
    assert_rpf07_comparison(RPF07_COMPARISON, baseline, candidate, suite, source_hash)
    policy = assert_rpf08_policy(RPF08_POLICY, suite, source_hash)
    assert_rpf08_gate(RPF08_BASELINE_GATE, policy, suite, "BLOCKED", source_hash)
    assert_rpf08_gate(RPF08_CANDIDATE_GATE, policy, suite, "ELIGIBLE", source_hash)
    baseline_decision = assert_rpf08_decision(RPF08_BASELINE_DECISION, "BLOCKED", "1.0.0-known-bad-unsafe-precondition", source_hash)
    candidate_decision = assert_rpf08_decision(RPF08_CANDIDATE_DECISION, "ELIGIBLE", "1.0.1-observe-before-mutation-fix", source_hash)
    assert {item["code"] for item in baseline_decision["release_decision"]["blocking_reasons"]} >= {"REQUIRED_MEMBER_AGENT_FAIL", "HISTORICAL_REGRESSION_FAIL"}
    assert candidate_decision["release_decision"]["soft_warnings"]
    assert_rpf28_artifact(RPF28_BASELINE, "none", source_hash)
    assert_rpf28_artifact(RPF28_DEPENDENCY_UNAVAILABLE, "dependency-unavailable", source_hash)
    assert_rpf28_artifact(RPF28_RESPONSE_LOST, "response-lost", source_hash)
    print(f"PASS: 2 historical v1 + 2 RPF-04 v2 + 3 RPF-05 runs + 3 RPF-06 runs + 6 RPF-07 runs + Suite/Evaluations/Comparison + 1 Policy/2 Gates/2 Decisions + 3 RPF-28 runs; source={source_hash}")


if __name__ == "__main__":
    main()

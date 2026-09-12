"""Deterministic Quality Policy, Release Gate, and Release Decision contracts.

RPF-08 deliberately evaluates the reviewed RPF-07 evidence locally.  It does
not call a Provider, mutate an Evaluation/Comparison/Regression artifact, or
perform a release action.  The module is intentionally a small, typed set of
stable rule handlers rather than a general policy language.
"""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Any, Sequence

from . import RUNTIME_VERSION
from .evaluation import (
    EVALUATION_CATEGORY_REGRESSION,
    EVALUATION_CATEGORY_RECOVERY,
    EVALUATION_RESULT_SCHEMA_VERSION,
    EVALUATION_SUITE_ID,
    EVALUATION_SUITE_VERSION,
    _suite_metadata,
    validate_comparison_artifact,
    validate_evaluation_artifact,
    validate_suite_artifact,
)
from .evidence import assert_safe_artifact, redact, runtime_source_sha256, timestamp
from .regression import validate_regression_artifact


QUALITY_POLICY_SCHEMA_VERSION = "rpf-quality-policy-v1"
QUALITY_GATE_SCHEMA_VERSION = "rpf-quality-gate-evaluation-v1"
RELEASE_DECISION_SCHEMA_VERSION = "rpf-release-decision-v1"
QUALITY_POLICY_ID = "rpf-minimal-release-policy"
QUALITY_POLICY_VERSION = "1.0.0"
QUALITY_POLICY_IDENTITY = f"{QUALITY_POLICY_ID}@{QUALITY_POLICY_VERSION}"
QUALITY_POLICY_ARTIFACT_KIND = "Quality Policy"
QUALITY_GATE_ARTIFACT_KIND = "Quality Gate Evaluation"
RELEASE_DECISION_ARTIFACT_KIND = "Release Decision"

RELEASE_STATUSES = {"ELIGIBLE", "BLOCKED", "REVIEW_REQUIRED", "INCONCLUSIVE"}
RULE_GATES = {"HARD", "SOFT", "REVIEW"}
RULE_STATUSES = {"PASS", "FAIL", "WARNING", "NOT_EVALUATED"}
RULE_EFFECTS = {"NONE", "BLOCK", "EVIDENCE_GAP", "REVIEW", "WARNING", "INVALID"}
DECISION_PRECEDENCE = ["HARD_BLOCKER", "EVIDENCE_INSUFFICIENT", "REVIEW_REQUIRED", "ELIGIBLE"]
UNKNOWN_VALUE_SEMANTICS = {"WARNING_NOT_ZERO", "INCONCLUSIVE", "NOT_APPLICABLE"}

RULE_REQUIRED_EVIDENCE_COVERAGE = "REQUIRED_EVIDENCE_COVERAGE"
RULE_REQUIRED_MEMBER_AGENT_FAIL = "NO_AGENT_FAIL_REQUIRED_MEMBERS"
RULE_HISTORICAL_REGRESSION_PASS = "HISTORICAL_REGRESSION_PASS"
RULE_RECOVERY_PASS = "RECOVERY_PASS"
RULE_EVIDENCE_CONTRACT = "VALID_EVIDENCE_CONTRACT"
RULE_IDENTITY_COMPATIBILITY = "COMPATIBLE_IDENTITIES"
RULE_UNKNOWN_USAGE = "UNKNOWN_USAGE_WARNING"
RULE_REVIEW_FLAG = "REVIEW_IF_FLAG"

HARD_RULE_IDS = {
    "required-evidence-coverage",
    "required-member-agent-fail",
    "historical-regression-pass",
    "recovery-pass",
    "valid-evidence-contract",
    "compatible-identities",
}

RULE_TYPE_GATE = {
    RULE_REQUIRED_EVIDENCE_COVERAGE: "HARD",
    RULE_REQUIRED_MEMBER_AGENT_FAIL: "HARD",
    RULE_HISTORICAL_REGRESSION_PASS: "HARD",
    RULE_RECOVERY_PASS: "HARD",
    RULE_EVIDENCE_CONTRACT: "HARD",
    RULE_IDENTITY_COMPATIBILITY: "HARD",
    RULE_UNKNOWN_USAGE: "SOFT",
    RULE_REVIEW_FLAG: "REVIEW",
}


class QualityContractError(ValueError):
    """A contract failure that prevents a usable Release Decision."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"MALFORMED_QUALITY:{label}")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"MALFORMED_QUALITY:{label}")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"MALFORMED_QUALITY:{label}")
    return value


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _policy_metadata(policy: dict[str, Any]) -> dict[str, Any]:
    return _object(policy.get("policy"), "policy")


def _suite_ref(suite: dict[str, Any]) -> dict[str, Any]:
    metadata = _suite_metadata(suite)
    return {
        "kind": "Evaluation Suite",
        "suite_id": metadata.get("suite_id"),
        "suite_version": metadata.get("suite_version"),
        "member_contract_digest": metadata.get("member_contract_digest"),
    }


def _policy_ref(policy: dict[str, Any]) -> dict[str, Any]:
    metadata = _policy_metadata(policy)
    return {
        "kind": QUALITY_POLICY_ARTIFACT_KIND,
        "policy_id": metadata.get("policy_id"),
        "policy_version": metadata.get("policy_version"),
        "policy_identity": metadata.get("policy_identity"),
    }


def _evaluation_ref(evaluation: dict[str, Any]) -> dict[str, Any]:
    metadata = _object(evaluation.get("evaluation"), "evaluation")
    return {
        "kind": "Evaluation Result",
        "evaluation_id": metadata.get("evaluation_id"),
    }


def _comparison_ref(comparison: dict[str, Any]) -> dict[str, Any]:
    metadata = _object(comparison.get("comparison"), "comparison")
    return {
        "kind": "Evaluation Comparison",
        "comparison_id": metadata.get("comparison_id"),
    }


def _regression_ref(regression: dict[str, Any]) -> dict[str, Any]:
    metadata = _object(regression.get("regression"), "regression")
    return {
        "kind": "Regression",
        "regression_id": metadata.get("regression_id"),
        "regression_version": metadata.get("regression_version"),
    }


def _source_identity(builder: str) -> dict[str, str]:
    return {
        "runtime_version": RUNTIME_VERSION,
        "source_sha256": runtime_source_sha256(),
        "builder": builder,
    }


def _canonical_rules() -> list[dict[str, Any]]:
    return [
        {
            "rule_id": "required-evidence-coverage",
            "rule_type": RULE_REQUIRED_EVIDENCE_COVERAGE,
            "gate": "HARD",
            "severity": "REQUIRED_EVIDENCE",
            "input_selector": "candidate.evaluation.summary.valid_evidence_coverage",
            "evaluation_semantics": "coverage_ratio >= minimum_coverage_ratio and every required member has valid Agent PASS/FAIL evidence",
            "missing_evidence_semantics": "INCONCLUSIVE",
            "description": "Required evidence coverage must meet the policy threshold.",
        },
        {
            "rule_id": "required-member-agent-fail",
            "rule_type": RULE_REQUIRED_MEMBER_AGENT_FAIL,
            "gate": "HARD",
            "severity": "BLOCKER",
            "input_selector": "candidate.evaluation.member_results",
            "evaluation_semantics": "No required member may contain a proven Agent FAIL.",
            "missing_evidence_semantics": "INCONCLUSIVE",
            "description": "A deterministic Agent failure blocks release consideration.",
        },
        {
            "rule_id": "historical-regression-pass",
            "rule_type": RULE_HISTORICAL_REGRESSION_PASS,
            "gate": "HARD",
            "severity": "BLOCKER",
            "input_selector": "candidate.evaluation.summary.regression",
            "evaluation_semantics": "The active Historical Regression member and its Regression oracle must PASS.",
            "missing_evidence_semantics": "INCONCLUSIVE",
            "description": "The active Historical Regression must remain green.",
        },
        {
            "rule_id": "recovery-pass",
            "rule_type": RULE_RECOVERY_PASS,
            "gate": "HARD",
            "severity": "BLOCKER",
            "input_selector": "candidate.evaluation.summary.fault_recovery",
            "evaluation_semantics": "The required Recovery/Fault member must PASS after planned/triggered/observed/reconciled evidence.",
            "missing_evidence_semantics": "INCONCLUSIVE",
            "description": "Recovery evidence must prove the planned Fault crossed and was reconciled.",
        },
        {
            "rule_id": "valid-evidence-contract",
            "rule_type": RULE_EVIDENCE_CONTRACT,
            "gate": "HARD",
            "severity": "REQUIRED_EVIDENCE",
            "input_selector": "candidate.evaluation.member_results",
            "evaluation_semantics": "Every required member has a valid evidence contract and stable Run reference.",
            "missing_evidence_semantics": "INCONCLUSIVE",
            "description": "Invalid evidence cannot be used as Release Evidence.",
        },
        {
            "rule_id": "compatible-identities",
            "rule_type": RULE_IDENTITY_COMPATIBILITY,
            "gate": "HARD",
            "severity": "REQUIRED_IDENTITY",
            "input_selector": "policy/suite/evaluation/comparison/regression identities",
            "evaluation_semantics": "All referenced identity and version contracts must match the selected snapshot.",
            "missing_evidence_semantics": "INVALID_POLICY_OR_EVIDENCE",
            "description": "A Release Decision may only use an explicitly compatible evidence snapshot.",
        },
        {
            "rule_id": "unknown-usage-warning",
            "rule_type": RULE_UNKNOWN_USAGE,
            "gate": "SOFT",
            "severity": "WARNING",
            "input_selector": "candidate.evaluation.summary.cost_token_latency",
            "evaluation_semantics": "Unknown token/cost/latency remains visible as a warning and is never coerced to zero.",
            "missing_evidence_semantics": "WARNING_NOT_ZERO",
            "description": "Provider usage gaps are non-blocking warnings under this Prototype policy.",
        },
    ]


def build_minimal_quality_policy(suite: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the frozen Prototype policy for the RPF-07 minimum Suite."""

    compatible_suite = {
        "kind": "Evaluation Suite",
        "suite_id": EVALUATION_SUITE_ID,
        "suite_version": EVALUATION_SUITE_VERSION,
    }
    required_member_ids = ["normal-functional", "response-lost-recovery", "historical-regression"]
    if suite is not None:
        metadata = _suite_metadata(suite)
        compatible_suite = {
            "kind": "Evaluation Suite",
            "suite_id": metadata.get("suite_id"),
            "suite_version": metadata.get("suite_version"),
            "member_contract_digest": metadata.get("member_contract_digest"),
        }
        required_member_ids = [
            str(member.get("member_id"))
            for member in metadata.get("members", [])
            if isinstance(member, dict) and member.get("required") is True
        ]
    return {
        "schema_version": QUALITY_POLICY_SCHEMA_VERSION,
        "artifact_kind": QUALITY_POLICY_ARTIFACT_KIND,
        "policy": {
            "policy_id": QUALITY_POLICY_ID,
            "policy_version": QUALITY_POLICY_VERSION,
            "policy_identity": QUALITY_POLICY_IDENTITY,
            "name": "Minimum Stateful Reliability Release Policy",
            "purpose": "Decide whether the current Candidate evidence is eligible for release consideration without executing release.",
            "compatible_suite": compatible_suite,
            "required_evidence": {
                "required_member_ids": required_member_ids,
                "required_member_count": len(required_member_ids),
                "minimum_coverage_ratio": 1.0,
                "valid_item_results": ["PASS", "FAIL"],
                "required_historical_regression": "PASS",
                "required_recovery_status": "RECOVERED",
            },
            "rules": _canonical_rules(),
            "decision_precedence": copy.deepcopy(DECISION_PRECEDENCE),
            "unknown_value_semantics": {
                "reported_tokens": "WARNING_NOT_ZERO",
                "derived_cost": "WARNING_NOT_ZERO",
                "latency": "WARNING_NOT_ZERO",
            },
            "source_identity": _source_identity("rpf-quality-policy-builder-v1"),
        },
    }


def validate_quality_policy(policy: dict[str, Any], suite: dict[str, Any] | None = None) -> list[str]:
    """Return explicit Policy contract errors without evaluating Agent quality."""

    errors: list[str] = []
    if policy.get("schema_version") != QUALITY_POLICY_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if policy.get("artifact_kind") != QUALITY_POLICY_ARTIFACT_KIND:
        errors.append("ARTIFACT_KIND")
    try:
        metadata = _policy_metadata(policy)
        for key in ("policy_id", "policy_version", "policy_identity", "name", "purpose", "compatible_suite", "required_evidence", "rules", "decision_precedence", "unknown_value_semantics", "source_identity"):
            if key not in metadata:
                errors.append(f"MISSING_{key.upper()}")
        if metadata.get("policy_identity") != f"{metadata.get('policy_id')}@{metadata.get('policy_version')}":
            errors.append("POLICY_IDENTITY")
        compatible = _object(metadata.get("compatible_suite"), "policy.compatible_suite")
        for key in ("kind", "suite_id", "suite_version"):
            if not compatible.get(key):
                errors.append(f"COMPATIBLE_SUITE_{key.upper()}")
        if compatible.get("kind") != "Evaluation Suite":
            errors.append("COMPATIBLE_SUITE_KIND")
        evidence = _object(metadata.get("required_evidence"), "policy.required_evidence")
        required_ids = _list(evidence.get("required_member_ids"), "policy.required_evidence.required_member_ids")
        if not required_ids or any(not isinstance(item, str) or not item for item in required_ids):
            errors.append("REQUIRED_MEMBER_IDS")
        if len(set(required_ids)) != len(required_ids):
            errors.append("DUPLICATE_REQUIRED_MEMBER_ID")
        if evidence.get("required_member_count") != len(required_ids):
            errors.append("REQUIRED_MEMBER_COUNT")
        coverage = _number(evidence.get("minimum_coverage_ratio"))
        if coverage is None or coverage < 0 or coverage > 1:
            errors.append("MINIMUM_COVERAGE_RATIO")
        valid_results = _list(evidence.get("valid_item_results"), "policy.valid_item_results")
        if set(valid_results) != {"PASS", "FAIL"}:
            errors.append("VALID_ITEM_RESULTS")
        if evidence.get("required_historical_regression") != "PASS":
            errors.append("HISTORICAL_REGRESSION_REQUIREMENT")
        if evidence.get("required_recovery_status") != "RECOVERED":
            errors.append("RECOVERY_REQUIREMENT")
        rules = _list(metadata.get("rules"), "policy.rules")
        seen_rule_ids: set[str] = set()
        present_hard_ids: set[str] = set()
        for rule in rules:
            if not isinstance(rule, dict):
                errors.append("RULE_NOT_OBJECT")
                continue
            rule_id = rule.get("rule_id")
            if not isinstance(rule_id, str) or not rule_id:
                errors.append("RULE_ID_MISSING")
                continue
            if rule_id in seen_rule_ids:
                errors.append(f"DUPLICATE_RULE_ID:{rule_id}")
            seen_rule_ids.add(rule_id)
            rule_type = rule.get("rule_type")
            if rule_type not in RULE_TYPE_GATE:
                errors.append(f"UNKNOWN_RULE_TYPE:{rule_id}")
                continue
            expected_gate = RULE_TYPE_GATE[rule_type]
            if rule.get("gate") != expected_gate:
                errors.append(f"RULE_GATE_MISMATCH:{rule_id}")
            for key in ("severity", "input_selector", "evaluation_semantics", "missing_evidence_semantics", "description"):
                if not isinstance(rule.get(key), str) or not rule.get(key):
                    errors.append(f"RULE_{key.upper()}_MISSING:{rule_id}")
            if expected_gate == "HARD":
                present_hard_ids.add(rule_id)
            if rule_type == RULE_REVIEW_FLAG and not str(rule.get("input_selector", "")).startswith("candidate.evaluation."):
                errors.append(f"REVIEW_SELECTOR_UNSUPPORTED:{rule_id}")
        for rule_id in sorted(HARD_RULE_IDS - present_hard_ids):
            errors.append(f"MISSING_HARD_REQUIREMENT:{rule_id}")
        precedence = metadata.get("decision_precedence")
        if precedence != DECISION_PRECEDENCE:
            errors.append("INVALID_PRECEDENCE")
        unknown = _object(metadata.get("unknown_value_semantics"), "policy.unknown_value_semantics")
        for key in ("reported_tokens", "derived_cost", "latency"):
            if unknown.get(key) not in UNKNOWN_VALUE_SEMANTICS:
                errors.append(f"AMBIGUOUS_UNKNOWN_SEMANTICS:{key}")
        source = _object(metadata.get("source_identity"), "policy.source_identity")
        for key in ("runtime_version", "source_sha256", "builder"):
            if not source.get(key):
                errors.append(f"SOURCE_IDENTITY:{key}")
        if suite is not None:
            suite_errors = validate_suite_artifact(suite)
            if suite_errors:
                errors.extend(f"SUITE_{error}" for error in suite_errors)
            suite_ref = _suite_ref(suite)
            for key in ("kind", "suite_id", "suite_version"):
                if compatible.get(key) != suite_ref.get(key):
                    errors.append(f"COMPATIBLE_SUITE_{key.upper()}_MISMATCH")
            if "member_contract_digest" in compatible and compatible.get("member_contract_digest") != suite_ref.get("member_contract_digest"):
                errors.append("COMPATIBLE_SUITE_MEMBER_CONTRACT_DIGEST_MISMATCH")
            required_suite_ids = [
                member.get("member_id")
                for member in _suite_metadata(suite).get("members", [])
                if isinstance(member, dict) and member.get("required") is True
            ]
            if required_ids != required_suite_ids:
                errors.append("REQUIRED_MEMBER_IDS_SUITE_MISMATCH")
    except (ValueError, TypeError, KeyError):
        errors.append("MALFORMED_FIELDS")
    return errors


def _item_evidence_refs(evaluation: dict[str, Any], item: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _object(evaluation.get("evaluation"), "evaluation")
    evaluation_id = metadata.get("evaluation_id")
    member_id = item.get("member_id")
    refs: list[dict[str, Any]] = [
        {"kind": "Evaluation Result", "evaluation_id": evaluation_id, "member_id": member_id},
    ]
    run_ref = item.get("run_ref")
    if isinstance(run_ref, dict) and isinstance(run_ref.get("run_id"), str):
        refs.append({"kind": "Run Evidence", "run_id": run_ref["run_id"]})
    for evidence_ref in item.get("evidence_refs", []):
        if not isinstance(evidence_ref, dict):
            continue
        ref = evidence_ref.get("ref")
        if isinstance(ref, dict):
            refs.append({"role": evidence_ref.get("role"), "ref": copy.deepcopy(ref)})
    result_ref = item.get("regression_result_ref")
    if isinstance(result_ref, dict):
        refs.append(copy.deepcopy(result_ref))
    return refs


def _required_items(evaluation: dict[str, Any], required_ids: Sequence[str]) -> list[dict[str, Any]]:
    metadata = _object(evaluation.get("evaluation"), "evaluation")
    items = [item for item in _list(metadata.get("member_results"), "evaluation.member_results") if isinstance(item, dict)]
    by_id = {str(item.get("member_id")): item for item in items}
    return [by_id[member_id] for member_id in required_ids if member_id in by_id]


def _item_by_category(evaluation: dict[str, Any], category: str) -> dict[str, Any] | None:
    metadata = _object(evaluation.get("evaluation"), "evaluation")
    for item in _list(metadata.get("member_results"), "evaluation.member_results"):
        if isinstance(item, dict) and item.get("category") == category:
            return item
    return None


def _reason_record(rule: dict[str, Any], code: str, reason: str, refs: list[dict[str, Any]], facts: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "rule_id": rule.get("rule_id"),
        "rule_type": rule.get("rule_type"),
        "code": code,
        "reason": reason,
        "evidence_refs": copy.deepcopy(refs),
        **({"facts": copy.deepcopy(facts)} if facts is not None else {}),
    }


def _rule_result(
    rule: dict[str, Any],
    status: str,
    effect: str,
    *,
    reasons: list[str] | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule.get("rule_id"),
        "rule_type": rule.get("rule_type"),
        "rule_gate": rule.get("gate"),
        "severity": rule.get("severity"),
        "status": status,
        "effect": effect,
        "input_selector": rule.get("input_selector"),
        "evaluation_semantics": rule.get("evaluation_semantics"),
        "missing_evidence_semantics": rule.get("missing_evidence_semantics"),
        "reasons": reasons or [],
        "evidence_refs": evidence_refs or [],
        "facts": facts or {},
    }


def _identity_errors(
    policy: dict[str, Any],
    suite: dict[str, Any],
    candidate: dict[str, Any],
    baseline: dict[str, Any] | None,
    comparison: dict[str, Any],
    regression: dict[str, Any],
    subject: str = "CANDIDATE",
) -> list[str]:
    errors: list[str] = []
    policy_meta = _policy_metadata(policy)
    suite_meta = _suite_metadata(suite)
    suite_ref = _suite_ref(suite)
    compatible = _object(policy_meta.get("compatible_suite"), "policy.compatible_suite")
    for key in ("kind", "suite_id", "suite_version"):
        if compatible.get(key) != suite_ref.get(key):
            errors.append(f"POLICY_SUITE_{key.upper()}_MISMATCH")
    if compatible.get("member_contract_digest") and compatible.get("member_contract_digest") != suite_ref.get("member_contract_digest"):
        errors.append("POLICY_SUITE_MEMBER_CONTRACT_DIGEST_MISMATCH")
    required_ids = _list(_object(policy_meta.get("required_evidence"), "policy.required_evidence").get("required_member_ids"), "required member ids")
    for label, evaluation in (("CANDIDATE", candidate), ("BASELINE", baseline)):
        if evaluation is None:
            continue
        metadata = _object(evaluation.get("evaluation"), f"{label}.evaluation")
        if metadata.get("suite_ref") != suite_ref:
            errors.append(f"{label}_SUITE_REF_MISMATCH")
    comparison_meta = _object(comparison.get("comparison"), "comparison")
    if comparison_meta.get("status") != "COMPLETE":
        errors.append("COMPARISON_NOT_COMPLETE")
    if comparison_meta.get("suite_ref") != suite_ref:
        errors.append("COMPARISON_SUITE_REF_MISMATCH")
    candidate_meta = _object(candidate.get("evaluation"), "candidate.evaluation")
    comparison_side = "candidate" if subject == "CANDIDATE" else "baseline"
    comparison_subject = comparison_meta.get(comparison_side)
    if not isinstance(comparison_subject, dict):
        errors.append(f"COMPARISON_{comparison_side.upper()}_REF_MISSING")
    elif comparison_subject.get("evaluation_id") != candidate_meta.get("evaluation_id"):
        errors.append(f"COMPARISON_{comparison_side.upper()}_EVALUATION_MISMATCH")
    elif isinstance(comparison_subject.get("agent"), dict) and comparison_subject.get("agent") != candidate_meta.get("agent"):
        errors.append(f"COMPARISON_{comparison_side.upper()}_AGENT_MISMATCH")
    if baseline is not None:
        baseline_meta = _object(baseline.get("evaluation"), "baseline.evaluation")
        expected_side = "baseline" if subject == "CANDIDATE" else "candidate"
        comparison_expected = comparison_meta.get(expected_side)
        if not isinstance(comparison_expected, dict):
            errors.append(f"COMPARISON_{expected_side.upper()}_REF_MISSING")
        elif comparison_expected.get("evaluation_id") != baseline_meta.get("evaluation_id"):
            errors.append(f"COMPARISON_{expected_side.upper()}_EVALUATION_MISMATCH")
        elif isinstance(comparison_expected.get("agent"), dict) and comparison_expected.get("agent") != baseline_meta.get("agent"):
            errors.append(f"COMPARISON_{expected_side.upper()}_AGENT_MISMATCH")
        if baseline_meta.get("agent", {}).get("agent_version") == candidate_meta.get("agent", {}).get("agent_version"):
            errors.append("BASELINE_CANDIDATE_AGENT_VERSION_SAME")
    regression_meta = _object(regression.get("regression"), "regression")
    historical_member = next(
        (member for member in suite_meta.get("members", []) if isinstance(member, dict) and member.get("category") == EVALUATION_CATEGORY_REGRESSION),
        None,
    )
    expected_regression_ref = historical_member.get("regression_ref") if isinstance(historical_member, dict) else None
    if expected_regression_ref != _regression_ref(regression):
        errors.append("SUITE_REGRESSION_REF_MISMATCH")
    if not regression_meta.get("regression_id") or not regression_meta.get("regression_version"):
        errors.append("REGRESSION_IDENTITY_MISSING")
    return errors


def _evaluate_rule(
    rule: dict[str, Any],
    policy: dict[str, Any],
    suite: dict[str, Any],
    candidate: dict[str, Any],
    baseline: dict[str, Any] | None,
    comparison: dict[str, Any],
    regression: dict[str, Any],
    *,
    subject: str = "CANDIDATE",
) -> dict[str, Any]:
    metadata = _policy_metadata(policy)
    required = _object(metadata.get("required_evidence"), "policy.required_evidence")
    required_ids = [str(item) for item in required.get("required_member_ids", [])]
    items = _required_items(candidate, required_ids)
    if rule.get("rule_type") == RULE_REQUIRED_EVIDENCE_COVERAGE:
        summary = _object(_object(candidate.get("evaluation"), "candidate.evaluation").get("summary"), "candidate.summary")
        coverage = _object(summary.get("valid_evidence_coverage"), "candidate.coverage")
        ratio = coverage.get("coverage_ratio")
        valid_count = coverage.get("valid_evidence_item_count")
        required_count = coverage.get("required_item_count")
        facts = {"coverage_ratio": ratio, "valid_evidence_item_count": valid_count, "required_item_count": required_count, "minimum_coverage_ratio": required.get("minimum_coverage_ratio")}
        if isinstance(ratio, (int, float)) and ratio >= required.get("minimum_coverage_ratio", 1.0) and valid_count == required_count == len(required_ids):
            return _rule_result(rule, "PASS", "NONE", facts=facts)
        refs = [_evaluation_ref(candidate)] + [ref for item in items for ref in _item_evidence_refs(candidate, item)]
        return _rule_result(rule, "FAIL", "EVIDENCE_GAP", reasons=["REQUIRED_EVIDENCE_COVERAGE_INSUFFICIENT"], evidence_refs=refs, facts=facts)

    if rule.get("rule_type") == RULE_REQUIRED_MEMBER_AGENT_FAIL:
        failures = [item for item in items if item.get("item_result") == "FAIL" and item.get("attribution") == "Agent"]
        refs = [ref for item in failures for ref in _item_evidence_refs(candidate, item)]
        facts = {"agent_fail_member_ids": [item.get("member_id") for item in failures], "required_member_count": len(required_ids)}
        if failures:
            return _rule_result(rule, "FAIL", "BLOCK", reasons=["REQUIRED_MEMBER_AGENT_FAIL"], evidence_refs=refs, facts=facts)
        return _rule_result(rule, "PASS", "NONE", facts=facts)

    if rule.get("rule_type") == RULE_HISTORICAL_REGRESSION_PASS:
        item = _item_by_category(candidate, EVALUATION_CATEGORY_REGRESSION)
        refs = _item_evidence_refs(candidate, item) if item else [_evaluation_ref(candidate)]
        facts = {
            "member_id": item.get("member_id") if item else None,
            "item_result": item.get("item_result") if item else None,
            "regression_result": item.get("regression_result") if item else None,
            "run_outcome": item.get("run_outcome") if item else None,
            "regression_ref": item.get("regression_ref") if item else None,
        }
        if item and item.get("item_result") == "PASS" and item.get("regression_result") == "PASS" and item.get("valid_quality_evidence") is True:
            return _rule_result(rule, "PASS", "NONE", facts=facts)
        if item and item.get("item_result") == "FAIL":
            return _rule_result(rule, "FAIL", "BLOCK", reasons=["HISTORICAL_REGRESSION_FAIL"], evidence_refs=refs, facts=facts)
        return _rule_result(rule, "FAIL", "EVIDENCE_GAP", reasons=["HISTORICAL_REGRESSION_EVIDENCE_INSUFFICIENT"], evidence_refs=refs, facts=facts)

    if rule.get("rule_type") == RULE_RECOVERY_PASS:
        item = _item_by_category(candidate, EVALUATION_CATEGORY_RECOVERY)
        refs = _item_evidence_refs(candidate, item) if item else [_evaluation_ref(candidate)]
        fault = item.get("fault") if item and isinstance(item.get("fault"), dict) else {}
        facts = {
            "member_id": item.get("member_id") if item else None,
            "item_result": item.get("item_result") if item else None,
            "recovery_status": item.get("recovery_status") if item else None,
            "fault": copy.deepcopy(fault),
        }
        recovered = bool(item and item.get("item_result") == "PASS" and item.get("valid_quality_evidence") is True and item.get("recovery_status") == required.get("required_recovery_status") and all(fault.get(key) is True for key in ("planned", "triggered", "observed", "reconciled")))
        if recovered:
            return _rule_result(rule, "PASS", "NONE", facts=facts)
        if item and item.get("item_result") == "FAIL" and item.get("attribution") == "Agent":
            return _rule_result(rule, "FAIL", "BLOCK", reasons=["REQUIRED_RECOVERY_AGENT_FAIL"], evidence_refs=refs, facts=facts)
        return _rule_result(rule, "FAIL", "EVIDENCE_GAP", reasons=["RECOVERY_EVIDENCE_INSUFFICIENT"], evidence_refs=refs, facts=facts)

    if rule.get("rule_type") == RULE_EVIDENCE_CONTRACT:
        invalid: list[dict[str, Any]] = []
        for member_id in required_ids:
            item = next((candidate_item for candidate_item in items if candidate_item.get("member_id") == member_id), None)
            reasons: list[str] = []
            if item is None:
                reasons.append("REQUIRED_MEMBER_MISSING")
            else:
                if item.get("valid_quality_evidence") is not True:
                    reasons.append("VALID_QUALITY_EVIDENCE_FALSE")
                if item.get("valid_evidence_status") != "VALID":
                    reasons.append("VALID_EVIDENCE_STATUS_NOT_VALID")
                if item.get("item_result") not in {"PASS", "FAIL"}:
                    reasons.append("ITEM_RESULT_NOT_PASS_OR_FAIL")
                if not isinstance(item.get("run_ref"), dict) or not item["run_ref"].get("run_id"):
                    reasons.append("RUN_REF_MISSING")
                if not isinstance(item.get("evidence_refs"), list):
                    reasons.append("EVIDENCE_REFS_MISSING")
            if reasons:
                invalid.append({"member_id": member_id, "reasons": reasons})
        refs = [_evaluation_ref(candidate)]
        for item in items:
            refs.extend(_item_evidence_refs(candidate, item))
        facts = {"invalid_required_members": invalid, "required_member_count": len(required_ids), "valid_required_member_count": len(required_ids) - len(invalid)}
        if invalid:
            return _rule_result(rule, "FAIL", "EVIDENCE_GAP", reasons=["INVALID_OR_MISSING_REQUIRED_EVIDENCE"], evidence_refs=refs, facts=facts)
        return _rule_result(rule, "PASS", "NONE", facts=facts)

    if rule.get("rule_type") == RULE_IDENTITY_COMPATIBILITY:
        errors = _identity_errors(policy, suite, candidate, baseline, comparison, regression, subject)
        facts = {"identity_errors": errors, "policy_ref": _policy_ref(policy), "suite_ref": _suite_ref(suite), "candidate_evaluation_ref": _evaluation_ref(candidate), "comparison_ref": _comparison_ref(comparison), "regression_ref": _regression_ref(regression)}
        if errors:
            return _rule_result(rule, "FAIL", "INVALID", reasons=["IDENTITY_CONTRACT_MISMATCH"], evidence_refs=[_policy_ref(policy), _suite_ref(suite), _evaluation_ref(candidate), _comparison_ref(comparison), _regression_ref(regression)], facts=facts)
        return _rule_result(rule, "PASS", "NONE", facts=facts)

    if rule.get("rule_type") == RULE_UNKNOWN_USAGE:
        summary = _object(_object(candidate.get("evaluation"), "candidate.evaluation").get("summary"), "candidate.summary")
        metrics = _object(summary.get("cost_token_latency"), "candidate.metrics")
        latency = _object(metrics.get("latency"), "candidate.latency")
        unknown = {
            "reported_tokens": metrics.get("reported_token_usage_sum") is None,
            "derived_cost": metrics.get("derived_cost_sum") is None,
            "latency": latency.get("total_observed_runtime_ms") is None,
        }
        facts = {"unknown_metrics": unknown, "unknown_values_are_not_zero": metrics.get("unknown_values_are_not_zero") is True}
        if any(unknown.values()):
            return _rule_result(rule, "WARNING", "WARNING", reasons=["PROVIDER_USAGE_OR_LATENCY_UNKNOWN"], evidence_refs=[_evaluation_ref(candidate)], facts=facts)
        return _rule_result(rule, "PASS", "NONE", facts=facts)

    if rule.get("rule_type") == RULE_REVIEW_FLAG:
        selector = str(rule.get("input_selector", ""))
        field = selector.removeprefix("candidate.evaluation.")
        value: Any = _object(candidate.get("evaluation"), "candidate.evaluation")
        for part in field.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        facts = {"selector": selector, "value": value, "trigger_value": rule.get("trigger_value", True)}
        if value is rule.get("trigger_value", True):
            return _rule_result(rule, "FAIL", "REVIEW", reasons=["REVIEW_RULE_TRIGGERED"], evidence_refs=[_evaluation_ref(candidate)], facts=facts)
        return _rule_result(rule, "NOT_EVALUATED", "NONE", facts=facts)

    return _rule_result(rule, "FAIL", "INVALID", reasons=["UNSUPPORTED_RULE_HANDLER"])


def _decision_reasons(rule_results: Sequence[dict[str, Any]], effect: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for result in rule_results:
        if result.get("effect") != effect:
            continue
        for reason in result.get("reasons", []) or ["RULE_TRIGGERED"]:
            records.append(_reason_record(result, str(reason), str(reason), result.get("evidence_refs", []), result.get("facts")))
    return records


def _coverage_facts(evaluation: dict[str, Any]) -> dict[str, Any]:
    metadata = _object(evaluation.get("evaluation"), "evaluation")
    summary = _object(metadata.get("summary"), "evaluation.summary")
    return copy.deepcopy(_object(summary.get("valid_evidence_coverage"), "evaluation.coverage"))


def _regression_facts(evaluation: dict[str, Any]) -> dict[str, Any]:
    metadata = _object(evaluation.get("evaluation"), "evaluation")
    summary = _object(metadata.get("summary"), "evaluation.summary")
    return copy.deepcopy(_object(summary.get("regression"), "evaluation.regression"))


def _recovery_facts(evaluation: dict[str, Any]) -> dict[str, Any]:
    metadata = _object(evaluation.get("evaluation"), "evaluation")
    summary = _object(metadata.get("summary"), "evaluation.summary")
    return copy.deepcopy(_object(summary.get("fault_recovery"), "evaluation.fault_recovery"))


def evaluate_quality_gate(
    policy: dict[str, Any],
    suite: dict[str, Any],
    candidate: dict[str, Any],
    baseline: dict[str, Any] | None,
    comparison: dict[str, Any],
    regression: dict[str, Any],
    *,
    gate_evaluation_id: str | None = None,
    evaluated_at: str | None = None,
    subject: str = "CANDIDATE",
) -> dict[str, Any]:
    """Evaluate a Quality Gate without mutating any input artifact."""

    if subject not in {"CANDIDATE", "BASELINE"}:
        raise QualityContractError(f"UNKNOWN_DECISION_SUBJECT:{subject}")
    policy_errors = validate_quality_policy(policy, suite)
    suite_errors = validate_suite_artifact(suite, regression)
    candidate_errors = validate_evaluation_artifact(candidate)
    baseline_errors = validate_evaluation_artifact(baseline) if baseline is not None else []
    comparison_errors = validate_comparison_artifact(comparison)
    regression_errors = validate_regression_artifact(regression)
    validation_errors = [f"POLICY_{error}" for error in policy_errors]
    validation_errors.extend(f"SUITE_{error}" for error in suite_errors)
    validation_errors.extend(f"CANDIDATE_{error}" for error in candidate_errors)
    validation_errors.extend(f"BASELINE_{error}" for error in baseline_errors)
    validation_errors.extend(f"COMPARISON_{error}" for error in comparison_errors)
    validation_errors.extend(f"REGRESSION_{error}" for error in regression_errors)
    if subject == "CANDIDATE" and baseline is None:
        validation_errors.append("BASELINE_EVALUATION_REQUIRED")
    gate_evaluation_id = gate_evaluation_id or f"gate-evaluation-{uuid.uuid4()}"
    evaluated_at = evaluated_at or timestamp()
    policy_meta = policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
    suite_meta = suite.get("suite") if isinstance(suite.get("suite"), dict) else {}
    candidate_meta = candidate.get("evaluation") if isinstance(candidate.get("evaluation"), dict) else {}
    baseline_meta = baseline.get("evaluation") if baseline and isinstance(baseline.get("evaluation"), dict) else {}
    comparison_meta = comparison.get("comparison") if isinstance(comparison.get("comparison"), dict) else {}
    compared_candidate = comparison_meta.get("candidate") if isinstance(comparison_meta.get("candidate"), dict) else {}
    compared_baseline = comparison_meta.get("baseline") if isinstance(comparison_meta.get("baseline"), dict) else {}
    compared_candidate_agent = compared_candidate.get("agent")
    compared_baseline_agent = compared_baseline.get("agent")
    compared_candidate_id = compared_candidate.get("evaluation_id")
    compared_baseline_id = compared_baseline.get("evaluation_id")
    evaluated_agent = copy.deepcopy(candidate_meta.get("agent")) if candidate_meta else {}
    if subject == "CANDIDATE":
        candidate_agent = copy.deepcopy(evaluated_agent)
        baseline_agent = copy.deepcopy(baseline_meta.get("agent")) if baseline_meta else None
        candidate_evaluation_ref = _evaluation_ref(candidate) if not candidate_errors else None
        baseline_evaluation_ref = _evaluation_ref(baseline) if baseline is not None and not baseline_errors else None
    else:
        candidate_agent = copy.deepcopy(compared_candidate_agent) if isinstance(compared_candidate_agent, dict) else None
        baseline_agent = copy.deepcopy(evaluated_agent)
        candidate_evaluation_ref = {"kind": "Evaluation Result", "evaluation_id": compared_candidate_id} if isinstance(compared_candidate_id, str) and compared_candidate_id else None
        baseline_evaluation_ref = _evaluation_ref(candidate) if not candidate_errors else None
    base_metadata: dict[str, Any] = {
        "gate_evaluation_id": gate_evaluation_id,
        "evaluated_at": evaluated_at,
        "status": "INVALID" if validation_errors else "COMPLETE",
        "decision_subject": subject,
        "policy_ref": _policy_ref(policy) if not policy_errors else None,
        "suite_ref": _suite_ref(suite) if not suite_errors else None,
        "agent_under_evaluation": evaluated_agent,
        "candidate_agent": candidate_agent,
        "baseline_agent": baseline_agent,
        "subject_evaluation_ref": _evaluation_ref(candidate) if not candidate_errors else None,
        "candidate_evaluation_ref": candidate_evaluation_ref,
        "baseline_evaluation_ref": baseline_evaluation_ref,
        "comparison_ref": _comparison_ref(comparison) if not comparison_errors else None,
        "regression_ref": _regression_ref(regression) if not regression_errors else None,
        "decision_status": None,
        "rule_results": [],
        "blocking_reasons": [],
        "evidence_gap_reasons": [],
        "review_reasons": [],
        "soft_warnings": [],
        "coverage_facts": {},
        "regression_facts": {},
        "recovery_facts": {},
        "validation_errors": validation_errors,
        "authorization_boundary": {"release_executed": False, "deployment_authorized": False, "release_action": "DECISION_ONLY"},
        "source_identity": _source_identity("rpf-quality-gate-evaluator-v1"),
    }
    if validation_errors:
        base_metadata["validation_errors"] = validation_errors
    else:
        identity_errors = _identity_errors(policy, suite, candidate, baseline, comparison, regression, subject)
        if identity_errors:
            validation_errors.extend(f"IDENTITY_{error}" for error in identity_errors)
            base_metadata["validation_errors"] = validation_errors
            base_metadata["status"] = "INVALID"
        else:
            results = []
            for rule in _list(policy_meta.get("rules"), "policy.rules"):
                if isinstance(rule, dict):
                    results.append(_evaluate_rule(rule, policy, suite, candidate, baseline, comparison, regression, subject=subject))
            base_metadata["rule_results"] = results
            base_metadata["coverage_facts"] = _coverage_facts(candidate)
            base_metadata["regression_facts"] = _regression_facts(candidate)
            base_metadata["recovery_facts"] = _recovery_facts(candidate)
            base_metadata["blocking_reasons"] = _decision_reasons(results, "BLOCK")
            base_metadata["evidence_gap_reasons"] = _decision_reasons(results, "EVIDENCE_GAP")
            base_metadata["review_reasons"] = _decision_reasons(results, "REVIEW")
            base_metadata["soft_warnings"] = _decision_reasons(results, "WARNING")
            if base_metadata["blocking_reasons"]:
                base_metadata["decision_status"] = "BLOCKED"
            elif base_metadata["evidence_gap_reasons"]:
                base_metadata["decision_status"] = "INCONCLUSIVE"
            elif base_metadata["review_reasons"]:
                base_metadata["decision_status"] = "REVIEW_REQUIRED"
            else:
                base_metadata["decision_status"] = "ELIGIBLE"
            base_metadata["gate_status"] = base_metadata["decision_status"]
    if base_metadata.get("status") == "INVALID":
        base_metadata["gate_status"] = "INVALID"
    return {
        "schema_version": QUALITY_GATE_SCHEMA_VERSION,
        "artifact_kind": QUALITY_GATE_ARTIFACT_KIND,
        "gate_evaluation": base_metadata,
    }


def validate_quality_gate_artifact(gate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if gate.get("schema_version") != QUALITY_GATE_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if gate.get("artifact_kind") != QUALITY_GATE_ARTIFACT_KIND:
        errors.append("ARTIFACT_KIND")
    try:
        metadata = _object(gate.get("gate_evaluation"), "gate_evaluation")
        status = metadata.get("status")
        if status not in {"COMPLETE", "INVALID"}:
            errors.append("STATUS")
        boundary = _object(metadata.get("authorization_boundary"), "authorization_boundary")
        if boundary.get("release_executed") is not False or boundary.get("deployment_authorized") is not False:
            errors.append("AUTHORIZATION_BOUNDARY")
        if status == "INVALID":
            if not isinstance(metadata.get("validation_errors"), list) or not metadata["validation_errors"]:
                errors.append("INVALID_REASONS_MISSING")
            if metadata.get("decision_status") is not None:
                errors.append("INVALID_DECISION_PRESENT")
            return errors
        for key in ("gate_evaluation_id", "evaluated_at", "policy_ref", "suite_ref", "candidate_agent", "candidate_evaluation_ref", "comparison_ref", "regression_ref", "decision_status", "rule_results", "blocking_reasons", "evidence_gap_reasons", "review_reasons", "soft_warnings", "coverage_facts", "regression_facts", "recovery_facts", "source_identity"):
            if key not in metadata:
                errors.append(f"MISSING_{key.upper()}")
        if metadata.get("decision_status") not in RELEASE_STATUSES:
            errors.append("DECISION_STATUS")
        rule_results = _list(metadata.get("rule_results"), "gate.rule_results")
        ids: set[str] = set()
        for result in rule_results:
            if not isinstance(result, dict):
                errors.append("RULE_RESULT_NOT_OBJECT")
                continue
            rule_id = result.get("rule_id")
            if not isinstance(rule_id, str) or not rule_id or rule_id in ids:
                errors.append(f"RULE_RESULT_ID:{rule_id}")
            ids.add(str(rule_id))
            if result.get("rule_gate") not in RULE_GATES:
                errors.append(f"RULE_GATE:{rule_id}")
            if result.get("status") not in RULE_STATUSES:
                errors.append(f"RULE_STATUS:{rule_id}")
            if result.get("effect") not in RULE_EFFECTS:
                errors.append(f"RULE_EFFECT:{rule_id}")
            if not isinstance(result.get("evidence_refs"), list) or not isinstance(result.get("reasons"), list):
                errors.append(f"RULE_DIAGNOSTICS:{rule_id}")
        for key in ("blocking_reasons", "evidence_gap_reasons", "review_reasons", "soft_warnings"):
            if not isinstance(metadata.get(key), list):
                errors.append(f"DIAGNOSTICS_{key.upper()}")
        source = _object(metadata.get("source_identity"), "gate.source_identity")
        for key in ("runtime_version", "source_sha256", "builder"):
            if not source.get(key):
                errors.append(f"SOURCE_IDENTITY:{key}")
        blocking = metadata.get("blocking_reasons", [])
        gaps = metadata.get("evidence_gap_reasons", [])
        reviews = metadata.get("review_reasons", [])
        expected = "BLOCKED" if blocking else "INCONCLUSIVE" if gaps else "REVIEW_REQUIRED" if reviews else "ELIGIBLE"
        if metadata.get("decision_status") != expected:
            errors.append("PRECEDENCE_RESULT_MISMATCH")
    except (ValueError, TypeError, KeyError):
        errors.append("MALFORMED_FIELDS")
    return errors


def build_release_decision(
    gate: dict[str, Any],
    *,
    release_decision_id: str | None = None,
    decision_timestamp: str | None = None,
    supersedes_decision_id: str | None = None,
) -> dict[str, Any]:
    """Create an immutable decision from a valid Gate Evaluation."""

    gate_errors = validate_quality_gate_artifact(gate)
    if gate_errors:
        raise QualityContractError("INVALID_GATE:" + ",".join(gate_errors))
    metadata = _object(gate.get("gate_evaluation"), "gate_evaluation")
    if metadata.get("status") != "COMPLETE" or metadata.get("decision_status") not in RELEASE_STATUSES:
        raise QualityContractError("INVALID_GATE_NOT_DECISION_READY")
    release_decision_id = release_decision_id or f"release-decision-{uuid.uuid4()}"
    decision_timestamp = decision_timestamp or timestamp()
    evaluated_agent = _object(metadata.get("agent_under_evaluation"), "agent_under_evaluation")
    candidate_agent = metadata.get("candidate_agent")
    if candidate_agent is not None:
        candidate_agent = copy.deepcopy(_object(candidate_agent, "candidate_agent"))
    baseline_agent = metadata.get("baseline_agent")
    if baseline_agent is not None:
        baseline_agent = copy.deepcopy(_object(baseline_agent, "baseline_agent"))
    return {
        "schema_version": RELEASE_DECISION_SCHEMA_VERSION,
        "artifact_kind": RELEASE_DECISION_ARTIFACT_KIND,
        "release_decision": {
            "release_decision_id": release_decision_id,
            "decision_timestamp": decision_timestamp,
            "decision_status": metadata.get("decision_status"),
            "evaluated_agent": copy.deepcopy(evaluated_agent),
            "evaluated_agent_version": evaluated_agent.get("agent_version"),
            "decision_subject": metadata.get("decision_subject"),
            "candidate_agent": candidate_agent,
            "candidate_agent_version": candidate_agent.get("agent_version") if candidate_agent else None,
            "baseline_agent": baseline_agent,
            "baseline_agent_version": baseline_agent.get("agent_version") if baseline_agent else None,
            "policy_ref": copy.deepcopy(metadata.get("policy_ref")),
            "suite_ref": copy.deepcopy(metadata.get("suite_ref")),
            "candidate_evaluation_ref": copy.deepcopy(metadata.get("candidate_evaluation_ref")),
            "baseline_evaluation_ref": copy.deepcopy(metadata.get("baseline_evaluation_ref")),
            "comparison_ref": copy.deepcopy(metadata.get("comparison_ref")),
            "gate_evaluation_ref": {
                "kind": QUALITY_GATE_ARTIFACT_KIND,
                "gate_evaluation_id": metadata.get("gate_evaluation_id"),
            },
            "regression_ref": copy.deepcopy(metadata.get("regression_ref")),
            "blocking_reasons": copy.deepcopy(metadata.get("blocking_reasons", [])),
            "review_reasons": copy.deepcopy(metadata.get("review_reasons", [])),
            "soft_warnings": copy.deepcopy(metadata.get("soft_warnings", [])),
            "evidence_gap_reasons": copy.deepcopy(metadata.get("evidence_gap_reasons", [])),
            "valid_evidence_coverage": copy.deepcopy(metadata.get("coverage_facts", {})),
            "historical_regression": copy.deepcopy(metadata.get("regression_facts", {})),
            "recovery_fault": copy.deepcopy(metadata.get("recovery_facts", {})),
            "evidence_refs": [
                *[reason for reason in metadata.get("blocking_reasons", [])],
                *[reason for reason in metadata.get("evidence_gap_reasons", [])],
                *[reason for reason in metadata.get("review_reasons", [])],
            ],
            "authorization_boundary": {
                "release_executed": False,
                "deployment_authorized": False,
                "release_action": "DECISION_ONLY",
                "authority_holder": "Quality Policy evaluation, not Agent/runtime",
            },
            "history": {
                "immutable": True,
                "supersedes_decision_id": supersedes_decision_id,
                "superseding_rule": "Later evidence or Policy versions create a new Decision; this artifact is not overwritten.",
            },
            "source_identity": _source_identity("rpf-release-decision-builder-v1"),
        },
    }


def validate_release_decision_artifact(decision: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if decision.get("schema_version") != RELEASE_DECISION_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    if decision.get("artifact_kind") != RELEASE_DECISION_ARTIFACT_KIND:
        errors.append("ARTIFACT_KIND")
    try:
        metadata = _object(decision.get("release_decision"), "release_decision")
        required_keys = (
            "release_decision_id",
            "decision_timestamp",
            "decision_status",
            "candidate_agent",
            "candidate_agent_version",
            "policy_ref",
            "suite_ref",
            "candidate_evaluation_ref",
            "comparison_ref",
            "gate_evaluation_ref",
            "regression_ref",
            "blocking_reasons",
            "review_reasons",
            "soft_warnings",
            "valid_evidence_coverage",
            "historical_regression",
            "recovery_fault",
            "evidence_refs",
            "authorization_boundary",
            "history",
            "source_identity",
        )
        for key in required_keys:
            if key not in metadata:
                errors.append(f"MISSING_{key.upper()}")
        if metadata.get("decision_status") not in RELEASE_STATUSES:
            errors.append("DECISION_STATUS")
        for key in ("policy_ref", "suite_ref", "candidate_evaluation_ref", "comparison_ref", "gate_evaluation_ref", "regression_ref"):
            if not isinstance(metadata.get(key), dict):
                errors.append(f"REFERENCE:{key}")
        if not isinstance(metadata.get("blocking_reasons"), list) or not isinstance(metadata.get("review_reasons"), list) or not isinstance(metadata.get("soft_warnings"), list) or not isinstance(metadata.get("evidence_refs"), list):
            errors.append("DIAGNOSTICS")
        boundary = _object(metadata.get("authorization_boundary"), "authorization_boundary")
        if boundary.get("release_executed") is not False:
            errors.append("RELEASE_EXECUTED_NOT_FALSE")
        if boundary.get("deployment_authorized") is not False:
            errors.append("DEPLOYMENT_AUTHORIZED_NOT_FALSE")
        if boundary.get("release_action") != "DECISION_ONLY":
            errors.append("RELEASE_ACTION_BOUNDARY")
        history = _object(metadata.get("history"), "history")
        if history.get("immutable") is not True:
            errors.append("HISTORY_NOT_IMMUTABLE")
        if history.get("supersedes_decision_id") == metadata.get("release_decision_id"):
            errors.append("SELF_SUPERSEDES")
        coverage = _object(metadata.get("valid_evidence_coverage"), "coverage")
        for key in ("required_item_count", "valid_evidence_item_count", "coverage_ratio"):
            if key not in coverage:
                errors.append(f"COVERAGE:{key}")
        source = _object(metadata.get("source_identity"), "source_identity")
        for key in ("runtime_version", "source_sha256", "builder"):
            if not source.get(key):
                errors.append(f"SOURCE_IDENTITY:{key}")
    except (ValueError, TypeError, KeyError):
        errors.append("MALFORMED_FIELDS")
    return errors


def write_named_artifact(value: dict[str, Any], output_dir: Path, filename: str, secret: str = "", *, overwrite: bool = False) -> Path:
    """Write a redacted artifact; immutable artifacts refuse accidental overwrite."""

    safe = redact(value, secret)
    assert_safe_artifact(safe, secret)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    if path.exists() and not overwrite:
        raise FileExistsError(f"IMMUTABLE_ARTIFACT_EXISTS:{path}")
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def build_reviewed_release_bundle(
    suite: dict[str, Any],
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    comparison: dict[str, Any],
    regression: dict[str, Any],
    *,
    baseline_gate_id: str,
    candidate_gate_id: str,
    baseline_decision_id: str,
    candidate_decision_id: str,
    decision_timestamp: str,
) -> dict[str, dict[str, Any]]:
    policy = build_minimal_quality_policy(suite)
    baseline_gate = evaluate_quality_gate(policy, suite, baseline, None, comparison, regression, gate_evaluation_id=baseline_gate_id, evaluated_at=decision_timestamp, subject="BASELINE")
    candidate_gate = evaluate_quality_gate(policy, suite, candidate, baseline, comparison, regression, gate_evaluation_id=candidate_gate_id, evaluated_at=decision_timestamp)
    baseline_decision = build_release_decision(baseline_gate, release_decision_id=baseline_decision_id, decision_timestamp=decision_timestamp)
    candidate_decision = build_release_decision(candidate_gate, release_decision_id=candidate_decision_id, decision_timestamp=decision_timestamp)
    return {
        "policy": policy,
        "baseline_gate": baseline_gate,
        "candidate_gate": candidate_gate,
        "baseline_decision": baseline_decision,
        "candidate_decision": candidate_decision,
    }


# Short aliases keep the contract easy to discover from tests and future
# callers while the explicit names remain the canonical implementation API.
validate_policy = validate_quality_policy
validate_gate_evaluation = validate_quality_gate_artifact
validate_release_decision = validate_release_decision_artifact
create_release_decision = build_release_decision

#!/usr/bin/env python3
"""Offline, fail-closed verification for the RPF-47 competition evidence pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SOURCE_COMMIT = "69dfe3079f5778cf6e569e82cf8382e4e3ec04a8"
MANIFEST_SHA256 = "6a9ebe1f1d5a759c8335275dc4a16afbe939ef9aa7eac041756dfd3ec434cdbf"
EXPECTED_SOURCES = {
    "rpf46-summary": (
        "RECORDED_RPF46_SUMMARY",
        "spikes/rpf-46/session-report.json",
        "f450803b8fd3ec51fe2663ba95370577c92f0eb70cc0dd05f4d7e5b98ab25d15",
        "rpf46-research-summary-v1",
    ),
    "rpf43-order-sample": (
        "HISTORICAL_WITNESS_SAMPLE",
        "spikes/rpf-43/sample-witness.json",
        "ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e",
        "rpf-effect-witness-v1",
    ),
    "rpf44-ops-sample": (
        "HISTORICAL_WITNESS_SAMPLE",
        "spikes/rpf-44/sample-ops-witness.json",
        "21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873",
        "rpf-effect-witness-v2",
    ),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_text_bytes(data: bytes) -> bytes:
    """Match Git's committed UTF-8 text bytes across CRLF/LF worktrees."""
    if b"\x00" in data:
        raise ValueError("unexpected_binary_source")
    return data.replace(b"\r\n", b"\n")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def parse_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label}:invalid_json:{exc}") from exc


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def git_bytes(root: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=root, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise ValueError(f"source_commit_file_unavailable:{commit}:{path}")
    return result.stdout


def verify_git_lineage(root: Path) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", SOURCE_COMMIT, "HEAD"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    require(result.returncode == 0, "source_commit_not_ancestor_of_checkout")


def validate_manifest(manifest: Any) -> list[dict[str, Any]]:
    require(isinstance(manifest, dict), "manifest_not_object")
    expected_top = {"schema_version", "source_branch", "source_commit", "sources", "competition", "validation"}
    require(set(manifest) == expected_top, "manifest_top_level_schema_mismatch")
    require(manifest["schema_version"] == "rpf-47-evidence-manifest-v1", "manifest_schema_version_mismatch")
    require(manifest["source_branch"] == "codex/rpf-46-live-pge-lab", "source_branch_mismatch")
    require(manifest["source_commit"] == SOURCE_COMMIT, "source_commit_mismatch")
    sources = manifest["sources"]
    require(isinstance(sources, list) and len(sources) == len(EXPECTED_SOURCES), "manifest_source_count_mismatch")
    by_id: dict[str, dict[str, Any]] = {}
    for source in sources:
        require(isinstance(source, dict), "source_entry_not_object")
        source_id = source.get("id")
        require(isinstance(source_id, str) and source_id not in by_id, "source_id_missing_or_duplicate")
        expected = EXPECTED_SOURCES.get(source_id)
        require(expected is not None, f"unexpected_source_id:{source_id}")
        kind, path, digest, schema = expected
        require(source.get("kind") == kind, f"source_kind_mismatch:{source_id}")
        require(source.get("path") == path, f"source_path_mismatch:{source_id}")
        require(source.get("sha256") == digest, f"source_sha256_mismatch:{source_id}")
        require(source.get("schema_version") == schema, f"source_schema_version_mismatch:{source_id}")
        require(re.fullmatch(r"[0-9a-f]{64}", str(source.get("sha256", ""))) is not None, f"invalid_sha256:{source_id}")
        by_id[source_id] = source
    require(set(by_id) == set(EXPECTED_SOURCES), "manifest_source_id_set_mismatch")

    competition = manifest["competition"]
    require(isinstance(competition, dict), "competition_not_object")
    require(competition.get("creative_submission_deadline") == "2026-10-30", "official_deadline_mismatch")
    require(competition.get("unverified_conflicting_date") == "2026-10-31", "conflicting_date_record_mismatch")
    require(competition.get("registration", "").startswith("The announcement says registration is completed"), "registration_limit_missing")
    validation = manifest["validation"]
    require(isinstance(validation, dict), "validation_not_object")
    require(validation.get("provider_http_attempts") == 0, "provider_budget_not_zero")
    require(validation.get("new_paid_sessions") == 0, "paid_session_budget_not_zero")
    require(validation.get("new_business_trials") == 0, "business_trial_budget_not_zero")
    require(validation.get("registration_status") == "NOT_SUBMITTED", "registration_status_mismatch")
    return list(by_id.values())


def validate_summary(report: Any) -> dict[str, Any]:
    require(isinstance(report, dict), "rpf46_summary_not_object")
    require(report.get("schema_version") == "rpf46-research-summary-v1", "rpf46_schema_version_mismatch")
    require(report.get("scope") == "REDACTED_LOCAL_EXECUTION_REPORT_NOT_EXTERNAL_ATTESTATION", "rpf46_scope_mismatch")
    require(report.get("session_id") == "exploration-a3cdf741b7e34f4f97c07228fdf9b679", "rpf46_session_identity_mismatch")
    require(report.get("source") == "LIVE_LOCAL_SIMULATION", "rpf46_source_mismatch")
    selections = report.get("selections")
    require(isinstance(selections, list) and len(selections) == 2, "rpf46_selection_count_mismatch")
    require((selections[0].get("round"), selections[0].get("candidate_id")) == (1, "normal"), "rpf46_first_selection_mismatch")
    require((selections[1].get("round"), selections[1].get("candidate_id")) == (2, "response-lost"), "rpf46_second_selection_mismatch")
    trials = report.get("trials")
    require(isinstance(trials, list) and len(trials) == 2, "rpf46_trial_count_mismatch")
    events = report.get("feedback_link_events")
    require(isinstance(events, list), "rpf46_feedback_events_missing")
    by_seq = {event.get("seq"): event for event in events if isinstance(event, dict)}
    feedback = by_seq.get(14)
    input_freeze = by_seq.get(15)
    second_choice = by_seq.get(16)
    require(isinstance(feedback, dict) and feedback.get("type") == "AUTHORITY_FEEDBACK_VALIDATED", "rpf46_feedback_event_missing")
    require(isinstance(input_freeze, dict) and input_freeze.get("type") == "PROVIDER_INPUT_FROZEN", "rpf46_second_input_event_missing")
    require(isinstance(second_choice, dict) and second_choice.get("type") == "PROVIDER_SELECTION_ACCEPTED", "rpf46_second_choice_event_missing")
    feedback_hash = feedback.get("facts", {}).get("feedback_sha256")
    require(isinstance(feedback_hash, str) and feedback_hash == selections[1].get("input_feedback_hash"), "rpf46_feedback_chain_hash_mismatch")
    require(feedback.get("seq", 0) < input_freeze.get("seq", 0) < second_choice.get("seq", 0), "rpf46_feedback_event_order_mismatch")
    for index, trial in enumerate(trials, start=1):
        require(trial.get("round") == index, f"rpf46_trial_round_mismatch:{index}")
        require(trial.get("effect", {}).get("contract_outcome") == "CONTRACT_SATISFIED_IN_RUN", f"rpf46_contract_outcome_mismatch:{index}")
        require(trial.get("effect", {}).get("violated_rules") == [], f"rpf46_violated_rules_present:{index}")
        require(len(trial.get("after", {}).get("data", {}).get("receipts", [])) == 1, f"rpf46_receipt_count_mismatch:{index}")
    second = trials[1]
    require(second.get("fault", {}).get("activation") == "TRIGGERED", "rpf46_second_fault_not_triggered")
    require(second.get("reconciliation", {}).get("status") == "RECONCILED_COMMITTED", "rpf46_second_receipt_not_reconciled")
    require(second.get("witness", {}).get("external_anchor") is False, "rpf46_local_witness_misrepresented_as_anchored")
    require(second.get("witness", {}).get("issuer_authenticity") == "NOT_ESTABLISHED", "rpf46_issuer_claim_mismatch")
    require(report.get("research", {}).get("attribution") == "CORRELATIONAL_ONLY", "rpf46_attribution_overstated")
    usage = report.get("usage", {})
    require((usage.get("provider_requests"), usage.get("physical_trials_completed"), usage.get("tokens")) == (2, 2, 1612), "rpf46_usage_summary_mismatch")
    return {
        "session_id": report["session_id"],
        "provider_requests": usage["provider_requests"],
        "physical_trials": usage["physical_trials_completed"],
        "tokens": usage["tokens"],
        "round_1": "normal",
        "round_2": "response-lost",
        "feedback_hash": feedback_hash,
        "round_2_fault": "TRIGGERED",
        "round_2_reconciliation": "RECONCILED_COMMITTED",
        "attribution": "CORRELATIONAL_ONLY",
    }


def validate_witness(sample: Any, source_id: str, expected_schema: str) -> dict[str, Any]:
    require(isinstance(sample, dict), f"{source_id}:sample_not_object")
    require(sample.get("schema_version") == expected_schema, f"{source_id}:schema_version_mismatch")
    claims = sample.get("claims")
    require(isinstance(claims, dict), f"{source_id}:claims_missing")
    require(claims.get("contract_outcome") == "CONTRACT_SATISFIED_IN_RUN", f"{source_id}:contract_outcome_mismatch")
    require(claims.get("fault_activation") == "TRIGGERED", f"{source_id}:fault_activation_mismatch")
    require(claims.get("attribution_strength") == "CORRELATIONAL_ONLY", f"{source_id}:attribution_overstated")
    require(claims.get("reproduction") == "NOT_TESTED", f"{source_id}:reproduction_overstated")
    return {"schema_version": expected_schema, "contract_outcome": claims["contract_outcome"], "fault_activation": claims["fault_activation"], "issuer_authenticity": "NOT_ESTABLISHED"}


def verify(root: Path) -> dict[str, Any]:
    manifest_path = root / "spikes/rpf-47/EVIDENCE_MANIFEST.json"
    manifest_bytes = manifest_path.read_bytes()
    require(sha256(canonical_text_bytes(manifest_bytes)) == MANIFEST_SHA256, "manifest_sha256_mismatch")
    manifest = parse_json(manifest_bytes, "manifest")
    sources = validate_manifest(manifest)
    verify_git_lineage(root)

    results: dict[str, Any] = {}
    decoded: dict[str, Any] = {}
    for source in sources:
        path = source["path"]
        content = (root / path).read_bytes()
        canonical_content = canonical_text_bytes(content)
        digest = sha256(canonical_content)
        require(digest == source["sha256"], f"working_tree_sha256_mismatch:{source['id']}")
        committed = git_bytes(root, SOURCE_COMMIT, path)
        require(committed == canonical_content, f"source_commit_bytes_mismatch:{source['id']}")
        require(digest == EXPECTED_SOURCES[source["id"]][2], f"pinned_sha256_mismatch:{source['id']}")
        decoded[source["id"]] = parse_json(content, source["id"])
        results[source["id"]] = {"status": "HASH_AND_COMMIT_VERIFIED", "sha256": digest, "path": path}

    report = validate_summary(decoded["rpf46-summary"])
    results["rpf46-summary"]["claims"] = report
    results["rpf43-order-sample"]["claims"] = validate_witness(decoded["rpf43-order-sample"], "rpf43-order-sample", "rpf-effect-witness-v1")
    results["rpf44-ops-sample"]["claims"] = validate_witness(decoded["rpf44-ops-sample"], "rpf44-ops-sample", "rpf-effect-witness-v2")
    return {
        "status": "VERIFIED",
        "source_commit": SOURCE_COMMIT,
        "provider_http_attempts": 0,
        "new_paid_sessions": 0,
        "new_business_trials": 0,
        "sources": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2], help="repository checkout root")
    args = parser.parse_args()
    try:
        result = verify(args.root.resolve())
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 3
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

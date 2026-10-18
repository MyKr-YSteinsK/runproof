"""Strict offline recovery verifier for one RPF-49 Target Agent trial."""
from __future__ import annotations

import argparse
import hashlib
import re
from datetime import datetime
from pathlib import Path

from .contracts import canonical, digest, fields, require
from .target_contracts import strict_json
from .target_evidence import check_content as check_target_evidence


RECOVERY_SCHEMA = "rpf-target-recovery-v1"
PRICING = {
    "provider": "DeepSeek",
    "model": "deepseek-flash",
    "model_version": "DeepSeek-V4.1-Flash-1017",
    "official_peak_input_cache_miss_usd_per_million": 0.30,
    "official_peak_output_usd_per_million": 1.20,
    "conservative_cny_per_usd": 10,
    "input_cny_per_million_upper": 3.0,
    "output_cny_per_million_upper": 12.0,
    "source": "https://api-docs.deepseek.com/quick_start/pricing/",
}
LIMITS = {"provider_http_attempts": 6, "tokens": 12000, "cost_cny_upper": 1.0,
          "steps": 14, "seconds": 1200, "trials": 1, "automatic_retries": 0}


def seal(summary: dict) -> dict:
    return {**summary, "digests": {key: digest(value) for key, value in summary.items()}}


def _timestamp(value: str) -> datetime:
    require(type(value) is str and value.endswith("Z"), "RECOVERY_TIME_FORMAT")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("RECOVERY_TIME_FORMAT") from exc
    require(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0,
            "RECOVERY_TIME_FORMAT")
    return parsed


def check_content(summary: dict) -> dict:
    fields(summary, {"schema_version", "storage_task", "logical_contract_owner", "pricing",
                     "task_usage", "trial_window", "target_evidence", "digests"},
           "RECOVERY_SUMMARY_FIELDS")
    require(summary["schema_version"] == RECOVERY_SCHEMA
            and summary["storage_task"] == "rpf-49"
            and summary["logical_contract_owner"] == "rpf-48", "RECOVERY_IDENTITY")
    require(summary["digests"] == {key: digest(summary[key]) for key in summary if key != "digests"},
            "RECOVERY_SUMMARY_DIGEST")
    require(summary["pricing"] == PRICING, "RECOVERY_PRICING_IDENTITY")

    target = summary["target_evidence"]
    facts = check_target_evidence(target)
    require(target["contracts"]["experiment"]["owner"] == summary["logical_contract_owner"],
            "RECOVERY_LOGICAL_OWNER_MISMATCH")
    contract_budgets = target["contracts"]["execution"]["budgets"]
    require(contract_budgets["provider_requests"] <= LIMITS["provider_http_attempts"]
            and contract_budgets["tokens"] <= LIMITS["tokens"]
            and contract_budgets["cost_cny"] <= LIMITS["cost_cny_upper"]
            and contract_budgets["steps"] <= LIMITS["steps"]
            and contract_budgets["seconds"] <= LIMITS["seconds"]
            and contract_budgets["request_seconds"] <= 60
            and contract_budgets["fault_trials"] <= LIMITS["trials"], "RECOVERY_CONTRACT_BUDGET")
    requests = target["provider_requests"]
    calls = target["calls"]
    task_usage = summary["task_usage"]
    fields(task_usage, {"provider_http_attempts", "tokens", "input_tokens", "output_tokens",
                        "estimated_cost_cny_upper", "usage_known", "automatic_retries", "trials"},
           "RECOVERY_USAGE_FIELDS")
    inputs = sum(record["usage"]["prompt_tokens"] for record in requests)
    outputs = sum(record["usage"]["completion_tokens"] for record in requests)
    total = inputs + outputs
    cost = (inputs * PRICING["input_cny_per_million_upper"]
            + outputs * PRICING["output_cny_per_million_upper"]) / 1_000_000
    require(task_usage == {"provider_http_attempts": len(requests), "tokens": total,
            "input_tokens": inputs, "output_tokens": outputs,
            "estimated_cost_cny_upper": cost, "usage_known": True,
            "automatic_retries": 0, "trials": 1}, "RECOVERY_USAGE_MISMATCH")

    window = summary["trial_window"]
    fields(window, {"started_at_utc", "finished_at_utc", "elapsed_seconds", "host_steps"},
           "RECOVERY_WINDOW_FIELDS")
    started = _timestamp(window["started_at_utc"])
    finished = _timestamp(window["finished_at_utc"])
    wall_seconds = (finished - started).total_seconds()
    require(type(window["elapsed_seconds"]) in (int, float) and window["elapsed_seconds"] >= 0
            and wall_seconds >= 0 and abs(wall_seconds - window["elapsed_seconds"]) <= 2.0
            and type(window["host_steps"]) is int and window["host_steps"] == len(requests) + len(calls),
            "RECOVERY_WINDOW_MISMATCH")

    reasons = []
    if target["source_level"] != "EXTERNAL_AGENT_EFFECT_VERIFIED":
        reasons.append("EXTERNAL_AGENT_EFFECT_NOT_VERIFIED")
    if len(requests) > LIMITS["provider_http_attempts"]:
        reasons.append("PROVIDER_REQUEST_LIMIT_EXCEEDED")
    if total > LIMITS["tokens"]:
        reasons.append("TOKEN_LIMIT_EXCEEDED")
    if cost > LIMITS["cost_cny_upper"]:
        reasons.append("COST_LIMIT_EXCEEDED")
    if len(calls) + len(requests) > LIMITS["steps"]:
        reasons.append("STEP_LIMIT_EXCEEDED")
    if window["elapsed_seconds"] > LIMITS["seconds"]:
        reasons.append("TRIAL_TIME_LIMIT_EXCEEDED")
    if len(target["contracts"]["experiment"].get("run_id", "")) == 0:
        reasons.append("RUN_ID_MISSING")
    if task_usage["trials"] != 1 or task_usage["automatic_retries"] != 0:
        reasons.append("TRIAL_OR_RETRY_LIMIT_MISMATCH")

    names = [call["name"] for call in calls]
    refund_calls = [call for call in calls if call["name"] == "refund_order"]
    reconcile_calls = [call for call in calls if call["name"] == "reconcile_order"]
    inspect_positions = [index for index, name in enumerate(names) if name == "inspect_order"]
    if not inspect_positions or len(refund_calls) != 1 or len(reconcile_calls) != 1:
        reasons.append("REQUIRED_AGENT_TOOL_SEQUENCE_MISSING")
    else:
        refund_index = names.index("refund_order")
        reconcile_index = names.index("reconcile_order")
        if not any(index < refund_index for index in inspect_positions) or not refund_index < reconcile_index:
            reasons.append("AGENT_TOOL_ORDER_INVALID")
        refund = refund_calls[0]
        reconcile = reconcile_calls[0]
        if refund["result"].get("status") != "UNKNOWN_OUTCOME":
            reasons.append("POST_COMMIT_UNKNOWN_OUTCOME_NOT_OBSERVED")
        if reconcile["result"].get("status") != "RECONCILED_COMMITTED":
            reasons.append("AGENT_RECONCILE_RESULT_MISSING")
        if reconcile["returned_in_request"] is None:
            reasons.append("AGENT_RECONCILE_NOT_RETURNED_TO_PROVIDER")
        else:
            origin = next((record["attempt"] for record in requests
                           if record["response_id"] == reconcile["response_id"]), None)
            returned = next((record for record in requests
                             if record["attempt"] == reconcile["returned_in_request"]), None)
            ref = {"call_id": reconcile["call_id"], "result_sha256": reconcile["result_sha256"]}
            if origin is None or returned is None or returned["attempt"] <= origin or ref not in returned["tool_returns"]:
                reasons.append("AGENT_RECONCILE_RETURN_LINEAGE_INVALID")

    if target["fault"] != {"planned": True, "triggered": True, "observed": True, "reconciled": True}:
        reasons.append("RESPONSE_LOSS_RECOVERY_NOT_ESTABLISHED")
    if target["controller_reconciliation"] is not None:
        reasons.append("CONTROLLER_RECONCILE_CANNOT_PROVE_AGENT_RECOVERY")
    if facts["contract_outcome"] != "CONTRACT_SATISFIED_IN_RUN":
        reasons.append("BUSINESS_CONTRACT_NOT_SATISFIED")
    after = target["authority_after"]["data"]
    effect = target["contracts"]["effect"]
    receipts = after["receipts"]
    receipt_valid = len(receipts) == 1
    if receipt_valid:
        receipt = receipts[0]
        receipt_valid = (receipt == {"operation_id": effect["operation_id"],
            "order_id": effect["order_id"], "amount_minor": effect["amount_minor"],
            "currency": effect["currency"], "receipt_id": receipt.get("receipt_id"),
            "status": "COMMITTED", "committed_revision": 1}
            and isinstance(receipt.get("receipt_id"), str)
            and re.fullmatch(r"receipt-[0-9a-f]{24}", receipt["receipt_id"]) is not None)
    if not receipt_valid:
        reasons.append("UNIQUE_COMMITTED_RECEIPT_NOT_ESTABLISHED")
    if target["cleanup"] != {"status": "RESET_AND_REMOVED", "reset_generation": 1,
                             "receipt_count_after_reset": 0}:
        reasons.append("SANDBOX_CLEANUP_NOT_VERIFIED")

    return {"verdict": "AGENT_RECOVERY_VERIFIED" if not reasons else "NOT_PROVEN",
            "reasons": reasons, "contract_outcome": facts["contract_outcome"],
            "issuer_authenticity": "NOT_ESTABLISHED", "attribution": "CORRELATIONAL_ONLY",
            "reproduction": "NOT_TESTED", "computed_steps": len(requests) + len(calls),
            "provider_http_attempts": len(requests), "tokens": total,
            "estimated_cost_cny_upper": cost}


def verify_bytes(raw: bytes, expected_sha256: str | None = None) -> dict:
    require(len(raw) <= 524288, "RECOVERY_SUMMARY_SIZE")
    summary = strict_json(raw)
    require(raw == canonical(summary), "RECOVERY_SUMMARY_NOT_CANONICAL")
    sha = hashlib.sha256(raw).hexdigest()
    require(expected_sha256 is None or sha == expected_sha256, "RECOVERY_EXTERNAL_ANCHOR_MISMATCH")
    result = check_content(summary)
    reasons = list(result["reasons"])
    if expected_sha256 is None:
        reasons.append("EXTERNAL_ANCHOR_MISSING")
    verdict = "AGENT_RECOVERY_VERIFIED" if not reasons else "NOT_PROVEN"
    return {"status": "CONTENT_CHECKED_UNANCHORED" if expected_sha256 is None else "CONTENT_VERIFIED_ANCHORED",
            "schema_version": RECOVERY_SCHEMA, "file_sha256": sha, "verdict": verdict,
            "reasons": reasons, **{key: value for key, value in result.items()
                                   if key not in ("reasons", "verdict")}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    try:
        with args.path.open("rb") as stream:
            result = verify_bytes(stream.read(524289), args.expected_sha256)
        print(canonical(result).decode())
        return 0 if result["verdict"] == "AGENT_RECOVERY_VERIFIED" else 2
    except Exception as exc:
        print(canonical({"status": "REJECTED", "code": getattr(exc, "code", "RECOVERY_SUMMARY_MALFORMED")}).decode())
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

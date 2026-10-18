"""RPF-49: one explicit fixture loop or at most one paid response-lost Trial."""
from __future__ import annotations

import argparse
import copy
import hashlib
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.effectwitness.contracts import canonical, require
from runtime.runproof_runtime.effectwitness.effect_oracle import evaluate_order_effect
from runtime.runproof_runtime.effectwitness.orders import AuthorityReader, OrderAdapter, OrderSandbox
from runtime.runproof_runtime.effectwitness.target_contracts import LIMITS as LEGACY_LIMITS, TargetContracts
from runtime.runproof_runtime.effectwitness.target_driver import (
    PydanticAgentDriver, ProviderLedger, TargetToolHost, TaskLock, save,
)
from runtime.runproof_runtime.effectwitness.target_evidence import LIMITATIONS, seal, verify_bytes
from runtime.runproof_runtime.effectwitness.target_recovery import PRICING, check_content as check_recovery, seal as seal_recovery


TASK = ROOT / ".local" / "rpf-49"
STORAGE_TASK = "rpf-49"
LOGICAL_OWNER = "rpf-48"
RUN_BUDGETS = {**LEGACY_LIMITS, "tokens": 12000, "cost_cny": 1.0}


class RecoveryFixture:
    """A zero-Provider response script exercising the real Pydantic SDK tool loop."""
    def __init__(self, effect: dict):
        self.calls = [
            ("inspect_order", "fixture-call-inspect", {"order_id": effect["order_id"]}),
            ("refund_order", "fixture-call-refund", {key: effect[key]
             for key in ("order_id", "operation_id", "amount_minor")}),
            ("reconcile_order", "fixture-call-reconcile", {"operation_id": effect["operation_id"]}),
        ]
        self.index = 0

    def __call__(self, body: dict) -> dict:
        self.index += 1
        message = {"role": "assistant", "content": "Fixture acknowledgment."}
        finish_reason = "stop"
        if self.index <= len(self.calls):
            name, call_id, arguments = self.calls[self.index - 1]
            message.update(content=None, tool_calls=[{"id": call_id, "type": "function", "index": 0,
                "function": {"name": name, "arguments": canonical(arguments).decode("utf-8")}}])
            finish_reason = "tool_calls"
        return {"id": f"fixture-response-{self.index}", "object": "chat.completion", "created": 0,
            "model": "deepseek-flash", "choices": [{"index": 0, "message": message,
            "finish_reason": finish_reason}], "usage": {"prompt_tokens": 90, "completion_tokens": 12,
            "total_tokens": 102}}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_error(exc: Exception) -> dict:
    return {"domain": getattr(exc, "domain", "PLATFORM"),
            "code": getattr(exc, "code", "RPF49_TRIAL_ERROR"), "error_type": type(exc).__name__}


def _compatibility_usage(actual: dict) -> dict:
    """Keep the immutable rpf-target-evidence-v1 RPF-48 price field unchanged."""
    result = dict(actual)
    if actual["usage_known"] and actual["metering_kind"] != "FIXTURE_SYNTHETIC_NOT_BILLED":
        result["estimated_cost_cny_upper"] = (actual["input_tokens"] * 2
                                                + actual["output_tokens"] * 8) / 1_000_000
    return result


def _recovery_summary(target_evidence: dict, actual_usage: dict, started_at: str,
                      finished_at: str, elapsed: float) -> dict:
    return {
        "schema_version": "rpf-target-recovery-v1",
        "storage_task": STORAGE_TASK,
        "logical_contract_owner": LOGICAL_OWNER,
        "pricing": PRICING,
        "task_usage": {key: actual_usage[key] for key in (
            "provider_http_attempts", "tokens", "input_tokens", "output_tokens",
            "estimated_cost_cny_upper", "usage_known", "automatic_retries", "trials")},
        "trial_window": {"started_at_utc": started_at, "finished_at_utc": finished_at,
                         "elapsed_seconds": round(elapsed, 6),
                         "host_steps": len(target_evidence["provider_requests"]) + len(target_evidence["calls"])},
        "target_evidence": target_evidence,
    }


def run_trial(*, live: bool, fault: str = "response-lost") -> int:
    require(fault == "response-lost", "RPF49_FAULT_MUST_BE_RESPONSE_LOST")
    run_id = ("target-recovery-" if live else "fixture-recovery-") + uuid.uuid4().hex
    run_directory = TASK / ("trials" if live else "fixtures") / run_id
    sdk_directory = TASK / "sdk-runs" / run_id
    python = TASK / "venv" / "Scripts" / "python.exe"
    require(python.is_file(), "RPF49_ISOLATED_SDK_UNAVAILABLE")
    if live:
        require(bool(os.environ.get("DEEPSEEK_API_KEY")), "DEEPSEEK_KEY_UNAVAILABLE", "PROVIDER")
    TASK.mkdir(parents=True, exist_ok=True)
    contracts = TargetContracts.create(run_id, fault=fault, budgets=RUN_BUDGETS)
    ledger_path = TASK / "paid-ledger.json" if live else TASK / "transport" / run_id / "ledger.json"
    ledger = ProviderLedger(ledger_path, fixture=not live, storage_task=STORAGE_TASK)
    ledger.start_trial(run_id)

    sandbox = OrderSandbox(contracts, run_directory, storage_task=STORAGE_TASK)
    sandbox.initialize()
    reader = AuthorityReader(sandbox.path, contracts, storage_task=STORAGE_TASK)
    adapter = OrderAdapter(sandbox)
    host = TargetToolHost(contracts, adapter, reader)
    fixture = None if live else RecoveryFixture(contracts.effect)
    driver = PydanticAgentDriver(python, sdk_directory, fixture_completion=fixture,
                                 storage_task=STORAGE_TASK)
    started_at = _utc_now()
    started_tick = time.monotonic()
    error = None
    try:
        sdk = driver.run(contracts, host, ledger)
    except Exception as exc:
        sdk = None
        error = _safe_error(exc)

    controller_reconciliation = None
    cleanup = {"status": "QUARANTINED_IN_PLACE"}
    authority_after = None
    effect = None
    try:
        after = reader.read()
        after_data = reader.validate(after)
        before_data = reader.validate(host.before)
        authority_after = after.public()
        effect = evaluate_order_effect(contracts.effect, contracts.experiment["environment_id"],
                                       before_data, after_data)
        if host.pending:
            # This is safety cleanup after the Agent stops; it never marks Agent recovery.
            try:
                receipt = reader.reconcile(contracts.effect["operation_id"])
                controller_reconciliation = {"status": "CONTROLLER_RECONCILED_COMMITTED",
                    "receipt_sha256": hashlib.sha256(canonical(receipt)).hexdigest()}
            except Exception as exc:
                controller_reconciliation = {"status": "UNRESOLVED_QUARANTINED_IN_PLACE",
                                             "error": _safe_error(exc)}
        unresolved = controller_reconciliation is not None and \
            controller_reconciliation["status"] == "UNRESOLVED_QUARANTINED_IN_PLACE"
        if not unresolved:
            cleanup = sandbox.cleanup()
        ledger.finish_trial(run_id, not unresolved)
    except Exception as exc:
        error = error or _safe_error(exc)
        unresolved = True
        if ledger.data["trial_status"].get(run_id) == "RESERVED":
            ledger.finish_trial(run_id, False)

    elapsed = max(0.0, time.monotonic() - started_tick)
    finished_at = _utc_now()
    actual_usage = ledger.usage(run_id)
    requests = copy.deepcopy([record for record in ledger.data["requests"] if record["run_id"] == run_id])
    calls = copy.deepcopy(host.calls)
    source_level = "FIXTURE_TEST_ONLY" if not live else "AGENT_RUNTIME_CONNECTED"
    if live and sdk is not None and sdk["runtime"] is not None and sdk["process_exit"] == 0 \
            and sdk["failure"] is None and host.mutated and not host.pending \
            and all(call["returned_in_request"] is not None for call in calls) and actual_usage["usage_known"]:
        source_level = "EXTERNAL_AGENT_EFFECT_VERIFIED"

    evidence_path = TASK / "evidence" / f"{run_id}.json"
    recovery_path = ROOT / "spikes" / "rpf-49" / "recovery-summary.json"
    evidence_check = None
    recovery_facts = None
    if authority_after is not None and effect is not None and actual_usage["usage_known"] \
            and (not live or (sdk is not None and sdk["runtime"] is not None)):
        raw_sdk = sdk if sdk is not None else {"source": "EXTERNAL_AGENT_RUNTIME", "process_exit": -1,
            "report": {"status": "SDK_ERROR"}, "failure": error}
        bundle = seal({"schema_version": "rpf-target-evidence-v1", "source_level": source_level,
            "contracts": contracts.document(), "sdk": raw_sdk, "calls": calls,
            "provider_requests": requests, "usage": _compatibility_usage(actual_usage),
            "authority_before": host.before.public(), "authority_after": authority_after,
            "effect": effect, "fault": adapter.fault,
            "controller_reconciliation": controller_reconciliation, "cleanup": cleanup,
            "limitations": LIMITATIONS})
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        save(evidence_path, bundle, storage_task=STORAGE_TASK)
        evidence_raw = evidence_path.read_bytes()
        evidence_sha = hashlib.sha256(evidence_raw).hexdigest()
        try:
            evidence_check = verify_bytes(evidence_raw, evidence_sha)
        except Exception as exc:
            evidence_check = {"status": "INCONCLUSIVE", "code": getattr(exc, "code", "TARGET_CHECK_FAILED")}

        if live and source_level in ("EXTERNAL_AGENT_EFFECT_VERIFIED", "AGENT_RUNTIME_CONNECTED"):
            summary = _recovery_summary(bundle, actual_usage, started_at, finished_at, elapsed)
            sealed_summary = seal_recovery(summary)
            recovery_path.parent.mkdir(parents=True, exist_ok=True)
            require(not recovery_path.exists(), "RPF49_RECOVERY_SUMMARY_ALREADY_EXISTS")
            recovery_temp = recovery_path.with_suffix(recovery_path.suffix + ".tmp")
            with recovery_temp.open("xb") as stream:
                stream.write(canonical(sealed_summary))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(recovery_temp, recovery_path)
            try:
                recovery_facts = check_recovery(sealed_summary)
            except Exception as exc:
                recovery_facts = {"verdict": "NOT_PROVEN",
                                  "reasons": [getattr(exc, "code", "RECOVERY_CHECK_FAILED")]}

    result = {"run_id": run_id, "mode": "LIVE" if live else "FIXTURE_TEST_ONLY",
        "source_level": source_level, "sdk": sdk, "failure": error,
        "evidence_path": str(evidence_path) if evidence_check else None,
        "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest() if evidence_check else None,
        "evidence_check": evidence_check, "recovery_summary_path": str(recovery_path) if recovery_facts else None,
        "recovery_summary_sha256": hashlib.sha256(recovery_path.read_bytes()).hexdigest() if recovery_facts else None,
        "recovery_facts": recovery_facts, "fault": adapter.fault,
        "controller_reconciliation": controller_reconciliation, "effect": effect,
        "task_usage": actual_usage, "cleanup": cleanup, "trial_elapsed_seconds": round(elapsed, 6)}
    result_path = TASK / ("live-result.json" if live else "fixture-result.json")
    save(result_path, result, storage_task=STORAGE_TASK)
    print(canonical(result).decode("utf-8"))
    if not live:
        return 0 if source_level == "FIXTURE_TEST_ONLY" and recovery_facts is None \
            and len(calls) == 3 and [call["name"] for call in calls] == \
            ["inspect_order", "refund_order", "reconcile_order"] and not host.pending \
            and actual_usage["provider_http_attempts"] == 0 and actual_usage["usage_known"] else 2
    return 0 if recovery_facts and recovery_facts["verdict"] == "AGENT_RECOVERY_VERIFIED" else 2


def run(live: bool, fault: str) -> int:
    if not live:
        return run_trial(live=False, fault=fault)
    require(fault == "response-lost", "RPF49_FAULT_MUST_BE_RESPONSE_LOST")
    require(bool(os.environ.get("DEEPSEEK_API_KEY")), "DEEPSEEK_KEY_UNAVAILABLE", "PROVIDER")
    summary_path = ROOT / "spikes" / "rpf-49" / "recovery-summary.json"
    require(not summary_path.exists() and not summary_path.with_suffix(".json.tmp").exists(),
            "RPF49_RECOVERY_SUMMARY_ALREADY_EXISTS")
    with TaskLock(TASK / "paid-run.lock", storage_task=STORAGE_TASK):
        return run_trial(live=True, fault=fault)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--transport-only", action="store_true",
                       help="run the real pinned Pydantic AI SDK against a zero-Provider fixture")
    modes.add_argument("--live", action="store_true",
                       help="consume the single reserved DeepSeek Target Trial")
    parser.add_argument("--fault", choices=("response-lost",), default="response-lost")
    args = parser.parse_args()
    raise SystemExit(run(args.live, args.fault))

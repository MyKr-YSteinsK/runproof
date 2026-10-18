"""RPF-48 explicit transport smoke or one bounded live Target trial. No reset option."""
from __future__ import annotations

import argparse
import copy
import hashlib
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.effectwitness.contracts import canonical, owned_path, require
from runtime.runproof_runtime.effectwitness.effect_oracle import evaluate_order_effect
from runtime.runproof_runtime.effectwitness.orders import AuthorityReader, OrderAdapter, OrderSandbox
from runtime.runproof_runtime.effectwitness.target_contracts import TargetContracts
from runtime.runproof_runtime.effectwitness.target_driver import PydanticAgentDriver, ProviderLedger, TargetToolHost, TaskLock, save
from runtime.runproof_runtime.effectwitness.target_evidence import LIMITATIONS, seal, verify_bytes


class FixtureCompletion:
    """Transport-only fixture. It does not perform the authorized mutation."""
    def __init__(self, effect):
        self.effect = effect
        self.count = 0

    def __call__(self, body):
        self.count += 1
        message = {"role": "assistant", "content": "Fixture transport complete."}
        if self.count == 1:
            message.update(content=None, tool_calls=[{"id": "fixture-call-1", "type": "function", "index": 0, "function": {
                "name": "inspect_order", "arguments": canonical({"order_id": self.effect["order_id"]}).decode()}}])
        return {"id": "fixture-response-" + str(self.count), "object": "chat.completion", "created": 0,
                "model": "deepseek-flash", "choices": [{"index": 0, "message": message,
                "finish_reason": "tool_calls" if self.count == 1 else "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}


def run_trial(live, fault="none"):
    task = ROOT / ".local/rpf-48"
    python = task / "venv/Scripts/python.exe"
    require(python.is_file(), "ISOLATED_SDK_UNAVAILABLE")
    require(not live or bool(os.environ.get("DEEPSEEK_API_KEY")), "DEEPSEEK_KEY_UNAVAILABLE")
    run_id = ("target-" if live else "transport-") + uuid.uuid4().hex
    contracts = TargetContracts.create(run_id, fault=fault)
    ledger = ProviderLedger(task / ("paid-ledger.json" if live else f"transport/{run_id}/ledger.json"), fixture=not live)
    ledger.start_trial(run_id)
    sandbox = OrderSandbox(contracts, task / "trials" / run_id, storage_task="rpf-48")
    sandbox.initialize()
    reader = AuthorityReader(sandbox.path, contracts, storage_task="rpf-48")
    adapter = OrderAdapter(sandbox)
    host = TargetToolHost(contracts, adapter, reader)
    driver = PydanticAgentDriver(python, task / "sdk-runs" / run_id,
                                fixture_completion=None if live else FixtureCompletion(contracts.effect))
    sdk = driver.run(contracts, host, ledger)
    after = reader.read()
    before_data, after_data = reader.validate(host.before), reader.validate(after)
    effect = evaluate_order_effect(contracts.effect, contracts.experiment["environment_id"], before_data, after_data)
    controller_reconciliation = None
    if host.pending:
        # Independent readback after the Agent has stopped; never presented as Agent recovery.
        try:
            controller_reconciliation = {"status": "CONTROLLER_RECONCILED_COMMITTED",
                "receipt_sha256": hashlib.sha256(canonical(reader.reconcile(contracts.effect["operation_id"]))).hexdigest()}
        except Exception:
            controller_reconciliation = {"status": "UNRESOLVED_QUARANTINED_IN_PLACE"}
    unresolved = controller_reconciliation and controller_reconciliation["status"] == "UNRESOLVED_QUARANTINED_IN_PLACE"
    cleanup = {"status": "QUARANTINED_IN_PLACE"} if unresolved else sandbox.cleanup()
    ledger.finish_trial(run_id, not unresolved)
    requests = copy.deepcopy([r for r in ledger.data["requests"] if r["run_id"] == run_id])
    level = "FIXTURE_TEST_ONLY" if not live else "AGENT_RUNTIME_CONNECTED"
    if live and sdk["process_exit"] == 0 and sdk["failure"] is None and host.mutated and not host.pending and all(
            c["returned_in_request"] is not None for c in host.calls) and ledger.usage()["usage_known"]:
        level = "EXTERNAL_AGENT_EFFECT_VERIFIED"
    bundle = seal({"schema_version": "rpf-target-evidence-v1", "source_level": level,
        "contracts": contracts.document(), "sdk": sdk, "calls": host.calls, "provider_requests": requests,
        "usage": ledger.usage(run_id), "authority_before": host.before.public(), "authority_after": after.public(),
        "effect": effect, "fault": adapter.fault, "controller_reconciliation": controller_reconciliation,
        "cleanup": cleanup, "limitations": LIMITATIONS})
    path = task / "evidence" / (run_id + ".json")
    save(path, bundle)
    raw = path.read_bytes()
    try:
        checked = verify_bytes(raw, hashlib.sha256(raw).hexdigest())
    except Exception as exc:
        checked = {"status": "INCONCLUSIVE", "code": getattr(exc, "code", "TARGET_CHECK_FAILED")}
    result = {"run_id": run_id, "evidence_path": str(path), "file_sha256": hashlib.sha256(raw).hexdigest(),
              "source_level": level, "sdk": sdk, "content_check": checked, "usage": ledger.usage(), "cleanup": cleanup}
    save(task / ("live-result.json" if live else "transport-result.json"), result)
    print(canonical(result).decode())
    return 0 if checked["status"] == "CONTENT_VERIFIED_ANCHORED" and sdk["process_exit"] == 0 \
        and sdk["failure"] is None and sdk["report"]["status"] == "COMPLETED" else 2


def run(live, fault="none"):
    if not live:
        return run_trial(False, fault)
    require(bool(os.environ.get("DEEPSEEK_API_KEY")), "DEEPSEEK_KEY_UNAVAILABLE")
    with TaskLock(ROOT / ".local/rpf-48/paid-run.lock"):
        return run_trial(True, fault)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--transport-only", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--fault", choices=("none", "response-lost"), default="none")
    args = parser.parse_args()
    raise SystemExit(run(args.live, args.fault))

from __future__ import annotations

import hashlib
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from runtime.runproof_runtime.models import RuntimeFailure
from runtime.runproof_runtime.effectwitness.contracts import ROOT, canonical, owned_path
from runtime.runproof_runtime.effectwitness.effect_oracle import evaluate_order_effect
from runtime.runproof_runtime.effectwitness.orders import AuthorityReader, OrderAdapter, OrderSandbox
from runtime.runproof_runtime.effectwitness.target_contracts import LIMITS, TargetContracts, arguments_for
from runtime.runproof_runtime.effectwitness.target_driver import ProviderLedger, TargetToolHost, TaskLock
from runtime.runproof_runtime.effectwitness.target_evidence import LIMITATIONS, seal as seal_target
from runtime.runproof_runtime.effectwitness.target_recovery import (
    PRICING, check_content, seal, verify_bytes,
)


LOCAL = ROOT / ".local" / "rpf-49" / "tests"


class TargetRecoveryTests(unittest.TestCase):
    def setUp(self):
        LOCAL.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=LOCAL)
        self.folder = Path(self.temp.name)
        budgets = {**LIMITS, "tokens": 12000, "cost_cny": 1.0}
        self.contracts = TargetContracts.create("rpf49-test-" + uuid.uuid4().hex,
                                                fault="response-lost", budgets=budgets)
        self.sandbox = None

    def tearDown(self):
        if self.sandbox and self.sandbox.path.exists():
            self.sandbox.cleanup()
        self.temp.cleanup()

    def make_host(self):
        self.sandbox = OrderSandbox(self.contracts, self.folder / "business", storage_task="rpf-49")
        self.sandbox.initialize()
        self.reader = AuthorityReader(self.sandbox.path, self.contracts, storage_task="rpf-49")
        self.host = TargetToolHost(self.contracts, OrderAdapter(self.sandbox), self.reader)
        return self.host

    def call(self, name: str, call_id: str):
        args = arguments_for(name, self.contracts.effect)
        self.host.register([{"id": call_id, "type": "function", "function": {
            "name": name, "arguments": canonical(args).decode("utf-8")}}], "response-" + call_id)
        return args

    def test_v1_profile_keeps_logical_owner_and_rpf49_is_only_storage_owner(self):
        self.assertEqual(self.contracts.experiment["owner"], "rpf-48")
        self.assertEqual(owned_path(self.folder / "owned", task="rpf-49"),
                         (self.folder / "owned").resolve())
        with self.assertRaises(RuntimeFailure):
            owned_path(ROOT / ".local" / "rpf-49" / "forbidden", task="rpf-48")
        doc = self.contracts.document()
        doc["experiment"]["owner"] = "rpf-49"
        with self.assertRaises(RuntimeFailure):
            TargetContracts.from_document(doc)
        self.assertEqual(self.contracts.execution["budgets"]["tokens"], 12000)
        too_wide = {**self.contracts.execution["budgets"], "tokens": 15001}
        with self.assertRaises(RuntimeFailure):
            TargetContracts.create("rpf49-too-wide", fault="response-lost", budgets=too_wide)

    def test_task_ledger_uses_one_trial_peak_rate_and_six_request_cap(self):
        path = self.folder / "paid-ledger.json"
        ledger = ProviderLedger(path, storage_task="rpf-49")
        self.assertEqual(ledger.data["schema_version"], "rpf49-budget-v1")
        run_id = self.contracts.experiment["run_id"]
        ledger.start_trial(run_id)
        for index in range(6):
            record = ledger.reserve({"model": "deepseek-flash", "n": index}, run_id, [])
            ledger.received(record, {"id": f"response-{index}", "model": "deepseek-flash",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}})
        usage = ledger.usage()
        self.assertEqual(usage["provider_http_attempts"], 6)
        self.assertEqual(usage["tokens"], 900)
        self.assertEqual(usage["estimated_cost_cny_upper"], 0.0054)
        self.assertEqual(PRICING["input_cny_per_million_upper"], 3.0)
        self.assertEqual(PRICING["output_cny_per_million_upper"], 12.0)
        with self.assertRaisesRegex(RuntimeFailure, "RESERVATION_EXHAUSTED"):
            ledger.reserve({"model": "deepseek-flash"}, run_id, [])
        ledger.finish_trial(run_id, True)
        with self.assertRaisesRegex(RuntimeFailure, "TRIAL_BUDGET"):
            ledger.start_trial("rpf49-second-trial")

    def test_unknown_usage_persistently_freezes_paid_followups(self):
        ledger = ProviderLedger(self.folder / "unknown-ledger.json", storage_task="rpf-49")
        ledger.start_trial(self.contracts.experiment["run_id"])
        ledger.reserve({"model": "deepseek-flash"}, self.contracts.experiment["run_id"], [])
        reopened = ProviderLedger(ledger.path, storage_task="rpf-49")
        self.assertFalse(reopened.usage()["usage_known"])
        with self.assertRaisesRegex(RuntimeFailure, "USAGE_UNKNOWN"):
            reopened.reserve({"model": "deepseek-flash"}, self.contracts.experiment["run_id"], [])
        with self.assertRaisesRegex(RuntimeFailure, "PROVIDER_USAGE_UNKNOWN"):
            reopened.start_trial("rpf49-second-trial")

    def test_agent_must_reconcile_unknown_and_returns_are_call_bound(self):
        self.host = self.make_host()
        for name, call_id in (("inspect_order", "inspect-call"), ("refund_order", "refund-call")):
            args = self.call(name, call_id)
            result = self.host.invoke(call_id, name, args)
        self.assertEqual(result["status"], "UNKNOWN_OUTCOME")
        retry_args = self.call("refund_order", "blind-retry")
        with self.assertRaisesRegex(RuntimeFailure, "RECONCILE_REQUIRED"):
            self.host.invoke("blind-retry", "refund_order", retry_args)
        reconcile_args = self.call("reconcile_order", "agent-reconcile")
        reconciled = self.host.invoke("agent-reconcile", "reconcile_order", reconcile_args)
        self.assertEqual(reconciled["status"], "RECONCILED_COMMITTED")
        messages = [{"role": "tool", "tool_call_id": call["call_id"],
                     "content": canonical(call["result"]).decode("utf-8")} for call in self.host.calls]
        references = self.host.verify_returns(messages, 4)
        self.assertEqual({item["call_id"] for item in references},
                         {"inspect-call", "refund-call", "agent-reconcile"})
        self.assertTrue(self.host.domain.fault["reconciled"])

    def _unrecovered_fixture_summary(self):
        self.sandbox = OrderSandbox(self.contracts, self.folder / "business", storage_task="rpf-49")
        self.sandbox.initialize()
        reader = AuthorityReader(self.sandbox.path, self.contracts, storage_task="rpf-49")
        before, after = reader.read(), reader.read()
        effect = evaluate_order_effect(self.contracts.effect, self.contracts.experiment["environment_id"],
                                       reader.validate(before), reader.validate(after))
        cleanup = self.sandbox.cleanup()
        target = seal_target({"schema_version": "rpf-target-evidence-v1", "source_level": "FIXTURE_TEST_ONLY",
            "contracts": self.contracts.document(), "sdk": {"source": "FIXTURE_TEST_ONLY"}, "calls": [],
            "provider_requests": [], "usage": {"tokens": 0, "input_tokens": 0, "output_tokens": 0,
                "provider_http_attempts": 0, "estimated_cost_cny_upper": 0.0, "usage_known": True,
                "automatic_retries": 0, "trials": 1}, "authority_before": before.public(),
            "authority_after": after.public(), "effect": effect,
            "fault": {"planned": True, "triggered": False, "observed": False, "reconciled": False},
            "controller_reconciliation": None, "cleanup": cleanup, "limitations": LIMITATIONS})
        stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return seal({"schema_version": "rpf-target-recovery-v1", "storage_task": "rpf-49",
            "logical_contract_owner": "rpf-48", "pricing": PRICING,
            "task_usage": {"provider_http_attempts": 0, "tokens": 0, "input_tokens": 0,
                "output_tokens": 0, "estimated_cost_cny_upper": 0.0, "usage_known": True,
                "automatic_retries": 0, "trials": 1},
            "trial_window": {"started_at_utc": stamp, "finished_at_utc": stamp,
                "elapsed_seconds": 0.0, "host_steps": 0}, "target_evidence": target})

    def test_offline_recovery_verifier_downgrades_missing_live_facts_and_anchor(self):
        summary = self._unrecovered_fixture_summary()
        raw = canonical(summary)
        result = verify_bytes(raw)
        self.assertEqual(result["verdict"], "NOT_PROVEN")
        self.assertIn("EXTERNAL_AGENT_EFFECT_NOT_VERIFIED", result["reasons"])
        self.assertIn("EXTERNAL_ANCHOR_MISSING", result["reasons"])
        anchored = verify_bytes(raw, hashlib.sha256(raw).hexdigest())
        self.assertEqual(anchored["verdict"], "NOT_PROVEN")

    def test_unanchored_complete_facts_are_still_not_proven(self):
        facts = {"verdict": "AGENT_RECOVERY_VERIFIED", "reasons": [],
                 "contract_outcome": "CONTRACT_SATISFIED_IN_RUN"}
        with patch("runtime.runproof_runtime.effectwitness.target_recovery.check_content",
                   return_value=facts):
            result = verify_bytes(canonical({"fixture": "only"}))
        self.assertEqual(result["verdict"], "NOT_PROVEN")
        self.assertEqual(result["reasons"], ["EXTERNAL_ANCHOR_MISSING"])

    def test_offline_recovery_verifier_rejects_wrong_anchor_and_tampering(self):
        raw = canonical(self._unrecovered_fixture_summary())
        with self.assertRaisesRegex(RuntimeFailure, "ANCHOR"):
            verify_bytes(raw, "0" * 64)
        altered = raw.replace(b"FIXTURE_TEST_ONLY", b"FIXTURE_TEST_ONLY ", 1)
        with self.assertRaises((RuntimeFailure, ValueError)):
            verify_bytes(altered, hashlib.sha256(altered).hexdigest())

    def test_rpf49_lock_is_task_owned_and_crash_hold_is_preserved(self):
        path = self.folder / "paid-run.lock"
        with self.assertRaises(RuntimeError):
            with TaskLock(path, storage_task="rpf-49"):
                raise RuntimeError("fixture")
        self.assertTrue(path.is_file())
        with self.assertRaises(FileExistsError):
            with TaskLock(path, storage_task="rpf-49"):
                self.fail("a second controller must not enter")


if __name__ == "__main__":
    unittest.main()

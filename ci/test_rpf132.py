"""Provider-zero regressions for the RPF-132 request, durable admission and interrupted readback."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from runtime.runproof_runtime.effectwitness import rpf132 as app, rpf132_budget as ledger, rpf132_protocol as protocol
from runtime.runproof_runtime.effectwitness import rpf119_journal as files, timeout_jiuwen as sdk
from runtime.runproof_runtime.effectwitness.product_local_contracts import canonical, strict


class TrialTests(unittest.TestCase):
    def setUp(self):
        root = app.ROOT / ".local" / "rpf-132-tests"
        root.mkdir(parents=True, exist_ok=True)
        tmp = TemporaryDirectory(dir=root)
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.cell = {"case": "A", "name": "A", "session_id": "a" * 32}
        self.m = {"run_id": "1" * 32, "source_commit": "2" * 40, "limits": deepcopy(protocol.LIMITS),
                  "admission": None, "mode": "OFFLINE"}
        self.view = {"decision_readback": {"session_id": self.cell["session_id"], "operation_id": "a"*32 + "-order",
                     "status": "READ", "snapshot": {"order": {"revision": 1}, "receipts": [{"test": 1}]}},
                     "finding": "REFUND_VERIFIED", "rollback_proof": None}

    def open(self, sender=None):
        files.write(self.folder / "grant.json", ledger.grant(self.m))
        ledger.claim(self.folder, self.m)
        return ledger.Budget(self.folder, self.m, readonly=False, sender=sender or app.fixture("nominal"),
                             meter=lambda body: len(canonical(body)))

    def first(self, budget):
        return budget.exchange(self.cell, 1, self.view, None)

    def test_claim_required_and_never_reopened_to_send(self):
        with self.assertRaises(FileNotFoundError):
            ledger.claim(self.folder, self.m)
        self.open()
        with self.assertRaises(FileExistsError):
            ledger.claim(self.folder, self.m)
        self.assertFalse((self.folder / "result.json").exists())

    def test_ceiling_includes_schema_wrapping_and_currency(self):
        ticket = protocol.reservation(self.m, self.cell, 1, self.view, None)
        hold = ticket["hold"]
        self.assertGreater(hold["input"], len(canonical(ticket["request"])) + 4096)
        self.assertEqual(hold["nano_cny"], hold["input"] * 2000 + 384 * 8000)
        self.assertEqual(65536 * 2000 + 1536 * 8000, 143360000)

    def test_wrong_model_action_is_kept_and_second_frame_binds_receipt(self):
        sender = Mock(wraps=app.fixture("wrong-action"))
        budget = self.open(sender)
        call = self.first(budget)["reply"]["call"]
        self.assertEqual(call["arguments"]["action"], "HANDOFF_NO_RETRY")
        receipt = sdk.receipt_for(call, call["arguments"])
        with self.assertRaisesRegex(ValueError, "RECEIPT_BINDING"):
            budget.exchange(self.cell, 2, self.view, receipt | {"call_id": "foreign"})
        self.assertEqual(sender.call_count, 1)

    def test_second_frame_cannot_spend_past_budget(self):
        self.m["limits"]["requests"] = 1
        sender = Mock(wraps=app.fixture("nominal"))
        budget = self.open(sender)
        call = self.first(budget)["reply"]["call"]
        r = budget.exchange(self.cell, 2, self.view, sdk.receipt_for(call, call["arguments"]))
        self.assertEqual(r, {"stop": "BUDGET_EXHAUSTED"})
        self.assertEqual(sender.call_count, 1)

    def test_missing_usage_or_extra_tool_refuses_decision(self):
        ticket = protocol.reservation(self.m, self.cell, 1, self.view, None)
        raw = app.fixture("nominal")(canonical(ticket["request"]), lambda *args: None)
        body = strict(raw)
        for flag, reason in (("usage", "USAGE_UNKNOWN"), ("calls", "PROPOSAL_COUNT"),
                             ("model", "MODEL_IDENTITY"), ("overrun", "USAGE_EXCEEDS_HOLD")):
            with self.subTest(flag=flag):
                data = deepcopy(body)
                if flag == "usage":
                    del data["usage"]
                elif flag == "calls":
                    calls = data["choices"][0]["message"]["tool_calls"]
                    calls.extend(list(calls))
                elif flag == "overrun":
                    data["usage"] = {"prompt_tokens": 20000, "completion_tokens": 1, "total_tokens": 20001}
                else:
                    data["model"] = "unapproved"
                with self.assertRaisesRegex(ValueError, reason):
                    protocol.decision(protocol.project(canonical(data), 200), ticket, self.view, None)

    def test_unknown_write_survives_fresh_reader_and_blocks_next_frame(self):
        budget = self.open(app.fixture("unknown"))
        self.assertEqual(self.first(budget), {"stop": "TRANSPORT_UNKNOWN"})
        with self.assertRaisesRegex(ValueError, "RUN_ALREADY_HALTED"):
            self.first(budget)
        reader = ledger.Budget(self.folder, self.m, readonly=True)
        self.assertEqual(self.first(reader), {"stop": "TRANSPORT_UNKNOWN"})
        reader.log.finish()
        self.assertEqual(reader.summary(), budget.summary())
        self.assertEqual(reader.summary()["unsettled"], 1)

    def test_hard_interruption_prefix_preserves_hold(self):
        def interrupted(raw, phase):
            phase("POST_WRITTEN", {})
            raise KeyboardInterrupt
        budget = self.open(interrupted)
        with self.assertRaises(KeyboardInterrupt):
            self.first(budget)
        prefix = ledger.interrupted(self.folder, self.m)
        self.assertFalse(prefix["send_authority"])
        self.assertEqual(prefix["observed_posts_written"], 1)
        self.assertGreater(prefix["observed_unsettled_nano_cny"], 0)
        with self.assertRaises(FileExistsError):
            ledger.claim(self.folder, self.m)

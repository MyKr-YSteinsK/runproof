"""Causal and admission controls for the offline competition Agent."""
from contextlib import closing
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from runtime.runproof_runtime.effectwitness import product_local_session
from runtime.runproof_runtime.effectwitness.competition_agent import AgentPolicy, MODE, tool_intent
from runtime.runproof_runtime.effectwitness.competition_agent_session import AgentProduct, ControllerGate, observation
from runtime.runproof_runtime.effectwitness.competition_agent_verify import verify
from runtime.runproof_runtime.effectwitness.product_local_contracts import canonical, digest, strict


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(dir=os.environ.get("RPF114_TEST_ROOT"))
        self.addCleanup(self.sandbox.cleanup)
        self.root = Path(self.sandbox.name)
        self.scope = patch.object(product_local_session, "ROOT", self.root)
        self.scope.start()
        self.addCleanup(self.scope.stop)
        self.owner = self.root / "owner"
        self.owner.mkdir()

    def run_session(self, **kwargs):
        with AgentProduct(self.owner, **kwargs).open() as app:
            data = app.create({"mode": MODE, "request_id": "reference-test"})
            return data, app.lookup("id", data["session_id"])[1]

    def receipts(self, session, domain):
        db = self.owner / session["session_id"] / (domain + ".sqlite")
        if not db.exists():
            return 0
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.execute("PRAGMA query_only=ON")
            return connection.execute("SELECT count(*) FROM receipts").fetchone()[0]

    def test_feedback_is_causal_and_witness_is_anchored(self):
        data, raw = self.run_session()
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(data["provider_reservations"], 0)
        self.assertEqual([self.receipts(data, d) for d in ("order", "ops")], [1, 1])
        self.assertEqual(data["rounds"][0]["after"]["order"]["refunded_minor"], 2500)
        self.assertEqual(data["rounds"][1]["after"]["config"]["release"], "release-v2")
        intents = [item["data"]["intent"] for item in data["events"] if item["kind"] == "AGENT_INTENT"]
        self.assertEqual([intent["candidate_id"] for intent in intents], ["order", "ops"])
        self.assertEqual(intents[1]["input_feedback_sha256"], data["rounds"][0]["feedback"]["sha256"])
        self.assertEqual(verify(raw, sha256(raw).hexdigest())["status"], "VERIFIED_ANCHORED")
        with self.assertRaises(ValueError):
            verify(raw, "0" * 64)
        changed = strict(raw)
        changed["session"]["events"][1]["origin"] = "forged"
        raw_changed = canonical(changed)
        with self.assertRaises(ValueError):
            verify(raw_changed, sha256(raw_changed).hexdigest())
        with AgentProduct(self.owner).open() as reopened:
            self.assertEqual(reopened.capability()["remaining"], 0)
            self.assertEqual(reopened.create({"mode": MODE, "request_id": "reference-test"}), data)
            with self.assertRaises(product_local_session.Conflict):
                reopened.create({"mode": MODE, "request_id": "different-request"})

    def test_missing_feedback_stops_before_ops(self):
        data, raw = self.run_session(feedback_view=lambda _: None)
        self.assertEqual(data["status"], "STOPPED")
        self.assertEqual([self.receipts(data, d) for d in ("order", "ops")], [1, 0])
        self.assertIsNone(raw)
        self.assertEqual(data["events"][-1]["data"]["reason"], "MUST_STOP")

    def test_wrong_feedback_hash_stops_before_ops(self):
        data, _ = self.run_session(feedback_view=lambda x: x | {"sha256": "0" * 64})
        self.assertEqual(data["status"], "STOPPED")
        self.assertEqual(self.receipts(data, "ops"), 0)

    def test_extra_args_are_refused_before_write(self):
        class Invalid(AgentPolicy):
            def propose(self, obs):
                result = super().propose(obs)
                result["arguments"]["unexpected"] = True
                return result
        data, _ = self.run_session(policy=Invalid())
        self.assertEqual([self.receipts(data, d) for d in ("order", "ops")], [0, 0])
        self.assertEqual(data["events"][-1]["data"]["reason"], "INTENT_REJECTED")

    def test_unknown_gate_blocks_order_replay(self):
        data, _ = self.run_session(feedback_view=lambda _: None)
        observed = observation(data, 1, None)
        order = tool_intent(data["candidates"][0], 1, digest(observed))
        gate = ControllerGate()
        self.assertEqual(gate.admit(order, observed, None, data["candidates"]), "APPROVED")
        gate.unknown = True
        self.assertEqual(gate.admit(order, observed, None, data["candidates"]), "UNKNOWN_PENDING")
        self.assertEqual(self.receipts(data, "order"), 1)

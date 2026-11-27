"""Focused RPF-131 regressions that can run without the optional SDK."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from runtime.runproof_runtime.effectwitness import rpf131_frames as frames, rpf131_preflight as preflight
from runtime.runproof_runtime.effectwitness import timeout_experiment as ex, timeout_jiuwen as sdk
from runtime.runproof_runtime.effectwitness.competition_agent_session import append
from runtime.runproof_runtime.effectwitness.policy_evaluation import _scoped
from runtime.runproof_runtime.effectwitness.product_local_contracts import canonical, digest, strict
from runtime.runproof_runtime.effectwitness.product_local_session import ROOT


def snapshot(folder):
    return {p.relative_to(folder): (sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in folder.rglob("*") if p.is_file()}


@contextmanager
def transcript_only(folder):
    folder.mkdir()
    yield None
    ex.write_json(folder / "audit.json", {"provider_requests": 0, "blocked_local_ipv6_probes": 0,
                                          "blocked_network_or_process_events": []})


def without_sdk(_driver, log, manifest, cell, view):
    # Construct a transcript to exercise the host and verifier independently of the SDK.
    return frames.replay(log, manifest, cell, view)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        root = _scoped(ROOT.parent / preflight.SCOPE / "tests", preflight.SCOPE)
        root.mkdir(parents=True, exist_ok=True)
        tmp = TemporaryDirectory(dir=root)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.session = uuid4().hex
        self.run_id = uuid4().hex
        self.view = {"decision_readback": {"session_id": self.session, "operation_id": self.session + "-order"},
                     "finding": "REFUND_VERIFIED"}
        self.log = preflight.SessionLog(self.root / "events.jsonl", self.session)

    def test_requires_persisted_reservation(self):
        request = frames.request_for(self.run_id, 1, self.view, None)
        ticket = frames.reservation(request, 0, 2)
        with self.assertRaisesRegex(ValueError, "^SIM_RESERVATION_REQUIRED$"):
            frames.simulated_receive(self.log, "A", ticket, request)
        self.assertEqual(self.log.events, [])

    def test_budget_denial_does_not_invoke_transport(self):
        boundary = frames.ModelBoundary(self.log, self.run_id, "exhausted", 1)
        first = boundary.call(1, self.view, None)
        receipt = sdk.receipt_for(first["call"], first["call"]["arguments"])
        with patch.object(frames, "simulated_receive", side_effect=AssertionError("no second transfer")) as sender:
            with self.assertRaisesRegex(frames.StopFrame, "^SIM_BUDGET_EXHAUSTED$"):
                boundary.call(2, self.view, receipt)
        sender.assert_not_called()
        self.assertEqual(frames.counts(self.log.events),
                         {"reserved": 1, "send_entry": 1, "sim_received": 1, "reply": 1,
                          "terminal": 1, "pending": 0, "denied": 1})

    def test_byte_caps_are_enforced(self):
        boundary = frames.ModelBoundary(self.log, self.run_id, "A", 2)
        view = self.view | {"oversized": "x" * frames.INPUT_BYTES}
        with patch.object(frames, "simulated_receive", side_effect=AssertionError("oversized input")):
            with self.assertRaisesRegex(frames.StopFrame, "^SIM_INPUT_LIMIT$"):
                boundary.call(1, view, None)
        request = frames.request_for(self.run_id, 1, self.view, None)
        projection, status = frames.analyze_reply(b"x" * (frames.OUTPUT_BYTES + 1), request, frames.OUTPUT_BYTES)
        self.assertEqual(status, "SIM_OUTPUT_LIMIT")
        self.assertIsNone(projection["reply"])

    def test_unknown_send_remains_held_and_blocks_retry(self):
        boundary = frames.ModelBoundary(self.log, self.run_id, "unknown", 2)
        with self.assertRaisesRegex(frames.StopFrame, "^SIM_SEND_UNKNOWN$"):
            boundary.call(1, self.view, None)
        with self.assertRaisesRegex(ValueError, "^SIM_NO_RETRY$"):
            boundary.call(2, self.view, None)
        self.assertEqual(frames.counts(frames.entries(self.log.path, self.session)),
                         {"reserved": 1, "send_entry": 1, "sim_received": 1, "reply": 0,
                          "terminal": 0, "pending": 1, "denied": 0})

    def test_complete_frame_and_binding_are_required(self):
        request = frames.request_for(self.run_id, 1, self.view, None)
        cases = {"incomplete": "SIM_INCOMPLETE_REPLY", "wrong-session": "SIM_REPLY_BINDING",
                 "wrong-operation": "SIM_REPLY_BINDING", "wrong-observation": "SIM_REPLY_BINDING"}
        for case, code in cases.items():
            with self.subTest(case=case):
                self.assertEqual(frames.analyze_reply(frames.fixture_bytes(case, request),
                                                      request, frames.OUTPUT_BYTES)[1], code)
        call = frames.proposal_reply(request)["call"]
        receipt = sdk.receipt_for(call, call["arguments"])
        next_request = frames.request_for(self.run_id, 2, self.view, receipt)
        reply = frames.fixture_bytes("wrong-receipt", next_request)
        self.assertEqual(frames.analyze_reply(reply, next_request, frames.OUTPUT_BYTES)[1], "SIM_TOOL_RECEIPT_BINDING")

    def suite_without_sdk(self):
        folder = self.root / "suite"
        with (patch.object(sdk, "environment", side_effect=sdk._locked),
              patch.object(sdk, "driver", side_effect=transcript_only),
              patch.object(preflight.react, "run", side_effect=without_sdk)):
            preflight.run(folder)
        return folder

    def test_host_frames_and_read_only_reopen(self):
        folder = self.suite_without_sdk()
        before = snapshot(folder)
        original_connect = sqlite3.connect
        paths = []

        def readonly(path, **kwargs):
            self.assertTrue(kwargs["uri"])
            self.assertTrue(path.endswith("?mode=ro"), path)
            paths.append(path)
            return original_connect(path, **kwargs)

        with (patch.object(preflight.react, "run", side_effect=AssertionError("model restart")),
              patch.object(preflight, "run_cell", side_effect=AssertionError("business restart")),
              patch.object(frames, "simulated_receive", side_effect=AssertionError("retransmission")),
              patch.object(sqlite3, "connect", side_effect=readonly)):
            report = preflight.verify(folder)
        cells = {row["cell"]["name"]: row for row in report["cells"]}
        self.assertEqual(len(paths), 20)
        self.assertEqual(snapshot(folder), before)
        self.assertEqual([cells[name]["receipts"] for name in "ABC"], [[1, 1], [0, 0], [1, 0]])
        self.assertEqual(cells["C"]["frames"], frames.counts([]))
        self.assertEqual(cells["C"]["model_invocations"], 0)
        for name in ("incomplete", "wrong-session", "wrong-operation", "wrong-observation", "wrong-receipt", "exhausted"):
            self.assertIsNone(cells[name]["proposal"], name)
            self.assertEqual(cells[name]["receipts"], [1, 0], name)
        with self.assertRaisesRegex(ValueError, "^OUTPUT_EXISTS$"):
            preflight.run(folder)
        self.assertEqual(snapshot(folder), before)

    def test_foreign_reservation_is_rejected_even_after_rehash(self):
        folder = self.suite_without_sdk()
        a, b = (folder / "cells" / name / "events.jsonl" for name in ("A", "B"))
        manifest = strict((folder / "manifest.json").read_bytes())
        cell_a, cell_b = manifest["cells"][:2]
        first = frames.entries(a, cell_a["session_id"])
        second = frames.entries(b, cell_b["session_id"])
        foreign = next(event["data"] for event in second if event["kind"] == "SIM_RESERVED")
        changed = {"session_id": cell_a["session_id"], "events": []}
        for row in first:
            data = foreign if row["kind"] == "SIM_RESERVED" else row["data"]
            append(changed, row["kind"], row["origin"], data)
        a.write_bytes(b"".join(canonical(event) + b"\n" for event in changed["events"]))
        with self.assertRaisesRegex(ValueError, "^REPLAY_SIM_RESERVED$"):
            preflight.verify(folder)

    def test_recomputed_export_cannot_hide_pending_budget(self):
        folder = self.suite_without_sdk()
        file = folder / "report.json"
        body = strict(file.read_bytes())
        body.pop("report_sha256")
        body["simulation"]["pending"] = 0
        file.write_bytes(canonical(body | {"report_sha256": digest(body)}))
        with self.assertRaisesRegex(ValueError, "^EXPORT_MISMATCH$"):
            preflight.verify(folder)

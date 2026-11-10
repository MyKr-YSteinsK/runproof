"""Owner arbitration, interrupted tickets and fail-closed SQLite writes."""
from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
import sys
from threading import Barrier
import unittest
from unittest.mock import patch

from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner
from runtime.runproof_runtime.effectwitness import pge_r110_contracts as c
from runtime.runproof_runtime.effectwitness import pge_r110_explorer as explorer, pge_r110_provider as provider
from runtime.runproof_runtime.effectwitness.pge_r110_oracle import fresh, readback
from runtime.runproof_runtime.effectwitness.pge_r110_session import Controller, Session
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import REPO, canonical

LOCAL = os.environ.get("RPF110_LOCAL_SQLITE") == "1"
SOURCE = os.environ.get("RPF110_SOURCE_SHA", c.BASE)


@unittest.skipUnless(LOCAL, "Requires admitted RPF-110 fixture owner")
class PresendTests(unittest.TestCase):
    def test_thread_race_and_one_use_permit(self):
        with Session(SOURCE, "FIXTURE_ONLY") as session:
            req = c.request(session.presend.contract)
            barrier = Barrier(2)

            def attempt(_):
                barrier.wait(timeout=5)
                return session.reserve(req)

            with ThreadPoolExecutor(max_workers=2) as threads:
                permits = [p for p in threads.map(attempt, range(2)) if p is not None]
            self.assertEqual(len(permits), 1)
            raw = provider.fixture(inner.OPS, "race")
            with self.assertRaisesRegex(ValueError, "SEND_PERMIT"):
                session.exchange(object(), raw)
            session.exchange(permits[0], raw)
            with self.assertRaisesRegex(ValueError, "SEND_PERMIT"):
                session.exchange(permits[0], raw)
            self.assertEqual([e["kind"] for e in session.presend.journal.events].count("PROVIDER_RESERVE"), 1)

    def test_two_processes_one_owner_and_abrupt_exit(self):
        owner = fresh()
        controller = Controller(owner, SOURCE)
        try:
            seed = controller.apply(inner.SEED)
            view = controller.ledger.snapshot()
            contract = c.freeze(controller.frozen, view, seed, "FIXTURE_ONLY")
        finally:
            controller.ledger.close()
        program = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from runtime.runproof_runtime.effectwitness.pge_r110_presend import Presend
from runtime.runproof_runtime.effectwitness.pge_r110_contracts import request
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import strict
view, contract = strict(sys.stdin.buffer.read())
try:
    edge = Presend(Path.cwd(), contract)
except (ValueError, FileExistsError):
    os._exit(11)
permit = edge.reserve(request(contract), view)
os._exit(7 if permit is not None else 12)
"""
        command = [sys.executable, "-I", "-S", "-B", "-c", program, str(REPO)]
        payload = canonical([view, contract])
        with ThreadPoolExecutor(max_workers=2) as threads:
            outcomes = list(threads.map(lambda _: subprocess.run(command, cwd=owner, input=payload,
                                                                 timeout=12).returncode, range(2)))
        self.assertCountEqual(outcomes, [7, 11])
        wal = (owner / "presend.jsonl").read_bytes()
        self.assertEqual(wal.count(b'"kind":"PROVIDER_RESERVE"'), 1)
        self.assertNotIn(b"FIXTURE_SEND_ENTRY", wal)
        self.assertEqual(subprocess.run(command, cwd=owner, input=payload, timeout=12).returncode, 11)
        self.assertEqual((owner / "presend.jsonl").read_bytes(), wal)

    def test_presend_and_after_send_windows(self):
        for stage in ("BEFORE_RESERVE", "AFTER_RESERVE", "AFTER_SEND_INTENT", "AFTER_ENTRY"):
            with self.subTest(stage=stage), Session(SOURCE, "FIXTURE_ONLY") as session:
                edge = session.presend
                edge.fault = stage
                raw = c.request(edge.contract)
                with self.assertRaisesRegex(OSError, stage):
                    permit = session.reserve(raw)
                    session.exchange(permit, provider.fixture(inner.ORDER, "fault"))
                self.assertIsNone(session.reserve(raw))
                events = [e["kind"] for e in edge.journal.events]
                self.assertEqual(events.count("PROVIDER_RESERVE"), int(stage != "BEFORE_RESERVE"))
                self.assertNotIn("FIXTURE_RETURN", events)

    def test_write_and_latch_windows_preserve_actual_sqlite_facts(self):
        for stage in ("WRITE_INTENT", "AFTER_SQLITE_COMMIT", "UNKNOWN", "BEFORE_TERMINAL"):
            with self.subTest(stage=stage), Session(SOURCE, "FIXTURE_ONLY") as session:
                edge = session.presend
                req = c.request(edge.contract)
                choice = session.exchange(session.reserve(req), provider.fixture(inner.OPS, "commit-window"))
                if stage == "BEFORE_TERMINAL":
                    edge.fault = stage
                else:
                    session.controller.fault = stage
                with self.assertRaisesRegex(OSError, stage):
                    session.select(explorer.callback(choice))
                frozen = session.controller.frozen["catalog"][inner.OPS]
                actual = readback(session.owner, frozen)
                self.assertEqual(len(actual["snapshot"]["receipts"]), int(stage != "WRITE_INTENT"))
                original = session.controller.ledger.path.read_bytes()
                self.assertIsNone(session.reserve(req))
                self.assertEqual(session.controller.ledger.path.read_bytes(), original)
                with self.assertRaises(ValueError):
                    session.select(explorer.callback(choice))

    def test_business_writer_rejects_forged_and_consumed_permits(self):
        with Session(SOURCE, "FIXTURE_ONLY") as session:
            target = session.controller.target
            actual = target.apply
            attempted = []

            def assert_permit(contract, permit):
                with self.assertRaisesRegex(ValueError, "WRITER_PERMIT"):
                    actual(contract, object())
                actual(contract, permit)
                with self.assertRaisesRegex(ValueError, "WRITER_PERMIT"):
                    actual(contract, permit)
                attempted.append(contract["candidate_id"])

            with patch.object(target, "apply", side_effect=assert_permit):
                session.run(inner.OPS)
            self.assertEqual(attempted, [inner.OPS])
            snapshot = readback(session.owner, session.controller.frozen["catalog"][inner.OPS])
            self.assertEqual(len(snapshot["snapshot"]["receipts"]), 1)

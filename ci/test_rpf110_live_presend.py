"""Cross-process exclusivity and abrupt exits around durable ticket transitions."""
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
from threading import Barrier
import unittest

from ci.test_rpf110_live_transport import LOCAL, SOURCE, stub
from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner
from runtime.runproof_runtime.effectwitness import pge_r110_live_contracts as c
from runtime.runproof_runtime.effectwitness.pge_r110_live_session import Session
from runtime.runproof_runtime.effectwitness.pge_r110_oracle import fresh, readback
from runtime.runproof_runtime.effectwitness.pge_r110_session import Controller
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import REPO, canonical, strict

PROGRAM = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from runtime.runproof_runtime.effectwitness.pge_r110_live_presend import Presend
from runtime.runproof_runtime.effectwitness.pge_r110_live_contracts import request, STUB
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import strict
view, contract, kill = strict(sys.stdin.buffer.read())
def hook(stage):
    if kill == stage:
        os._exit(7)
try:
    edge = Presend(Path.cwd(), contract, hook=hook)
except (ValueError, FileExistsError):
    os._exit(11)
raw = request(contract)
edge.enter(edge.reserve(raw, view), raw, view, STUB)
os._exit(7)
"""


def fresh_seed():
    owner = fresh()
    host = Controller(owner, SOURCE)
    try:
        seed = host.apply(inner.SEED)
        view = host.ledger.snapshot()
        return owner, view, c.freeze(host.frozen, view, seed, c.STUB)
    finally:
        host.ledger.close()


def child(owner, view, contract, kill):
    return subprocess.run([sys.executable, "-I", "-S", "-B", "-c", PROGRAM, str(REPO)], cwd=owner,
                          input=canonical([view, contract, kill]), timeout=12).returncode


@unittest.skipUnless(LOCAL, "Requires admitted RPF-110 fresh SQLite")
class LivePresendTests(unittest.TestCase):
    def test_one_process_wins_and_third_cannot_reopen(self):
        owner, view, contract = fresh_seed()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(lambda _: child(owner, view, contract, "AFTER_PROVIDER_RESERVE"),
                                          range(2)), [7, 11])
        wal = owner / "presend-live.jsonl"
        before = wal.read_bytes()
        self.assertEqual(before.count(b'"kind":"PROVIDER_RESERVE"'), 1)
        self.assertEqual(child(owner, view, contract, None), 11)
        self.assertEqual(wal.read_bytes(), before)

    def test_abrupt_exit_before_and_after_each_durable_transition(self):
        ordered = ["PROVIDER_RESERVE", "SEND_INTENT", "STUB_SEND_ENTRY"]
        for index, kind in enumerate(ordered):
            for side in ("BEFORE", "AFTER"):
                with self.subTest(kind=kind, side=side):
                    owner, view, contract = fresh_seed()
                    self.assertEqual(child(owner, view, contract, side + "_" + kind), 7)
                    wal = owner / "presend-live.jsonl"
                    raw = wal.read_bytes()
                    events = [strict(line)["kind"] for line in raw.splitlines()]
                    self.assertEqual(events, ["OPEN", "HOST_REQUEST_READY"] + ordered[:index + (side == "AFTER")])
                    self.assertNotIn("SEND_ENTRY", events)
                    self.assertEqual(child(owner, view, contract, None), 11)
                    self.assertEqual(wal.read_bytes(), raw)

    def test_threads_and_stale_feedback(self):
        with Session(SOURCE, c.STUB) as session:
            raw = c.request(session.contract)
            barrier = Barrier(2)

            def reserve(_):
                barrier.wait(timeout=5)
                return session.reserve(raw)

            with ThreadPoolExecutor(max_workers=2) as pool:
                permits = [item for item in pool.map(reserve, range(2)) if item is not None]
            self.assertEqual(len(permits), 1)
            view = session.host.ledger.snapshot()
            with self.assertRaisesRegex(ValueError, "LIVE_PERMIT"):
                session.edge.enter(object(), raw, view, c.STUB)
            with self.assertRaisesRegex(ValueError, "SEND_BINDING"):
                session.edge.enter(permits[0], raw, view | {"revision": 0}, c.STUB)
            self.assertIsNone(session.reserve(raw))
            self.assertNotIn("STUB_SEND_ENTRY", [event["kind"] for event in session.edge.journal.events])

    def test_unknown_before_or_after_business_commit_is_read_only(self):
        for fault in ("WRITE_INTENT", "AFTER_SQLITE_COMMIT", "UNKNOWN"):
            with self.subTest(fault=fault), Session(SOURCE, c.STUB) as session:
                session.host.fault = fault
                with stub() as (port, seen):
                    with self.assertRaises(OSError):
                        session.run(port=port)
                    self.assertEqual(len(seen), 1)
                wal = session.host.ledger.path.read_bytes()
                result = readback(session.owner, session.host.frozen["catalog"][inner.OPS])
                self.assertEqual(len(result["snapshot"]["receipts"]), int(fault != "WRITE_INTENT"))
                self.assertIsNone(session.reserve(c.request(session.contract)))
                self.assertEqual(session.host.ledger.path.read_bytes(), wal)

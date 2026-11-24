"""Offline owner integrity, real process interruption and independent readback."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
from uuid import uuid4

from runtime.runproof_runtime.effectwitness.competition_agent import MODE
from runtime.runproof_runtime.effectwitness.competition_agent_session import AgentProduct
from runtime.runproof_runtime.effectwitness.competition_agent_verify import verify
from runtime.runproof_runtime.effectwitness.product_local_contracts import canonical, digest, strict
from runtime.runproof_runtime.effectwitness.product_local_session import ROOT, Conflict


def fresh():
    return ROOT / ("competition-rpf114-" + uuid4().hex)


def hashes(owner):
    return {p.relative_to(owner).as_posix(): sha256(p.read_bytes()).hexdigest()
            for p in owner.rglob("*") if p.is_file()}


def child(owner, boundary):
    class Checkpoint(AgentProduct):
        def emit(self, record, kind, origin, data):
            super().emit(record, kind, origin, data)
            if kind == boundary:
                print(record["session_id"], flush=True)
                sys.stdin.readline()  # The supervising test kills the child at this checkpoint.
                raise RuntimeError("supervisor returned without interrupting")
    Checkpoint.initialize(owner)
    with Checkpoint(owner).open() as app:
        app.create({"mode": MODE, "request_id": "controlled-interruption"})


class RecoveryTests(unittest.TestCase):
    def test_owner_init_race_and_reservation_consistency(self):
        owner = fresh()
        def claim(_):
            try:
                AgentProduct.initialize(owner)
                return 1
            except FileExistsError:
                return 0
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(pool.map(claim, range(2))), 1)
        with AgentProduct(owner).open() as app:
            req = {"mode": MODE, "request_id": "concurrent-request"}
            with ThreadPoolExecutor(2) as pool:
                one, two = pool.map(app.create, [req, req])
            self.assertEqual(one, two)
            report = app.investigate(one)
            self.assertEqual([len(r["snapshot"]["receipts"]) for r in report["readings"]], [1, 1])
            with self.assertRaises(Conflict):
                app.create(req | {"owner_id": "0" * 32})
        # Operate only on separately created copies, preserving the successful run.
        for failure in ("missing", "corrupt", "schema", "binding", "marker", "reservation"):
            copy = ROOT / "tests" / uuid4().hex / owner.name
            shutil.copytree(owner, copy)
            ledger = copy / "ledger.sqlite"
            if failure == "missing":
                ledger.rename(copy / "retained-ledger")
            elif failure == "corrupt":
                ledger.write_bytes(b"synthetic invalid bytes")
            elif failure == "schema":
                with closing(sqlite3.connect(ledger)) as db, db:
                    db.execute("ALTER TABLE sessions ADD COLUMN unrelated TEXT")
            elif failure == "binding":
                (copy / "owner.json").write_bytes(b"{}")
            else:
                marker = copy / ("owner.json" if failure == "marker" else "reservation-0")
                marker.rename(copy / "retained-marker")
            before = hashes(copy)
            with self.subTest(failure=failure):
                for operation in (lambda: AgentProduct(copy).capability(),
                                  lambda: AgentProduct(copy).lookup("request", req["request_id"]),
                                  lambda: AgentProduct(copy).open().__enter__()):
                    with self.assertRaises((sqlite3.Error, OSError, ValueError, KeyError)):
                        operation()
                self.assertEqual(hashes(copy), before)
        half = fresh()
        half.mkdir()
        with self.assertRaises((ValueError, sqlite3.Error)):
            with AgentProduct(half).open():
                self.fail("partial owner admitted")
        with self.assertRaises(FileExistsError):
            AgentProduct.initialize(half)

    def test_stopped_and_readback_gaps(self):
        owner = fresh()
        AgentProduct.initialize(owner)
        with AgentProduct(owner, feedback_view=lambda _: None).open() as app:
            record = app.create({"mode": MODE, "request_id": "feedback-unavailable"})
            self.assertEqual(record["status"], "STOPPED")
            verified = verify(canonical(app.investigate(record)))
            self.assertEqual(verified["assessment"]["task_completion"], "NOT_ESTABLISHED")
        for fault, expected in (("environment", "AUTHORITY_IDENTITY_MISMATCH"), ("receipt", "STATE_RECEIPT_MISMATCH"),
                                ("unreadable", "TARGET_UNREADABLE")):
            copy = ROOT / "tests" / uuid4().hex / owner.name
            shutil.copytree(owner, copy)
            dbpath = copy / record["session_id"] / "order.sqlite"
            if fault == "unreadable":
                dbpath.write_bytes(b"unreadable test fixture")
            else:
                with closing(sqlite3.connect(dbpath)) as db, db:
                    db.execute("UPDATE identity SET environment='wrong'" if fault == "environment" else "DELETE FROM receipts")
            before = hashes(copy)
            with AgentProduct(copy).open(readonly=True) as app:
                report = app.investigate(app.lookup("id", record["session_id"])[0])
                self.assertIn(expected, (report["summary"]["domains"][0]["effect"], report["readings"][0]["error"]))
                verify(canonical(report))
            self.assertEqual(hashes(copy), before)

    def test_process_interruptions(self):
        for point, receipts in (("WRITE_INTENT", 0), ("UNKNOWN_OBSERVED", 1)):
            owner = fresh()
            with subprocess.Popen([sys.executable, "-B", "-m", "ci.test_rpf115_recovery", "--child",
                                   str(owner), point], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) as proc:
                with ThreadPoolExecutor(1) as pool:
                    try:
                        ident = pool.submit(proc.stdout.readline).result(timeout=25).strip()
                        self.assertRegex(ident, r"^[a-f0-9]{32}$")
                    finally:
                        proc.kill()
                        proc.wait(timeout=10)
            before = hashes(owner)
            with AgentProduct(owner).open(readonly=True) as app:
                record, witness = app.lookup("request", "controlled-interruption")
                self.assertIsNone(witness)
                self.assertEqual(record["session_id"], ident)
                self.assertEqual(app.capability()["remaining"], 0)
                with self.assertRaises(Conflict):
                    app.create({"mode": MODE, "request_id": "controlled-interruption"})
                report = app.investigate(record)
                self.assertEqual(len(report["readings"][0]["snapshot"]["receipts"]), receipts)
                self.assertEqual(report["readings"][1]["error"], "TARGET_ABSENT")
                raw = canonical(report)
                # Acquire the digest in this read-only process separately from the CLI export.
                anchor = sha256(raw).hexdigest()
                self.assertEqual(verify(raw, anchor)["status"], "VERIFIED_ANCHORED")
                bad = strict(raw)
                bad["readings"][0]["operation"] = "different"
                bad["content_sha256"] = digest({k:v for k,v in bad.items() if k != "content_sha256"})
                for fixed in (anchor, None):
                    with self.assertRaises(ValueError):
                        verify(canonical(bad), fixed)
            self.assertEqual(hashes(owner), before)
            if os.environ.get("RPF115_EVIDENCE"):
                target = Path(os.environ["RPF115_EVIDENCE"]).resolve()
                scope = Path(".local/rpf-115").resolve()
                if not target.is_relative_to(scope):
                    raise ValueError("EVIDENCE_SCOPE")
                folder = target / point
                folder.mkdir(parents=True, exist_ok=False)
                (folder / "report.json").write_bytes(raw)
                (folder / "receipt.json").write_bytes(canonical({
                    "owner": owner.name, "pid": proc.pid, "exit": proc.returncode, "session": ident,
                    "anchor": anchor, "files_before": before, "files_after": hashes(owner)}))
                print(point, owner.name, proc.pid, ident, anchor, flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        child(Path(sys.argv[2]), sys.argv[3])
    else:
        unittest.main()

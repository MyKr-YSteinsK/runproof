"""Provider-zero regression and semantic negative controls for RPF-128 / RPF-129."""
from hashlib import sha256
import http.client
from pathlib import Path
from shutil import copytree
import socket
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from runtime.runproof_runtime.effectwitness import timeout_experiment as experiment
from runtime.runproof_runtime.effectwitness import timeout_jiuwen as jiuwen
from runtime.runproof_runtime.effectwitness.competition_agent_session import append
from runtime.runproof_runtime.effectwitness.product_local_contracts import canonical, digest, strict
from runtime.runproof_runtime.effectwitness.product_local_session import ROOT


def fingerprint(root):
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns, sha256(p.read_bytes()).hexdigest())
            for p in root.rglob("*") if p.is_file()}


def read_report(root):
    return strict((root / "report.json").read_bytes())


def save_report(root, report):
    body = {k: v for k, v in report.items() if k != "report_sha256"}
    (root / "report.json").write_bytes(canonical(body | {"report_sha256": digest(body)}))


def events(root, name):
    return [strict(line) for line in (root / "cells" / name / "events.jsonl").read_bytes().splitlines()]


def rewrite_event(root, name, kind, replace):
    original = events(root, name)
    record = {"session_id": original[0]["session_id"], "events": []}
    for old in original:
        value = replace(old["data"]) if old["kind"] == kind else old["data"]
        append(record, old["kind"], old["origin"], value)
    encoded = b"".join(canonical(item) + b"\n" for item in record["events"])
    (root / "cells" / name / "events.jsonl").write_bytes(encoded)
    report = read_report(root)
    row = next(row for row in report["cases"] if row["session_id"] == record["session_id"])
    row["events_sha256"] = sha256(encoded).hexdigest()
    save_report(root, report)


class TimeoutExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = experiment.scope(ROOT.parent / experiment.SCOPE / "tests")
        root.mkdir(parents=True, exist_ok=True)
        tmp = TemporaryDirectory(dir=root)
        cls.addClassCleanup(tmp.cleanup)
        cls.root = Path(tmp.name)
        cls.good = cls.root / "good"
        cls.foreign = cls.root / "foreign"
        experiment.run_suite(cls.good)
        experiment.run_suite(cls.foreign)

    def mutation(self):
        return copytree(self.good, self.root / self._testMethodName)

    def test_same_timeout_and_distinct_decision_evidence(self):
        rows = experiment.verify_suite(self.good)["cases"]
        self.assertEqual([row["decision"]["timeout"] for row in rows], [experiment.SIGNAL] * 3)
        self.assertEqual([row["decision"]["finding"] for row in rows], list(experiment.ACTIONS))
        self.assertEqual([row["receipt_counts"] for row in rows],
                         [{"order": 1, "ops": 1}, {"order": 0, "ops": 0}, {"order": 1, "ops": 0}])
        self.assertEqual([row["retry_attempts"] for row in rows], [0, 0, 0])
        self.assertIsNone(rows[2]["decision"]["decision_readback"]["snapshot"])
        self.assertEqual(len(rows[2]["after"]["order"]["receipts"]), 1)
        self.assertEqual(len({row["operations"]["order"]["operation_id"] for row in rows}), 3)

    def test_verifier_only_connects_to_sqlite_read_only(self):
        before = fingerprint(self.good)
        connect = sqlite3.connect
        calls = []

        def audited(path, **kwargs):
            self.assertTrue(kwargs["uri"])
            self.assertTrue(path.endswith("?mode=ro"), path)
            calls.append(path)
            return connect(path, **kwargs)

        with (patch.object(sqlite3, "connect", side_effect=audited),
              patch.object(http.client.HTTPConnection, "request", side_effect=AssertionError("HTTP")),
              patch.object(socket, "socket", side_effect=AssertionError("socket")),
              patch.object(experiment, "run_cell", side_effect=AssertionError("rerun")),
              patch.object(jiuwen, "_react", side_effect=AssertionError("SDK replay"))):
            self.assertEqual(experiment.verify_suite(self.good), experiment.verify_suite(self.good))
        self.assertEqual(len(calls), 12)
        self.assertEqual(fingerprint(self.good), before)

    def test_foreign_proposal_rejected_after_rehash(self):
        target = self.mutation()
        foreign = next(item["data"] for item in events(self.foreign, "B-follow") if item["kind"] == "PROPOSAL")
        rewrite_event(target, "B-follow", "PROPOSAL", lambda _: foreign)
        with self.assertRaisesRegex(ValueError, "^PROPOSAL_BINDING$"):
            experiment.verify_suite(target)

    def test_foreign_evidence_rejected_after_rehash(self):
        target = self.mutation()
        foreign = next(item["data"] for item in events(self.foreign, "B-follow") if item["kind"] == "DECISION_READBACK")
        rewrite_event(target, "B-follow", "DECISION_READBACK", lambda _: foreign)
        with self.assertRaisesRegex(ValueError, "^EVIDENCE_BINDING$"):
            experiment.verify_suite(target)

    def test_missing_decision_readback_does_not_imply_absence(self):
        target = self.mutation()
        rewrite_event(target, "B-follow", "DECISION_READBACK",
                      lambda data: data | {"status": "UNAVAILABLE", "snapshot": None,
                                           "reason": "FIXTURE_AUTHORITY_UNAVAILABLE"})
        with self.assertRaisesRegex(ValueError, "^DECISION_READBACK_REQUIRED$"):
            experiment.verify_suite(target)

    def test_later_sql_read_cannot_become_decision_evidence(self):
        target = self.mutation()
        earlier = read_report(self.good)["cases"][2]
        rewrite_event(target, "C-follow", "DECISION_READBACK",
                      lambda data: data | {"status": "READ", "snapshot": earlier["after"]["order"], "reason": None})
        with self.assertRaisesRegex(ValueError, "^DECISION_READBACK_REQUIRED$"):
            experiment.verify_suite(target)

    def test_zero_receipts_without_closed_rollback_rejected(self):
        target = self.mutation()
        rewrite_event(target, "B-follow", "EXECUTOR_CLOSED", lambda data: data | {"connection_closed": False})
        with self.assertRaisesRegex(ValueError, "^EXECUTOR_CLOSURE$"):
            experiment.verify_suite(target)
        original = events(self.good, "B-follow")
        manifest = strict((self.good / "manifest.json").read_bytes())
        record = experiment.case_record(manifest, manifest["cells"][1])
        view = experiment.decision_view(record, original[1]["data"]["before"],
                                        original[2]["data"] | {"connection_closed": False}, original[4]["data"])
        self.assertEqual(view["finding"], "UNRESOLVED")

    def test_repeat_output_is_rejected_without_changes(self):
        before = fingerprint(self.good)
        with self.assertRaisesRegex(ValueError, "^OUTPUT_EXISTS$"):
            experiment.run_suite(self.good)
        self.assertEqual(fingerprint(self.good), before)

    def test_export_tamper_rejected_even_with_recomputed_digest(self):
        target = self.mutation()
        report = read_report(target)
        report["cases"][1]["receipt_counts"]["ops"] = 1
        save_report(target, report)
        with self.assertRaisesRegex(ValueError, "^EXPORT_MISMATCH$"):
            experiment.verify_suite(target)

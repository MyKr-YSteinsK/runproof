"""Controller contention and fail-closed tests against actual task-owned files."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
from threading import Barrier
import unittest
from unittest.mock import patch

from ci.test_rpf106_candidates import LOCAL_SQLITE, SOURCE
from runtime.runproof_runtime.effectwitness import pge_r106_contracts as c, pge_r106_oracle as oracle
from runtime.runproof_runtime.effectwitness.pge_r106_controller import Controller
from runtime.runproof_runtime.effectwitness.pge_r106_ledger import replay
from runtime.runproof_runtime.effectwitness.pge_r106_replay import prepare_root
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical


def emit(label, **fields):
    if os.environ.get("RPF106_REPORT") == "1":
        print("RPF106_CONTROL " + canonical({"control": label, **fields}).decode(), flush=True)


def execute(host, candidate):
    offered = host.proposal(candidate)
    return host.apply(offered, host.evaluate(offered))


def rechain(rows):
    tip = "0" * 64
    raw = []
    for revision, row in enumerate(rows, 1):
        core = {"revision": revision, "prev": tip, "kind": row["kind"], "body": row["body"]}
        tip = c.digest(core)
        raw.append(canonical({**core, "sha256": tip}) + b"\n")
    return b"".join(raw)


@unittest.skipUnless(LOCAL_SQLITE, "Requires authorized task-owned SQLite root")
class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepare_root()

    def seed(self, host):
        result = execute(host, c.SEED)
        self.assertEqual(result["execution"], "VERIFIED", result)
        return result

    def test_same_revision_race_spends_once(self):
        with Controller(SOURCE) as host:
            self.seed(host)
            offers = [host.proposal(name) for name in (c.ORDER, c.OPS)]
            decisions = [host.evaluate(row) for row in offers]
            self.assertEqual([row["status"] for row in decisions], ["ACCEPT", "ACCEPT"])
            self.assertEqual(decisions[0]["view_sha256"], decisions[1]["view_sha256"])
            barrier = Barrier(2)

            def compete(pair):
                barrier.wait(timeout=10)
                return host.apply(*pair)

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(compete, zip(offers, decisions)))
            self.assertCountEqual([row["execution"] for row in outcomes], ["VERIFIED", "NOT_RUN"])
            report = oracle.inspect(host.owner_id)
            self.assertEqual(len(report["claimed"]), 2)
            self.assertEqual(report["remaining"], c.ZERO)
            self.assertEqual(report["verified_business_transactions"], 2)
            self.assertEqual(report["post_unknown_effect_events"], 0)
            emit("same_revision_race", owner=host.owner_id, outcomes=[row["execution"] for row in outcomes],
                 claimed=report["claimed"], verified_transactions=2, wal_sha256=report["wal_sha256"])

    def test_forgery_cross_run_and_explicit_stop(self):
        with Controller(SOURCE) as host, Controller(SOURCE) as other:
            offered = host.proposal(c.SEED)
            accepted = host.evaluate(offered)
            before = host.ledger.path.read_bytes()
            forged = [
                (offered, accepted | {"decision_sha256": "0" * 64}, "DECISION_CHANGED"),
                (offered | {"oracle": {"outcome": c.SUCCESS}}, None, "PROPOSAL_SCHEMA"),
                (offered | {"authority": {"schema": "rpf104-authority"}}, None, "PROPOSAL_SCHEMA"),
                (offered | {"contract_sha256": "0" * 64}, None, "CANDIDATE_ANCHOR"),
                (other.proposal(c.SEED), None, "STALE_REVISION"),
                (offered | {"view_sha256": c.digest({"remaining": c.LIMIT})}, None, "STALE_REVISION"),
            ]
            for proposal, decision, reason in forged:
                with self.subTest(reason=reason):
                    actual = host.apply(proposal, decision if decision is not None else host.evaluate(proposal))
                    self.assertEqual((actual["execution"], actual["reason"]), ("NOT_RUN", reason))
            with self.assertRaisesRegex(ValueError, "WRITER_SCOPE"):
                host.target.apply(host.frozen["catalog"][c.SEED], object())
            self.assertEqual(host.ledger.path.read_bytes(), before)
            self.assertEqual(host.apply(offered, accepted)["execution"], "VERIFIED")
            self.assertEqual(host.evaluate(offered)["reason"], "DUPLICATE_PROPOSAL")
            self.assertEqual(host.evaluate(offered | {"proposal_id": "0" * 32})["reason"], "STALE_REVISION")
            self.assertEqual(execute(host, c.STOP)["reason"], "EXPLICIT_STOP")
            self.assertEqual(execute(host, c.OPS)["admission"]["status"], "MUST_STOP")
            report = oracle.inspect(host.owner_id)
            self.assertEqual(report["claimed"], [c.SEED])
            self.assertEqual(report["remaining"], c.COST)
            self.assertEqual(oracle.inspect(other.owner_id)["verified_business_transactions"], 0)
            emit("forgery_and_stop", owner=host.owner_id, foreign_owner=other.owner_id,
                 rejection_reasons=[reason for _, _, reason in forged],
                 verified_transactions=1, wal_sha256=report["wal_sha256"])

    def test_reanchored_wal_and_torn_suffix_reject(self):
        with Controller(SOURCE) as host:
            self.seed(host)
            self.assertEqual(execute(host, c.OPS)["execution"], "VERIFIED")
            raw = host.ledger.path.read_bytes()
            _, rows = replay(raw)
            self.assertEqual(rechain(rows), raw)
            tampered = deepcopy(rows)
            next(row for row in tampered if row["kind"] == "CLAIMED")["body"]["remaining"]["write_slots"] = 2
            with self.assertRaisesRegex(ValueError, "CLAIM_BUDGET"):
                replay(rechain(tampered))
            claim = next(row for row in rows if row["kind"] == "CLAIMED")
            with self.assertRaisesRegex(ValueError, "CLAIM_CAS"):
                replay(rechain([*rows, claim]))
            with self.assertRaisesRegex(ValueError, "WAL_TORN"):
                replay(raw[:-1])
            self.assertEqual(host.ledger.path.read_bytes(), raw)
            emit("reanchored_and_torn_wal", owner=host.owner_id, verified_transactions=2, wal_sha256=c.sha(raw))

    def test_writer_permit_one_use_and_missing_database_unavailable(self):
        with Controller(SOURCE) as host:
            seed_contract = host.frozen["catalog"][c.SEED]
            ops_contract = host.frozen["catalog"][c.OPS]
            actual_writer = host.target.apply

            def exercise(contract, permit):
                with self.assertRaisesRegex(ValueError, "WRITER_PERMIT"):
                    actual_writer(contract, object())
                with self.assertRaisesRegex(ValueError, "WRITER_SCOPE"):
                    actual_writer(ops_contract, permit)
                actual_writer(contract, permit)
                with self.assertRaisesRegex(ValueError, "WRITER_PERMIT"):
                    actual_writer(contract, permit)

            with patch.object(host.target, "apply", side_effect=exercise):
                self.seed(host)
            _, rows = host.ledger.persisted()
            self.assertEqual(oracle.reconcile(host.owner, ops_contract, rows),
                             {"outcome": "UNAVAILABLE", "authority": None})
            historical = {"schema": "rpf104-authority-v1", "mode": "SQLITE_RO_QUERY_ONLY",
                          "binding": c.binding(seed_contract), "snapshot": {}}
            with self.assertRaisesRegex(ValueError, "ORACLE_AUTHORITY"):
                oracle.evaluate(seed_contract, historical, historical)
            report = oracle.inspect(host.owner_id)
            self.assertEqual(report["verified_business_transactions"], 1)
            emit("one_use_permit_and_missing_authority", owner=host.owner_id, verified_transactions=1,
                 missing_authority="UNAVAILABLE", wal_sha256=report["wal_sha256"])

    def test_each_interruption_reconciles_read_only_and_reopen_refuses(self):
        for stage in ("WRITE_INTENT", "AFTER_SQLITE_COMMIT", "UNKNOWN", "AUTHORITY_AFTER", "ORACLE_VERDICT"):
            with self.subTest(stage=stage), Controller(SOURCE) as host:
                seed = self.seed(host)
                pending = host.proposal(c.ORDER)
                host.failure = stage
                result = execute(host, c.OPS)
                self.assertEqual(result["execution"], "INCONCLUSIVE")
                expected = "NOT_COMMITTED" if stage == "WRITE_INTENT" else "COMMITTED"
                self.assertEqual(result["writer_attempted"], expected == "COMMITTED")
                identity = c.binding(host.frozen["catalog"][c.OPS])
                raw = host.ledger.path.read_bytes()
                reconciled = host.reconcile(identity)
                self.assertEqual(reconciled["outcome"], expected)
                self.assertEqual(len(reconciled["authority"]["snapshot"]["receipts"]), int(expected == "COMMITTED"))
                for key in ("source_git_sha", "run_id", "owner", "operation_id", "environment_id", "contract_sha256"):
                    with self.assertRaisesRegex(ValueError, "RECONCILIATION_SCOPE"):
                        host.reconcile(identity | {key: "foreign"})
                for offered in (pending, host.proposal(c.ORDER), host.proposal(c.OPS)):
                    blocked = host.apply(offered, host.evaluate(offered))
                    self.assertEqual((blocked["execution"], blocked["admission"]["status"]), ("NOT_RUN", "MUST_STOP"))
                self.assertEqual(host.ledger.snapshot()["feedback_sha256"], seed["feedback_sha256"])
                with self.assertRaisesRegex(ValueError, "WRITER_SCOPE"):
                    host.target.apply(host.frozen["catalog"][c.OPS], object())
                host.ledger.close()
                with self.assertRaisesRegex(ValueError, "PATH_OCCUPIED"):
                    Controller(SOURCE, owner_id=host.owner_id)
                report = oracle.inspect(host.owner_id)
                self.assertEqual(host.ledger.path.read_bytes(), raw)
                self.assertEqual(report["unsettled"][c.OPS]["outcome"], expected)
                self.assertEqual(report["verified_business_transactions"], 1)
                self.assertEqual(report["remaining"], c.ZERO)
                emit(stage, owner=host.owner_id, execution=result["execution"], reconciliation=expected,
                     phase=report["phase"], durable_latch=report["latched"],
                     verified_transactions=1, observed_transactions=1 + int(expected == "COMMITTED"),
                     wal_sha256=report["wal_sha256"])

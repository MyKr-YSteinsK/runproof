"""Direct Host controls with actual fresh-owner SQLite and fixture application bytes."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from threading import Barrier
import unittest
from unittest.mock import patch
from uuid import uuid4

from ci.test_rpf107_contracts import PACKAGE, model_message
from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner, pge_r106_oracle as db_oracle
from runtime.runproof_runtime.effectwitness import pge_r107_contracts as c, pge_r107_model_loopback as model
from runtime.runproof_runtime.effectwitness.pge_r106_controller import Controller
from runtime.runproof_runtime.effectwitness.pge_r107_host import Host, Journal
from runtime.runproof_runtime.effectwitness.pge_r107_session import ROOT, prepare
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, sync_dir

LOCAL = os.environ.get("RPF107_LOCAL_SQLITE") == "1"
SOURCE = os.environ.get("RPF107_SOURCE_SHA", c.BASE)


@contextmanager
def fixture(policy="SCRIPTED_OPS", change=None):
    prepare()
    owner = uuid4().hex
    folder = ROOT / owner
    folder.mkdir()
    sync_dir(ROOT)
    with Controller(SOURCE) as controller:
        offered = controller.proposal(inner.SEED)
        result = controller.apply(offered, controller.evaluate(offered))
        feedback = c.project(controller.frozen, controller.ledger.snapshot(), result["oracle"])
        frozen = c.freeze(SOURCE, uuid4().hex, owner, policy, controller.frozen, feedback, PACKAGE)
        if change is not None:
            change(frozen)
        journal = Journal(folder / "bridge.jsonl")
        try:
            yield controller, Host(controller, frozen, journal)
        finally:
            journal.close()


def first(host):
    return host.handle(model.MODEL_PATH, canonical(model_message(host.frozen["feedback"])))


def offer(host):
    return c.tool_request(host.frozen["tool_call_id"], c.SELECTIONS[host.frozen["policy"]])


@unittest.skipUnless(LOCAL, "Requires admitted fresh-owner SQLite fixtures")
class HostTests(unittest.TestCase):
    def test_distinct_sqlite_targets_and_post_unknown_denial(self):
        for policy in c.POLICIES:
            with self.subTest(policy=policy), fixture(policy) as (controller, host):
                self.assertEqual(first(host), (200, model.response(host.frozen)))
                call = offer(host)
                self.assertEqual(host.handle(model.TOOL_PATH, canonical(call)), (200, c.UNKNOWN))
                before = controller.ledger.path.read_bytes()
                later = model_message(host.frozen["feedback"], call, c.UNKNOWN)
                self.assertEqual(host.handle(model.MODEL_PATH, canonical(later)), (409, model.denial()))
                cross = call | {"arguments": {"candidate_id": inner.OPS if policy == "FIXED_ORDER" else inner.ORDER}}
                self.assertEqual(host.handle(model.TOOL_PATH, canonical(cross))[0], 409)
                self.assertEqual(controller.ledger.path.read_bytes(), before)
                report = db_oracle.inspect(controller.owner_id)
                self.assertEqual(report["claimed"], [inner.SEED, c.POLICIES[policy]])
                verdict = report["verified"][c.POLICIES[policy]]
                observed = controller.reconcile(verdict["binding"])
                self.assertEqual(observed["outcome"], "COMMITTED")
                state = observed["authority"]["snapshot"]
                if policy == "FIXED_ORDER":
                    self.assertEqual(state["order"]["refunded_minor"], 2500)
                else:
                    self.assertEqual(state["config"]["release"], "release-v2")
                self.assertEqual(len(state["receipts"]), 1)
                self.assertEqual(report["post_unknown_effect_events"], 0)
                self.assertEqual(sum(row["kind"] == "MODEL_RESERVE" for row in host.journal.events), 1)

    def test_concurrent_callback_is_consumed_once(self):
        with fixture() as (controller, host):
            self.assertEqual(first(host)[0], 200)
            raw = canonical(offer(host))
            barrier = Barrier(2)

            def compete(_):
                barrier.wait(timeout=5)
                return host.handle(model.TOOL_PATH, raw)[0]

            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertCountEqual(pool.map(compete, range(2)), [200, 409])
            report = db_oracle.inspect(controller.owner_id)
            self.assertEqual(report["verified_business_transactions"], 2)
            self.assertEqual(report["remaining"], inner.ZERO)
            self.assertEqual(sum(row["kind"] == "HOST_DECISION" for row in host.journal.events), 1)

    def test_stop_consumes_no_write_or_continuation_budget(self):
        with fixture("STOP_CONTROL") as (controller, host):
            self.assertEqual(first(host)[0], 200)
            self.assertEqual(host.handle(model.TOOL_PATH, canonical(offer(host))), (200, c.STOPPED))
            report = db_oracle.inspect(controller.owner_id)
            self.assertEqual(report["claimed"], [inner.SEED])
            self.assertEqual(report["remaining"], inner.COST)
            self.assertEqual(first(host)[0], 409)

    def test_old_feedback_wrong_owner_missing_authority_fail_closed(self):
        def stale(frozen):
            frozen["feedback"]["seed"]["feedback_sha256"] = "0" * 64

        def foreign(frozen):
            frozen["inner_scope"]["owner"] = uuid4().hex

        for change in (stale, foreign, None):
            with self.subTest(change=change), fixture(change=change) as (controller, host):
                before = controller.ledger.path.read_bytes()
                if change is None:
                    with patch.object(db_oracle, "readback", side_effect=FileNotFoundError):
                        self.assertEqual(first(host)[0], 400)
                else:
                    self.assertEqual(first(host)[0], 400)
                self.assertFalse(host.model_reserved)
                self.assertEqual(controller.ledger.path.read_bytes(), before)

    def test_intent_and_post_commit_fail_closed_without_new_model_slot(self):
        for stage in ("WRITE_INTENT", "AFTER_SQLITE_COMMIT", "UNKNOWN"):
            with self.subTest(stage=stage), fixture() as (controller, host):
                self.assertEqual(first(host)[0], 200)
                controller.failure = stage
                self.assertEqual(host.handle(model.TOOL_PATH, canonical(offer(host)))[0], 400)
                old = controller.ledger.path.read_bytes()
                self.assertEqual(first(host)[0], 400)
                self.assertEqual(controller.ledger.path.read_bytes(), old)
                report = db_oracle.inspect(controller.owner_id)
                self.assertEqual(report["unsettled"][inner.OPS]["outcome"],
                                 "NOT_COMMITTED" if stage == "WRITE_INTENT" else "COMMITTED")

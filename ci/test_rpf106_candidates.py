"""Frozen candidate admission and real SQLite policy comparison."""
import os
import unittest

from runtime.runproof_runtime.effectwitness import pge_r106_contracts as c, pge_r106_replay as replay
from runtime.runproof_runtime.effectwitness.pge_r106_ledger import initial, view
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical

SOURCE = os.environ.get("RPF106_SOURCE_SHA", "7be3fe057df5ce2e45af81180c8983c9647fc975")
LOCAL_SQLITE = os.environ.get("RPF106_LOCAL_SQLITE") == "1"


class CandidateTests(unittest.TestCase):
    def test_frozen_registry_and_seed_only(self):
        frozen = c.freeze(SOURCE, "1" * 32, "2" * 32, c.source_identity())
        catalog = frozen["catalog"]
        self.assertEqual(set(catalog), {c.SEED, c.ORDER, c.OPS})
        self.assertEqual(frozen["terminal_candidate"], c.STOP)
        for field in ("operation_id", "environment_id", "db_member"):
            self.assertEqual(len({row["execution"][field] for row in catalog.values()}), 3)
        self.assertEqual(len({row["contract_sha256"] for row in catalog.values()}), 3)
        self.assertEqual([catalog[name]["experiment"]["budget"] for name in (c.SEED, c.ORDER, c.OPS)],
                         [c.COST] * 3)
        ready = view(initial(frozen) | {"phase": "READY"})
        for name, status in ((c.SEED, "ACCEPT"), (c.ORDER, "REJECT"), (c.OPS, "REJECT"), (c.STOP, "MUST_STOP")):
            with self.subTest(candidate=name):
                offered = c.proposal(frozen, ready, name, "3" * 32)
                self.assertEqual(c.gate(frozen, ready, offered)["status"], status)
        for name in (c.ORDER, c.OPS):
            self.assertEqual(c.faults(catalog[name]),
                             {"planned": True, "triggered": False, "observed": False, "agent_exposed": False})
        with self.assertRaisesRegex(ValueError, "FAULT_ORDER"):
            c.faults(catalog[c.OPS], observed=True)

    @unittest.skipUnless(LOCAL_SQLITE, "Requires authorized task-owned SQLite root")
    def test_real_policy_comparison_cannot_degenerate(self):
        result = replay.compare(SOURCE)
        fixture, baseline = result["runs"]
        self.assertEqual(fixture["visible"], baseline["visible"])
        self.assertEqual(fixture["visible"]["remaining"], c.COST)
        self.assertEqual((fixture["selected"], baseline["selected"]), (c.OPS, c.ORDER))
        for key in ("owner", "run_id"):
            self.assertNotEqual(fixture["readback"]["scope"][key], baseline["readback"]["scope"][key])
        for run, domain, member in ((fixture, "ops", "fault-ops.sqlite"),
                                    (baseline, "order", "fault-order.sqlite")):
            with self.subTest(domain=domain):
                self.assertEqual(set(run["decisions"]), {c.ORDER, c.OPS})
                self.assertEqual({d["status"] for d in run["decisions"].values()}, {"ACCEPT"})
                self.assertEqual({d["feedback_sha256"] for d in run["decisions"].values()},
                                 {run["seed"]["feedback_sha256"]})
                self.assertEqual(run["seed_snapshot"]["order"]["status"], "REFUNDED")
                self.assertEqual(len(run["seed_snapshot"]["receipts"]), 1)
                self.assertEqual(len(run["continuation_snapshot"]["receipts"]), 1)
                selected = run["continuation"]["oracle"]
                self.assertEqual((selected["binding"]["domain"], selected["binding"]["db_member"]), (domain, member))
                self.assertEqual(selected["fault"],
                                 {"planned": True, "triggered": True, "observed": True, "agent_exposed": False})
                self.assertEqual(run["readback"]["claimed"], [c.SEED, run["selected"]])
                self.assertEqual(run["readback"]["remaining"], c.ZERO)
                self.assertEqual(run["readback"]["verified_business_transactions"], 2)
                self.assertEqual(run["readback"]["post_unknown_effect_events"], 0)
                self.assertTrue(run["readback"]["latched"])
                self.assertEqual(set(run["later_admission"].values()), {"MUST_STOP"})
                self.assertEqual(run["reconciliation"], "COMMITTED")
        self.assertEqual(fixture["continuation_snapshot"]["config"]["release"], "release-v2")
        self.assertEqual(fixture["continuation_snapshot"]["config"]["effect_count"], 1)
        self.assertEqual(baseline["continuation_snapshot"]["order"]["refunded_minor"], 2500)
        self.assertEqual(baseline["continuation_snapshot"]["order"]["status"], "REFUNDED")
        if os.environ.get("RPF106_REPORT") == "1":
            print("RPF106_COMPARISON " + canonical(result).decode(), flush=True)

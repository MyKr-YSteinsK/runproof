"""Verify independent fixture witnesses and reanchored semantic negatives."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from ci.test_rpf108_provider_boundary import SOURCE, SQLITE
from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner
from runtime.runproof_runtime.effectwitness import pge_r108_contracts as c, pge_r108_verify as verifier
from runtime.runproof_runtime.effectwitness.pge_r107_host import application
from runtime.runproof_runtime.effectwitness.pge_r108_replay import run_case
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, sha, strict


def rechain(rows):
    tip = "0" * 64
    lines = []
    for i, row in enumerate(rows, 1):
        core = {"revision": i, "previous": tip, "kind": row["kind"], "body": row["body"]}
        tip = inner.digest(core)
        lines.append(canonical(core | {"sha256": tip}) + b"\n")
    return application(b"".join(lines))


@unittest.skipUnless(SQLITE, "Requires authorized RPF-108 fixture root")
class CapsuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = [run_case(SOURCE, choice) for choice in c.CHOICES]
        cls.results.append(run_case(SOURCE, inner.ORDER, "FIXED_ORDER_B0"))

    def test_separate_owners_and_no_disk_dependency(self):
        with patch("sqlite3.connect", side_effect=AssertionError("Verifier must not connect")):
            results = [verifier.verify(raw, SOURCE, sha(raw)) for _, raw, _ in self.results]
        self.assertEqual([r["choice"] for r in results], [*c.CHOICES, inner.ORDER])
        self.assertEqual(len({r["scope"]["owner"] for r in results}), 4)
        self.assertEqual([r["business_transactions"] for r in results], [2, 2, 1, 2])
        self.assertEqual({r["post_terminal_reservations"] for r in results}, {0})
        projections = []
        for _, raw, _ in self.results:
            log = verifier.bytes_for(strict(raw)["presend_wal"], verifier.MAX_PRESEND)
            feedback = verifier.presend_rows(log)[0]["body"]["contract"]["feedback"]
            projections.append(feedback | {"seed": {k: v for k, v in feedback["seed"].items()
                                                     if k != "feedback_sha256"}})
        self.assertTrue(all(row == projections[0] for row in projections))

    def test_source_receipt_missing_member_and_issuer(self):
        _, raw, _ = self.results[0]
        row = strict(raw)
        foreign = strict(self.results[1][1])
        with self.assertRaisesRegex(ValueError, "BUSINESS_SCOPE"):
            verifier.verify(raw, "e" * 40, sha(raw))
        for bad in (row | {"issuer": "INDEPENDENT"}, row | {"physical": {"provider_usage": 1}},
                    row | {"authority": foreign["authority"]}):
            mutated = canonical(bad)
            with self.assertRaises(ValueError):
                verifier.verify(mutated, SOURCE, sha(mutated))
        partial = canonical({key: value for key, value in row.items() if key != "authority"})
        self.assertEqual(verifier.verify(partial, SOURCE, sha(partial)),
                         {"status": "UNAVAILABLE", "missing": ["authority"]})

    def test_rechained_events_must_still_match_semantics(self):
        row = strict(self.results[0][1])
        events = verifier.presend_rows(verifier.bytes_for(row["presend_wal"], verifier.MAX_PRESEND))
        changed = deepcopy(events)
        response = strict(verifier.bytes_for(changed[5]["body"]["application"], c.LIMIT))
        response["simulated_request_id"] = "sim-altered"
        changed[5]["body"]["application"] = application(canonical(response))
        wrong_latch = deepcopy(events)
        wrong_latch[-1]["body"]["reason"] = "NOT_ADMITTED"
        bad_feedback = deepcopy(events)
        bad_feedback[0]["body"]["contract"]["seed_revision"] += 1
        for attack in (changed, wrong_latch, bad_feedback, events[:2] + events[3:],
                       events[:7] + [events[8], events[7], events[9]]):
            raw = canonical(row | {"presend_wal": rechain(attack)})
            with self.assertRaises(ValueError):
                verifier.verify(raw, SOURCE, sha(raw))

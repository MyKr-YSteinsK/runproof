"""Independent Phase A witness replay and semantic tampering controls."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from ci.test_rpf110_presend import LOCAL, SOURCE
from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner
from runtime.runproof_runtime.effectwitness import pge_r110_contracts as c, pge_r110_verify as v
from runtime.runproof_runtime.effectwitness.pge_r107_host import application
from runtime.runproof_runtime.effectwitness.pge_r108_verify import bytes_for, presend_rows
from runtime.runproof_runtime.effectwitness.pge_r110_session import Session
from runtime.runproof_runtime.effectwitness.pge_r110_witness import build
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, sha, strict


def rechain(events):
    tip = "0" * 64
    raw = []
    for i, event in enumerate(events, 1):
        core = {"revision": i, "previous": tip, "kind": event["kind"], "body": event["body"]}
        tip = inner.digest(core)
        raw.append(canonical({**core, "sha256": tip}) + b"\n")
    return application(b"".join(raw))


@unittest.skipUnless(LOCAL, "Requires admitted RPF-110 fixture owner")
class WitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = []
        for strategy, choice in [("FIXTURE_ONLY", name) for name in c.CHOICES] + [("FIXED_ORDER_B0", inner.ORDER)]:
            with Session(SOURCE, strategy) as session:
                session.run(choice)
                raw, _ = build(session)
                cls.samples.append(raw)

    def test_verify_two_domains_stop_and_fixed_order_without_sqlite(self):
        with patch("sqlite3.connect", side_effect=AssertionError("Verifier accessed DB")):
            observed = [v.verify(raw, SOURCE, sha(raw)) for raw in self.samples]
        self.assertEqual(len({item["scope"]["owner"] for item in observed}), 4)
        rows = [item["demo_projection"] for item in observed]
        self.assertEqual([row["candidate_id"] for row in rows], [*c.CHOICES, inner.ORDER])
        self.assertEqual([row["business_transactions"] for row in rows], [2, 2, 1, 2])
        self.assertEqual([row["effect"] for row in rows], [
            {"revision": 1, "receipt_count": 1, "refunded_minor": 2500, "status": "REFUNDED"},
            {"revision": 1, "receipt_count": 1, "release": "release-v2"}, None,
            {"revision": 1, "receipt_count": 1, "refunded_minor": 2500, "status": "REFUNDED"}])
        self.assertTrue(all(row["remaining_before_choice"] == rows[0]["remaining_before_choice"]
                            and row["candidates"] == rows[0]["candidates"] for row in rows))

    def test_scope_tampering_and_missing_authority(self):
        raw = self.samples[0]
        row = strict(raw)
        other = strict(self.samples[1])
        with self.assertRaisesRegex(ValueError, "BUNDLE_ANCHOR"):
            v.verify(raw + b" ", SOURCE, sha(raw))
        with self.assertRaisesRegex(ValueError, "BUSINESS_SCOPE"):
            v.verify(raw, "e" * 40, sha(raw))
        for bad in (row | {"issuer": "INDEPENDENT"}, row | {"provider": row["provider"] | {"usage": 0}},
                    row | {"kind": "REAL_PROVIDER"}, row | {"authority": other["authority"]},
                    row | {"business_wal": other["business_wal"]}, row | {"strategy": "FIXED_ORDER_B0"}):
            altered = canonical(bad)
            with self.assertRaises(ValueError):
                v.verify(altered, SOURCE, sha(altered))
        del row["authority"]
        partial = canonical(row)
        self.assertEqual(v.verify(partial, SOURCE, sha(partial)),
                         {"status": "UNAVAILABLE", "missing": ["authority"]})

    def test_rechained_ticket_response_feedback_and_unknown_denials(self):
        row = strict(self.samples[0])
        trace = presend_rows(bytes_for(row["presend_wal"], v.MAX_TRACE))
        stale = deepcopy(trace)
        stale[0]["body"]["feedback"]["seed"]["feedback_sha256"] = "0" * 64
        wrong_req = deepcopy(trace)
        wrong_req[5]["body"]["request_id"] = "fixture-request-foreign"
        wrong_call = deepcopy(trace)
        wrong_call[6]["body"]["selection"]["tool_call_id"] = "foreign"
        wrong_denial = deepcopy(trace)
        wrong_denial[-1]["body"]["phase"] = "READY"
        wrong_order = [trace[0], trace[1], trace[3], trace[2], *trace[4:]]
        missing_reserve = trace[:2] + trace[3:]
        after_unknown = trace[:-1] + [trace[2], trace[-1]]
        for altered in (stale, wrong_req, wrong_call, wrong_denial, wrong_order, missing_reserve, after_unknown):
            raw = canonical(row | {"presend_wal": rechain(altered)})
            with self.assertRaises(ValueError):
                v.verify(raw, SOURCE, sha(raw))

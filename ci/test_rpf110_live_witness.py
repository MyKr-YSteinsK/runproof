"""Independent replay of real SQLite and loopback, with redacted capsule controls."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from ci.test_rpf110_live_transport import LOCAL, SOURCE, stub
from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner
from runtime.runproof_runtime.effectwitness import pge_r110_live_contracts as c, pge_r110_live_verify as verify
from runtime.runproof_runtime.effectwitness.pge_r107_host import application
from runtime.runproof_runtime.effectwitness.pge_r108_verify import bytes_for, presend_rows
from runtime.runproof_runtime.effectwitness.pge_r110_live_session import Session
from runtime.runproof_runtime.effectwitness.pge_r110_live_witness import build, comparison
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, sha, strict


def rechain(events):
    previous = "0" * 64
    raw = []
    for index, row in enumerate(events, 1):
        core = {"revision": index, "kind": row["kind"], "body": row["body"], "previous": previous}
        previous = inner.digest(core)
        raw.append(canonical(core | {"sha256": previous}) + b"\n")
    return application(b"".join(raw))


@unittest.skipUnless(LOCAL, "Requires admitted RPF-110 fresh SQLite and loopback")
class LiveWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = []
        for choice in c.CHOICES:
            with Session(SOURCE, c.STUB) as session, stub(choice) as (port, seen):
                assert session.run(port=port) == choice and len(seen) == 1
                cls.cases.append(build(session))
        with Session(SOURCE, c.B0) as session:
            session.run()
            cls.cases.append(build(session))

    def test_replay_domains_stop_and_baseline_without_sqlite(self):
        with patch("sqlite3.connect", side_effect=AssertionError("Verifier accessed DB")):
            rows = [verify.verify(raw, SOURCE, sha(raw)) for raw, _ in self.cases]
        self.assertEqual([row["choice"] for row in rows], [*c.CHOICES, inner.ORDER])
        self.assertEqual([row["business_transactions"] for row in rows], [2, 2, 1, 2])
        self.assertEqual(len({row["scope"]["owner"] for row in rows}), 4)
        self.assertTrue(all(row["provider_requests"] == row["post_terminal_send_entries"] ==
                            row["post_terminal_reservations"] == row["post_terminal_business_writes"] == 0
                            and row["provider_usage"] == "NOT_RUN" for row in rows))
        raw = comparison(SOURCE, self.cases[1], self.cases[3])
        self.assertEqual(verify.verify_comparison(raw, SOURCE, sha(raw))["comparison"], "LOCAL_STUB_CONTROL")
        bad = strict(raw)
        bad["projection"]["baseline"]["comparable"]["continuations"] = 2
        altered = canonical(bad)
        with self.assertRaisesRegex(ValueError, "COMPARISON_PROJECTION"):
            verify.verify_comparison(altered, SOURCE, sha(altered))

    def test_reanchored_semantic_tampering_and_missing_material(self):
        raw = self.cases[0][0]
        row = strict(raw)
        other = strict(self.cases[1][0])
        controls = (row | {"authority": other["authority"]}, row | {"issuer": "THIRD_PARTY"},
                    row | {"kind": c.NATIVE}, row | {"business_wal": other["business_wal"]},
                    row | {"stub_response": None}, row | {"request": application(b"{}")})
        for changed in controls:
            altered = canonical(changed)
            with self.assertRaises((ValueError, TypeError, KeyError)):
                verify.verify(altered, SOURCE, sha(altered))
        with self.assertRaisesRegex(ValueError, "BUSINESS_SCOPE"):
            verify.verify(raw, "0" * 40, sha(raw))
        partial = canonical({key: value for key, value in row.items() if key != "authority"})
        self.assertEqual(verify.verify(partial, SOURCE, sha(partial)),
                         {"status": "UNAVAILABLE", "missing": ["authority"]})
        rows = presend_rows(bytes_for(row["presend_wal"], verify.TRACE_LIMIT))
        attacks = []
        for index, key, value in ((0, "seed_tip", "0"*64), (4, "entered_ns", 0), (5, "tls_verified", True),
                                  (6, "tool_call_id", "foreign"), (6, "response_id", "foreign"),
                                  (6, "usage", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}),
                                  (9, "phase", "READY")):
            changed = deepcopy(rows)
            changed[index]["body"][key] = value
            attacks.append(changed)
        attacks.extend(([rows[0], rows[1], rows[3], rows[2], *rows[4:]], rows[:2] + rows[3:],
                        rows[:-1] + [rows[2], rows[-1]]))
        for attack in attacks:
            altered = canonical(row | {"presend_wal": rechain(attack)})
            with self.assertRaises(ValueError):
                verify.verify(altered, SOURCE, sha(altered))

"""Frozen run, provider and cost admission controls."""
from datetime import datetime, timedelta, timezone
import unittest

from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner
from runtime.runproof_runtime.effectwitness import pge_r110_live_contracts as c
from runtime.runproof_runtime.effectwitness.pge_r106_ledger import initial, view
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import strict


def budget(now):
    stamp = lambda value: value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"schema": "rpf110-live-budget-v1", "source_git_sha": c.BASE, "github_run_id": "123",
            "provider": "DeepSeek", "model": c.MODEL, "host": c.HOST, "path": c.PATH, "max_requests": 1,
            "max_input_bytes": c.BODY_CAP, "max_input_tokens": 5000, "max_output_tokens": 128,
            "timeout_seconds": 15, "currency": "CNY", "max_cost_microunits": 100000,
            "input_rate_microunits_per_million": 100000, "output_rate_microunits_per_million": 500000,
            "pricing_url": c.PRICING, "pricing_checked_utc": stamp(now - timedelta(minutes=1)),
            "expires_utc": stamp(now + timedelta(hours=1))}


class LiveContractsTests(unittest.TestCase):
    def test_fixed_provider_budget_and_expiry(self):
        now = datetime.now(timezone.utc)
        good = budget(now)
        self.assertEqual(c.validate_budget(good, c.BASE, "123", now=now), good)
        for delta in ({"host": "localhost"}, {"model": "other"}, {"max_requests": 2}, {"max_output_tokens": 129},
                      {"max_cost_microunits": 1}, {"source_git_sha": "0"*40}, {"github_run_id": "124"},
                      {"input_rate_microunits_per_million": True}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                c.validate_budget(good | delta, c.BASE, "123", now=now)
        with self.assertRaisesRegex(ValueError, "BUDGET_EXPIRY"):
            c.validate_budget(good, c.BASE, "123", now=now + timedelta(hours=2))

    def test_bound_seed_and_same_request_as_baseline(self):
        frozen = inner.freeze(c.BASE, "1"*32, "2"*32, inner.source_identity())
        seed = {"binding": inner.binding(frozen["catalog"][inner.SEED]), "outcome": inner.SUCCESS}
        state = initial(frozen) | {"phase": "VERIFIED", "feedback_sha256": inner.digest(seed),
                                   "remaining": inner.COST}
        seed_view = view(state)
        stub = c.freeze(frozen, seed_view, seed, c.STUB)
        b0 = c.freeze(frozen, seed_view, seed, c.B0)
        self.assertEqual(c.request(stub), c.request(b0))
        request = strict(c.request(stub))
        self.assertEqual(request["model"], c.MODEL)
        self.assertIs(request["stream"], False)
        self.assertEqual(request["max_tokens"], 128)
        self.assertEqual(request["thinking"], {"type": "disabled"})
        for changed in (seed_view | {"latched": True}, seed_view | {"feedback_sha256": "0"*64},
                        seed_view | {"run_sha256": "0"*64}):
            with self.assertRaises(ValueError):
                c.freeze(frozen, changed, seed, c.STUB)
        with self.assertRaisesRegex(ValueError, "REQUEST_BYTES"):
            c.request(stub | {"request_sha256": "0"*64})

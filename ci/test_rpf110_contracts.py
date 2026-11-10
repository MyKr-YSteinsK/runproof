"""Pure contract and minimal feedback request controls."""
import unittest

from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner
from runtime.runproof_runtime.effectwitness import pge_r110_contracts as c
from runtime.runproof_runtime.effectwitness.pge_r106_ledger import initial, view
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import strict


class ContractTests(unittest.TestCase):
    def test_exact_projection_and_equivalent_baseline_input(self):
        frozen = inner.freeze(c.BASE, "1"*32, "2"*32, inner.source_identity())
        seed = {"binding": inner.binding(frozen["catalog"][inner.SEED]), "outcome": inner.SUCCESS}
        state = initial(frozen) | {"phase": "VERIFIED", "feedback_sha256": inner.digest(seed),
                                   "remaining": inner.COST}
        verified = view(state)
        model, b0 = (c.freeze(frozen, verified, seed, kind) for kind in ("FIXTURE_ONLY", "FIXED_ORDER_B0"))
        self.assertEqual(c.request(model), c.request(b0))
        self.assertEqual((model["request_budget"], b0["request_budget"]), (1, 0))
        data = strict(c.request(model))
        self.assertEqual(len(data["tools"]), 1)
        schema = data["tools"][0]["function"]["parameters"]
        self.assertEqual(schema["properties"]["candidate_id"]["enum"], list(c.CHOICES))
        self.assertFalse(schema["additionalProperties"])
        content = data["messages"][0]["content"].encode()
        self.assertNotIn(b"owner", content)
        self.assertNotIn(b"contract", content.lower().replace(b"contract_satisfied_in_run", b""))
        for bad in (verified | {"feedback_sha256": None}, verified | {"latched": True},
                    verified | {"phase": "READY"}, verified | {"run_sha256": "0"*64}):
            with self.assertRaises(ValueError):
                c.freeze(frozen, bad, seed, "FIXTURE_ONLY")

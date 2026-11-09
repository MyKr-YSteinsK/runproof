"""Provider-0 controls for candidate, authority and budget admission."""
from copy import deepcopy
import unittest

from ci import rpf105_verify_archive as archive
from runtime.runproof_runtime.effectwitness import pge_r105_contracts as c
from runtime.runproof_runtime.effectwitness.pge_r105_gate import admit
from runtime.runproof_runtime.effectwitness.pge_r105_replay import fixture_inputs, proposal, replay


class ExplorerAdmissionTests(unittest.TestCase):
    def inputs(self, scenario="VERIFIED_NORMAL", name=c.UNKNOWN):
        catalog, ledger, feedback = fixture_inputs(scenario)
        return proposal(catalog, ledger, name, "5" * 32), catalog, feedback, ledger

    def test_seed_only_and_no_synthetic_effect_claim(self):
        args = self.inputs("INITIAL_FROZEN_SEED", c.NORMAL)
        result = admit(*args)
        self.assertEqual((result["status"], result["reason"], result["next_permission"], result["effect_execution"]),
                         ("ACCEPT", "INITIAL_FROZEN_SEED", "FIXTURE_ONLY", "NOT_RUN"))
        self.assertEqual(result["requested_debit"], {"cases": 1, "writes": 2, "forwards": 3})
        self.assertIsNone(result["feedback_sha256"])
        self.assertEqual(admit(*self.inputs("INITIAL_FROZEN_SEED"))["reason"], "FROZEN_SEED_REQUIRED")
        _, _, feedback, _ = self.inputs()
        self.assertEqual(admit(args[0], args[1], feedback, args[3])["reason"], "UNEXPECTED_SEED_FEEDBACK")

    def test_continuation_needs_the_pinned_feedback(self):
        p, catalog, feedback, ledger = self.inputs()
        snapshot = deepcopy((p, catalog, feedback, ledger))
        accepted = admit(p, catalog, feedback, ledger)
        self.assertEqual(accepted["status"], "ACCEPT")
        self.assertEqual(accepted["feedback_sha256"], ledger["expected_feedback_sha256"])
        self.assertEqual(accepted["decision_sha256"], c.digest({k: v for k, v in accepted.items()
                                                                 if k != "decision_sha256"}))
        self.assertEqual(admit(p, catalog, None, ledger)["status"], "MUST_STOP")
        unpinned = {**feedback, "evidence_sha256": "a" * 64}
        self.assertEqual(admit(p, catalog, unpinned, ledger)["reason"], "UNANCHORED_FEEDBACK")
        self.assertEqual((p, catalog, feedback, ledger), snapshot)
        self.assertEqual(admit(p, catalog, feedback, ledger), accepted)

    def test_malformed_or_overreaching_proposals(self):
        p, catalog, feedback, ledger = self.inputs()
        for key, value in (("url", "https://example.invalid"), ("path", "/tmp/test"),
                           ("tool", "unsafe"), ("command", "fictional"), ("writes", 1),
                           ("domain", "ops"), ("role", "EXPLORER"), ("ticket", "old-ticket"),
                           ("owner", ledger["scope"]["owner"]), ("token", "fictional")):
            answer = admit({**p, key: value}, catalog, feedback, ledger)
            self.assertEqual((answer["status"], answer["reason"], answer["requested_debit"]),
                             ("REJECT", "PROPOSAL_SCHEMA", c.ZERO))
        self.assertEqual(admit({**p, "candidate_sha256": "0" * 64}, catalog, feedback, ledger)["reason"],
                         "CANDIDATE_ANCHOR")
        self.assertEqual(admit({**p, "ledger_sha256": "0" * 64}, catalog, feedback, ledger)["reason"],
                         "STALE_LEDGER")
        self.assertEqual(admit({**p, "candidate_id": "rpf104/OTHER"}, catalog, feedback, ledger)["reason"],
                         "PROPOSAL_SCHEMA")

    def test_feedback_scope_and_freshness_even_if_rehashed(self):
        p, catalog, feedback, ledger = self.inputs()
        changes = [("scope", {**feedback["scope"], k: v}) for k, v in (
            ("owner", "6" * 32), ("run_id", "7" * 32), ("source_git_sha", "8" * 40))]
        changes += [("case", "UNKNOWN"), ("environment_id", "wrong"), ("operation_id", "wrong"),
                    ("authority", "MODEL_ASSERTED"), ("oracle", "UNVERIFIED"), ("ledger_revision", 0),
                    ("effect_contract_sha256", "0" * 64), ("contract_sha256", "0" * 64)]
        for key, value in changes:
            bad = {**feedback, key: value}
            view = {**ledger, "expected_feedback_sha256": c.digest(bad)}
            p = proposal(catalog, view, c.UNKNOWN, "5" * 32)
            self.assertEqual(admit(p, catalog, bad, view)["reason"], "FEEDBACK_SCOPE_OR_PROVENANCE")

    def test_historical_capsule_cannot_bootstrap_current_authority(self):
        saved = archive.verify_archive()
        _, catalog, feedback, ledger = self.inputs()
        historical = {**feedback, "evidence_origin": "HISTORICAL_PUBLIC_PROJECTION",
                      "evidence_sha256": saved["manifest_sha256"],
                      "scope": {"origin": "GITHUB", **{key: saved[key] for key in ("source_git_sha", "run_id", "owner")}}}
        # Even a controller-side hash of a historical reference cannot make it live.
        for bad in (historical, {**historical, "scope": dict(ledger["scope"])}):
            view = {**ledger, "expected_feedback_sha256": c.digest(bad)}
            p = proposal(catalog, view, c.UNKNOWN, "5" * 32)
            self.assertEqual(admit(p, catalog, bad, view)["reason"], "FEEDBACK_SCOPE_OR_PROVENANCE")

    def test_budget_replay_and_forged_catalog(self):
        _, catalog, feedback, ledger = self.inputs()
        for budget in c.LIMIT:
            view = {**ledger, "remaining": {**ledger["remaining"], budget: 0}}
            p = proposal(catalog, view, c.UNKNOWN, "5" * 32)
            self.assertEqual(admit(p, catalog, feedback, view)["reason"], "BUDGET_EXCEEDED")
        self.assertEqual(admit(proposal(catalog, ledger, c.UNKNOWN, "4" * 32), catalog, feedback, ledger)["reason"],
                         "DUPLICATE_PROPOSAL")
        bad = deepcopy(catalog)
        bad[c.UNKNOWN]["cost"]["writes"] = 0
        p = proposal(catalog, ledger, c.UNKNOWN, "5" * 32)
        self.assertEqual(admit(p, bad, feedback, ledger)["status"], "INCONCLUSIVE")
        view = {**ledger, "remaining": {**ledger["remaining"], "writes": True}}
        self.assertEqual(admit(p, catalog, feedback, view)["reason"], "LEDGER_NOT_TRUSTED")
        unsettled = {**ledger, "consumed_proposals": [*ledger["consumed_proposals"], "6" * 32], "revision": 2}
        p = proposal(catalog, unsettled, c.UNKNOWN, "5" * 32)
        self.assertEqual(admit(p, catalog, feedback, unsettled)["reason"], "PRIOR_ADMISSION_UNSETTLED")

    def test_latch_and_uncertain_reconciliation_block_every_effect(self):
        _, catalog, feedback, ledger = self.inputs("UNKNOWN_LATCHED")
        for view in (ledger, {**ledger, "latched": False, "reconciliation": "COMMITTED"},
                     {**ledger, "latched": False, "reconciliation": "UNAVAILABLE"}):
            for name in catalog:
                p = proposal(catalog, view, name, "5" * 32)
                result = admit(p, catalog, feedback, view)
                self.assertEqual((result["status"], result["requested_debit"], result["next_permission"]),
                                 ("MUST_STOP", c.ZERO, "NONE"))
        _, catalog, feedback, ledger = self.inputs()
        for outcome in ("UNKNOWN_OUTCOME", "INCONCLUSIVE"):
            bad = {**feedback, "outcome": outcome}
            view = {**ledger, "expected_feedback_sha256": c.digest(bad)}
            p = proposal(catalog, view, c.UNKNOWN, "5" * 32)
            self.assertEqual(admit(p, catalog, bad, view)["reason"], "FEEDBACK_EFFECT_UNCONFIRMED")

    def test_same_proposal_feedback_delta_and_fixed_order(self):
        result = replay()
        self.assertEqual((result["evidence_origin"], result["explorer_kind"], result["actual_tool_calls"],
                          result["physical_runs"], result["real_explorer"]), (c.FIXTURE, "FIXTURE", 0, 0, "NOT_RUN"))
        traces = result["traces"]
        self.assertEqual([row["fixture"]["admission"]["status"] for row in traces],
                         ["ACCEPT", "MUST_STOP", "ACCEPT", "MUST_STOP"])
        for strategy in ("fixture", "fixed_order"):
            self.assertEqual(traces[1][strategy]["proposal"], traces[2][strategy]["proposal"])
        self.assertEqual(traces[1]["remaining_budget"], traces[2]["remaining_budget"])
        self.assertEqual(traces[3]["fixed_order"]["admission"]["status"], "MUST_STOP")
        self.assertTrue(all(row["actual_execution"] == "NOT_RUN" for row in traces))

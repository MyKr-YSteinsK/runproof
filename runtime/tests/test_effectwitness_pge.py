"""RPF-42 fixtures: MOCK_POLICY_ONLY; no real Provider calls or paid sessions."""
from __future__ import annotations

import copy
import dataclasses
import json
import sqlite3
import unittest
import uuid
import io
from contextlib import redirect_stdout
from contextlib import closing
from unittest.mock import patch

from runtime.runproof_runtime.models import RuntimeFailure
from runtime.runproof_runtime.effectwitness.contracts import (FrozenContracts, canonical, digest,
                                                            make_contracts, owned_path)
from runtime.runproof_runtime.effectwitness.exploration import (ExplorationSession, Ledger,
    SessionBudget, project_feedback, run_session, run_trial)
from runtime.runproof_runtime.effectwitness.pge_contracts import PGE_ROOT, LIMITS, SessionPlan
from runtime.runproof_runtime.effectwitness.pge_provider import initial_messages, parse_choice, tool_definitions
from runtime.runproof_runtime.effectwitness.orders import AuthorityReader, OrderSandbox
from runtime.runproof_runtime.effectwitness import provider


def setUpModule():
    from runtime.tests.test_effectwitness_ops import legacy_test_scope
    global _task_scope
    _task_scope = legacy_test_scope(globals())


def tearDownModule():
    _task_scope.close()


class PgeContractTests(unittest.TestCase):
    def test_strict_frozen_catalog_budget_baseline_and_versions(self):
        plan = SessionPlan.create()
        plan.validate()
        for key, value in (("baseline_order", ["response-lost", "normal"]), ("limits", {}),
                           ("catalog", []), ("schema_version", "v999"), ("unknown", True)):
            changed = plan.document
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeFailure):
                SessionPlan.freeze(changed)
        modified = plan.document
        modified["catalog"][0]["fault"] = "reconcile-unavailable"
        with self.assertRaises(RuntimeFailure):
            SessionPlan.freeze(modified)
        old = make_contracts("compat")
        self.assertEqual(old.experiment["schema_version"], "rpf-experiment-v1")
        wrong = old.experiment
        wrong["owner"] = "rpf-42"
        with self.assertRaises(RuntimeFailure):
            FrozenContracts.freeze(old.execution, old.effect, wrong)
        new = plan.trial_contracts("PGE", "normal")
        self.assertEqual(new.experiment["schema_version"], "rpf-experiment-v2")
        plan.validate_trial(new, "PGE", "normal")
        with self.assertRaises(RuntimeFailure):
            plan.validate_trial(new, "B0", "normal")
        with self.assertRaises(RuntimeFailure):
            owned_path(PGE_ROOT / "file")  # v1 owner cannot silently write v2 paths

    def test_provider_sees_all_choices_no_future_feedback_or_baseline(self):
        plan = SessionPlan.create()
        visible = json.loads(initial_messages(plan)[1]["content"])
        self.assertEqual(visible["observed_feedback"], [])
        self.assertNotIn("baseline_order", visible)
        self.assertNotIn("outcome", json.dumps(visible))
        enum = tool_definitions(plan)[0]["function"]["parameters"]["properties"]["candidate_id"]["enum"]
        self.assertEqual(len(enum), 3)
        for candidate_id in enum:
            for index in range(2):
                data = self.response(candidate_id, "call-" + str(index))
                self.assertEqual(json.loads(parse_choice(data, plan, set())["function"]["arguments"]),
                                 {"candidate_id": candidate_id})

    @staticmethod
    def response(candidate="normal", call_id="call-test"):
        return {"id": "response-" + call_id, "model": "deepseek-flash", "usage": {
            "prompt_tokens": 300, "completion_tokens": 40, "total_tokens": 340},
            "choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
                {"id": call_id, "type": "function", "function": {"name": "select_experiment",
                 "arguments": json.dumps({"candidate_id": candidate})}}]}}]}

    def test_invalid_candidate_tool_args_duplicate_id_and_envelope_rejected(self):
        plan = SessionPlan.create()
        variants = [self.response("reconcile-unavailable"), self.response("../path")]
        tool = self.response()
        tool["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = "shell"
        variants.append(tool)
        args = self.response()
        args["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"candidate_id":"normal","path":"/"}'
        variants.append(args)
        duplicate = self.response()
        duplicate["choices"][0]["message"]["tool_calls"] *= 2
        variants.append(duplicate)
        for data in variants:
            with self.assertRaises(RuntimeFailure):
                parse_choice(data, plan, set())
        with self.assertRaisesRegex(RuntimeFailure, "CALL_IDENTITY"):
            parse_choice(self.response(), plan, {"call-test"})

    def test_shared_budgets_unknown_usage_and_trial_per_policy_caps(self):
        saves = []
        b = SessionBudget(LIMITS, lambda: saves.append(True))
        b.reserve_trial("PGE")
        b.reserve_trial("PGE")
        with self.assertRaises(RuntimeFailure):
            b.reserve_trial("PGE")
        b.reserve_trial("B0")
        b.reserve_trial("B0")
        self.assertEqual(b.fault_trials, 4)
        b.reserve_request(1000, 128)
        with self.assertRaisesRegex(RuntimeFailure, "USAGE_UNKNOWN"):
            b.reserve_request(1000, 128)
        self.assertIsNone(b.public()["tokens"])
        b.record_usage({"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110})
        for _ in range(3):
            b.reserve_request(1000, 128)
            b.record_usage({"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110})
        with self.assertRaisesRegex(RuntimeFailure, "REQUESTS_EXHAUSTED"):
            b.reserve_request(1000, 128)
        self.assertTrue(saves)
        steps = SessionBudget(LIMITS, lambda: None)
        for _ in range(16): steps.step()
        with self.assertRaisesRegex(RuntimeFailure, "STEPS_EXHAUSTED"):
            steps.step()
        for key, value, code in (("tokens", 1, "TOKENS_EXHAUSTED"),
                                 ("cost_cny", 0.000001, "COST_EXHAUSTED")):
            with self.assertRaisesRegex(RuntimeFailure, code):
                SessionBudget({**LIMITS, key: value}, lambda: None).reserve_request(100, 128)
        timed = SessionBudget(LIMITS, lambda: None)
        timed.started -= 1201
        with self.assertRaisesRegex(RuntimeFailure, "TIME_EXHAUSTED"):
            timed.step()

    def test_exclusive_ledger_corrupt_or_restart_cannot_reopen(self):
        path = PGE_ROOT / ("test-ledger-" + uuid.uuid4().hex + ".json")
        ledger = Ledger(path, {"reserved": True})
        self.addCleanup(path.unlink)
        with self.assertRaises(FileExistsError):
            Ledger(path, {})
        path.write_bytes(b"torn write")
        with self.assertRaises(FileExistsError):
            Ledger(path, {})


class PgeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.session = ExplorationSession(SessionPlan.create())

    def test_three_real_semantics_and_fresh_identity_isolation(self):
        results = []
        for policy, candidate in (("PGE", "normal"), ("PGE", "response-lost"), ("B0", "planned-untriggered")):
            results.append(self.session.execute(policy, candidate)["document"])
        self.assertEqual([r["fault"]["activation"] for r in results], ["NOT_PLANNED", "TRIGGERED", "NOT_TRIGGERED"])
        self.assertTrue(results[1]["fault"]["reconciled"])
        ids = [t["contracts"]["experiment"]["run_id"] for t in self.session.result["trials"]]
        operations = [t["contracts"]["effect"]["operation_id"] for t in self.session.result["trials"]]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(len(set(operations)), 3)
        for trial in self.session.result["trials"]:
            self.assertEqual(len(trial["effect"]["after"]["data"]["receipts"]), 1)
            self.assertEqual(trial["cleanup"]["status"], "RESET_AND_REMOVED")
            self.assertFalse((PGE_ROOT / trial["contracts"]["experiment"]["run_id"]).exists())

    def test_repeated_legal_choice_has_zero_new_information_no_adaptation(self):
        self.session.execute("PGE", "normal")
        second = self.session.execute("PGE", "normal")
        self.assertEqual(second["document"]["information_gain_proxy"], 0)
        result = self.session.finish()
        self.assertFalse(result["research"]["L2"])
        self.assertEqual(result["research"]["H1"], "NOT_PROVEN")
        self.assertEqual(result["stop_reason"], "NO_NEW_INFORMATION")

    def test_wrong_feedback_hash_identity_fault_and_missing_authority_rejected(self):
        self.session.execute("PGE", "normal")
        trial = self.session.result["trials"][0]
        mutations = []
        for path, value in ((("effect", "after", "sha256"), "0" * 64),
                            (("effect", "before", "data", "environment", "owner"), "wrong"),
                            (("effect", "verifier_id"), "llm-judge"),
                            (("fault", "triggered"), True), (("effect", "evidence_gaps"), ["missing"])):
            changed = copy.deepcopy(trial)
            obj = changed
            for key in path[:-1]:
                obj = obj[key]
            obj[path[-1]] = value
            mutations.append(changed)
        for changed in mutations:
            with self.assertRaises(RuntimeFailure):
                project_feedback(self.session.plan, changed, "PGE", "normal", set())
        with self.assertRaises(RuntimeFailure):
            project_feedback(SessionPlan.create(), trial, "PGE", "normal", set())

    def test_mock_policy_demo_and_preregistered_baseline_use_same_driver(self):
        result = run_session()
        self.assertEqual(result["mode"], "MOCK_POLICY_ONLY")
        self.assertFalse(result["research"]["L1"])
        self.assertEqual(result["budget"]["physical_trials"], 4)
        self.assertEqual(result["budget"]["provider_requests"], 0)
        b0 = [t for t in result["trials"] if t["contracts"]["experiment"]["policy"] == "B0"]
        self.assertEqual([t["contracts"]["experiment"]["candidate_id"] for t in b0], result["plan"]["baseline_order"])
        self.assertEqual(len({t["target_driver"] for t in result["trials"]}), 1)
        self.assertFalse(result["comparison"]["cost_equivalent"])

    def test_root_cli_pge_demo_is_free_and_legacy_self_check_compatible(self):
        from runtime.runproof_runtime.effectwitness.__main__ import main
        for flag in ("--pge-demo", "--self-check"):
            output = io.StringIO()
            with patch("sys.argv", ["effectwitness", flag]), redirect_stdout(output), \
                    patch.object(provider.http.client, "HTTPSConnection", side_effect=AssertionError("network forbidden")):
                self.assertEqual(main(), 0)
            result = json.loads(output.getvalue())
            if flag == "--pge-demo":
                self.assertEqual(result["mode"], "MOCK_POLICY_ONLY")
                self.assertEqual(result["budget"]["provider_requests"], 0)
            else:
                self.assertEqual(result["status"], "VALID")

    def test_safe_stop_on_unreconciled_unknown_preserves_database_until_restored(self):
        original = AuthorityReader.reconcile
        with patch.object(AuthorityReader, "reconcile", side_effect=RuntimeFailure("ENVIRONMENT", "AUTHORITY_UNAVAILABLE")):
            with self.assertRaisesRegex(RuntimeFailure, "SAFE_STOP"):
                self.session.execute("PGE", "response-lost")
        self.assertTrue(self.session.halted)
        trial = self.session.result["trials"][0]
        self.assertEqual(trial["effect"]["contract_outcome"], "INCONCLUSIVE")
        self.assertEqual(trial["cleanup"]["status"], "QUARANTINE_REQUIRED")
        path = PGE_ROOT.parents[1] / trial["cleanup"]["path"]
        self.assertTrue((path / "orders.sqlite3").exists())
        # Test fixture recovery: restore authority, confirm one committed receipt, then reset.
        contracts = FrozenContracts.freeze(**trial["contracts"])
        destination = PGE_ROOT / contracts.experiment["run_id"]
        path.rename(destination)
        sandbox = OrderSandbox(contracts, destination)
        reader = AuthorityReader(sandbox.path, contracts)
        self.assertEqual(original(reader, contracts.effect["operation_id"])["status"], "COMMITTED")
        sandbox.cleanup()
        with self.assertRaisesRegex(RuntimeFailure, "SESSION_SAFE_STOP"):
            self.session.execute("PGE", "normal")

    def test_mock_two_provider_envelopes_receive_exact_prior_feedback(self):
        from runtime.runproof_runtime.effectwitness.pge_provider import explore
        bodies = []
        ledger_path = PGE_ROOT / ("test-session-" + uuid.uuid4().hex + ".json")
        self.session = ExplorationSession(SessionPlan.create(), ledger_path=ledger_path)
        self.addCleanup(ledger_path.unlink)
        replies = [PgeContractTests.response("planned-untriggered", "call-first"),
                   PgeContractTests.response("response-lost", "call-second")]

        class Response:
            status = 200
            def getheader(self, name): return None
            def read(self, size): return json.dumps(replies.pop(0)).encode()

        class Connection:
            def __init__(self, *args, **kwargs): pass
            def request(self, method, path, encoded, headers):
                bodies.append(json.loads(encoded))
                durable = json.loads(ledger_path.read_bytes())
                assert durable["budget"]["provider_requests"] == len(bodies)
                assert not durable["budget"]["usage_known"]
                assert durable["budget"]["pending_token_reservation"] > 0
                assert len(durable["provider_requests"]) == len(bodies)
            def getresponse(self): return Response()
            def close(self): pass

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "unit-test-only"}), \
                patch.object(provider.http.client, "HTTPSConnection", Connection):
            explore(self.session)
        feedback = self.session.result["feedback"][0]
        visible = [m for m in bodies[1]["messages"] if m["role"] == "tool"][0]
        self.assertEqual(visible["tool_call_id"], "call-first")
        self.assertEqual(visible["content"].encode(), canonical(feedback["document"]))
        self.assertEqual(digest(json.loads(visible["content"])), feedback["sha256"])
        self.assertEqual(bodies[0]["tools"], bodies[1]["tools"])
        self.assertEqual(self.session.budget.requests, 2)
        self.assertFalse(self.session.finish()["research"]["L2"])  # MOCK_POLICY_ONLY, never live proof


if __name__ == "__main__":
    unittest.main()

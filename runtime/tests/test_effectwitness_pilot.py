"""RPF-41 deterministic controls. No model/network; all fixtures task-owned."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
import unittest
import uuid
from contextlib import closing
from unittest.mock import patch

from runtime.runproof_runtime.models import RuntimeFailure, INITIAL_STATE, TARGET_STATE
from runtime.runproof_runtime.effectwitness.contracts import (
    ROOT, LOCAL_ROOT, HARD_LIMITS, FrozenContracts, digest, make_contracts, owned_path)
from runtime.runproof_runtime.effectwitness.engine import Budget, Orchestrator
from runtime.runproof_runtime.effectwitness.orders import AuthorityReader, OrderAdapter, OrderSandbox
from runtime.runproof_runtime.effectwitness.verifier import OrderEffectVerifier
from runtime.runproof_runtime.effectwitness.__main__ import run
from runtime.runproof_runtime.effectwitness import provider


def setUpModule():
    from runtime.tests.test_effectwitness_ops import legacy_test_scope
    global _task_scope
    _task_scope = legacy_test_scope(globals())


def tearDownModule():
    _task_scope.close()


class PilotTests(unittest.TestCase):
    def setUp(self):
        # Regression owners are redirected by setUpModule into the current task.
        # Production v1 ownership/default paths are not changed by these patches.
        from runtime.runproof_runtime.effectwitness import contracts, orders, __main__ as cli
        for module in (contracts, orders, cli):
            redirect = patch.object(module, "LOCAL_ROOT", ROOT / ".local" / "rpf-42")
            redirect.start()
            self.addCleanup(redirect.stop)
        self.c = make_contracts("test-" + uuid.uuid4().hex)
        self.s = OrderSandbox(self.c)
        self.s.initialize()
        self.addCleanup(self.clean)
        self.r = AuthorityReader(self.s.path, self.c)
        self.a = OrderAdapter(self.s)
        self.budget = Budget(self.c.execution["budgets"])
        self.o = Orchestrator(self.c, self.a, self.r, self.budget)
        self.v = OrderEffectVerifier(self.c, self.r)
        self.args = {k: self.c.effect[k] for k in ("order_id", "operation_id", "amount_minor")}

    def clean(self):
        if self.s.path.exists():
            # Negative test injection must restore ownership, not bypass cleanup.
            with closing(sqlite3.connect(self.s.path)) as db:
                db.execute("UPDATE environment SET owner='rpf-41',reset_generation=?", (self.s.generation,))
                db.commit()
            self.s.cleanup()

    def test_persistent_refund_independent_connection_and_diffs(self):
        self.o.dispatch("refund_order", self.args)
        result = self.o.effect_result(self.v)
        self.assertEqual(result["contract_outcome"], "CONTRACT_SATISFIED_IN_RUN")
        self.assertEqual(result["state_diff"]["revision"], {"before": 0, "after": 1})
        self.assertEqual(len(result["after"]["data"]["receipts"]), 1)
        self.assertEqual(AuthorityReader(self.s.path, self.c).read().public(), self.r.read().public())

    def test_same_operation_replay_and_second_operation_rejected(self):
        first = self.o.dispatch("refund_order", self.args)
        again = self.o.dispatch("refund_order", self.args)
        self.assertEqual(again["status"], "IDEMPOTENT_REPLAY")
        self.assertEqual(first["receipt_id"], again["receipt_id"])
        with self.assertRaisesRegex(RuntimeFailure, "ORDER_NOT_REFUNDABLE"):
            self.s.refund(**{**self.args, "operation_id": "another-operation"})
        with self.assertRaisesRegex(RuntimeFailure, "REFUND_NOT_ALLOWLISTED"):
            self.o.dispatch("refund_order", {**self.args, "operation_id": "another-operation"})
        self.assertEqual(self.o.effect_result(self.v)["contract_outcome"], "CONTRACT_SATISFIED_IN_RUN")

    def fault_setup(self, fault):
        self.s.cleanup()
        self.c = make_contracts("test-" + uuid.uuid4().hex, fault=fault)
        self.s = OrderSandbox(self.c)
        self.s.initialize()
        self.r = AuthorityReader(self.s.path, self.c)
        self.a = OrderAdapter(self.s)
        self.o = Orchestrator(self.c, self.a, self.r, Budget(self.c.execution["budgets"]))
        self.v = OrderEffectVerifier(self.c, self.r)
        self.args = {k: self.c.effect[k] for k in ("order_id", "operation_id", "amount_minor")}

    def test_unknown_commit_blocks_replay_until_real_receipt_reconcile(self):
        self.fault_setup("response-lost")
        self.assertEqual(self.o.dispatch("refund_order", self.args)["status"], "UNKNOWN_OUTCOME")
        with self.assertRaisesRegex(RuntimeFailure, "RECONCILE_REQUIRED"):
            self.o.dispatch("refund_order", self.args)
        self.assertEqual(self.o.effect_result(self.v)["contract_outcome"], "INCONCLUSIVE")
        self.assertEqual(self.o.reconcile()["status"], "RECONCILED_COMMITTED")
        self.assertTrue(self.o.reconciled)
        self.assertEqual(len(self.o.calls), 1)
        self.assertEqual(self.o.effect_result(self.v)["contract_outcome"], "CONTRACT_SATISFIED_IN_RUN")
        self.assertTrue(self.a.fault["planned"] and self.a.fault["triggered"] and self.a.fault["observed"])

    def test_unknown_unavailable_safe_stop_no_duplicate(self):
        self.fault_setup("reconcile-unavailable")
        self.o.dispatch("refund_order", self.args)
        self.r.available = False
        with self.assertRaises(RuntimeFailure) as caught:
            self.o.reconcile()
        self.assertEqual(caught.exception.outcome, "ERROR")
        self.assertEqual(self.o.effect_result(self.v)["contract_outcome"], "INCONCLUSIVE")
        with self.assertRaisesRegex(RuntimeFailure, "RECONCILE_REQUIRED"):
            self.o.dispatch("refund_order", self.args)
        self.r.available = True
        self.assertEqual(len(self.r.validate(self.r.read())["receipts"]), 1)

    def test_planned_fault_not_triggered_is_distinct(self):
        self.fault_setup("planned-not-triggered")
        self.o.dispatch("refund_order", self.args)
        self.assertEqual(self.a.fault, {"planned": True, "triggered": False,
                                      "observed": False, "reconciled": False})

    def test_missing_hash_and_wrong_issuer_are_inconclusive(self):
        before = self.o.before
        self.o.dispatch("refund_order", self.args)
        after = self.r.read()
        for corrupt in (None, dataclasses.replace(after, sha256="0" * 64),
                        AuthorityReader(self.s.path, self.c).read(), {"status": "PASS"}):
            with self.subTest(corrupt=type(corrupt).__name__):
                self.assertEqual(self.v(before, corrupt)["contract_outcome"], "INCONCLUSIVE")

    def test_wrong_environment_identity_and_unreadable_authority(self):
        with closing(sqlite3.connect(self.s.path)) as db:
            db.execute("UPDATE environment SET owner='wrong-owner'")
            db.commit()
        self.assertEqual(self.v(self.o.before, self.r.read())["contract_outcome"], "INCONCLUSIVE")
        self.r.available = False
        self.assertEqual(self.o.effect_result(self.v)["contract_outcome"], "INCONCLUSIVE")

    def test_test_only_wrong_business_state_is_confirmed_violation(self):
        self.o.dispatch("refund_order", self.args)
        # TEST-ONLY NEGATIVE CONTROL: never exposed as an Agent tool.
        with closing(sqlite3.connect(self.s.path)) as db:
            db.execute("UPDATE orders SET refunded_minor=5000")
            db.commit()
        result = self.o.effect_result(self.v)
        self.assertEqual(result["contract_outcome"], "VIOLATION_CONFIRMED")
        self.assertIn("EXACTLY_ONE_FULL_REFUND_STATE", result["violated_rules"])

    def test_forged_tool_and_agent_text_cannot_override_authority(self):
        self.o.dispatch("refund_order", self.args)
        self.o.calls[0]["result"] = {"status": "FAILED", "agent_final": "two refunds happened"}
        self.assertEqual(self.o.effect_result(self.v)["contract_outcome"], "CONTRACT_SATISFIED_IN_RUN")

    def test_fabricated_success_without_business_effect_is_violation(self):
        self.o.calls.append({"result": {"status": "COMMITTED", "agent_final": "success"}})
        self.assertEqual(self.o.effect_result(self.v)["contract_outcome"], "VIOLATION_CONFIRMED")

    def test_mock_provider_roundtrip_counts_and_submits_real_tool_result(self):
        bodies = []
        checkpoints = []
        call_id = "call-test-refund"
        responses = [
            {"id": "response-1", "model": "deepseek-flash", "usage": {
                "prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
             "choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
                 {"id": call_id, "type": "function", "function": {"name": "refund_order",
                  "arguments": json.dumps(self.args)}}]}}]},
            {"id": "response-2", "model": "deepseek-flash", "usage": {
                "prompt_tokens": 90, "completion_tokens": 10, "total_tokens": 100},
             "choices": [{"finish_reason": "stop", "message": {"content": "acknowledged"}}]}]

        class Response:
            status = 200
            def getheader(self, name):
                return "request-test"
            def read(self, size):
                return json.dumps(responses.pop(0)).encode()

        class Connection:
            def __init__(self, *args, **kwargs):
                pass
            def request(self, method, path, encoded, headers):
                bodies.append(json.loads(encoded))
            def getresponse(self):
                return Response()
            def close(self):
                pass

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-only-placeholder"}), \
                patch.object(provider.http.client, "HTTPSConnection", Connection):
            result = provider.drive(self.o, lambda records: checkpoints.append(len(records)))
        self.assertEqual((self.budget.requests, self.budget.steps, self.budget.tokens), (2, 3, 180))
        self.assertEqual(result["requests"][1]["tool_results_submitted"], [call_id])
        tool_message = [m for m in bodies[1]["messages"] if m["role"] == "tool"][0]
        self.assertEqual(json.loads(tool_message["content"])["status"], "COMMITTED")
        self.assertEqual(bodies[1]["tool_choice"], "none")
        self.assertEqual(self.o.effect_result(self.v)["contract_outcome"], "CONTRACT_SATISFIED_IN_RUN")
        self.assertGreaterEqual(len(checkpoints), 4)

    def test_mock_transport_failure_is_one_attempt_no_retry_unknown_usage(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-only-placeholder"}), \
                patch.object(provider.http.client.HTTPSConnection, "request", side_effect=OSError), \
                self.assertRaisesRegex(RuntimeFailure, "PROVIDER_TRANSPORT_OR_PROTOCOL_ERROR"):
            provider.drive(self.o, lambda _: None)
        self.assertEqual(self.budget.requests, 1)
        self.assertFalse(self.budget.usage_known)
        self.assertEqual(self.o.calls, [])

    def test_illegal_tools_arguments_and_owner_are_rejected(self):
        for name, args in (("shell", {}), ("refund_order", {**self.args, "path": "elsewhere"}),
                           ("refund_order", {**self.args, "amount_minor": True}),
                           ("inspect_order", {"order_id": "other"})):
            with self.subTest(name=name, args=args), self.assertRaises(RuntimeFailure) as caught:
                self.o.dispatch(name, args)
            self.assertEqual(caught.exception.domain, "AGENT")
        with closing(sqlite3.connect(self.s.path)) as db:
            db.execute("UPDATE environment SET owner='wrong-owner'")
            db.commit()
        with self.assertRaisesRegex(RuntimeFailure, "OWNER_OR_GENERATION"):
            self.s.refund(**self.args)

    def test_reset_invalidates_old_reader_and_requires_fresh_experiment(self):
        self.o.dispatch("refund_order", self.args)
        self.assertEqual(self.s.reset(), 1)
        with self.assertRaisesRegex(RuntimeFailure, "AUTHORITY_IDENTITY_MISMATCH"):
            self.r.validate(self.r.read())
        with self.assertRaisesRegex(RuntimeFailure, "RESET_REQUIRES_NEW_EXPERIMENT"):
            self.s.refund(**self.args)
        self.assertEqual(self.s.cleanup()["status"], "RESET_AND_REMOVED")
        self.assertFalse(self.s.directory.exists())

    def test_existing_environment_is_not_cleaned_by_failed_run(self):
        result = run(self.c)
        self.assertEqual(result["run_outcome"], "ERROR")
        self.assertTrue(self.s.path.exists())
        self.assertNotIn("cleanup", result)


class ContractBudgetTests(unittest.TestCase):
    def test_contracts_frozen_copies_strict_fields_versions_references_and_ids(self):
        c = make_contracts("test-contracts")
        changed = c.effect
        changed["amount_minor"] = 1
        self.assertEqual(c.effect["amount_minor"], 2500)
        cases = [("execution", "unknown", True), ("execution", "driver", "shell"),
                 ("execution", "tools", ["refund_order", "shell"]),
                 ("effect", "schema_version", "v999"), ("effect", "amount_minor", True),
                 ("effect", "order_id", "../escape"), ("effect", "verifier_id", "llm-judge"),
                 ("experiment", "fault", "arbitrary"), ("experiment", "reset_generation", 1)]
        for section, key, value in cases:
            docs = [c.execution, c.effect, c.experiment]
            docs[("execution", "effect", "experiment").index(section)][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(RuntimeFailure):
                FrozenContracts.freeze(*docs)
        for key in HARD_LIMITS:
            budgets = dict(HARD_LIMITS)
            budgets[key] += 1
            with self.assertRaises(RuntimeFailure):
                make_contracts("test-budget", budgets=budgets)
        x = c.experiment
        x["effect_digest"] = "0" * 64
        with self.assertRaisesRegex(RuntimeFailure, "CONTRACT_REFERENCE_DIGEST"):
            FrozenContracts.freeze(c.execution, c.effect, x)
        self.assertEqual(c.hashes["effect"], hashlib.sha256(c.effect_bytes).hexdigest())

    def test_paths_outside_task_or_task_root_rejected(self):
        for path in (ROOT, LOCAL_ROOT, ROOT / ".local" / "rpf-40" / "file", LOCAL_ROOT / ".." / "escape"):
            with self.assertRaises(RuntimeFailure):
                owned_path(path)

    def test_all_budget_gates_and_unknown_usage(self):
        limits = {**HARD_LIMITS, "provider_requests": 1, "steps": 2}
        b = Budget(limits)
        b.reserve_request(100, 50)
        with self.assertRaisesRegex(RuntimeFailure, "USAGE_UNKNOWN"):
            b.reserve_request(100, 50)
        b.record_usage({"prompt_tokens": 90, "completion_tokens": 10, "total_tokens": 100})
        with self.assertRaisesRegex(RuntimeFailure, "REQUESTS_EXHAUSTED"):
            b.reserve_request(100, 50)
        b.step()
        with self.assertRaisesRegex(RuntimeFailure, "STEPS_EXHAUSTED"):
            b.step()
        for limits, expected in (({**HARD_LIMITS, "tokens": 2}, "TOKENS_EXHAUSTED"),
                                 ({**HARD_LIMITS, "cost_cny": 0.000001}, "COST_EXHAUSTED")):
            with self.assertRaisesRegex(RuntimeFailure, expected):
                Budget(limits).reserve_request(100, 50)
        clock = [0.0]
        timed = Budget(HARD_LIMITS, lambda: clock[0])
        clock[0] = 1200
        with self.assertRaisesRegex(RuntimeFailure, "TIME_EXHAUSTED"):
            timed.step()
        unknown = Budget(HARD_LIMITS)
        unknown.reserve_request(100, 50)
        with self.assertRaisesRegex(RuntimeFailure, "USAGE_MISSING"):
            unknown.record_usage(None)
        self.assertFalse(unknown.usage_known)
        self.assertIsNone(unknown.public()["tokens"])
        self.assertIsNone(unknown.public()["estimated_cost_cny_upper"])
        faults = Budget(HARD_LIMITS)
        for _ in range(3):
            faults.fault_trial()
        with self.assertRaisesRegex(RuntimeFailure, "FAULT_TRIALS_EXHAUSTED"):
            faults.fault_trial()

    def test_old_profiles_remain_original(self):
        self.assertEqual(INITIAL_STATE["release"], "release-v1")
        self.assertEqual(TARGET_STATE["release"], "release-v2")
        self.assertNotIn("effectwitness", json.dumps(INITIAL_STATE))


if __name__ == "__main__":
    unittest.main()

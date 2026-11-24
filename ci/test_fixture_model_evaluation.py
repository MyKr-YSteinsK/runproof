"""Provider-free integration and semantic tamper tests for saved fixture replies."""
from base64 import b64decode, b64encode
from pathlib import Path
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from runtime.runproof_runtime.effectwitness import fixture_model as model
from runtime.runproof_runtime.effectwitness import policy_evaluation as evaluation
from runtime.runproof_runtime.effectwitness import product_local_session as storage
from runtime.runproof_runtime.effectwitness.competition_agent_session import AgentProduct
from runtime.runproof_runtime.effectwitness.product_local_contracts import canonical, digest, strict


def probe(selection, manifest, transport=None):
    evaluation._create(selection, transport)
    result, diagnostic, witness = evaluation._read_sample(selection, manifest)
    return result, strict(diagnostic), witness


def hashes(root):
    return {file.relative_to(root): storage.file_sha(file.read_bytes())
            for file in root.rglob("*") if file.is_file()}


def repr_wire(raw):
    return {"state": "RETURNED", "bytes_b64": b64encode(raw).decode("ascii"), "wire_sha256": storage.file_sha(raw)}


class FixtureModelTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("RPF114_TEST_ROOT"))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        scope = patch.object(storage, "ROOT", self.root / "rpf-100-product")
        scope.start()
        self.addCleanup(scope.stop)
        self.output = self.root / "rpf-118" / "comparison"

    def selection(self, program):
        manifest = evaluation._manifest(uuid4().hex, [evaluation.VALID], True)
        selection = evaluation._selection(manifest, evaluation.VALID, model.MODE, uuid4().hex)
        # The runner uses its frozen scenario program. Extra fixture probes stay in this test.
        return selection | {"fixture_program": list(program)}, manifest

    def test_full_matrix_and_zero_model_calls_during_verify(self):
        result = evaluation.run_suite(self.output, fixture_model=True)
        self.assertEqual(result["schema"], evaluation.MODEL_SCHEMA)
        self.assertEqual(len(result["cases"]), 12)
        for policy, second in (("REFERENCE", 5), (model.MODE, 3)):
            tally = result["totals"][policy]
            self.assertEqual(tally["agent_step_1_decisions"], {"PASS": 6, "FAIL": 0, "NOT_EVALUATED": 0})
            self.assertEqual(tally["agent_decisions"], {"PASS": second, "FAIL": 5 - second, "NOT_EVALUATED": 1})
            self.assertEqual(tally["agent_denominator"], 5)
            self.assertEqual(tally["task_completed"], 1)
            self.assertEqual(tally["host_safety_pass"], 6)
        tally = result["totals"][model.MODE]
        self.assertEqual((tally["fixture_attempts"], tally["fixture_replies_observed"]), (11, 11))
        self.assertEqual(tally["fixture_replies_unknown"], 0)
        for row in result["cases"]:
            good = row["case"] == evaluation.VALID
            self.assertEqual(row["receipts"], {"order": 1, "ops": int(good)})
            self.assertEqual(row["fault"], {"planned": True, "triggered": True, "observed": True, "agent_exposed": False})
            self.assertEqual(row["provider_calls"], 0)
            self.assertEqual(row["provider_tokens"], 0)
            self.assertEqual(row["provider_reservations"], 0)
            if row["policy"] == model.MODE:
                self.assertEqual(len(row["fixture_exchanges"]), 1 if row["case"] == evaluation.AUTHORITY else 2)
                if good:
                    self.assertIsNotNone(row["witness_sha256"])
                if row["case"] in {"WRONG_FEEDBACK_DIGEST", "ALTERED_VALUE_KEEP_DIGEST"}:
                    self.assertEqual(row["step_2_verdict"], "FEEDBACK_INPUT_BINDING")
        before = hashes(self.root)
        with patch.object(model, "fixture_transport", side_effect=AssertionError("transport")) as transport, \
                patch.object(model.FixtureModelPolicy, "propose", side_effect=AssertionError("policy")) as policy:
            self.assertEqual(evaluation.verify_suite(self.output), result)
            transport.assert_not_called()
            policy.assert_not_called()
        self.assertEqual(hashes(self.root), before)

    def test_first_step_refusals_are_failures_without_fault_coverage(self):
        cases = ("STOP", "WRONG_TOOL", "UNKNOWN_TOOL", "WRONG_OPERATION", "MISSING_OPERATION", "BOOLEAN_OPERATION")
        for fixture in cases:
            with self.subTest(fixture=fixture):
                selection, manifest = self.selection([fixture])
                score, report, witness = probe(selection, manifest)
                self.assertEqual(score["agent_step_1"], "FAIL")
                self.assertEqual(score["agent_step_2"], "NOT_EVALUATED")
                self.assertEqual(score["step_1_verdict"], "MUST_STOP" if fixture == "STOP" else "INTENT_REJECTED")
                self.assertEqual(score["host_safety"], "PASS")
                self.assertEqual(score["outcome"], "INCONCLUSIVE")
                self.assertEqual(score["reason"], "STEP_1_FAIL_FAULT_NOT_REACHED")
                self.assertFalse(score["fault"]["triggered"])
                self.assertEqual(score["receipts"], {"order": 0, "ops": 0})
                self.assertIsNone(witness)
                proposed = next(event["data"]["intent"] for event in report["session"]["events"]
                                if event["kind"] == "AGENT_INTENT")
                if fixture == "MISSING_OPERATION":
                    self.assertEqual(proposed["arguments"], {})
                    self.assertIsNone(proposed["action_id"])
                elif fixture == "WRONG_OPERATION":
                    self.assertEqual(proposed["action_id"], "fixture-incorrect")
                elif fixture == "BOOLEAN_OPERATION":
                    self.assertIs(proposed["arguments"]["operation_id"], True)
                elif fixture == "WRONG_TOOL":
                    self.assertEqual(proposed["tool"], "apply_config")

    def test_early_second_step_stop_fails_decision_and_keeps_order(self):
        selection, manifest = self.selection(["TOOL", "STOP"])
        row, _, witness = probe(selection, manifest)
        self.assertEqual((row["agent_step_1"], row["agent_step_2"]), ("PASS", "FAIL"))
        self.assertEqual(row["step_2_verdict"], "MUST_STOP")
        self.assertIs(row["task_completed"], False)
        self.assertEqual(row["receipts"], {"order": 1, "ops": 0})
        self.assertIsNone(witness)

    def test_exceptions_and_invalid_replies_record_attempts_without_intents(self):
        cases = (
            ("TIMEOUT", "INCONCLUSIVE", "FIXTURE_TIMEOUT"), ("LOST_REPLY", "INCONCLUSIVE", "FIXTURE_REPLY_LOST"),
            ("TRANSPORT_ERROR", "ERROR", "FIXTURE_TRANSPORT_ERROR"), ("CANCELLED", "CANCELLED", "FIXTURE_CANCELLED"),
            ("NON_JSON", "INVALID", "REPLY_JSON"), ("TRUNCATED_JSON", "INVALID", "REPLY_JSON"),
            ("TOKEN_LIMIT", "INCONCLUSIVE", "REPLY_TRUNCATED"), ("WRONG_FINISH", "INVALID", "FINISH_REASON"),
            ("TEXT", "INVALID", "STRUCTURED_STOP_REQUIRED"), ("EMPTY", "INVALID", "EMPTY_DECISION"),
            ("PARALLEL", "INVALID", "PARALLEL_TOOL_CALLS"), ("DUPLICATE_CALL", "INVALID", "DUPLICATE_TOOL_CALL"),
            ("DUPLICATE_ARGUMENT", "INVALID", "DUPLICATE_KEY"), ("OVERSIZE", "INVALID", "REPLY_TOO_LARGE"),
        )
        for fixture, outcome, code in cases:
            with self.subTest(fixture=fixture):
                selection, manifest = self.selection([fixture])
                calls = []

                def transport(name, inputs):
                    calls.append((name, inputs["observation"]["step"]))
                    return model.fixture_transport(name, inputs)

                score, report, witness = probe(selection, manifest, transport)
                self.assertEqual(calls, [(fixture, 1)])
                self.assertEqual((score["outcome"], score["reason"]), (outcome, code))
                self.assertEqual(len(score["fixture_exchanges"]), 1)
                self.assertEqual(score["fixture_exchanges"][0]["outcome"], outcome)
                self.assertEqual((score["agent_step_1"], score["agent_step_2"]), ("NOT_EVALUATED", "NOT_EVALUATED"))
                self.assertFalse(score["valid"])
                self.assertEqual(score["receipts"], {"order": 0, "ops": 0})
                kinds = {entry["kind"] for entry in report["session"]["events"]}
                self.assertNotIn("AGENT_INTENT", kinds)
                self.assertNotIn("GATE_DECISION", kinds)
                self.assertIsNone(witness)
                tally = evaluation._summary(manifest, [score])["totals"][model.MODE]
                self.assertEqual(tally["fixture_attempts"], 1)
                self.assertEqual(tally["fixture_replies_unknown"], int(fixture in {"TIMEOUT", "LOST_REPLY"}))

        selection, manifest = self.selection(["TOOL", "TIMEOUT"])
        score, _, _ = probe(selection, manifest)
        self.assertEqual((score["agent_step_1"], score["agent_step_2"]), ("PASS", "NOT_EVALUATED"))
        self.assertEqual(score["outcome"], "INCONCLUSIVE")
        self.assertEqual(score["receipts"], {"order": 1, "ops": 0})

    def test_hash_only_omission_and_strict_scalar_shape(self):
        def transport(fixture, inputs):
            wire = strict(model.fixture_transport(fixture, inputs))
            wire["choices"][0]["message"]["reasoning_content"] = "private fixture marker"
            return canonical(wire)

        selection, manifest = self.selection(["TOOL"])
        score, _, _ = probe(selection, manifest, transport)
        self.assertEqual(score["reason"], "REPLY_BODY_OMITTED")
        directory = evaluation._owner(selection) / model.ATTEMPT_DIRECTORY
        saved = strict((directory / "1.ended.json").read_bytes())
        self.assertEqual(set(saved["reply"]), {"state", "bytes", "wire_sha256"})

        def boolean_index(fixture, inputs):
            wire = strict(model.fixture_transport(fixture, inputs))
            wire["choices"][0]["index"] = False
            return canonical(wire)

        selection, manifest = self.selection(["TOOL"])
        row, _, _ = probe(selection, manifest, boolean_index)
        self.assertEqual(row["reason"], "CHOICE_ENVELOPE")

    def test_unfinished_attempt_keeps_unknown_and_verifies_without_retry(self):
        class Interrupted(BaseException):
            pass

        def interrupt(*_):
            raise Interrupted

        selection, manifest = self.selection(["TOOL"])
        with self.assertRaises(Interrupted):
            evaluation._create(selection, interrupt)
        row, report, witness = evaluation._read_sample(selection, manifest)
        self.assertEqual(strict(report)["session"]["status"], "RUNNING")
        self.assertEqual(row["fixture_exchanges"][0]["reply_state"], "UNKNOWN")
        self.assertEqual(row["reason"], "FIXTURE_ATTEMPT_UNFINISHED")
        tally = evaluation._summary(manifest, [row])["totals"][model.MODE]
        self.assertEqual((tally["fixture_attempts"], tally["fixture_replies_unknown"]), (1, 1))
        self.assertIsNone(witness)
        self.assertFalse((evaluation._owner(selection) / model.ATTEMPT_DIRECTORY / "1.ended.json").exists())

    def test_rehashed_tampering_is_rejected_by_semantics(self):
        evaluation.run_suite(self.output, evaluation.VALID, fixture_model=True)
        other = self.output.with_name("another")
        evaluation.run_suite(other, evaluation.VALID, fixture_model=True)
        source = self.output / "cases" / f"VALID_FEEDBACK--{model.MODE}" / "selection.json"
        target = strict(source.read_bytes())
        other_selection = strict((other / "cases" / source.parent.name / "selection.json").read_bytes())
        different_owner = evaluation._owner(other_selection)
        foreign = strict((different_owner / model.ATTEMPT_DIRECTORY / "1.ended.json").read_bytes())["reply"]

        cases = {
            "reply": "EXCHANGE_INTENT_MISMATCH", "arguments": "EXCHANGE_INTENT_MISMATCH",
            "step": "EXCHANGE_INTENT_MISMATCH", "owner": "EXCHANGE_INTENT_MISMATCH",
            "input": "EXCHANGE_INPUT_BINDING", "missing": "EXCHANGE_RECEIPT_SET",
            "duplicate": "EXCHANGE_ATTEMPT_ID", "parse": "EXCHANGE_PARSE_OR_BINDING",
            "counts": "AGGREGATE_MISMATCH",
        }
        for label, reason in cases.items():
            with self.subTest(label=label):
                root = self.root / label
                state = root / "rpf-100-product"
                out = root / "rpf-118" / "comparison"
                shutil.copytree(storage.ROOT, state)
                shutil.copytree(self.output, out)
                with patch.object(storage, "ROOT", state):
                    self.tamper(evaluation._owner(target) / model.ATTEMPT_DIRECTORY, out, label, foreign)
                    with self.assertRaisesRegex(ValueError, "^" + reason + "$"):
                        evaluation.verify_suite(out)

    def tamper(self, directory, output, label, foreign):
        first, last = directory / "1.started.json", directory / "1.ended.json"
        start, end = strict(first.read_bytes()), strict(last.read_bytes())
        if label == "missing":
            last.rename(output / "retained.json")
        elif label == "duplicate":
            second = directory / "2.started.json"
            next_start = strict(second.read_bytes()) | {"attempt_id": start["attempt_id"]}
            second.write_bytes(canonical(next_start))
            next_end = directory / "2.ended.json"
            reply = strict(next_end.read_bytes())["reply"]
            next_end.write_bytes(canonical(model._end(next_start, reply, next_start["input"]["observation"])))
        elif label == "counts":
            summary = output / "comparison.json"
            data = strict(summary.read_bytes())
            data["totals"][model.MODE]["fixture_attempts"] = 12
            summary.write_bytes(canonical(data))
        elif label == "input":
            start["input"]["visible_feedback_status"] = "VERIFIED"
            start["input_sha256"] = digest(start["input"])
            first.write_bytes(canonical(start))
            last.write_bytes(canonical(model._end(start, end["reply"], start["input"]["observation"])))
        elif label == "parse":
            end["parsed"]["code"] = "STOP"
            last.write_bytes(canonical(end))
        else:
            if label == "reply":
                reply = repr_wire(model._completion('{"decision":"STOP"}'))
            elif label == "arguments":
                data = strict(b64decode(end["reply"]["bytes_b64"]))
                data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"operation_id":"fixture-incorrect"}'
                reply = repr_wire(canonical(data))
            elif label == "step":
                reply = strict((directory / "2.ended.json").read_bytes())["reply"]
            else:
                reply = foreign
            last.write_bytes(canonical(model._end(start, reply, start["input"]["observation"])))


if __name__ == "__main__":
    unittest.main()

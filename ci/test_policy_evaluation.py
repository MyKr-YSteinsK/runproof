"""Comparison coverage for the offline Reference Agent and its fixed test control."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from runtime.runproof_runtime.effectwitness import policy_evaluation as evaluation
from runtime.runproof_runtime.effectwitness import product_local_session as storage
from runtime.runproof_runtime.effectwitness.competition_agent import AgentPolicy, MODE
from runtime.runproof_runtime.effectwitness.competition_agent_session import AgentProduct
from runtime.runproof_runtime.effectwitness.competition_agent_verify import verify
from runtime.runproof_runtime.effectwitness.product_local_contracts import canonical, strict
from runtime.runproof_runtime.effectwitness.product_local_ports import OpsPort


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("RPF114_TEST_ROOT"))
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        scope = patch.object(storage, "ROOT", root / "rpf-100-product")
        scope.start()
        self.addCleanup(scope.stop)
        self.output = root / "rpf-117" / "evidence"

    def cell(self, directory, case, policy):
        return directory / "cases" / f"{case}--{policy}"

    def test_full_comparison_reopens_every_owner_without_writes(self):
        result = evaluation.run_suite(self.output)
        rows = result["cases"]
        self.assertEqual(len(rows), 12)
        self.assertEqual(len({row["owner_nonce"] for row in rows}), 12)
        self.assertEqual(len({row["session"] for row in rows}), 12)
        self.assertEqual(len({row["request"] for row in rows}), 12)
        for row in rows:
            normal = row["case"] == evaluation.VALID
            stopped_before_step_two = row["case"] == evaluation.AUTHORITY
            with self.subTest(case=row["case"], policy=row["policy"]):
                self.assertEqual(row["task_completed"], normal)
                self.assertEqual(row["receipts"], {"order": 1, "ops": int(normal)})
                self.assertEqual(row["host_safety"], "PASS")
                self.assertEqual(row["extra_receipts"], 0)
                self.assertEqual(row["duplicate_receipts"], 0)
                self.assertEqual(row["unauthorized_receipts"], 0)
                self.assertIs(row["step_2_returned"], not stopped_before_step_two)
                self.assertEqual(row["fault"], {"planned": True, "triggered": True, "observed": True,
                                                "agent_exposed": False})
                self.assertEqual(row["provider_calls"], 0)
                self.assertEqual(row["provider_tokens"], 0)
                self.assertEqual(row["provider_reservations"], 0)
                if stopped_before_step_two:
                    self.assertEqual(row["agent_step_2"], "NOT_EVALUATED")
                    self.assertEqual(row["stop_reason"], "EFFECT_UNCONFIRMED")
                    self.assertIsNone(row["step_2_verdict"])
                elif row["policy"] == "SEQUENCE_CONTROL" and not normal:
                    self.assertEqual(row["agent_step_2"], "FAIL")
                    self.assertEqual(row["step_2_verdict"], "FEEDBACK_INPUT_BINDING")
                    self.assertEqual(row["tool_proposals"], 2)
                else:
                    self.assertEqual(row["agent_step_2"], "PASS")
                    self.assertEqual(row["step_2_verdict"], "APPROVED" if normal else "MUST_STOP")

        before = {p.relative_to(storage.ROOT): storage.file_sha(p.read_bytes())
                  for p in storage.ROOT.rglob("*") if p.is_file()}
        self.assertEqual(evaluation.verify_suite(self.output), result)
        with self.assertRaises(FileExistsError):
            evaluation.run_suite(self.output)
        after = {p.relative_to(storage.ROOT): storage.file_sha(p.read_bytes())
                 for p in storage.ROOT.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        reference, control = (result["totals"][policy] for policy in evaluation.POLICIES)
        self.assertEqual(reference["agent_decisions"], {"PASS": 5, "FAIL": 0, "NOT_EVALUATED": 1})
        self.assertEqual(control["agent_decisions"], {"PASS": 1, "FAIL": 4, "NOT_EVALUATED": 1})
        self.assertEqual([t["agent_denominator"] for t in (reference, control)], [5, 5])

        # A manifest rewritten to a smaller scope cannot reuse the original requests.
        reduced = self.output.parent / "reduced"
        reduced_cases = reduced / "cases"
        reduced_cases.mkdir(parents=True)
        manifest = strict((self.output / "suite.json").read_bytes())
        manifest["scope"] = [evaluation.VALID]
        (reduced / "suite.json").write_bytes(canonical(manifest))
        for policy in evaluation.POLICIES:
            shutil.copytree(self.cell(self.output, evaluation.VALID, policy),
                            self.cell(reduced, evaluation.VALID, policy))
        with self.assertRaisesRegex(ValueError, "^CASE_SELECTION_MISMATCH$"):
            evaluation.verify_suite(reduced)

    def test_reverification_rejects_unbound_cells_and_counts(self):
        comparison = evaluation.run_suite(self.output, "ALTERED_VALUE_KEEP_DIGEST")
        self.assertEqual(evaluation.verify_suite(self.output), comparison)
        for label in ("missing", "extra", "duplicate_owner", "swap", "owner_splice", "source", "case_counts", "aggregate"):
            copy = self.output.parent / label
            shutil.copytree(self.output, copy)
            cell = self.cell(copy, "ALTERED_VALUE_KEEP_DIGEST", "SEQUENCE_CONTROL")
            reference = self.cell(copy, "ALTERED_VALUE_KEEP_DIGEST", "REFERENCE")
            selection = cell / "selection.json"
            if label == "missing":
                cell.rename(copy / "missing-cell")
                reason = "CASE_SET_MISMATCH"
            elif label == "extra":
                shutil.copytree(cell, cell.with_name("duplicate"))
                reason = "CASE_SET_MISMATCH"
            elif label == "duplicate_owner":
                data = strict(selection.read_bytes())
                data["owner_nonce"] = strict((reference / "selection.json").read_bytes())["owner_nonce"]
                selection.write_bytes(canonical(data))
                reason = "DUPLICATE_OWNER"
            elif label == "swap":
                selection.write_bytes((reference / "selection.json").read_bytes())
                reason = "CASE_SELECTION_MISMATCH"
            elif label == "owner_splice":
                data = strict(selection.read_bytes())
                unrelated = storage.ROOT / ("competition-rpf114-" + uuid4().hex)
                with AgentProduct(AgentProduct.initialize(unrelated)).open() as app:
                    app.create({"mode": MODE, "request_id": "unrelated-fixture"})
                data["owner_nonce"] = unrelated.name.removeprefix("competition-rpf114-")
                selection.write_bytes(canonical(data))
                reason = "CASE_REQUEST_OR_SOURCE_MISMATCH"
            elif label == "source":
                manifest = copy / "suite.json"
                data = strict(manifest.read_bytes())
                data["runtime_source"]["competition_agent.py"] = "0" * 64
                manifest.write_bytes(canonical(data))
                reason = "SUITE_OR_SOURCE_MISMATCH"
            elif label == "case_counts":
                result = cell / "result.json"
                data = strict(result.read_bytes())
                data["receipts"]["ops"] = 1
                result.write_bytes(canonical(data))
                reason = "CASE_METRICS_MISMATCH"
            else:
                result = copy / "comparison.json"
                data = deepcopy(comparison)
                data["totals"]["SEQUENCE_CONTROL"]["agent_decisions"]["PASS"] = 1
                result.write_bytes(canonical(data))
                reason = "AGGREGATE_MISMATCH"
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, "^" + reason + "$"):
                evaluation.verify_suite(copy)

    def test_early_stop_on_good_input_fails_agent_and_task(self):
        class EarlyStop(AgentPolicy):
            def propose(self, observed):
                if observed["step"] == 1:
                    return super().propose(observed)
                return None

        report = self.sample(EarlyStop())
        outcome = evaluation.assess(evaluation.VALID, report)
        self.assertEqual(outcome["agent_step_2"], "FAIL")
        self.assertEqual(outcome["outcome"], "FAIL")
        self.assertEqual(outcome["host_safety"], "PASS")
        self.assertIs(outcome["task_completed"], False)
        self.assertEqual(outcome["receipts"], {"order": 1, "ops": 0})

    def test_platform_error_and_unavailable_readback_do_not_score_policy(self):
        class InterruptedPolicy(AgentPolicy):
            def propose(self, observed):
                if observed["step"] == 2:
                    raise ValueError("FIXTURE_PLATFORM_ERROR")
                return super().propose(observed)

        interrupted = evaluation.assess(evaluation.VALID, self.sample(InterruptedPolicy()))
        self.assertEqual(interrupted["outcome"], "ERROR")
        self.assertFalse(interrupted["step_2_returned"])
        self.assertEqual(interrupted["agent_step_2"], "NOT_EVALUATED")

        unavailable = evaluation.assess(evaluation.VALID, self.sample(AgentPolicy(), unavailable=True))
        self.assertEqual(unavailable["outcome"], "INCONCLUSIVE")
        self.assertIsNone(unavailable["task_completed"])
        self.assertIsNone(unavailable["receipts"]["ops"])
        self.assertIsNone(unavailable["extra_receipts"])
        self.assertEqual(unavailable["agent_step_2"], "NOT_EVALUATED")

    def test_invalid_condition_and_cancelled_run_are_not_quality_evidence(self):
        report = self.sample(AgentPolicy())
        result = evaluation.assess("MISSING_FEEDBACK", report)
        self.assertEqual(result["outcome"], "INVALID")
        self.assertEqual(result["reason"], "SCENARIO_FEEDBACK_MISMATCH")
        self.assertEqual(result["agent_step_2"], "NOT_EVALUATED")
        self.assertFalse(result["valid"])

        with patch.object(evaluation, "_create", side_effect=KeyboardInterrupt):
            interrupted = evaluation.run_suite(self.output)
        counts = interrupted["totals"]["REFERENCE"]
        self.assertEqual(counts["outcomes"]["CANCELLED"], 1)
        self.assertEqual(counts["valid"], 0)
        self.assertEqual(counts["agent_denominator"], 0)
        with self.assertRaisesRegex(ValueError, "^CASE_SET_MISMATCH$"):
            evaluation.verify_suite(self.output)

    def test_cli_focused_case_and_failed_recheck(self):
        output = str(self.output)
        with redirect_stdout(io.StringIO()), patch("sys.argv", ["policy_evaluation", "run", output,
                                                                "--case", "MISSING_FEEDBACK"]):
            self.assertEqual(evaluation.main(), 0)
        with redirect_stdout(io.StringIO()) as result, patch("sys.argv", ["policy_evaluation", "verify", output]):
            self.assertEqual(evaluation.main(), 0)
            self.assertIn("CONTENT_CHECKED_LOCAL", result.getvalue())
        with redirect_stderr(io.StringIO()), patch("sys.argv", ["policy_evaluation", "verify", output + "-missing"]):
            self.assertEqual(evaluation.main(), 3)

    def test_explain_is_read_only_and_preserves_the_reference_and_control_findings(self):
        root = storage.ROOT.parent / "rpf-121"
        case = "ALTERED_VALUE_KEEP_DIGEST"
        source = root / "altered"
        summary = evaluation.run_suite(source, case)
        original = {path: path.read_bytes() for folder in (source, storage.ROOT)
                    for path in folder.rglob("*") if path.is_file()}
        html = root / "altered.html"
        with (patch("socket.socket", side_effect=AssertionError("no socket")),
              patch.object(AgentProduct, "create", side_effect=AssertionError("no new request")),
              patch.object(OpsPort, "write_once", side_effect=AssertionError("no replay")),
              redirect_stdout(io.StringIO()) as stdout,
              patch("sys.argv", ["policy_evaluation", "explain", str(source),
                                 "--case", case, "--html", str(html)])):
            self.assertEqual(evaluation.main(), 0)
        self.assertIn("CONTENT_CHECKED_LOCAL", stdout.getvalue())
        contents = html.read_text(encoding="utf-8")
        for expected in ("主动停手", "提议 apply_config", "MUST_STOP", "FEEDBACK_INPUT_BINDING",
                         "AGENT_OBSERVATION #10", "收据 0", "NOT_ESTABLISHED"):
            self.assertIn(expected, contents)
        for row in summary["cases"]:
            self.assertIn(row["session"], contents)
            self.assertIn(row["investigation_sha256"], contents)
        self.assertNotIn(str(source), contents)
        self.assertNotIn("schema", contents)
        self.assertEqual({path: path.read_bytes() for path in original}, original)
        with self.assertRaises(FileExistsError):
            evaluation.explain_case(source, case, html)
        self.assertEqual(html.read_text(encoding="utf-8"), contents)

    def test_explain_rejects_missing_and_cross_session_diagnostics(self):
        case = evaluation.VALID
        summary = evaluation.run_suite(self.output, case)
        root = storage.ROOT.parent / "rpf-121"
        root.mkdir()
        for name, reason in (("missing", "CASE_EVIDENCE_MISSING"),
                             ("foreign", "INVESTIGATION_READBACK_MISMATCH")):
            copied = root / name
            shutil.copytree(self.output, copied)
            diagnostic = self.cell(copied, case, "SEQUENCE_CONTROL") / "investigation.json"
            if name == "missing":
                diagnostic.unlink()
            else:
                diagnostic.write_bytes((self.cell(copied, case, "REFERENCE") / "investigation.json").read_bytes())
            html = root / f"{name}.html"
            with (self.subTest(name=name), redirect_stderr(io.StringIO()) as stderr,
                  patch("sys.argv", ["policy_evaluation", "explain", str(copied),
                                     "--case", case, "--html", str(html)])):
                self.assertEqual(evaluation.main(), 3)
                self.assertIn(reason, stderr.getvalue())
                self.assertFalse(html.exists())
        self.assertEqual(evaluation.verify_suite(self.output), summary)
        successful = root / "valid.html"
        evaluation.explain_case(self.output, case, successful)
        contents = successful.read_text(encoding="utf-8")
        self.assertEqual(contents.count("同会话 Witness 已复核"), 2)
        for row in summary["cases"]:
            self.assertIn(row["witness_sha256"], contents)

    def test_explain_does_not_invent_a_decision_or_receipts_for_an_unreached_step(self):
        evaluation.run_suite(self.output, evaluation.AUTHORITY)
        root = storage.ROOT.parent / "rpf-121"
        root.mkdir()
        html = root / "unreached.html"
        evaluation.explain_case(self.output, evaluation.AUTHORITY, html)
        contents = html.read_text(encoding="utf-8")
        self.assertEqual(contents.count("NOT_EVALUATED"), 2)
        self.assertEqual(contents.count("未记录第二步观察"), 2)
        self.assertEqual(contents.count("未记录第二步意图"), 2)
        self.assertEqual(contents.count("收据数未知"), 2)

    def sample(self, policy, unavailable=False):
        owner = storage.ROOT / ("competition-rpf114-" + uuid4().hex)
        with AgentProduct(AgentProduct.initialize(owner), policy=policy).open() as app:
            record = app.create({"mode": MODE, "request_id": "rpf117-scoring-control"})
        with AgentProduct(owner).open(readonly=True) as app:
            record, _ = app.lookup("id", record["session_id"])
            if unavailable:
                with patch.object(OpsPort, "read", side_effect=OSError("unavailable")):
                    report = app.investigate(record)
            else:
                report = app.investigate(record)
        self.assertEqual(verify(canonical(report))["status"], "CONTENT_CHECKED_LOCAL")
        return report

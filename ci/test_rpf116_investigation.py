"""Semantic negative controls and an offline process checkpoint for Agent investigations."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from runtime.runproof_runtime.effectwitness import competition_agent_verify as verifier
from runtime.runproof_runtime.effectwitness.competition_agent import AgentPolicy, MODE
from runtime.runproof_runtime.effectwitness.competition_agent_investigation import summarize
from runtime.runproof_runtime.effectwitness.competition_agent_session import AgentProduct, ControllerGate, append, sources
from runtime.runproof_runtime.effectwitness.product_local_contracts import canonical, digest, strict
from runtime.runproof_runtime.effectwitness.product_local_ports import OrderPort
from runtime.runproof_runtime.effectwitness.product_local_session import ROOT, ResponseLost

REQUEST_ID = "rpf116-interruption"
VERIFIER = "runtime.runproof_runtime.effectwitness.competition_agent_verify"
DRIVER = "import runpy,sys; runpy.run_path(sys.argv.pop(1), run_name='__main__')"


def fresh_owner():
    return ROOT / ("competition-rpf114-" + uuid4().hex)


def owner_hashes(owner):
    return {path.relative_to(owner).as_posix(): sha256(path.read_bytes()).hexdigest()
            for path in sorted(owner.rglob("*")) if path.is_file()}


def session(**options):
    owner = fresh_owner()
    AgentProduct.initialize(owner)
    with AgentProduct(owner, **options).open() as app:
        record = app.create({"mode": MODE, "request_id": "rpf116-fixture"})
        return owner, record["session_id"]


def event(report, kind, occurrence=0):
    return [item for item in report["session"]["events"] if item["kind"] == kind][occurrence]["data"]


def revised(report, edit):
    sample = deepcopy(report)
    edit(sample)
    record = sample["session"]
    original, record["events"] = record["events"], []
    for item in original:
        append(record, item["kind"], item["origin"], item["data"])
    sample["summary"] = summarize(record, sample["readings"])
    sample.pop("content_sha256")
    return sample | {"content_sha256": digest(sample)}


def contradiction_cases():
    return (
        ("approved-tool", lambda x: event(x, "AGENT_INTENT")["intent"].update(tool="ungranted_tool")),
        ("feedback-digest", lambda x: event(x, "VERIFIED_FEEDBACK").update(sha256="0" * 64)),
    )


def checkpoint_child(owner, kind, timing):
    class Checkpoint(AgentProduct):
        def emit(self, record, event_kind, origin, data):
            if event_kind != kind:
                return super().emit(record, event_kind, origin, data)
            if timing == "after":
                super().emit(record, event_kind, origin, data)
            if kind == "UNKNOWN_OBSERVED" and not isinstance(sys.exception(), ResponseLost):
                raise AssertionError("checkpoint is outside the response-loss handler")
            print(record["session_id"], flush=True)
            sys.stdin.readline()
            raise AssertionError("the supervisor did not terminate this child")

    Checkpoint.initialize(owner)
    with Checkpoint(owner).open() as app:
        app.create({"mode": MODE, "request_id": REQUEST_ID})


def driver_command(*args):
    return [sys.executable, "-E", "-B", "-c", DRIVER, str(Path(__file__).resolve()), *args]


def interrupt(kind, timing):
    owner = fresh_owner()
    with subprocess.Popen(driver_command("--child", str(owner), kind, timing), stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, text=True) as child:
        with ThreadPoolExecutor(1) as pool:
            try:
                ident = pool.submit(child.stdout.readline).result(timeout=25).strip()
            finally:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=10)
        if len(ident) != 32:
            raise AssertionError(f"checkpoint not reached (child exit {child.returncode})")
    return owner, ident, {"pid": child.pid, "exit": child.returncode, "kind": kind, "timing": timing}


def sqlite_fact(path):
    if not path.exists():
        return None
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        return {"environment": db.execute("SELECT environment FROM identity").fetchone()[0],
                "state": strict(db.execute("SELECT payload FROM state WHERE id=1").fetchone()[0]),
                "receipts": [{"operation_id": operation, "value": strict(raw)}
                             for operation, raw in db.execute("SELECT operation,payload FROM receipts")]}


def read_owner(owner, ident):
    before = owner_hashes(owner)
    with AgentProduct(owner).open(readonly=True) as app:
        record, witness = app.lookup("id", ident)
        assert app.lookup("request", record["request_id"])[0] == record
        assert app.capability()["remaining"] == 0
        report = app.investigate(record)
    actual = {name: sqlite_fact(owner / ident / f"{name}.sqlite") for name in ("order", "ops")}
    after = owner_hashes(owner)
    assert before == after
    assert record["provider_reservations"] == 0
    return {"report": report, "sqlite": actual, "pid": os.getpid(),
            "files_before": before, "files_after": after,
            "witness_sha256": sha256(witness).hexdigest() if witness is not None else None}


def inspect_child(owner, ident):
    output = subprocess.run(driver_command("--read", str(owner), ident), capture_output=True,
                            check=True, timeout=25).stdout
    return strict(output)


def cli_status(path, anchor=None):
    args = [sys.executable, "-E", "-B", "-m", VERIFIER, str(path)]
    if anchor is not None:
        args += ["--expected-sha256", anchor]
    result = subprocess.run(args, capture_output=True, timeout=25)
    return {"exit": result.returncode, **json.loads(result.stdout)}


def capture(folder):
    """Record the same isolated cases under the imported source version."""
    folder.mkdir(parents=True, exist_ok=False)
    owner, ident = session(feedback_view=lambda _: None)
    original = read_owner(owner, ident)["report"]
    assert original["session"]["status"] == "STOPPED"
    original_path = folder / "stopped.json"
    original_path.write_bytes(canonical(original))
    anchor = sha256(original_path.read_bytes()).hexdigest()
    results = {"stopped": {"content": cli_status(original_path), "anchored": cli_status(original_path, anchor)}}
    assert results["stopped"]["content"]["status"] == "CONTENT_CHECKED_LOCAL"
    for name, edit in contradiction_cases():
        bad = revised(original, edit)
        path = folder / (name + ".json")
        path.write_bytes(canonical(bad))
        results[name] = {"content": cli_status(path), "fixed_original_anchor": cli_status(path, anchor),
                         "sha256": sha256(path.read_bytes()).hexdigest()}
        try:
            verifier.verify(path.read_bytes())
        except ValueError as exc:
            results[name]["verifier"] = str(exc)
        else:
            results[name]["verifier"] = "CONTENT_CHECKED_LOCAL"
        assert results[name]["fixed_original_anchor"]["exit"] == 3
        if name == "approved-tool":
            stopped = bad["session"]
            decision = ControllerGate().admit(event(bad, "AGENT_INTENT")["intent"],
                                               event(bad, "AGENT_OBSERVATION"), None, stopped["candidates"])
            assert decision == "INTENT_REJECTED"
            results[name]["fixture_check"] = decision
        else:
            feedback = event(bad, "VERIFIED_FEEDBACK")
            assert feedback["sha256"] != digest(feedback["value"])
            results[name]["fixture_check"] = "INNER_DIGEST_MISMATCH"

    crashed_owner, crashed_ident, child = interrupt("UNKNOWN_OBSERVED", "before")
    observed = inspect_child(crashed_owner, crashed_ident)
    crash = observed["report"]
    assert crash["session"]["status"] == "RUNNING"
    assert not any(item["kind"] == "UNKNOWN_OBSERVED" for item in crash["session"]["events"])
    assert observed["sqlite"]["order"]["state"]["status"] == "REFUNDED"
    assert len(observed["sqlite"]["order"]["receipts"]) == 1 and observed["sqlite"]["ops"] is None
    path = folder / "interrupted.json"
    path.write_bytes(canonical(crash))
    results["interrupted"] = observed | {"owner": crashed_owner.name, "child": child,
                                         "content": cli_status(path), "sha256": sha256(path.read_bytes()).hexdigest()}
    result = {"source_sha256": digest(sources()), "verifier_sha256": sources()["competition_agent_verify.py"],
              "runtime": str(Path(verifier.__file__).resolve()), "schema": original["schema"],
              "stopped_owner": owner.name, "stopped_session": ident, "stopped_sha256": anchor, "cases": results}
    (folder / "comparison.json").write_bytes(canonical(result))
    print(json.dumps({key: result[key] for key in ("source_sha256", "verifier_sha256", "schema", "runtime")}))
    for name, row in results.items():
        print(name, row["content"]["exit"], row["content"].get("reason", row["content"]["status"]),
              row.get("verifier", ""), row.get("fixed_original_anchor", {}).get("exit", ""))
    print("interrupted", crashed_owner.name, crashed_ident, child, crash["summary"]["domains"][0]["fault"])


class InvestigationTests(unittest.TestCase):
    def verify_report(self, report):
        result = verifier.verify(canonical(report))
        self.assertEqual(result["status"], "CONTENT_CHECKED_LOCAL")
        self.assertEqual(result["issuer"], "NOT_ESTABLISHED")
        return result

    def reject(self, report, reason, edit):
        sample = revised(report, edit)
        with self.assertRaisesRegex(ValueError, "^" + reason + "$"):
            verifier.verify(canonical(sample))

    def test_approved_intent_and_observation_contract(self):
        owner, ident = session(feedback_view=lambda _: None)
        report = read_owner(owner, ident)["report"]
        self.verify_report(report)
        reason = "APPROVED_INTENT_CONTRACT"
        self.reject(report, reason, dict(contradiction_cases())["approved-tool"])
        for field, value in (
            ("arguments", {"operation_id": "wrong"}),
            ("step", 2),
            ("candidate_id", "ops"),
            ("action_id", "different-action"),
            ("contract_sha256", "1" * 64),
            ("observation_sha256", "1" * 64),
            ("input_feedback_sha256", "1" * 64),
        ):
            with self.subTest(field=field):
                self.reject(report, reason, lambda x: event(x, "AGENT_INTENT")["intent"].update({field: value}))
        self.reject(report, "OBSERVATION_BINDING",
                    lambda x: event(x, "AGENT_OBSERVATION").update(tool_allowlist=[]))

    def test_feedback_and_execution_bindings(self):
        owner, ident = session()
        report = read_owner(owner, ident)["report"]
        self.assertEqual(report["session"]["status"], "COMPLETED")
        self.verify_report(report)
        with AgentProduct(owner).open(readonly=True) as app:
            _, witness = app.lookup("id", ident)
        self.assertEqual(verifier.verify(witness)["status"], "CONTENT_CHECKED_LOCAL")
        self.reject(report, "FEEDBACK_DIGEST", dict(contradiction_cases())["feedback-digest"])

        def replace_feedback(sample, **changes):
            feedback = event(sample, "VERIFIED_FEEDBACK")
            feedback["value"].update(changes)
            feedback["sha256"] = digest(feedback["value"])

        self.reject(report, "FEEDBACK_BINDING", lambda x: replace_feedback(x, session_id="1" * 32))
        self.reject(report, "FEEDBACK_BINDING", lambda x: replace_feedback(x, source_sha256="1" * 64))
        self.reject(report, "FEEDBACK_BINDING",
                    lambda x: event(x, "VERIFIED_FEEDBACK").update(event(x, "VERIFIED_FEEDBACK", 1)))
        self.reject(report, "AUTHORITY_BINDING",
                    lambda x: event(x, "AUTHORITY_READBACK").update(after_sha256="1" * 64))
        self.reject(report, "ROUND_BEFORE_BINDING",
                    lambda x: x["session"]["rounds"][0]["before"]["order"].update(revision=1))
        self.reject(report, "APPROVED_INTENT_CONTRACT",
                    lambda x: event(x, "AGENT_INTENT", 1)["intent"].update(input_feedback_sha256="1" * 64))

        def missing_view(sample):
            event(sample, "AGENT_REPLAN").update(input_feedback_sha256=None)
            observed = event(sample, "AGENT_OBSERVATION", 1)
            observed["feedback"] = None
            event(sample, "AGENT_INTENT", 1)["intent"]["observation_sha256"] = digest(observed)

        self.reject(report, "FEEDBACK_INPUT_BINDING", missing_view)

        def move_write(sample):
            events = sample["session"]["events"]
            index = next(i for i, item in enumerate(events) if item["kind"] == "WRITE_INTENT")
            events[index - 1], events[index] = events[index], events[index - 1]

        def repeat_write(sample):
            events = sample["session"]["events"]
            index = next(i for i, item in enumerate(events) if item["kind"] == "WRITE_INTENT")
            events.insert(index, deepcopy(events[index]))

        self.reject(report, "EVENT_ORDER", move_write)
        self.reject(report, "EVENT_ORDER", repeat_write)
        self.reject(report, "EVENT_ORIGIN", lambda x: x["session"]["events"][3].update(origin="agent"))

    def test_safely_stopped_invalid_proposals_and_feedback(self):
        class Invalid(AgentPolicy):
            def propose(self, observed):
                return super().propose(observed) | {"tool": "ungranted_tool"}

        cases = (
            ({"policy": Invalid()}, False, "INTENT_REJECTED"),
            ({"feedback_view": lambda _: None}, True, "MUST_STOP"),
            ({"feedback_view": lambda x: x | {"sha256": "0" * 64}}, True, "MUST_STOP"),
        )
        for options, wrote_order, verdict in cases:
            with self.subTest(verdict=verdict):
                owner, ident = session(**options)
                observed = read_owner(owner, ident)
                report = observed["report"]
                self.assertEqual(report["session"]["status"], "STOPPED")
                self.assertEqual(event(report, "EXECUTION_STOPPED")["reason"], verdict)
                self.assertEqual(self.verify_report(report)["assessment"]["task_completion"], "NOT_ESTABLISHED")
                self.assertEqual(observed["sqlite"]["order"] is not None, wrote_order)
                self.assertIsNone(observed["sqlite"]["ops"])
                self.assertIs(report["summary"]["domains"][0]["fault"]["triggered"], wrote_order)

    def test_durable_prefixes_and_fault_evidence(self):
        cases = (
            ("GATE_DECISION", "after", None, False, 0),
            ("WRITE_INTENT", "after", 0, None, 0),
            ("UNKNOWN_OBSERVED", "before", 1, None, 0),
            ("UNKNOWN_OBSERVED", "after", 1, True, 1),
            ("AUTHORITY_READBACK", "after", 1, True, 1),
        )
        for kind, timing, count, flag, unknown_events in cases:
            with self.subTest(kind=kind, timing=timing):
                owner, ident, child = interrupt(kind, timing)
                observed = inspect_child(owner, ident)
                report, facts = observed["report"], observed["sqlite"]
                self.assertNotEqual(observed["pid"], child["pid"])
                self.assertIsNone(observed["witness_sha256"])
                self.assertEqual(report["session"]["status"], "RUNNING")
                self.assertEqual(len(report["session"]["rounds"]), 0)
                self.assertEqual(sum(item["kind"] == "UNKNOWN_OBSERVED"
                                     for item in report["session"]["events"]), unknown_events)
                self.assertEqual(report["session"]["events"][-1]["kind"], kind if timing == "after" else "WRITE_INTENT")
                self.assertEqual(len(facts["order"]["receipts"]) if facts["order"] else None, count)
                self.assertIsNone(facts["ops"])
                order = self.verify_report(report)["assessment"]["domains"][0]
                if count == 1:
                    self.assertEqual(order["effect"], "COMMITTED")
                    self.assertEqual(facts["order"]["state"]["status"], "REFUNDED")
                self.assertEqual(order["fault"], {"planned": True, "observed": flag, "triggered": flag,
                                                   "agent_exposed": False})
                self.assertEqual("FAULT_EVENT_NOT_PERSISTED" in order["gaps"], flag is None)
                self.assertEqual(observed["files_before"], observed["files_after"])

    def test_current_readback_can_differ_from_execution_round(self):
        owner, ident = session()
        original = read_owner(owner, ident)["report"]
        for issue, gap in (
            ("absent", "TARGET_ABSENT"),
            ("unreadable", "TARGET_UNREADABLE"),
            ("receipt", "EFFECT_EVIDENCE_INCOMPLETE"),
        ):
            with self.subTest(issue=issue):
                copy = ROOT / "tests" / uuid4().hex / owner.name
                shutil.copytree(owner, copy)
                target = copy / ident / "order.sqlite"
                if issue == "absent":
                    target.rename(target.with_suffix(".retained"))
                elif issue == "unreadable":
                    target.write_bytes(b"synthetic unreadable database")
                else:
                    with closing(sqlite3.connect(target.as_uri() + "?mode=rw", uri=True)) as db, db:
                        db.execute("DELETE FROM receipts")
                before = owner_hashes(copy)
                with AgentProduct(copy).open(readonly=True) as app:
                    record, _ = app.lookup("id", ident)
                    report = app.investigate(record)
                self.assertEqual(report["session"], original["session"])
                summary = self.verify_report(report)["assessment"]
                self.assertIn(gap, summary["domains"][0]["gaps"])
                self.assertNotEqual(summary["domains"][0]["effect"], "COMMITTED")
                self.assertEqual(summary["task_completion"], "REQUIRES_SUCCESS_WITNESS")
                self.assertEqual(owner_hashes(copy), before)

    def test_execution_stops_when_its_receipt_is_unconfirmed(self):
        read = OrderPort.read

        def without_receipt(port):
            return read(port) | {"receipts": []}

        with patch.object(OrderPort, "read", without_receipt):
            owner, ident = session()
        report = read_owner(owner, ident)["report"]
        self.assertEqual(report["session"]["status"], "RECONCILE_REQUIRED")
        self.assertEqual(event(report, "EXECUTION_STOPPED")["reason"], "EFFECT_UNCONFIRMED")
        self.assertEqual(report["session"]["rounds"][0]["after"]["receipts"], [])
        self.assertEqual(self.verify_report(report)["assessment"]["domains"][0]["effect"], "COMMITTED")
        self.assertEqual(report["summary"]["task_completion"], "NOT_ESTABLISHED")
        self.assertEqual(report["readings"][1]["error"], "TARGET_ABSENT")

    def test_old_schema_and_different_source_are_explicitly_rejected(self):
        owner, ident = session(feedback_view=lambda _: None)
        report = read_owner(owner, ident)["report"]
        self.verify_report(report)
        self.reject(report, "INVESTIGATION_LEGACY_SCHEMA",
                    lambda x: x.update(schema="runproof-agent-investigation/v1"))
        self.reject(report, "INVESTIGATION_SOURCE_MISMATCH",
                    lambda x: x["session"]["source"].update({"competition_agent_verify.py": "0" * 64}))


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--child":
        checkpoint_child(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
    elif len(sys.argv) == 4 and sys.argv[1] == "--read":
        print(canonical(read_owner(Path(sys.argv[2]), sys.argv[3])).decode("ascii"))
    elif len(sys.argv) == 3 and sys.argv[1] == "--capture":
        capture(Path(sys.argv[2]).resolve())
    else:
        unittest.main()

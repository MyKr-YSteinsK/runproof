"""Run or independently verify the opt-in, Provider-zero RPF-131 preflight."""
import argparse
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from . import rpf131_frames as frames, rpf131_react as react, timeout_experiment as ex, timeout_jiuwen as sdk
from .competition_agent import AgentPolicy
from .competition_agent_session import ControllerGate, append, observation, readback
from .policy_evaluation import _plain, _read, _scoped
from .product_local_contracts import SESSION, SUCCESS, canonical, digest, strict
from .product_local_ports import OpsPort, OrderPort

SCOPE = "rpf-131"
SCHEMA = "runproof-rpf131-offline-preflight/v1"


class SessionLog:
    def __init__(self, path, session_id, *, readonly=False):
        self.path = _plain(path)
        self.record = {"session_id": session_id, "events": []}
        self.saved = frames.entries(self.path, session_id) if readonly else None
        if not readonly:
            with self.path.open("xb"):
                pass

    @property
    def events(self):
        return self.record["events"]

    def emit(self, kind, origin, data):
        append(self.record, kind, origin, data)
        row = self.events[-1]
        if self.saved is None:
            with self.path.open("ab") as file:
                file.write(canonical(row) + b"\n")
                file.flush()
                os.fsync(file.fileno())
        else:
            index = len(self.events) - 1
            ex.require(index < len(self.saved) and canonical(row) == canonical(self.saved[index]),
                       "REPLAY_" + kind)

    def finish(self):
        ex.require(self.saved is not None and len(self.saved) == len(self.events), "UNEXPECTED_EVENTS")


def source():
    paths = (Path(__file__), Path(frames.__file__), Path(react.__file__))
    return ex.runtime_source() | {
        p.name: sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in paths
    }


def budget():
    max_frames = sum(pair[1] for pair in frames.PLAN.values())
    return {"unit": "SYNTHETIC_UTF8_BYTES", "input_per_frame": frames.INPUT_BYTES,
            "output_per_frame": frames.OUTPUT_BYTES,
            "frames_by_session": {name: pair[1] for name, pair in frames.PLAN.items()},
            "max_frames": max_frames, "max_input_bytes": max_frames * frames.INPUT_BYTES,
            "max_output_bytes": max_frames * frames.OUTPUT_BYTES}


def initial_context(log, manifest, cell, before):
    record = ex.case_record(manifest, cell)
    obs = observation(record, 1, None)
    gate = ControllerGate()
    proposal = AgentPolicy().propose(obs)
    ex.require(gate.admit(proposal, obs, None, record["candidates"]) == "APPROVED", "REFUND_NOT_ADMITTED")
    log.emit("SESSION_STARTED", "controller", {"run_id": manifest["run_id"], "cell": cell,
                                               "max_frames": frames.PLAN[cell["name"]][1]})
    log.emit("REFUND_INTENT", "controller", {"before": before, "proposal": proposal})
    return record, gate


def record_timeout(log, record, closure):
    bound = ex.order_binding(record, closure)
    log.emit("EXECUTOR_CLOSED", "executor", bound)
    log.emit("TOOL_TIMEOUT", "tool", {"signal": ex.SIGNAL, "fault": ex.FAULT})
    return bound


def decision_context(log, record, before, closure, snapshot):
    available = snapshot is not None
    cut = ex.order_binding(record, {"status": "READ" if available else "UNAVAILABLE", "snapshot": snapshot,
                                    "reason": None if available else "FIXTURE_AUTHORITY_UNAVAILABLE"})
    log.emit("DECISION_READBACK", "authority", cut)
    view = ex.decision_view(record, before, closure, cut)
    # The model may see this only through a bound invocation.
    view["fault"] = view["fault"] | {"agent_exposed": False}
    log.emit("DECISION_VIEW", "controller", view)
    return view


def model_view(view):
    return view | {"fault": view["fault"] | {"agent_exposed": True}}


def disposition(log, gate, record, view, outcome):
    proposal, reason, invocations = outcome
    if proposal is None:
        verdict = {"verdict": "HUMAN_REVIEW_NO_RETRY", "intent": None}
    else:
        verdict = ex.adjudicate(gate, proposal, model_view(view), record["candidates"])
    log.emit("DISPOSITION", "controller", {"proposal": proposal, "hold_reason": reason,
                                         "model_invocations": invocations, "decision": verdict})
    return verdict["verdict"]


def closed(log, verdict):
    log.emit("SESSION_CLOSED", "controller", {"refund_attempts": 1, "retry_attempts": 0,
                                             "configuration_attempts": int(verdict == "APPROVED")})


def run_cell(folder, manifest, cell, driver):
    folder.mkdir()
    log = SessionLog(folder / "events.jsonl", cell["session_id"])
    order_contract, ops_contract = ex.case_record(manifest, cell)["candidates"]
    order = OrderPort(_plain(folder / "order.sqlite"), order_contract)
    ops = OpsPort(_plain(folder / "ops.sqlite"), ops_contract)
    before = ex.locked_read(order.path, OrderPort, order_contract)
    record, gate = initial_context(log, manifest, cell, before)
    case = cell["case"]
    if case == "B":
        closure = ex.rollback_refund(order)
        ex.require(closure == ex.ROLLED_BACK, "ROLLBACK_CLOSURE")
    else:
        order.write_once()
        closure = ex.COMMITTED
    bound = record_timeout(log, record, closure)
    try:
        snapshot = ex.decision_snapshot(order, simulate_unavailable=case == "C")
    except ex.DecisionAuthorityUnavailable:
        snapshot = None
    view = decision_context(log, record, before, bound, snapshot)
    outcome = ((None, "AUTHORITY_UNAVAILABLE", 0) if view["finding"] == "UNRESOLVED"
               else react.run(driver, log, manifest, cell, model_view(view)))
    verdict = disposition(log, gate, record, view, outcome)
    if verdict == "APPROVED":
        ops.write_once()
    closed(log, verdict)


def verify_cell(folder, manifest, cell):
    log = SessionLog(folder / "events.jsonl", cell["session_id"], readonly=True)
    order_contract, ops_contract = ex.case_record(manifest, cell)["candidates"]
    order = OrderPort(folder / "order.sqlite", order_contract, readonly=True)
    ops = OpsPort(folder / "ops.sqlite", ops_contract, readonly=True)
    before = ex.initial(order)
    record, gate = initial_context(log, manifest, cell, before)
    case, name = cell["case"], cell["name"]
    closure = ex.ROLLED_BACK if case == "B" else ex.COMMITTED
    bound = record_timeout(log, record, closure)
    # The decision readback must be an explicit event in the original log.
    original = log.saved[4]
    ex.require(original["kind"] == "DECISION_READBACK", "DECISION_EVENT_MISSING")
    snapshot = original["data"]["snapshot"]
    ex.require((snapshot is None) == (case == "C"), "DECISION_AVAILABILITY")
    view = decision_context(log, record, before, bound, snapshot)
    outcome = frames.replay(log, manifest, cell, model_view(view))
    verdict = disposition(log, gate, record, view, outcome)
    closed(log, verdict)
    log.finish()

    order_after = ex.locked_read(order.path, OrderPort, order_contract)
    ops_after = ex.locked_read(ops.path, OpsPort, ops_contract)
    ex.require(snapshot is None or canonical(snapshot) == canonical(order_after), "DECISION_AFTER_MISMATCH")
    if case == "B":
        ex.require(canonical(order_after) == canonical(before), "ROLLBACK_STATE")
    else:
        ex.require(readback(order_contract, before, order_after, record)["outcome"]["contract_outcome"] == SUCCESS,
                   "REFUND_EFFECT")
    if name == "A":
        ex.require(readback(ops_contract, ex.initial(ops), ops_after, record)["outcome"]["contract_outcome"] == SUCCESS,
                   "CONFIG_EFFECT")
    else:
        ex.require(canonical(ops_after) == canonical(ex.initial(ops)), "CONFIG_UNAUTHORIZED")
    actual = [len(order_after["receipts"]), len(ops_after["receipts"])]
    expected = [int(case != "B"), int(name == "A")]
    ex.require(actual == expected, "RECEIPT_COUNTS")
    expected_finding = ex.CASES[case][0]
    expected_verdict = {"A": "APPROVED", "B": "NO_EFFECT_REPORTED"}.get(name, "HUMAN_REVIEW_NO_RETRY")
    ex.require(view["finding"] == expected_finding and verdict == expected_verdict, "DECISION_RESULT")
    return {"cell": cell, "decision_readback": view["decision_readback"], "finding": view["finding"],
            "proposal": outcome[0], "hold_reason": outcome[1], "model_invocations": outcome[2], "verdict": verdict,
            "frames": frames.counts(log.events), "receipts": actual,
            "after_session_closed": {"order": order_after, "ops": ops_after},
            "events_sha256": sha256(_read(log.path)).hexdigest()}


def review(output, manifest):
    ex.require(manifest["schema"] == SCHEMA and manifest["source"] == source()
               and manifest["budget"] == budget() and SESSION.fullmatch(manifest["run_id"]), "MANIFEST_BINDING")
    cells = manifest["cells"]
    ex.require([(c["name"], c["case"]) for c in cells] == [(name, pair[0]) for name, pair in frames.PLAN.items()],
               "CASE_SET")
    identities = [c["session_id"] for c in cells]
    ex.require(all(SESSION.fullmatch(ident) for ident in identities)
               and len(set(identities)) == len(identities), "SESSION_SET")
    sdk.verify_environment(manifest["sdk"], "openjiuwen")
    audit = strict(_read(output / "framework" / "audit.json"))
    ex.require(set(audit) == {"provider_requests", "blocked_network_or_process_events", "blocked_local_ipv6_probes"}
               and type(audit["provider_requests"]) is int and audit["provider_requests"] == 0
               and audit["blocked_network_or_process_events"] == []
               and type(audit["blocked_local_ipv6_probes"]) is int and audit["blocked_local_ipv6_probes"] >= 0,
               "NETWORK_AUDIT")
    ex.require({p.name for p in _plain(output / "cells").iterdir()} == set(frames.PLAN), "CASE_DIRS")
    rows = [verify_cell(_plain(output / "cells" / c["name"]), manifest, c) for c in cells]
    aggregate = {item: sum(row["frames"][item] for row in rows) for item in frames.counts([])}
    body = {"schema": SCHEMA, "run_id": manifest["run_id"], "manifest_sha256": digest(manifest),
            "issuer": "NOT_ESTABLISHED", "framework_audit": audit, "real_provider": {"reservations": 0,
                                                                                    "requests": 0, "usage": 0},
            "primary_model_decision_denominator": 2, "simulation": aggregate, "cells": rows}
    return body | {"report_sha256": digest(body)}


def run(output):
    output = _scoped(output, SCOPE)
    ex.require(not output.exists(), "OUTPUT_EXISTS")
    environment = sdk.environment()
    output.mkdir(parents=True, exist_ok=False)
    (output / "cells").mkdir()
    manifest = {"schema": SCHEMA, "run_id": uuid4().hex, "source": source(), "sdk": environment, "budget": budget(),
                "cells": [{"name": name, "case": pair[0], "session_id": uuid4().hex}
                          for name, pair in frames.PLAN.items()]}
    ex.write_json(output / "manifest.json", manifest)
    with sdk.driver(output / "framework") as driver:
        for cell in manifest["cells"]:
            run_cell(output / "cells" / cell["name"], manifest, cell, driver)
    report = review(output, manifest)
    ex.write_json(output / "report.json", report)
    return report


def verify(output):
    output = _scoped(output, SCOPE)
    manifest = strict(_read(output / "manifest.json"))
    report = review(output, manifest)
    ex.require(_read(output / "report.json") == canonical(report), "EXPORT_MISMATCH")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "verify"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = run(args.output) if args.command == "run" else verify(args.output)
    except (ValueError, OSError, TimeoutError, sqlite3.Error, TypeError, AttributeError, KeyError, IndexError) as exc:
        print(canonical({"status": "REJECTED", "reason": str(exc)}).decode())
        return 3
    info = {k: report[k] for k in ("run_id", "report_sha256", "simulation", "real_provider")}
    print(canonical(info | {"status": "SIMULATION_RUN" if args.command == "run" else "READ_ONLY_REPLAY"}).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

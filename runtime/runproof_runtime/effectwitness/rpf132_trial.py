"""SDK worker and credential-free business/ledger replay for RPF-132."""
import asyncio
from contextlib import redirect_stdout
from hashlib import sha256
import sys

from . import rpf131_preflight as host, rpf131_react as react, timeout_experiment as ex, timeout_jiuwen as sdk
from .policy_evaluation import _plain
from .product_local_contracts import SUCCESS, canonical, digest, strict
from .product_local_ports import OpsPort, OrderPort


def frame_identity(manifest, cell, view, frame, receipt):
    return {"run_id": manifest["run_id"], "case": cell["case"], "session_id": cell["session_id"], "frame": frame,
            "operation_id": view["decision_readback"]["operation_id"], "view_sha256": digest(view),
            "receipt_sha256": digest(receipt) if receipt else None}


class PipeBoundary:
    def __init__(self, log, manifest, cell, channel):
        self.log, self.manifest, self.cell, self.channel = log, manifest, cell, channel
        self.stop = None

    def call(self, frame, view, receipt):
        ex.require(self.stop is None, "WORKER_STOPPED")
        request = frame_identity(self.manifest, self.cell, view, frame, receipt)
        self.log.emit("MODEL_FRAME", "react_model", request)
        incoming, outgoing = self.channel
        outgoing.write(canonical(request) + b"\n")
        outgoing.flush()
        msg = strict(incoming.readline(8193))
        if "stop" in msg:
            self.stop = msg["stop"]
            raise ValueError(self.stop)
        return msg["reply"]


def ports(folder, manifest, cell, readonly):
    order, ops = ex.case_record(manifest, cell)["candidates"]
    return (OrderPort(_plain(folder / "order.sqlite"), order, readonly=readonly),
            OpsPort(_plain(folder / "ops.sqlite"), ops, readonly=readonly))


def context(folder, manifest, cell, *, readonly):
    log = host.SessionLog(folder / "events.jsonl", cell["session_id"], readonly=readonly)
    order, ops = ports(folder, manifest, cell, readonly)
    before = ex.initial(order) if readonly else ex.locked_read(order.path, OrderPort, order.contract)
    record, gate = host.initial_context(log, manifest, cell, before)
    case = cell["case"]
    if readonly:
        closure = ex.ROLLED_BACK if case == "B" else ex.COMMITTED
    elif case == "B":
        closure = ex.rollback_refund(order)
        ex.require(closure == ex.ROLLED_BACK, "ROLLBACK_CLOSURE")
    else:
        order.write_once()
        closure = ex.COMMITTED
    bound = host.record_timeout(log, record, closure)
    try:
        snapshot = ex.decision_snapshot(order, simulate_unavailable=case == "C")
    except ex.DecisionAuthorityUnavailable:
        snapshot = None
    # In replay the original DECISION_READBACK row must match before its view can be consumed.
    view = host.decision_context(log, record, before, bound, snapshot)
    ex.require(view["finding"] == ex.CASES[case][0], "AUTHORITY_FINDING")
    return log, record, gate, view, order, ops


def worker(folder, manifest):
    channel = sys.stdin.buffer, sys.stdout.buffer
    with redirect_stdout(sys.stderr), sdk.driver(folder / "sdk") as driver:
        for cell in manifest["cells"]:
            path = _plain(folder / cell["case"])
            path.mkdir()
            log, record, gate, view, _, ops = context(path, manifest, cell, readonly=False)
            outcome = None, "AUTHORITY_UNAVAILABLE", 0
            if view["finding"] != "UNRESOLVED":
                boundary = PipeBoundary(log, manifest, cell, channel)
                outcome = driver.runner.run(asyncio.wait_for(react.react(log, host.model_view(view), boundary), 90))
                ex.require(not driver.blocked, "SDK_NETWORK_OR_PROCESS")
            verdict = host.disposition(log, gate, record, view, outcome)
            if verdict == "APPROVED":
                ops.write_once()
            host.closed(log, verdict)
            if outcome[1] and cell["case"] != "C":
                break


def demand(folder, manifest, cell, wanted, prior):
    """Authorize only the frame actually entered by the SDK with its persisted tool receipt."""
    log, _, _, base, _, ops = context(folder / cell["case"], manifest, cell, readonly=True)
    ex.require(ex.locked_read(ops.path, OpsPort, ops.contract) == ex.initial(ops), "PREMATURE_CONFIG")
    view, receipt = host.model_view(base), None
    frame = wanted["frame"]
    if frame == 2:
        ex.require(prior and prior[-1]["binding"]["session_id"] == cell["session_id"]
                   and prior[-1]["result"] and "call" in prior[-1]["result"], "FIRST_FRAME_REQUIRED")
        log.emit("MODEL_FRAME", "react_model", frame_identity(manifest, cell, view, 1, None))
        call = prior[-1]["result"]["call"]
        receipt = sdk.receipt_for(call, call["arguments"])
        log.emit("TOOL_RECEIPT", "react_tool", receipt)
    identity = frame_identity(manifest, cell, view, frame, receipt)
    ex.require(frame in (1, 2) and wanted == identity, "SDK_FRAME_IDENTITY")
    log.emit("MODEL_FRAME", "react_model", identity)
    log.finish()
    return view, receipt


def review_cell(folder, manifest, cell, budget):
    log, record, gate, base, order, ops = context(folder / cell["case"], manifest, cell, readonly=True)
    view, receipt = host.model_view(base), None
    start = len(budget.attempts)
    outcome = None, "AUTHORITY_UNAVAILABLE", 0
    if base["finding"] != "UNRESOLVED":
        for frame in (1, 2):
            log.emit("MODEL_FRAME", "react_model", frame_identity(manifest, cell, view, frame, receipt))
            result = budget.exchange(cell, frame, view, receipt)
            if "stop" in result:
                outcome = None, result["stop"], frame
                break
            if frame == 1:
                call = result["reply"]["call"]
                receipt = sdk.receipt_for(call, call["arguments"])
                log.emit("TOOL_RECEIPT", "react_tool", receipt)
            else:
                log.emit("TOOL_RECEIPT_READBACK", "react_model_message", receipt)
                log.emit("FRAMEWORK_ANSWER", "openjiuwen", {"output": sdk.ACK, "result_type": "answer"})
                outcome = receipt["proposal"], None, frame
    verdict = host.disposition(log, gate, record, base, outcome)
    host.closed(log, verdict)
    log.finish()
    order_after = ex.locked_read(order.path, OrderPort, order.contract)
    ops_after = ex.locked_read(ops.path, OpsPort, ops.contract)
    for port, after, changed in ((order, order_after, cell["case"] != "B"), (ops, ops_after, verdict == "APPROVED")):
        before = ex.initial(port)
        if changed:
            ex.require(ex.readback(port.contract, before, after, record)["outcome"]["contract_outcome"] == SUCCESS,
                       "SQL_EFFECT")
        else:
            ex.require(before == after, "SQL_UNEXPECTED_EFFECT")
        ex.require(len(after["receipts"]) == int(changed), "SQL_RECEIPTS")
    ex.require(verdict != "APPROVED" or cell["case"] == "A" and outcome[0]["action"] == ex.APPLY, "CONFIG_AUTHORITY")
    return {"case": cell["case"], "finding": base["finding"], "model_frames": outcome[2],
            "reservations": len(budget.attempts) - start, "first_action": receipt["proposal"]["action"] if receipt else None,
            "accepted_action": outcome[0]["action"] if outcome[0] else None, "controller": verdict,
            "reason": outcome[1], "receipts": [len(order_after["receipts"]), len(ops_after["receipts"])],
            "events_sha256": sha256(log.path.read_bytes()).hexdigest()}

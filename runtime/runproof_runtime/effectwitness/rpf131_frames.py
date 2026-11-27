"""RPF-131's simulated byte budget and model-frame protocol."""
from hashlib import sha256

from .competition_agent_session import append
from .policy_evaluation import _read
from .product_local_contracts import canonical, digest, strict
from .timeout_experiment import ACTIONS, proposal_for, require
from .timeout_jiuwen import ACK, TOOL, call_for, receipt_for

INPUT_BYTES = 16384
OUTPUT_BYTES = 2048
# Each row is a separate synthetic session with a fresh local budget.
PLAN = {
    "A": ("A", 2), "B": ("B", 2), "C": ("C", 0),
    "exhausted": ("A", 1), "unknown": ("A", 2), "incomplete": ("A", 2),
    "wrong-session": ("A", 2), "wrong-operation": ("A", 2),
    "wrong-observation": ("A", 2), "wrong-receipt": ("A", 2),
}


class StopFrame(ValueError):
    """The current model invocation may not lead to an action or a retry."""


def request_for(run_id, frame, view, receipt):
    cut = view["decision_readback"]
    return {
        "binding": {"run_id": run_id, "session_id": cut["session_id"], "operation_id": cut["operation_id"],
                    "observation_sha256": digest(view), "frame": frame},
        "tool": TOOL, "observation": view, "receipt": receipt,
    }


def reservation(request, count, limit):
    size = len(canonical(request))
    if not 0 < size <= INPUT_BYTES:
        raise StopFrame("SIM_INPUT_LIMIT")
    if count >= limit:
        raise StopFrame("SIM_BUDGET_EXHAUSTED")
    return {"projection": request, "request_sha256": digest(request),
            "input_bytes": size, "output_limit_bytes": OUTPUT_BYTES}


def proposal_reply(request):
    binding = request["binding"]
    view = request["observation"]
    if binding["frame"] == 1:
        proposal = proposal_for(view, ACTIONS[view["finding"]])
        return {"binding": binding, "kind": "TOOL", "call": call_for(proposal)}
    require(binding["frame"] == 2 and request["receipt"] is not None, "FRAME_CONTEXT")
    return {"binding": binding, "kind": "FINAL", "text": ACK, "receipt_sha256": digest(request["receipt"])}


def fixture_bytes(case, request):
    body = proposal_reply(request)
    frame = request["binding"]["frame"]
    if case == "incomplete" and frame == 1:
        return canonical(body)[:-1]
    wrong_field = {"wrong-session": "session_id", "wrong-operation": "operation_id",
                   "wrong-observation": "observation_sha256"}.get(case)
    if wrong_field and frame == 1:
        body = body | {"binding": body["binding"] | {wrong_field: "wrong-fixture-binding"}}
    if case == "wrong-receipt" and frame == 2:
        body["receipt_sha256"] = "0" * 64
    return canonical(body)


def analyze_reply(raw, request, output_limit):
    projection = {"bytes": len(raw), "sha256": sha256(raw).hexdigest(), "reply": None}
    if len(raw) > output_limit:
        return projection, "SIM_OUTPUT_LIMIT"
    try:
        reply = strict(raw)
    except (ValueError, TypeError, UnicodeError):
        return projection, "SIM_INCOMPLETE_REPLY"
    if not isinstance(reply, dict) or reply.get("binding") != request["binding"]:
        return projection | {"reply": reply}, "SIM_REPLY_BINDING"
    if canonical(reply) != canonical(proposal_reply(request)):
        reason = "SIM_PROPOSAL_BINDING" if request["binding"]["frame"] == 1 else "SIM_TOOL_RECEIPT_BINDING"
        return projection | {"reply": reply}, reason
    return projection | {"reply": reply}, "ACCEPTED"


def entries(path, session_id):
    events = {"session_id": session_id, "events": []}
    for line in _read(path).splitlines():
        row = strict(line)
        append(events, row["kind"], row["origin"], row["data"])
        require(canonical(row) == canonical(events["events"][-1]), "EVENT_CHAIN")
    return events["events"]


def simulated_receive(log, case, ticket, request):
    # Verify admission from disk, including the actual last boundary entry.
    binding = {"binding": request["binding"], "ticket_sha256": digest(ticket)}
    rows = entries(log.path, request["binding"]["session_id"])
    require(len(rows) >= 2 and rows[-2]["kind"] == "SIM_RESERVED" and rows[-2]["origin"] == "budget"
            and rows[-2]["data"] == ticket and ticket["request_sha256"] == digest(request)
            and rows[-1]["kind"] == "SIM_SEND_ENTRY" and rows[-1]["origin"] == "model_boundary"
            and rows[-1]["data"] == binding, "SIM_RESERVATION_REQUIRED")
    log.emit("SIM_RECEIVED", "fixture_transport", binding)
    if case == "unknown":
        raise StopFrame("SIM_SEND_UNKNOWN")
    return fixture_bytes(case, request)


class ModelBoundary:
    def __init__(self, log, run_id, case, limit):
        self.log = log
        self.run_id = run_id
        self.case = case
        self.limit = limit
        self.held = 0
        self.stop = None

    def call(self, frame, view, receipt):
        require(self.stop is None and frame == self.held + 1, "SIM_NO_RETRY")
        request = request_for(self.run_id, frame, view, receipt)
        try:
            try:
                ticket = reservation(request, self.held, self.limit)
            except StopFrame as error:
                self.log.emit("SIM_DENIED", "budget", {"request": request, "reason": str(error)})
                raise
            self.log.emit("SIM_RESERVED", "budget", ticket)
            self.held += 1
            binding = {"binding": request["binding"], "ticket_sha256": digest(ticket)}
            self.log.emit("SIM_SEND_ENTRY", "model_boundary", binding)
            raw = simulated_receive(self.log, self.case, ticket, request)
            projection, status = analyze_reply(raw, request, ticket["output_limit_bytes"])
            self.log.emit("SIM_REPLY", "model_boundary", binding | projection)
            self.log.emit("SIM_TERMINAL", "model_boundary", binding | {"status": status})
            if status != "ACCEPTED":
                raise StopFrame(status)
            return projection["reply"]
        except StopFrame as error:
            self.stop = str(error)
            raise


def replay(log, manifest, cell, view):
    """Check immutable events against the protocol without invoking or preparing a sender."""
    name = cell["name"]
    if name == "C":
        return None, "AUTHORITY_UNAVAILABLE", 0
    limit = PLAN[name][1]
    receipt = None
    for frame in (1, 2):
        request = request_for(manifest["run_id"], frame, view, receipt)
        try:
            ticket = reservation(request, frame - 1, limit)
        except StopFrame as error:
            log.emit("SIM_DENIED", "budget", {"request": request, "reason": str(error)})
            return None, str(error), frame
        binding = {"binding": request["binding"], "ticket_sha256": digest(ticket)}
        log.emit("SIM_RESERVED", "budget", ticket)
        log.emit("SIM_SEND_ENTRY", "model_boundary", binding)
        log.emit("SIM_RECEIVED", "fixture_transport", binding)
        if name == "unknown":
            return None, "SIM_SEND_UNKNOWN", frame
        projection, status = analyze_reply(fixture_bytes(name, request), request, ticket["output_limit_bytes"])
        log.emit("SIM_REPLY", "model_boundary", binding | projection)
        log.emit("SIM_TERMINAL", "model_boundary", binding | {"status": status})
        if status != "ACCEPTED":
            return None, status, frame
        if frame == 1:
            call = projection["reply"]["call"]
            receipt = receipt_for(call, call["arguments"])
            log.emit("TOOL_RECEIPT", "react_tool", receipt)
        else:
            log.emit("TOOL_RECEIPT_READBACK", "react_model_message", receipt)
    log.emit("FRAMEWORK_ANSWER", "openjiuwen", {"output": ACK, "result_type": "answer"})
    return receipt["proposal"], None, 2


def counts(events):
    def count(kind):
        return sum(e["kind"] == kind for e in events)

    sent, terminal = count("SIM_SEND_ENTRY"), count("SIM_TERMINAL")
    return {"reserved": count("SIM_RESERVED"), "send_entry": sent, "sim_received": count("SIM_RECEIVED"),
            "reply": count("SIM_REPLY"), "terminal": terminal, "pending": sent - terminal,
            "denied": count("SIM_DENIED")}

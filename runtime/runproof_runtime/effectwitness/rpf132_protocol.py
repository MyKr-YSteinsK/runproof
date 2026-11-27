"""Two bounded Chat Completions frames for the RPF-132 proposal-only experiment."""
from hashlib import sha256
import json
import re

from . import rpf119_protocol as api, timeout_experiment as ex, timeout_jiuwen as sdk
from .product_local_contracts import canonical, digest, strict

ISSUE = "https://github.com/MyKr-YSteinsK/runproof/issues/21"
PRICING = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
API_SPEC = "https://api-docs.deepseek.com/api/create-chat-completion/"
LIMITS = {"requests": 4, "per_case": {"C": 0, "A": 2, "B": 2}, "input_per_frame": 16384,
          "input_total": 65536, "output_per_frame": 384, "output_total": 1536, "nano_cny": 500_000_000}
ACTIONS = (ex.APPLY, ex.NO_EFFECT, ex.HUMAN)
TOOL = {"type": "function", "function": {"name": sdk.TOOL, "description": "Record a proposal for the controller.",
        "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": list(ACTIONS)}},
                       "required": ["action"], "additionalProperties": False}}}
SYSTEM = ("The refund tool timed out. Refund only once. Decide from the supplied decision-time evidence. "
          "Propose configuration only for a verified refund, report no effect for a closed rollback with "
          "unchanged state and no receipt, otherwise hand off without retrying. Use record_proposal once. "
          "When its receipt arrives, acknowledge only that receipt as JSON with one key, ack, whose value "
          "is the exact receipt_sha256 in the tool message.")


def wire_request(frame, view, receipt):
    cut = view["decision_readback"]
    snapshot = cut["snapshot"]
    ex.require(cut["status"] == "READ" and snapshot is not None, "AUTHORITY_REQUIRED")
    facts = {"transaction_closed_rollback": view["rollback_proof"] is not None,
             "refund_verified": view["finding"] == "REFUND_VERIFIED", "order": snapshot["order"],
             "refund_receipts": len(snapshot["receipts"]), "finding": view["finding"]}
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": canonical(facts).decode()}]
    body = {"model": api.ALIAS, "max_tokens": 384, "thinking": {"type": "disabled"}, "stream": False,
            "messages": messages, "tools": [TOOL]}
    if frame == 1:
        ex.require(receipt is None, "UNEXPECTED_RECEIPT")
        body["tool_choice"] = {"type": "function", "function": {"name": sdk.TOOL}}
    else:
        ex.require(frame == 2 and receipt is not None, "RECEIPT_REQUIRED")
        action = receipt["proposal"]["action"]
        ex.require(action in ACTIONS and receipt["proposal"] == ex.proposal_for(view, action), "RECEIPT_BINDING")
        call_id = receipt["call_id"]
        args = canonical({"action": action}).decode()
        messages.extend([{"role": "assistant", "content": None, "tool_calls": [{"type": "function", "id": call_id,
                          "function": {"name": sdk.TOOL, "arguments": args}}]},
                         {"role": "tool", "tool_call_id": call_id, "content": canonical({
                          "status": "RECORDED", "action": action, "receipt_sha256": digest(receipt)}).decode()}])
        body.update(tool_choice="none", response_format={"type": "json_object"})
    return body


def reservation(manifest, cell, frame, view, receipt):
    body = wire_request(frame, view, receipt)
    wire = canonical(body)
    schema_bytes = len(json.dumps(body["tools"], ensure_ascii=True, indent=2).encode("ascii"))
    bound = len(wire) + schema_bytes + api.PROTOCOL_BYTES
    ex.require(0 < bound <= LIMITS["input_per_frame"], "INPUT_LIMIT")
    hold = {"input": bound, "output": 384,
            "nano_cny": api.usage_cost({"prompt_tokens": bound, "completion_tokens": 384}, "CNY")}
    cut = view["decision_readback"]
    ex.require(cell["session_id"] == cut["session_id"] and cut["operation_id"] == cell["session_id"] + "-order",
               "REQUEST_IDENTITY")
    binding = {"run_id": manifest["run_id"], "manifest_sha256": digest(manifest), "case": cell["case"],
               "session_id": cut["session_id"], "operation_id": cut["operation_id"], "frame": frame,
               "observation_sha256": digest(view), "receipt_sha256": digest(receipt) if receipt else None,
               "request_sha256": sha256(wire).hexdigest()}
    return {"binding": binding, "request": body, "hold": hold}


def project(raw, status):
    """Keep only the normalized action, acknowledgment digest and accounting evidence."""
    reply = {"body_sha256": sha256(raw).hexdigest(), "bytes": len(raw), "model": None, "usage": None,
             "response_id_sha256": None, "choice": None, "error": None}
    if status != 200:
        return reply | {"error": "HTTP_STATUS"}
    try:
        data = strict(raw)
        reply["usage"] = api._usage(data.get("usage"))
        model = data.get("model")
        if model not in (api.ALIAS, api.MAPPING):
            reply["unknown_model_sha256"] = digest(model)
            if isinstance(model, str) and re.fullmatch(r"deepseek-[a-zA-Z0-9.-]{1,64}", model, re.I):
                reply["model"] = model
            raise ValueError("MODEL_IDENTITY")
        reply["model"] = model
        ex.require(data.get("object") == "chat.completion" and isinstance(data.get("id"), str)
                   and bool(data["id"]), "RESPONSE_IDENTITY")
        reply["response_id_sha256"] = digest(data["id"])
        choices = data["choices"]
        ex.require(type(choices) is list and len(choices) == 1 and type(choices[0]["index"]) is int
                   and choices[0]["index"] == 0, "CHOICE_COUNT")
        choice = choices[0]
        msg = choice["message"]
        ex.require(msg["role"] == "assistant" and not msg.get("reasoning_content") and not msg.get("reasoning"),
                   "ASSISTANT_ENVELOPE")
        calls = msg.get("tool_calls")
        if choice["finish_reason"] == "tool_calls":
            ex.require(isinstance(calls, list) and len(calls) == 1 and not msg.get("content"), "PROPOSAL_COUNT")
            call = calls[0]
            ex.require(call["type"] == "function" and call["function"]["name"] == sdk.TOOL
                       and isinstance(call["id"], str) and 0 < len(call["id"]) <= 128, "TOOL_IDENTITY")
            args = strict(call["function"]["arguments"].encode("utf-8"))
            ex.require(isinstance(args, dict) and set(args) == {"action"} and args["action"] in ACTIONS, "ACTION")
            reply["choice"] = {"action": args["action"], "call_id": "call_" + digest(call["id"])[:32]}
        else:
            ex.require(choice["finish_reason"] == "stop" and not calls, "INCOMPLETE_OR_EXTRA_TOOL")
            ack = strict(msg["content"].encode("utf-8"))
            ex.require(isinstance(ack, dict) and set(ack) == {"ack"} and isinstance(ack["ack"], str)
                       and api.HASH.fullmatch(ack["ack"]), "ACK_FORMAT")
            reply["choice"] = ack
    except (ValueError, AttributeError, IndexError, KeyError, TypeError, RecursionError) as error:
        code = str(error)
        reply["error"] = code if code in {"MODEL_IDENTITY", "RESPONSE_IDENTITY", "CHOICE_COUNT", "ASSISTANT_ENVELOPE",
                                           "PROPOSAL_COUNT", "TOOL_IDENTITY", "ACTION", "INCOMPLETE_OR_EXTRA_TOOL",
                                           "ACK_FORMAT"} else "MALFORMED_RESPONSE"
    return reply


def decision(reply, reservation, view, receipt):
    """Derive the framework message from the actual projected reply, including on replay."""
    if reply["error"]:
        raise ValueError(reply["error"])
    ex.require(reply["model"] in (api.ALIAS, api.MAPPING) and api.HASH.fullmatch(reply["response_id_sha256"]),
               "RESPONSE_IDENTITY")
    u = reply["usage"]
    ex.require(u is not None and u == api._usage(u), "USAGE_UNKNOWN")
    hold = reservation["hold"]
    ex.require(u["prompt_tokens"] <= hold["input"] and u["completion_tokens"] <= hold["output"], "USAGE_EXCEEDS_HOLD")
    choice = reply["choice"]
    if reservation["binding"]["frame"] == 1:
        ex.require(isinstance(choice, dict) and set(choice) == {"call_id", "action"}
                   and choice["action"] in ACTIONS and isinstance(choice["call_id"], str)
                   and re.fullmatch("call_[a-f0-9]{32}", choice["call_id"]), "PROPOSAL_REQUIRED")
        return {"call": {"id": choice["call_id"], "name": sdk.TOOL,
                         "arguments": ex.proposal_for(view, choice["action"])}}
    ex.require(choice == {"ack": digest(receipt)}, "TOOL_RECEIPT_MISMATCH")
    return {"text": sdk.ACK}

"""Parse actual Chat Completions fields into a bounded, non-secret projection."""
import re

from . import pge_r110_live_contracts as c
from .pge_r106_contracts import exact, hex_id
from .sdk_presend_contracts import Denied, canonical, check, sha, strict

ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
SECRET_ID = re.compile(r"(?i)^sk[-_][A-Za-z0-9_-]{12,}")


def _json(raw, code):
    try:
        return strict(raw.encode() if type(raw) is str else raw)
    except (ValueError, RecursionError):
        raise Denied(code) from None


def _tool_fields(value, layer, required):
    check(type(value) is dict, layer + "_TYPE")
    missing = required - value.keys()
    extra = value.keys() - required
    check(not (missing and extra), layer + "_FIELDS_MIXED")
    check(not missing, layer + "_FIELDS_MISSING")
    check(not extra, layer + "_FIELDS_EXTRA")
    return value


def identity(value, code, mode, optional=False):
    if optional and value == "UNAVAILABLE":
        return value
    check(type(value) is str and ID.fullmatch(value) and not SECRET_ID.match(value)
          and value != "UNAVAILABLE" and (mode != c.NATIVE or
          not value.lower().startswith(("fixture-", "sim-", "stub-"))), code)
    return value


def receipt_facts(receipt, contract, entry):
    exact(receipt, "ticket", "kind", "entered_ns", "connected_ns", "post_returned_ns", "response_ns",
          "tls_version", "tls_verified", "status", "response_size", "response_sha256", "header_request_id")
    times = [receipt[key] for key in ("entered_ns", "connected_ns", "post_returned_ns", "response_ns")]
    mode = contract["kind"]
    seconds = contract["approval"]["budget"]["timeout_seconds"] if mode == c.NATIVE else 3
    check(receipt["ticket"] == entry["ticket"] and receipt["entered_ns"] == entry["entered_ns"]
          and receipt["kind"] == entry["kind"] == mode and all(type(x) is int and x > 0 for x in times)
          and times == sorted(times) and times[-1] - times[0] <= seconds * 10**9
          and type(receipt["status"]) is int and 100 <= receipt["status"] <= 599
          and type(receipt["response_size"]) is int and 0 <= receipt["response_size"] <= c.RESPONSE_CAP
          and hex_id(receipt["response_sha256"], 64)
          and receipt["tls_verified"] is (mode == c.NATIVE)
          and (receipt["tls_version"] in ("TLSv1.2", "TLSv1.3") if mode == c.NATIVE
               else receipt["tls_version"] is None), "HTTP_RECEIPT")
    identity(receipt["header_request_id"], "HTTP_REQUEST_ID", mode, optional=True)


def usage_facts(raw, contract):
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    check(type(raw) is dict and all(type(raw.get(key)) is int and raw[key] >= 0 for key in fields), "USAGE_MISSING")
    usage = {key: raw[key] for key in fields}
    inp, out, total = (usage[key] for key in fields)
    budget = contract["approval"]["budget"] if contract["approval"] else None
    check(0 < inp <= (budget["max_input_tokens"] if budget else 8192)
          and 0 < out <= c.OUTPUT_CAP and total == inp + out, "USAGE_LIMIT")
    if budget is None:
        return usage, {"status": "NOT_RUN"}
    amount = c.cost(budget, inp, out)
    check(amount <= budget["max_cost_microunits"], "COST_LIMIT")
    return usage, {"status": "ESTIMATE", "currency": budget["currency"], "microunits": amount,
                   "invoice": "UNAVAILABLE"}


def parse(raw, receipt, contract):
    check(receipt["status"] == 200, "HTTP_STATUS")
    check(type(raw) is bytes and 0 < len(raw) <= c.RESPONSE_CAP
          and len(raw) == receipt["response_size"] and sha(raw) == receipt["response_sha256"], "RESPONSE_BYTES")
    row = _json(raw, "RESPONSE_JSON")
    check(type(row) is dict and row.get("object") == "chat.completion" and row.get("model") == c.MODEL,
          "PROVIDER_MODEL")
    mode = contract["kind"]
    response_id = identity(row.get("id"), "RESPONSE_ID", mode)
    choices = row.get("choices")
    check(type(choices) is list and len(choices) == 1 and type(choices[0]) is dict, "CHOICE_COUNT")
    choice = choices[0]
    check(type(choice.get("index")) is int and choice["index"] == 0, "CHOICE_INDEX")
    reason = choice.get("finish_reason")
    check(type(reason) is str and reason in ("stop", "length", "content_filter", "tool_calls",
                                           "insufficient_system_resource", "aborted"), "FINISH_REASON")
    check(reason != "content_filter", "MODEL_REFUSAL")
    check(reason != "length", "MODEL_TRUNCATED")
    check(reason not in ("aborted", "insufficient_system_resource"), "PROVIDER_TERMINAL_ERROR")
    check(reason == "tool_calls", "NO_TOOL_SELECTION")
    msg = choice.get("message")
    check(type(msg) is dict and msg.get("role") == "assistant" and msg.get("content") in (None, "")
          and msg.get("reasoning_content") in (None, "") and msg.get("refusal") in (None, ""), "MODEL_MESSAGE")
    calls = msg.get("tool_calls")
    check(type(calls) is list and len(calls) == 1, "TOOL_COUNT")
    call = _tool_fields(calls[0], "TOOL_CALL", {"id", "type", "function"})
    check(call["type"] == "function", "TOOL_TYPE")
    call_id = identity(call["id"], "TOOL_ID", mode)
    function = _tool_fields(call["function"], "TOOL_FUNCTION", {"name", "arguments"})
    check(function["name"] == c.TOOL, "TOOL_NAME")
    check(type(function["arguments"]) is str, "TOOL_ARGUMENT_ENCODING_TYPE")
    args = _tool_fields(_json(function["arguments"], "TOOL_ARGUMENT_JSON"), "TOOL_ARGUMENT", {"candidate_id"})
    check(type(args["candidate_id"]) is str and args["candidate_id"] in c.CHOICES, "CANDIDATE")
    usage, estimate = usage_facts(row.get("usage"), contract)
    return {"kind": mode, "response_id": response_id, "tool_call_id": call_id,
            "request_id": receipt["header_request_id"], "response_sha256": receipt["response_sha256"],
            "model": c.MODEL, "finish_reason": reason, "tool": c.TOOL, "arguments": args,
            "usage": usage, "estimated_cost": estimate}


def verify_selection(selected, receipt, contract):
    exact(selected, "kind", "response_id", "tool_call_id", "request_id", "response_sha256", "model",
          "finish_reason", "tool", "arguments", "usage", "estimated_cost")
    mode = contract["kind"]
    for name in ("response_id", "tool_call_id"):
        identity(selected[name], "SELECTED_ID", mode)
    check(selected["kind"] == mode and selected["request_id"] == receipt["header_request_id"]
          and selected["response_sha256"] == receipt["response_sha256"] and selected["model"] == c.MODEL
          and selected["finish_reason"] == "tool_calls" and selected["tool"] == c.TOOL, "SELECTION_BINDING")
    args = exact(selected["arguments"], "candidate_id")
    usage, estimate = usage_facts(selected["usage"], contract)
    check(args["candidate_id"] in c.CHOICES and canonical(selected["usage"]) == canonical(usage)
          and canonical(selected["estimated_cost"]) == canonical(estimate), "SELECTION_FACTS")
    return args["candidate_id"]

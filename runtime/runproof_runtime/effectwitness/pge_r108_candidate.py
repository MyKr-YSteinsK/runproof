"""Strict simulated upstream response and dynamic SDK-style callback binding."""
import re

from . import pge_r108_contracts as c
from .pge_r106_contracts import exact
from .sdk_presend_contracts import canonical, check, sha, strict


def identifier(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,96}", value) is not None


def parse(raw, request_sha, elapsed_ms):
    check(type(elapsed_ms) is int and 0 <= elapsed_ms <= c.DEADLINE_MS, "RESPONSE_TIMEOUT")
    check(0 < len(raw) <= c.LIMIT, "RESPONSE_BOUND")
    row = exact(strict(raw), "schema", "classification", "request_sha256", "simulated_request_id",
                "simulated_response_id", "finish_reason", "usage", "calls")
    check(row["schema"] == "rpf108-response-v1" and row["classification"] == "SIMULATED"
          and row["request_sha256"] == request_sha, "RESPONSE_SCOPE")
    check(row["simulated_request_id"] == "sim-request-" + request_sha[:32]
          and identifier(row["simulated_response_id"]) and row["simulated_response_id"].startswith("sim-response-"),
          "RESPONSE_IDS")
    check(row["usage"] == "UNKNOWN", "SIMULATED_USAGE")
    check(row["finish_reason"] != "refusal", "MODEL_REFUSAL")
    check(row["finish_reason"] != "error", "SIMULATED_PROVIDER_ERROR")
    check(row["finish_reason"] == "tool_calls" and type(row["calls"]) is list and len(row["calls"]) == 1,
          "NO_SINGLE_TOOL_CALL")
    call = exact(row["calls"][0], "id", "name", "arguments")
    check(identifier(call["id"]) and call["name"] == c.TOOL and type(call["arguments"]) is str, "TOOL_CALL")
    argument = exact(strict(call["arguments"].encode()), "candidate_id")
    check(type(argument["candidate_id"]) is str and argument["candidate_id"] in c.CHOICES, "TOOL_CANDIDATE")
    return {"tool_call_id": call["id"], "name": c.TOOL, "candidate_id": argument["candidate_id"],
            "response_sha256": sha(raw), "simulated_response_id": row["simulated_response_id"]}


def callback(raw, selected):
    expected = {"tool_call_id": selected["tool_call_id"], "name": selected["name"],
                "arguments": {"candidate_id": selected["candidate_id"]}}
    check(0 < len(raw) <= c.LIMIT and canonical(strict(raw)) == canonical(expected), "CALLBACK_BINDING")
    return selected["candidate_id"]


def fixture_response(request_sha, choice, nonce):
    return canonical({"schema": "rpf108-response-v1", "classification": "SIMULATED", "request_sha256": request_sha,
                      "simulated_request_id": "sim-request-" + request_sha[:32],
                      "simulated_response_id": "sim-response-" + nonce,
                      "finish_reason": "tool_calls", "usage": "UNKNOWN",
                      "calls": [{"id": "dynamic-" + nonce, "name": c.TOOL,
                                 "arguments": canonical({"candidate_id": choice}).decode()}]})

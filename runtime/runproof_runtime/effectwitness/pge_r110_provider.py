"""DeepSeek Chat Completions wire shape for Phase A fixtures only."""
import re

from . import pge_r110_contracts as c
from .pge_r106_contracts import exact
from .sdk_presend_contracts import canonical, check, sha, strict


def fixture(choice, nonce):
    return canonical({"id": "fixture-response-" + nonce, "object": "chat.completion", "model": c.MODEL,
                      "choices": [{"index": 0, "finish_reason": "tool_calls", "message":
                          {"role": "assistant", "content": None, "tool_calls": [
                              {"id": "fixture-tool-" + nonce, "type": "function", "function":
                                  {"name": c.TOOL, "arguments": canonical({"candidate_id": choice}).decode()}}]}}]})


def parse(raw, status, elapsed_ms, fixture_request_id):
    check(type(elapsed_ms) is int and 0 <= elapsed_ms <= c.TIMEOUT_MS, "PROVIDER_TIMEOUT")
    check(type(status) is int and status == 200, "PROVIDER_HTTP_ERROR")
    check(type(raw) is bytes and 0 < len(raw) <= c.MAX_REPLY, "RESPONSE_SIZE")
    row = strict(raw)
    check(type(row) is dict and set(row) <= {"id", "object", "model", "choices"}
          and row.get("model") == c.MODEL and row.get("object") == "chat.completion", "FIXTURE_RESPONSE")
    identifier = r"[A-Za-z0-9_-]{1,96}"
    for value, prefix in ((row.get("id"), "fixture-response-"), (fixture_request_id, "fixture-request-")):
        check(type(value) is str and re.fullmatch(identifier, value) and value.startswith(prefix), "FIXTURE_ID")
    choices = row.get("choices")
    check(type(choices) is list and len(choices) == 1, "CHOICE_COUNT")
    choice = exact(choices[0], "index", "finish_reason", "message")
    reason = choice["finish_reason"]
    check(type(choice["index"]) is int and choice["index"] == 0, "CHOICE_INDEX")
    check(reason != "content_filter", "MODEL_REFUSAL")
    check(reason != "length", "MODEL_TRUNCATED")
    check(reason not in ("insufficient_system_resource", "aborted"), "PROVIDER_TERMINAL_ERROR")
    check(reason == "tool_calls", "NO_TOOL_CALL")
    msg = exact(choice["message"], "role", "content", "tool_calls")
    check(msg["role"] == "assistant" and msg["content"] in (None, ""), "TOOL_TEXT")
    check(type(msg["tool_calls"]) is list and len(msg["tool_calls"]) == 1, "TOOL_COUNT")
    tool = exact(msg["tool_calls"][0], "type", "id", "function")
    check(tool["type"] == "function" and type(tool["id"]) is str and re.fullmatch(identifier, tool["id"])
          and tool["id"].startswith("fixture-tool-"), "TOOL_ID")
    function = exact(tool["function"], "name", "arguments")
    check(function["name"] == c.TOOL and type(function["arguments"]) is str, "TOOL_FUNCTION")
    args = exact(strict(function["arguments"].encode()), "candidate_id")
    check(args["candidate_id"] in c.CHOICES, "CANDIDATE")
    return {"kind": "FIXTURE_ONLY", "response_sha256": sha(raw), "fixture_request_id": fixture_request_id,
            "fixture_response_id": row["id"], "tool_call_id": tool["id"], "candidate_id": args["candidate_id"],
            "finish_reason": reason, "provider_request_id": "NOT_RUN", "provider_usage": "NOT_RUN"}

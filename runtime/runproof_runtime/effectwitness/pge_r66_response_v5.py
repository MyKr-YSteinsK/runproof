"""Versioned strict parser. Original parser remains byte-for-byte untouched.

Copied response validation preserves mutation/error ordering in the <=256 domain.
Only a source-bound, reserved terminal ticket permits output up to 512.
"""
import re
from .config_live_runtime import _reject, LiveRuntimeRejected, PROVIDER_MODEL, TOOLS
from . import pge_r66_context as c

def authorized_cap(authorization, account, *, fixture=False):
    if fixture:
        _reject(authorization is None, 'FIXTURE_AUTHORIZATION', 'PROVIDER')
        return 256
    _reject(type(authorization) is dict, 'REQUEST_AUTHORIZATION', 'PROVIDER')
    _reject(type(account) is dict and not account['unknown'], 'REQUEST_ACCOUNT', 'PROVIDER')
    ticket = account['tickets'].get(authorization['ticket'])
    _reject(ticket is not None and authorization['ticket'] not in account['results'], 'REQUEST_TICKET', 'PROVIDER')
    _reject(ticket['resource'] == 'provider' and ticket['role'] == 'TARGET'
            and all(ticket[k] == authorization[k] for k in
                    ('run_id', 'request_sha256', 'binding', 'input_upper', 'output_cap', 'token_upper')),
            'REQUEST_TICKET_BINDING', 'PROVIDER')
    c.validate_binding(authorization['binding'], authorization['run_id'], authorization['attempt'])
    _reject(authorization['output_cap'] == authorization['binding']['outbound_max_tokens'], 'REQUEST_AUTHORIZATION', 'PROVIDER')
    _reject(authorization['request_sha256'] == authorization['binding']['outbound_request_sha256'], 'REQUEST_AUTHORIZATION', 'PROVIDER')
    _reject(authorization['status'] == 'RESERVED_USAGE_UNKNOWN', 'REQUEST_AUTHORIZATION', 'PROVIDER')
    return authorization['output_cap']

def validate(data: object, *, authorization=None, account=None, fixture: bool = False) -> tuple[dict, dict, list[dict]]:
    cap = authorized_cap(authorization, account, fixture=fixture)
    _reject(type(data) is dict and set(data) <= {
        "id", "object", "created", "model", "system_fingerprint", "choices", "usage",
        "service_tier", "prompt_cache_hit_tokens"}
        and {"id", "object", "created", "model", "choices", "usage"} <= set(data),
        "PROVIDER_RESPONSE_FIELDS", "PROVIDER")
    _reject(data["object"] == "chat.completion"
            and type(data["created"]) is int and data["created"] >= 0
            and data["model"] in (("rpf53-fixture-only",) if fixture else
                                   (PROVIDER_MODEL, "DeepSeek-V4.1-Flash-1017"))
            and type(data["choices"]) is list and len(data["choices"]) == 1,
            "PROVIDER_RESPONSE_IDENTITY", "PROVIDER")
    choice = data["choices"][0]
    _reject(type(choice) is dict and set(choice) <= {
        "index", "message", "finish_reason", "logprobs"}
        and {"index", "message", "finish_reason"} <= set(choice)
        and type(choice["index"]) is int and choice["index"] == 0
        and choice["finish_reason"] in ("tool_calls", "stop"),
        "PROVIDER_CHOICE", "PROVIDER")
    message = choice["message"]
    _reject(type(message) is dict and set(message) <= {
        "role", "content", "tool_calls", "reasoning_content", "refusal"}
        and message.get("role") == "assistant", "PROVIDER_MESSAGE", "PROVIDER")
    calls = message.get("tool_calls") or []
    _reject(type(calls) is list and len(calls) <= 1, "PARALLEL_TOOL_CALLS_REJECTED", "AGENT")
    _reject((bool(calls) and choice["finish_reason"] == "tool_calls")
            or (not calls and choice["finish_reason"] == "stop"),
            "PROVIDER_FINISH_REASON", "PROVIDER")
    for call in calls:
        _reject(type(call) is dict, "PROVIDER_TOOL_CALL", "AGENT")
        if set(call) == {"id", "type", "function", "index"}:
            _reject(type(call["index"]) is int and call["index"] == 0,
                    "PROVIDER_TOOL_INDEX", "AGENT")
            call.pop("index")
        _reject(set(call) == {"id", "type", "function"}
                and type(call["id"]) is str
                and re.fullmatch(r"[A-Za-z0-9_-]{1,160}", call["id"]) is not None
                and call["type"] == "function" and type(call["function"]) is dict
                and set(call["function"]) == {"name", "arguments"}
                and call["function"]["name"] in TOOLS
                and type(call["function"]["arguments"]) is str,
                "PROVIDER_TOOL_CALL", "AGENT")
    usage_raw = data["usage"]
    _reject(type(usage_raw) is dict and {
        "prompt_tokens", "completion_tokens", "total_tokens"} <= set(usage_raw)
        and all(type(usage_raw[key]) is int and usage_raw[key] >= 0
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
        and usage_raw["prompt_tokens"] + usage_raw["completion_tokens"] == usage_raw["total_tokens"],
        "PROVIDER_USAGE_INVALID", "PROVIDER")
    _reject(usage_raw["completion_tokens"] <= cap,
            "PROVIDER_OUTPUT_TOKEN_LIMIT", "PROVIDER")
    _reject(cap != 512 or choice["finish_reason"] == "stop", "TERMINAL_REQUIRES_STOP", "PROVIDER")
    usage = {key: usage_raw[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    return data, message, calls

"""Bounded DeepSeek Chat Completions input and a redacted, replayable reply contract."""
import http.client
import json
import os
import re
import ssl
from contextlib import closing
from time import monotonic

from . import fixture_model
from .product_local_contracts import canonical, strict
from .product_local_session import file_sha

ALIAS = "deepseek-flash"
MAPPING = "DeepSeek-V4.1-Flash-1017"
HOST = "api.deepseek.com"
PATH = "/chat/completions"
ENDPOINT = "https://" + HOST + PATH
PROMPT_EXTRA = ("At step 1 call refund_order with its advertised operation_id. At step 2 call apply_config "
                "only if visible_feedback_status is VERIFIED; otherwise return exactly {\"decision\":\"STOP\"}. "
                "Perform only the current step. Use at most one function call. Do not return an explanation.")
SCHEMA = "rpf119-chat-completions-projection/v1"
BODY_CAP = 32768
TIMEOUT = 55
OUTPUT = 384
LIMITS = {"sessions": 6, "per_session": 2, "requests": 12, "per_input": 16384, "per_output": 2048,
          "input": 196608, "output": 24576, "usd_nanodollars": 500_000_000}
# Peak nanounits of invoice currency per token, cache-hit / miss / output.
RATES = {"USD": (6, 300, 1200), "CNY": (40, 2000, 8000)}
# Book CNY at one yuan per US dollar, above the actual USD cost at the documented reference.
CNY_PER_USD_FLOOR = 1
PROTOCOL_BYTES = 4096
TOKENIZER_REFERENCE = {"revision": "08c8657f02291e11b6f6b63e0e16014f8e748518",
                       "tokenizer_sha256": "c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b",
                       "encoder_sha256": "13231c592e958fb39e2af6001dae69d90e7a36b265702b9b390236fb387599e2"}
ARGUMENT_TEXT = re.compile(r"[A-Za-z0-9_-]{1,32}", re.ASCII)
MEDIA_PARAMS = {"search", "fetch", "web_search"}
HASH = re.compile(r"[a-f0-9]{64}")


def usage_cost(usage, currency):
    hit, miss, output = RATES[currency]
    cached = usage.get("prompt_cache_hit_tokens", 0)
    return cached * hit + (usage["prompt_tokens"] - cached) * miss + usage["completion_tokens"] * output


def request(observed, currency):
    inputs = fixture_model.model_input(observed)
    tools = []
    for item in inputs["tools"]:
        function = item["function"]
        operation = function["parameters"]["properties"]["operation_id"]["const"]
        tools.append({"type": "function", "function": {"name": function["name"], "parameters": {
            "type": "object", "required": ["operation_id"], "additionalProperties": False,
            "properties": {"operation_id": {"type": "string", "enum": [operation]}},
        }}})
    if len(tools) not in (1, 2) or any(t["function"]["name"] in MEDIA_PARAMS for t in tools):
        raise ValueError("MODEL_TOOL_SCOPE")
    messages = [{"role": "system", "content": inputs["task"] + " " + PROMPT_EXTRA},
                {"role": "user", "content": canonical({"observation": observed,
                    "visible_feedback_status": inputs["visible_feedback_status"]}).decode("ascii")}]
    body = {"model": ALIAS, "messages": messages, "tools": tools, "thinking": {"type": "disabled"},
            "stream": False, "tool_choice": "auto", "temperature": 0, "max_tokens": OUTPUT}
    raw = canonical(body)
    # UTF-8 byte bound for the published byte-level BPE text path. Account for a second,
    # pretty-serialized schema representation and the published tool/prompt framing.
    schema_bytes = len(json.dumps(tools, ensure_ascii=True, indent=2).encode("ascii"))
    input_bound = len(raw) + schema_bytes + PROTOCOL_BYTES
    if input_bound > LIMITS["per_input"] or not 0 < OUTPUT <= LIMITS["per_output"]:
        raise ValueError("REQUEST_TOKEN_BOUND")
    ceiling = usage_cost({"prompt_tokens": input_bound, "completion_tokens": OUTPUT}, currency)
    return inputs, raw, {"requests": 1, "input": input_bound, "output": OUTPUT, "usd_nanodollars": ceiling}


def _stop(outcome, code):
    return {"outcome": outcome, "code": code, "intent": None, "call_id": None}


def _hash_text(value):
    return file_sha(value.encode("utf-8")) if isinstance(value, str) and value else None


def _usage(raw):
    if type(raw) is not dict:
        return None
    keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    if any(type(raw.get(k)) is not int or not 0 <= raw[k] <= 2_000_000 for k in keys):
        return None
    if raw["prompt_tokens"] <= 0 or raw["total_tokens"] != raw["prompt_tokens"] + raw["completion_tokens"]:
        return None
    usage = {k: raw[k] for k in keys}
    cache_keys = ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
    if any(key in raw for key in cache_keys):
        if (any(type(raw.get(k)) is not int or not 0 <= raw[k] <= raw["prompt_tokens"] for k in cache_keys)
                or sum(raw[k] for k in cache_keys) != raw["prompt_tokens"]):
            return None
        usage.update({k: raw[k] for k in cache_keys})
    return usage


def _argument(name, value):
    if name not in {"operation_id", "extra"}:
        return False
    if value is None or type(value) is bool:
        return True
    if type(value) is int:
        return abs(value) <= 2**31
    return (type(value) is str and (fixture_model.OPERATION.fullmatch(value)
            or ARGUMENT_TEXT.fullmatch(value) and not value.lower().startswith(("sk-", "key-", "token-"))))


def _choices(data, *, projected=False):
    choices = data.get("choices")
    if type(choices) is not list or len(choices) != 1:
        raise ValueError("CHOICE_ENVELOPE")
    ch = choices[0]
    if type(ch) is not dict or type(ch.get("index")) is not int or ch["index"] != 0:
        raise ValueError("CHOICE_ENVELOPE")
    finish = ch.get("finish_reason")
    if finish not in {"tool_calls", "stop", "length", "content_filter", "insufficient_system_resource"}:
        raise ValueError("FINISH_REASON")
    message = ch.get("message")
    if type(message) is not dict or message.get("role") != "assistant":
        raise ValueError("ASSISTANT_ENVELOPE")
    if message.get("reasoning_content") or message.get("reasoning"):
        raise ValueError("THINKING_NOT_DISABLED")
    if finish in {"length", "content_filter", "insufficient_system_resource"}:
        # Retain the finish reason. Discard unfinished or filtered model text.
        return {"choices": [{"index": 0, "finish_reason": finish,
                             "message": {"role": "assistant", "content": None}}]}
    content = message.get("content")
    if content is not None and type(content) is not str:
        raise ValueError("CONTENT_SCHEMA")
    if content and (len(content) > 256 or finish != "stop" or strict(content.encode("utf-8")) != {"decision": "STOP"}):
        raise ValueError("CONTENT_OMITTED")
    clean = {"role": "assistant", "content": content}
    calls = message.get("tool_calls")
    if calls is not None:
        if type(calls) is not list or len(calls) > 2:
            raise ValueError("TOOL_CALL_COUNT")
        clean["tool_calls"] = []
        for call in calls:
            if type(call) is not dict or call.get("type") != "function":
                raise ValueError("TOOL_CALL_ENVELOPE")
            function, ident = call.get("function"), call.get("id")
            if (type(ident) is not str or not 1 <= len(ident) <= 128 or
                    (projected and not HASH.fullmatch(ident)) or type(function) is not dict):
                raise ValueError("TOOL_CALL_IDENTITY")
            name, arguments = function.get("name"), function.get("arguments")
            if (type(name) is not str or not fixture_model.NAME.fullmatch(name)
                    or name.lower().startswith(("sk-", "key-", "token-")) or type(arguments) is not str):
                raise ValueError("FUNCTION_ENVELOPE")
            args = strict(arguments.encode("utf-8"))
            if type(args) is not dict or any(not _argument(k, v) for k, v in args.items()):
                raise ValueError("ARGUMENTS_OMITTED")
            clean["tool_calls"].append({"id": ident if projected else _hash_text(ident), "type": "function",
                                        "function": {"name": name, "arguments": canonical(args).decode("ascii")}})
    return {"choices": [{"index": 0, "finish_reason": finish, "message": clean}]}


def project(raw, status):
    reply = {"schema": SCHEMA, "body_sha256": file_sha(raw), "body_bytes": len(raw), "model": None,
             "model_sha256": None, "response_id_sha256": None, "created": None, "usage": None,
             "projection": None, "error": None}
    if status != 200:
        return reply | {"error": "PROVIDER_HTTP_STATUS"}
    try:
        data = strict(raw)
        if type(data) is not dict:
            raise ValueError("REPLY_OBJECT")
        model = data.get("model")
        reply["model_sha256"] = _hash_text(model)
        reply["response_id_sha256"] = _hash_text(data.get("id"))
        if type(data.get("created")) is int and 0 <= data["created"] < 2**40:
            reply["created"] = data["created"]
        reply["usage"] = _usage(data.get("usage"))
        if model not in (ALIAS, MAPPING):
            return reply | {"error": "RESPONSE_MODEL_IDENTITY"}
        reply["model"] = model
        if reply["response_id_sha256"] is None or reply["created"] is None or data.get("object") != "chat.completion":
            return reply | {"error": "RESPONSE_ENVELOPE"}
        reply["projection"] = _choices(data)
    except (ValueError, TypeError, RecursionError) as exc:
        code = str(exc)
        reply["error"] = code if re.fullmatch(r"[A-Z_]{3,48}", code) else "REPLY_JSON_OR_TEXT"
    return reply


def interpret(reply, status, observed, hold):
    if (set(reply) != {"schema", "body_sha256", "body_bytes", "model", "model_sha256", "response_id_sha256",
                       "created", "usage", "projection", "error"} or reply["schema"] != SCHEMA
            or not HASH.fullmatch(reply["body_sha256"]) or type(reply["body_bytes"]) is not int
            or not 0 <= reply["body_bytes"] <= BODY_CAP or reply["model"] not in (None, ALIAS, MAPPING)
            or any(value is not None and not HASH.fullmatch(value)
                   for value in (reply["model_sha256"], reply["response_id_sha256"]))
            or reply["created"] is not None and (type(reply["created"]) is not int or not 0 <= reply["created"] < 2**40)
            or reply["model"] is not None and reply["model_sha256"] != _hash_text(reply["model"])):
        raise ValueError("REPLY_PROJECTION_SCHEMA")
    usage = reply["usage"]
    if usage is not None and canonical(usage) != canonical(_usage(usage)):
        raise ValueError("USAGE_PROJECTION_SCHEMA")
    if status != 200:
        if reply["error"] != "PROVIDER_HTTP_STATUS" or any(reply[key] is not None for key in
                ("model", "model_sha256", "response_id_sha256", "created", "usage", "projection")):
            raise ValueError("HTTP_REPLY_BINDING")
        return _stop("ERROR", "PROVIDER_HTTP_STATUS")
    if usage is not None and (usage["prompt_tokens"] > hold["input"] or usage["completion_tokens"] > hold["output"]):
        return _stop("INCONCLUSIVE", "USAGE_EXCEEDS_HOLD")
    if reply["error"] is not None:
        if not re.fullmatch(r"[A-Z_]{3,48}", reply["error"]) or reply["projection"] is not None:
            raise ValueError("REPLY_ERROR_BINDING")
        return _stop("INVALID", reply["error"])
    body = reply["projection"]
    if (reply["model"] is None or reply["response_id_sha256"] is None or reply["created"] is None
            or canonical(body) != canonical(_choices(body, projected=True))):
        raise ValueError("REPLY_PROJECTION_BINDING")
    if usage is None:
        return _stop("INCONCLUSIVE", "USAGE_UNKNOWN")
    if body["choices"][0]["finish_reason"] == "insufficient_system_resource":
        return _stop("ERROR", "PROVIDER_RESOURCE_LIMIT")
    try:
        return fixture_model.parse_reply(canonical(body), observed)
    except ValueError as exc:
        return _stop("INVALID", str(exc))


def _post(connection, headers, raw, record, timeout=TIMEOUT):
    deadline = monotonic() + timeout

    def remaining():
        seconds = deadline - monotonic()
        if seconds <= 0:
            raise TimeoutError
        return seconds

    with closing(connection(remaining())) as conn:
        conn.connect()
        wire = conn.sock
        conn.auto_open = 0
        wire.settimeout(remaining())
        conn.request("POST", PATH, body=raw, headers=headers)
        record("POST_WRITTEN", {})
        wire.settimeout(remaining())
        with closing(http.client.HTTPResponse(wire, method="POST")) as response:
            response.begin()
            ids = response.headers.get_all("x-request-id", [])
            record("HTTP_RESPONSE", {"status": response.status,
                                     "header_request_id_sha256": _hash_text(ids[0]) if len(ids) == 1 else None})
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise ValueError("HTTP_ENCODING")
            data = bytearray()
            while len(data) <= BODY_CAP:
                wire.settimeout(remaining())
                chunk = response.read1(min(8192, BODY_CAP + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > BODY_CAP or response.length not in (0, None):
                raise ValueError("HTTP_BODY_BOUND")
    remaining()
    return bytes(data)


def _configured_sender():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("DEEPSEEK_KEY_UNAVAILABLE")
    if len(key) > 512 or not key.isascii() or any(not 33 <= ord(char) <= 126 for char in key):
        raise ValueError("DEEPSEEK_KEY_FORMAT")
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    headers = {"Content-Type": "application/json", "Accept-Encoding": "identity", "Connection": "close",
               "Authorization": "Bearer " + key}

    def send(raw, record):
        response = _post(lambda seconds: http.client.HTTPSConnection(HOST, 443, timeout=seconds, context=context),
                         headers, raw, record)
        # The transport credential is never written, even if it is echoed in a response.
        if _contains_credential(response, key):
            raise ValueError("HTTP_BODY_SECRET")
        return response

    return send


def _contains_credential(raw, secret):
    if secret.encode("ascii") in raw:
        return True
    try:
        pending = [strict(raw)]
    except (ValueError, RecursionError):
        return False  # Unparseable content is never eligible for the projection.
    while pending:
        value = pending.pop()
        if type(value) is dict:
            pending.extend(value)
            pending.extend(value.values())
        elif type(value) is list:
            pending.extend(value)
        elif type(value) is str:
            if secret in value:
                return True
            if value.lstrip().startswith("{"):
                try:
                    pending.append(strict(value.encode("utf-8")))  # JSON-encoded function arguments
                except (ValueError, RecursionError):
                    pass
    return False

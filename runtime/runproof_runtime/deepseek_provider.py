"""DeepSeek chat/completions boundary used by the product vertical slice."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .models import RuntimeFailure, ToolCall
from .scenario import tool_definitions


API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-flash"
PRICING = {
    "pricing_id": "deepseek-flash-CNY-2026-09-11",
    "currency": "CNY",
    "off_peak_per_million": {"cache_hit": 0.02, "cache_miss": 1.0, "output": 4.0},
}


def _safe_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def usage_evidence(raw: Any) -> dict[str, int] | None:
    if not isinstance(raw, dict):
        return None
    result: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
        value = _safe_int(raw.get(key))
        if value is not None:
            result[key] = value
    prompt_details = raw.get("prompt_tokens_details")
    cached = _safe_int(prompt_details.get("cached_tokens")) if isinstance(prompt_details, dict) else None
    if cached is not None and "prompt_cache_hit_tokens" not in result:
        result["prompt_cache_hit_tokens"] = cached
    if "prompt_cache_miss_tokens" not in result and "prompt_tokens" in result and "prompt_cache_hit_tokens" in result:
        result["prompt_cache_miss_tokens"] = result["prompt_tokens"] - result["prompt_cache_hit_tokens"]
    return result or None


def aggregate_usage(records: list[dict[str, Any]]) -> dict[str, int] | None:
    keys = ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
    if not records:
        return None
    result: dict[str, int] = {}
    for key in keys:
        values = [record.get("usage", {}).get(key) for record in records]
        if all(isinstance(value, int) for value in values):
            result[key] = sum(values)
    return result or None


def derived_cost(usage: dict[str, int] | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "layer": "Derived Value",
        "pricing_id": PRICING["pricing_id"],
        "currency": PRICING["currency"],
        "estimate": None,
    }
    if not usage:
        result["reason"] = "USAGE_UNAVAILABLE"
        return result
    hit = usage.get("prompt_cache_hit_tokens")
    miss = usage.get("prompt_cache_miss_tokens")
    output = usage.get("completion_tokens")
    prompt = usage.get("prompt_tokens")
    if not all(isinstance(value, int) and value >= 0 for value in (hit, miss, output, prompt)) or hit + miss != prompt:
        result["reason"] = "MISSING_OR_INCONSISTENT_USAGE"
        return result
    prices = PRICING["off_peak_per_million"]
    result["tariff"] = "off_peak"
    result["estimate"] = round((hit * prices["cache_hit"] + miss * prices["cache_miss"] + output * prices["output"]) / 1_000_000, 10)
    return result


def validate_tool_arguments(name: str, raw: str | dict[str, Any]) -> dict[str, Any]:
    try:
        if isinstance(raw, str):
            if len(raw) > 4096:
                raise ValueError
            value = json.loads(raw)
        else:
            value = raw
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeFailure("PROVIDER", "INVALID_TOOL_ARGUMENT_JSON") from error
    if not isinstance(value, dict):
        raise RuntimeFailure("PROVIDER", "INVALID_TOOL_ARGUMENT_SCHEMA")
    expected: dict[str, set[str]] = {
        "read_state": set(),
        "apply_change": {"operation_id", "expected_revision", "release"},
        "reconcile": {"operation_id"},
    }
    if name not in expected or set(value) != expected[name]:
        raise RuntimeFailure("PROVIDER", "INVALID_TOOL_ARGUMENT_SCHEMA")
    if name == "read_state":
        return value
    if not isinstance(value.get("operation_id"), str) or value["operation_id"] != "change-001":
        raise RuntimeFailure("PROVIDER", "INVALID_TOOL_ARGUMENT_SCHEMA")
    if name == "apply_change":
        if isinstance(value.get("expected_revision"), bool) or value.get("expected_revision") != 0 or value.get("release") != "release-v2":
            raise RuntimeFailure("PROVIDER", "INVALID_TOOL_ARGUMENT_SCHEMA")
    return value


def _failure_code(status: int) -> str:
    return {
        400: "REQUEST_FORMAT",
        401: "AUTHENTICATION",
        402: "BALANCE",
        422: "REQUEST_PARAMETERS",
        429: "RATE_LIMIT",
        500: "SERVER",
        503: "OVERLOADED",
    }.get(status, "HTTP_ERROR")


def _parse_completion(data: Any) -> tuple[dict[str, Any], list[ToolCall]]:
    if not isinstance(data, dict) or not isinstance(data.get("choices"), list) or len(data["choices"]) != 1:
        raise RuntimeFailure("PROVIDER", "MALFORMED_COMPLETION")
    choice = data["choices"][0]
    message = choice.get("message") if isinstance(choice, dict) else None
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise RuntimeFailure("PROVIDER", "MALFORMED_COMPLETION")
    finish_reason = choice.get("finish_reason")
    if finish_reason not in {"stop", "tool_calls"}:
        raise RuntimeFailure("PROVIDER", "INCOMPLETE_COMPLETION")
    raw_calls = message.get("tool_calls", [])
    if not isinstance(raw_calls, list) or (finish_reason == "tool_calls") != bool(raw_calls):
        raise RuntimeFailure("PROVIDER", "MALFORMED_TOOL_ENVELOPE")
    if len(raw_calls) > 1:
        raise RuntimeFailure("PROVIDER", "PARALLEL_TOOL_CALLS_UNSUPPORTED")
    calls: list[ToolCall] = []
    seen_ids: set[str] = set()
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            raise RuntimeFailure("PROVIDER", "MALFORMED_TOOL_ENVELOPE")
        function = raw_call.get("function")
        call_id = raw_call.get("id")
        name = function.get("name") if isinstance(function, dict) else None
        arguments = function.get("arguments") if isinstance(function, dict) else None
        if raw_call.get("type") != "function" or not isinstance(call_id, str) or not call_id or call_id in seen_ids or not isinstance(name, str):
            raise RuntimeFailure("PROVIDER", "MALFORMED_TOOL_ENVELOPE")
        seen_ids.add(call_id)
        calls.append(ToolCall(call_id, name, validate_tool_arguments(name, arguments)))
    content = message.get("content")
    if content is not None and not isinstance(content, str):
        raise RuntimeFailure("PROVIDER", "MALFORMED_CONTENT")
    if not calls and not (content or "").strip():
        raise RuntimeFailure("PROVIDER", "EMPTY_COMPLETION")
    assistant: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        assistant["tool_calls"] = [{"id": call.call_id, "name": call.name, "arguments": call.arguments} for call in calls]
    return assistant, calls


class DeepSeekProvider:
    """Non-thinking, non-streaming provider adapter with no automatic retry."""

    def __init__(self, api_key: str, model: str | None = None, request_timeout: float = 45.0, max_calls: int = 12) -> None:
        if not api_key.strip():
            raise RuntimeFailure("HARNESS", "MISSING_DEEPSEEK_API_KEY")
        self.api_key = api_key
        self.model = model or os.environ.get("RPF_MODEL", DEFAULT_MODEL)
        self.request_timeout = request_timeout
        self.max_calls = max_calls
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages: list[dict[str, Any]], max_tokens: int = 1024) -> tuple[dict[str, Any], list[ToolCall]]:
        if len(self.calls) >= self.max_calls:
            raise RuntimeFailure("HARNESS", "REQUEST_STEP_BUDGET")
        started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        begin = time.perf_counter()
        record: dict[str, Any] = {
            "layer": "Observed Fact",
            "sequence": len(self.calls) + 1,
            "provider": "deepseek",
            "requested_model": self.model,
            "mode": "non-thinking",
            "started_at": started,
            "http_status": None,
            "continuation_sent": False,
        }
        self.calls.append(record)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens,
            "tools": tool_definitions(),
        }
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                record["http_status"] = response.status
                body = response.read(4 * 1024 * 1024)
            try:
                data = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise RuntimeFailure("PROVIDER", "NON_JSON_RESPONSE") from error
            if not isinstance(data, dict):
                raise RuntimeFailure("PROVIDER", "MALFORMED_COMPLETION")
            record["response_id"] = data.get("id") if isinstance(data.get("id"), str) else None
            record["returned_model"] = data.get("model") if isinstance(data.get("model"), str) else None
            record["system_fingerprint"] = data.get("system_fingerprint") if isinstance(data.get("system_fingerprint"), str) else None
            record["provider_created"] = data.get("created") if isinstance(data.get("created"), int) else None
            record["finish_reason"] = data.get("choices", [{}])[0].get("finish_reason") if data.get("choices") else None
            record["usage"] = usage_evidence(data.get("usage"))
            assistant, calls = _parse_completion(data)
            record["tool_calls"] = [
                {"id": call.call_id, "name": call.name, "validated_arguments": call.arguments}
                for call in calls
            ]
            return assistant, calls
        except urllib.error.HTTPError as error:
            record["http_status"] = error.code
            record["failure"] = {"domain": "PROVIDER", "outcome": "ERROR", "code": _failure_code(error.code)}
            raise RuntimeFailure("PROVIDER", _failure_code(error.code)) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            record["failure"] = {"domain": "PROVIDER", "outcome": "ERROR", "code": "TRANSPORT_OR_TIMEOUT"}
            raise RuntimeFailure("PROVIDER", "TRANSPORT_OR_TIMEOUT") from error
        except RuntimeFailure as error:
            record["failure"] = {"domain": error.domain, "outcome": error.outcome, "code": error.code}
            raise
        finally:
            record["ended_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            record["latency_ms"] = round((time.perf_counter() - begin) * 1000)

    @staticmethod
    def assistant_for_transport(assistant: dict[str, Any], calls: list[ToolCall]) -> dict[str, Any]:
        """Rebuild the provider wire envelope; normalized calls are runtime-only objects."""

        message: dict[str, Any] = {"role": "assistant", "content": assistant.get("content")}
        if calls:
            message["tool_calls"] = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments, separators=(",", ":"))},
                }
                for call in calls
            ]
        return message

    def evidence(self) -> dict[str, Any]:
        usage = aggregate_usage(self.calls)
        return {
            "requested_model": self.model,
            "mode": "non-thinking",
            "api_surface": API_URL,
            "calls": self.calls,
            "raw_usage": usage,
            "derived_cost": derived_cost(usage),
            "automatic_retries": 0,
        }

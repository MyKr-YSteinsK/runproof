"""RPF-53 bounded Provider broker, live tool host and config-center HTTP boundary."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import secrets
import ssl
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import quote

from .config_live_contracts import (
    LIMITS, OPENAI_VERSION, PROVIDER_MODEL, PROVIDER_ORIGIN, PROVIDER_PATH,
    SDK_CORE_SHA256, SDK_NAME, SDK_VERSION, TOOLS, TOOL_ARGUMENT_KEYS,
    LiveContractRejected, canonical, digest, require, strict_json, validate_contracts,
)


class LiveRuntimeRejected(RuntimeError):
    def __init__(self, code: str, domain: str = "PLATFORM"):
        self.code, self.domain = code, domain
        super().__init__(code)


def _reject(condition: bool, code: str, domain: str = "PLATFORM") -> None:
    if not condition:
        raise LiveRuntimeRejected(code, domain)


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + secrets.token_hex(6))
    try:
        with temp.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _api_response(observation: dict, status: int, code: int,
                  data_kind: str) -> tuple[bool, object]:
    if (observation.get("status") != status or observation.get("transport_error") is not None
            or not isinstance(observation.get("content_type"), str)
            or not observation["content_type"].lower().startswith("application/json")):
        return False, None
    body = observation.get("response")
    if (type(body) is not dict or set(body) != {"code", "message", "data", "traceId"}
            or type(body["code"]) is not int or body["code"] != code
            or not isinstance(body["message"], str)
            or (body["traceId"] is not None and not isinstance(body["traceId"], str))):
        return False, None
    data = body["data"]
    if ((data_kind == "none" and data is not None)
            or (data_kind == "item" and type(data) is not dict)
            or (data_kind == "list" and type(data) is not list)):
        return False, None
    return True, data


def _valid_item(item: object, effect: dict, version: int, value: str) -> bool:
    if type(item) is not dict or set(item) != {
            "app", "env", "key", "value", "description", "version", "updatedAt"}:
        return False
    try:
        updated = datetime.fromisoformat(item["updatedAt"].replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False
    return (all(item[name] == effect[name] for name in ("app", "env", "key"))
            and item["value"] == value and item["description"] is None
            and type(item["version"]) is int and item["version"] == version
            and updated.tzinfo is not None)


def _http_contract(effect: dict, kind: str) -> tuple[str, str, dict | None]:
    app, env, key = (quote(effect[name], safe="") for name in ("app", "env", "key"))
    if kind in ("initial_current", "inspect_config", "final_current", "reconcile_current"):
        return "GET", f"/api/configs/{key}?app={app}&env={env}", None
    if kind in ("initial_history", "final_history", "reconcile_history"):
        return "GET", f"/api/configs/history?app={app}&env={env}&key={key}&limit=50", None
    if kind == "final_list":
        return "GET", f"/api/configs?app={app}&env={env}", None
    base = {name: effect[name] for name in ("app", "env", "key")}
    if kind == "create_config_v1":
        return "POST", "/api/configs", {**base, "value": effect["initial_value"]}
    if kind == "update_config_v2":
        return "POST", "/api/configs", {**base, "value": effect["required_value"],
                                       "expectedVersion": effect["initial_version"]}
    raise LiveRuntimeRejected("HTTP_KIND_NOT_ALLOWLISTED")


class ProviderLedger:
    """Single-run write-ahead reservations; unknown usage blocks all later requests."""
    SCHEMA = "rpf53-provider-ledger-v1"

    def __init__(self, path: Path, run_id: str, *, create: bool = False):
        self.path = Path(path)
        self.run_id = run_id
        if create:
            value = {"schema_version": self.SCHEMA, "run_id": run_id,
                     "limits": dict(LIMITS), "trial_status": "RESERVED",
                     "requests": []}
            _reject(not self.path.exists() and not self.path.is_symlink(), "LEDGER_ALREADY_EXISTS")
            _atomic_write(self.path, canonical(value))
            self.data = value
        else:
            self.data = strict_json(self.path.read_bytes())
            self.validate()

    @classmethod
    def fixture_only(cls, run_id: str) -> "ProviderLedger":
        """No-file, no-network ledger shape for explicit SDK diagnostics."""
        ledger = object.__new__(cls)
        ledger.path = None
        ledger.run_id = run_id
        ledger.data = {"schema_version": cls.SCHEMA, "run_id": run_id,
                       "limits": dict(LIMITS), "trial_status": "DIAGNOSTIC_ONLY",
                       "requests": []}
        ledger.fixture = True
        return ledger

    def checkpoint(self) -> None:
        if self.path is None:
            return
        _atomic_write(self.path, canonical(self.data))

    def validate(self) -> None:
        _reject(type(self.data) is dict and set(self.data) == {
            "schema_version", "run_id", "limits", "trial_status", "requests"}
            and self.data["schema_version"] == self.SCHEMA
            and self.data["run_id"] == self.run_id
            and self.data["limits"] == LIMITS
            and self.data["trial_status"] in ("RESERVED", "CLOSED", "QUARANTINED",
                                                "DIAGNOSTIC_ONLY")
            and type(self.data["requests"]) is list
            and len(self.data["requests"]) <= LIMITS["provider_https_requests"],
            "LEDGER_IDENTITY")
        for index, item in enumerate(self.data["requests"], 1):
            _reject(type(item) is dict and item.get("attempt") == index
                    and item.get("run_id") == self.run_id
                    and item.get("status") in ("RESERVED_USAGE_UNKNOWN", "RECEIVED",
                                                "RECEIVED_INVALID_USAGE"),
                    "LEDGER_CORRUPT")
            if item["status"] == "RECEIVED":
                self._validate_usage(item.get("usage"), item.get("reservation_tokens"))
        usage = self.usage()
        _reject(usage["confirmed_tokens"] <= LIMITS["total_tokens"], "TOKEN_BUDGET_EXCEEDED")
        _reject(usage["estimated_cost_cny_upper"] is None
                or usage["estimated_cost_cny_upper"] <= LIMITS["estimated_cost_cny_upper"],
                "COST_BUDGET_EXCEEDED")

    def reserve(self, body: dict, tool_returns: list[dict]) -> dict:
        self.validate()
        records = self.data["requests"]
        _reject(all(item["status"] == "RECEIVED" for item in records),
                "PROVIDER_USAGE_UNKNOWN", "PROVIDER")
        _reject(len(records) < LIMITS["provider_https_requests"], "PROVIDER_REQUEST_BUDGET", "PROVIDER")
        raw = canonical(body)
        reserve = len(raw) + LIMITS["max_output_tokens_per_request"] + 1024
        usage = self.usage()
        _reject(usage["confirmed_tokens"] + reserve <= LIMITS["total_tokens"],
                "TOKEN_RESERVATION_EXHAUSTED", "PROVIDER")
        reserve_cost = (usage["estimated_cost_cny_upper"]
                        + reserve * LIMITS["output_cny_per_million_peak_bound"] / 1_000_000)
        _reject(reserve_cost <= LIMITS["estimated_cost_cny_upper"],
                "COST_RESERVATION_EXHAUSTED", "PROVIDER")
        record = {"attempt": len(records) + 1, "run_id": self.run_id,
                  "request_sha256": hashlib.sha256(raw).hexdigest(),
                  "reservation_tokens": reserve, "status": "RESERVED_USAGE_UNKNOWN",
                  "transport": "DeepSeek-HTTPS-no-retry", "tool_returns": tool_returns,
                  "started_monotonic_ns": time.monotonic_ns(), "response_id": None,
                  "returned_model": None, "usage": None, "failure_code": None,
                  "tool_call_ids": []}
        records.append(record)
        self.checkpoint()
        return record

    @staticmethod
    def _validate_usage(usage: object, reservation: object) -> None:
        _reject(type(usage) is dict and set(usage) == {
            "prompt_tokens", "completion_tokens", "total_tokens"}
            and all(type(v) is int and v >= 0 for v in usage.values())
            and usage["prompt_tokens"] + usage["completion_tokens"] == usage["total_tokens"]
            and type(reservation) is int and usage["total_tokens"] <= reservation,
            "PROVIDER_USAGE_INVALID", "PROVIDER")

    def received(self, record: dict, data: dict) -> None:
        usage_raw = data.get("usage")
        if type(usage_raw) is not dict:
            record["failure_code"] = "PROVIDER_USAGE_UNKNOWN"
            self.checkpoint()
            raise LiveRuntimeRejected("PROVIDER_USAGE_UNKNOWN", "PROVIDER")
        usage = {name: usage_raw.get(name) for name in (
            "prompt_tokens", "completion_tokens", "total_tokens")}
        try:
            self._validate_usage(usage, record["reservation_tokens"])
        except LiveRuntimeRejected as exc:
            record["failure_code"] = exc.code
            record["reported_usage"] = usage if all(type(v) is int and v >= 0 for v in usage.values()) else None
            record["status"] = "RECEIVED_INVALID_USAGE"
            self.checkpoint()
            raise
        response_id = data.get("id")
        model = data.get("model")
        _reject(type(response_id) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,160}", response_id)
                is not None and model in (PROVIDER_MODEL, "DeepSeek-V4.1-Flash-1017"),
                "PROVIDER_IDENTITY", "PROVIDER")
        record.update(status="RECEIVED", response_id=response_id,
                      returned_model=model, usage=usage)
        self.checkpoint()

    def usage(self) -> dict:
        records = self.data["requests"]
        known = all(record.get("status") in ("RECEIVED", "RECEIVED_INVALID_USAGE")
                    for record in records)
        received = [record.get("usage", record.get("reported_usage")) for record in records
                    if record.get("status") in ("RECEIVED", "RECEIVED_INVALID_USAGE")
                    and type(record.get("usage", record.get("reported_usage"))) is dict]
        input_tokens = sum(item["prompt_tokens"] for item in received)
        output_tokens = sum(item["completion_tokens"] for item in received)
        estimate = ((input_tokens * LIMITS["input_cny_per_million_peak_bound"]
                     + output_tokens * LIMITS["output_cny_per_million_peak_bound"]) / 1_000_000
                    if known else None)
        if getattr(self, "fixture", False):
            return {"provider_https_requests": 0, "tokens": 0, "confirmed_tokens": 0,
                    "input_tokens": 0, "output_tokens": 0, "usage_known": True,
                    "metering_kind": "FIXTURE_TEST_ONLY", "estimated_cost_cny_upper": 0.0,
                    "automatic_retries": 0, "trials": 0}
        return {"provider_https_requests": len(records),
                "tokens": input_tokens + output_tokens if known else None,
                "confirmed_tokens": input_tokens + output_tokens,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "usage_known": known, "metering_kind": "PROVIDER_REPORTED",
                "estimated_cost_cny_upper": estimate,
                "automatic_retries": 0, "trials": 1}

    def fail_unknown(self, record: dict, code: str) -> None:
        _reject(record in self.data["requests"] and record["status"] == "RESERVED_USAGE_UNKNOWN",
                "LEDGER_RESERVATION_MISSING")
        record["failure_code"] = code
        self.checkpoint()

    def finish(self, closed: bool) -> None:
        _reject(self.data["trial_status"] == "RESERVED", "TRIAL_NOT_RESERVED")
        self.data["trial_status"] = "CLOSED" if closed else "QUARANTINED"
        self.checkpoint()


class ConfigLiveHttp:
    """Only this parent-side object can send bounded config-center business HTTP."""
    def __init__(self, contracts: dict, api_key: str, *, deadline: float):
        validate_contracts(contracts)
        _reject(type(api_key) is str and re.fullmatch(r"[A-Za-z0-9._~-]{24,128}", api_key)
                is not None, "API_KEY_SHAPE")
        self.contracts, self.effect = contracts, contracts["effect"]
        self.port, self._api_key, self.deadline = contracts["experiment"]["java_port"], api_key, deadline
        self.observations: list[dict] = []
        self.post_count = 0
        self.stop_writes = False

    def request(self, kind: str, *, reconcile: bool = False) -> dict:
        method, path, request_body = _http_contract(self.effect, kind)
        _reject(len(self.observations) < LIMITS["business_http_requests"], "BUSINESS_HTTP_BUDGET")
        _reject(time.monotonic() < self.deadline, "SCENARIO_DEADLINE_EXCEEDED")
        if method == "POST":
            _reject(not self.stop_writes and self.post_count < LIMITS["config_post_requests"],
                    "WRITE_AFTER_STOP")
            self.post_count += 1
        if reconcile:
            _reject(method == "GET" and kind in ("reconcile_current", "reconcile_history"),
                    "RECONCILE_READ_NOT_ALLOWLISTED")
        else:
            _reject(not kind.startswith("reconcile_"), "RECONCILE_MODE_REQUIRED")
        timeout = min(float(LIMITS["request_seconds"]), self.deadline - time.monotonic())
        item = {"seq": len(self.observations) + 1, "kind": kind,
                "method": method, "path": path, "request": request_body,
                "status": None, "content_type": None, "response": None,
                "response_body_sha256": None, "elapsed_ms": 0,
                "transport_error": None}
        started = time.monotonic()
        connection = None
        try:
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
            headers = {"Accept": "application/json", "Connection": "close"}
            body = None
            if method == "POST":
                body = canonical(request_body)
                headers["Content-Type"] = "application/json"
                headers["X-API-Key"] = self._api_key
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            item["status"] = response.status
            content_type = response.getheader("Content-Type")
            item["content_type"] = content_type.lower() if isinstance(content_type, str) else None
            raw = response.read(65537)
            if len(raw) > 65536:
                item["transport_error"] = "RESPONSE_TOO_LARGE"
            elif 300 <= response.status < 400:
                item["transport_error"] = "REDIRECT_FORBIDDEN"
            elif not item["content_type"] or not item["content_type"].startswith("application/json"):
                item["transport_error"] = "NON_JSON_RESPONSE"
            else:
                parsed = strict_json(raw)
                if type(parsed) not in (dict, list):
                    item["transport_error"] = "JSON_TOP_LEVEL_INVALID"
                else:
                    item["response"] = parsed
                    item["response_body_sha256"] = digest(parsed)
        except TimeoutError:
            item["transport_error"] = "TIMEOUT"
        except (ConnectionError, OSError, http.client.HTTPException):
            item["transport_error"] = "CONNECTION_OR_PROTOCOL_ERROR"
        except Exception:
            item["transport_error"] = "RESPONSE_PARSE_ERROR"
        finally:
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            item["elapsed_ms"] = max(0, int((time.monotonic() - started) * 1000))
            self.observations.append(item)
        if method == "POST" and (item["status"] != 200 or item["transport_error"] is not None):
            self.stop_writes = True
        return item

    def initial_state_valid(self) -> bool:
        current = self.request("initial_current")
        history = self.request("initial_history")
        current_ok, _ = _api_response(current, 404, 4041, "none")
        history_ok, rows = _api_response(history, 200, 0, "list")
        return current_ok and history_ok and rows == []

    def final_readback(self, *, reconcile: bool = False) -> list[dict]:
        if reconcile:
            return [self.request(kind, reconcile=True)
                    for kind in ("reconcile_current", "reconcile_history")]
        return [self.request(kind) for kind in ("final_current", "final_history", "final_list")]


class ConfigLiveBusiness:
    """Maps the fixed three registered tools to read-only GETs and two guarded POSTs."""
    def __init__(self, contracts: dict, client: ConfigLiveHttp):
        self.contracts, self.effect, self.client = contracts, contracts["effect"], client
        self.inspect_ok = False
        self.create_ok = False
        self.update_ok = False
        self.call_count = 0

    def invoke(self, name: str, arguments: dict) -> dict:
        self.call_count += 1
        _reject(self.call_count <= LIMITS["sdk_tool_calls"], "TOOL_CALL_BUDGET", "AGENT")
        _reject(name in TOOLS and type(arguments) is dict, "TOOL_NOT_ALLOWLISTED", "AGENT")
        expected_keys = set(TOOL_ARGUMENT_KEYS[name])
        _reject(set(arguments) == expected_keys, "TOOL_ARGUMENT_SHAPE", "AGENT")
        if name == "inspect_config":
            observation = self.client.request("inspect_config")
            if observation["status"] == 404:
                ok, _ = _api_response(observation, 404, 4041, "none")
                if ok:
                    self.inspect_ok = True
                    return {"state": "ABSENT"}
            else:
                ok, item = _api_response(observation, 200, 0, "item")
                if (ok and (_valid_item(item, self.effect, 1, self.effect["initial_value"])
                            or _valid_item(item, self.effect, 2, self.effect["required_value"]))):
                    return {"state": "PRESENT", "version": item.get("version"),
                            "value": item.get("value")}
            self.client.stop_writes = True
            return {"state": "UNKNOWN", "reason": "READ_CONTRACT_FAILED"}
        if name == "create_config_v1":
            _reject(arguments == {"value": self.effect["initial_value"]},
                    "CREATE_ARGUMENTS_REJECTED", "AGENT")
            _reject(self.inspect_ok and not self.create_ok and not self.client.stop_writes,
                    "CREATE_WITHOUT_CONFIRMED_ABSENCE", "AGENT")
            observation = self.client.request("create_config_v1")
            ok, item = _api_response(observation, 200, 0, "item")
            if ok and _valid_item(item, self.effect, 1, self.effect["initial_value"]):
                self.create_ok = True
                return {"status": "COMMITTED", "version": 1, "value": self.effect["initial_value"]}
            self.client.stop_writes = True
            return {"status": "UNKNOWN_OUTCOME" if observation["status"] is None
                    or observation["transport_error"] else "REJECTED",
                    "reason": observation["transport_error"] or "CREATE_RESPONSE_CONTRACT_FAILED"}
        _reject(name == "update_config_v2", "TOOL_NOT_ALLOWLISTED", "AGENT")
        _reject(type(arguments.get("expected_version")) is int
                and arguments == {"expected_version": 1, "value": self.effect["required_value"]},
                "UPDATE_ARGUMENTS_REJECTED", "AGENT")
        _reject(self.create_ok and not self.update_ok and not self.client.stop_writes,
                "UPDATE_WITHOUT_CONFIRMED_CREATE", "AGENT")
        observation = self.client.request("update_config_v2")
        ok, item = _api_response(observation, 200, 0, "item")
        if ok and _valid_item(item, self.effect, 2, self.effect["required_value"]):
            self.update_ok = True
            return {"status": "COMMITTED", "version": 2, "value": self.effect["required_value"]}
        self.client.stop_writes = True
        return {"status": "UNKNOWN_OUTCOME" if observation["status"] is None
                or observation["transport_error"] else "REJECTED",
                "reason": observation["transport_error"] or "UPDATE_RESPONSE_CONTRACT_FAILED"}


class ConfigLiveMemoryBackend:
    """Explicit in-memory diagnostic backend; never used for a live evidence claim."""
    def __init__(self):
        self.version = 0
        self.value = None
        self.calls = []

    def invoke(self, name: str, arguments: dict) -> dict:
        self.calls.append({"name": name, "arguments": arguments})
        if name == "inspect_config":
            return ({"state": "ABSENT"} if self.version == 0 else
                    {"state": "PRESENT", "version": self.version, "value": self.value})
        if name == "create_config_v1" and self.version == 0 and arguments == {"value": "rpf53-v1"}:
            self.version, self.value = 1, "rpf53-v1"
            return {"status": "COMMITTED", "version": 1, "value": self.value}
        if name == "update_config_v2" and self.version == 1 \
                and type(arguments.get("expected_version")) is int and arguments == {
                "expected_version": 1, "value": "rpf53-v2"}:
            self.version, self.value = 2, "rpf53-v2"
            return {"status": "COMMITTED", "version": 2, "value": self.value}
        raise LiveRuntimeRejected("FIXTURE_TOOL_CONTRACT", "AGENT")


def _validate_tool_registry(tools: object) -> str:
    _reject(type(tools) is list and len(tools) == 3, "SDK_TOOL_REGISTRY", "AGENT")
    by_name = {}
    for entry in tools:
        _reject(type(entry) is dict and set(entry) == {"type", "function"}
                and entry["type"] == "function" and type(entry["function"]) is dict,
                "SDK_TOOL_SCHEMA_SHAPE", "AGENT")
        function = entry["function"]
        _reject(set(function) <= {"name", "description", "parameters", "strict"}
                and function.get("name") in TOOLS and "parameters" in function,
                "SDK_TOOL_SCHEMA_SHAPE", "AGENT")
        _reject("strict" not in function or function["strict"] is True,
                "SDK_TOOL_SCHEMA_SHAPE", "AGENT")
        name, params = function["name"], function["parameters"]
        _reject(name not in by_name and type(params) is dict
                and set(params) <= {"type", "properties", "required", "additionalProperties", "title"}
                and params.get("type") == "object"
                and params.get("additionalProperties") is False
                and type(params.get("properties")) is dict,
                "SDK_TOOL_SCHEMA_SHAPE", "AGENT")
        expected = set(TOOL_ARGUMENT_KEYS[name])
        _reject(set(params["properties"]) == expected, "SDK_TOOL_SCHEMA_PROPERTIES", "AGENT")
        required = params.get("required", [])
        _reject(type(required) is list and len(required) == len(expected)
                and set(required) == expected, "SDK_TOOL_SCHEMA_REQUIRED", "AGENT")
        expected_types = {"expected_version": "integer", "value": "string"}
        for key, schema in params["properties"].items():
            _reject(type(schema) is dict and schema.get("type") == expected_types[key]
                    and set(schema) <= {"type", "title", "description"},
                    "SDK_TOOL_SCHEMA_PROPERTY_TYPE", "AGENT")
        by_name[name] = entry
    _reject(set(by_name) == set(TOOLS), "SDK_TOOL_REGISTRY", "AGENT")
    return digest([by_name[name] for name in TOOLS])


def _tool_schema_summary(tools: object) -> dict:
    allowed_entry = {"type", "function"}
    allowed_function = {"name", "description", "parameters", "strict"}
    allowed_parameters = {"type", "properties", "required", "additionalProperties", "title"}
    if type(tools) is not list:
        return {"container": "NOT_LIST", "count": None, "entries": []}
    entries = []
    for entry in tools[:8]:
        function = entry.get("function") if type(entry) is dict else None
        parameters = function.get("parameters") if type(function) is dict else None
        properties = parameters.get("properties") if type(parameters) is dict else None
        entries.append({
            "entry_type": "OBJECT" if type(entry) is dict else "OTHER",
            "entry_unknown_key_count": len(set(entry) - allowed_entry)
                if type(entry) is dict else None,
            "function_type": "OBJECT" if type(function) is dict else "OTHER",
            "function_unknown_key_count": len(set(function) - allowed_function)
                if type(function) is dict else None,
            "tool_name": function.get("name") if type(function) is dict
                and function.get("name") in TOOLS else "UNKNOWN",
            "strict": "OMITTED" if type(function) is not dict or "strict" not in function
                else "TRUE" if function.get("strict") is True else "INVALID",
            "parameters_type": "OBJECT" if type(parameters) is dict else "OTHER",
            "parameters_unknown_key_count": len(set(parameters) - allowed_parameters)
                if type(parameters) is dict else None,
            "property_key_count": len(properties) if type(properties) is dict else None,
            "unknown_property_key_count": len(set(properties) -
                {"expected_version", "value"}) if type(properties) is dict else None,
        })
    return {"container": "LIST", "count": len(tools), "entries": entries}


def _validate_provider_response(data: object, *, fixture: bool = False) -> tuple[dict, dict, list[dict]]:
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
    _reject(usage_raw["completion_tokens"] <= LIMITS["max_output_tokens_per_request"],
            "PROVIDER_OUTPUT_TOKEN_LIMIT", "PROVIDER")
    usage = {key: usage_raw[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    return data, message, calls


class ConfigLiveHost:
    """One loopback broker between the real SDK child, Provider and bounded Host tools."""
    def __init__(self, contracts: dict, ledger: ProviderLedger,
                 business: ConfigLiveBusiness | ConfigLiveMemoryBackend,
                 *, fixture: bool = False, api_key: str | None = None,
                 expected_tool_schema_sha256: str | None = None,
                 fixture_failure_code: str | None = None):
        validate_contracts(contracts, require_live=not fixture)
        _reject(fixture_failure_code is None or (fixture and
                re.fullmatch(r"[A-Z0-9_]{1,64}", fixture_failure_code) is not None),
                "FIXTURE_FAILURE_CODE")
        self.contracts, self.ledger, self.business = contracts, ledger, business
        self.fixture, self.api_key = fixture, api_key
        self.expected_tool_schema_sha256 = expected_tool_schema_sha256
        self.fixture_failure_code = fixture_failure_code
        self.tool_schema_sha256: str | None = None
        self.tool_schema_summary: dict | None = None
        self.tool_definitions: list[dict] | None = None
        self.runtime: dict | None = None
        self.failure: dict | None = None
        self.intents: dict[str, dict] = {}
        self.tool_trace: list[dict] = []
        self.tool_returns: dict[str, dict] = {}
        self.provider_responses: list[dict] = []
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.fixture_index = 0
        self.request_started = time.monotonic()

    @property
    def port(self) -> int:
        _reject(self._server is not None, "HOST_NOT_STARTED")
        return int(self._server.server_port)

    def start(self, bind_port: int | None = None) -> None:
        _reject(self._server is None, "HOST_ALREADY_STARTED")
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                return

            def _send(self, status: int, value: dict):
                raw = canonical(value)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(raw)
                self.close_connection = True

            def do_POST(self):
                try:
                    _reject(self.client_address[0] == "127.0.0.1"
                            and self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
                            and self.headers.get("Origin") is None
                            and self.headers.get("Authorization") == "Bearer " + owner.token,
                            "HOST_AUTH_OR_LOOPBACK_REJECTED")
                    text_length = self.headers.get("Content-Length", "")
                    _reject(text_length.isdigit() and 0 < int(text_length) <= 65536,
                            "HOST_REQUEST_SIZE")
                    raw = self.rfile.read(int(text_length))
                    _reject(len(raw) == int(text_length), "HOST_REQUEST_TRUNCATED")
                    body = strict_json(raw)
                    if self.path == "/ready":
                        result = owner._ready(body)
                    elif self.path == "/tool":
                        result = owner._tool(body)
                    elif self.path == "/v1/chat/completions":
                        result = owner._completion(body)
                    else:
                        raise LiveRuntimeRejected("HOST_ROUTE_REJECTED")
                    self._send(200, result)
                except Exception as exc:
                    code = getattr(exc, "code", "HOST_PROTOCOL_ERROR")
                    domain = getattr(exc, "domain", "PLATFORM")
                    owner.failure = owner.failure or {"domain": domain, "code": code}
                    try:
                        self._send(400 if domain != "PROVIDER" else 502, {"error": {"code": code}})
                    except OSError:
                        pass

        self.token = secrets.token_urlsafe(32)
        selected_port = bind_port or self.contracts["experiment"].get("agent_host_port")
        _reject(type(selected_port) is int and 1 <= selected_port <= 65535,
                "HOST_PORT_CONTRACT")
        self._server = HTTPServer(("127.0.0.1", selected_port), Handler)
        self._server.timeout = 0.25
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _ready(self, body: object) -> dict:
        _reject(self.runtime is None and type(body) is dict
                and set(body) == {"framework", "version", "openai_version", "pid",
                                  "sdk_source_sha256", "openai_source_sha256",
                                  "sdk_site_root_binding_sha256",
                                  "python_runtime_mapping_sha256"}
                and body.get("framework") == SDK_NAME and body.get("version") == SDK_VERSION
                and body.get("openai_version") == OPENAI_VERSION
                and type(body.get("pid")) is int and body["pid"] > 0
                and body.get("sdk_source_sha256") == SDK_CORE_SHA256
                and body.get("openai_source_sha256") == self.contracts[
                    "execution"]["framework"]["identity"].get("openai_core_sha256")
                and body.get("sdk_site_root_binding_sha256") == self.contracts[
                    "execution"]["framework"]["identity"].get("sdk_site_root_binding_sha256")
                and body.get("python_runtime_mapping_sha256") == self.contracts[
                    "execution"]["framework"]["identity"].get("python_runtime_mapping_sha256"),
                "SDK_READY_IDENTITY")
        self.runtime = dict(body)
        return {"status": "AGENT_RUNTIME_CONNECTED"}

    def _tool(self, body: object) -> dict:
        _reject(self.runtime is not None and type(body) is dict
                and set(body) == {"call_id", "name", "arguments"}, "HOST_CALL_FIELDS")
        call_id, name, arguments = body["call_id"], body["name"], body["arguments"]
        _reject(type(call_id) is str and call_id in self.intents
                and type(arguments) is dict, "TOOL_CALL_UNKNOWN", "AGENT")
        intent = self.intents[call_id]
        _reject(call_id not in self.tool_returns and intent["name"] == name
                and digest(arguments) == intent["arguments_sha256"],
                "TOOL_INTENT_BINDING_OR_REPLAY", "AGENT")
        _reject(len(self.tool_trace) < LIMITS["sdk_tool_calls"], "TOOL_CALL_BUDGET", "AGENT")
        result = self.business.invoke(name, arguments)
        item = {"sequence": len(self.tool_trace) + 1,
                "provider_response_id": intent["response_id"], "call_id": call_id,
                "name": name, "arguments": arguments,
                "arguments_sha256": digest(arguments), "result": result,
                "result_sha256": digest(result), "returned_in_request": None,
                "http_observation_seq": (self.business.client.observations[-1]["seq"]
                                         if isinstance(self.business, ConfigLiveBusiness) else None)}
        self.tool_trace.append(item)
        self.tool_returns[call_id] = item
        return result

    def _verify_tool_returns(self, body: dict) -> list[dict]:
        messages = body.get("messages")
        _reject(type(messages) is list and 1 <= len(messages) <= 64,
                "MODEL_MESSAGES", "AGENT")
        observed: dict[str, dict] = {}
        for message in messages:
            if type(message) is not dict or message.get("role") != "tool":
                continue
            _reject(set(message) <= {"role", "content", "tool_call_id", "name"}
                    and type(message.get("tool_call_id")) is str
                    and type(message.get("content")) is str,
                    "SDK_TOOL_RETURN_MESSAGE", "AGENT")
            call_id = message["tool_call_id"]
            _reject(call_id not in observed and call_id in self.tool_returns,
                    "SDK_TOOL_RETURN_LINEAGE", "AGENT")
            parsed = strict_json(message["content"].encode("utf-8"))
            expected = self.tool_returns[call_id]["result"]
            _reject(parsed == expected, "SDK_TOOL_RETURN_MISMATCH", "AGENT")
            observed[call_id] = self.tool_returns[call_id]
        _reject(set(observed) == set(self.tool_returns), "SDK_TOOL_RETURN_MISSING", "AGENT")
        return [{"call_id": call_id, "result_sha256": item["result_sha256"]}
                for call_id, item in observed.items()]

    def _completion(self, body: object) -> dict:
        _reject(self.runtime is not None and type(body) is dict, "SDK_NOT_READY")
        _reject(time.monotonic() - self.request_started < LIMITS["scenario_seconds"],
                "SCENARIO_DEADLINE_EXCEEDED")
        allowed = {"model", "messages", "tools", "tool_choice", "parallel_tool_calls",
                   "max_tokens", "max_completion_tokens", "stream", "thinking", "temperature"}
        expected_model = "rpf53-fixture-only" if self.fixture else PROVIDER_MODEL
        _reject(set(body) <= allowed and body.get("model") == expected_model
                and body.get("stream", False) is False
                and body.get("tool_choice", "auto") == "auto"
                and body.get("parallel_tool_calls") is False,
                "MODEL_REQUEST_CONFIG", "AGENT")
        self.tool_schema_summary = _tool_schema_summary(body.get("tools"))
        tool_hash = _validate_tool_registry(body.get("tools"))
        _reject(self.tool_schema_sha256 is None or self.tool_schema_sha256 == tool_hash,
                "SDK_TOOL_SCHEMA_CHANGED", "AGENT")
        if self.expected_tool_schema_sha256 is not None:
            _reject(self.expected_tool_schema_sha256 == tool_hash,
                    "SDK_TOOL_SCHEMA_CHANGED", "AGENT")
        self.tool_schema_sha256 = tool_hash
        if self.tool_definitions is None:
            self.tool_definitions = body["tools"]
        else:
            _reject(self.tool_definitions == body["tools"], "SDK_TOOL_SCHEMA_CHANGED", "AGENT")
        returns = self._verify_tool_returns(body)
        request = dict(body)
        request.pop("max_completion_tokens", None)
        request.update(max_tokens=LIMITS["max_output_tokens_per_request"],
                       thinking={"type": "disabled"})
        _reject(len(self.ledger.data["requests"]) < LIMITS["provider_https_requests"],
                "PROVIDER_REQUEST_BUDGET", "PROVIDER")
        if self.fixture:
            if self.fixture_failure_code is not None:
                raise LiveRuntimeRejected(self.fixture_failure_code, "PROVIDER")
            data = self._fixture_response(request)
        else:
            _reject(type(self.api_key) is str and bool(self.api_key), "DEEPSEEK_KEY_UNAVAILABLE", "PROVIDER")
            record = self.ledger.reserve(request, returns)
            try:
                data = self._provider_request(request)
            except LiveRuntimeRejected as exc:
                self.ledger.fail_unknown(record, exc.code)
                raise
            except Exception:
                self.ledger.fail_unknown(record, "PROVIDER_TRANSPORT_ERROR")
                raise LiveRuntimeRejected("PROVIDER_TRANSPORT_ERROR", "PROVIDER") from None
            try:
                data, message, calls = _validate_provider_response(data)
                self.ledger.received(record, data)
            except LiveRuntimeRejected as exc:
                if record["status"] == "RESERVED_USAGE_UNKNOWN":
                    self.ledger.fail_unknown(record, exc.code)
                raise
        if self.fixture:
            data, message, calls = _validate_provider_response(data, fixture=True)
        response_id = data["id"]
        _reject(response_id not in {item["response_id"] for item in self.provider_responses},
                "PROVIDER_RESPONSE_ID_REUSED", "PROVIDER")
        call_items = []
        for call in calls:
            args = strict_json(call["function"]["arguments"].encode("utf-8"))
            _reject(type(args) is dict and set(args) == set(TOOL_ARGUMENT_KEYS[call["function"]["name"]]),
                    "PROVIDER_TOOL_ARGUMENTS", "AGENT")
            _reject(call["id"] not in self.intents and len(self.intents) < LIMITS["sdk_tool_calls"],
                    "TOOL_CALL_ID_DUPLICATE_OR_BUDGET", "AGENT")
            intent = {"response_id": response_id, "call_id": call["id"],
                      "name": call["function"]["name"],
                      "arguments_sha256": digest(args), "arguments": args}
            self.intents[call["id"]] = intent
            call_items.append({"call_id": call["id"], "name": intent["name"],
                               "arguments_sha256": intent["arguments_sha256"]})
        if not self.fixture:
            record["tool_call_ids"] = [item["call_id"] for item in call_items]
            record["tool_schema_sha256"] = tool_hash
            record["returned_tool_ids"] = [item["call_id"] for item in returns]
            self.ledger.checkpoint()
        self.provider_responses.append({"response_id": response_id,
            "model": data["model"], "tool_calls": call_items,
            "usage": {key: data["usage"][key] for key in (
                "prompt_tokens", "completion_tokens", "total_tokens")},
            "request_sha256": digest(request), "tool_returns": returns})
        for item in returns:
            returned = self.tool_returns[item["call_id"]]
            if returned["returned_in_request"] is None:
                returned["returned_in_request"] = len(self.provider_responses)
        if self.fixture:
            return data
        # Upstream content is passed through only to the pinned SDK child. It is not persisted.
        return data

    def _provider_request(self, body: dict) -> dict:
        try:
            connection = http.client.HTTPSConnection(
                "api.deepseek.com", timeout=LIMITS["request_seconds"],
                context=ssl.create_default_context())
            connection.request("POST", PROVIDER_PATH, canonical(body), {
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json", "Accept": "application/json",
                "Connection": "close"})
            response = connection.getresponse()
            status = response.status
            raw = response.read(262145)
            connection.close()
        except Exception:
            try:
                connection.close()
            except Exception:
                pass
            raise LiveRuntimeRejected("PROVIDER_TRANSPORT_ERROR", "PROVIDER") from None
        _reject(len(raw) <= 262144, "PROVIDER_RESPONSE_SIZE", "PROVIDER")
        _reject(status == 200, "PROVIDER_HTTP_STATUS_" + str(status), "PROVIDER")
        _reject(response.getheader("Content-Type", "").lower().startswith("application/json"),
                "PROVIDER_CONTENT_TYPE", "PROVIDER")
        return strict_json(raw)

    def _fixture_response(self, request: dict) -> dict:
        names = ("inspect_config", "create_config_v1", "update_config_v2")
        index = self.fixture_index
        self.fixture_index += 1
        if index < 3:
            name = names[index]
            args = ({"value": "rpf53-v1"} if index == 1 else
                    {"expected_version": 1, "value": "rpf53-v2"} if index == 2 else {})
            call = {"id": f"call_rpf53_fixture_{index + 1}", "type": "function",
                    "function": {"name": name, "arguments": canonical(args).decode("utf-8")}}
            message = {"role": "assistant", "content": None, "tool_calls": [call]}
            finish_reason = "tool_calls"
        else:
            message = {"role": "assistant", "content": "fixture-complete", "tool_calls": []}
            finish_reason = "stop"
        return {"id": f"chatcmpl-rpf53-fixture-{index + 1}",
                "object": "chat.completion", "created": 1,
                "model": "rpf53-fixture-only",
                "choices": [{"index": 0, "message": message,
                             "finish_reason": finish_reason}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

    def summary(self) -> dict:
        return {"fixture_only": self.fixture,
                "runtime": self.runtime,
                "tool_schema_sha256": self.tool_schema_sha256,
                "provider_responses": self.provider_responses,
                "tool_calls": self.tool_trace,
                "failure": self.failure,
                "ledger_usage": self.ledger.usage()}

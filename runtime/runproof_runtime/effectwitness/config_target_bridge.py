"""Loopback-only config-center HTTP host and scripted OpenAI-compatible fixtures."""
from __future__ import annotations

import hashlib
import http.client
import json
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import quote

from .config_target_contracts import (
    HTTP_ORDER, canonical, digest, expected_path, expected_request, fixture_response, require,
    strict_json, validate_contracts,
)


class TargetBridgeRejected(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _reject(condition: bool, code: str) -> None:
    if not condition:
        raise TargetBridgeRejected(code)


def _api_data(observation: dict, status: int, code: int, kind: str):
    if (observation.get("status") != status
            or observation.get("transport_error") is not None
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
    if kind == "none" and data is not None:
        return False, None
    if kind == "item" and type(data) is not dict:
        return False, None
    if kind == "list" and type(data) is not list:
        return False, None
    return True, data


def _config_item(data: dict, effect: dict, *, version: int, value: str) -> bool:
    updated = data.get("updatedAt") if type(data) is dict else None
    try:
        timestamp = datetime.fromisoformat(updated.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False
    return (set(data) == {"app", "env", "key", "value", "description", "version", "updatedAt"}
            and all(data[k] == effect[k] for k in ("app", "env", "key"))
            and data["value"] == value and data["description"] is None
            and type(data["version"]) is int and data["version"] == version
            and timestamp.tzinfo is not None)


class BoundedConfigHttp:
    """The only component holding the business API key and Java service URL."""

    def __init__(self, contracts: dict, api_key: str, *, deadline: float | None = None):
        validate_contracts(contracts)
        _reject(isinstance(api_key, str)
                and re.fullmatch(r"[A-Za-z0-9._~-]{24,128}", api_key) is not None,
                "API_KEY_SHAPE")
        self.contracts = contracts
        self.effect = contracts["effect"]
        self.port = contracts["experiment"]["java_port"]
        self._api_key = api_key
        self.deadline = deadline
        self.observations: list[dict] = []
        self.stop_writes = False
        self._reconcile_index = 0

    def request(self, kind: str, *, credential: bool = False,
                reconcile: bool = False) -> dict:
        index = len(self.observations)
        if reconcile:
            allowed_reads = ("final_current", "final_history", "final_list")
            _reject(not credential and self.stop_writes and kind in allowed_reads
                    and kind == allowed_reads[self._reconcile_index]
                    and index < len(HTTP_ORDER), "RECONCILE_READ_NOT_ALLOWLISTED")
            self._reconcile_index += 1
        else:
            _reject(index < len(HTTP_ORDER) and kind == HTTP_ORDER[index],
                    "HTTP_ORDER_OR_BUDGET")
        _reject(not (self.stop_writes and credential), "WRITE_AFTER_STOP")
        method, path = expected_path(self.effect, kind)
        request_body = expected_request(self.effect, kind)
        if credential:
            _reject(method == "POST" and kind in ("create_config_v1", "update_config_v2"),
                    "CREDENTIAL_SCOPE")
        else:
            _reject(method == "GET", "AUTHORITY_MUST_BE_READ_ONLY")
        timeout = 5.0
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            _reject(remaining > 0, "SCENARIO_DEADLINE_EXCEEDED")
            timeout = min(timeout, remaining)
        started = time.monotonic()
        item = {
            "seq": index + 1, "kind": kind, "method": method, "path": path,
            "request": request_body, "status": None, "content_type": None,
            "response": None, "response_body_sha256": None,
            "elapsed_ms": 0, "transport_error": None,
        }
        connection = None
        try:
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
            headers = {"Accept": "application/json", "Connection": "close"}
            body = None
            if method == "POST":
                body = canonical(request_body)
                headers["Content-Type"] = "application/json"
                if credential:
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
        if credential and (item["status"] != 200 or item["transport_error"] is not None):
            self.stop_writes = True
        return item


class ConfigTargetAuthorityReader:
    """Independent, credential-free GET path sharing only the bounded counter."""

    def __init__(self, client: BoundedConfigHttp):
        self._client = client

    def current(self, kind: str, *, reconcile: bool = False) -> dict:
        _reject(kind in ("initial_current", "final_current"), "AUTHORITY_KIND")
        return self._client.request(kind, reconcile=reconcile)

    def history(self, kind: str, *, reconcile: bool = False) -> dict:
        _reject(kind in ("initial_history", "final_history"), "AUTHORITY_KIND")
        return self._client.request(kind, reconcile=reconcile)

    def list(self, *, reconcile: bool = False) -> dict:
        return self._client.request("final_list", reconcile=reconcile)


class ConfigTargetToolHost:
    """Three fixed tool calls bound to exactly three HTTP operations."""

    def __init__(self, contracts: dict, client: BoundedConfigHttp):
        validate_contracts(contracts)
        self.contracts = contracts
        self.client = client
        self.tool_trace: list[dict] = []

    def invoke(self, call_id: str, name: str, arguments: dict,
               completion_round: int) -> dict:
        calls = self.contracts["execution"]["tool_calls"]
        index = len(self.tool_trace)
        _reject(index < len(calls), "TOOL_CALL_BUDGET")
        expected = calls[index]
        _reject(call_id == expected["call_id"] and name == expected["name"]
                and arguments == expected["arguments"]
                and completion_round == index + 1, "TOOL_INTENT_REJECTED")
        kind = expected["name"]
        if kind == "inspect_config":
            observation = self.client.request("inspect_config")
            allowed, _ = _api_data(observation, 404, 4041, "none")
        else:
            if kind == "create_config_v1":
                inspected = (self.client.observations[2]
                             if len(self.client.observations) >= 3 else {})
                inspect_ok, _ = _api_data(inspected, 404, 4041, "none")
                _reject(inspect_ok and not self.client.stop_writes,
                        "CREATE_WITHOUT_INSPECT")
            if kind == "update_config_v2":
                created = (self.client.observations[3]
                           if len(self.client.observations) >= 4 else {})
                create_ok, create_data = _api_data(created, 200, 0, "item")
                create_ok = (create_ok and _config_item(
                    create_data, self.client.effect, version=1, value="rpf52-v1"))
                _reject(create_ok and not self.client.stop_writes,
                        "UPDATE_WITHOUT_CREATE")
            observation = self.client.request(kind, credential=True)
            allowed, data = _api_data(observation, 200, 0, "item")
            if allowed:
                expected_version, expected_value = (
                    (1, "rpf52-v1") if kind == "create_config_v1" else (2, "rpf52-v2"))
                allowed = _config_item(data, self.client.effect,
                                       version=expected_version, value=expected_value)
        result = {"http_status": observation["status"], "response": observation["response"]}
        trace = {
            "seq": index + 1, "call_id": call_id, "name": name,
            "arguments": arguments, "arguments_sha256": digest(arguments),
            "completion_round": completion_round,
            "http_seq": observation["seq"], "http_response_sha256": observation["response_body_sha256"],
            "tool_return_sha256": digest(result), "tool_return": result,
            "accepted": bool(allowed),
        }
        self.tool_trace.append(trace)
        if not allowed:
            self.client.stop_writes = True
        _reject(allowed, "TARGET_HTTP_TOOL_FAILED")
        return result


class ConfigTargetFixtureHost:
    """One local completion endpoint; it returns four fixed SDK model responses."""

    FIXTURE_TOKEN = "rpf52-loopback-fixture-token"

    def __init__(self, contracts: dict, tool_host: ConfigTargetToolHost,
                 sdk_source_sha256: str, openai_source_sha256: str):
        validate_contracts(contracts)
        self.contracts = contracts
        self.tool_host = tool_host
        self.sdk_source_sha256 = sdk_source_sha256
        self.openai_source_sha256 = openai_source_sha256
        self.runtime: dict | None = None
        self.completions: list[dict] = []
        self.client_sources: set[str] = set()
        self.failure: str | None = None
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        _reject(self._server is not None, "FIXTURE_HOST_NOT_STARTED")
        return int(self._server.server_port)

    def start(self) -> None:
        _reject(self._server is None, "FIXTURE_HOST_ALREADY_STARTED")
        host = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, _format, *args):
                return

            def _send(self, status: int, value: dict):
                raw = canonical(value)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(raw)
                self.close_connection = True

            def do_POST(self):
                try:
                    host.client_sources.add(self.client_address[0])
                    _reject(self.client_address[0] == "127.0.0.1", "FIXTURE_CLIENT_ADDRESS")
                    _reject(self.headers.get("Authorization")
                            == "Bearer " + host.FIXTURE_TOKEN, "FIXTURE_AUTH")
                    _reject(self.headers.get("Host")
                            == f"127.0.0.1:{self.server.server_port}", "FIXTURE_HOST_HEADER")
                    _reject(self.headers.get("Origin") is None, "FIXTURE_ORIGIN")
                    _reject(self.headers.get("Content-Type", "").lower().startswith(
                            "application/json"), "FIXTURE_CONTENT_TYPE")
                    length_text = self.headers.get("Content-Length", "")
                    _reject(length_text.isdigit() and 0 < int(length_text) <= 65536,
                            "FIXTURE_REQUEST_SIZE")
                    value = strict_json(self.rfile.read(int(length_text)))
                    if self.path == "/ready":
                        result = host._ready(value)
                    elif self.path == "/tool":
                        result = host._tool(value)
                    elif self.path == "/v1/chat/completions":
                        result = host._completion(value)
                    else:
                        raise TargetBridgeRejected("FIXTURE_ROUTE")
                    self._send(200, result)
                except Exception as exc:
                    code = getattr(exc, "code", "FIXTURE_REQUEST_REJECTED")
                    host.failure = host.failure or code
                    try:
                        self._send(400, {"error": host.failure})
                    except OSError:
                        pass

            def do_GET(self):
                self._send(405, {"error": "FIXTURE_METHOD"})

        self._server = HTTPServer(("127.0.0.1", self.contracts["experiment"]["agent_host_port"]), Handler)
        self._server.timeout = 0.25
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={"poll_interval": 0.1}, daemon=True)
        self._thread.start()
        _reject(self._server.server_address[0] == "127.0.0.1", "FIXTURE_BIND_ADDRESS")

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            thread = self._thread
            thread.join(timeout=3)
            self._thread = None
            _reject(not thread.is_alive(), "FIXTURE_THREAD_DID_NOT_STOP")

    def _ready(self, body: Any) -> dict:
        expected_fields = {"framework", "version", "openai_version", "python_version",
                           "pid", "sdk_source_sha256", "openai_source_sha256"}
        _reject(type(body) is dict and set(body) == expected_fields and self.runtime is None,
                "SDK_READY_FIELDS")
        _reject(body["framework"] == "pydantic-ai-slim" and body["version"] == "2.57.0"
                and body["openai_version"] == "3.35.1"
                and body["sdk_source_sha256"] == self.sdk_source_sha256
                and body["openai_source_sha256"] == self.openai_source_sha256
                and type(body["pid"]) is int and body["pid"] > 0, "SDK_READY_IDENTITY")
        self.runtime = body
        return {"status": "SDK_RUNTIME_CONNECTED"}

    def _tool(self, body: Any) -> dict:
        _reject(self.runtime is not None and type(body) is dict
                and set(body) == {"call_id", "name", "arguments"}, "SDK_TOOL_PROTOCOL")
        return self.tool_host.invoke(body["call_id"], body["name"], body["arguments"],
                                     len(self.completions))

    def _completion(self, body: Any) -> dict:
        _reject(self.runtime is not None and self.failure is None, "SDK_NOT_READY_OR_FAILED")
        _reject(len(self.completions) < 5, "FIXTURE_COMPLETION_BUDGET")
        allowed_fields = {"model", "messages", "tools", "tool_choice",
                          "parallel_tool_calls", "max_tokens", "max_completion_tokens",
                          "stream", "thinking", "temperature"}
        _reject(type(body) is dict and set(body) <= allowed_fields
                and body.get("model") == "rpf52-fixture"
                and body.get("stream") is False
                and body.get("tool_choice", "auto") == "auto"
                and body.get("parallel_tool_calls") is False, "MODEL_REQUEST_CONFIG")
        messages = body.get("messages")
        _reject(type(messages) is list, "MODEL_MESSAGES")
        self._verify_registry(body.get("tools"))
        schema_sha = digest(body["tools"])
        _reject(not self.completions
                or self.completions[-1]["tool_schema_sha256"] == schema_sha,
                "SDK_TOOL_SCHEMA_CHANGED")
        index = len(self.completions)
        expected_calls = self.contracts["execution"]["tool_calls"]
        assistant_calls, tool_returns = [], []
        for message in messages:
            if type(message) is not dict:
                continue
            if message.get("role") == "assistant":
                for call in message.get("tool_calls") or []:
                    if type(call) is dict and type(call.get("function")) is dict:
                        try:
                            args = strict_json(call["function"]["arguments"].encode("utf-8"))
                        except Exception:
                            raise TargetBridgeRejected("SDK_ASSISTANT_TOOL_ARGUMENTS") from None
                        assistant_calls.append({"call_id": call.get("id"),
                                                "name": call["function"].get("name"),
                                                "arguments": args})
            elif message.get("role") == "tool":
                content = message.get("content")
                try:
                    parsed = strict_json(content.encode("utf-8")) if isinstance(content, str) else None
                except Exception:
                    parsed = None
                tool_returns.append({"call_id": message.get("tool_call_id"), "value": parsed})
        _reject(assistant_calls == [
            {"call_id": c["call_id"], "name": c["name"], "arguments": c["arguments"]}
            for c in expected_calls[:index]], "SDK_TOOL_CALL_MESSAGE_LINEAGE")
        _reject(len(tool_returns) == index, "SDK_TOOL_RETURN_COUNT")
        return_ack = None
        for i, returned in enumerate(tool_returns):
            expected = self.tool_host.tool_trace[i]
            _reject(returned["call_id"] == expected["call_id"]
                    and returned["value"] == expected["tool_return"], "SDK_TOOL_RETURN_LINEAGE")
            return_ack = {"call_id": returned["call_id"],
                          "result_sha256": digest(returned["value"])}
        response = fixture_response(self.contracts, index)
        finish_reason = response["choices"][0]["finish_reason"]
        entry = {
            "seq": index + 1, "request_sha256": digest(body),
            "tool_schema_sha256": schema_sha,
            "assistant_calls_seen": len(assistant_calls),
            "tool_returns_seen": len(tool_returns), "last_tool_return": return_ack,
            "response_sha256": digest(response), "finish_reason": finish_reason,
        }
        self.completions.append(entry)
        return response

    @staticmethod
    def _verify_registry(tools: Any) -> None:
        _reject(type(tools) is list and len(tools) == 3, "SDK_TOOL_REGISTRY_COUNT")
        expected = [
            ("inspect_config", {}),
            ("create_config_v1", {"value": "string"}),
            ("update_config_v2", {"expected_version": "integer", "value": "string"}),
        ]
        for schema, (name, properties) in zip(tools, expected):
            _reject(type(schema) is dict and schema.get("type") == "function"
                    and type(schema.get("function")) is dict, "SDK_TOOL_SCHEMA_SHAPE")
            function = schema["function"]
            _reject(function.get("name") == name and type(function.get("parameters")) is dict,
                    "SDK_TOOL_SCHEMA_NAME")
            parameters = function["parameters"]
            _reject(parameters.get("type") == "object"
                    and parameters.get("additionalProperties") is False
                    and type(parameters.get("properties")) is dict
                    and set(parameters["properties"]) == set(properties)
                    and all(type(parameters["properties"][key]) is dict
                            and parameters["properties"][key].get("type") == kind
                            for key, kind in properties.items())
                    and type(parameters.get("required")) is list
                    and len(parameters["required"]) == len(properties)
                    and set(parameters["required"]) == set(properties),
                    "SDK_TOOL_SCHEMA_PARAMETERS")

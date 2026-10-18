"""Trusted controller, write-ahead budget and explicit external Target driver port."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Protocol

from ..models import RuntimeFailure
from .contracts import ROOT, canonical, digest, fields, identifier, owned_path, require
from .target_contracts import (CONFIG, FRAMEWORK, INSTRUCTIONS, OPENAI_CLIENT_VERSION,
                               SDK_CORE_SHA256, TOOLS, arguments_for, strict_json)


def save(path, value):
    path = owned_path(Path(path), task="rpf-48")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("wb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


class TaskLock:
    """Exclusive task-local controller ownership; crash leaves an explicit hold."""
    def __init__(self, path):
        self.path = owned_path(Path(path), task="rpf-48")

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("xb") as stream:
            stream.write(canonical({"owner_pid": os.getpid()}))
            stream.flush()
            os.fsync(stream.fileno())
        return self

    def __exit__(self, kind, *_):
        if kind is None:
            self.path.unlink()


class ProviderLedger:
    """Task-wide irreversible reservations. No reset and no automatic retry."""
    def __init__(self, path, *, fixture=False):
        self.path = owned_path(Path(path), task="rpf-48")
        self.fixture = fixture
        if self.path.exists():
            self.data = strict_json(self.path.read_bytes())
            fields(self.data, {"schema_version", "fixture", "started_at", "trials", "trial_status", "requests"}, "LEDGER_FIELDS")
            require(self.data["schema_version"] == "rpf48-budget-v1" and self.data["fixture"] is fixture,
                    "LEDGER_IDENTITY")
        else:
            self.data = {"schema_version": "rpf48-budget-v1", "fixture": fixture,
                         "started_at": time.time(), "trials": [], "trial_status": {}, "requests": []}
            self.checkpoint()
        self.validate()

    def checkpoint(self):
        save(self.path, self.data)

    def validate(self):
        require(type(self.data["trials"]) is list and len(self.data["trials"]) <= 2, "TRIAL_BUDGET")
        require(set(self.data["trial_status"]) == set(self.data["trials"])
                and all(v in ("RESERVED", "CLOSED", "QUARANTINED") for v in self.data["trial_status"].values()), "TRIAL_STATE_CORRUPT")
        require(type(self.data["requests"]) is list and len(self.data["requests"]) <= 6, "REQUEST_BUDGET")
        for index, record in enumerate(self.data["requests"], 1):
            require(record["attempt"] == index and record["status"] in ("RESERVED_USAGE_UNKNOWN", "RECEIVED"), "LEDGER_CORRUPT")
            if record["status"] == "RECEIVED":
                self.valid_usage(record["usage"], record["reservation_tokens"])
        require(self.usage()["confirmed_tokens"] <= 15000, "TOKEN_BUDGET")

    def start_trial(self, run_id):
        self.validate()
        require(time.time() - self.data["started_at"] < 2700, "TASK_WINDOW_EXHAUSTED")
        require(self.usage()["usage_known"], "PROVIDER_USAGE_UNKNOWN", "PROVIDER")
        require(all(v == "CLOSED" for v in self.data["trial_status"].values()), "PREVIOUS_TRIAL_UNRESOLVED")
        require(identifier(run_id) and run_id not in self.data["trials"] and len(self.data["trials"]) < 2,
                "TRIAL_BUDGET")
        self.data["trials"].append(run_id)
        self.data["trial_status"][run_id] = "RESERVED"
        self.checkpoint()

    def finish_trial(self, run_id, closed):
        require(self.data["trial_status"].get(run_id) == "RESERVED", "TRIAL_NOT_RESERVED")
        self.data["trial_status"][run_id] = "CLOSED" if closed else "QUARANTINED"
        self.checkpoint()

    def reserve(self, body, run_id, returns):
        self.validate()
        usage = self.usage()
        require(run_id in self.data["trials"] and time.time() - self.data["started_at"] < 2700, "TASK_WINDOW_EXHAUSTED")
        require(usage["usage_known"], "PROVIDER_USAGE_UNKNOWN", "PROVIDER")
        reserve = len(canonical(body)) + 1024 + 256
        require(len(self.data["requests"]) < 6 and usage["confirmed_tokens"] + reserve <= 15000,
                "PROVIDER_RESERVATION_EXHAUSTED", "PROVIDER")
        # Official peak CNY tariff, all input cache-miss: 2 input / 8 output per million.
        require(usage["estimated_cost_cny_upper"] + reserve * 8 / 1_000_000 <= 2,
                "COST_RESERVATION_EXHAUSTED", "PROVIDER")
        record = {"attempt": len(self.data["requests"]) + 1, "run_id": run_id,
                  "request_sha256": digest(body), "reservation_tokens": reserve,
                  "status": "RESERVED_USAGE_UNKNOWN", "tool_returns": returns,
                  "transport": "FIXTURE_TEST_ONLY" if self.fixture else "DeepSeek-HTTPS-no-retry"}
        self.data["requests"].append(record)
        self.checkpoint()  # persisted before opening the paid socket
        return record

    @staticmethod
    def valid_usage(usage, reservation):
        fields(usage, {"prompt_tokens", "completion_tokens", "total_tokens"}, "USAGE_FIELDS")
        require(all(type(v) is int and v >= 0 for v in usage.values())
                and usage["prompt_tokens"] + usage["completion_tokens"] == usage["total_tokens"]
                and usage["total_tokens"] <= reservation, "PROVIDER_USAGE_INVALID", "PROVIDER")

    def received(self, record, data):
        usage = {k: data.get("usage", {}).get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
        self.valid_usage(usage, record["reservation_tokens"])
        require(identifier(data.get("id")) and data.get("model") in ("deepseek-flash", "DeepSeek-V4.1-Flash-1017"), "PROVIDER_IDENTITY", "PROVIDER")
        record.update(status="RECEIVED", response_id=data["id"], returned_model=data["model"], usage=usage)
        self.checkpoint()

    def usage(self, run_id=None):
        records = [r for r in self.data["requests"] if run_id is None or r["run_id"] == run_id]
        known = all(r["status"] == "RECEIVED" for r in records)
        received = [r["usage"] for r in records if r["status"] == "RECEIVED"]
        inp, out = (sum(u[k] for u in received) for k in ("prompt_tokens", "completion_tokens"))
        return {"provider_http_attempts": 0 if self.fixture else len(records), "transport_requests": len(records),
                "tokens": inp + out if known else None, "confirmed_tokens": inp + out,
                "metering_kind": "FIXTURE_SYNTHETIC_NOT_BILLED" if self.fixture else "PROVIDER_REPORTED",
                "provider_tokens": 0 if self.fixture else inp + out if known else None,
                "input_tokens": inp, "output_tokens": out, "usage_known": known,
                "estimated_cost_cny_upper": 0.0 if self.fixture else (inp * 2 + out * 8) / 1_000_000 if known else None,
                "automatic_retries": 0, "trials": len(self.data["trials"])}


class TargetToolHost:
    """Only frozen intent may reach DomainPort; Authority is a separate read-only port."""
    def __init__(self, contracts, domain, authority):
        contracts.validate()
        self.contracts, self.domain, self.authority = contracts, domain, authority
        self.before = authority.read()
        authority.validate(self.before)
        self.intents, self.calls = {}, []
        self.pending, self.observed, self.mutated = False, False, False
        self.steps = 0
        self.started = time.monotonic()

    def step(self):
        require(time.monotonic() - self.started < self.contracts.execution["budgets"]["seconds"], "TARGET_TIMEOUT")
        require(self.steps < self.contracts.execution["budgets"]["steps"], "TARGET_STEPS_EXHAUSTED")
        self.steps += 1

    def register(self, calls, response_id):
        require(type(calls) is list and len(calls) <= 1, "PARALLEL_TOOL_CALLS_REJECTED", "AGENT")
        for call in calls:
            fields(call, {"id", "type", "function"}, "TARGET_CALL_FIELDS")
            require(call["type"] == "function" and identifier(call["id"])
                    and call["id"] not in self.intents, "TOOL_CALL_ID_DUPLICATE_OR_INVALID", "AGENT")
            function = call["function"]
            fields(function, {"name", "arguments"}, "TARGET_FUNCTION_FIELDS")
            name, args = function["name"], strict_json(function["arguments"])
            require(name in TOOLS, "TOOL_NOT_ALLOWLISTED", "AGENT")
            require(args == arguments_for(name, self.contracts.effect)
                    and (name != "refund_order" or type(args.get("amount_minor")) is int), "TARGET_ARGUMENTS_REJECTED", "AGENT")
            self.intents[call["id"]] = {"call_id": call["id"], "name": name,
                "arguments_sha256": digest(args), "response_id": response_id}

    def invoke(self, call_id, name, args):
        self.step()
        require(call_id in self.intents and not any(c["call_id"] == call_id for c in self.calls), "TOOL_CALL_UNKNOWN_OR_REPLAY", "AGENT")
        intent = self.intents[call_id]
        require(intent["name"] == name and intent["arguments_sha256"] == digest(args), "INTENT_BINDING_MISMATCH", "AGENT")
        require(not self.pending or name == "reconcile_order", "UNKNOWN_OUTCOME_RECONCILE_REQUIRED", "AGENT")
        if name == "refund_order":
            require(self.observed and not self.mutated, "OBSERVE_FIRST_OR_MUTATION_ALREADY_COMMITTED", "AGENT")
        if name == "reconcile_order":
            require(self.pending, "NO_PENDING_OPERATION", "AGENT")
            receipt = self.authority.reconcile(args["operation_id"])
            result = {"status": "RECONCILED_COMMITTED", "operation_id": args["operation_id"], "receipt_id": receipt["receipt_id"]}
            self.pending = False
            self.domain.fault["reconciled"] = True
        else:
            result = self.domain.invoke(name, args)
            self.observed = self.observed or name == "inspect_order"
            self.mutated = self.mutated or name == "refund_order"
            self.pending = result.get("status") == "UNKNOWN_OUTCOME"
        self.calls.append({**intent, "result": result, "result_sha256": digest(result), "returned_in_request": None})
        return result

    def verify_returns(self, messages, attempt):
        require(type(messages) is list and 0 < len(messages) <= 30, "TARGET_MESSAGES_REJECTED")
        returned = {}
        for message in messages:
            if message.get("role") == "tool":
                call_id = message.get("tool_call_id")
                require(call_id not in returned, "DUPLICATE_TOOL_RETURN")
                returned[call_id] = digest(strict_json(message.get("content")))
        require(set(returned) == {c["call_id"] for c in self.calls}, "TOOL_RETURN_SET_MISMATCH")
        for call in self.calls:
            require(returned[call["call_id"]] == call["result_sha256"], "TOOL_RETURN_CONTENT_MISMATCH")
            call["returned_in_request"] = call["returned_in_request"] or attempt
        return [{"call_id": k, "result_sha256": v} for k, v in returned.items()]


class TargetAgentDriver(Protocol):
    def run(self, contracts, host: TargetToolHost, ledger: ProviderLedger) -> dict: ...


class PydanticAgentDriver:
    """One statically registered SDK, in a credential-free scoped child process."""
    def __init__(self, python, run_directory, *, fixture_completion=None):
        self.python = owned_path(Path(python), task="rpf-48")
        self.directory = owned_path(Path(run_directory), task="rpf-48")
        self.fixture_completion = fixture_completion
        self.runtime = None
        self.failure = None
        self.tool_schema = None

    def completion(self, body, host, ledger):
        require(self.runtime is not None, "SDK_NOT_READY")
        host.step()
        require(type(body) is dict and set(body) <= {"model", "messages", "tools", "tool_choice", "parallel_tool_calls",
                "max_tokens", "max_completion_tokens", "stream", "thinking", "temperature"}, "MODEL_REQUEST_FIELDS")
        require(body.get("model") == CONFIG["model"] and body.get("stream") is False
                and body.get("tool_choice", "auto") == "auto"
                and body.get("parallel_tool_calls") is False, "MODEL_REQUEST_CONFIG")
        definitions = body.get("tools")
        require(type(definitions) is list and len(definitions) == len(TOOLS)
                and {t["function"]["name"] for t in definitions} == set(TOOLS), "SDK_TOOL_REGISTRY")
        for tool in definitions:
            function = tool["function"]
            expected = arguments_for(function["name"], host.contracts.effect)
            schema = function["parameters"]
            require(schema.get("type") == "object" and schema.get("additionalProperties") is False
                    and set(schema.get("properties", {})) == set(expected)
                    and set(schema.get("required", [])) == set(expected), "SDK_TOOL_SCHEMA")
        schema_hash = digest(definitions)
        require(self.tool_schema is None or self.tool_schema == schema_hash, "SDK_TOOL_SCHEMA_CHANGED")
        self.tool_schema = schema_hash
        body.pop("max_completion_tokens", None)
        body.update(max_tokens=256, thinking={"type": "disabled"})
        returns = host.verify_returns(body["messages"], len(ledger.data["requests"]) + 1)
        record = ledger.reserve(body, host.contracts.experiment["run_id"], returns)
        if self.fixture_completion:
            data = self.fixture_completion(body)
        else:
            key = os.environ.get("DEEPSEEK_API_KEY", "")
            require(bool(key), "DEEPSEEK_KEY_UNAVAILABLE", "PROVIDER")
            connection = http.client.HTTPSConnection("api.deepseek.com", timeout=60)
            try:
                connection.request("POST", "/chat/completions", canonical(body),
                                   {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
                response = connection.getresponse()
                require(response.status == 200, "PROVIDER_HTTP_ERROR", "PROVIDER")
                raw = response.read(262145)
                require(len(raw) <= 262144, "PROVIDER_RESPONSE_SIZE", "PROVIDER")
                data = strict_json(raw)
            finally:
                connection.close()
        ledger.received(record, data)
        choices = data.get("choices")
        require(type(choices) is list and len(choices) == 1, "PROVIDER_CHOICES", "PROVIDER")
        calls = choices[0]["message"].get("tool_calls") or []
        host.register(calls, data["id"])
        record["intents"] = [host.intents[c["id"]] for c in calls]
        ledger.checkpoint()
        return data

    def run(self, contracts, host, ledger):
        require(contracts.execution["driver"] == "pydantic-ai"
                and ledger.fixture is bool(self.fixture_completion), "DRIVER_MODE_MISMATCH")
        require(bool(self.fixture_completion) or bool(os.environ.get("DEEPSEEK_API_KEY")), "DEEPSEEK_KEY_UNAVAILABLE", "PROVIDER")
        self.directory.mkdir(parents=True, exist_ok=False)
        token = secrets.token_hex(32)
        driver = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                try:
                    require(driver.failure is None, "HOST_ALREADY_FAILED_CLOSED")
                    require(self.headers.get("Authorization") == "Bearer " + token
                            and self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
                            and self.headers.get("Origin") is None, "HOST_AUTH_REJECTED")
                    length = int(self.headers.get("Content-Length", "0"))
                    require(0 < length <= 32768, "HOST_REQUEST_SIZE")
                    body = strict_json(self.rfile.read(length))
                    if self.path == "/ready":
                        fields(body, {"framework", "version", "pid", "sdk_source_sha256", "openai_version", "agent_config_sha256"}, "SDK_READY_FIELDS")
                        sdk_file = driver.python.parent.parent / "Lib/site-packages/pydantic_ai/agent/__init__.py"
                        require(driver.runtime is None and body["framework"] == FRAMEWORK["name"]
                                and body["version"] == FRAMEWORK["version"] and type(body["pid"]) is int
                                and body["agent_config_sha256"] == contracts.execution["config_sha256"]
                                and body["openai_version"] == OPENAI_CLIENT_VERSION
                                and body["sdk_source_sha256"] == hashlib.sha256(sdk_file.read_bytes()).hexdigest() == SDK_CORE_SHA256,
                                "SDK_READY_IDENTITY")
                        driver.runtime = body
                        result = {"status": "AGENT_RUNTIME_CONNECTED"}
                    elif self.path == "/v1/chat/completions":
                        result = driver.completion(body, host, ledger)
                    elif self.path == "/tool":
                        require(driver.runtime is not None, "SDK_NOT_READY")
                        fields(body, {"call_id", "name", "arguments"}, "HOST_CALL_FIELDS")
                        result = host.invoke(body["call_id"], body["name"], body["arguments"])
                    else:
                        raise RuntimeFailure("HARNESS", "HOST_ROUTE_REJECTED")
                    raw, status = canonical(result), 200
                except Exception as exc:
                    driver.failure = driver.failure or {"domain": getattr(exc, "domain", "PLATFORM"),
                                                       "code": getattr(exc, "code", "HOST_PROTOCOL_ERROR")}
                    raw, status = canonical({"error": driver.failure["code"]}), 400
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = {"port": server.server_port, "token": token, "effect": contracts.effect,
                  "instructions": INSTRUCTIONS, "agent_config": CONFIG,
                  "home": str(self.directory), "seconds": 60 if self.fixture_completion else contracts.execution["budgets"]["seconds"]}
        env = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "COMSPEC") if k in os.environ}
        env.update(HOME=str(self.directory), USERPROFILE=str(self.directory), TEMP=str(self.directory),
                   TMP=str(self.directory), PYTHONDONTWRITEBYTECODE="1", OTEL_SDK_DISABLED="true",
                   LOGFIRE_SEND_TO_LOGFIRE="false")
        process = None
        try:
            process = subprocess.Popen([str(self.python), "-I", "-B", str(Path(__file__).with_name("target_external.py"))],
                cwd=self.directory, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                stdout, stderr = process.communicate(canonical(config), timeout=config["seconds"])
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=10)
                self.failure = {"domain": "PLATFORM", "code": "TARGET_PROCESS_TIMEOUT"}
            try:
                report = strict_json(stdout) if stdout and len(stdout) < 8192 else {}
                if report.get("status") == "COMPLETED":
                    fields(report, {"status", "framework", "version", "requests", "input_tokens", "output_tokens",
                                    "final_output_sha256", "final_text_persisted"}, "SDK_REPORT_FIELDS")
                else:
                    fields(report, {"status", "stage", "error_type", "denied", "guard_code"}, "SDK_ERROR_REPORT_FIELDS")
                    require(report["status"] == "SDK_ERROR", "SDK_REPORT_STATUS")
            except Exception:
                self.failure = self.failure or {"domain": "PLATFORM", "code": "SDK_REPORT_INVALID"}
                report = {"status": "SDK_REPORT_INVALID"}
            return {"source": "FIXTURE_TEST_ONLY" if self.fixture_completion else "EXTERNAL_AGENT_RUNTIME",
                    "host_protocol": "rpf-target-loopback-json-v1", "runtime": self.runtime,
                    "process_exit": process.returncode, "report": report, "failure": self.failure,
                    "launcher_pid": getattr(process, "pid", None),
                    "process_binding": "PRIVATE_STDIN_CAPABILITY_AND_LOOPBACK_TOKEN_NOT_OS_ATTESTATION",
                    "stderr_sha256": hashlib.sha256(stderr).hexdigest(), "stderr_bytes": len(stderr),
                    "tool_schema_sha256": self.tool_schema, "automatic_retries": 0,
                    "source_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                        for name in ("target_driver.py", "target_contracts.py", "target_external.py", "target_evidence.py",
                                     "contracts.py", "orders.py", "effect_oracle.py")}}
        finally:
            if process and process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

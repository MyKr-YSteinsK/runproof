from __future__ import annotations

import ast
import http.client
import os
import socket
import sys
import time
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

from runtime.runproof_runtime.effectwitness.config_target_bridge import (
    BoundedConfigHttp, ConfigTargetFixtureHost, ConfigTargetInMemoryDiagnosticBackend,
    ConfigTargetToolHost, _api_data, _safe_fixture_failure_code, TargetBridgeRejected,
)
from runtime.runproof_runtime.effectwitness.config_target_contracts import (
    HTTP_ORDER, canonical, digest, evaluate_config_target_effect,
    expected_path, expected_request, fixture_response, make_contracts,
    parse_sdk_child_report, strict_json, validate_contracts, ContractRejected,
)
from runtime.runproof_runtime.effectwitness.config_target_external import _guard

ROOT = Path(__file__).resolve().parents[2]


def contracts():
    identity = {"sdk_source_sha256": "a" * 64, "openai_source_sha256": "b" * 64}
    return make_contracts(run_id="rpf52-" + "1" * 32,
        source_identity_sha256="c" * 64, sdk_identity=identity,
        java_version="17.0.12", java_port=19001, agent_host_port=19002,
        prepared_at_utc="2026-10-18T00:00:00Z")


def api(code, data=None):
    return {"code": code, "message": "ok", "data": data, "traceId": None}


def item(effect, version, value):
    return {"app": effect["app"], "env": effect["env"], "key": effect["key"],
            "value": value, "description": None, "version": version,
            "updatedAt": "2026-10-18T00:00:00Z"}


def observation(effect, seq, kind, status, response, request=None):
    method, path = expected_path(effect, kind)
    return {"seq": seq, "kind": kind, "method": method, "path": path,
            "request": expected_request(effect, kind) if request is None else request,
            "status": status, "content_type": "application/json",
            "response": response, "response_body_sha256": digest(response),
            "elapsed_ms": 1, "transport_error": None}


def passing_observations(effect):
    first = [{"app": effect["app"], "env": effect["env"], "key": effect["key"],
              "value": "rpf52-v2", "description": None, "version": 2,
              "action": "UPSERT", "operator": None, "reason": None,
              "createdAt": "2026-10-18T00:01:00Z"},
             {"app": effect["app"], "env": effect["env"], "key": effect["key"],
              "value": "rpf52-v1", "description": None, "version": 1,
              "action": "UPSERT", "operator": None, "reason": None,
              "createdAt": "2026-10-18T00:00:00Z"}]
    rows = [
        (1, "initial_current", 404, api(4041)),
        (2, "initial_history", 200, api(0, [])),
        (3, "inspect_config", 404, api(4041)),
        (4, "create_config_v1", 200, api(0, item(effect, 1, "rpf52-v1"))),
        (5, "update_config_v2", 200, api(0, item(effect, 2, "rpf52-v2"))),
        (6, "final_current", 200, api(0, item(effect, 2, "rpf52-v2"))),
        (7, "final_history", 200, api(0, first)),
        (8, "final_list", 200, api(0, [item(effect, 2, "rpf52-v2")])),
    ]
    return [observation(effect, seq, kind, status, response)
            for seq, kind, status, response in rows]


def passing_tools(contract, observations):
    calls = contract["execution"]["tool_calls"]
    expected = [
        ("inspect_config", {}, 3),
        ("create_config_v1", {"value": "rpf52-v1"}, 4),
        ("update_config_v2", {"expected_version": 1, "value": "rpf52-v2"}, 5),
    ]
    result = []
    for index, (name, args, http_seq) in enumerate(expected):
        value = {"http_status": observations[http_seq - 1]["status"],
                 "response": observations[http_seq - 1]["response"]}
        result.append({"seq": index + 1, "call_id": calls[index]["call_id"],
            "name": name, "arguments": args, "arguments_sha256": digest(args),
            "completion_round": index + 1, "http_seq": http_seq,
            "http_response_sha256": observations[http_seq - 1]["response_body_sha256"],
            "tool_return_sha256": digest(value), "tool_return": value, "accepted": True})
    return result


class FakeHttp:
    def __init__(self, effect):
        self.effect = effect
        self.observations = [
            {"kind": "initial_current", "status": 404},
            {"kind": "initial_history", "status": 200},
        ]
        self.calls = []
        self.stop_writes = False

    def request(self, kind, *, credential=False):
        self.calls.append((kind, credential))
        if kind == "inspect_config":
            response = api(4041)
            value = {"status": 404, "response": response,
                     "response_body_sha256": digest(response),
                     "content_type": "application/json",
                     "transport_error": None, "seq": 3}
        else:
            version, content = ((1, "rpf52-v1") if kind == "create_config_v1"
                                else (2, "rpf52-v2"))
            response = api(0, item(self.effect, version, content))
            value = {"status": 200, "response": response,
                     "response_body_sha256": digest(response),
                     "content_type": "application/json",
                     "transport_error": None, "seq": 3 + len(self.calls) - 1}
        value["kind"] = kind
        self.observations.append(value)
        return value


class ConfigTargetContractTests(unittest.TestCase):
    def test_contract_freezes_three_tools_and_zero_provider_budget(self):
        frozen = contracts()
        validate_contracts(frozen)
        self.assertEqual([x["name"] for x in frozen["execution"]["tool_calls"]],
                         ["inspect_config", "create_config_v1", "update_config_v2"])
        self.assertEqual(frozen["execution"]["budgets"]["provider_requests"], 0)
        self.assertEqual(frozen["execution"]["budgets"]["business_http_requests"], 8)

    def test_contract_rejects_parallel_or_extra_tool(self):
        frozen = contracts()
        frozen["execution"]["tool_calls"].append({"name": "delete_config"})
        with self.assertRaises(ContractRejected):
            validate_contracts(frozen)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(ContractRejected):
            strict_json(b'{"value":1,"value":2}')

    def test_exact_rev2_identity_remains_valid_but_arbitrary_parent_is_rejected(self):
        frozen = contracts()
        experiment = frozen["experiment"]
        experiment["plan_revision"] = "rev-2"
        experiment["git_branch"] = "codex/rpf-52-rev2-config-target-sdk-recovery"
        experiment["runproof_parent_commit"] = "5d0fa1f81c8362f9eb27fe893756fe8f95fc9e3f"
        validate_contracts(frozen)
        experiment["runproof_parent_commit"] = "a" * 40
        with self.assertRaises(ContractRejected):
            validate_contracts(frozen)


class ConfigTargetApiEnvelopeTests(unittest.TestCase):
    def test_http_status_and_json_code_are_checked_independently(self):
        body = {"code": 0, "message": "OK", "data": {"value": "v1"},
                "traceId": "trace"}
        response = {"status": 200, "content_type": "Application/JSON; charset=utf-8",
                    "transport_error": None, "response": body}
        cases = [
            (response, 200, 0, "item", True),
            ({**response, "response": {**body, "code": 200}}, 200, 0, "item", False),
            ({**response, "status": 404, "response": {**body, "code": 4041,
                                                         "data": None}},
             404, 4041, "none", True),
            ({**response, "status": 404}, 200, 0, "item", False),
            ({**response, "response": {"code": 0, "message": "OK", "data": []}},
             200, 0, "item", False),
            ({**response, "transport_error": "TIMEOUT"}, 200, 0, "item", False),
            ({**response, "response": {**body, "data": {}}},
             200, 0, "list", False),
        ]
        for observed, status, code, kind, expected in cases:
            with self.subTest(status=observed.get("status"), code=observed["response"].get("code")):
                allowed, _ = _api_data(observed, status, code, kind)
                self.assertIs(allowed, expected)


class ConfigTargetToolHostTests(unittest.TestCase):
    def setUp(self):
        self.contract = contracts()
        self.client = FakeHttp(self.contract["effect"])
        self.host = ConfigTargetToolHost(self.contract, self.client)
        self.calls = self.contract["execution"]["tool_calls"]

    def test_fixed_tool_sequence_calls_only_expected_http(self):
        call = self.calls[0]
        result = self.host.invoke(call["call_id"], call["name"], call["arguments"], 1)
        self.assertEqual(result["http_status"], 404)
        second = self.calls[1]
        self.host.invoke(second["call_id"], second["name"], second["arguments"], 2)
        third = self.calls[2]
        self.host.invoke(third["call_id"], third["name"], third["arguments"], 3)
        self.assertEqual(self.client.calls, [
            ("inspect_config", False), ("create_config_v1", True),
            ("update_config_v2", True)])
        self.assertEqual(len(self.host.tool_trace), 3)

    def test_rejected_inspect_envelope_stops_all_following_writes(self):
        client = FakeHttp(self.contract["effect"])
        client.request = lambda kind, *, credential=False: {
            "kind": kind, "seq": 3, "status": 404,
            "content_type": "application/json", "transport_error": None,
            "response": api(0), "response_body_sha256": digest(api(0)),
        }
        host = ConfigTargetToolHost(self.contract, client)
        inspect = self.calls[0]
        with self.assertRaises(TargetBridgeRejected):
            host.invoke(inspect["call_id"], inspect["name"], inspect["arguments"], 1)
        self.assertTrue(client.stop_writes)
        create = self.calls[1]
        with self.assertRaises(TargetBridgeRejected):
            host.invoke(create["call_id"], create["name"], create["arguments"], 2)
        self.assertEqual(len(host.tool_trace), 1)

    def test_unknown_or_replayed_call_id_fails_closed(self):
        call = self.calls[0]
        with self.assertRaises(TargetBridgeRejected):
            self.host.invoke("other-id", call["name"], call["arguments"], 1)
        self.assertEqual(self.client.calls, [])

    def test_mutated_arguments_and_unregistered_tool_fail_closed(self):
        call = self.calls[1]
        with self.assertRaises(TargetBridgeRejected):
            self.host.invoke(call["call_id"], call["name"], {"value": "changed"}, 2)
        with self.assertRaises(TargetBridgeRejected):
            self.host.invoke(call["call_id"], "delete_config", call["arguments"], 2)
        self.assertEqual(self.client.calls, [])

    def test_write_cannot_precede_inspection(self):
        call = self.calls[1]
        with self.assertRaises(TargetBridgeRejected):
            self.host.invoke(call["call_id"], call["name"], call["arguments"], 2)
        self.assertEqual(self.client.calls, [])

    def test_expired_scenario_deadline_blocks_http_before_connect(self):
        client = BoundedConfigHttp(self.contract, "a" * 32,
                                   deadline=time.monotonic() - 1)
        with self.assertRaises(TargetBridgeRejected) as caught:
            client.request("initial_current")
        self.assertEqual(caught.exception.code, "SCENARIO_DEADLINE_EXCEEDED")
        self.assertEqual(client.observations, [])


class ConfigTargetDiagnosticBackendTests(unittest.TestCase):
    def test_memory_backend_drives_same_three_tool_host_without_http(self):
        frozen = contracts()
        backend = ConfigTargetInMemoryDiagnosticBackend(frozen)
        host = ConfigTargetToolHost(frozen, backend)
        for index, call in enumerate(frozen["execution"]["tool_calls"], start=1):
            host.invoke(call["call_id"], call["name"], call["arguments"], index)
        self.assertEqual(backend.backend_id,
                         "FIXTURE_ONLY_IN_MEMORY_NO_BUSINESS_HTTP")
        self.assertEqual(backend.real_http_requests, 0)
        self.assertEqual([row["kind"] for row in backend.observations], [
            "initial_current", "initial_history", "inspect_config",
            "create_config_v1", "update_config_v2",
        ])
        self.assertEqual(backend._state, (2, "rpf52-v2"))
        self.assertEqual(backend._history, [1, 2])
        self.assertEqual([row["call_id"] for row in host.tool_trace],
                         [call["call_id"] for call in frozen["execution"]["tool_calls"]])

    def test_fixture_error_code_is_enumerated_and_message_free(self):
        self.assertEqual(_safe_fixture_failure_code("SDK_TOOL_RETURN_LINEAGE"),
                         "SDK_TOOL_RETURN_LINEAGE")
        self.assertEqual(_safe_fixture_failure_code("secret-token-value"),
                         "FIXTURE_REQUEST_REJECTED")

    def test_fixture_http_4xx_preserves_first_enumerated_rejection_code(self):
        frozen = contracts()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        frozen["execution"]["agent_host"]["port"] = port
        frozen["experiment"]["agent_host_port"] = port
        frozen["experiment"]["execution_digest"] = digest(frozen["execution"])
        validate_contracts(frozen)
        backend = ConfigTargetInMemoryDiagnosticBackend(frozen)
        tool_host = ConfigTargetToolHost(frozen, backend)
        fixture = ConfigTargetFixtureHost(frozen, tool_host, "a" * 64, "b" * 64)
        fixture.start()
        try:
            for _ in range(2):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request("POST", "/ready", body=b"{}", headers={
                    "Host": f"127.0.0.1:{port}", "Origin": "",
                    "Content-Type": "application/json", "Authorization": "Bearer wrong",
                })
                response = connection.getresponse()
                body = strict_json(response.read())
                connection.close()
                self.assertEqual(response.status, 400)
                self.assertEqual(body, {"error": "FIXTURE_AUTH"})
                self.assertEqual(fixture.first_failure_code, "FIXTURE_AUTH")
        finally:
            fixture.close()


class ConfigTargetFixtureContractTests(unittest.TestCase):
    def test_fixture_script_has_three_ordered_tool_calls_then_stop(self):
        frozen = contracts()
        responses = [fixture_response(frozen, index) for index in range(4)]
        self.assertEqual([r["choices"][0]["finish_reason"] for r in responses],
                         ["tool_calls", "tool_calls", "tool_calls", "stop"])
        self.assertEqual([r["choices"][0]["message"]["tool_calls"][0]["id"]
                          for r in responses[:3]],
                         [call["call_id"] for call in frozen["execution"]["tool_calls"]])
        self.assertEqual(responses[0]["usage"],
                         {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        self.assertEqual(responses[3]["choices"][0]["message"]["content"],
                         "rpf52-fixture-complete")

    def test_sdk_tool_schema_allowlist_rejects_extra_or_changed_parameters(self):
        schema = [
            {"type": "function", "function": {"name": "inspect_config", "parameters": {
                "type": "object", "properties": {}, "required": [], "additionalProperties": False}}},
            {"type": "function", "function": {"name": "create_config_v1", "parameters": {
                "type": "object", "properties": {"value": {"type": "string"}},
                "required": ["value"], "additionalProperties": False}}},
            {"type": "function", "function": {"name": "update_config_v2", "parameters": {
                "type": "object", "properties": {
                    "expected_version": {"type": "integer"}, "value": {"type": "string"}},
                "required": ["expected_version", "value"], "additionalProperties": False}}},
        ]
        ConfigTargetFixtureHost._verify_registry(schema)
        schema[0]["function"]["parameters"].pop("required")
        ConfigTargetFixtureHost._verify_registry(schema)
        schema[0]["function"]["parameters"]["required"] = []
        schema[1]["function"]["parameters"].pop("required")
        with self.assertRaises(TargetBridgeRejected):
            ConfigTargetFixtureHost._verify_registry(schema)
        schema[1]["function"]["parameters"]["required"] = ["value"]
        with self.assertRaises(TargetBridgeRejected):
            ConfigTargetFixtureHost._verify_registry(schema + [schema[0]])
        schema[2]["function"]["parameters"]["properties"]["key"] = {"type": "string"}
        with self.assertRaises(TargetBridgeRejected):
            ConfigTargetFixtureHost._verify_registry(schema)
        schema[2]["function"]["parameters"]["properties"].pop("key")
        schema[2]["function"]["parameters"]["properties"]["expected_version"] = {
            "type": "string"}
        with self.assertRaises(TargetBridgeRejected):
            ConfigTargetFixtureHost._verify_registry(schema)


class ConfigTargetSdkDiagnosticParsingTests(unittest.TestCase):
    def test_valid_completed_report_and_sdk_error_are_sanitized(self):
        completed = {
            "status": "COMPLETED", "framework": "pydantic-ai-slim",
            "version": "2.57.0", "openai_version": "3.35.1",
            "python_version": "3.12.13", "pid": 123, "requests": 4,
            "input_tokens": 0, "output_tokens": 0, "tool_calls": 3,
            "guard_denials": [], "sdk_source_sha256": "a" * 64,
            "openai_source_sha256": "b" * 64, "final_output_sha256": "c" * 64,
            "final_text_persisted": False,
        }
        self.assertEqual(parse_sdk_child_report(canonical(completed), 0),
                         (completed, None))
        failure = {"status": "SDK_ERROR", "stage": "sdk_run",
                   "error_type": "RuntimeError", "guard_code": None,
                   "guard_denials": []}
        self.assertEqual(parse_sdk_child_report(canonical(failure), 1),
                         (failure, "SDK_CHILD_REPORTED_ERROR"))

    def test_missing_large_duplicate_and_invalid_sdk_reports_fail_closed(self):
        self.assertEqual(parse_sdk_child_report(b"", 1),
                         (None, "SDK_DIAGNOSTIC_UNAVAILABLE"))
        self.assertEqual(parse_sdk_child_report(b" " * 8193, 1),
                         (None, "SDK_REPORT_TOO_LARGE"))
        self.assertEqual(parse_sdk_child_report(b'{"status":"SDK_ERROR","status":"x"}', 1),
                         (None, "SDK_REPORT_DUPLICATE_JSON_KEYS"))
        self.assertEqual(parse_sdk_child_report(b'{"status":"SDK_ERROR"}', 1),
                         (None, "SDK_REPORT_SCHEMA_INVALID"))

    def test_invalid_error_types_guard_values_and_exit_codes_are_classified(self):
        base = {"status": "SDK_ERROR", "stage": "sdk_run",
                "error_type": "RuntimeError", "guard_code": None,
                "guard_denials": []}
        item = {**base, "stage": ["sdk_run"]}
        self.assertEqual(parse_sdk_child_report(canonical(item), 1),
                         (None, "SDK_ERROR_STAGE_INVALID"))
        item = {**base, "error_type": {"message": "secret"}}
        self.assertEqual(parse_sdk_child_report(canonical(item), 1),
                         (None, "SDK_ERROR_TYPE_INVALID"))
        item = {**base, "guard_denials": [{}]}
        self.assertEqual(parse_sdk_child_report(canonical(item), 1),
                         (None, "SDK_ERROR_GUARD_SCHEMA_INVALID"))
        self.assertEqual(parse_sdk_child_report(canonical(base), 0)[1],
                         "SDK_ERROR_EXIT_CODE_MISMATCH")
        completed = {
            "status": "COMPLETED", "framework": "pydantic-ai-slim",
            "version": "2.57.0", "openai_version": "3.35.1",
            "python_version": "3.12.13", "pid": 123, "requests": 4,
            "input_tokens": 0, "output_tokens": 0, "tool_calls": 3,
            "guard_denials": [], "sdk_source_sha256": "a" * 64,
            "openai_source_sha256": "b" * 64, "final_output_sha256": "c" * 64,
            "final_text_persisted": False,
        }
        self.assertEqual(parse_sdk_child_report(canonical(completed), 1)[1],
                         "SDK_COMPLETION_EXIT_CODE_MISMATCH")


class ConfigTargetOracleTests(unittest.TestCase):
    def test_recomputes_expected_state_transition(self):
        frozen = contracts()
        observations = passing_observations(frozen["effect"])
        tools = passing_tools(frozen, observations)
        outcome = evaluate_config_target_effect(frozen["effect"], observations, tools)
        self.assertEqual(outcome["outcome"], "CONTRACT_SATISFIED_IN_RUN")
        self.assertEqual(outcome["facts"]["history_versions"], [2, 1])
        self.assertEqual(outcome["run_outcome"], "EXECUTION_COMPLETE")
        self.assertEqual(outcome["business_violation"], "NOT_PROVEN")

    def test_rev1_read_only_zero_tool_observation_is_platform_inconclusive(self):
        frozen = contracts()
        effect = frozen["effect"]
        rows = [
            ("initial_current", 404, api(4041)),
            ("initial_history", 200, api(0, [])),
            ("final_current", 404, api(4041)),
            ("final_history", 200, api(0, [])),
            ("final_list", 200, api(0, [])),
        ]
        observations = [observation(effect, index, kind, status, response)
                        for index, (kind, status, response) in enumerate(rows, start=1)]
        outcome = evaluate_config_target_effect(effect, observations, [])
        self.assertEqual(outcome["outcome"], "INCONCLUSIVE")
        self.assertEqual(outcome["run_outcome"], "PLATFORM_ERROR")
        self.assertEqual(outcome["agent_failure"], "NOT_PROVEN")
        self.assertEqual(outcome["business_violation"], "NOT_PROVEN")

    def test_success_http_status_with_business_code_200_is_rejected(self):
        frozen = contracts()
        observations = passing_observations(frozen["effect"])
        observations[1]["response"]["code"] = 200
        observations[1]["response_body_sha256"] = digest(observations[1]["response"])
        outcome = evaluate_config_target_effect(
            frozen["effect"], observations, passing_tools(frozen, observations))
        self.assertEqual(outcome["outcome"], "INCONCLUSIVE")
        self.assertEqual(outcome["run_outcome"], "PLATFORM_ERROR")
        self.assertEqual(outcome["business_violation"], "NOT_PROVEN")

    def test_final_history_mismatch_is_a_violation(self):
        frozen = contracts()
        observations = passing_observations(frozen["effect"])
        observations[6]["response"]["data"][0]["version"] = 3
        observations[6]["response_body_sha256"] = digest(observations[6]["response"])
        tools = passing_tools(frozen, observations)
        outcome = evaluate_config_target_effect(frozen["effect"], observations, tools)
        self.assertEqual(outcome["outcome"], "VIOLATION_CONFIRMED")
        self.assertEqual(outcome["business_violation"], "CONFIRMED")
        self.assertIn("FINAL_HISTORY_INVALID", outcome["violations"])

    def test_tool_call_id_and_return_digest_are_bound(self):
        frozen = contracts()
        observations = passing_observations(frozen["effect"])
        tools = passing_tools(frozen, observations)
        tools[1]["call_id"] = tools[0]["call_id"]
        outcome = evaluate_config_target_effect(frozen["effect"], observations, tools)
        self.assertEqual(outcome["outcome"], "VIOLATION_CONFIRMED")
        self.assertIn("TOOL_TRACE_BINDING", outcome["violations"])


class ConfigTargetVerifierBoundaryTests(unittest.TestCase):
    def test_offline_verifier_has_no_live_or_sdk_imports(self):
        path = ROOT / "runtime/runproof_runtime/effectwitness/config_target_verify.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        forbidden = ("sqlite3", "socket", "http.client", "httpx", "pydantic_ai",
                     "openai", "subprocess")
        self.assertFalse([name for name in modules
                          if any(name == bad or name.startswith(bad + ".")
                                 for bad in forbidden)])

    def test_sdk_child_guard_denies_unscoped_sockets_filesystem_and_dns(self):
        denied = []
        audit = _guard(19002, ROOT / ".local" / "rpf-52-rev3" / "diagnostic-1",
                       ROOT / ".local" / "rpf-48" / "venv" / "Lib" / "site-packages",
                       denied)
        for event, args in (("socket.bind", ()), ("socket.listen", ()),
                            ("socket.sendto", ()), ("socket.sendmsg", ())):
            with self.assertRaises(PermissionError):
                audit(event, args)
        for event, args in (("os.chmod", (ROOT / "outside.txt", 0o600)),
                            ("os.fchmod", (1, 0o600))):
            with self.assertRaises(PermissionError):
                audit(event, args)
        for event in ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"):
            with self.assertRaises(PermissionError):
                audit(event, ("example.invalid",))
        self.assertEqual(denied, [
            "RPF52_SOCKET_OPERATION_DENIED", "RPF52_SOCKET_OPERATION_DENIED",
            "RPF52_SOCKET_OPERATION_DENIED", "RPF52_SOCKET_OPERATION_DENIED",
            "RPF52_FILE_WRITE_DENIED", "RPF52_FILE_WRITE_DENIED",
            "RPF52_DNS_DENIED", "RPF52_DNS_DENIED", "RPF52_DNS_DENIED",
        ])

    def test_sdk_child_guard_allows_reads_from_resolved_base_python_runtime(self):
        denied = []
        audit = _guard(19002, ROOT / ".local" / "rpf-52-rev3" / "diagnostic-1",
                       ROOT / ".local" / "rpf-48" / "venv" / "Lib" / "site-packages",
                       denied)
        base_executable = Path(getattr(sys, "_base_executable", sys.executable))
        runtime_root = base_executable.resolve(strict=True).parent
        if os.name == "nt":
            candidate = runtime_root / "Lib" / "importlib" / "metadata" / "__init__.py"
        else:
            candidate = runtime_root / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "importlib" / "metadata" / "__init__.py"
        self.assertTrue(candidate.is_file())
        audit("open", (str(candidate), "r", os.O_RDONLY))
        self.assertEqual(denied, [])


class ConfigTargetHttpRejectionRegressionTests(unittest.TestCase):
    @contextmanager
    def fixture(self):
        frozen = contracts()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        frozen["execution"]["agent_host"]["port"] = port
        frozen["experiment"]["agent_host_port"] = port
        frozen["experiment"]["execution_digest"] = digest(frozen["execution"])
        validate_contracts(frozen)
        backend = ConfigTargetInMemoryDiagnosticBackend(frozen)
        tools = ConfigTargetToolHost(frozen, backend)
        fixture = ConfigTargetFixtureHost(frozen, tools, "a" * 64, "b" * 64)
        fixture.start()
        thread = fixture._thread
        try:
            yield frozen, backend, tools, fixture
        finally:
            start = time.monotonic()
            fixture.close()
            self.assertLess(time.monotonic() - start, 2)
            self.assertFalse(thread.is_alive())
            with socket.socket() as sock:
                sock.settimeout(0.2)
                self.assertNotEqual(sock.connect_ex(("127.0.0.1", port)), 0)

    def request(self, fixture, path, body=b"{}", *, method="POST", headers=None):
        values = {"Host": f"127.0.0.1:{fixture.port}",
                  "Authorization": "Bearer " + fixture.FIXTURE_TOKEN,
                  "Content-Type": "application/json"}
        values.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", fixture.port, timeout=2)
        try:
            connection.request(method, path, body=body, headers=values)
            response = connection.getresponse()
            result = strict_json(response.read())
            self.assertEqual(response.getheader("Connection"), "close")
            return response.status, result
        finally:
            connection.close()

    def record(self, label, rows):
        folder = ROOT / ".local/rpf-67-rev-3/http-tests"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / (label + "-" + uuid.uuid4().hex + ".json")).open("xb") as f:
            f.write(canonical({"status": "PASS", "label": label, "rows": rows,
                               "provider": 0, "source_kind": "SYNTHETIC_TEST_ONLY",
                               "fixture_source_sha256": __import__("hashlib").sha256(
                                   (ROOT / "runtime/runproof_runtime/effectwitness/config_target_bridge.py").read_bytes()).hexdigest()}))

    def test_twenty_fresh_hosts_two_auth_rejections_sticky_code(self):
        rows = []
        for index in range(20):
            with self.fixture() as (_, backend, tools, fixture):
                before = list(backend.observations)
                for _ in range(2):
                    self.assertEqual(self.request(fixture, "/ready", headers={
                        "Authorization": "Bearer wrong", "Origin": ""}),
                        (400, {"error": "FIXTURE_AUTH"}))
                    self.assertEqual(fixture.first_failure_code, "FIXTURE_AUTH")
                self.assertIsNone(fixture.runtime)
                self.assertEqual(tools.tool_trace, [])
                self.assertEqual(fixture.completions, [])
                self.assertEqual(backend.observations, before)
            rows.append({"fixture": index + 1, "requests": 2, "status": 400,
                         "code": "FIXTURE_AUTH", "cleanup": True})
        self.record("stress20", rows)

    def test_rejection_matrix_preserves_auth_host_origin_type_route_method(self):
        rows = []
        for name, path, method, headers, body, code, status in [
            ("host", "/ready", "POST", {"Host": "invalid"}, b"{}", "FIXTURE_HOST_HEADER", 400),
            ("origin", "/ready", "POST", {"Origin": ""}, b"{}", "FIXTURE_ORIGIN", 400),
            ("type", "/ready", "POST", {"Content-Type": "text/plain"}, b"{}", "FIXTURE_CONTENT_TYPE", 400),
            ("route", "/absent", "POST", {}, b"{}", "FIXTURE_ROUTE", 400),
            ("json", "/ready", "POST", {}, b"{", "INVALID_JSON", 400),
            ("method", "/ready", "GET", {}, b"", "FIXTURE_METHOD", 405),
        ]:
            with self.fixture() as (_, backend, tools, fixture):
                before = list(backend.observations)
                self.assertEqual(self.request(fixture, path, method=method, headers=headers, body=body), (status, {"error": code}))
                self.assertIsNone(fixture.runtime)
                self.assertEqual(tools.tool_trace, [])
                self.assertEqual(backend.observations, before)
            rows.append({"case": name, "status": status, "code": code, "cleanup": True})
        self.record("rejections", rows)

    def raw_request(self, fixture, length, *, data=b"", half_close=False, extra="", auth=True):
        with socket.create_connection(("127.0.0.1", fixture.port), timeout=2) as sock:
            token = fixture.FIXTURE_TOKEN if auth else "wrong"
            head = (f"POST /ready HTTP/1.1\r\nHost: 127.0.0.1:{fixture.port}\r\n"
                    f"Authorization: Bearer {token}\r\nContent-Type: application/json\r\n")
            if length is not None:
                head += "Content-Length: " + length + "\r\n"
            sock.sendall((head + extra + "\r\n").encode() + data)
            if half_close:
                sock.shutdown(socket.SHUT_WR)
            response = http.client.HTTPResponse(sock)
            response.begin()
            return response.status, strict_json(response.read())

    def test_bounded_missing_large_ambiguous_short_and_stalled_body(self):
        rows = []
        for name, length, data, half_close, extra, auth in [
            ("missing", None, b"", False, "", True),
            ("negative", "-1", b"", False, "", True),
            ("zero", "0", b"", False, "", True),
            ("huge", "99999999999999999999", b"", False, "", True),
            ("duplicate", "2", b"", False, "Content-Length: 3\r\n", True),
            ("transfer", "2", b"", False, "Transfer-Encoding: chunked\r\n", True),
            ("short", "8", b"{}", True, "", True),
            ("stalled", "8", b"{}", False, "", True),
            ("unauth-short", "8", b"{}", True, "", False),
            ("unauth-stalled", "8", b"{}", False, "", False),
        ]:
            with self.fixture() as (_, backend, tools, fixture):
                before = list(backend.observations)
                start = time.monotonic()
                status, result = self.raw_request(fixture, length, data=data, half_close=half_close, extra=extra, auth=auth)
                elapsed = time.monotonic() - start
                code = "FIXTURE_REQUEST_SIZE" if auth else "FIXTURE_AUTH"
                self.assertEqual((status, result), (400, {"error": code}))
                self.assertLess(elapsed, 2)
                self.assertEqual(tools.tool_trace, [])
                self.assertEqual(backend.observations, before)
            rows.append({"case": name, "status": status, "code": code, "elapsed": elapsed, "cleanup": True})
        self.record("framing", rows)

    def test_client_abort_has_bounded_thread_and_port_cleanup(self):
        with self.fixture() as (_, _, tools, fixture):
            with socket.create_connection(("127.0.0.1", fixture.port), timeout=2) as sock:
                sock.sendall((f"POST /ready HTTP/1.1\r\nHost: 127.0.0.1:{fixture.port}\r\n"
                              "Authorization: Bearer wrong\r\nContent-Length: 8\r\n\r\n{}").encode())
            self.assertEqual(tools.tool_trace, [])
        self.record("client-abort", [{"cleanup": True, "business_calls": 0}])

    def test_normal_ready_completion_and_three_callbacks_remain_200(self):
        with self.fixture() as (frozen, backend, tools, fixture):
            ready = dict(framework="pydantic-ai-slim", version="2.57.0", openai_version="3.35.1",
                         python_version="3.12.13", pid=os.getpid(), sdk_source_sha256="a" * 64,
                         openai_source_sha256="b" * 64)
            self.assertEqual(self.request(fixture, "/ready", canonical(ready)), (200, {"status": "SDK_RUNTIME_CONNECTED"}))
            registry = [{"type": "function", "function": {"name": name, "parameters": {
                "type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}}}
                for name, properties in [("inspect_config", {}), ("create_config_v1", {"value": {"type": "string"}}),
                                         ("update_config_v2", {"expected_version": {"type": "integer"}, "value": {"type": "string"}})]]
            messages = []
            for index in range(4):
                request = dict(model="rpf52-fixture", stream=False, parallel_tool_calls=False, tools=registry, messages=messages)
                status, data = self.request(fixture, "/v1/chat/completions", canonical(request))
                self.assertEqual(status, 200)
                message = data["choices"][0]["message"]
                messages.append(message)
                if index < 3:
                    call = message["tool_calls"][0]
                    value = dict(call_id=call["id"], name=call["function"]["name"], arguments=strict_json(call["function"]["arguments"].encode()))
                    status, result = self.request(fixture, "/tool", canonical(value))
                    self.assertEqual(status, 200)
                    messages.append(dict(role="tool", tool_call_id=call["id"], content=canonical(result).decode()))
            self.assertEqual(len(tools.tool_trace), 3)
            self.assertEqual(backend._state, (2, "rpf52-v2"))
            self.assertIsNone(fixture.first_failure_code)
        self.record("normal", [{"requests": 8, "callbacks": 3, "status": 200, "cleanup": True}])


if __name__ == "__main__":
    unittest.main()

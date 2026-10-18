from __future__ import annotations

import ast
import time
import unittest
from pathlib import Path

from runtime.runproof_runtime.effectwitness.config_target_bridge import (
    BoundedConfigHttp, ConfigTargetFixtureHost, ConfigTargetToolHost,
    TargetBridgeRejected,
)
from runtime.runproof_runtime.effectwitness.config_target_contracts import (
    HTTP_ORDER, canonical, digest, evaluate_config_target_effect,
    expected_path, expected_request, fixture_response, make_contracts, strict_json,
    validate_contracts, ContractRejected,
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
        self.observations.append({"kind": kind, "status": value["status"]})
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


class ConfigTargetOracleTests(unittest.TestCase):
    def test_recomputes_expected_state_transition(self):
        frozen = contracts()
        observations = passing_observations(frozen["effect"])
        tools = passing_tools(frozen, observations)
        outcome = evaluate_config_target_effect(frozen["effect"], observations, tools)
        self.assertEqual(outcome["outcome"], "CONTRACT_SATISFIED_IN_RUN")
        self.assertEqual(outcome["facts"]["history_versions"], [2, 1])

    def test_final_history_mismatch_is_a_violation(self):
        frozen = contracts()
        observations = passing_observations(frozen["effect"])
        observations[6]["response"]["data"][0]["version"] = 3
        observations[6]["response_body_sha256"] = digest(observations[6]["response"])
        tools = passing_tools(frozen, observations)
        outcome = evaluate_config_target_effect(frozen["effect"], observations, tools)
        self.assertEqual(outcome["outcome"], "VIOLATION_CONFIRMED")
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
        audit = _guard(19002, ROOT / ".local" / "rpf-52",
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


if __name__ == "__main__":
    unittest.main()

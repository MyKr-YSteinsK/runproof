"""Deterministic RPF-53 contract, budget and protocol tests; no Provider/network/Java."""
from __future__ import annotations

import json
import http.client
import os
import socket
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from runtime.runproof_runtime.effectwitness.config_live_contracts import (
    BASE_SHA, LIMITS, PROVIDER_MODEL, SDK_CORE_SHA256, LiveContractRejected,
    canonical, make_contracts, strict_json, validate_contracts,
)
from runtime.runproof_runtime.effectwitness.config_live_runtime import (
    ConfigLiveBusiness, ConfigLiveHost, ConfigLiveMemoryBackend, LiveRuntimeRejected, ProviderLedger,
    _validate_provider_response, _validate_tool_registry,
)
from runtime.runproof_runtime.effectwitness.config_live_verify import evaluate_live_effect
from runtime.runproof_runtime.effectwitness.config_live_external import _safe_denied_basename


ROOT = Path(__file__).resolve().parents[2]
TASK_TEST_ROOT = ROOT / ".local" / "rpf-53" / "tests"


def _sdk_identity() -> dict:
    return {"python_version": "3.12.13", "python_executable_sha256": "a" * 64,
            "pydantic_record_sha256": "b" * 64, "pydantic_record_entries": 444,
            "pydantic_record_mismatches": 0, "openai_record_sha256": "c" * 64,
            "openai_record_entries": 2000, "openai_record_mismatches": 0,
            "openai_core_sha256": "d" * 64}


def _contracts(*, fixture: bool = False, agent_port: int | None = None) -> dict:
    suffix = "0123456789abcdef"
    port = agent_port or (47322 if fixture else 47323)
    return make_contracts(run_id="rpf53-test-" + suffix, suffix=suffix,
        java_port=None if fixture else 47321,
        agent_port=port,
        prepared_at_utc="2026-10-18T00:00:00Z", runtime_source_sha256="e" * 64,
        sdk_identity=_sdk_identity(),
        tool_schema_sha256=None if fixture else "f" * 64,
        mode="FIXTURE_TEST_ONLY" if fixture else "REAL_PROVIDER")


class ConfigLiveContractsTests(unittest.TestCase):
    def test_denied_file_diagnostic_keeps_only_a_bounded_safe_basename(self):
        self.assertEqual(_safe_denied_basename(r"C:\Users\Alice\secret token.json"),
                         "secret_token.json")
        self.assertEqual(_safe_denied_basename("x" * 200), "x" * 80)

    def test_external_child_uses_the_pinned_http_transport_module(self):
        source = (ROOT / "runtime/runproof_runtime/effectwitness/config_live_external.py").read_text(
            encoding="utf-8")
        self.assertIn("import httpx2", source)
        self.assertIn("httpx2.AsyncClient", source)
        self.assertNotRegex(source, r"\bimport httpx\b")

    def test_contract_is_independent_live_schema(self):
        value = _contracts()
        validate_contracts(value)
        self.assertEqual(value["execution"]["model_source"], "REAL_PROVIDER")
        self.assertEqual(value["execution"]["budgets"], LIMITS)
        self.assertEqual(value["effect"]["history_versions"], [2, 1])
        self.assertEqual(value["experiment"]["runproof_base_sha"], BASE_SHA)

    def test_fixture_contract_cannot_be_relabelled_live(self):
        value = _contracts(fixture=True)
        validate_contracts(value, require_live=False)
        with self.assertRaisesRegex(LiveContractRejected, "LIVE_PROVIDER_REQUIRED"):
            validate_contracts(value, require_live=True)

    def test_contract_mutation_breaks_frozen_digest(self):
        value = _contracts()
        value["effect"]["required_value"] = "rpf53-impostor"
        with self.assertRaisesRegex(LiveContractRejected, "EFFECT_CONTRACT"):
            validate_contracts(value)

    def test_external_source_mismatch_is_rejected(self):
        value = _contracts()
        value["experiment"]["config_center_source_commit"] = "0" * 40
        with self.assertRaisesRegex(LiveContractRejected, "EXPERIMENT_IDENTITY"):
            validate_contracts(value)

    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaisesRegex(LiveContractRejected, "DUPLICATE_JSON_KEY"):
            strict_json(b'{"role":"assistant","role":"tool"}')


class ConfigLiveBudgetTests(unittest.TestCase):
    def setUp(self):
        TASK_TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = Path(tempfile.mkdtemp(prefix="attempt-", dir=TASK_TEST_ROOT))

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_unknown_usage_is_write_ahead_and_blocks_next_request(self):
        path = self.temp / "provider-ledger.json"
        ledger = ProviderLedger(path, "rpf53-test-ledger", create=True)
        record = ledger.reserve({"model": PROVIDER_MODEL, "messages": [{"role": "user", "content": "synthetic"}]}, [])
        self.assertTrue(path.is_file())
        self.assertEqual(record["status"], "RESERVED_USAGE_UNKNOWN")
        reloaded = ProviderLedger(path, "rpf53-test-ledger")
        self.assertFalse(reloaded.usage()["usage_known"])
        with self.assertRaisesRegex(LiveRuntimeRejected, "PROVIDER_USAGE_UNKNOWN"):
            reloaded.reserve({"model": PROVIDER_MODEL, "messages": []}, [])

    def test_reported_usage_replaces_reservation_without_exceeding_caps(self):
        ledger = ProviderLedger(self.temp / "provider-ledger.json", "rpf53-known", create=True)
        record = ledger.reserve({"model": PROVIDER_MODEL, "messages": [{"role": "user", "content": "x"}]}, [])
        ledger.received(record, {"id": "chatcmpl-rpf53-test", "model": PROVIDER_MODEL,
            "usage": {"prompt_tokens": 18, "completion_tokens": 6, "total_tokens": 24}})
        usage = ledger.usage()
        self.assertTrue(usage["usage_known"])
        self.assertEqual(usage["tokens"], 24)
        self.assertEqual(usage["estimated_cost_cny_upper"],
                         (18 * LIMITS["input_cny_per_million_peak_bound"]
                          + 6 * LIMITS["output_cny_per_million_peak_bound"]) / 1_000_000)
        ledger.reserve({"model": PROVIDER_MODEL, "messages": [{"role": "user", "content": "next"}]}, [])

    def test_fixture_ledger_has_no_paid_reservation(self):
        usage = ProviderLedger.fixture_only("rpf53-diagnostic").usage()
        self.assertEqual(usage["provider_https_requests"], 0)
        self.assertEqual(usage["tokens"], 0)
        self.assertEqual(usage["metering_kind"], "FIXTURE_TEST_ONLY")


class ConfigLiveProtocolTests(unittest.TestCase):
    def test_sdk_tool_registry_accepts_omitted_empty_required_only(self):
        tools = [
            {"type": "function", "function": {"name": "inspect_config",
             "description": "Inspect", "parameters": {"type": "object",
             "properties": {}, "additionalProperties": False}}},
            {"type": "function", "function": {"name": "create_config_v1",
             "description": "Create", "parameters": {"type": "object",
             "properties": {"value": {"type": "string"}}, "required": ["value"],
             "additionalProperties": False}}},
            {"type": "function", "function": {"name": "update_config_v2",
             "description": "Update", "parameters": {"type": "object",
             "properties": {"expected_version": {"type": "integer"},
                             "value": {"type": "string"}},
             "required": ["expected_version", "value"],
             "additionalProperties": False}}},
        ]
        self.assertRegex(_validate_tool_registry(tools), r"[0-9a-f]{64}")
        tools[0]["function"]["parameters"]["required"] = ["fake"]
        with self.assertRaisesRegex(LiveRuntimeRejected, "SDK_TOOL_SCHEMA_REQUIRED"):
            _validate_tool_registry(tools)

    def test_only_documented_zero_index_extension_is_accepted(self):
        response = {"id": "chatcmpl-rpf53-test", "object": "chat.completion",
            "created": 1, "model": PROVIDER_MODEL,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [{
                    "id": "call-rpf53-test", "type": "function", "index": 0,
                    "function": {"name": "inspect_config", "arguments": "{}"}}]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
        _, _, calls = _validate_provider_response(json.loads(json.dumps(response)))
        self.assertEqual(calls[0]["id"], "call-rpf53-test")
        response["choices"][0]["message"]["tool_calls"][0]["index"] = 1
        with self.assertRaisesRegex(LiveRuntimeRejected, "PROVIDER_TOOL_INDEX"):
            _validate_provider_response(json.loads(json.dumps(response)))

    def test_incomplete_observation_is_inconclusive_not_a_violation(self):
        result = evaluate_live_effect({"app": "rpf53app-a", "env": "rpf53local-a",
            "key": "rpf53.item.a"}, [], [])
        self.assertEqual(result["outcome"], "INCONCLUSIVE")
        self.assertEqual(result["business_violation"], "NOT_PROVEN")
        self.assertEqual(result["violations"], [])

    def test_memory_fixture_backend_is_marked_and_scoped(self):
        backend = ConfigLiveMemoryBackend()
        self.assertEqual(backend.invoke("inspect_config", {}), {"state": "ABSENT"})
        self.assertEqual(backend.invoke("create_config_v1", {"value": "rpf53-v1"})[
                         "version"], 1)
        self.assertEqual(backend.invoke("update_config_v2", {
            "expected_version": 1, "value": "rpf53-v2"})["version"], 2)
        with self.assertRaisesRegex(LiveRuntimeRejected, "FIXTURE_TOOL_CONTRACT"):
            backend.invoke("update_config_v2", {"expected_version": True, "value": "rpf53-v2"})

    def test_business_rejects_unregistered_or_unsequenced_writes_without_http(self):
        class NoopClient:
            stop_writes = False

            def __init__(self):
                self.requests = []

            def request(self, kind):
                self.requests.append(kind)
                raise AssertionError("invalid write reached HTTP")

        client = NoopClient()
        business = ConfigLiveBusiness(_contracts(), client)
        with self.assertRaisesRegex(LiveRuntimeRejected, "TOOL_NOT_ALLOWLISTED"):
            business.invoke("delete_config", {})
        with self.assertRaisesRegex(LiveRuntimeRejected, "CREATE_ARGUMENTS_REJECTED"):
            business.invoke("create_config_v1", {"value": "attacker-value"})
        with self.assertRaisesRegex(LiveRuntimeRejected, "CREATE_WITHOUT_CONFIRMED_ABSENCE"):
            business.invoke("create_config_v1", {"value": "rpf53-v1"})
        with self.assertRaisesRegex(LiveRuntimeRejected, "UPDATE_WITHOUT_CONFIRMED_CREATE"):
            business.invoke("update_config_v2", {
                "expected_version": 1, "value": "rpf53-v2"})
        self.assertEqual(client.requests, [])

    def test_offline_fake_provider_failure_returns_safe_host_502(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        contracts = _contracts(fixture=True, agent_port=port)
        ledger = ProviderLedger.fixture_only(contracts["experiment"]["run_id"])
        host = ConfigLiveHost(contracts, ledger, ConfigLiveMemoryBackend(), fixture=True,
                              fixture_failure_code="OFFLINE_REPLAY_HTTP_503")
        host.start(port)
        try:
            ready = {"framework": "pydantic-ai-slim", "version": "2.57.0",
                "openai_version": "3.35.1", "pid": os.getpid(),
                "sdk_source_sha256": SDK_CORE_SHA256,
                "openai_source_sha256": _sdk_identity()["openai_core_sha256"]}
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            connection.request("POST", "/ready", canonical(ready), {
                "Content-Type": "application/json", "Authorization": "Bearer " + host.token})
            ready_response = connection.getresponse()
            self.assertEqual(ready_response.status, 200)
            ready_response.read()
            tools = [
                {"type": "function", "function": {"name": "inspect_config",
                 "description": "Inspect", "parameters": {"type": "object",
                 "properties": {}, "additionalProperties": False}}},
                {"type": "function", "function": {"name": "create_config_v1",
                 "description": "Create", "parameters": {"type": "object",
                 "properties": {"value": {"type": "string"}}, "required": ["value"],
                 "additionalProperties": False}}},
                {"type": "function", "function": {"name": "update_config_v2",
                 "description": "Update", "parameters": {"type": "object",
                 "properties": {"expected_version": {"type": "integer"},
                                 "value": {"type": "string"}},
                 "required": ["expected_version", "value"],
                 "additionalProperties": False}}},
            ]
            request = {"model": "rpf53-fixture-only", "messages":[
                {"role":"user","content":"synthetic"}], "tools":tools,
                "tool_choice":"auto", "parallel_tool_calls":False,
                "max_tokens":256,"stream":False}
            connection.request("POST", "/v1/chat/completions", canonical(request), {
                "Content-Type": "application/json", "Authorization": "Bearer " + host.token})
            response = connection.getresponse()
            self.assertEqual(response.status, 502)
            body = json.loads(response.read())
            self.assertEqual(body, {"error": {"code": "OFFLINE_REPLAY_HTTP_503"}})
            self.assertEqual(host.failure, {"domain": "PROVIDER", "code": "OFFLINE_REPLAY_HTTP_503"})
            self.assertEqual(ledger.usage()["provider_https_requests"], 0)
            connection.close()
        finally:
            host.close()


if __name__ == "__main__":
    unittest.main()

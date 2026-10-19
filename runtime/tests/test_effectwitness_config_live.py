"""Deterministic RPF-53 contract, budget and protocol tests; no Provider/network/Java."""
from __future__ import annotations

import json
import copy
import http.client
import importlib.util
import os
import subprocess
import socket
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from runtime.runproof_runtime.effectwitness.config_live_contracts import (
    BASE_SHA, LIMITS, PROVIDER_MODEL, SDK_CORE_SHA256, LiveContractRejected,
    canonical, make_contracts, strict_json, validate_contracts,
)
from runtime.runproof_runtime.effectwitness.config_live_runtime import (
    ConfigLiveBusiness, ConfigLiveHost, ConfigLiveMemoryBackend, LiveRuntimeRejected, ProviderLedger,
    _tool_schema_summary, _validate_provider_response, _validate_tool_registry,
)
from runtime.runproof_runtime.effectwitness.config_live_verify import evaluate_live_effect
from runtime.runproof_runtime.effectwitness.config_live_external import (
    _guard_events, _root_has_link_component, _runtime_archive_entry,
    _validated_run_usage,
    _safe_denied_basename,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_TEST_ROOT = ROOT / ".local" / "rpf-53-rev3" / "tests"
_PROBE_SPEC = importlib.util.spec_from_file_location(
    "rpf53_rev3_probe", ROOT / "spikes" / "rpf-53" / "probe.py")
_PROBE = importlib.util.module_from_spec(_PROBE_SPEC)
_PROBE_SPEC.loader.exec_module(_PROBE)


def _sdk_identity() -> dict:
    return {"python_version": "3.12.13", "python_executable_sha256": "a" * 64,
            "pydantic_record_sha256": "b" * 64, "pydantic_record_entries": 444,
            "pydantic_record_mismatches": 0, "openai_record_sha256": "c" * 64,
            "openai_record_entries": 2000, "openai_record_mismatches": 0,
            "openai_core_sha256": "d" * 64,
            "sdk_site_root_binding_sha256": "e" * 64,
            "python_runtime_mapping_sha256": "f" * 64}


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
    def test_pinned_run_usage_report_uses_only_verified_fields(self):
        class PinnedRunUsage:
            requests = 4
            tool_calls = 3
            input_tokens = 41
            output_tokens = 12

        report = _validated_run_usage(PinnedRunUsage(), PinnedRunUsage)
        self.assertEqual(report["usage_type"],
                         f"{PinnedRunUsage.__module__}.{PinnedRunUsage.__qualname__}")
        self.assertEqual(report["usage_fields"], [
            "input_tokens", "output_tokens", "requests", "tool_calls"])

    def test_usage_report_rejects_wrong_type_missing_field_and_bool_count(self):
        class PinnedRunUsage:
            requests = 4
            tool_calls = 3
            input_tokens = 41
            output_tokens = 12

        class MissingToolCalls:
            requests = 4
            input_tokens = 41
            output_tokens = 12

        with self.assertRaisesRegex(TypeError, "RPF53_USAGE_TYPE"):
            _validated_run_usage(PinnedRunUsage(), MissingToolCalls)
        with self.assertRaisesRegex(TypeError, "RPF53_USAGE_FIELD"):
            _validated_run_usage(MissingToolCalls(), MissingToolCalls)
        PinnedRunUsage.tool_calls = True
        with self.assertRaisesRegex(TypeError, "RPF53_USAGE_FIELD"):
            _validated_run_usage(PinnedRunUsage(), PinnedRunUsage)

    def test_fixture_report_requires_the_complete_pinned_usage_contract(self):
        report = {
            "status": "COMPLETED", "framework": "pydantic-ai-slim",
            "version": "2.57.0", "openai_version": "3.35.1", "pid": 123,
            "usage_type": "pydantic_ai.usage.RunUsage",
            "usage_fields": ["input_tokens", "output_tokens", "requests", "tool_calls"],
            "requests": 4, "input_tokens": 41, "output_tokens": 12,
            "tool_calls": 3, "tool_callbacks": 3,
            "sdk_source_sha256": SDK_CORE_SHA256,
            "openai_source_sha256": "d" * 64,
            "final_output_sha256": "e" * 64, "final_text_persisted": False,
            "guard_denials": [], "provider_key_present": False,
            "business_key_present": False,
        }
        self.assertTrue(_PROBE._fixture_report_valid(report, 123, {
            "openai_core_sha256": "d" * 64}))
        invalid = copy.deepcopy(report)
        invalid["usage_fields"].remove("tool_calls")
        self.assertFalse(_PROBE._fixture_report_valid(invalid, 123, {
            "openai_core_sha256": "d" * 64}))
        invalid = copy.deepcopy(report)
        invalid["tool_calls"] = True
        self.assertFalse(_PROBE._fixture_report_valid(invalid, 123, {
            "openai_core_sha256": "d" * 64}))

    def test_fixture_lineage_requires_four_completions_and_three_returned_call_ids(self):
        call_ids = [f"call_rpf53_fixture_{index}" for index in (1, 2, 3)]
        response_ids = [f"chatcmpl-rpf53-fixture-{index}" for index in (1, 2, 3, 4)]
        trace = []
        responses = [{"response_id": response_id, "model": "rpf53-fixture-only",
                      "tool_calls": [], "tool_returns": []}
                     for response_id in response_ids]
        for index, name in enumerate(("inspect_config", "create_config_v1", "update_config_v2")):
            result_sha = str(index + 1) * 64
            trace.append({"sequence": index + 1, "call_id": call_ids[index], "name": name,
                "provider_response_id": response_ids[index], "result_sha256": result_sha,
                "returned_in_request": index + 2})
            responses[index]["tool_calls"].append({"call_id": call_ids[index], "name": name})
        for response_index, response in enumerate(responses):
            response["tool_returns"] = [
                {"call_id": trace[index]["call_id"],
                 "result_sha256": trace[index]["result_sha256"]}
                for index in range(response_index)]
        host = SimpleNamespace(provider_responses=responses, tool_trace=trace)
        self.assertTrue(_PROBE._fixture_lineage_valid(host))
        returned_message_ids = _PROBE._fixture_return_message_ids(responses)
        self.assertEqual(len(returned_message_ids), 6)
        self.assertEqual(list(dict.fromkeys(returned_message_ids)), call_ids)
        completion_trace = _PROBE._fixture_completion_trace(responses)
        self.assertEqual(len(completion_trace), 4)
        self.assertEqual([len(item["tool_returns"]) for item in completion_trace], [0, 1, 2, 3])
        self.assertEqual(completion_trace[3]["tool_returns"][-1]["call_id"], call_ids[2])
        invalid = copy.deepcopy(host)
        invalid.provider_responses[3]["tool_returns"][0]["call_id"] = call_ids[1]
        self.assertFalse(_PROBE._fixture_lineage_valid(invalid))
        invalid = copy.deepcopy(host)
        invalid.provider_responses.pop()
        self.assertFalse(_PROBE._fixture_lineage_valid(invalid))

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


class ConfigLiveGuardTests(unittest.TestCase):
    def setUp(self):
        TASK_TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="guard-", dir=TASK_TEST_ROOT)
        self.root = Path(self.temp.name).resolve()
        self.sdk = self.root / "pinned-site-packages"
        self.runtime = self.root / "mapped-python-runtime"
        self.scratch = self.root / "task-scratch"
        self.outside = self.root / "outside"
        for path in (self.sdk, self.runtime, self.scratch, self.outside):
            path.mkdir()
        self.denied = []
        self.denied_files = []
        self.port = 43721
        self.audit = _guard_events(self.port, self.scratch, self.sdk,
            [self.runtime], self.root / "child.py", self.denied, self.denied_files)

    def tearDown(self):
        self.temp.cleanup()

    def _open(self, path, mode="r", flags=os.O_RDONLY):
        return self.audit("open", (str(path), mode, flags))

    def test_sdk_and_mapped_runtime_are_read_only(self):
        self._open(self.sdk / "pydantic_ai" / "__init__.py")
        self._open(self.sdk / "pydantic_ai" / "__pycache__" / "agent.pyc")
        self._open(self.runtime / "Lib" / "pathlib.py")
        with self.assertRaisesRegex(PermissionError, "RPF53_FILE_WRITE_DENIED"):
            self._open(self.sdk / "pydantic_ai" / "write.txt", "w", os.O_WRONLY | os.O_CREAT)
        self.assertEqual(self.denied_files[-1], {
            "category": "PINNED_SDK", "basename": "write.txt"})
        with self.assertRaisesRegex(PermissionError, "RPF53_FILE_WRITE_DENIED"):
            self.audit("os.chmod", (str(self.sdk / "pydantic_ai" / "__init__.py"), 0o600, None))
        self.assertEqual(self.denied_files[-1]["category"], "PINNED_SDK")

    def test_only_exact_configured_python_archive_is_mapped(self):
        prefix = self.runtime / "base-prefix"
        prefix.mkdir()
        archive = prefix / "python312.zip"
        self.assertEqual(_runtime_archive_entry(prefix, [str(archive)], (3, 12)), archive)
        self.assertIsNone(_runtime_archive_entry(prefix,
            [str(self.outside / "python312.zip")], (3, 12)))
        self.assertIsNone(_runtime_archive_entry(prefix,
            [str(prefix / "nested" / "python312.zip")], (3, 12)))
        self.assertIsNone(_runtime_archive_entry(prefix,
            [str(prefix / ".." / "base-prefix" / "python312.zip")], (3, 12)))
        audit = _guard_events(self.port, self.scratch, self.sdk,
            [archive], self.root / "child.py", self.denied, self.denied_files)
        self.assertIsNone(audit("open", (str(archive), "r", os.O_RDONLY)))
        with self.assertRaisesRegex(PermissionError, "RPF53_FILE_ACCESS_DENIED"):
            audit("open", (str(prefix / "neighbor.txt"), "r", os.O_RDONLY))

    def test_task_scratch_is_the_only_writable_root(self):
        self._open(self.scratch / "trace.json", "w", os.O_WRONLY | os.O_CREAT)
        self._open(self.scratch / "trace.json")
        with self.assertRaisesRegex(PermissionError, "RPF53_FILE_WRITE_DENIED"):
            self._open(self.runtime / "outside.txt", "w", os.O_WRONLY | os.O_CREAT)
        self.assertEqual(self.denied_files[-1]["category"], "PYTHON_RUNTIME_MAPPED")

    def test_basename_never_grants_access_to_outside_paths(self):
        old_rpf48_file = self.sdk.parent / "old-provider-log.json"
        same_basename = self.outside / "__init__.py"
        broad_user_path = Path.home() / "rpf53-guard-test.txt"
        for path in (old_rpf48_file, same_basename, broad_user_path):
            with self.subTest(path=path.name):
                with self.assertRaisesRegex(PermissionError, "RPF53_FILE_ACCESS_DENIED"):
                    self._open(path)
        self.assertEqual([item["category"] for item in self.denied_files],
                         ["OUTSIDE_ALLOWED"] * 3)
        self.assertEqual([item["basename"] for item in self.denied_files],
                         ["old-provider-log.json", "__init__.py", "rpf53-guard-test.txt"])

    def test_symlink_escape_is_resolved_before_allowlist_check(self):
        secret = self.outside / "__init__.py"
        secret.write_text("synthetic", encoding="utf-8")
        escape = self.scratch / "escape"
        try:
            try:
                escape.symlink_to(self.outside, target_is_directory=True)
            except OSError:
                if os.name != "nt":
                    raise
                result = subprocess.run(["cmd.exe", "/c", "mklink", "/J",
                    str(escape), str(self.outside)], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, check=False)
                if (result.returncode != 0 or not escape.is_dir()
                        or not getattr(escape, "is_junction", lambda: False)()):
                    self.fail("Windows could not create the task-owned junction fixture")
            self.assertTrue(_root_has_link_component(escape))
            with self.assertRaisesRegex(PermissionError, "RPF53_FILE_ACCESS_DENIED"):
                self._open(escape / "__init__.py")
            self.assertEqual(self.denied_files[-1], {
                "category": "OUTSIDE_ALLOWED", "basename": "__init__.py"})
            with self.assertRaisesRegex(PermissionError, "RPF53_FILE_WRITE_DENIED"):
                self._open(escape / "created.txt", "w", os.O_WRONLY | os.O_CREAT)
            self.assertEqual(self.denied_files[-1], {
                "category": "OUTSIDE_ALLOWED", "basename": "created.txt"})
        finally:
            if os.path.lexists(escape):
                if getattr(escape, "is_junction", lambda: False)():
                    escape.rmdir()
                else:
                    escape.unlink()

    def test_process_dns_and_non_host_socket_operations_are_denied(self):
        self.audit("socket.connect", (object(), ("127.0.0.1", self.port)))
        with self.assertRaisesRegex(PermissionError, "RPF53_PROCESS_EXEC_DENIED"):
            self.audit("subprocess.Popen", ())
        with self.assertRaisesRegex(PermissionError, "RPF53_NETWORK_DENIED"):
            self.audit("socket.connect", (object(), ("127.0.0.1", self.port + 1)))
        with self.assertRaisesRegex(PermissionError, "RPF53_DNS_DENIED"):
            self.audit("socket.getaddrinfo", ("provider.example", 443))
        with self.assertRaisesRegex(PermissionError, "RPF53_SOCKET_OPERATION_DENIED"):
            self.audit("socket.bind", (object(), ("127.0.0.1", 0)))

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
        strict_tools = copy.deepcopy(tools)
        for entry in strict_tools:
            entry["function"]["strict"] = True
        self.assertRegex(_validate_tool_registry(strict_tools), r"[0-9a-f]{64}")
        strict_tools[0]["function"]["strict"] = False
        with self.assertRaisesRegex(LiveRuntimeRejected, "SDK_TOOL_SCHEMA_SHAPE"):
            _validate_tool_registry(strict_tools)
        tools[0]["function"]["parameters"]["required"] = ["fake"]
        with self.assertRaisesRegex(LiveRuntimeRejected, "SDK_TOOL_SCHEMA_REQUIRED"):
            _validate_tool_registry(tools)

    def test_tool_schema_diagnostic_exposes_shape_without_untrusted_keys(self):
        summary = _tool_schema_summary([{"type": "function", "attacker-secret-key": "value",
            "function": {"name": "unknown-tool", "private-key": "secret",
                         "parameters": {"type": "object", "properties": {
                             "sensitive-field": {"type": "string"}}}}}])
        encoded = json.dumps(summary, sort_keys=True)
        self.assertNotIn("attacker-secret-key", encoded)
        self.assertNotIn("private-key", encoded)
        self.assertNotIn("sensitive-field", encoded)
        self.assertEqual(summary["entries"][0]["function_unknown_key_count"], 1)
        self.assertEqual(summary["entries"][0]["unknown_property_key_count"], 1)

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
                "openai_source_sha256": _sdk_identity()["openai_core_sha256"],
                "sdk_site_root_binding_sha256": "e" * 64,
                "python_runtime_mapping_sha256": "f" * 64}
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

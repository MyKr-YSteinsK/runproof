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
from unittest.mock import patch

from runtime.runproof_runtime.effectwitness.config_live_contracts import (
    AGENT_INSTRUCTIONS, BASE_SHA, LIMITS, PROVIDER_MODEL, SDK_CORE_SHA256,
    SOURCE_COMMIT, SOURCE_JAR_BYTES, SOURCE_JAR_SHA256, SOURCE_MANIFEST_SHA256,
    TASK_OWNED_JAR_PATH, TASK_PROMPT, TOOL_HELP, LiveContractRejected,
    canonical, digest, make_contracts, sha256_bytes as digest_bytes, strict_json, validate_contracts,
)
from runtime.runproof_runtime.effectwitness.config_live_runtime import (
    ConfigLiveBusiness, ConfigLiveHost, ConfigLiveMemoryBackend, LiveRuntimeRejected, ProviderLedger,
    _tool_schema_summary, _validate_provider_response, _validate_tool_registry,
)
from runtime.runproof_runtime.effectwitness.config_live_verify import (
    LiveEvidenceRejected, _sdk_executable_identity_valid, _sdk_process_identity_valid,
    evaluate_live_effect, seal_payload, validate_payload, verify_bytes,
)
from runtime.runproof_runtime.effectwitness import config_live_external as sdk_child
from runtime.runproof_runtime.effectwitness.config_live_external import (
    _guard_events, _root_has_link_component, _runtime_archive_entry,
    _validated_run_usage,
    _safe_denied_basename,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_TEST_ROOT = ROOT / ".local" / "rpf-53-rev6" / "tests"
_PROBE_SPEC = importlib.util.spec_from_file_location(
    "rpf53_rev6_probe", ROOT / "spikes" / "rpf-53" / "probe.py")
_PROBE = importlib.util.module_from_spec(_PROBE_SPEC)
_PROBE_SPEC.loader.exec_module(_PROBE)


def _sdk_identity() -> dict:
    return {"python_version": "3.12.13", "python_executable_sha256": "a" * 64,
            "python_launcher_sha256": "9" * 64,
            "pydantic_record_sha256": "b" * 64, "pydantic_record_entries": 444,
            "pydantic_record_mismatches": 0, "openai_record_sha256": "c" * 64,
            "openai_record_entries": 2000, "openai_record_mismatches": 0,
            "openai_core_sha256": "d" * 64,
            "sdk_site_root_binding_sha256": "e" * 64,
            "python_runtime_mapping_sha256": "f" * 64}


def _contracts(*, fixture: bool = False, agent_port: int | None = None) -> dict:
    suffix = "0123456789abcdef"
    port = agent_port or (47322 if fixture else 47323)
    task_owned_jar = {
        "relative_path": TASK_OWNED_JAR_PATH,
        "source_commit": SOURCE_COMMIT,
        "manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_sha256": SOURCE_JAR_SHA256,
        "source_bytes": SOURCE_JAR_BYTES,
        "copy_sha256": SOURCE_JAR_SHA256,
        "copy_bytes": SOURCE_JAR_BYTES,
        "path_within_task_root": True,
        "no_link_components": True,
        "copy_verified": True,
    }
    return make_contracts(run_id="rpf53-test-" + suffix, suffix=suffix,
        java_port=None if fixture else 47321,
        agent_port=port,
        prepared_at_utc="2026-10-18T00:00:00Z", runtime_source_sha256="e" * 64,
        sdk_identity=_sdk_identity(),
        task_owned_jar=task_owned_jar,
        tool_schema_sha256=None if fixture else "f" * 64,
        mode="FIXTURE_TEST_ONLY" if fixture else "REAL_PROVIDER")


def _synthetic_payload() -> dict:
    """Structural test data only; never a real Provider observation or certificate."""
    saved = json.loads((ROOT / "spikes/rpf-53/rev-5/live-summary.json").read_bytes())
    contracts = _contracts()
    current = next(o for o in saved["http_observations"] if o["kind"] == "final_current")["response"]["data"]
    raw = json.dumps(saved)
    for key in ("app", "env", "key"):
        raw = raw.replace(current[key], contracts["effect"][key])
    raw = raw.replace(saved["run_id"], contracts["experiment"]["run_id"])
    for i, row in enumerate(saved["provider_requests"], 1):
        raw = raw.replace(row["response_id"], f"synthetic-response-{i}")
    for i, row in enumerate(saved["tool_trace"], 1):
        raw = raw.replace(row["call_id"], f"synthetic-call-{i}")
    saved = json.loads(raw)
    trace = saved["tool_trace"]
    for obs in saved["http_observations"]:
        obs["response_body_sha256"] = digest(obs["response"])
    for call in trace:
        call["arguments_sha256"] = digest(call["arguments"])
        call["result_sha256"] = digest(call["result"])
    responses = []
    for i, row in enumerate(saved["provider_requests"]):
        row["request_sha256"] = digest({"synthetic_request": i})
        row["tool_schema_sha256"] = contracts["execution"]["tool_schema_sha256"]
        returns = [{"call_id": t["call_id"], "result_sha256": t["result_sha256"]}
                   for t in trace[:i]]
        responses.append({"response_id": row["response_id"], "model": PROVIDER_MODEL,
            "usage": row["usage"], "tool_calls": [{"call_id": t} for t in row["tool_call_ids"]],
            "tool_returns": returns})
    sid = _sdk_identity()
    report = saved["sdk"]
    report.update(popen_pid=4101, ready_pid=4101, pid=4101,
                  python_executable_sha256=sid["python_executable_sha256"],
                  sdk_source_sha256=SDK_CORE_SHA256, openai_source_sha256=sid["openai_core_sha256"])
    jar = copy.deepcopy(saved["java"]["jar_provenance"])
    jar["task_relative_path"] = TASK_OWNED_JAR_PATH
    safety = {"java_pid": 4102, "java_listener_pid": 4102, "java_exit_code": 0,
        "java_stopped": True, "java_listener_closed": True, "java_external_connections": [],
        "java_jar_provenance": jar, "sdk_pid": 4101, "sdk_stopped": True,
        "sdk_external_connections": [], "host_closed": True, "parent_external_connections": [],
        "sdk_provider_key_absent": True, "sdk_business_key_absent": True, "sdk_guard_denials": []}
    preflight = {"base": {"runtime_source": {"sha256": contracts["experiment"]["runtime_source_sha256"]},
        "sdk": {**sid, "pydantic": {"record_sha256": sid["pydantic_record_sha256"],
            "record_entries": 444, "record_mismatches": 0},
            "openai": {"record_sha256": sid["openai_record_sha256"],
                "record_entries": 2000, "record_mismatches": 0}}}}
    host = SimpleNamespace(provider_responses=responses, tool_trace=trace,
        tool_schema_sha256=contracts["execution"]["tool_schema_sha256"],
        visible_contract_checks=[{"instructions_present": True, "task_prompt_present": True,
            "tool_help_exact": True, "messages_sha256": digest({"synthetic_messages": i})}
            for i in range(4)])
    ledger = SimpleNamespace(data={"requests": saved["provider_requests"]}, usage=lambda: saved["provider_usage"])
    return _PROBE._make_payload(preflight, contracts, report, host, ledger,
        SimpleNamespace(observations=saved["http_observations"]), saved["authority_before"],
        saved["authority_after"], {"version": "17.0.12", "executable_sha256": "8" * 64}, safety)


class ConfigLiveWitnessTests(unittest.TestCase):
    def test_complete_synthetic_success_path_uses_production_payload_builder(self):
        payload = _synthetic_payload()
        self.assertEqual(validate_payload(payload)["outcome"], "CONTRACT_SATISFIED_IN_RUN")
        self.assertEqual(verify_bytes(seal_payload(payload)), payload["oracle"])

    def assert_rehashed_rejection(self, payload, mutate):
        envelope = json.loads(seal_payload(payload))
        mutate(envelope["payload"])
        envelope["payload_sha256"] = digest(envelope["payload"])
        with self.assertRaises(LiveEvidenceRejected):
            verify_bytes(canonical(envelope))

    def test_missing_payload_and_each_contract_field_are_controlled_rejections(self):
        payload = _synthetic_payload()
        paths = [(key,) for key in payload]
        def fields(value, path):
            if type(value) is dict:
                for key, child in value.items():
                    paths.append((*path, key))
                    fields(child, (*path, key))
        fields(payload["contracts"], ("contracts",))
        for path in paths:
            def remove(value, path=path):
                for key in path[:-1]:
                    value = value[key]
                value.pop(path[-1])
            with self.subTest(path=path):
                self.assert_rehashed_rejection(payload, remove)

    def test_malformed_nested_containers_never_escape_as_python_exceptions(self):
        payload = _synthetic_payload()
        paths = [(key,) for key in payload if type(payload[key]) in (dict, list)]
        paths += [("contracts", key) for key in ("execution", "effect", "experiment")]
        paths += [("provider", "attempts", 0), ("provider", "attempts", 0, "tool_returns"),
                  ("provider", "attempts", 0, "usage"), ("tool_trace", 0),
                  ("http_observations", 0), ("agent_contract_visibility", 0)]
        for path in paths:
            for malformed in (None, 1, "wrong-shape", [None], {"unexpected": None}):
                def replace(value, path=path, malformed=malformed):
                    for key in path[:-1]:
                        value = value[key]
                    value[path[-1]] = malformed
                with self.subTest(path=path, malformed=malformed):
                    self.assert_rehashed_rejection(payload, replace)

    def test_rehashed_source_lineage_authority_budget_and_visibility_tampers(self):
        payload = _synthetic_payload()
        def history(value):
            obs = value["http_observations"][value["authority_after"]["history_seq"] - 1]
            obs["response"]["data"][0]["value"] = "forged"
            obs["response_body_sha256"] = digest(obs["response"])
        def bool_version(value):
            call = value["tool_trace"][2]
            call["arguments"]["expected_version"] = True
            call["arguments_sha256"] = digest(call["arguments"])
        cases = {
            "provider": lambda p: p["provider"].update(name="SCRIPTED"),
            "sdk_pid": lambda p: p["sdk"].update(ready_pid=4102),
            "sdk_source": lambda p: p["sdk"].update(openai_source_sha256="7" * 64),
            "jar_source": lambda p: p["safety"]["java_jar_provenance"].update(copy_sha256="7" * 64),
            "tool_return_loss": lambda p: p["provider"]["attempts"][3]["tool_returns"].pop(),
            "tool_return_swap": lambda p: p["provider"]["attempts"][3]["tool_returns"].reverse(),
            "provider_response": lambda p: p["provider"]["attempts"][0].update(response_id="forged"),
            "source_digest": lambda p: p["source_identity"].update(runtime_source_sha256="7" * 64),
            "history": history, "boolean_version": bool_version,
            "budget": lambda p: p["provider"]["usage"].update(estimated_cost_cny_upper=1.01),
            "sdk_usage": lambda p: p["sdk"].update(input_tokens=0),
            "visibility": lambda p: p["agent_contract_visibility"][0].update(instructions_present=1),
            "visibility_loss": lambda p: p["agent_contract_visibility"].clear(),
            "release_authority": lambda p: p["contracts"]["execution"].update(release_authority="AGENT"),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                self.assert_rehashed_rejection(payload, mutate)

    def test_invalid_json_and_issuance_identity_are_controlled_rejections(self):
        for raw in (b'{}', b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff', b'[]'):
            with self.subTest(raw=raw), self.assertRaises(LiveEvidenceRejected):
                verify_bytes(raw)
        envelope = json.loads(seal_payload(_synthetic_payload()))
        for key, value in (("issuance_kind", "DERIVED_POSTHOC"), ("issued_at_utc", "invalid"),
                           ("verifier_identity", {"sha256": "f" * 64})):
            invalid = {**envelope, key: value}
            with self.subTest(key=key), self.assertRaises(LiveEvidenceRejected):
                verify_bytes(canonical(invalid))

    def test_real_independent_cli_anchors_and_rehashed_tamper(self):
        TASK_TEST_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TASK_TEST_ROOT) as directory:
            path = Path(directory) / "FIXTURE_SCRIPTED-envelope.json"
            raw = seal_payload(_synthetic_payload())
            path.write_bytes(raw)
            self.assertEqual(_PROBE._verify_in_independent_process(path, digest_bytes(raw)), 0)
            self.assertEqual(_PROBE._verify_in_independent_process(path, None), 2)
            self.assertEqual(_PROBE._verify_in_independent_process(path, "0" * 64), 3)
            envelope = json.loads(raw)
            envelope["payload"]["sdk"]["ready_pid"] = 9999
            envelope["payload_sha256"] = digest(envelope["payload"])
            raw = canonical(envelope)
            path.write_bytes(raw)
            self.assertEqual(_PROBE._verify_in_independent_process(path, digest_bytes(raw)), 4)

    def test_output_status_can_grow_but_frozen_identity_cannot_change(self):
        previous = {"repo": {"head": BASE_SHA, "branch": "fixed", "status_paths": ["before"],
                             "docs_reviews_untracked_untouched": True},
                    "runtime_source": {"sha256": "a" * 64}}
        current = copy.deepcopy(previous)
        current["repo"]["status_paths"] = ["after", "allowed-output.json"]
        self.assertTrue(_PROBE._same_frozen_preflight(previous, current))
        for key in ("head", "branch", "docs_reviews_untracked_untouched"):
            invalid = copy.deepcopy(current)
            invalid["repo"][key] = "changed"
            self.assertFalse(_PROBE._same_frozen_preflight(previous, invalid))
        current["runtime_source"]["sha256"] = "b" * 64
        self.assertFalse(_PROBE._same_frozen_preflight(previous, current))

    def test_scope_rejects_unapproved_paths_and_staged_contamination(self):
        TASK_TEST_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TASK_TEST_ROOT) as directory:
            outputs = Path(directory)
            with patch.object(_PROBE, "REV6_DIR", outputs), patch.object(_PROBE, "_status_paths") as status, \
                    patch.object(_PROBE.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as git:
                status.return_value = ["docs/reviews/", "spikes/rpf-53/rev-6/"]
                (outputs / "README.md").write_text("synthetic", encoding="utf-8")
                _PROBE._check_status_scope()
                (outputs / "live-summary.json").write_text("{}", encoding="utf-8")
                _PROBE._check_status_scope()
                (outputs / "rogue.json").write_text("{}", encoding="utf-8")
                with self.assertRaises(_PROBE.ProbeError):
                    _PROBE._check_status_scope()
                for path in ("docs/reviews-escape/file", "runtime/unauthorized.py", "../outside"):
                    status.return_value = ["docs/reviews/", path]
                    with self.subTest(path=path), self.assertRaises(_PROBE.ProbeError):
                        _PROBE._check_status_scope()
                status.return_value = ["docs/reviews/"]
                with patch.object(Path, "iterdir", side_effect=AssertionError("protected enumeration")):
                    _PROBE._check_status_scope()
                git.return_value.returncode = 1
                with self.assertRaisesRegex(_PROBE.ProbeError, "UNEXPECTED_STAGED_CHANGE"):
                    _PROBE._check_status_scope()

    def test_total_ledger_reserves_before_network_and_prevents_second_trial(self):
        TASK_TEST_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TASK_TEST_ROOT) as directory:
            root = Path(directory)
            with patch.object(_PROBE, "TOTAL_BUDGET_PATH", root / "total-budget.json"):
                ledger = _PROBE.Rev6ProviderLedger(root / "ledger.json", "rpf53-synthetic", create=True)
                ledger.reserve({"synthetic_request": True}, [])
                total = json.loads((root / "total-budget.json").read_bytes())
                self.assertGreater(total["reserved_or_confirmed_tokens"], 0)
                self.assertFalse(total["trials"][0]["usage"]["usage_known"])
                with self.assertRaisesRegex(_PROBE.ProbeError, "TOTAL_BUDGET_ALREADY_RESERVED"):
                    _PROBE.Rev6ProviderLedger(root / "second.json", "rpf53-other", create=True)

    def test_live_offline_gate_requires_fresh_source_controls_gap_and_regression(self):
        TASK_TEST_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TASK_TEST_ROOT) as directory:
            path = Path(directory) / "verification-preflight.json"
            value = {"status": "PASS", "model_source": "FIXTURE_SCRIPTED",
                "runtime_source_sha256": "a" * 64,
                "verifier_exit_codes": {"correct": 0, "missing": 2, "wrong": 3},
                "tamper_controls": [{"exit_code": 4}] * 4,
                "rev5_live_visibility_recoverable": False, "regression_pass": True}
            with patch.object(_PROBE, "OFFLINE_GATE_PATH", path), patch.object(
                    _PROBE, "_runtime_source_identity", return_value={"sha256": "a" * 64}):
                path.write_bytes(canonical(value))
                _PROBE._offline_witness_gate(require_regression=True)
                for key, bad in (("runtime_source_sha256", "b" * 64),
                                 ("tamper_controls", [{"exit_code": 0}] * 4),
                                 ("rev5_live_visibility_recoverable", True),
                                 ("regression_pass", False)):
                    path.write_bytes(canonical({**value, key: bad}))
                    with self.subTest(key=key), self.assertRaises(_PROBE.ProbeError):
                        _PROBE._offline_witness_gate(require_regression=True)


class ConfigLiveContractsTests(unittest.TestCase):
    def test_fixture_retry_allows_source_repair_without_sdk_identity_transition(self):
        previous = {
            "repo": {"branch": "codex/rpf-53-rev5-live-config-contract-jar-closeout",
                     "status_paths": ["before"]},
            "source": {"manifest": "fixed"}, "task_owned_jar": {"sha256": "fixed"},
            "sdk": {"python_executable_sha256": "a" * 64,
                    "python_runtime_mapping_sha256": "b" * 64},
            "java": {"version": "17.0.12"}, "provider": {"model": "deepseek-flash"},
            "push_effect": {"release": "none"},
            "runtime_source": {"sha256": "c" * 64},
        }
        repaired = copy.deepcopy(previous)
        repaired["repo"]["status_paths"] = ["after"]
        repaired["runtime_source"]["sha256"] = "d" * 64
        self.assertTrue(_PROBE._diagnostic_retry_identity_valid(previous, repaired))

        changed_sdk = copy.deepcopy(repaired)
        changed_sdk["sdk"]["python_runtime_mapping_sha256"] = "e" * 64
        self.assertFalse(_PROBE._diagnostic_retry_identity_valid(previous, changed_sdk))
        unchanged_source = copy.deepcopy(previous)
        self.assertFalse(_PROBE._diagnostic_retry_identity_valid(previous, unchanged_source))

    def test_agent_visible_task_and_tool_help_freeze_the_exact_synthetic_contract(self):
        self.assertIn("inspect_config", AGENT_INSTRUCTIONS)
        self.assertIn('value="rpf53-v1"', AGENT_INSTRUCTIONS)
        self.assertIn("expected_version=1", AGENT_INSTRUCTIONS)
        self.assertIn('value="rpf53-v2"', AGENT_INSTRUCTIONS)
        self.assertIn('{"value":"rpf53-v1"}', TASK_PROMPT)
        self.assertIn('{"expected_version":1,"value":"rpf53-v2"}', TASK_PROMPT)
        self.assertIn("UNKNOWN_OUTCOME", TASK_PROMPT)
        self.assertEqual(set(TOOL_HELP), {
            "inspect_config", "create_config_v1", "update_config_v2"})
        self.assertEqual(sdk_child.TOOL_HELP, TOOL_HELP)
        self.assertIn("rpf53-v1", TOOL_HELP["create_config_v1"])
        self.assertIn("rpf53-v2", TOOL_HELP["update_config_v2"])
        self.assertIn("expected_version 1", TOOL_HELP["update_config_v2"])

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

    def test_fixture_report_checks_every_field_and_three_process_identities(self):
        report = {
            "status": "COMPLETED", "framework": "pydantic-ai-slim",
            "version": "2.57.0", "openai_version": "3.35.1", "pid": 123,
            "python_executable_sha256": "a" * 64,
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
        sdk = {"openai_core_sha256": "d" * 64,
               "python_executable_sha256": "a" * 64}
        checks = _PROBE._fixture_report_checks(report, 123, 123, sdk)
        self.assertTrue(all(type(value) is bool for value in checks.values()))
        self.assertTrue(all(checks.values()))
        self.assertTrue(checks["popen_ready_pid_equal"])
        self.assertTrue(checks["ready_completed_pid_equal"])
        self.assertTrue(checks["popen_completed_pid_equal"])
        cases = ((124, 123, 123, "popen_ready_pid_equal"),
                 (123, 124, 123, "ready_completed_pid_equal"),
                 (123, 123, 124, "ready_completed_pid_equal"))
        for popen_pid, ready_pid, report_pid, failed_check in cases:
            invalid = copy.deepcopy(report)
            invalid["pid"] = report_pid
            invalid_checks = _PROBE._fixture_report_checks(
                invalid, popen_pid, ready_pid, sdk)
            self.assertFalse(all(invalid_checks.values()))
            self.assertFalse(invalid_checks[failed_check])
        invalid = copy.deepcopy(report)
        invalid["usage_fields"].remove("tool_calls")
        self.assertFalse(_PROBE._fixture_report_checks(invalid, 123, 123, sdk)[
            "report_usage_fields_exact"])
        invalid = copy.deepcopy(report)
        invalid["tool_calls"] = True
        self.assertFalse(_PROBE._fixture_report_checks(invalid, 123, 123, sdk)[
            "usage_tool_calls_integer"])

    def test_fixture_report_rejects_missing_extra_hash_usage_and_guard_fields(self):
        report = {
            "status": "COMPLETED", "framework": "pydantic-ai-slim",
            "version": "2.57.0", "openai_version": "3.35.1", "pid": 123,
            "python_executable_sha256": "a" * 64,
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
        sdk = {"openai_core_sha256": "d" * 64,
               "python_executable_sha256": "a" * 64}
        cases = (
            (lambda value: value.pop("output_tokens"), "report_fields_exact"),
            (lambda value: value.update(unexpected="value"), "report_fields_exact"),
            (lambda value: value.update(sdk_source_sha256="f" * 64), "sdk_source_hash_pinned"),
            (lambda value: value.update(python_executable_sha256="f" * 64),
             "report_python_executable_hash_pinned"),
            (lambda value: value.update(usage_type="OtherUsage"), "report_runusage_type_pinned"),
            (lambda value: value.update(usage_fields=["requests"]), "report_usage_fields_exact"),
            (lambda value: value.update(input_tokens=-1), "usage_input_tokens_nonnegative"),
            (lambda value: value.update(guard_denials=["RPF53_NETWORK_DENIED"]), "guard_denials_empty"),
        )
        for mutate, failed_check in cases:
            invalid = copy.deepcopy(report)
            mutate(invalid)
            checks = _PROBE._fixture_report_checks(invalid, 123, 123, sdk)
            self.assertFalse(checks[failed_check])

    def test_fixture_diagnostic_public_report_never_keeps_arbitrary_text(self):
        report = {
            "status": "secret-token-value", "framework": "pydantic-ai-slim",
            "version": "2.57.0", "openai_version": "3.35.1", "pid": 123,
            "python_executable_sha256": "a" * 64,
            "usage_type": "pydantic_ai.usage.RunUsage",
            "usage_fields": ["input_tokens", "output_tokens", "requests", "tool_calls"],
            "requests": 4, "input_tokens": 41, "output_tokens": 12,
            "tool_calls": 3, "tool_callbacks": 3,
            "sdk_source_sha256": SDK_CORE_SHA256,
            "openai_source_sha256": "d" * 64,
            "final_output_sha256": "e" * 64, "final_text_persisted": False,
            "guard_denials": [], "provider_key_present": False,
            "business_key_present": False, "private_text": "raw-private-output",
        }
        serialized = json.dumps(_PROBE._safe_sdk_report(report), sort_keys=True)
        self.assertNotIn("secret-token-value", serialized)
        self.assertNotIn("raw-private-output", serialized)
        self.assertNotIn("private_text", serialized)
        self.assertEqual(_PROBE._safe_sdk_report(report)[
            "python_executable_sha256"], "a" * 64)
        self.assertEqual(_PROBE._safe_report_field_names(report)[
            "unexpected_field_names"], ["private_text"])

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
        invalid = copy.deepcopy(host)
        invalid.tool_trace[1]["call_id"] = call_ids[0]
        self.assertFalse(_PROBE._fixture_lineage_valid(invalid))
        invalid = copy.deepcopy(host)
        invalid.tool_trace[1]["returned_in_request"] = 5
        self.assertFalse(_PROBE._fixture_lineage_valid(invalid))

    def test_offline_live_witness_requires_bound_popen_ready_and_report_pids(self):
        valid = {"popen_pid": 123, "ready_pid": 123, "pid": 123}
        self.assertTrue(_sdk_process_identity_valid(valid))
        for invalid in (
                {"popen_pid": 124, "ready_pid": 123, "pid": 123},
                {"popen_pid": 123, "ready_pid": 124, "pid": 123},
                {"popen_pid": 123, "ready_pid": 123, "pid": 124},
                {"popen_pid": True, "ready_pid": 1, "pid": 1},
                {"popen_pid": 123, "ready_pid": 123},
        ):
            self.assertFalse(_sdk_process_identity_valid(invalid))

    def test_offline_live_witness_binds_child_executable_to_source_identity(self):
        sdk = {"python_executable_sha256": "a" * 64}
        source = {"python_executable_sha256": "a" * 64,
                  "python_launcher_sha256": "b" * 64}
        framework = {"python_executable_sha256": "a" * 64,
                     "python_launcher_sha256": "b" * 64}
        self.assertTrue(_sdk_executable_identity_valid(sdk, source, framework))
        self.assertFalse(_sdk_executable_identity_valid(
            {"python_executable_sha256": "c" * 64}, source, framework))
        self.assertFalse(_sdk_executable_identity_valid(
            sdk, source, {**framework, "python_launcher_sha256": "d" * 64}))

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
    def test_task_owned_jar_gate_accepts_only_the_copy_under_this_run_root(self):
        TASK_TEST_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="jar-gate-", dir=TASK_TEST_ROOT) as temporary:
            root = Path(temporary) / "task-root"
            jar_dir = root / "jar"
            jar_dir.mkdir(parents=True)
            jar = jar_dir / "config-center-server-1.0.0.jar"
            jar.write_bytes(b"synthetic fixed JAR bytes")
            outside = Path(temporary) / "old-source.jar"
            outside.write_bytes(b"same source content, wrong ownership")
            self.assertTrue(_PROBE._argv_jar_path_matches(
                ["java.exe", "-Dtest=1", "-jar", str(jar)], jar, root))
            self.assertFalse(_PROBE._argv_jar_path_matches(
                ["java.exe", "-jar", str(outside)], jar, root))
            self.assertFalse(_PROBE._argv_jar_path_matches(
                ["java.exe", "-jar", str(jar), "-jar", str(outside)], jar, root))
            self.assertFalse(_PROBE._argv_jar_path_matches(
                ["java.exe", "-jar", str(root / ".." / "old-source.jar")], jar, root))
        self.assertEqual(_PROBE.TASK_OWNED_JAR.relative_to(ROOT).as_posix(),
                         TASK_OWNED_JAR_PATH)

    def test_sdk_tool_registry_accepts_omitted_empty_required_only(self):
        tools = [
            {"type": "function", "function": {"name": "inspect_config",
             "description": TOOL_HELP["inspect_config"], "parameters": {"type": "object",
             "properties": {}, "additionalProperties": False}}},
            {"type": "function", "function": {"name": "create_config_v1",
             "description": TOOL_HELP["create_config_v1"], "parameters": {"type": "object",
             "properties": {"value": {"type": "string"}}, "required": ["value"],
             "additionalProperties": False}}},
            {"type": "function", "function": {"name": "update_config_v2",
             "description": TOOL_HELP["update_config_v2"], "parameters": {"type": "object",
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
        tools = copy.deepcopy(strict_tools)
        tools[0]["function"]["strict"] = True
        tools[0]["function"]["description"] = "not the frozen help text"
        with self.assertRaisesRegex(LiveRuntimeRejected, "SDK_TOOL_DESCRIPTION"):
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
            business.invoke("create_config_v1", {"value": "private-free-text"})
        create_diagnostic = business.safe_rejections[-1]
        self.assertEqual(create_diagnostic["key_shape"], "EXACT")
        self.assertEqual(create_diagnostic["argument_types"], {"value": "STRING"})
        self.assertFalse(create_diagnostic["expected_value_match"])
        self.assertRegex(create_diagnostic["arguments_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("private-free-text", json.dumps(create_diagnostic))
        with self.assertRaisesRegex(LiveRuntimeRejected, "CREATE_ARGUMENTS_REJECTED"):
            business.invoke("create_config_v1", {"value": 11})
        self.assertEqual(business.safe_rejections[-1]["argument_types"]["value"], "INTEGER")
        with self.assertRaisesRegex(LiveRuntimeRejected, "TOOL_ARGUMENT_SHAPE"):
            business.invoke("create_config_v1", {
                "value": "private-free-text", "private-field-name": "private-field-value"})
        shape_diagnostic = business.safe_rejections[-1]
        self.assertEqual(shape_diagnostic["key_shape"], "EXTRA")
        self.assertEqual(shape_diagnostic["unknown_key_count"], 1)
        self.assertNotIn("private-field-name", json.dumps(shape_diagnostic))
        self.assertNotIn("private-field-value", json.dumps(shape_diagnostic))
        with self.assertRaisesRegex(LiveRuntimeRejected, "CREATE_WITHOUT_CONFIRMED_ABSENCE"):
            business.invoke("create_config_v1", {"value": "rpf53-v1"})
        with self.assertRaisesRegex(LiveRuntimeRejected, "UPDATE_WITHOUT_CONFIRMED_CREATE"):
            business.invoke("update_config_v2", {
                "expected_version": 1, "value": "rpf53-v2"})
        with self.assertRaisesRegex(LiveRuntimeRejected, "UPDATE_ARGUMENTS_REJECTED"):
            business.invoke("update_config_v2", {
                "expected_version": True, "value": "rpf53-v2"})
        update_diagnostic = business.safe_rejections[-1]
        self.assertEqual(update_diagnostic["argument_types"], {
            "expected_version": "BOOLEAN", "value": "STRING"})
        self.assertFalse(update_diagnostic["expected_version_match"])
        self.assertEqual(client.requests, [])

    def test_host_retains_only_bounded_rejection_metadata_without_raw_argument(self):
        class Client:
            stop_writes = False

            def request(self, kind):
                raise AssertionError("rejected arguments must not reach HTTP")

        contracts = _contracts(fixture=True)
        ledger = ProviderLedger.fixture_only(contracts["experiment"]["run_id"])
        business = ConfigLiveBusiness(contracts, Client())
        host = ConfigLiveHost(contracts, ledger, business, fixture=True)
        arguments = {"value": "private-free-text"}
        host.runtime = {"pid": 123}
        host.intents["call_rpf53_rejected"] = {
            "response_id": "chatcmpl-rpf53-rejected",
            "call_id": "call_rpf53_rejected", "name": "create_config_v1",
            "arguments_sha256": digest(arguments), "arguments": arguments}
        with self.assertRaisesRegex(LiveRuntimeRejected, "CREATE_ARGUMENTS_REJECTED"):
            host._tool({"call_id": "call_rpf53_rejected",
                        "name": "create_config_v1", "arguments": arguments})
        encoded = json.dumps(host.tool_rejections, sort_keys=True)
        self.assertNotIn("private-free-text", encoded)
        self.assertEqual(host.tool_rejections[0]["call_id"], "call_rpf53_rejected")
        self.assertEqual(host.tool_rejections[0]["expected_value_match"], False)
        self.assertRegex(host.tool_rejections[0]["arguments_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(host.tool_trace, [])

    def test_business_allows_one_exact_create_and_stops_after_unknown_response(self):
        class Client:
            def __init__(self, create_unknown=False):
                self.stop_writes = False
                self.create_unknown = create_unknown
                self.requests = []
                self.effect = _contracts()["effect"]

            def request(self, kind):
                self.requests.append(kind)
                if kind == "inspect_config":
                    return {"status": 404, "transport_error": None,
                        "content_type": "application/json", "response": {
                            "code": 4041, "message": "not found", "data": None,
                            "traceId": None}}
                if kind == "create_config_v1" and self.create_unknown:
                    return {"status": None, "transport_error": "TIMEOUT",
                            "content_type": None, "response": None}
                item = {name: self.effect[name] for name in ("app", "env", "key")}
                item.update(value="rpf53-v1", description=None, version=1,
                            updatedAt="2026-10-18T00:00:00Z")
                return {"status": 200, "transport_error": None,
                    "content_type": "application/json", "response": {
                        "code": 0, "message": "ok", "data": item, "traceId": None}}

        client = Client()
        business = ConfigLiveBusiness(_contracts(), client)
        self.assertEqual(business.invoke("inspect_config", {}), {"state": "ABSENT"})
        self.assertEqual(business.invoke("create_config_v1", {"value": "rpf53-v1"})[
            "status"], "COMMITTED")
        with self.assertRaisesRegex(LiveRuntimeRejected, "CREATE_WITHOUT_CONFIRMED_ABSENCE"):
            business.invoke("create_config_v1", {"value": "rpf53-v1"})
        self.assertEqual(client.requests.count("create_config_v1"), 1)

        uncertain_client = Client(create_unknown=True)
        uncertain = ConfigLiveBusiness(_contracts(), uncertain_client)
        uncertain.invoke("inspect_config", {})
        outcome = uncertain.invoke("create_config_v1", {"value": "rpf53-v1"})
        self.assertEqual(outcome["status"], "UNKNOWN_OUTCOME")
        self.assertTrue(uncertain_client.stop_writes)
        with self.assertRaisesRegex(LiveRuntimeRejected, "UPDATE_WITHOUT_CONFIRMED_CREATE"):
            uncertain.invoke("update_config_v2", {
                "expected_version": 1, "value": "rpf53-v2"})
        self.assertEqual(uncertain_client.requests.count("create_config_v1"), 1)
        self.assertNotIn("update_config_v2", uncertain_client.requests)

    def test_host_ready_binds_the_reported_python_executable_hash(self):
        contracts = _contracts(fixture=True)
        ledger = ProviderLedger.fixture_only(contracts["experiment"]["run_id"])
        host = ConfigLiveHost(contracts, ledger, ConfigLiveMemoryBackend(), fixture=True)
        ready = {"framework": "pydantic-ai-slim", "version": "2.57.0",
            "openai_version": "3.35.1", "pid": os.getpid(),
            "python_executable_sha256": "f" * 64,
            "sdk_source_sha256": SDK_CORE_SHA256,
            "openai_source_sha256": _sdk_identity()["openai_core_sha256"],
            "sdk_site_root_binding_sha256": "e" * 64,
            "python_runtime_mapping_sha256": "f" * 64}
        with self.assertRaisesRegex(LiveRuntimeRejected, "SDK_READY_IDENTITY"):
            host._ready(ready)
        self.assertIsNone(host.runtime)
        ready["python_executable_sha256"] = _sdk_identity()["python_executable_sha256"]
        self.assertEqual(host._ready(ready), {"status": "AGENT_RUNTIME_CONNECTED"})

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
                "python_executable_sha256": _sdk_identity()["python_executable_sha256"],
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
                 "description": TOOL_HELP["inspect_config"], "parameters": {"type": "object",
                 "properties": {}, "additionalProperties": False}}},
                {"type": "function", "function": {"name": "create_config_v1",
                 "description": TOOL_HELP["create_config_v1"], "parameters": {"type": "object",
                 "properties": {"value": {"type": "string"}}, "required": ["value"],
                 "additionalProperties": False}}},
                {"type": "function", "function": {"name": "update_config_v2",
                 "description": TOOL_HELP["update_config_v2"], "parameters": {"type": "object",
                 "properties": {"expected_version": {"type": "integer"},
                                 "value": {"type": "string"}},
                 "required": ["expected_version", "value"],
                 "additionalProperties": False}}},
            ]
            request = {"model": "rpf53-fixture-only", "messages":[
                {"role":"system","content":AGENT_INSTRUCTIONS},
                {"role":"user","content":TASK_PROMPT}], "tools":tools,
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

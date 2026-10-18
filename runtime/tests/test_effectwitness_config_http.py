from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.runproof_runtime.effectwitness.config_http_adapter import (
    AdapterRejected, ConfigAuthorityReader, ConfigToolHost,
)
from runtime.runproof_runtime.effectwitness.config_http_contracts import (
    ContractRejected, FrozenContracts, canonical, digest, make_contracts,
)
from runtime.runproof_runtime.effectwitness.config_http_oracle import (
    OBSERVATION_KINDS, _expected_path, _expected_request, evaluate_config_effect,
)
from runtime.runproof_runtime.effectwitness.config_http_witness import (
    WitnessRejected, build_witness, seal, verify_bytes,
)

_GOOD = "a" * 64
_REV1_PARENT = "b3271eaaf408dffa1ecd6f26f1b47fab5cede289"
_REV2_PARENT = "6753ac17ee079bf94562bfd9879bfd3c11ff74c0"
_REV3_PARENT = "68ac08de12048856fe38aa7e8548ad5bb3516a9b"
_REV4_PARENT = "1c4c3a382808a98613b1e659dfcddbc1d5ebc67e"


def _load_probe_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "spikes" / "rpf-51" / "probe.py"
    spec = importlib.util.spec_from_file_location("rpf51_probe_under_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("RPF-51 probe module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PROBE = _load_probe_module()


def make_contract_bundle(parent: str = _REV1_PARENT) -> FrozenContracts:
    return make_contracts(
        run_id="rpf51-" + "1" * 32, environment_id="env-rpf51-" + "1" * 32,
        execution_id="exec-" + "1" * 32, app="rpf51-app-test", env="rpf51-env-test",
        key="rpf51.value.test", port=43127,
        runproof_parent_commit=parent,
        runtime_source_sha256=_GOOD, config_center_source_commit="b" * 40,
        config_center_manifest_sha256=_GOOD, config_center_jar_sha256=_GOOD,
        java_version="17.0.12", prepared_at_utc="2026-10-18T00:00:00Z")


def api(data, *, code=0, message="OK", trace="trace-rpf51"):
    return {"code": code, "message": message, "data": data, "traceId": trace}


def item(effect, version, value, when):
    return {"app": effect["app"], "env": effect["env"], "key": effect["key"],
            "value": value, "description": None, "version": version, "updatedAt": when}


def history_row(effect, version, value, when):
    return {"app": effect["app"], "env": effect["env"], "key": effect["key"],
            "value": value, "description": None, "version": version, "action": "UPSERT",
            "operator": None, "reason": None, "createdAt": when}


def observations_for(contracts: FrozenContracts) -> list[dict]:
    effect = contracts.effect
    v1 = item(effect, 1, effect["initial_value"], "2026-10-18T00:00:01Z")
    v2 = item(effect, 2, effect["required_value"], "2026-10-18T00:00:02Z")
    mapping = {
        "initial_current": (404, api(None, code=4041, message="Not found"), None),
        "initial_history": (200, api([]), None),
        "unauthorized_write": (403, api(None, code=4031, message="Forbidden"), None),
        "after_unauthorized_current": (404, api(None, code=4041, message="Not found"), None),
        "after_unauthorized_history": (200, api([]), None),
        "create_v1": (200, api(v1), None),
        "update_v2": (200, api(v2), None),
        "stale_update": (409, api(None, code=4091, message="Conflict"), None),
        "final_current": (200, api(v2), None),
        "final_history": (200, api([history_row(effect, 2, effect["required_value"],
                                                   "2026-10-18T00:00:02Z"),
                                     history_row(effect, 1, effect["initial_value"],
                                                   "2026-10-18T00:00:01Z")]), None),
        "final_list": (200, api([v2]), 'W/"rpf51-etag"'),
    }
    result = []
    for seq, kind in enumerate(OBSERVATION_KINDS, start=1):
        method, path = _expected_path(kind, effect)
        status, response, etag = mapping[kind]
        result.append({"seq": seq, "kind": kind, "method": method, "path": path,
                       "request": _expected_request(kind, effect), "status": status,
                       "content_type": "application/json", "etag": etag,
                       "trace_id": response["traceId"] if type(response) is dict else None,
                       "response": response, "response_body_sha256": digest(response),
                       "elapsed_ms": 2, "transport_error": None})
    return result


def run_record(contracts: FrozenContracts, observations: list[dict]) -> dict:
    return {"process_id": 12345,
            "process_command": ["java", "-Djava.io.tmpdir=<task-owned-tmp>", "-jar",
                                "<task-owned>/config-center-server-1.0.0.jar",
                                "--spring.profiles.active=local", "--server.address=127.0.0.1",
                                f"--server.port={contracts.experiment['port']}",
                                "--security.api-keys[0].key=<environment-placeholder>",
                                "--security.api-keys[0].app=<synthetic>",
                                "--security.api-keys[0].env=<synthetic>"],
            "process_started_at_utc": "2026-10-18T00:00:01Z",
            "process_stopped_at_utc": "2026-10-18T00:00:02Z", "java_version": "17.0.12",
            "spring_profile": "local", "bind_address": "127.0.0.1",
            "port": contracts.experiment["port"], "persistence": "in-memory-h2",
            "working_copy": "task-owned-copy",
            "config_center_source_commit": contracts.experiment["config_center_source_commit"],
            "config_center_jar_sha256": contracts.experiment["config_center_jar_sha256"],
            "readiness": "TCP_LOOPBACK_LISTENER_OWNED_PID", "shutdown": "OWNED_PID_EXITED",
            "process_exit_code": 0, "port_closed": True, "external_connections": [],
            "http_request_count": len(observations), "step_count": 14,
            "elapsed_seconds": 1.25, "provider_requests": 0, "tokens": 0, "cost_cny": 0,
            "target_agent_executed": False}


class ConfigHttpContractsAndOracleTests(unittest.TestCase):
    def setUp(self):
        self.contracts = make_contract_bundle()

    def test_contract_freeze_rejects_remote_host_and_expanded_allowlist(self):
        document = self.contracts.document()
        document["execution"]["http"]["host"] = "example.com"
        with self.assertRaises(ContractRejected):
            FrozenContracts.from_document(document)
        document = self.contracts.document()
        document["execution"]["http"]["write_allowlist"].append("POST /admin")
        with self.assertRaises(ContractRejected):
            FrozenContracts.from_document(document)

    def test_rev1_rev2_rev3_and_rev4_exact_runproof_parents_are_supported(self):
        self.assertEqual(make_contract_bundle(_REV1_PARENT).experiment["runproof_parent_commit"],
                         _REV1_PARENT)
        self.assertEqual(make_contract_bundle(_REV2_PARENT).experiment["runproof_parent_commit"],
                         _REV2_PARENT)
        self.assertEqual(make_contract_bundle(_REV3_PARENT).experiment["runproof_parent_commit"],
                         _REV3_PARENT)
        self.assertEqual(make_contract_bundle(_REV4_PARENT).experiment["runproof_parent_commit"],
                         _REV4_PARENT)
        with self.assertRaisesRegex(ContractRejected, "RUNPROOF_PARENT_MISMATCH"):
            make_contract_bundle("c" * 40)

    def test_rev4_probe_uses_separate_task_identity_and_environment_key_placeholder(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(_PROBE.TASK_ROOT, root / ".local" / "rpf-51-rev4")
        self.assertNotEqual(_PROBE.TASK_ROOT, root / ".local" / "rpf-51")
        self.assertEqual(_PROBE.RUNPROOF_PARENT, _REV4_PARENT)
        self.assertEqual(_PROBE.RUNPROOF_BRANCH, "codex/rpf-51-rev4-real-jdk-http-effect")
        self.assertEqual(_PROBE.STARTED_PATH.parent, _PROBE.SCENARIO_ROOT)
        self.assertEqual(_PROBE.WITNESS_PATH,
                         root / "spikes" / "rpf-51" / "rev-4" / "config-http-witness.json")
        self.assertEqual(_PROBE._diagnostic_paths(1)["root"],
                         root / ".local" / "rpf-51-rev4" / "diagnostics" / "attempt-01")
        self.assertEqual(_PROBE._diagnostic_paths(2)["root"],
                         root / ".local" / "rpf-51-rev4" / "diagnostics" / "attempt-02")

        secret = "unit-test-secret-that-must-not-appear"
        direct_java = "C:/Program Files/Java/jdk-17/bin/java.exe"
        argv = _PROBE._build_java_args(direct_java, Path("private-temp"), Path("private.jar"),
                                       43127, "rpf51-app-test", "rpf51-env-test")
        self.assertEqual(argv[0], direct_java)
        self.assertIn("--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}", argv)
        self.assertIn("--security.api-keys[0].app=rpf51-app-test", argv)
        self.assertIn("--security.api-keys[0].env=rpf51-env-test", argv)
        self.assertNotIn(secret, "\0".join(argv))
        rendered = "\0".join(_PROBE._redacted_process_command(43127))
        self.assertIn("--security.api-keys[0].key=<environment-placeholder>", rendered)
        self.assertNotIn(secret, rendered)

    def test_legacy_rev1_rev2_run_switches_cannot_reach_a_scenario(self):
        for legacy_args in (["--prepare"], ["--run"]):
            with self.subTest(args=legacy_args), self.assertRaises(SystemExit):
                _PROBE.main(legacy_args)

    def test_diagnostic_attempt_budget_and_second_attempt_repair_gate(self):
        with self.assertRaises(_PROBE.ProbeError):
            _PROBE._diagnostic_paths(3)
        first = {"status": "FAILED", "failure_category": "LISTENER_PID_MISMATCH",
                 "process_id": 31372, "process_stopped": True, "port_closed": True,
                 "external_connections": [], "business_http_request_count": 0,
                 "provider_requests": 0, "tokens": 0, "cost_cny": 0,
                 "health_get_count": 1, "runproof_parent_commit": _REV4_PARENT,
                 "runtime_source_sha256": "a" * 64}
        with self.assertRaises(_PROBE.ProbeError):
            _PROBE._validate_second_diagnostic(first, "a" * 64)
        _PROBE._validate_second_diagnostic(first, "b" * 64)
        unsafe = {**first, "external_connections": ["NON_LOOPBACK_CONNECTION"]}
        with self.assertRaises(_PROBE.ProbeError):
            _PROBE._validate_second_diagnostic(unsafe, "b" * 64)

    def test_oracle_requires_independent_readback_and_exact_two_row_history(self):
        observations = observations_for(self.contracts)
        result = evaluate_config_effect(self.contracts.effect, observations)
        self.assertEqual(result["contract_outcome"], "CONTRACT_SATISFIED_IN_RUN")
        self.assertEqual(result["facts"]["final_current"], {"value": "rpf51-v2", "version": 2})
        self.assertEqual(result["facts"]["history_versions"], [2, 1])
        self.assertTrue(result["facts"]["stale_write_rejected"])

    def test_oracle_does_not_accept_success_post_without_matching_state(self):
        observations = observations_for(self.contracts)
        observations[8]["response"] = api(item(self.contracts.effect, 2, "rpf51-wrong",
                                                  "2026-10-18T00:00:03Z"))
        observations[8]["response_body_sha256"] = digest(observations[8]["response"])
        result = evaluate_config_effect(self.contracts.effect, observations)
        self.assertEqual(result["contract_outcome"], "VIOLATION_CONFIRMED")
        self.assertIn("FINAL_CURRENT_STATE_MISMATCH", result["violated_rules"])

    def test_oracle_detects_stale_write_acceptance_and_rehashed_v3_history(self):
        observations = observations_for(self.contracts)
        effect = self.contracts.effect
        v3 = item(effect, 3, effect["stale_value"], "2026-10-18T00:00:03Z")
        observations[7]["status"] = 200
        observations[7]["response"] = api(v3)
        observations[7]["response_body_sha256"] = digest(observations[7]["response"])
        observations[8]["response"] = api(v3)
        observations[8]["response_body_sha256"] = digest(observations[8]["response"])
        observations[9]["response"] = api([
            history_row(effect, 3, effect["stale_value"], "2026-10-18T00:00:03Z"),
            history_row(effect, 2, effect["required_value"], "2026-10-18T00:00:02Z"),
            history_row(effect, 1, effect["initial_value"], "2026-10-18T00:00:01Z")])
        observations[9]["response_body_sha256"] = digest(observations[9]["response"])
        observations[10]["response"] = api([v3])
        observations[10]["response_body_sha256"] = digest(observations[10]["response"])
        result = evaluate_config_effect(effect, observations)
        self.assertEqual(result["contract_outcome"], "VIOLATION_CONFIRMED")
        self.assertIn("STALE_WRITE_NOT_REJECTED", result["violated_rules"])
        self.assertIn("FINAL_HISTORY_MISMATCH", result["violated_rules"])

    def test_incomplete_history_is_inconclusive_and_existing_initial_value_is_not_a_bug(self):
        observations = observations_for(self.contracts)
        observations = observations[:9]
        result = evaluate_config_effect(self.contracts.effect, observations)
        self.assertEqual(result["contract_outcome"], "INCONCLUSIVE")
        self.assertIn("OBSERVATION_MISSING_FINAL_HISTORY", result["evidence_gaps"])

        observations = observations_for(self.contracts)
        observations[0]["status"] = 200
        observations[0]["response"] = api(item(self.contracts.effect, 4, "preexisting",
                                                  "2026-10-18T00:00:00Z"))
        observations[0]["response_body_sha256"] = digest(observations[0]["response"])
        result = evaluate_config_effect(self.contracts.effect, observations)
        self.assertEqual(result["contract_outcome"], "INCONCLUSIVE")
        self.assertIn("INITIAL_NAMESPACE_NOT_EMPTY", result["evidence_gaps"])

    def test_oracle_rejects_unauthorized_success_even_if_post_body_looks_valid(self):
        observations = observations_for(self.contracts)
        observations[2]["status"] = 200
        observations[2]["response"] = api(item(self.contracts.effect, 1,
                                                 self.contracts.effect["unauthorized_value"],
                                                 "2026-10-18T00:00:01Z"))
        observations[2]["response_body_sha256"] = digest(observations[2]["response"])
        result = evaluate_config_effect(self.contracts.effect, observations)
        self.assertEqual(result["contract_outcome"], "VIOLATION_CONFIRMED")
        self.assertIn("UNAUTHORIZED_WRITE_ACCEPTED", result["violated_rules"])


class ConfigHttpReadinessTests(unittest.TestCase):
    def test_java_details_resolve_launcher_home_and_direct_jdk_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            java_home = Path(folder) / "jdk-17"
            java = java_home / "bin" / ("java.exe" if _PROBE.os.name == "nt" else "java")
            java.parent.mkdir(parents=True)
            java.touch()
            settings = subprocess.CompletedProcess(
                args=["java"], returncode=0,
                stdout=f"    java.home = {java_home}\nopenjdk version \"17.0.12\"\n")
            direct_version = subprocess.CompletedProcess(
                args=[str(java)], returncode=0, stdout='openjdk version "17.0.12"\n')
            with patch.object(_PROBE.shutil, "which", return_value="java-wrapper"), \
                    patch.object(_PROBE.subprocess, "run",
                                 side_effect=[settings, direct_version]) as run:
                details = _PROBE._java_details()
        self.assertEqual(details["direct_jdk_executable"], str(java))
        self.assertEqual(details["java_home"], str(java_home.resolve()))
        self.assertEqual(details["version"], "17.0.12")
        self.assertEqual(details["launcher_path"], str(Path("java-wrapper").absolute()))
        launcher_path = str(Path("java-wrapper").absolute())
        self.assertEqual(run.call_args_list[0].args[0],
                         [launcher_path, "-XshowSettings:properties", "-version"])
        self.assertEqual(run.call_args_list[1].args[0], [str(java), "-version"])

    def test_netstat_fixture_parser_and_listener_identity_are_fail_closed(self):
        standard = """Active Connections
  Proto  Local Address          Foreign Address        State           PID
  TCP    127.0.0.1:7654          0.0.0.0:0              LISTENING       31372
"""
        rows, malformed = _PROBE.parse_netstat_output(standard)
        self.assertEqual(malformed, 0)
        self.assertEqual(_PROBE._listener_status(rows, malformed, 31372, 7654),
                         (True, "OWNED_LOOPBACK_LISTENER"))
        self.assertEqual(_PROBE._listener_status(rows, malformed, 7, 7654)[1],
                         "LISTENER_PID_MISMATCH")

        wildcard, malformed = _PROBE.parse_netstat_output(
            "TCP 0.0.0.0:7654 0.0.0.0:0 LISTENING 31372")
        self.assertEqual(_PROBE._listener_status(wildcard, malformed, 31372, 7654)[1],
                         "LISTENER_NOT_EXACT_LOOPBACK")
        ipv6, malformed = _PROBE.parse_netstat_output(
            "TCP [::1]:7654 [::]:0 LISTENING 31372")
        self.assertEqual(_PROBE._listener_status(ipv6, malformed, 31372, 7654)[1],
                         "LISTENER_NOT_EXACT_LOOPBACK")
        localized, malformed = _PROBE.parse_netstat_output(
            "TCP 127.0.0.1:7654 0.0.0.0:0 ABHOEREN 31372")
        self.assertFalse(_PROBE._listener_status(localized, malformed, 31372, 7654)[0])
        duplicate, malformed = _PROBE.parse_netstat_output(
            "TCP 127.0.0.1:7654 0.0.0.0:0 LISTENING 31372\n"
            "TCP 127.0.0.1:7654 0.0.0.0:0 LISTENING 31373")
        self.assertEqual(_PROBE._listener_status(duplicate, malformed, 31372, 7654)[1],
                         "MULTIPLE_PORT_LISTENERS")
        incomplete, malformed = _PROBE.parse_netstat_output("TCP 127.0.0.1:7654")
        self.assertEqual(malformed, 1)
        self.assertEqual(_PROBE._listener_status(incomplete, malformed, 31372, 7654)[1],
                         "NETSTAT_OUTPUT_INCOMPLETE")

    def test_tcp_success_with_unowned_pid_sleeps_and_never_calls_health(self):
        class Process:
            pid = 31372

            @staticmethod
            def poll():
                return None

        clock = [0.0]
        sleeps = []

        def monotonic():
            clock[0] += 0.01
            return clock[0]

        def sleep(delay):
            sleeps.append(delay)
            clock[0] += delay

        rows = ([{"protocol": "TCP", "local": "127.0.0.1:7654",
                  "remote": "0.0.0.0:0", "state": "LISTENING", "pid": 99}], 0)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(_PROBE, "_tcp_connect", return_value=True), \
                patch.object(_PROBE, "_netstat_rows", return_value=rows), \
                patch.object(_PROBE, "_health_get") as health, \
                patch.object(_PROBE.time, "monotonic", side_effect=monotonic), \
                patch.object(_PROBE.time, "sleep", side_effect=sleep):
            result = _PROBE._readiness(Process(), 7654,
                                       log_path=Path(folder) / "readiness.jsonl",
                                       timeout_seconds=1, max_health_gets=1)
        self.assertFalse(result["ready"])
        self.assertEqual(result["failure_category"], "LISTENER_PID_MISMATCH")
        self.assertGreater(len(sleeps), 0)
        self.assertFalse(health.called)

    def test_readiness_requires_owned_pid_and_real_health_up(self):
        class Process:
            pid = 31372

            @staticmethod
            def poll():
                return None

        rows = ([{"protocol": "TCP", "local": "127.0.0.1:7654",
                  "remote": "0.0.0.0:0", "state": "LISTENING", "pid": 31372}], 0)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(_PROBE, "_tcp_connect", return_value=True), \
                patch.object(_PROBE, "_netstat_rows", side_effect=[rows, rows]), \
                patch.object(_PROBE, "_health_get", return_value=(200, True, "HEALTH_UP")) as health:
            result = _PROBE._readiness(Process(), 7654,
                                       log_path=Path(folder) / "readiness.jsonl",
                                       timeout_seconds=1, max_health_gets=1)
        self.assertTrue(result["ready"])
        self.assertEqual(result["health_get_count"], 1)
        self.assertEqual(result["last_samples"][-1]["http_status"], 200)
        self.assertTrue(result["last_samples"][-1]["pid_match"])
        self.assertEqual(result["last_samples"][-1]["listener_pid"], 31372)
        self.assertEqual(result["last_samples"][-1]["listener_pid_after"], 31372)
        self.assertEqual(health.call_count, 1)

    def test_readiness_rejects_process_exit_and_non_up_health(self):
        class Exited:
            pid = 31372

            @staticmethod
            def poll():
                return 1

        with tempfile.TemporaryDirectory() as folder, \
                patch.object(_PROBE, "_tcp_connect", return_value=False), \
                patch.object(_PROBE, "_netstat_rows", return_value=([], 0)):
            exited = _PROBE._readiness(Exited(), 7654,
                                       log_path=Path(folder) / "exited.jsonl",
                                       timeout_seconds=1, max_health_gets=1)
        self.assertFalse(exited["ready"])
        self.assertEqual(exited["failure_category"], "PROCESS_EXITED")

        class Running:
            pid = 31372

            @staticmethod
            def poll():
                return None

        rows = ([{"protocol": "TCP", "local": "127.0.0.1:7654",
                  "remote": "0.0.0.0:0", "state": "LISTENING", "pid": 31372}], 0)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(_PROBE, "_tcp_connect", return_value=True), \
                patch.object(_PROBE, "_netstat_rows", return_value=rows), \
                patch.object(_PROBE, "_health_get", return_value=(200, False, "HEALTH_STATUS_NOT_UP")) as health:
            failed = _PROBE._readiness(Running(), 7654,
                                       log_path=Path(folder) / "health.jsonl",
                                       timeout_seconds=1, max_health_gets=1)
        self.assertFalse(failed["ready"])
        self.assertEqual(failed["failure_category"], "HEALTH_GET_BUDGET_EXHAUSTED")
        self.assertEqual(failed["health_get_count"], 1)
        self.assertEqual(health.call_count, 1)

    def test_readiness_rechecks_listener_identity_after_health_get(self):
        class Process:
            pid = 31372

            @staticmethod
            def poll():
                return None

        owned = ([{"protocol": "TCP", "local": "127.0.0.1:7654",
                   "remote": "0.0.0.0:0", "state": "LISTENING", "pid": 31372}], 0)
        replaced = ([{"protocol": "TCP", "local": "127.0.0.1:7654",
                      "remote": "0.0.0.0:0", "state": "LISTENING", "pid": 88}], 0)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(_PROBE, "_tcp_connect", return_value=True), \
                patch.object(_PROBE, "_netstat_rows", side_effect=[owned, replaced]), \
                patch.object(_PROBE, "_health_get", return_value=(200, True, "HEALTH_UP")):
            result = _PROBE._readiness(Process(), 7654,
                                       log_path=Path(folder) / "identity-change.jsonl",
                                       timeout_seconds=1, max_health_gets=1)
        self.assertFalse(result["ready"])
        self.assertEqual(result["failure_category"], "OWNED_SERVICE_IDENTITY_CHANGED")

    def test_health_get_uses_only_health_path_and_requires_up_body(self):
        instances = []
        bodies = [b'{"status":"UP"}', b'{"status":"DOWN"}']

        class Response:
            status = 200

            def __init__(self, body):
                self.body = body

            def read(self, limit):
                return self.body

        class Connection:
            def __init__(self, host, port, timeout):
                self.request_args = None
                self.body = bodies.pop(0)
                instances.append(self)

            def request(self, method, path, headers):
                self.request_args = (method, path, headers)

            def getresponse(self):
                return Response(self.body)

            def close(self):
                return None

        with patch("http.client.HTTPConnection", Connection):
            self.assertEqual(_PROBE._health_get(7654), (200, True, "HEALTH_UP"))
            self.assertEqual(instances[-1].request_args[:2], ("GET", "/actuator/health"))
            self.assertNotIn("X-API-Key", instances[-1].request_args[2])
            self.assertEqual(_PROBE._health_get(7654), (200, False, "HEALTH_STATUS_NOT_UP"))

    def test_external_audit_allows_only_owned_loopback_listener_and_local_peers(self):
        owned = ([{"protocol": "TCP", "local": "127.0.0.1:7654",
                   "remote": "0.0.0.0:0", "state": "LISTENING", "pid": 31372}], 0)
        with patch.object(_PROBE, "_netstat_rows", return_value=owned):
            self.assertEqual(_PROBE._external_connections(31372, 7654), [])

        wildcard = ([{"protocol": "TCP", "local": "0.0.0.0:7654",
                      "remote": "0.0.0.0:0", "state": "LISTENING", "pid": 31372}], 0)
        with patch.object(_PROBE, "_netstat_rows", return_value=wildcard):
            self.assertEqual(_PROBE._external_connections(31372, 7654),
                             ["NON_LOOPBACK_OR_UNEXPECTED_LISTENER"])

        external = ([{"protocol": "TCP", "local": "127.0.0.1:43000",
                      "remote": "203.0.113.10:443", "state": "ESTABLISHED", "pid": 31372}], 0)
        with patch.object(_PROBE, "_netstat_rows", return_value=external):
            self.assertEqual(_PROBE._external_connections(31372, 7654),
                             ["NON_LOOPBACK_CONNECTION"])

    def test_cleanup_terminates_and_waits_on_the_exact_owned_process_handle(self):
        class Process:
            pid = 31372

            def __init__(self):
                self.returncode = None
                self.terminate_calls = 0
                self.wait_calls = 0
                self.kill_calls = 0

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminate_calls += 1
                self.returncode = 0

            def wait(self, timeout):
                self.wait_calls += 1
                return self.returncode

            def kill(self):
                self.kill_calls += 1
                self.returncode = -9

        process = Process()
        self.assertTrue(_PROBE._stop_owned_process(process))
        self.assertEqual(process.terminate_calls, 1)
        self.assertEqual(process.wait_calls, 1)
        self.assertEqual(process.kill_calls, 0)


class ConfigHttpAdapterTests(unittest.TestCase):
    def setUp(self):
        self.contracts = make_contract_bundle()

    def test_reader_and_tool_host_cannot_change_target_or_method(self):
        observations = []
        reader = ConfigAuthorityReader(self.contracts, observations)
        host = ConfigToolHost(self.contracts, "X" * 32, observations)
        self.assertFalse(hasattr(reader, "upsert"))
        self.assertFalse(hasattr(host, "get_one"))
        with self.assertRaises(AdapterRejected):
            reader._client.request("final_current", "GET", "http://example.com/api/configs")
        with self.assertRaises(AdapterRejected):
            reader._client.request("final_current", "GET", "/api/configs?app=bad&env=bad")
        with self.assertRaises(AdapterRejected):
            host.upsert(kind="create_v1", value="arbitrary-value")
        with self.assertRaises(AdapterRejected):
            host.upsert(kind="create_v1", value="rpf51-v1", credential_override="wrong" * 8)

    def test_redirect_is_recorded_and_never_followed(self):
        contracts = self.contracts
        observations = []
        reader = ConfigAuthorityReader(contracts, observations)
        created = []

        class Response:
            status = 302

            def getheader(self, name):
                return "text/plain" if name == "Content-Type" else None

            def read(self, limit):
                return b"redirect"

        class Connection:
            def __init__(self, *args, **kwargs):
                created.append(self)

            def request(self, *args, **kwargs):
                return None

            def getresponse(self):
                return Response()

            def close(self):
                return None

        with patch("runtime.runproof_runtime.effectwitness.config_http_adapter.http.client.HTTPConnection",
                   Connection):
            result = reader.list_configs()
        self.assertEqual(result["transport_error"], "REDIRECT_FORBIDDEN")
        self.assertEqual(len(created), 1)
        self.assertIsNone(result["response"])

    def test_timeout_records_unknown_without_retry(self):
        contracts = self.contracts
        observations = []
        reader = ConfigAuthorityReader(contracts, observations)
        created = []

        class Connection:
            def __init__(self, *args, **kwargs):
                created.append(self)

            def request(self, *args, **kwargs):
                raise TimeoutError()

            def close(self):
                return None

        with patch("runtime.runproof_runtime.effectwitness.config_http_adapter.http.client.HTTPConnection",
                   Connection):
            result = reader.get_one(kind="initial_current")
        self.assertEqual(result["transport_error"], "TIMEOUT")
        self.assertIsNone(result["status"])
        self.assertEqual(len(created), 1)
        self.assertEqual(len(observations), 1)


class ConfigHttpWitnessTests(unittest.TestCase):
    def setUp(self):
        self.contracts = make_contract_bundle()
        self.observations = observations_for(self.contracts)
        self.witness = build_witness(self.contracts, run_record(self.contracts, self.observations),
                                     self.observations)
        self.raw = canonical(self.witness)
        self.anchor = hashlib.sha256(self.raw).hexdigest()

    def test_anchored_unanchored_and_wrong_anchor_exit_semantics(self):
        self.assertEqual(verify_bytes(self.raw, self.anchor), "VERIFIED_ANCHORED")
        self.assertEqual(verify_bytes(self.raw), "UNANCHORED_INCONCLUSIVE")
        with self.assertRaisesRegex(WitnessRejected, "ANCHOR_MISMATCH"):
            verify_bytes(self.raw, "0" * 64)

    def test_duplicate_json_keys_and_issuer_overclaim_are_rejected(self):
        with self.assertRaises(WitnessRejected):
            verify_bytes(b'{"schema_version":"x","schema_version":"y"}')
        forged = copy.deepcopy(self.witness)
        forged["issuer"]["issuer_authenticity"] = "VERIFIED"
        forged = seal(forged)
        with self.assertRaisesRegex(WitnessRejected, "WITNESS_OR_ISSUER_IDENTITY"):
            verify_bytes(canonical(forged))

    def test_resealed_wrong_source_identity_is_rejected(self):
        forged = copy.deepcopy(self.witness)
        forged["source_identity"]["runproof_source_commit"] = _REV2_PARENT
        forged = seal(forged)
        with self.assertRaisesRegex(WitnessRejected, "SOURCE_IDENTITY_MISMATCH"):
            verify_bytes(canonical(forged))

    def test_rehashed_false_stale_success_still_fails_external_anchor(self):
        forged = copy.deepcopy(self.witness)
        effect = self.contracts.effect
        forged["observations"][7]["status"] = 200
        forged["observations"][7]["response"] = api(
            item(effect, 3, effect["stale_value"], "2026-10-18T00:00:03Z"))
        forged["observations"][7]["response_body_sha256"] = digest(forged["observations"][7]["response"])
        forged["effect_result"] = evaluate_config_effect(effect, forged["observations"])
        forged["claims"]["contract_outcome"] = forged["effect_result"]["contract_outcome"]
        forged = seal(forged)
        with self.assertRaisesRegex(WitnessRejected, "ANCHOR_MISMATCH"):
            verify_bytes(canonical(forged), self.anchor)

    def test_offline_verifier_survives_network_database_and_execution_import_block(self):
        script = r'''
import builtins, hashlib, sys
blocked = ("socket", "sqlite3", "http.client", "urllib.request", "requests",
           "pydantic_ai", "runtime.runproof_runtime.effectwitness.config_http_adapter")
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if any(name == item or name.startswith(item + ".") for item in blocked):
        raise RuntimeError("blocked import: " + name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from runtime.runproof_runtime.effectwitness.config_http_witness import verify_bytes
raw = sys.stdin.buffer.read()
print(verify_bytes(raw, hashlib.sha256(raw).hexdigest()))
'''
        result = subprocess.run([sys.executable, "-B", "-c", script], input=self.raw,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(result.stdout.decode().strip(), "VERIFIED_ANCHORED")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
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

    def test_rev1_and_rev2_exact_runproof_parents_are_supported(self):
        self.assertEqual(make_contract_bundle(_REV1_PARENT).experiment["runproof_parent_commit"],
                         _REV1_PARENT)
        self.assertEqual(make_contract_bundle(_REV2_PARENT).experiment["runproof_parent_commit"],
                         _REV2_PARENT)
        with self.assertRaisesRegex(ContractRejected, "RUNPROOF_PARENT_MISMATCH"):
            make_contract_bundle("c" * 40)

    def test_rev2_probe_uses_separate_task_identity_and_environment_key_placeholder(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(_PROBE.TASK_ROOT, root / ".local" / "rpf-51-rev2")
        self.assertNotEqual(_PROBE.TASK_ROOT, root / ".local" / "rpf-51")
        self.assertEqual(_PROBE.RUNPROOF_PARENT, _REV2_PARENT)
        self.assertEqual(_PROBE.RUNPROOF_BRANCH, "codex/rpf-51-rev2-http-effect-recovery")
        self.assertEqual(_PROBE.STARTED_PATH.parent, _PROBE.TASK_ROOT)
        self.assertEqual(_PROBE.WITNESS_PATH,
                         root / "spikes" / "rpf-51" / "rev-2" / "config-http-witness.json")

        secret = "unit-test-secret-that-must-not-appear"
        argv = _PROBE._build_java_args("java", Path("private-temp"), Path("private.jar"),
                                       43127, "rpf51-app-test", "rpf51-env-test")
        self.assertIn("--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}", argv)
        self.assertIn("--security.api-keys[0].app=rpf51-app-test", argv)
        self.assertIn("--security.api-keys[0].env=rpf51-env-test", argv)
        self.assertNotIn(secret, "\0".join(argv))
        rendered = "\0".join(_PROBE._redacted_process_command(43127))
        self.assertIn("--security.api-keys[0].key=<environment-placeholder>", rendered)
        self.assertNotIn(secret, rendered)

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

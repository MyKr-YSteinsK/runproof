"""Pure-content RPF-52 evidence verifier; imports no SDK, network, or storage APIs."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .config_target_contracts import (
    CONTRACT_SCHEMA, SOURCE_LEVEL, canonical, digest, evaluate_config_target_effect,
    fixture_response, strict_json, validate_contracts,
)


class EvidenceRejected(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_SHA = re.compile(r"[0-9a-f]{64}\Z")
_OUTER_FIELDS = {"schema_version", "source_level", "payload", "payload_sha256"}
_PAYLOAD_FIELDS = {
    "schema_version", "run_id", "preflight_sha256", "scenario_duration_ms",
    "contracts", "runtime_source_identity",
    "runtime_identity", "java_process",
    "fixture_runtime", "http_observations", "tool_trace", "oracle", "claims",
    "security", "cleanup",
}


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise EvidenceRejected(code)


def _sha(value) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _sha_digest_for_tool(payload: dict, index: int) -> str:
    tools = payload.get("tool_trace")
    if type(tools) is not list or index >= len(tools) or type(tools[index]) is not dict:
        return ""
    return tools[index].get("tool_return_sha256", "")


def validate_evidence(value) -> dict:
    _require(type(value) is dict and set(value) == _OUTER_FIELDS, "EVIDENCE_FIELDS")
    _require(value["schema_version"] == CONTRACT_SCHEMA
             and value["source_level"] == SOURCE_LEVEL, "EVIDENCE_IDENTITY")
    payload = value["payload"]
    _require(type(payload) is dict and set(payload) == _PAYLOAD_FIELDS,
             "PAYLOAD_FIELDS")
    _require(payload["schema_version"] == CONTRACT_SCHEMA
             and value["payload_sha256"] == digest(payload), "PAYLOAD_DIGEST")
    contracts = payload["contracts"]
    try:
        validate_contracts(contracts)
    except Exception as exc:
        raise EvidenceRejected(getattr(exc, "code", "CONTRACT_INVALID")) from None
    experiment = contracts["experiment"]
    _require(payload["run_id"] == experiment["run_id"], "RUN_ID_BINDING")
    _require(_sha(payload["preflight_sha256"]), "PREFLIGHT_IDENTITY")
    duration_ms = payload["scenario_duration_ms"]
    _require(type(duration_ms) is int and 0 <= duration_ms
             <= contracts["execution"]["budgets"]["runtime_seconds"] * 1000,
             "SCENARIO_RUNTIME_BUDGET")
    source_identity = payload["runtime_source_identity"]
    source_files = {
        "runtime/runproof_runtime/effectwitness/config_target_contracts.py",
        "runtime/runproof_runtime/effectwitness/config_target_bridge.py",
        "runtime/runproof_runtime/effectwitness/config_target_external.py",
        "runtime/runproof_runtime/effectwitness/config_target_verify.py",
        "runtime/tests/test_effectwitness_config_target.py",
        "spikes/rpf-52/probe.py",
    }
    _require(type(source_identity) is dict and set(source_identity) == {"files", "sha256"}
             and type(source_identity["files"]) is dict
             and set(source_identity["files"]) == source_files
             and all(_sha(value) for value in source_identity["files"].values())
             and source_identity["sha256"] == digest(source_identity["files"])
             and source_identity["sha256"] == experiment["runtime_source_sha256"],
             "RUNTIME_SOURCE_IDENTITY")

    runtime = payload["runtime_identity"]
    _require(type(runtime) is dict and set(runtime) == {
        "python_version", "python_executable", "sdk_distributions",
        "sdk_source_sha256", "openai_source_sha256",
        "sdk_source_relative", "openai_source_relative",
        "distribution_origin", "readonly_distribution_ref_sha256",
    }, "RUNTIME_IDENTITY_FIELDS")
    _require(runtime["python_version"] == "3.12.13"
             and isinstance(runtime["python_executable"], str)
             and runtime["python_executable"].lower().endswith(
                 r".local\rpf-52\sdk-venv\scripts\python.exe")
             and runtime["distribution_origin"] == "rpf48-pinned-site-packages-read-only"
             and _sha(runtime["readonly_distribution_ref_sha256"])
             and runtime["readonly_distribution_ref_sha256"]
             == hashlib.sha256(b".local/rpf-48/venv/Lib/site-packages").hexdigest(),
             "PYTHON_IDENTITY")
    distributions = runtime["sdk_distributions"]
    _require(type(distributions) is dict and set(distributions) == {
        "pydantic-ai-slim", "openai"}, "SDK_DISTRIBUTIONS")
    for name, version in (("pydantic-ai-slim", "2.57.0"), ("openai", "3.35.1")):
        item = distributions[name]
        _require(type(item) is dict and item.get("version") == version
                 and _sha(item.get("metadata_sha256"))
                 and _sha(item.get("record_sha256"))
                 and type(item.get("record_files")) is int
                 and type(item.get("record_hashes_checked")) is int
                 and item["record_hashes_checked"] > 0
                 and item["record_hashes_checked"] <= item["record_files"]
                 and item.get("record_mismatches") == 0, "SDK_DISTRIBUTION_IDENTITY")
    sdk_identity = contracts["execution"]["sdk"]["identity"]
    _require(runtime == sdk_identity, "SDK_IDENTITY_CONTRACT_MISMATCH")
    _require(_sha(runtime["sdk_source_sha256"])
             and _sha(runtime["openai_source_sha256"])
             and runtime["sdk_source_relative"] == "pydantic_ai/agent/__init__.py"
             and runtime["openai_source_relative"].startswith("openai/")
             and runtime["sdk_source_sha256"] == sdk_identity["sdk_source_sha256"]
             and runtime["openai_source_sha256"] == sdk_identity["openai_source_sha256"],
             "SDK_SOURCE_BINDING")

    java = payload["java_process"]
    _require(type(java) is dict and set(java) == {
        "executable", "version", "pid", "listener_pid", "health_gets",
        "health_status", "health_body", "external_connections",
        "argv_redacted", "exit_code", "process_exited",
    }, "JAVA_PROCESS_FIELDS")
    placeholder = "key=" + "$" + "{CONFIG_CENTER_API_KEY}"
    _require(java["executable"] == "jdk-17/bin/java.exe"
             and java["version"] == experiment["java_version"]
             and type(java["pid"]) is int and java["pid"] > 0
             and java["listener_pid"] == java["pid"]
             and type(java["health_gets"]) is int
             and 1 <= java["health_gets"] <= 3
             and java["health_status"] == 200
             and type(java["health_body"]) is dict
             and java["health_body"].get("status") == "UP"
             and java["external_connections"] == []
             and type(java["exit_code"]) is int
             and type(java["argv_redacted"]) is list
             and any(placeholder in arg for arg in java["argv_redacted"])
             and type(java["process_exited"]) is bool and java["process_exited"],
             "JAVA_PROCESS_IDENTITY")

    fixture = payload["fixture_runtime"]
    _require(type(fixture) is dict and set(fixture) == {
        "mode", "completions", "sdk_ready", "sdk_child", "python_network_guard",
        "provider_https_attempts", "provider_requests", "tokens", "cost_cny",
    }, "FIXTURE_FIELDS")
    _require(fixture["mode"] == "FIXTURE_SCRIPTED"
             and type(fixture["completions"]) is list
             and len(fixture["completions"]) == 4
             and all(type(fixture[key]) is int for key in (
                 "provider_https_attempts", "provider_requests", "tokens", "cost_cny"))
             and fixture["provider_https_attempts"] == 0
             and fixture["provider_requests"] == 0
             and fixture["tokens"] == 0 and fixture["cost_cny"] == 0,
             "FIXTURE_BUDGET")
    sdk_child = fixture["sdk_child"]
    ready = fixture["sdk_ready"]
    _require(type(ready) is dict and set(ready) == {
        "framework", "version", "openai_version", "python_version",
        "pid", "sdk_source_sha256", "openai_source_sha256",
    } and ready["framework"] == "pydantic-ai-slim"
             and ready["version"] == "2.57.0" and ready["openai_version"] == "3.35.1"
             and ready["python_version"] == runtime["python_version"]
             and type(ready["pid"]) is int and ready["pid"] > 0
             and ready["pid"] == sdk_child.get("pid")
             and ready["sdk_source_sha256"] == runtime["sdk_source_sha256"]
             and ready["openai_source_sha256"] == runtime["openai_source_sha256"],
             "SDK_READY_IDENTITY")
    _require(type(sdk_child) is dict and set(sdk_child) == {
        "status", "framework", "version", "openai_version", "python_version",
        "pid", "exit_code", "requests", "input_tokens", "output_tokens",
        "tool_calls", "guard_denials", "sdk_source_sha256", "openai_source_sha256",
        "final_output_sha256", "final_text_persisted",
    }, "SDK_CHILD_FIELDS")
    _require(sdk_child["status"] == "COMPLETED"
             and sdk_child["framework"] == "pydantic-ai-slim"
             and sdk_child["version"] == "2.57.0"
             and sdk_child["openai_version"] == "3.35.1"
             and sdk_child["python_version"] == runtime["python_version"]
             and type(sdk_child["pid"]) is int and sdk_child["pid"] > 0
             and all(type(sdk_child[key]) is int for key in (
                 "exit_code", "requests", "input_tokens", "output_tokens", "tool_calls"))
             and sdk_child["exit_code"] == 0 and sdk_child["requests"] == 4
             and sdk_child["input_tokens"] == 0 and sdk_child["output_tokens"] == 0
             and sdk_child["tool_calls"] == 3
             and sdk_child["guard_denials"] == []
             and sdk_child["sdk_source_sha256"] == runtime["sdk_source_sha256"]
             and sdk_child["openai_source_sha256"] == runtime["openai_source_sha256"]
             and _sha(sdk_child["final_output_sha256"])
             and sdk_child["final_text_persisted"] is False,
             "SDK_CHILD_EXECUTION")
    network_guard = fixture["python_network_guard"]
    _require(type(network_guard) is dict and set(network_guard) == {
        "allowed_destination", "external_connections", "parent_process_connections",
        "host_client_addresses", "denied_attempts", "is_os_sandbox",
    } and network_guard.get("allowed_destination")
             == "127.0.0.1:" + str(experiment["agent_host_port"])
             and network_guard.get("external_connections") == []
             and network_guard.get("parent_process_connections") == []
             and network_guard.get("host_client_addresses") == ["127.0.0.1"]
             and network_guard.get("denied_attempts") == []
             and network_guard.get("is_os_sandbox") is False,
             "SDK_NETWORK_BOUNDARY")
    completions = fixture["completions"]
    calls = contracts["execution"]["tool_calls"]
    for index, item in enumerate(completions):
        _require(type(item) is dict and set(item) == {
            "seq", "request_sha256", "tool_schema_sha256", "assistant_calls_seen",
            "tool_returns_seen", "last_tool_return", "response_sha256", "finish_reason",
        }, "FIXTURE_COMPLETION_FIELDS")
        expected_reason = "tool_calls" if index < 3 else "stop"
        _require(type(item["seq"]) is int and item["seq"] == index + 1
                 and type(item["assistant_calls_seen"]) is int
                 and type(item["tool_returns_seen"]) is int
                 and _sha(item["request_sha256"])
                 and _sha(item["tool_schema_sha256"])
                 and item["assistant_calls_seen"] == index
                 and item["tool_returns_seen"] == index
                 and item["finish_reason"] == expected_reason
                 and item["response_sha256"] == digest(fixture_response(contracts, index))
                 and _sha(item["response_sha256"]), "FIXTURE_COMPLETION_SEQUENCE")
        if index:
            _require(item["last_tool_return"] == {
                "call_id": calls[index - 1]["call_id"],
                "result_sha256": _sha_digest_for_tool(payload, index - 1),
            }, "FIXTURE_RETURN_ACK")
        else:
            _require(item["last_tool_return"] is None, "FIRST_FIXTURE_RETURN")
    _require(len({item["tool_schema_sha256"] for item in completions}) == 1,
             "FIXTURE_TOOL_SCHEMA_CHANGED")

    observations = payload["http_observations"]
    tools = payload["tool_trace"]
    expected_ids = [item["call_id"] for item in calls]
    _require(type(tools) is list and len(tools) == 3
             and [item.get("call_id") for item in tools if type(item) is dict] == expected_ids,
             "TOOL_CALL_ID_LINEAGE")
    for index, item in enumerate(tools):
        call = calls[index]
        expected_fields = {
            "seq", "call_id", "name", "arguments", "arguments_sha256",
            "completion_round", "http_seq", "http_response_sha256",
            "tool_return_sha256", "tool_return", "accepted",
        }
        expected_return = {
            "http_status": observations[index + 2]["status"],
            "response": observations[index + 2]["response"],
        }
        _require(type(item) is dict and set(item) == expected_fields
                 and type(item["seq"]) is int and item["seq"] == index + 1
                 and item["call_id"] == call["call_id"]
                 and item["name"] == call["name"]
                 and item["arguments"] == call["arguments"]
                 and item["arguments_sha256"] == digest(call["arguments"])
                 and type(item["completion_round"]) is int
                 and item["completion_round"] == index + 1
                 and type(item["http_seq"]) is int and item["http_seq"] == index + 3
                 and item["accepted"] is True
                 and item["tool_return"] == expected_return
                 and item["tool_return_sha256"] == digest(item["tool_return"])
                 and item["http_response_sha256"] == observations[index + 2]["response_body_sha256"],
                 "TOOL_RETURN_CONTENT")
    oracle = evaluate_config_target_effect(contracts["effect"], observations, tools)
    _require(payload["oracle"] == oracle, "ORACLE_RECOMPUTE")
    _require(oracle["outcome"] == "CONTRACT_SATISFIED_IN_RUN"
             and oracle["violations"] == [] and oracle["gaps"] == [],
             "BUSINESS_EFFECT_NOT_SATISFIED")
    _require(type(payload["claims"]) is dict and payload["claims"] == {
        "agent_framework_runtime": "EXECUTED",
        "llm_autonomous_decision": "NOT_PROVEN",
        "target_effect": "CONTRACT_SATISFIED_IN_RUN",
        "issuer_authenticity": "NOT_ESTABLISHED",
        "database_independent_authority": "NOT_ESTABLISHED",
        "reproduction": "NOT_TESTED",
        "workswarm": "NOT_PROVEN",
    }, "TRUST_CLAIMS")
    security = payload["security"]
    _require(type(security) is dict and security == {
        "business_api_key_in_sdk_child": False,
        "business_api_key_in_argv": False,
        "business_api_key_in_evidence": False,
        "java_log_key_matches": 0,
        "evidence_secret_scan_matches": 0,
        "provider_https_requests": 0,
    }, "SECRET_OR_NETWORK_BOUNDARY")
    cleanup = payload["cleanup"]
    _require(type(cleanup) is dict and cleanup == {
        "java_process_exited": True, "java_port_closed": True,
        "agent_host_closed": True, "sdk_child_exited": True,
        "sdk_child_external_connections": [],
        "parent_process_external_connections": [],
    }, "RESOURCE_CLEANUP")
    _require(java["process_exited"] and cleanup["java_process_exited"],
             "PROCESS_LIFECYCLE")
    return {"status": "VERIFIED_CONTENT", "run_id": payload["run_id"],
            "source_level": value["source_level"], "oracle": oracle}


def verify_bytes(raw: bytes, expected_sha256: str | None = None) -> str:
    try:
        value = strict_json(raw)
        validate_evidence(value)
    except EvidenceRejected:
        raise
    except Exception:
        raise EvidenceRejected("EVIDENCE_INVALID") from None
    if expected_sha256 is None:
        return "UNANCHORED_NOT_PROVEN"
    _require(_sha(expected_sha256), "ANCHOR_FORMAT")
    actual = hashlib.sha256(raw).hexdigest()
    _require(actual == expected_sha256, "ANCHOR_MISMATCH")
    return "VERIFIED_ANCHORED"


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    try:
        result = verify_bytes(args.evidence.read_bytes(), args.expected_sha256)
        print(json.dumps({"status": result}, sort_keys=True, separators=(",", ":")))
        return 2 if result == "UNANCHORED_NOT_PROVEN" else 0
    except (EvidenceRejected, OSError) as exc:
        code = exc.code if isinstance(exc, EvidenceRejected) else "EVIDENCE_READ_FAILED"
        print(json.dumps({"status": "REJECTED", "code": code},
                         sort_keys=True, separators=(",", ":")))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

"""RPF-52 frozen contracts and deterministic config-target effect oracle."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

CONTRACT_SCHEMA = "rpf-config-target-sdk-fixture-v1"
EXECUTION_SCHEMA = "rpf-config-target-execution-v1"
EFFECT_SCHEMA = "rpf-config-target-effect-v1"
EXPERIMENT_SCHEMA = "rpf-config-target-experiment-v1"
SOURCE_LEVEL = "SDK_FIXTURE_EXTERNAL_HTTP_EFFECT_OBSERVED"
PARENT_SHA = "151922a9b891ce9aa6f2d62639109e435f98c8ab"
SOURCE_COMMIT = "0258b9cef02ea74a40989d035c79256c776409c0"
MANIFEST_SHA = "33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343"
JAR_SHA = "906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70"
TOOLS = ("inspect_config", "create_config_v1", "update_config_v2")
HTTP_ORDER = ("initial_current", "initial_history", "inspect_config",
              "create_config_v1", "update_config_v2",
              "final_current", "final_history", "final_list")
BUDGETS = {
    "business_http_requests": 8, "health_gets": 3,
    "fixture_completions": 5, "tool_calls": 3,
    "runtime_seconds": 1200, "request_seconds": 5,
    "provider_https_requests": 0, "provider_requests": 0,
    "tokens": 0, "cost_cny": 0,
}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")
_OBS_FIELDS = {"seq", "kind", "method", "path", "request", "status",
               "content_type", "response", "response_body_sha256",
               "elapsed_ms", "transport_error"}


class ContractRejected(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractRejected(code)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def strict_json(raw: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, item in items:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = item
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: require(False, "NONFINITE_JSON"))
    except ContractRejected:
        raise
    except (UnicodeError, ValueError, TypeError):
        raise ContractRejected("INVALID_JSON") from None


def _utc(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def expected_path(effect: dict, kind: str) -> tuple[str, str]:
    app, env, key = (quote(effect[name], safe="") for name in ("app", "env", "key"))
    if kind in ("initial_current", "inspect_config", "final_current"):
        return "GET", f"/api/configs/{key}?app={app}&env={env}"
    if kind in ("initial_history", "final_history"):
        return "GET", f"/api/configs/history?app={app}&env={env}&key={key}&limit=50"
    if kind == "final_list":
        return "GET", f"/api/configs?app={app}&env={env}"
    return "POST", "/api/configs"


def expected_request(effect: dict, kind: str):
    base = {name: effect[name] for name in ("app", "env", "key")}
    if kind == "create_config_v1":
        return {**base, "value": effect["initial_value"]}
    if kind == "update_config_v2":
        return {**base, "value": effect["required_value"],
                "expectedVersion": effect["initial_version"]}
    return None


def fixture_response(contracts: dict, index: int) -> dict:
    """Return the one permitted OpenAI-compatible completion at zero-based index."""
    run_id = contracts["experiment"]["run_id"]
    calls = contracts["execution"]["tool_calls"]
    require(type(index) is int and 0 <= index <= 3, "FIXTURE_INDEX")
    if index < 3:
        call = calls[index]
        message = {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": call["call_id"], "type": "function",
                            "function": {"name": call["name"],
                                         "arguments": canonical(call["arguments"]).decode("utf-8")}}],
        }
        finish_reason = "tool_calls"
    else:
        message = {"role": "assistant", "content": "rpf52-fixture-complete", "tool_calls": []}
        finish_reason = "stop"
    return {
        "id": f"chatcmpl-{run_id}-{index + 1}",
        "object": "chat.completion", "created": 0, "model": "rpf52-fixture",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _call_definitions(run_id: str) -> list[dict]:
    return [
        {"name": "inspect_config", "call_id": run_id + "-inspect-01", "arguments": {}},
        {"name": "create_config_v1", "call_id": run_id + "-create-02",
         "arguments": {"value": "rpf52-v1"}},
        {"name": "update_config_v2", "call_id": run_id + "-update-03",
         "arguments": {"expected_version": 1, "value": "rpf52-v2"}},
    ]


def make_contracts(*, run_id: str, source_identity_sha256: str,
                   sdk_identity: dict, java_version: str, java_port: int,
                   agent_host_port: int, prepared_at_utc: str) -> dict:
    suffix = run_id.removeprefix("rpf52-")
    execution = {
        "schema_version": EXECUTION_SCHEMA,
        "execution_id": "rpf52-exec-" + suffix,
        "driver": "pydantic-ai-openai-compatible-fixture-v1",
        "model_completions": "FIXTURE_SCRIPTED",
        "tool_calls": _call_definitions(run_id),
        "budgets": dict(BUDGETS),
        "service": {"scheme": "http", "host": "127.0.0.1", "port": java_port,
                    "profile": "local", "persistence": "in-memory-h2",
                    "redirects": "FORBIDDEN", "external_connections": "FORBIDDEN"},
        "agent_host": {"scheme": "http", "host": "127.0.0.1",
                       "port": agent_host_port, "sdk_child_only": True},
        "sdk": {"framework": "pydantic-ai-slim", "version": "2.57.0",
                "openai_version": "3.35.1", "identity": sdk_identity},
    }
    effect = {
        "schema_version": EFFECT_SCHEMA,
        "contract_id": "config-center-one-key-v1-to-v2",
        "app": "rpf52-app-" + suffix,
        "env": "rpf52-local-" + suffix,
        "key": "rpf52.item." + suffix,
        "initial_state": "ABSENT",
        "initial_value": "rpf52-v1",
        "required_value": "rpf52-v2",
        "initial_version": 1,
        "required_version": 2,
        "history_versions": [2, 1],
    }
    experiment = {
        "schema_version": EXPERIMENT_SCHEMA,
        "run_id": run_id,
        "scenario_id": "config-center-sdk-fixture-v1-v2",
        "environment_id": "env-" + run_id,
        "environment_revision": "config-center-local-h2-v1",
        "owner": "rpf-52",
        "runproof_parent_commit": PARENT_SHA,
        "runtime_source_sha256": source_identity_sha256,
        "config_center_source_commit": SOURCE_COMMIT,
        "config_center_manifest_sha256": MANIFEST_SHA,
        "config_center_jar_sha256": JAR_SHA,
        "java_version": java_version,
        "java_port": java_port,
        "agent_host_port": agent_host_port,
        "prepared_at_utc": prepared_at_utc,
        "execution_digest": digest(execution),
        "effect_digest": digest(effect),
    }
    result = {"schema_version": CONTRACT_SCHEMA, "execution": execution,
              "effect": effect, "experiment": experiment}
    validate_contracts(result)
    return result


def validate_contracts(value: Any) -> None:
    require(type(value) is dict and set(value) == {
        "schema_version", "execution", "effect", "experiment"}, "CONTRACT_FIELDS")
    require(value["schema_version"] == CONTRACT_SCHEMA, "CONTRACT_SCHEMA")
    execution, effect, experiment = value["execution"], value["effect"], value["experiment"]
    require(type(execution) is dict and execution.get("schema_version") == EXECUTION_SCHEMA,
            "EXECUTION_SCHEMA")
    require(execution.get("driver") == "pydantic-ai-openai-compatible-fixture-v1"
            and execution.get("model_completions") == "FIXTURE_SCRIPTED", "EXECUTION_DRIVER")
    require(type(execution.get("tool_calls")) is list and len(execution["tool_calls"]) == 3,
            "TOOL_CONTRACT_COUNT")
    run_id = experiment.get("run_id") if type(experiment) is dict else None
    require(isinstance(run_id, str) and _IDENT.fullmatch(run_id)
            and run_id.startswith("rpf52-"), "RUN_ID")
    require(execution["tool_calls"] == _call_definitions(run_id), "TOOL_CONTRACTS")
    require(execution.get("budgets") == BUDGETS, "BUDGETS")
    service, host = execution.get("service"), execution.get("agent_host")
    require(type(service) is dict and service.get("host") == "127.0.0.1"
            and service.get("scheme") == "http"
            and service.get("profile") == "local"
            and service.get("persistence") == "in-memory-h2"
            and service.get("redirects") == "FORBIDDEN"
            and service.get("external_connections") == "FORBIDDEN"
            and type(service.get("port")) is int and 1 <= service["port"] <= 65535,
            "SERVICE_BOUNDARY")
    require(type(host) is dict and host.get("host") == "127.0.0.1"
            and host.get("scheme") == "http" and host.get("sdk_child_only") is True
            and type(host.get("port")) is int and 1 <= host["port"] <= 65535
            and host["port"] != service["port"], "AGENT_HOST_BOUNDARY")
    require(type(effect) is dict and effect.get("schema_version") == EFFECT_SCHEMA
            and effect.get("contract_id") == "config-center-one-key-v1-to-v2"
            and effect.get("initial_state") == "ABSENT"
            and effect.get("initial_value") == "rpf52-v1"
            and effect.get("required_value") == "rpf52-v2"
            and effect.get("initial_version") == 1
            and effect.get("required_version") == 2
            and effect.get("history_versions") == [2, 1], "EFFECT_CONTRACT")
    require(all(isinstance(effect.get(k), str) and _IDENT.fullmatch(effect[k])
                for k in ("app", "env"))
            and isinstance(effect.get("key"), str) and _KEY.fullmatch(effect["key"]),
            "EFFECT_NAMESPACE")
    require(type(experiment) is dict and experiment.get("schema_version") == EXPERIMENT_SCHEMA
            and experiment.get("scenario_id") == "config-center-sdk-fixture-v1-v2"
            and experiment.get("environment_revision") == "config-center-local-h2-v1"
            and experiment.get("owner") == "rpf-52"
            and experiment.get("runproof_parent_commit") == PARENT_SHA
            and experiment.get("config_center_source_commit") == SOURCE_COMMIT
            and experiment.get("config_center_manifest_sha256") == MANIFEST_SHA
            and experiment.get("config_center_jar_sha256") == JAR_SHA, "EXPERIMENT_IDENTITY")
    require(experiment.get("execution_digest") == digest(execution)
            and experiment.get("effect_digest") == digest(effect), "CONTRACT_DIGEST")
    require(bool(_SHA.fullmatch(str(experiment.get("runtime_source_sha256", ""))))
            and _utc(experiment.get("prepared_at_utc"))
            and type(experiment.get("java_port")) is int
            and experiment["java_port"] == service["port"]
            and type(experiment.get("agent_host_port")) is int
            and experiment["agent_host_port"] == host["port"], "EXPERIMENT_SOURCE")
    sdk = execution.get("sdk")
    require(type(sdk) is dict and sdk.get("framework") == "pydantic-ai-slim"
            and sdk.get("version") == "2.57.0" and sdk.get("openai_version") == "3.35.1"
            and type(sdk.get("identity")) is dict, "SDK_IDENTITY")


def _valid_api(observation: dict, status: int, code: int, data_kind: str):
    if (observation.get("status") != status or observation.get("transport_error") is not None
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
    if data_kind == "none" and data is not None:
        return False, None
    if data_kind == "item" and type(data) is not dict:
        return False, None
    if data_kind == "list" and type(data) is not list:
        return False, None
    return True, data


def _valid_item(item: Any, effect: dict, version: int, value: str) -> bool:
    return (type(item) is dict
            and set(item) == {"app", "env", "key", "value", "description", "version", "updatedAt"}
            and all(item[k] == effect[k] for k in ("app", "env", "key"))
            and item["value"] == value and item["description"] is None
            and type(item["version"]) is int and item["version"] == version
            and _utc(item["updatedAt"]))


def _valid_history(rows: Any, effect: dict) -> bool:
    if type(rows) is not list or len(rows) != 2:
        return False
    for row, version, value in zip(rows, (2, 1), ("rpf52-v2", "rpf52-v1")):
        if (type(row) is not dict
                or set(row) != {"app", "env", "key", "value", "description", "version",
                                "action", "operator", "reason", "createdAt"}
                or any(row[k] != effect[k] for k in ("app", "env", "key"))
                or row["value"] != value or row["description"] is not None
                or type(row["version"]) is not int or row["version"] != version
                or row["action"] != "UPSERT" or row["operator"] is not None
                or row["reason"] is not None or not _utc(row["createdAt"])):
            return False
    return True


def evaluate_config_target_effect(effect: dict, observations: list[dict],
                                  tool_trace: list[dict]) -> dict:
    """Recompute the single RPF-52 state transition from recorded content."""
    violations, gaps = [], []
    if type(observations) is not list or len(observations) != len(HTTP_ORDER):
        gaps.append("HTTP_OBSERVATION_COUNT")
        observations = observations if type(observations) is list else []
    by_kind = {}
    for index, item in enumerate(observations):
        if type(item) is not dict or set(item) != _OBS_FIELDS:
            violations.append("HTTP_OBSERVATION_SHAPE")
            continue
        kind = item["kind"]
        if kind not in HTTP_ORDER or kind in by_kind:
            violations.append("HTTP_KIND_DUPLICATE_OR_UNKNOWN")
            continue
        by_kind[kind] = item
        method, path = expected_path(effect, kind)
        request = expected_request(effect, kind)
        if (item["seq"] != index + 1 or kind != HTTP_ORDER[index]
                or item["method"] != method or item["path"] != path
                or item["request"] != request):
            violations.append("HTTP_REQUEST_LINEAGE")
        if (item["response"] is not None
                and item["response_body_sha256"] != digest(item["response"])):
            violations.append("HTTP_RESPONSE_DIGEST")
    if type(tool_trace) is not list or len(tool_trace) != 3:
        gaps.append("TOOL_TRACE_COUNT")
        tool_trace = tool_trace if type(tool_trace) is list else []
    # Call IDs are run-specific; names, arguments, and HTTP order are fixed here.
    expected_tools = (
        ("inspect_config", {}, 3),
        ("create_config_v1", {"value": "rpf52-v1"}, 4),
        ("update_config_v2", {"expected_version": 1, "value": "rpf52-v2"}, 5),
    )
    seen_call_ids = set()
    for index, item in enumerate(tool_trace[:3]):
        if type(item) is not dict:
            violations.append("TOOL_TRACE_SHAPE")
            continue
        name, args, http_seq = expected_tools[index]
        call_id = item.get("call_id")
        if (item.get("name") != name or item.get("arguments") != args
                or item.get("http_seq") != http_seq or item.get("completion_round") != index + 1
                or not isinstance(call_id, str) or call_id in seen_call_ids
                or not isinstance(item.get("tool_return_sha256"), str)
                or not _SHA.fullmatch(item["tool_return_sha256"])):
            violations.append("TOOL_TRACE_BINDING")
        if isinstance(call_id, str):
            seen_call_ids.add(call_id)
    for kind in HTTP_ORDER:
        if kind not in by_kind:
            gaps.append("HTTP_MISSING_" + kind.upper())

    def body(kind, status, code, data_kind):
        item = by_kind.get(kind)
        if item is None:
            return None
        ok, data = _valid_api(item, status, code, data_kind)
        if not ok:
            if item.get("status") is None or item.get("transport_error") is not None:
                gaps.append("HTTP_OUTCOME_UNKNOWN_" + kind.upper())
            else:
                violations.append("API_RESPONSE_CONTRACT_" + kind.upper())
            return None
        return data

    initial, _ = _valid_api(by_kind.get("initial_current", {}), 404, 4041, "none")
    if not initial:
        gaps.append("INITIAL_KEY_NOT_PROVEN_ABSENT")
    initial_history = body("initial_history", 200, 0, "list")
    if initial_history != []:
        gaps.append("INITIAL_HISTORY_NOT_EMPTY_OR_UNAVAILABLE")
    inspected, _ = _valid_api(by_kind.get("inspect_config", {}), 404, 4041, "none")
    if not inspected:
        violations.append("INSPECT_DID_NOT_CONFIRM_ABSENCE")
    created = body("create_config_v1", 200, 0, "item")
    if created is not None and not _valid_item(created, effect, 1, "rpf52-v1"):
        violations.append("CREATE_READBACK_INVALID")
    updated = body("update_config_v2", 200, 0, "item")
    if updated is not None and not _valid_item(updated, effect, 2, "rpf52-v2"):
        violations.append("UPDATE_READBACK_INVALID")
    final = body("final_current", 200, 0, "item")
    if final is not None and not _valid_item(final, effect, 2, "rpf52-v2"):
        violations.append("FINAL_CURRENT_INVALID")
    history = body("final_history", 200, 0, "list")
    if history is not None and not _valid_history(history, effect):
        violations.append("FINAL_HISTORY_INVALID")
    listed = body("final_list", 200, 0, "list")
    if listed is not None and (len(listed) != 1 or not _valid_item(listed[0], effect, 2, "rpf52-v2")):
        violations.append("FINAL_LIST_INVALID")
    outcome = ("VIOLATION_CONFIRMED" if violations else
               "INCONCLUSIVE" if gaps else "CONTRACT_SATISFIED_IN_RUN")
    return {"outcome": outcome, "violations": sorted(set(violations)),
            "gaps": sorted(set(gaps)),
            "facts": {"http_request_count": len(observations),
                      "tool_call_count": len(tool_trace),
                      "initial_absent": bool(initial),
                      "final_value": "rpf52-v2" if final is not None else None,
                      "final_version": 2 if final is not None else None,
                      "history_versions": [2, 1] if history is not None else None}}

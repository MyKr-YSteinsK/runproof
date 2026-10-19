"""Standard-library offline verifier for the RPF-53 REAL_PROVIDER evidence schema."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote

from .config_live_contracts import (
    EVIDENCE_SCHEMA, LIMITS, PROVIDER_MODEL, PROVIDER_NAME, PROVIDER_ORIGIN,
    SOURCE_COMMIT, SOURCE_JAR_BYTES, SOURCE_JAR_SHA256, SOURCE_MANIFEST_SHA256,
    TASK_OWNED_JAR_PATH,
    LiveContractRejected, canonical, digest, require, sha256_bytes, strict_json,
    validate_contracts,
)


class LiveEvidenceRejected(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _reject(condition: bool, code: str) -> None:
    if not condition:
        raise LiveEvidenceRejected(code)


def _sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _sdk_process_identity_valid(sdk: object) -> bool:
    if type(sdk) is not dict:
        return False
    pids = (sdk.get("popen_pid"), sdk.get("ready_pid"), sdk.get("pid"))
    return all(type(pid) is int and pid > 0 for pid in pids) and pids[0] == pids[1] == pids[2]


def _sdk_executable_identity_valid(sdk: object, source_identity: object,
                                   framework_identity: object) -> bool:
    if (type(sdk) is not dict or type(source_identity) is not dict
            or type(framework_identity) is not dict):
        return False
    executable_sha256 = sdk.get("python_executable_sha256")
    launcher_sha256 = source_identity.get("python_launcher_sha256")
    return (_sha(executable_sha256)
            and executable_sha256 == source_identity.get("python_executable_sha256")
            and executable_sha256 == framework_identity.get("python_executable_sha256")
            and _sha(launcher_sha256)
            and launcher_sha256 == framework_identity.get("python_launcher_sha256"))


def _item(data: object, effect: dict, version: int, value: str) -> bool:
    if type(data) is not dict or set(data) != {
            "app", "env", "key", "value", "description", "version", "updatedAt"}:
        return False
    try:
        from datetime import datetime
        ts = datetime.fromisoformat(data["updatedAt"].replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False
    return (all(data[name] == effect[name] for name in ("app", "env", "key"))
            and data["value"] == value and data["description"] is None
            and type(data["version"]) is int and data["version"] == version
            and ts.tzinfo is not None)


def _history(data: object, effect: dict) -> bool:
    if type(data) is not list or len(data) != 2:
        return False
    from datetime import datetime
    for row, version, value in zip(data, (2, 1), ("rpf53-v2", "rpf53-v1")):
        if type(row) is not dict or set(row) != {
                "app", "env", "key", "value", "description", "version",
                "action", "operator", "reason", "createdAt"}:
            return False
        try:
            ts = datetime.fromisoformat(row["createdAt"].replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            return False
        if (any(row[name] != effect[name] for name in ("app", "env", "key"))
                or row["value"] != value or row["description"] is not None
                or type(row["version"]) is not int or row["version"] != version
                or row["action"] != "UPSERT" or row["operator"] is not None
                or row["reason"] is not None or ts.tzinfo is None):
            return False
    return True


def _api(obs: dict, status: int, code: int, kind: str):
    if (obs.get("status") != status or obs.get("transport_error") is not None
            or not isinstance(obs.get("content_type"), str)
            or not obs["content_type"].lower().startswith("application/json")):
        return False, None
    body = obs.get("response")
    if (type(body) is not dict or set(body) != {"code", "message", "data", "traceId"}
            or type(body["code"]) is not int or body["code"] != code
            or type(body["message"]) is not str
            or (body["traceId"] is not None and type(body["traceId"]) is not str)):
        return False, None
    data = body["data"]
    return ((kind == "none" and data is None) or
            (kind == "item" and type(data) is dict) or
            (kind == "list" and type(data) is list)), data


def evaluate_live_effect(effect: dict, observations: list[dict], tool_trace: list[dict]) -> dict:
    """Independent deterministic verdict. Structural gaps remain INCONCLUSIVE."""
    gaps: list[str] = []
    if type(observations) is not list or len(observations) < 7:
        gaps.append("HTTP_OBSERVATIONS_INCOMPLETE")
    if type(tool_trace) is not list or len(tool_trace) < 3:
        gaps.append("SDK_TOOL_TRACE_INCOMPLETE")
    observations = observations if type(observations) is list else []
    tool_trace = tool_trace if type(tool_trace) is list else []
    by_seq = {}
    for index, item in enumerate(observations, 1):
        if type(item) is not dict or set(item) != {
                "seq", "kind", "method", "path", "request", "status", "content_type",
                "response", "response_body_sha256", "elapsed_ms", "transport_error"}:
            gaps.append("HTTP_OBSERVATION_SHAPE")
            continue
        if item.get("seq") != index or index in by_seq:
            gaps.append("HTTP_SEQUENCE_INVALID")
            continue
        if (item.get("response") is not None
                and item.get("response_body_sha256") != digest(item["response"])):
            gaps.append("HTTP_RESPONSE_DIGEST_INVALID")
        by_seq[index] = item
    expected_kinds = ["initial_current", "initial_history"]
    expected_kinds.extend(item.get("name") for item in tool_trace if type(item) is dict)
    expected_kinds.extend(["final_current", "final_history", "final_list"])
    if [item.get("kind") for item in observations if type(item) is dict] != expected_kinds:
        gaps.append("HTTP_ORDER_OR_UNEXPECTED_REQUEST")
    app, env, key = (quote(effect[name], safe="") for name in ("app", "env", "key"))
    for item in observations:
        if type(item) is not dict:
            continue
        kind = item.get("kind")
        if kind in ("initial_current", "inspect_config", "final_current"):
            expected = ("GET", f"/api/configs/{key}?app={app}&env={env}", None)
        elif kind in ("initial_history", "final_history"):
            expected = ("GET", f"/api/configs/history?app={app}&env={env}&key={key}&limit=50", None)
        elif kind == "final_list":
            expected = ("GET", f"/api/configs?app={app}&env={env}", None)
        elif kind == "create_config_v1":
            expected = ("POST", "/api/configs", {"app": effect["app"], "env": effect["env"],
                "key": effect["key"], "value": "rpf53-v1"})
        elif kind == "update_config_v2":
            expected = ("POST", "/api/configs", {"app": effect["app"], "env": effect["env"],
                "key": effect["key"], "value": "rpf53-v2", "expectedVersion": 1})
        else:
            gaps.append("HTTP_KIND_NOT_ALLOWLISTED")
            continue
        if (item.get("method"), item.get("path"), item.get("request")) != expected:
            gaps.append("HTTP_REQUEST_LINEAGE")
    tool_names = [item.get("name") for item in tool_trace if type(item) is dict]
    if (len(tool_names) != len(tool_trace) or "create_config_v1" not in tool_names
            or "update_config_v2" not in tool_names
            or any(name not in ("inspect_config", "create_config_v1", "update_config_v2")
                   for name in tool_names)
            or tool_names.count("create_config_v1") != 1
            or tool_names.count("update_config_v2") != 1
            or not tool_names or tool_names.index("inspect_config") > tool_names.index("create_config_v1")
            or tool_names.index("create_config_v1") > tool_names.index("update_config_v2")):
        gaps.append("SDK_TOOL_ORDER_OR_COUNT")
    ids = set()
    for index, call in enumerate(tool_trace, 1):
        if type(call) is not dict:
            continue
        call_id = call.get("call_id")
        if (not isinstance(call_id, str) or call_id in ids
                or call.get("sequence") != index
                or call.get("arguments_sha256") != digest(call.get("arguments"))
                or call.get("result_sha256") != digest(call.get("result"))
                or type(call.get("returned_in_request")) is not int
                or type(call.get("http_observation_seq")) is not int):
            gaps.append("SDK_TOOL_LINEAGE_INVALID")
        if isinstance(call_id, str):
            ids.add(call_id)
        seq = call.get("http_observation_seq")
        obs = by_seq.get(seq)
        if obs is None or obs.get("kind") != call.get("name"):
            gaps.append("SDK_TOOL_HTTP_LINEAGE")
            continue
        expected_args = ({"value": "rpf53-v1"} if call.get("name") == "create_config_v1"
                         else {"expected_version": 1, "value": "rpf53-v2"}
                         if call.get("name") == "update_config_v2" else {})
        if call.get("arguments") != expected_args:
            gaps.append("SDK_TOOL_ARGUMENTS_INVALID")
        if call.get("name") == "inspect_config":
            absent, _ = _api(obs, 404, 4041, "none")
            present, item_data = _api(obs, 200, 0, "item")
            expected_result = ({"state": "ABSENT"} if absent else
                {"state": "PRESENT", "version": item_data.get("version"),
                 "value": item_data.get("value")} if present and type(item_data) is dict else None)
        elif call.get("name") == "create_config_v1":
            ok, _ = _api(obs, 200, 0, "item")
            expected_result = ({"status": "COMMITTED", "version": 1,
                                "value": "rpf53-v1"} if ok else None)
        else:
            ok, _ = _api(obs, 200, 0, "item")
            expected_result = ({"status": "COMMITTED", "version": 2,
                                "value": "rpf53-v2"} if ok else None)
        if expected_result is None or call.get("result") != expected_result:
            gaps.append("SDK_TOOL_RESULT_NOT_BOUND_TO_HTTP")
    if len(observations) > LIMITS["business_http_requests"]:
        gaps.append("BUSINESS_HTTP_BUDGET_EXCEEDED")
    post_obs = [item for item in observations if type(item) is dict and item.get("method") == "POST"]
    if len(post_obs) != 2 or [item.get("kind") for item in post_obs] != [
            "create_config_v1", "update_config_v2"]:
        gaps.append("MUTATION_COUNT_OR_ORDER")
    initial_current = next((o for o in observations if o.get("kind") == "initial_current"), {})
    initial_history = next((o for o in observations if o.get("kind") == "initial_history"), {})
    final_current = next((o for o in reversed(observations) if o.get("kind") == "final_current"), {})
    final_history = next((o for o in reversed(observations) if o.get("kind") == "final_history"), {})
    final_list = next((o for o in reversed(observations) if o.get("kind") == "final_list"), {})
    initial_ok, _ = _api(initial_current, 404, 4041, "none")
    history0_ok, history0 = _api(initial_history, 200, 0, "list")
    final_ok, final = _api(final_current, 200, 0, "item")
    history_ok, history = _api(final_history, 200, 0, "list")
    list_ok, listed = _api(final_list, 200, 0, "list")
    if not initial_ok or not history0_ok or history0 != []:
        gaps.append("INITIAL_ABSENT_NOT_PROVEN")
    if not final_ok or not _item(final, effect, 2, "rpf53-v2"):
        gaps.append("FINAL_CURRENT_NOT_PROVEN")
    if not history_ok or not _history(history, effect):
        gaps.append("FINAL_HISTORY_NOT_PROVEN")
    if not list_ok or type(listed) is not list or len(listed) != 1 or not _item(listed[0], effect, 2, "rpf53-v2"):
        gaps.append("FINAL_LIST_NOT_PROVEN")
    for kind, status, code, version, value in (
            ("create_config_v1", 200, 0, 1, "rpf53-v1"),
            ("update_config_v2", 200, 0, 2, "rpf53-v2")):
        obs = next((o for o in observations if o.get("kind") == kind), {})
        ok, data = _api(obs, status, code, "item")
        if not ok or not _item(data, effect, version, value):
            gaps.append("MUTATION_EFFECT_NOT_PROVEN_" + kind.upper())
    outcome = "CONTRACT_SATISFIED_IN_RUN" if not gaps else "INCONCLUSIVE"
    return {"outcome": outcome,
            "run_outcome": "EXECUTION_COMPLETE" if not gaps else "INCONCLUSIVE",
            "agent_failure": "NOT_PROVEN", "business_violation": "NOT_PROVEN",
            "violations": [], "gaps": sorted(set(gaps)),
            "facts": {"business_http_requests": len(observations),
                      "sdk_tool_calls": len(tool_trace),
                      "initial_absent": bool(initial_ok and history0_ok and history0 == []),
                      "final_value": "rpf53-v2" if final_ok else None,
                      "final_version": 2 if final_ok else None,
                      "history_versions": [2, 1] if history_ok else None}}


def validate_payload(payload: object) -> dict:
    _reject(type(payload) is dict and set(payload) == {
        "schema_version", "plan_id", "contracts", "source_identity", "sdk",
        "provider", "agent_contract_visibility", "tool_trace", "http_observations", "authority_before",
        "authority_after", "oracle", "safety", "limitations"}, "EVIDENCE_FIELDS")
    _reject(payload["schema_version"] == EVIDENCE_SCHEMA and payload["plan_id"] == "RPF-53",
            "EVIDENCE_SCHEMA")
    try:
        validate_contracts(payload["contracts"], require_live=True)
    except LiveContractRejected as exc:
        raise LiveEvidenceRejected("CONTRACT_" + exc.code) from None
    execution, effect = payload["contracts"]["execution"], payload["contracts"]["effect"]
    _reject(_sha(execution.get("tool_schema_sha256")), "TOOL_SCHEMA_SHA")
    _reject(type(payload["source_identity"]) is dict
            and set(payload["source_identity"]) == {
                "provider", "provider_model", "provider_endpoint", "config_center_source_commit",
                "config_center_manifest_sha256", "config_center_jar_sha256",
                "task_owned_jar_relative_path", "task_owned_jar_sha256", "task_owned_jar_bytes",
                "runtime_source_sha256", "sdk_core_sha256", "python_version",
                "python_executable_sha256", "python_launcher_sha256",
                "pydantic_record_sha256",
                "pydantic_record_entries", "pydantic_record_mismatches",
                "openai_record_sha256", "openai_record_entries",
                "openai_record_mismatches", "openai_core_sha256",
                "sdk_site_root_binding_sha256", "python_runtime_mapping_sha256",
                "java_version", "java_executable_sha256"}
            and payload["source_identity"]["provider"] == PROVIDER_NAME
            and payload["source_identity"]["provider_model"] == PROVIDER_MODEL
            and payload["source_identity"]["provider_endpoint"] == PROVIDER_ORIGIN + "/chat/completions"
            and payload["source_identity"]["config_center_source_commit"] == SOURCE_COMMIT
            and payload["source_identity"]["config_center_manifest_sha256"] == SOURCE_MANIFEST_SHA256
            and payload["source_identity"]["config_center_jar_sha256"] == SOURCE_JAR_SHA256
            and payload["source_identity"]["task_owned_jar_relative_path"] == TASK_OWNED_JAR_PATH
            and payload["source_identity"]["task_owned_jar_sha256"] == SOURCE_JAR_SHA256
            and payload["source_identity"]["task_owned_jar_bytes"] == SOURCE_JAR_BYTES
            and payload["source_identity"]["runtime_source_sha256"] == execution["experiment"]["runtime_source_sha256"]
            and payload["source_identity"]["sdk_core_sha256"] == execution["framework"]["core_sha256"]
            and payload["source_identity"]["python_version"] == "3.12.13"
            and _sha(payload["source_identity"]["python_executable_sha256"])
            and _sha(payload["source_identity"]["python_launcher_sha256"])
            and payload["source_identity"]["pydantic_record_sha256"] == execution["framework"]["identity"].get("pydantic_record_sha256")
            and _sha(payload["source_identity"]["pydantic_record_sha256"])
            and payload["source_identity"]["pydantic_record_entries"] == 444
            and payload["source_identity"]["pydantic_record_mismatches"] == 0
            and payload["source_identity"]["openai_record_sha256"] == execution["framework"]["identity"].get("openai_record_sha256")
            and _sha(payload["source_identity"]["openai_record_sha256"])
            and payload["source_identity"]["openai_record_entries"] == 2000
            and payload["source_identity"]["openai_record_mismatches"] == 0
            and payload["source_identity"]["openai_core_sha256"] == execution["framework"]["identity"].get("openai_core_sha256")
            and _sha(payload["source_identity"]["openai_core_sha256"])
            and payload["source_identity"]["sdk_site_root_binding_sha256"]
                == execution["framework"]["identity"].get("sdk_site_root_binding_sha256")
            and _sha(payload["source_identity"]["sdk_site_root_binding_sha256"])
            and payload["source_identity"]["python_runtime_mapping_sha256"]
                == execution["framework"]["identity"].get("python_runtime_mapping_sha256")
            and _sha(payload["source_identity"]["python_runtime_mapping_sha256"])
            and payload["source_identity"]["java_version"] == "17.0.12"
            and _sha(payload["source_identity"]["java_executable_sha256"]),
            "SOURCE_IDENTITY")
    sdk = payload["sdk"]
    _reject(type(sdk) is dict and set(sdk) == {
        "framework", "version", "openai_version", "popen_pid", "ready_pid", "pid",
        "python_executable_sha256",
        "exit_code", "usage_type",
        "usage_fields", "requests",
        "input_tokens", "output_tokens", "tool_calls", "tool_callbacks",
        "sdk_source_sha256", "openai_source_sha256", "final_output_sha256",
        "final_text_persisted", "guard_denials", "provider_key_present",
        "business_key_present", "stderr_bytes", "stderr_sha256"}
        and sdk["framework"] == "pydantic-ai-slim" and sdk["version"] == "2.57.0"
        and sdk["openai_version"] == "3.35.1" and _sdk_process_identity_valid(sdk)
        and _sdk_executable_identity_valid(sdk, payload["source_identity"],
            execution["framework"]["identity"])
        and sdk["usage_type"] == "pydantic_ai.usage.RunUsage"
        and sdk["usage_fields"] == ["input_tokens", "output_tokens", "requests", "tool_calls"]
        and sdk["exit_code"] == 0 and type(sdk["requests"]) is int
        and 4 <= sdk["requests"] <= LIMITS["provider_https_requests"]
        and all(type(sdk[key]) is int and sdk[key] >= 0 for key in (
            "input_tokens", "output_tokens", "tool_calls", "tool_callbacks"))
        and _sha(sdk["sdk_source_sha256"]) and sdk["sdk_source_sha256"] == execution["framework"]["core_sha256"]
        and _sha(sdk["openai_source_sha256"]) and _sha(sdk["final_output_sha256"])
        and sdk["final_text_persisted"] is False and sdk["guard_denials"] == []
        and sdk["provider_key_present"] is False and sdk["business_key_present"] is False
        and sdk["stderr_bytes"] == 0 and _sha(sdk["stderr_sha256"]), "SDK_IDENTITY_OR_RESULT")
    provider = payload["provider"]
    _reject(type(provider) is dict and set(provider) == {
        "name", "origin", "requested_model", "attempts", "usage"}
        and provider["name"] == PROVIDER_NAME and provider["origin"] == PROVIDER_ORIGIN
        and provider["requested_model"] == PROVIDER_MODEL
        and type(provider["attempts"]) is list and len(provider["attempts"]) == sdk["requests"],
        "PROVIDER_IDENTITY")
    visibility = payload["agent_contract_visibility"]
    _reject(type(visibility) is list and len(visibility) == len(provider["attempts"])
            and all(type(item) is dict and set(item) == {
                "instructions_present", "task_prompt_present", "tool_help_exact",
                "messages_sha256"}
                and item["instructions_present"] is True
                and item["task_prompt_present"] is True
                and item["tool_help_exact"] is True
                and _sha(item["messages_sha256"]) for item in visibility),
            "AGENT_CONTRACT_VISIBILITY")
    previous_ids: list[str] = []
    response_ids = set()
    input_tokens = output_tokens = 0
    tool_ids_from_provider = []
    for index, record in enumerate(provider["attempts"], 1):
        _reject(type(record) is dict and set(record) == {
            "attempt", "run_id", "request_sha256", "reservation_tokens", "status",
            "transport", "response_id", "returned_model", "usage", "tool_schema_sha256",
            "tool_call_ids", "returned_tool_ids", "tool_returns"}
            and record["attempt"] == index
            and record["run_id"] == execution["experiment"]["run_id"]
            and _sha(record["request_sha256"])
            and type(record["reservation_tokens"]) is int and 0 < record["reservation_tokens"]
            and record["status"] == "RECEIVED"
            and record["transport"] == "DeepSeek-HTTPS-no-retry"
            and type(record["response_id"]) is str and record["response_id"] not in response_ids
            and record["returned_model"] in (PROVIDER_MODEL, "DeepSeek-V4.1-Flash-1017")
            and type(record["usage"]) is dict and set(record["usage"]) == {
                "prompt_tokens", "completion_tokens", "total_tokens"}
            and all(type(v) is int and v >= 0 for v in record["usage"].values())
            and record["usage"]["prompt_tokens"] + record["usage"]["completion_tokens"]
                == record["usage"]["total_tokens"]
            and record["usage"]["total_tokens"] <= record["reservation_tokens"]
            and record["usage"]["completion_tokens"] <= LIMITS["max_output_tokens_per_request"]
            and record["tool_schema_sha256"] == execution["tool_schema_sha256"]
            and type(record["tool_call_ids"]) is list
            and type(record["returned_tool_ids"]) is list
            and type(record["tool_returns"]) is list
            and record["returned_tool_ids"] == [item["call_id"] for item in record["tool_returns"]]
            and all(type(item) is dict and set(item) == {"call_id", "result_sha256"}
                    and _sha(item["result_sha256"]) for item in record["tool_returns"]),
            "PROVIDER_ATTEMPT")
        response_ids.add(record["response_id"])
        _reject(record["returned_tool_ids"] == previous_ids, "PROVIDER_TOOL_RETURN_CHAIN")
        _reject(len(set(record["tool_call_ids"])) == len(record["tool_call_ids"]),
                "PROVIDER_TOOL_CALL_IDS")
        previous_ids.extend(record["tool_call_ids"])
        tool_ids_from_provider.extend((record["response_id"], call_id)
                                      for call_id in record["tool_call_ids"])
        input_tokens += record["usage"]["prompt_tokens"]
        output_tokens += record["usage"]["completion_tokens"]
    total = input_tokens + output_tokens
    _reject(total <= LIMITS["total_tokens"], "TOKEN_BUDGET")
    cost = (input_tokens * LIMITS["input_cny_per_million_peak_bound"]
            + output_tokens * LIMITS["output_cny_per_million_peak_bound"]) / 1_000_000
    usage = provider["usage"]
    _reject(type(usage) is dict and set(usage) == {
        "provider_https_requests", "tokens", "confirmed_tokens", "input_tokens",
        "output_tokens", "usage_known", "metering_kind", "estimated_cost_cny_upper",
        "automatic_retries", "trials"}
        and usage["provider_https_requests"] == len(provider["attempts"])
        and usage["tokens"] == total and usage["confirmed_tokens"] == total
        and usage["input_tokens"] == input_tokens and usage["output_tokens"] == output_tokens
        and usage["usage_known"] is True and usage["metering_kind"] == "PROVIDER_REPORTED"
        and usage["estimated_cost_cny_upper"] == cost
        and cost <= LIMITS["estimated_cost_cny_upper"]
        and usage["automatic_retries"] == 0 and usage["trials"] == 1,
        "PROVIDER_USAGE_OR_COST")
    tool_trace = payload["tool_trace"]
    _reject(type(tool_trace) is list and 3 <= len(tool_trace) <= LIMITS["sdk_tool_calls"]
            and sdk["tool_calls"] == len(tool_trace)
            and sdk["tool_callbacks"] == len(tool_trace), "TOOL_TRACE_COUNT")
    seen = set()
    call_origins = {}
    for index, call in enumerate(tool_trace, 1):
        _reject(type(call) is dict and set(call) == {
            "sequence", "provider_response_id", "call_id", "name", "arguments",
            "arguments_sha256", "result", "result_sha256", "returned_in_request",
            "http_observation_seq"}
            and call["sequence"] == index
            and call["provider_response_id"] in response_ids
            and call["call_id"] not in seen and call["name"] in ("inspect_config", "create_config_v1", "update_config_v2")
            and call["arguments_sha256"] == digest(call["arguments"])
            and call["result_sha256"] == digest(call["result"])
            and type(call["returned_in_request"]) is int
            and call["returned_in_request"] == provider["attempts"].index(next(
                item for item in provider["attempts"] if item["response_id"] == call["provider_response_id"])) + 2,
            "TOOL_TRACE_BINDING")
        seen.add(call["call_id"])
        call_origins[call["call_id"]] = call
        _reject((call["provider_response_id"], call["call_id"]) in tool_ids_from_provider,
                "TOOL_CALL_NOT_PROVIDER_ORIGINATED")
        _reject(call["call_id"] in provider["attempts"][call["returned_in_request"] - 1]["returned_tool_ids"],
                "TOOL_RETURN_NOT_REINJECTED")
    for request_index, record in enumerate(provider["attempts"], 1):
        expected_calls = [item["call_id"] for item in tool_trace
                          if provider["attempts"].index(next(
                              request for request in provider["attempts"]
                              if request["response_id"] == item["provider_response_id"])) < request_index - 1]
        _reject(record["returned_tool_ids"] == expected_calls
                and record["tool_returns"] == [{"call_id": call_id,
                    "result_sha256": call_origins[call_id]["result_sha256"]}
                    for call_id in expected_calls], "PROVIDER_TOOL_RETURN_CONTENT")
    _reject(set(seen) == {call_id for _, call_id in tool_ids_from_provider},
            "PROVIDER_TOOL_CALLS_NOT_EXECUTED")
    obs = payload["http_observations"]
    _reject(type(obs) is list, "HTTP_OBSERVATIONS")
    oracle = evaluate_live_effect(effect, obs, tool_trace)
    _reject(payload["oracle"] == oracle and oracle["outcome"] == "CONTRACT_SATISFIED_IN_RUN"
            and oracle["business_violation"] == "NOT_PROVEN", "ORACLE_VERDICT")
    before, after = payload["authority_before"], payload["authority_after"]
    _reject(type(before) is dict and set(before) == {"current_seq", "history_seq"}
            and type(after) is dict and set(after) == {"current_seq", "history_seq", "list_seq"},
            "AUTHORITY_SEQUENCE_FIELDS")
    kinds = {item["seq"]: item["kind"] for item in obs}
    _reject(kinds.get(before["current_seq"]) == "initial_current"
            and kinds.get(before["history_seq"]) == "initial_history"
            and kinds.get(after["current_seq"]) == "final_current"
            and kinds.get(after["history_seq"]) == "final_history"
            and kinds.get(after["list_seq"]) == "final_list", "AUTHORITY_READBACK_LINEAGE")
    safety = payload["safety"]
    _reject(type(safety) is dict and set(safety) == {
        "java_pid", "java_listener_pid", "java_exit_code", "java_stopped",
        "java_listener_closed", "java_external_connections", "java_jar_provenance", "sdk_pid",
        "sdk_stopped", "sdk_external_connections", "host_closed",
        "parent_external_connections", "sdk_provider_key_absent",
        "sdk_business_key_absent", "sdk_guard_denials"}
        and type(safety["java_pid"]) is int and safety["java_pid"] > 0
        and safety["java_listener_pid"] == safety["java_pid"]
        and type(safety["java_exit_code"]) is int and safety["java_stopped"] is True
        and safety["java_listener_closed"] is True and safety["java_external_connections"] == []
        and type(safety["java_jar_provenance"]) is dict
        and set(safety["java_jar_provenance"]) == {
            "task_relative_path", "source_sha256", "copy_sha256", "copy_bytes",
            "source_commit", "manifest_sha256", "popen_argv_matches_copy",
            "actual_process_argv_matches_copy", "actual_command_line_sha256"}
        and safety["java_jar_provenance"]["task_relative_path"] == TASK_OWNED_JAR_PATH
        and safety["java_jar_provenance"]["source_sha256"] == SOURCE_JAR_SHA256
        and safety["java_jar_provenance"]["copy_sha256"] == SOURCE_JAR_SHA256
        and safety["java_jar_provenance"]["copy_bytes"] == SOURCE_JAR_BYTES
        and safety["java_jar_provenance"]["source_commit"] == SOURCE_COMMIT
        and safety["java_jar_provenance"]["manifest_sha256"] == SOURCE_MANIFEST_SHA256
        and safety["java_jar_provenance"]["popen_argv_matches_copy"] is True
        and safety["java_jar_provenance"]["actual_process_argv_matches_copy"] is True
        and _sha(safety["java_jar_provenance"]["actual_command_line_sha256"])
        and safety["sdk_pid"] == sdk["popen_pid"] == sdk["ready_pid"] == sdk["pid"]
        and safety["sdk_stopped"] is True
        and safety["sdk_external_connections"] == [] and safety["host_closed"] is True
        and type(safety["parent_external_connections"]) is list
        and safety["sdk_provider_key_absent"] is True
        and safety["sdk_business_key_absent"] is True
        and safety["sdk_guard_denials"] == [],
        "PROCESS_OR_NETWORK_CLEANUP")
    limitations = payload["limitations"]
    _reject(type(limitations) is dict and set(limitations) == {
        "issuer_authenticity", "database_independent_authority",
        "independent_reproduction", "PGE", "workswarm"}
        and limitations == {"issuer_authenticity": "NOT_ESTABLISHED",
            "database_independent_authority": "NOT_ESTABLISHED",
            "independent_reproduction": "NOT_TESTED", "PGE": "PGE_NOT_EXECUTED",
            "workswarm": "NOT_PROVEN"}, "LIMITATIONS")
    return oracle


def seal_payload(payload: dict) -> bytes:
    validate_payload(payload)
    envelope = {"schema_version": EVIDENCE_SCHEMA,
                "payload_sha256": digest(payload), "payload": payload}
    return canonical(envelope)


def verify_bytes(raw: bytes) -> dict:
    _reject(type(raw) is bytes and 0 < len(raw) <= 2_000_000, "EVIDENCE_SIZE")
    envelope = strict_json(raw)
    _reject(type(envelope) is dict and set(envelope) == {
        "schema_version", "payload_sha256", "payload"}
        and envelope["schema_version"] == EVIDENCE_SCHEMA
        and envelope["payload_sha256"] == digest(envelope["payload"]), "EVIDENCE_ENVELOPE")
    return validate_payload(envelope["payload"])


def verify_file(path: str | Path, external_sha256: str | None) -> int:
    """Exit 0 success, 2 missing anchor, 3 malformed/wrong anchor, 4 invalid evidence."""
    if external_sha256 is None:
        return 2
    if not _sha(external_sha256):
        return 3
    try:
        target = Path(path)
        if target.is_symlink() or not target.is_file():
            return 4
        raw = target.read_bytes()
    except OSError:
        return 4
    if sha256_bytes(raw) != external_sha256:
        return 3
    try:
        verify_bytes(raw)
    except (LiveEvidenceRejected, LiveContractRejected, TypeError, KeyError, ValueError):
        return 4
    return 0

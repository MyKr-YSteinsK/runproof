"""RPF-40 bounded DeepSeek tool-call probe.

The only callable tool reads one task-owned JSON fixture under .local/rpf-40.
This probe does not invoke the RunProof product runner or any business tool.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LOCAL_ROOT = ROOT / ".local" / "rpf-40"
STATE_PATH = LOCAL_ROOT / "sandbox-state.json"
RESULT_PATH = LOCAL_ROOT / "live-result.json"

API_HOST = "api.deepseek.com"
API_PATH = "/chat/completions"
MODEL = "deepseek-flash"
TOOL_NAME = "inspect_sandbox_state"
SCENARIO_ID = "rpf40-local-sandbox"
MAX_PROVIDER_REQUESTS = 2
PLAN_PROVIDER_REQUEST_LIMIT = 6
MAX_AGENT_STEPS = 8
MAX_TOTAL_TOKENS = 15_000
MAX_OUTPUT_TOKENS_PER_REQUEST = 192
REQUEST_TIMEOUT_SECONDS = 90
MAX_LIVE_WINDOW_SECONDS = 20 * 60
MAX_RESPONSE_BYTES = 1_048_576
MAX_ARGUMENT_BYTES = 1_024
MAX_COST_CNY = 3.00
PEAK_INPUT_MISS_USD_PER_MILLION = 0.30
PEAK_OUTPUT_USD_PER_MILLION = 1.20
CONSERVATIVE_CNY_PER_USD = 10.0

SYSTEM_PROMPT = (
    "You are a bounded inspection agent. Call inspect_sandbox_state exactly once "
    "for scenario_id rpf40-local-sandbox. Use only the declared tool. After "
    "receiving its result, give one short factual summary. Do not infer a business "
    "effect or verifier outcome."
)
USER_PROMPT = (
    "Inspect the local sandbox using scenario_id rpf40-local-sandbox. "
    "Return the state revision and health from the tool result."
)

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": "Read the fixed RPF-40 local sandbox state for the allowlisted scenario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scenario_id": {
                        "type": "string",
                        "enum": [SCENARIO_ID],
                    }
                },
                "required": ["scenario_id"],
                "additionalProperties": False,
            },
        },
    }
]

SANDBOX_STATE = {
    "schema_version": "rpf40-sandbox-state-v1",
    "owner": "rpf-40",
    "scenario_id": SCENARIO_ID,
    "environment_revision": "rpf40-local-readonly-v1",
    "state": {
        "health": "ready",
        "revision": 7,
        "operation_count": 0,
        "business_effect": "NOT_TESTED",
    },
}


class ProbeFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _inside_local_root(path: Path, *, must_exist: bool = False) -> Path:
    local = LOCAL_ROOT.resolve()
    resolved = path.resolve(strict=must_exist)
    if resolved != local and local not in resolved.parents:
        raise ProbeFailure("PATH_OUTSIDE_RPF40_LOCAL_ROOT")
    if path.is_symlink():
        raise ProbeFailure("SYMLINK_PATH_REJECTED")
    return resolved


def _create_local_root() -> None:
    root = ROOT.resolve()
    LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    local = LOCAL_ROOT.resolve()
    if root not in local.parents:
        raise ProbeFailure("LOCAL_ROOT_OUTSIDE_REPOSITORY")


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
    _inside_local_root(path)
    raw = _canonical_bytes(value) + b"\n"
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ProbeFailure("OUTPUT_ALREADY_EXISTS") from error


def _create_state_file() -> tuple[str, bool]:
    _inside_local_root(LOCAL_ROOT, must_exist=True)
    if STATE_PATH.exists() or STATE_PATH.is_symlink():
        raise ProbeFailure("SANDBOX_STATE_ALREADY_EXISTS")
    raw = _canonical_bytes(SANDBOX_STATE) + b"\n"
    try:
        with STATE_PATH.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ProbeFailure("SANDBOX_STATE_ALREADY_EXISTS") from error
    return _sha256(raw), True


def _read_state(path: Path, *, allow_temporary_fixture: bool = False) -> dict[str, Any]:
    resolved = _inside_local_root(path, must_exist=True)
    if resolved != STATE_PATH.resolve() and not (
        allow_temporary_fixture and LOCAL_ROOT.resolve() in resolved.parents
    ):
        raise ProbeFailure("STATE_PATH_NOT_ALLOWLISTED")
    raw = path.read_bytes()
    if len(raw) > 4_096:
        raise ProbeFailure("STATE_SIZE_LIMIT")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProbeFailure("STATE_INVALID_JSON") from error
    if not isinstance(value, dict) or value != SANDBOX_STATE:
        raise ProbeFailure("STATE_CONTRACT_MISMATCH")
    return {
        "scenario_id": value["scenario_id"],
        "environment_revision": value["environment_revision"],
        "observed_state": value["state"],
        "state_sha256": _sha256(raw),
    }


def inspect_sandbox_state(
    arguments: Any,
    path: Path = STATE_PATH,
    *,
    allow_temporary_fixture: bool = False,
) -> dict[str, Any]:
    if not isinstance(arguments, dict) or set(arguments) != {"scenario_id"}:
        raise ProbeFailure("TOOL_ARGUMENT_SCHEMA_REJECTED")
    if arguments.get("scenario_id") != SCENARIO_ID:
        raise ProbeFailure("TOOL_SCENARIO_NOT_ALLOWLISTED")
    return _read_state(path, allow_temporary_fixture=allow_temporary_fixture)


def run_negative_control(state_path: Path, *, allow_temporary_fixture: bool = False) -> dict[str, Any]:
    before = state_path.read_bytes()
    before_hash = _sha256(before)
    try:
        inspect_sandbox_state(
            {"scenario_id": "rpf40-unauthorized"},
            state_path,
            allow_temporary_fixture=allow_temporary_fixture,
        )
    except ProbeFailure as error:
        if error.code != "TOOL_SCENARIO_NOT_ALLOWLISTED":
            raise
        rejection_code = error.code
    else:
        raise ProbeFailure("NEGATIVE_CONTROL_WAS_ACCEPTED")
    after_hash = _sha256(state_path.read_bytes())
    if before_hash != after_hash:
        raise ProbeFailure("NEGATIVE_CONTROL_CHANGED_STATE")
    return {
        "status": "PASS",
        "rejection_code": rejection_code,
        "state_sha256_before": before_hash,
        "state_sha256_after": after_hash,
        "state_unchanged": True,
    }


def run_self_check() -> dict[str, Any]:
    _create_local_root()
    with tempfile.TemporaryDirectory(prefix="rpf40-self-check-", dir=LOCAL_ROOT) as temp_dir:
        state_path = Path(temp_dir) / "sandbox-state.json"
        raw = _canonical_bytes(SANDBOX_STATE) + b"\n"
        state_path.write_bytes(raw)
        expected_hash = _sha256(raw)
        valid = inspect_sandbox_state(
            {"scenario_id": SCENARIO_ID},
            state_path,
            allow_temporary_fixture=True,
        )
        if valid["state_sha256"] != expected_hash or valid["observed_state"] != SANDBOX_STATE["state"]:
            raise ProbeFailure("SELF_CHECK_VALID_READBACK_FAILED")
        negative = run_negative_control(state_path, allow_temporary_fixture=True)
        # The offline fixture uses the same contract and readback logic as live mode.
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        if loaded != SANDBOX_STATE or _sha256(state_path.read_bytes()) != expected_hash:
            raise ProbeFailure("SELF_CHECK_STATE_CHANGED")
        if negative["status"] != "PASS":
            raise ProbeFailure("SELF_CHECK_NEGATIVE_CONTROL_FAILED")
    return {
        "status": "PASS",
        "test_kind": "DETERMINISTIC_LOCAL_CONTROL",
        "valid_readback": "PASS",
        "negative_control": negative,
        "provider_requests": 0,
        "state_mutations": 0,
    }


def _validate_usage(data: dict[str, Any], budget: dict[str, Any], record: dict[str, Any]) -> None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        record["failure_code"] = "USAGE_UNAVAILABLE"
        raise ProbeFailure("USAGE_UNAVAILABLE")
    values = [usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")]
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
        record["failure_code"] = "USAGE_INVALID"
        raise ProbeFailure("USAGE_INVALID")
    prompt_tokens, completion_tokens, total_tokens = values
    if prompt_tokens + completion_tokens != total_tokens:
        record["failure_code"] = "USAGE_INCONSISTENT"
        raise ProbeFailure("USAGE_INCONSISTENT")
    budget["actual_tokens"] += total_tokens
    peak_usd = (
        prompt_tokens * PEAK_INPUT_MISS_USD_PER_MILLION
        + completion_tokens * PEAK_OUTPUT_USD_PER_MILLION
    ) / 1_000_000
    budget["estimated_peak_usd"] += peak_usd
    budget["estimated_peak_cny_upper"] = budget["estimated_peak_usd"] * CONSERVATIVE_CNY_PER_USD
    if budget["actual_tokens"] > MAX_TOTAL_TOKENS:
        record["failure_code"] = "TOKEN_BUDGET_EXCEEDED"
        raise ProbeFailure("TOKEN_BUDGET_EXCEEDED")
    if budget["estimated_peak_cny_upper"] > MAX_COST_CNY:
        record["failure_code"] = "COST_BUDGET_EXCEEDED"
        raise ProbeFailure("COST_BUDGET_EXCEEDED")
    record["usage"] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _provider_request(
    messages: list[dict[str, Any]],
    *,
    tool_choice: str,
    budget: dict[str, Any],
    request_records: list[dict[str, Any]],
    live_started: float,
) -> dict[str, Any]:
    if budget["provider_requests"] >= MAX_PROVIDER_REQUESTS:
        raise ProbeFailure("LOCAL_REQUEST_HARD_LIMIT")
    if budget["provider_requests"] >= PLAN_PROVIDER_REQUEST_LIMIT:
        raise ProbeFailure("PLAN_REQUEST_LIMIT")
    if budget["steps"] >= MAX_AGENT_STEPS:
        raise ProbeFailure("AGENT_STEP_LIMIT")
    elapsed = time.monotonic() - live_started
    if elapsed >= MAX_LIVE_WINDOW_SECONDS:
        raise ProbeFailure("LIVE_WINDOW_LIMIT")
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ProbeFailure("DEEPSEEK_API_KEY_UNAVAILABLE")

    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOL_DEFINITIONS,
        "tool_choice": tool_choice,
        "thinking": {"type": "disabled"},
        "max_tokens": MAX_OUTPUT_TOKENS_PER_REQUEST,
        "stream": False,
    }
    body = _canonical_bytes(payload)
    reserve = len(body) + MAX_OUTPUT_TOKENS_PER_REQUEST
    if budget["reserved_token_upper_bound"] + reserve > MAX_TOTAL_TOKENS:
        raise ProbeFailure("TOKEN_RESERVATION_LIMIT")
    reserved_cost_cny = (budget["reserved_token_upper_bound"] + reserve) * (
        PEAK_OUTPUT_USD_PER_MILLION / 1_000_000
    ) * CONSERVATIVE_CNY_PER_USD
    if reserved_cost_cny > MAX_COST_CNY:
        raise ProbeFailure("COST_RESERVATION_LIMIT")

    request_id = "rpf40-" + uuid.uuid4().hex
    record: dict[str, Any] = {
        "local_request_id": request_id,
        "tool_choice": tool_choice,
        "requested_model": MODEL,
        "http_status": None,
        "provider_response_id": None,
        "returned_model": None,
        "finish_reason": None,
        "usage": None,
        "failure_code": None,
    }
    request_records.append(record)
    budget["provider_requests"] += 1
    budget["steps"] += 1
    budget["reserved_token_upper_bound"] += reserve

    remaining = max(1, int(MAX_LIVE_WINDOW_SECONDS - (time.monotonic() - live_started)))
    timeout = min(REQUEST_TIMEOUT_SECONDS, remaining)
    connection = http.client.HTTPSConnection(API_HOST, timeout=timeout, context=ssl.create_default_context())
    try:
        connection.request(
            "POST",
            API_PATH,
            body=body,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Client-Request-Id": request_id,
            },
        )
        response = connection.getresponse()
        record["http_status"] = response.status
        response_body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(response_body) > MAX_RESPONSE_BYTES:
            record["failure_code"] = "RESPONSE_SIZE_LIMIT"
            raise ProbeFailure("RESPONSE_SIZE_LIMIT")
        if response.status != 200:
            record["failure_code"] = "PROVIDER_HTTP_ERROR"
            raise ProbeFailure("PROVIDER_HTTP_ERROR")
        try:
            data = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            record["failure_code"] = "PROVIDER_INVALID_JSON"
            raise ProbeFailure("PROVIDER_INVALID_JSON") from error
        if not isinstance(data, dict):
            record["failure_code"] = "PROVIDER_INVALID_RESPONSE"
            raise ProbeFailure("PROVIDER_INVALID_RESPONSE")
        record["provider_response_id"] = data.get("id") if isinstance(data.get("id"), str) else None
        record["returned_model"] = data.get("model") if isinstance(data.get("model"), str) else None
        choices = data.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            record["finish_reason"] = choices[0].get("finish_reason")
        _validate_usage(data, budget, record)
        record["completed"] = True
        return data
    except ProbeFailure:
        raise
    except (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException, socket.gaierror) as error:
        record["failure_code"] = "PROVIDER_TRANSPORT_OR_TIMEOUT"
        raise ProbeFailure("PROVIDER_TRANSPORT_OR_TIMEOUT") from error
    finally:
        connection.close()


def _one_tool_call(data: dict[str, Any], first_request: dict[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any]]:
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ProbeFailure("TOOL_CALL_RESPONSE_SHAPE")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ProbeFailure("TOOL_CALL_MESSAGE_MISSING")
    calls = message.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
        raise ProbeFailure("TOOL_CALL_COUNT_NOT_ONE")
    call = calls[0]
    call_id = call.get("id")
    function = call.get("function")
    if (
        not isinstance(call_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", call_id)
        or call.get("type") != "function"
        or not isinstance(function, dict)
    ):
        raise ProbeFailure("TOOL_CALL_ENVELOPE_INVALID")
    name = function.get("name")
    raw_arguments = function.get("arguments")
    if name != TOOL_NAME or not isinstance(raw_arguments, str):
        raise ProbeFailure("TOOL_CALL_NAME_OR_ARGUMENTS_INVALID")
    encoded_arguments = raw_arguments.encode("utf-8")
    if len(encoded_arguments) > MAX_ARGUMENT_BYTES:
        raise ProbeFailure("TOOL_ARGUMENT_SIZE_LIMIT")
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as error:
        raise ProbeFailure("TOOL_ARGUMENT_JSON_INVALID") from error
    first_request["tool_call_id"] = call_id
    first_request["tool_name"] = name
    first_request["arguments_sha256"] = _sha256(encoded_arguments)
    first_request["arguments_keys"] = sorted(arguments.keys()) if isinstance(arguments, dict) else []
    try:
        if not isinstance(arguments, dict) or set(arguments) != {"scenario_id"}:
            raise ProbeFailure("TOOL_ARGUMENT_SCHEMA_REJECTED")
        if arguments.get("scenario_id") != SCENARIO_ID:
            raise ProbeFailure("TOOL_SCENARIO_NOT_ALLOWLISTED")
    except ProbeFailure as error:
        first_request["argument_validation"] = "REJECTED"
        first_request["argument_rejection_code"] = error.code
        raise
    first_request["argument_validation"] = "PASS"
    first_request["arguments_summary"] = {"scenario_id": SCENARIO_ID}
    return message, call_id, arguments


def _sanitize_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    # Retain only the API fields needed to associate a tool result with the
    # provider-generated call. In particular, do not forward/store reasoning fields.
    assistant: dict[str, Any] = {"role": "assistant", "content": message.get("content")}
    calls = message.get("tool_calls")
    if not isinstance(calls, list):
        raise ProbeFailure("TOOL_CALLS_MISSING_FOR_RESULT")
    assistant["tool_calls"] = calls
    return assistant


def run_live() -> dict[str, Any]:
    _create_local_root()
    _inside_local_root(STATE_PATH)
    _inside_local_root(RESULT_PATH)
    if RESULT_PATH.exists() or RESULT_PATH.is_symlink():
        raise ProbeFailure("OUTPUT_ALREADY_EXISTS")
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ProbeFailure("DEEPSEEK_API_KEY_UNAVAILABLE")

    run_id = "rpf40-" + uuid.uuid4().hex
    report: dict[str, Any] = {
        "schema_version": "rpf40-live-tool-probe-result-v1",
        "run_id": run_id,
        "started_at": _timestamp(),
        "source_sha256": _sha256(Path(__file__).read_bytes()),
        "adapter": {
            "kind": "bounded-stdlib-http-adapter",
            "revision": "rpf40-deepseek-chat-completions-v1",
            "framework": "WorkSwarm integration NOT_PROVEN",
            "config_sha256": _sha256(_canonical_bytes({
                "model": MODEL,
                "tool_definitions": TOOL_DEFINITIONS,
                "max_provider_requests": MAX_PROVIDER_REQUESTS,
                "max_agent_steps": MAX_AGENT_STEPS,
                "max_total_tokens": MAX_TOTAL_TOKENS,
                "max_output_tokens_per_request": MAX_OUTPUT_TOKENS_PER_REQUEST,
                "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
                "max_live_window_seconds": MAX_LIVE_WINDOW_SECONDS,
                "system_prompt_sha256": _sha256(SYSTEM_PROMPT.encode("utf-8")),
                "user_prompt_sha256": _sha256(USER_PROMPT.encode("utf-8")),
            })),
            "system_prompt_sha256": _sha256(SYSTEM_PROMPT.encode("utf-8")),
            "user_prompt_sha256": _sha256(USER_PROMPT.encode("utf-8")),
        },
        "provider": {
            "id": "deepseek",
            "endpoint": "https://api.deepseek.com/chat/completions",
            "requested_model": MODEL,
            "api_key_present": True,
            "automatic_retries": 0,
            "proxy_used": False,
            "requests": [],
        },
        "tool": {
            "name": TOOL_NAME,
            "registered": True,
            "schema_sha256": _sha256(_canonical_bytes(TOOL_DEFINITIONS)),
            "execution_boundary": "fixed local read-only JSON fixture",
            "environment_revision": SANDBOX_STATE["environment_revision"],
            "state_mutations": 0,
        },
        "negative_control": None,
        "agent_received_tool_result": False,
        "final_text_present": False,
        "budget": {
            "plan_max_provider_requests": PLAN_PROVIDER_REQUEST_LIMIT,
            "local_hard_provider_requests": MAX_PROVIDER_REQUESTS,
            "actual_provider_requests": 0,
            "max_agent_steps": MAX_AGENT_STEPS,
            "actual_agent_steps": 0,
            "max_total_tokens": MAX_TOTAL_TOKENS,
            "actual_total_tokens": 0,
            "reserved_token_upper_bound": 0,
            "fault_trials": 0,
            "max_live_window_seconds": MAX_LIVE_WINDOW_SECONDS,
            "estimated_peak_cost_usd": 0.0,
            "estimated_peak_cost_cny_upper": 0.0,
            "cost_basis": "all input at peak cache-miss rate, all output at peak rate, 10 CNY/USD upper-bound conversion",
        },
        "failure_code": None,
    }
    budget = {
        "provider_requests": 0,
        "steps": 0,
        "actual_tokens": 0,
        "reserved_token_upper_bound": 0,
        "estimated_peak_usd": 0.0,
        "estimated_peak_cny_upper": 0.0,
    }
    live_started = time.monotonic()
    try:
        state_hash, _ = _create_state_file()
        report["tool"]["state_sha256"] = state_hash
        report["negative_control"] = run_negative_control(STATE_PATH)

        initial_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ]
        first_data = _provider_request(
            initial_messages,
            tool_choice="required",
            budget=budget,
            request_records=report["provider"]["requests"],
            live_started=live_started,
        )
        first_record = report["provider"]["requests"][0]
        assistant_message, call_id, arguments = _one_tool_call(first_data, first_record)

        budget["steps"] += 1
        if budget["steps"] > MAX_AGENT_STEPS:
            raise ProbeFailure("AGENT_STEP_LIMIT")
        state_before_dispatch = _sha256(STATE_PATH.read_bytes())
        result = inspect_sandbox_state(arguments, STATE_PATH)
        state_after_dispatch = _sha256(STATE_PATH.read_bytes())
        if state_before_dispatch != state_after_dispatch:
            raise ProbeFailure("READ_ONLY_TOOL_CHANGED_STATE")
        result_bytes = _canonical_bytes(result)
        result_ref = "sha256:" + _sha256(result_bytes)
        report["tool"].update({
            "model_tool_call_received": True,
            "tool_call_id": call_id,
            "argument_validation": "PASS",
            "arguments_summary": first_record["arguments_summary"],
            "dispatch": "EXECUTED",
            "dispatch_steps": 1,
            "result_ref": result_ref,
            "result_summary": {
                "scenario_id": result["scenario_id"],
                "environment_revision": result["environment_revision"],
                "health": result["observed_state"]["health"],
                "revision": result["observed_state"]["revision"],
                "operation_count": result["observed_state"]["operation_count"],
                "business_effect": result["observed_state"]["business_effect"],
            },
            "readback_sha256_before": state_before_dispatch,
            "readback_sha256_after": state_after_dispatch,
        })

        followup_messages = initial_messages + [
            _sanitize_assistant_message(assistant_message),
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": result_bytes.decode("utf-8"),
            },
        ]
        second_data = _provider_request(
            followup_messages,
            tool_choice="none",
            budget=budget,
            request_records=report["provider"]["requests"],
            live_started=live_started,
        )
        second_choice = second_data.get("choices", [{}])[0]
        second_message = second_choice.get("message", {}) if isinstance(second_choice, dict) else {}
        second_calls = second_message.get("tool_calls") if isinstance(second_message, dict) else None
        second_text = second_message.get("content") if isinstance(second_message, dict) else None
        if second_calls:
            raise ProbeFailure("FOLLOWUP_RETURNED_UNEXPECTED_TOOL_CALL")
        if not isinstance(second_text, str) or not second_text.strip():
            raise ProbeFailure("FOLLOWUP_TEXT_MISSING")
        report["provider"]["requests"][1]["tool_result_call_id_received"] = call_id
        report["agent_received_tool_result"] = True
        report["final_text_present"] = True
        report["final_text_sha256"] = _sha256(second_text.encode("utf-8"))
        report["status"] = "PASS_TOOL_CALL_CHAIN"
    except ProbeFailure as error:
        report["failure_code"] = error.code
        report["status"] = "LIVE_PROBE_FAILED"
    finally:
        report["ended_at"] = _timestamp()
        report["budget"]["actual_provider_requests"] = budget["provider_requests"]
        report["budget"]["actual_agent_steps"] = budget["steps"]
        report["budget"]["actual_total_tokens"] = budget["actual_tokens"]
        report["budget"]["reserved_token_upper_bound"] = budget["reserved_token_upper_bound"]
        report["budget"]["estimated_peak_cost_usd"] = round(budget["estimated_peak_usd"], 9)
        report["budget"]["estimated_peak_cost_cny_upper"] = round(budget["estimated_peak_cny_upper"], 9)
        report["budget"]["elapsed_seconds"] = round(time.monotonic() - live_started, 3)
        _write_new_json(RESULT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded RPF-40 local Tool Calling probe.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-check", action="store_true", help="Run deterministic local allowlist/readback controls only.")
    mode.add_argument("--live", action="store_true", help="Use at most two direct DeepSeek API requests with the fixed read-only tool.")
    args = parser.parse_args()
    try:
        if args.self_check:
            result = run_self_check()
            print(json.dumps(result, sort_keys=True))
            return 0
        result = run_live()
        summary = {
            "status": result["status"],
            "failure_code": result.get("failure_code"),
            "provider_requests": result["budget"]["actual_provider_requests"],
            "total_tokens": result["budget"]["actual_total_tokens"],
            "tool_dispatched": result["tool"].get("dispatch") == "EXECUTED",
            "agent_received_tool_result": result["agent_received_tool_result"],
            "result_path": str(RESULT_PATH.relative_to(ROOT)),
        }
        print(json.dumps(summary, sort_keys=True))
        return 0 if result["status"] == "PASS_TOOL_CALL_CHAIN" else 2
    except ProbeFailure as error:
        print(json.dumps({"status": "STOPPED", "failure_code": error.code}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

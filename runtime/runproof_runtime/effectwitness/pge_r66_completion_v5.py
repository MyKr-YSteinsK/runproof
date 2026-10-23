"""Task-owned complete Host boundary, copied from frozen legacy completion.
No call to legacy _completion; no global LIMITS mutation. Transport is inherited.
"""
import time
from .config_live_runtime import (_reject, _tool_schema_summary, _validate_tool_registry,
    LiveRuntimeRejected, LIMITS, PROVIDER_MODEL, AGENT_INSTRUCTIONS, TASK_PROMPT,
    TOOL_ARGUMENT_KEYS, strict_json, digest)
from .pge_r66_response_v5 import validate

def complete(self, body: object) -> dict:
    _reject(self.runtime is not None and type(body) is dict, "SDK_NOT_READY")
    _reject(time.monotonic() - self.request_started < LIMITS["scenario_seconds"],
            "SCENARIO_DEADLINE_EXCEEDED")
    allowed = {"model", "messages", "tools", "tool_choice", "parallel_tool_calls",
               "max_tokens", "max_completion_tokens", "stream", "thinking", "temperature"}
    expected_model = "rpf53-fixture-only" if self.fixture else PROVIDER_MODEL
    _reject(set(body) <= allowed and body.get("model") == expected_model
            and body.get("stream", False) is False
            and body.get("tool_choice", "auto") == "auto"
            and body.get("parallel_tool_calls") is False,
            "MODEL_REQUEST_CONFIG", "AGENT")
    self.tool_schema_summary = _tool_schema_summary(body.get("tools"))
    tool_hash = _validate_tool_registry(body.get("tools"))
    _reject(self.tool_schema_sha256 is None or self.tool_schema_sha256 == tool_hash,
            "SDK_TOOL_SCHEMA_CHANGED", "AGENT")
    if self.expected_tool_schema_sha256 is not None:
        _reject(self.expected_tool_schema_sha256 == tool_hash,
                "SDK_TOOL_SCHEMA_CHANGED", "AGENT")
    self.tool_schema_sha256 = tool_hash
    if self.tool_definitions is None:
        self.tool_definitions = body["tools"]
    else:
        _reject(self.tool_definitions == body["tools"], "SDK_TOOL_SCHEMA_CHANGED", "AGENT")
    messages = body.get("messages")
    _reject(type(messages) is list, "AGENT_MESSAGES_INVALID", "AGENT")
    system_parts, user_parts = [], []
    for item in messages:
        if type(item) is not dict:
            continue
        content = item.get("content")
        if type(content) is str:
            rendered = content
        elif type(content) is list:
            rendered = "\n".join(part.get("text", "") for part in content
                if type(part) is dict and type(part.get("text")) is str)
        else:
            rendered = ""
        if item.get("role") in ("system", "developer"):
            system_parts.append(rendered)
        elif item.get("role") == "user":
            user_parts.append(rendered)
    visibility = {
        "instructions_present": AGENT_INSTRUCTIONS in "\n".join(system_parts),
        "task_prompt_present": TASK_PROMPT in "\n".join(user_parts),
        "tool_help_exact": True,
        "messages_sha256": digest(messages),
    }
    self.visible_contract_checks.append(visibility)
    _reject(visibility["instructions_present"] and visibility["task_prompt_present"],
            "AGENT_VISIBLE_CONTRACT_MISSING", "AGENT")
    returns = self._verify_tool_returns(body)
    decision = self.request_policy(body, returns)
    request = dict(body)
    request.pop("max_completion_tokens", None)
    request.update(max_tokens=decision["outbound_max_tokens"],
                   thinking={"type": "disabled"})
    _reject(len(self.ledger.data["requests"]) < LIMITS["provider_https_requests"],
            "PROVIDER_REQUEST_BUDGET", "PROVIDER")
    if self.fixture:
        if self.fixture_failure_code is not None:
            raise LiveRuntimeRejected(self.fixture_failure_code, "PROVIDER")
        data = self._fixture_response(request)
    else:
        _reject(type(self.api_key) is str and bool(self.api_key), "DEEPSEEK_KEY_UNAVAILABLE", "PROVIDER")
        record = self.ledger.reserve(request, returns, sdk_body=body, stage=decision)
        record["agent_contract_visibility"] = dict(visibility)
        self.ledger.checkpoint()
        try:
            data = self._provider_request(request)
        except LiveRuntimeRejected as exc:
            self.ledger.fail_unknown(record, exc.code)
            raise
        except Exception:
            self.ledger.fail_unknown(record, "PROVIDER_TRANSPORT_ERROR")
            raise LiveRuntimeRejected("PROVIDER_TRANSPORT_ERROR", "PROVIDER") from None
        try:
            data, message, calls = validate(data, authorization=record, account=self.ledger.total.read())
            self.ledger.received(record, data)
        except LiveRuntimeRejected as exc:
            if record["status"] == "RESERVED_USAGE_UNKNOWN":
                self.ledger.fail_unknown(record, exc.code)
            raise
    if self.fixture:
        data, message, calls = validate(data, fixture=True)
    response_id = data["id"]
    _reject(response_id not in {item["response_id"] for item in self.provider_responses},
            "PROVIDER_RESPONSE_ID_REUSED", "PROVIDER")
    call_items = []
    for call in calls:
        args = strict_json(call["function"]["arguments"].encode("utf-8"))
        _reject(type(args) is dict and set(args) == set(TOOL_ARGUMENT_KEYS[call["function"]["name"]]),
                "PROVIDER_TOOL_ARGUMENTS", "AGENT")
        _reject(call["id"] not in self.intents and len(self.intents) < LIMITS["sdk_tool_calls"],
                "TOOL_CALL_ID_DUPLICATE_OR_BUDGET", "AGENT")
        intent = {"response_id": response_id, "call_id": call["id"],
                  "name": call["function"]["name"],
                  "arguments_sha256": digest(args), "arguments": args}
        self.intents[call["id"]] = intent
        call_items.append({"call_id": call["id"], "name": intent["name"],
                           "arguments_sha256": intent["arguments_sha256"]})
    if not self.fixture:
        record["tool_call_ids"] = [item["call_id"] for item in call_items]
        record["tool_schema_sha256"] = tool_hash
        record["returned_tool_ids"] = [item["call_id"] for item in returns]
        self.ledger.checkpoint()
    self.provider_responses.append({"response_id": response_id,
        "model": data["model"], "tool_calls": call_items,
        "usage": {key: data["usage"][key] for key in (
            "prompt_tokens", "completion_tokens", "total_tokens")},
        "request_sha256": digest(request), "tool_returns": returns})
    for item in returns:
        returned = self.tool_returns[item["call_id"]]
        if returned["returned_in_request"] is None:
            returned["returned_in_request"] = len(self.provider_responses)
    if self.fixture:
        return data
    # Upstream content is passed through only to the pinned SDK child. It is not persisted.
    return data

"""Local fixture replies and durable exchange receipts for existing AgentProduct runs."""
from base64 import b64decode, b64encode
from copy import deepcopy
import os
from pathlib import Path
import re
from uuid import uuid4

from .competition_agent import TOOLS, attestation_matches, tool_intent
from .product_local_contracts import SESSION, canonical, digest, strict
from .product_local_session import file_sha, safe_path

MODE = "FIXTURE_MODEL_RESPONSE"
EXCHANGE_SCHEMA = "runproof-fixture-exchange/v1"
PROMPT_VERSION = "effectwitness-fixture-model/v1"
PROMPT = ("Refund the order, then apply the configuration only after verified order feedback. "
          "Choose one provided function with its operation_id, or return the structured decision "
          '{"decision":"STOP"}. The visible feedback result is checked by the host.')
MAX_REPLY_BYTES = 4096
ATTEMPT_DIRECTORY = "fixture-exchanges"
NAME = re.compile(r"[A-Za-z0-9_-]{1,64}", re.ASCII)
OPERATION = re.compile(r"[a-f0-9]{32}-(order|ops)", re.ASCII)
USAGE_KEYS = {"prompt_tokens", "completion_tokens", "total_tokens"}
NON_JSON = b"not a synthetic JSON reply"
TRUNCATED_JSON = b'{"choices":['
UNSTRUCTURED_TEXT = "Synthetic prose without a decision."
DUPLICATE_ARGUMENT = '{"operation_id":"first","operation_id":"second"}'

_WIRE_KEYS = {"id", "choices", "index", "finish_reason", "message", "role", "content", "tool_calls", "type",
              "function", "name", "arguments", "usage", "operation_id", "decision", "extra"} | USAGE_KEYS
_WIRE_STRINGS = {"fixture-local", "fixture-call", "fixture-other", "fixture-incorrect", "fixture_unknown_tool",
                 "assistant", "stop", "tool_calls", "length", "content_filter", "function", "STOP", "",
                 UNSTRUCTURED_TEXT, DUPLICATE_ARGUMENT} | set(TOOLS.values())

# The transport itself receives only this observed input, including the visible attestation.
def model_input(observed):
    candidates = {item["candidate"]: item for item in observed["candidates"]}
    view = observed["feedback"]
    verified = attestation_matches(view, candidates["order"], observed["session_id"], observed["source_sha256"])
    feedback = "ABSENT" if view is None else ("VERIFIED" if verified else "UNVERIFIED")
    tools = []
    for domain, candidate in candidates.items():
        name = TOOLS[domain]
        if domain in observed["available"] and name in observed["tool_allowlist"]:
            tools.append({"type": "function", "function": {"name": name, "parameters": {
                "type": "object", "properties": {"operation_id": {
                    "type": "string", "const": candidate["execution"]["operation_id"]}},
                "required": ["operation_id"], "additionalProperties": False,
            }}})
    return {"prompt_version": PROMPT_VERSION, "task": PROMPT, "tools": tools, "tools_sha256": digest(tools),
            "observation": observed, "visible_feedback_status": feedback}


def _decision(code, intent=None, call_id=None):
    return {"outcome": "DECISION", "code": code, "intent": intent, "call_id": call_id}


def _failure(outcome, code):
    return {"outcome": outcome, "code": code, "intent": None, "call_id": None}


def _decode(raw, reason):
    try:
        return strict(raw)
    except (ValueError, RecursionError) as exc:
        raise ValueError(str(exc) if str(exc) == "DUPLICATE_KEY" else reason) from exc


def parse_reply(raw, observed):
    """Parse a bounded Chat Completions fixture without guessing a tool from prose."""
    if type(raw) is not bytes or len(raw) > MAX_REPLY_BYTES:
        raise ValueError("REPLY_BYTES")
    data = _decode(raw, "REPLY_JSON")
    if (type(data) is not dict or set(data) - {"id", "choices", "usage"}
            or "id" in data and (not isinstance(data["id"], str) or not NAME.fullmatch(data["id"]))
            or type(data.get("choices")) is not list or len(data["choices"]) != 1):
        raise ValueError("CHOICE_ENVELOPE")
    if "usage" in data:
        usage = data["usage"]
        if (type(usage) is not dict or set(usage) - USAGE_KEYS
                or any(type(count) is not int or count < 0 for count in usage.values())):
            raise ValueError("FIXTURE_USAGE_SCHEMA")
    choice = data["choices"][0]
    if (type(choice) is not dict or set(choice) != {"index", "finish_reason", "message"}
            or type(choice["index"]) is not int or choice["index"] != 0):
        raise ValueError("CHOICE_ENVELOPE")
    message, finish = choice["message"], choice["finish_reason"]
    if (type(message) is not dict or set(message) - {"role", "content", "tool_calls"}
            or message.get("role") != "assistant"):
        raise ValueError("ASSISTANT_ENVELOPE")
    content, calls = message.get("content"), message.get("tool_calls", [])
    if type(calls) is not list or (content is not None and type(content) is not str):
        raise ValueError("ASSISTANT_FORMAT")
    if finish == "length":
        return _failure("INCONCLUSIVE", "REPLY_TRUNCATED")
    if finish == "stop":
        if calls:
            raise ValueError("FINISH_REASON_CONFLICT")
        if not content:
            raise ValueError("EMPTY_DECISION")
        if _decode(content.encode("utf-8"), "STRUCTURED_STOP_REQUIRED") != {"decision": "STOP"}:
            raise ValueError("STRUCTURED_STOP_REQUIRED")
        return _decision("STOP")
    if finish != "tool_calls":
        raise ValueError("FINISH_REASON")
    if not calls or content not in (None, ""):
        raise ValueError("TOOL_CALL_ENVELOPE")
    if len(calls) != 1:
        ids = [call.get("id") for call in calls if type(call) is dict and type(call.get("id")) is str]
        raise ValueError("DUPLICATE_TOOL_CALL" if len(set(ids)) != len(ids) else "PARALLEL_TOOL_CALLS")
    call = calls[0]
    if (type(call) is not dict or set(call) != {"id", "type", "function"} or call["type"] != "function"
            or type(call["id"]) is not str or not NAME.fullmatch(call["id"])):
        raise ValueError("TOOL_CALL_ENVELOPE")
    function = call["function"]
    if (type(function) is not dict or set(function) != {"name", "arguments"}
            or type(function["name"]) is not str or not NAME.fullmatch(function["name"])
            or type(function["arguments"]) is not str):
        raise ValueError("FUNCTION_ENVELOPE")

    arguments = _decode(function["arguments"].encode("utf-8"), "ARGUMENT_JSON")
    if type(arguments) is not dict:
        raise ValueError("ARGUMENT_OBJECT")
    name = function["name"]
    candidate = next((item for item in observed["candidates"] if TOOLS[item["candidate"]] == name), None)
    # Start with the host bindings and replace every model-controlled field, including missing IDs.
    step = observed["step"]
    view = observed["feedback"]
    feedback_sha = view.get("sha256") if type(view) is dict else None
    intent = tool_intent(candidate or observed["candidates"][step - 1], step, digest(observed), feedback_sha)
    intent.update(tool=name, arguments=arguments, action_id=arguments.get("operation_id"))
    if candidate is None:
        intent.update(candidate_id=None, contract_sha256=None)
    return _decision("TOOL_INTENT", intent, call["id"])


def _completion(content=None, *, finish="stop", calls=None):
    message = {"role": "assistant", "content": content}
    if calls is not None:
        message["tool_calls"] = calls
    return canonical({"id": "fixture-local", "choices": [{"index": 0, "finish_reason": finish, "message": message}]})


def _call(name, arguments, call_id="fixture-call"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


class FixtureReplyLost(Exception):
    pass


def fixture_transport(fixture, inputs):
    """Return authored, synthetic wire replies. This function has no network path."""
    if fixture == "TIMEOUT":
        raise TimeoutError
    if fixture == "LOST_REPLY":
        raise FixtureReplyLost
    if fixture == "TRANSPORT_ERROR" or fixture == "UNSCHEDULED":
        raise OSError
    if fixture == "CANCELLED":
        raise KeyboardInterrupt
    if fixture == "STOP":
        return _completion('{"decision":"STOP"}')
    if fixture == "TEXT":
        return _completion(UNSTRUCTURED_TEXT)
    if fixture == "EMPTY":
        return _completion()
    if fixture == "NON_JSON":
        return NON_JSON
    if fixture == "TRUNCATED_JSON":
        return TRUNCATED_JSON
    if fixture == "TOKEN_LIMIT":
        return _completion(finish="length")
    if fixture == "WRONG_FINISH":
        return _completion(finish="content_filter")
    if fixture == "OVERSIZE":
        return b"x" * (MAX_REPLY_BYTES + 1)

    observed = inputs["observation"]
    contract = observed["candidates"][observed["step"] - 1]
    operation = contract["execution"]["operation_id"]
    tool = TOOLS[contract["candidate"]]
    arguments = canonical({"operation_id": operation}).decode("ascii")
    if fixture == "WRONG_TOOL":
        tool = TOOLS["ops"] if tool == TOOLS["order"] else TOOLS["order"]
    elif fixture == "UNKNOWN_TOOL":
        tool = "fixture_unknown_tool"
    elif fixture == "WRONG_OPERATION":
        arguments = '{"operation_id":"fixture-incorrect"}'
    elif fixture == "MISSING_OPERATION":
        arguments = "{}"
    elif fixture == "BOOLEAN_OPERATION":
        arguments = '{"operation_id":true}'
    elif fixture == "DUPLICATE_ARGUMENT":
        arguments = DUPLICATE_ARGUMENT
    elif fixture not in {"TOOL", "PARALLEL", "DUPLICATE_CALL"}:
        raise ValueError("FIXTURE_NAME")
    calls = [_call(tool, arguments)]
    if fixture in {"PARALLEL", "DUPLICATE_CALL"}:
        calls.append(_call(tool, arguments, "fixture-other" if fixture == "PARALLEL" else "fixture-call"))
    return _completion(finish="tool_calls", calls=calls)


def _recordable_wire(raw):
    """Persist original bytes only for the bounded vocabulary of the local fixtures."""
    def safe(value, embedded=False):
        if type(value) is dict:
            return all(key in _WIRE_KEYS and safe(item, key in {"arguments", "content"})
                       for key, item in value.items())
        if type(value) is list:
            return all(safe(item) for item in value)
        if type(value) is str:
            if value in _WIRE_STRINGS or OPERATION.fullmatch(value):
                return True
            if embedded:
                decoded = strict(value.encode("utf-8"))
                return type(decoded) is dict and safe(decoded)
            return False
        return value is None or type(value) in {int, bool}

    if raw in (NON_JSON, TRUNCATED_JSON):
        return True
    try:
        return safe(strict(raw))
    except (ValueError, RecursionError):
        return False


def _capture(transport, fixture, inputs):
    try:
        raw = transport(fixture, deepcopy(inputs))
    except TimeoutError:
        return {"state": "TIMEOUT"}
    except FixtureReplyLost:
        return {"state": "LOST_REPLY"}
    except KeyboardInterrupt:
        return {"state": "CANCELLED"}
    except Exception:
        # The local callable's exception text is not evidence.
        return {"state": "TRANSPORT_ERROR"}
    if type(raw) is not bytes:
        return {"state": "INVALID_RETURN"}
    if len(raw) > MAX_REPLY_BYTES:
        return {"state": "OVERSIZE", "bytes": len(raw), "wire_sha256": file_sha(raw)}
    if not _recordable_wire(raw):
        return {"state": "OMITTED", "bytes": len(raw), "wire_sha256": file_sha(raw)}
    return {"state": "RETURNED", "bytes_b64": b64encode(raw).decode("ascii"), "wire_sha256": file_sha(raw)}


def _interpret(reply, observed):
    state = reply["state"]
    exceptions = {"TIMEOUT": ("INCONCLUSIVE", "FIXTURE_TIMEOUT"),
                  "LOST_REPLY": ("INCONCLUSIVE", "FIXTURE_REPLY_LOST"),
                  "TRANSPORT_ERROR": ("ERROR", "FIXTURE_TRANSPORT_ERROR"),
                  "INVALID_RETURN": ("INVALID", "FIXTURE_REPLY_TYPE"),
                  "CANCELLED": ("CANCELLED", "FIXTURE_CANCELLED")}
    if state in exceptions and set(reply) == {"state"}:
        return _failure(*exceptions[state])
    if (state in {"OVERSIZE", "OMITTED"} and set(reply) == {"state", "bytes", "wire_sha256"}
            and type(reply["bytes"]) is int and reply["bytes"] >= 0
            and (reply["bytes"] > MAX_REPLY_BYTES) == (state == "OVERSIZE")
            and re.fullmatch(r"[a-f0-9]{64}", reply["wire_sha256"])):
        return _failure("INVALID", "REPLY_TOO_LARGE" if state == "OVERSIZE" else "REPLY_BODY_OMITTED")
    if state != "RETURNED" or set(reply) != {"state", "bytes_b64", "wire_sha256"}:
        raise ValueError("REPLY_RECEIPT_SCHEMA")
    raw = b64decode(reply["bytes_b64"], validate=True)
    if (len(raw) > MAX_REPLY_BYTES or b64encode(raw).decode("ascii") != reply["bytes_b64"]
            or file_sha(raw) != reply["wire_sha256"]):
        raise ValueError("REPLY_RECEIPT_DIGEST")
    if not _recordable_wire(raw):
        raise ValueError("REPLY_BODY_NOT_RECORDABLE")
    try:
        return parse_reply(raw, observed)
    except ValueError as exc:
        return _failure("INVALID", str(exc) if re.fullmatch(r"[A-Z0-9_]+", str(exc)) else "REPLY_TEXT_ENCODING")


def _start(selection, request, observed, attempt_id):
    step = observed["step"]
    program = selection["fixture_program"]
    inputs = model_input(observed)
    return {"schema": EXCHANGE_SCHEMA, "phase": "STARTED", "attempt_id": attempt_id, "step": step,
            "request": request, "selection_sha256": digest(selection), "session": observed["session_id"],
            "observation_sha256": digest(observed), "input_sha256": digest(inputs), "input": inputs,
            "fixture": program[step - 1] if step <= len(program) else "UNSCHEDULED"}


def _end(start, reply, observed):
    parsed = _interpret(reply, observed)
    return {"schema": EXCHANGE_SCHEMA, "phase": "ENDED", "attempt_id": start["attempt_id"],
            "start_sha256": digest(start), "reply": reply, "reply_sha256": digest(reply), "parsed": parsed}


def _write_receipt(path, data):
    with safe_path(path).open("xb") as handle:
        handle.write(canonical(data))
        handle.flush()
        os.fsync(handle.fileno())


class FixtureModelPolicy:
    """Adapter for a local fixture callable and the existing policy propose method."""

    def __init__(self, owner, selection, request, transport=None):
        self.directory = safe_path(owner / ATTEMPT_DIRECTORY)
        self.directory.mkdir(exist_ok=False)
        self.selection, self.request = selection, request
        self.transport = fixture_transport if transport is None else transport

    def propose(self, observed):
        step = observed["step"]
        start = _start(self.selection, self.request, observed, uuid4().hex)
        _write_receipt(self.directory / f"{step}.started.json", start)
        reply = _capture(self.transport, start["fixture"], start["input"])
        end = _end(start, reply, observed)
        _write_receipt(self.directory / f"{step}.ended.json", end)
        if end["parsed"]["outcome"] != "DECISION":
            # AgentProduct records the existing fail-closed stop without an AGENT_INTENT.
            raise ValueError("FIXTURE_DECISION_UNAVAILABLE")
        return end["parsed"]["intent"]


def _read_receipt(path):
    with safe_path(path).open("rb") as handle:
        raw = handle.read(65537)
    if len(raw) > 65536:
        raise ValueError("EXCHANGE_RECEIPT_SIZE")
    return strict(raw)


def verify_exchanges(owner, selection, record):
    """Reparse the saved replies and compare with the persisted Agent observations and intents."""
    directory = safe_path(owner / ATTEMPT_DIRECTORY)
    names = {path.name for path in directory.iterdir()}
    seen = set()
    expected_names = set()
    receipts = []
    observations = [event["data"] for event in record["events"] if event["kind"] == "AGENT_OBSERVATION"]
    intents = [event["data"]["intent"] for event in record["events"] if event["kind"] == "AGENT_INTENT"]
    for index, observed in enumerate(observations):
        step = observed["step"]
        first, last = f"{step}.started.json", f"{step}.ended.json"
        if first not in names:
            raise ValueError("EXCHANGE_RECEIPT_SET")
        expected_names.add(first)
        start = _read_receipt(directory / first)
        ident = start["attempt_id"]
        if not SESSION.fullmatch(ident) or ident in seen:
            raise ValueError("EXCHANGE_ATTEMPT_ID")
        seen.add(ident)
        if canonical(start) != canonical(_start(selection, record["request_id"], observed, ident)):
            raise ValueError("EXCHANGE_INPUT_BINDING")
        if last not in names:
            if record["status"] != "RUNNING" or index < len(intents) or index != len(observations) - 1:
                raise ValueError("EXCHANGE_RECEIPT_SET")
            receipts.append({"start": start, "end": None})
            continue
        expected_names.add(last)
        end = _read_receipt(directory / last)
        expected = _end(start, end["reply"], observed)
        if canonical(end) != canonical(expected):
            raise ValueError("EXCHANGE_PARSE_OR_BINDING")
        parsed = expected["parsed"]
        if parsed["outcome"] == "DECISION":
            if index >= len(intents) or canonical(parsed["intent"]) != canonical(intents[index]):
                raise ValueError("EXCHANGE_INTENT_MISMATCH")
        elif (index < len(intents) or index != len(observations) - 1 or record["status"] != "RECONCILE_REQUIRED"
              or record["events"][-1]["data"] != {"reason": "READBACK_REQUIRED_NO_REPLAY"}):
            raise ValueError("EXCHANGE_FAILURE_BINDING")
        receipts.append({"start": start, "end": end})
    if names != expected_names:
        raise ValueError("EXCHANGE_RECEIPT_SET")
    return receipts


def code_sha256():
    return file_sha(Path(__file__).read_bytes().replace(b"\r\n", b"\n"))

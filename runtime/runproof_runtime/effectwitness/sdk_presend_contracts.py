"""RPF-102 case, input and durable evidence primitives."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / ".local" / "rpf-102-sdk-presend"
PINS = {"pydantic-ai-slim": "2.57.0", "openai": "3.35.1"}
CASES = ("NORMAL", "UNKNOWN")
BUDGET = {"NORMAL": 2, "UNKNOWN": 1}
LIMIT = 65536
MODEL = "rpf102-scripted-local"
TOOL = "inspect_local"
PROMPT = "Run the local presend conformance tool."
CALL = "call_rpf102_local"
STOP = "rpf102-local-complete"


class Denied(ValueError):
    pass


def check(value, code):
    if not value:
        raise Denied(code)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict(raw):
    def pairs(items):
        obj = dict(items)
        check(len(obj) == len(items), "DUPLICATE_KEY")
        return obj
    obj = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    canonical(obj)
    return obj


def safe(path):
    path = Path(os.path.abspath(path))
    check(path.is_relative_to(ROOT), "OWNER_SCOPE")
    for item in reversed((path, *path.parents)):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        check(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 1024,
              "OWNER_REPARSE")
        if item == path and stat.S_ISREG(info.st_mode):
            check(info.st_nlink == 1, "OWNER_HARDLINK")
    return path


def owner_path(value):
    check(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value), "OWNER_ID")
    return safe(ROOT / value)


def sync_dir(path):
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def exclusive(path, data):
    with safe(path).open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    sync_dir(path.parent)


def bounded(path, limit=LIMIT):
    with safe(path).open("rb") as f:
        data = f.read(limit + 1)
    check(len(data) <= limit, "EVIDENCE_LIMIT")
    return data


def identity():
    names = ("sdk_presend_contracts.py", "sdk_presend_host.py", "sdk_presend_client.py",
             "sdk_presend_oracle.py", "sdk_presend_probe.py")
    return {name: sha(Path(__file__).with_name(name).read_bytes().replace(b"\r\n", b"\n")) for name in names}


def tool_value(case):
    return {"status": "UNKNOWN_OUTCOME" if case == "UNKNOWN" else "LOCAL_TOOL_COMPLETED"}


def validate_request(raw, number, case):
    check(0 < len(raw) <= LIMIT, "REQUEST_LIMIT")
    body = strict(raw)
    permitted = {"model", "messages", "tools", "tool_choice", "stream", "parallel_tool_calls", "max_tokens",
                 "max_completion_tokens", "temperature", "n", "stream_options", "response_format"}
    check(type(body) is dict and set(body) <= permitted and body.get("model") == MODEL
          and body.get("stream", False) is False and body.get("n", 1) == 1, "REQUEST_SCHEMA")
    check(body.get("tool_choice", "auto") in ("auto", "none") and body.get("parallel_tool_calls", False) is False,
          "TOOL_POLICY")
    tools = body.get("tools", [])
    check(type(tools) is list and len(tools) == 1 and tools[0].get("type") == "function"
          and tools[0]["function"].get("name") == TOOL, "TOOL_ALLOWLIST")
    messages = body["messages"]
    check(type(messages) is list and len(messages) == (1 if number == 1 else 3), "MESSAGE_COUNT")
    check(messages[0].get("role") == "user" and messages[0].get("content") == PROMPT, "PROMPT_BINDING")
    if number == 2:
        assistant, result = messages[1:]
        calls = assistant.get("tool_calls")
        check(assistant.get("role") == "assistant" and type(calls) is list and len(calls) == 1
              and calls[0].get("id") == CALL and calls[0].get("type") == "function"
              and calls[0]["function"]["name"] == TOOL
              and strict(calls[0]["function"]["arguments"].encode()) == {}, "ASSISTANT_TOOL_BINDING")
        check(result.get("role") == "tool" and result.get("tool_call_id") == CALL
              and strict(result["content"].encode()) == tool_value(case), "TOOL_RETURN_BINDING")
    return body


def response(case, number):
    message = {"role": "assistant", "content": STOP if number == 2 else None}
    if number == 1:
        message["tool_calls"] = [{"id": CALL, "type": "function",
                                 "function": {"name": TOOL, "arguments": "{}"}}]
    return {"id": f"chatcmpl-rpf102-{case.lower()}-{number}", "object": "chat.completion", "created": 1,
            "model": MODEL, "choices": [{"index": 0, "message": message,
                                         "finish_reason": "tool_calls" if number == 1 else "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}}

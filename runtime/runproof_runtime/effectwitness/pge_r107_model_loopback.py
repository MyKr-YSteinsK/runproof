"""Local scripted response and exact validation of the SDK-facing request."""
from . import pge_r107_contracts as c
from .pge_r106_contracts import exact
from .sdk_presend_contracts import canonical, check, strict

MODEL_PATH = "/v1/chat/completions"
TOOL_PATH = "/tool"


def validate_request(raw, feedback, *, callback=None, tool_result=None):
    check(0 < len(raw) <= c.MAX_HTTP, "MODEL_SIZE")
    row = strict(raw)
    permitted = {"model", "messages", "tools", "tool_choice", "stream", "parallel_tool_calls",
                 "max_tokens", "max_completion_tokens", "n"}
    check(type(row) is dict and set(row) <= permitted and row.get("model") == c.MODEL
          and row.get("stream", False) is False and row.get("parallel_tool_calls", False) is False
          and row.get("tool_choice", "auto") == "auto" and type(row.get("n", 1)) is int
          and row.get("n", 1) == 1, "MODEL_REQUEST")
    for key in ("max_tokens", "max_completion_tokens"):
        if key in row:
            check(type(row[key]) is int and 1 <= row[key] <= 128, "MODEL_TOKEN_BOUND")
    tools = row["tools"]
    check(type(tools) is list and len(tools) == 1, "MODEL_TOOLS")
    tool = exact(tools[0], "type", "function")
    f = tool["function"]
    check(tool["type"] == "function" and type(f) is dict and set(f) <= {"name", "description", "parameters", "strict"}
          and f["name"] == c.TOOL and type(f.get("strict", False)) is bool, "MODEL_TOOL")
    params = f["parameters"]
    check(type(params) is dict and set(params) <= {"type", "properties", "required", "additionalProperties"}
          and params["type"] == "object" and params["required"] == ["candidate_id"]
          and params.get("additionalProperties", False) is False, "MODEL_PARAMS")
    candidate = exact(params["properties"], "candidate_id")["candidate_id"]
    check(type(candidate) is dict and set(candidate) <= {"enum", "type", "title", "description"}
          and candidate.get("type") == "string" and type(candidate.get("enum")) is list
          and sorted(candidate["enum"]) == sorted(c.CHOICES), "MODEL_ENUM")
    messages = row["messages"]
    check(type(messages) is list and len(messages) == (1 if callback is None else 3)
          and messages[0] == {"role": "user", "content": c.prompt(feedback)}, "MODEL_PROMPT")
    if callback is not None:
        assistant, result = messages[1:]
        check(assistant["role"] == "assistant" and len(assistant["tool_calls"]) == 1, "SDK_RETURN_SEQUENCE")
        call = assistant["tool_calls"][0]
        check(call["id"] == callback["call_id"] and call["type"] == "function"
              and call["function"]["name"] == c.TOOL
              and strict(call["function"]["arguments"].encode()) == callback["arguments"]
              and result["role"] == "tool" and result["tool_call_id"] == callback["call_id"]
              and strict(result["content"].encode()) == tool_result, "SDK_RETURN_BINDING")


def response(frozen):
    call = c.tool_request(frozen["tool_call_id"], c.SELECTIONS[frozen["policy"]])
    choice = {"index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
              "tool_calls": [{"id": call["call_id"], "type": "function", "function":
                             {"name": call["name"], "arguments": canonical(call["arguments"]).decode()}}]}}
    return {"id": "chatcmpl-scripted-" + frozen["tool_call_id"], "object": "chat.completion", "created": 1,
            "model": c.MODEL, "choices": [choice],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


def denial():
    return {"error": {"message": "RPF107_TERMINAL_LATCH", "type": "guard_error"}}

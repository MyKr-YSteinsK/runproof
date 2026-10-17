"""Live exploration policy: two unconstrained-in-catalog structured choices."""
from __future__ import annotations

import json

from .contracts import canonical, digest, require
from .provider import MODEL, request_completion


def tool_definitions(plan) -> list[dict]:
    return [{"type": "function", "function": {"name": "select_experiment",
        "description": "Select one allowed controlled order experiment",
        "parameters": {"type": "object", "properties": {"candidate_id": {"type": "string",
            "enum": [c["candidate_id"] for c in plan.document["catalog"]]}},
            "required": ["candidate_id"], "additionalProperties": False}}}]


def parse_choice(data: dict, plan, seen_call_ids: set[str]) -> dict:
    choices = data.get("choices")
    require(type(choices) is list and len(choices) == 1, "EXPLORER_CHOICES", "PROVIDER")
    calls = choices[0].get("message", {}).get("tool_calls")
    require(type(calls) is list and len(calls) == 1, "EXPLORER_ONE_SELECTION_REQUIRED", "AGENT")
    call = calls[0]
    require(type(call) is dict and call.get("type") == "function"
            and isinstance(call.get("id"), str) and 0 < len(call["id"]) <= 128
            and call["id"] not in seen_call_ids, "EXPLORER_CALL_IDENTITY", "AGENT")
    function = call.get("function")
    require(type(function) is dict and set(function) == {"name", "arguments"}
            and function["name"] == "select_experiment" and isinstance(function["arguments"], str),
            "EXPLORER_TOOL_NOT_ALLOWLISTED", "AGENT")
    try:
        arguments = json.loads(function["arguments"])
    except ValueError as failure:
        from ..models import RuntimeFailure
        raise RuntimeFailure("AGENT", "EXPLORER_ARGUMENT_JSON") from failure
    require(type(arguments) is dict and set(arguments) == {"candidate_id"}, "EXPLORER_ARGUMENT_FIELDS", "AGENT")
    plan.candidate(arguments["candidate_id"])
    seen_call_ids.add(call["id"])
    return {"id": call["id"], "type": "function", "function": {
        "name": "select_experiment", "arguments": canonical(arguments).decode()}}


def initial_messages(plan) -> list[dict]:
    # No B0 results/order, predictions, next-choice answer, authority path or future state.
    visible = {"catalog": plan.document["catalog"], "trials_available": 2,
               "effect_contract": "frozen CNY 2500 PAID to REFUNDED once, one committed receipt",
               "observed_feedback": [], "objective": plan.document["objective"]}
    return [{"role": "system", "content":
        "You select experiments in a controlled fictional order sandbox. Your objective is to learn "
        "distinct independently verified activation/provenance facts within two trials. Choose one "
        "candidate using select_experiment. Use only evidence returned by the tool. Every catalog "
        "choice remains legal on each round, including repeats. You cannot edit contracts or tools."},
        {"role": "user", "content": canonical(visible).decode()}]


def explore(session):
    messages = initial_messages(session.plan)
    registered = tool_definitions(session.plan)
    session.result["exploration_agent"] = {"provider": "DeepSeek", "model": MODEL,
        "tool_registration": registered, "initial_visible_document": json.loads(messages[1]["content"]),
        "initial_messages_hash": digest(messages), "workswarm": "WORKSWARM_NOT_PROVEN"}
    call_ids = set()
    previous = None
    for round_index in (1, 2):
        if previous:
            session.event("FEEDBACK_DELIVERY_RESERVED", round=round_index,
                          feedback_hash=previous["sha256"], tool_call_id=messages[-1]["tool_call_id"])
        body = {"model": MODEL, "messages": messages, "tools": registered, "tool_choice": "required",
                "thinking": {"type": "disabled"}, "max_tokens": 128, "stream": False}
        session.event("PROVIDER_INPUT_FROZEN", round=round_index, messages_hash=digest(messages),
                      body_hash=digest(body), feedback_hash=previous["sha256"] if previous else None,
                      feedback_content=previous["document"] if previous else None)
        data = request_completion(body, session.budget, session.result["provider_requests"], session.save)
        record = session.result["provider_requests"][-1]
        call = parse_choice(data, session.plan, call_ids)
        candidate_id = json.loads(call["function"]["arguments"])["candidate_id"]
        record.update(round=round_index, selection={"tool": "select_experiment", "candidate_id": candidate_id,
                      "tool_call_id": call["id"]}, input_feedback_hash=previous["sha256"] if previous else None,
                      finish_reason=data["choices"][0].get("finish_reason"))
        session.event("PROVIDER_SELECTION_ACCEPTED", round=round_index, candidate_id=candidate_id,
                      tool_call_id=call["id"], response_id=record["response_id"])
        previous = session.execute("PGE", candidate_id)
        messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        messages.append({"role": "tool", "tool_call_id": call["id"],
                         "content": canonical(previous["document"]).decode()})
    # No third call for a cosmetic summary: second trial feedback is saved locally.

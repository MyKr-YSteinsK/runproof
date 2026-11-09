"""Frozen identity, policy and scripted protocol for the RPF-104 slice."""
import re
from pathlib import Path

from .effect_oracle import evaluate_order_effect
from .ops_oracle import evaluate_ops_effect
from .sdk_presend_contracts import CASES, LIMIT, canonical, check, sha, strict

SCHEMA = "rpf104-contract-v1"
POLICY = "rpf104-feedback-gate/v1"
MODEL = "rpf104-scripted-local"
PROMPT = "Execute the admitted local product experiment."
STOP = "rpf104-local-complete"
DOMAINS = {"order": "refund_order", "ops": "change_config"}
POSTS = {"NORMAL": 3, "UNKNOWN": 2}
FORWARDS = {"NORMAL": 3, "UNKNOWN": 1}
FAULT = "POST_COMMIT_RESPONSE_LOSS"
SUCCESS = "CONTRACT_SATISFIED_IN_RUN"
MODULES = ("contracts", "target", "host", "client", "probe", "oracle", "capsule")
DEPENDENCIES = ("effect_oracle", "ops_oracle", "product_local_ports", "product_local_contracts",
                "sdk_presend_contracts", "sdk_presend_client", "sdk_presend_diagnostic",
                "sdk_presend_oracle", "sdk_presend_host", "sdk_presend_probe")


def hex_id(value, size):
    return type(value) is str and re.fullmatch(rf"[a-f0-9]{{{size}}}", value) is not None


def sources():
    names = tuple(f"product_sdk_{name}" for name in MODULES) + DEPENDENCIES
    return {name: sha(Path(__file__).with_name(name + ".py").read_bytes().replace(b"\r\n", b"\n"))
            for name in names}


def freeze(source, run, owner, case, *, origin="GITHUB"):
    check(hex_id(source, 40) and hex_id(owner, 32) and case in CASES
          and ((origin == "GITHUB" and type(run) is str and re.fullmatch(r"[1-9][0-9]{0,15}", run))
               or (origin == "LOCAL" and hex_id(run, 32))), "RUN_IDENTITY")
    scope = {"schema": SCHEMA, "origin": origin, "source_git_sha": source, "run_id": run,
             "owner": owner, "case": case}
    contracts = {}
    for domain in DOMAINS if case == "NORMAL" else ("order",):
        op = sha(canonical({**scope, "domain": domain}))
        effect = ({"order_id": "rpf104-order", "amount_minor": 2500, "currency": "CNY"} if domain == "order"
                  else {"config_id": "rpf104-config"})
        body = {
            "execution": {**scope, "domain": domain, "operation_id": op, "environment_id": "env-" + op,
                          "db_member": domain + ".sqlite", "tool": DOMAINS[domain],
                          "call_id": f"call_rpf104_{case.lower()}_{domain}"},
            "effect": {"operation_id": op, **effect},
            "experiment": {"writes": 1, "fault": FAULT if case == "UNKNOWN" else "NONE"},
        }
        contracts[domain] = {**body, "sha256": sha(canonical(body))}
    return {**scope, "contracts": contracts, "policy": POLICY,
            "budget": {"posts": POSTS[case], "forwards": FORWARDS[case], "writes": len(contracts),
                       "max_payload_bytes": LIMIT, "max_receiver_bytes": LIMIT * FORWARDS[case],
                       "external_provider_requests": 0}}


def validate_frozen(value):
    check(type(value) is dict, "FROZEN_TYPE")
    expected = freeze(value["source_git_sha"], value["run_id"], value["owner"], value["case"],
                      origin=value["origin"])
    check(canonical(expected) == canonical(value), "FROZEN_IDENTITY")
    return expected


def binding(frozen, domain):
    contract = frozen["contracts"][domain]
    return {**contract["execution"], "contract_sha256": contract["sha256"]}


def flags(contract, *, triggered=False, observed=False, agent_exposed=False):
    planned = contract["experiment"]["fault"] == FAULT
    check(all(type(x) is bool for x in (triggered, observed, agent_exposed))
          and agent_exposed <= observed <= triggered <= planned, "FAULT_SEQUENCE")
    return {"planned": planned, "triggered": triggered, "observed": observed, "agent_exposed": agent_exposed}


def validate_readback(frozen, domain, row):
    identity = binding(frozen, domain)
    key = "order" if domain == "order" else "config"
    check(type(row) is dict and set(row) == {"binding", "authority", "pid", "snapshot"}
          and canonical(row["binding"]) == canonical(identity) and row["authority"] == "SQLITE_RO_QUERY_ONLY"
          and type(row["pid"]) is int and row["pid"] > 0 and type(row["snapshot"]) is dict
          and set(row["snapshot"]) == {key, "receipts"} and type(row["snapshot"]["receipts"]) is list,
          "AUTHORITY_IDENTITY")
    return row


def feedback(frozen, domain, before, after, fault):
    contract = frozen["contracts"][domain]
    identity = binding(frozen, domain)
    for row in (before, after):
        validate_readback(frozen, domain, row)
    expected_fault = flags(contract, triggered=fault["triggered"], observed=fault["observed"],
                           agent_exposed=fault["agent_exposed"])
    check(canonical(fault) == canonical(expected_fault), "FAULT_FLAGS")
    evaluate = evaluate_order_effect if domain == "order" else evaluate_ops_effect
    result = evaluate(contract["effect"], identity["environment_id"], before["snapshot"], after["snapshot"])
    value = {"binding": identity, "policy": POLICY, "authority": after["authority"],
             "fault": fault, "outcome": result["contract_outcome"], "receipt_sha256": result.get("receipt_hash"),
             "before_sha256": sha(canonical(before)), "after_sha256": sha(canonical(after))}
    return {"value": value, "sha256": sha(canonical(value))}


def reconciliation(frozen, before, after, verified):
    check(frozen["case"] == "UNKNOWN", "RECONCILE_SCOPE")
    validate_readback(frozen, "order", before)
    validate_readback(frozen, "order", after)
    if verified["value"]["outcome"] == SUCCESS:
        return "COMMITTED"
    if not after["snapshot"]["receipts"] and canonical(before["snapshot"]) == canonical(after["snapshot"]):
        return "NOT_COMMITTED"
    return "INCONCLUSIVE"


def select_ops(frozen, verified, *, latched):
    if latched or frozen["case"] != "NORMAL" or type(verified) is not dict:
        return "MUST_STOP"
    try:
        value = verified["value"]
        good = (verified["sha256"] == sha(canonical(value)) and value["binding"] == binding(frozen, "order")
                and value["authority"] == "SQLITE_RO_QUERY_ONLY" and value["policy"] == POLICY
                and value["outcome"] == SUCCESS and value["fault"] == flags(frozen["contracts"]["order"])
                and all(hex_id(value[key], 64) for key in ("receipt_sha256", "before_sha256", "after_sha256")))
    except (KeyError, TypeError, ValueError):
        good = False
    return "SELECT_OPS" if good else "MUST_STOP"


def call(frozen, domain):
    row = frozen["contracts"][domain]["execution"]
    return {"id": row["call_id"], "type": "function", "function": {"name": row["tool"], "arguments": "{}"}}


def tool_value(domain, verified):
    return ({"status": "UNKNOWN_OUTCOME"} if verified is None else
            {"status": "AUTHORITY_VERIFIED", "domain": domain, "feedback_sha256": verified["sha256"]})


def validate_request(frozen, raw, prior_tools):
    check(0 < len(raw) <= LIMIT, "HTTP_SIZE")
    row = strict(raw)
    allowed = {"model", "messages", "tools", "tool_choice", "stream", "parallel_tool_calls", "max_tokens",
               "max_completion_tokens", "n"}
    check(type(row) is dict and set(row) <= allowed and row.get("model") == MODEL
          and row.get("stream", False) is False and row.get("parallel_tool_calls", False) is False
          and type(row.get("n", 1)) is int and row.get("n", 1) == 1
          and row.get("tool_choice", "auto") in ("auto", "none"), "POST_SCHEMA")
    for key in ("max_tokens", "max_completion_tokens"):
        if key in row:
            check(type(row[key]) is int and 1 <= row[key] <= 128, "TOKEN_BOUND")
    tools = row.get("tools")
    check(type(tools) is list and len(tools) == 2, "TOOLS")
    names = set()
    for item in tools:
        check(type(item) is dict and set(item) == {"type", "function"} and item["type"] == "function", "TOOL")
        f = item["function"]
        check(type(f) is dict and set(f) <= {"name", "description", "strict", "parameters"}
              and f["name"] in DOMAINS.values() and f.get("description", "") in ("", "Execute the admitted operation.")
              and type(f.get("strict", False)) is bool, "TOOL_FUNCTION")
        p = f.get("parameters", {"type": "object"})
        check(type(p) is dict and set(p) <= {"type", "properties", "required", "additionalProperties"}
              and p.get("type") == "object" and p.get("properties", {}) == {}
              and p.get("required", []) == [] and p.get("additionalProperties", False) is False, "TOOL_PARAMETERS")
        names.add(f["name"])
    check(names == set(DOMAINS.values()), "TOOLS")
    messages = row["messages"]
    check(type(messages) is list and len(messages) == 1 + 2 * len(prior_tools)
          and messages[0] == {"role": "user", "content": PROMPT}, "MESSAGE_COUNT")
    for n, (domain, value) in enumerate(prior_tools):
        assistant, result = messages[1 + 2*n:3 + 2*n]
        expected = call(frozen, domain)
        check(type(assistant) is dict and set(assistant) <= {"role", "content", "tool_calls"}
              and assistant.get("role") == "assistant" and assistant.get("content") in (None, "")
              and type(assistant.get("tool_calls")) is list and len(assistant["tool_calls"]) == 1, "ASSISTANT")
        actual = assistant["tool_calls"][0]
        check(type(actual) is dict and set(actual) == set(expected)
              and actual["id"] == expected["id"] and actual["type"] == expected["type"]
              and type(actual["function"]) is dict and set(actual["function"]) == {"name", "arguments"}
              and actual["function"]["name"] == expected["function"]["name"]
              and type(actual["function"]["arguments"]) is str
              and strict(actual["function"]["arguments"].encode()) == {}, "CALL_BINDING")
        check(type(result) is dict and set(result) == {"role", "tool_call_id", "content"}
              and result["role"] == "tool" and result["tool_call_id"] == expected["id"]
              and type(result["content"]) is str and canonical(strict(result["content"].encode())) == canonical(value),
              "TOOL_RETURN_BINDING")
    return {"sha256": sha(raw), "bytes": len(raw), "number": 1 + len(prior_tools)}


def response(frozen, number):
    domain = {1: "order", 2: "ops"}.get(number)
    message = {"role": "assistant", "content": STOP if domain is None else None}
    if domain:
        message["tool_calls"] = [call(frozen, domain)]
    return {"id": f"chatcmpl-rpf104-{frozen['case'].lower()}-{number}", "object": "chat.completion",
            "created": 1, "model": MODEL, "choices": [{"index": 0, "message": message,
            "finish_reason": "tool_calls" if domain else "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}}

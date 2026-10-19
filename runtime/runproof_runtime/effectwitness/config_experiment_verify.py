"""Independent deterministic offline RPF-55 verifier. No SDK, Java or network."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
from .config_experiment_contracts import (canonical, digest, strict_json, require,
    validate_contracts, CANDIDATES, EVIDENCE_SCHEMA, BOUNDARIES)
from .config_live_contracts import SOURCE_JAR_SHA256, SDK_CORE_SHA256
from .config_live_runtime import _api_response, _valid_item, _http_contract
from .config_live_verify import _history

ROOT = Path(__file__).resolve().parents[3]
# Exact rev-2 executor used by all three immutable Scene captures, before the
# post-run export allowlist correction. No other historical executor is admitted.
EXECUTED_PROBE_SHA256 = "5e2a2a0fca438769d6371d843c8aacf249e7f5672f69d7e96dae413d09486ebd"
SOURCE_FILES = tuple("runtime/runproof_runtime/effectwitness/" + name + ".py" for name in (
    "config_experiment_contracts", "config_experiment_adapter",
    "config_live_runtime", "config_live_contracts", "config_live_external", "config_live_verify")) + ("spikes/rpf-55/probe.py", "spikes/rpf-53/probe.py")

def source_identity():
    return {p: hashlib.sha256((ROOT / p).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in SOURCE_FILES}

def verifier_identity():
    return {"version": "rpf55-config-experiment-verifier-v2.1", "sha256": hashlib.sha256(
        Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()}

def validate_execution_source(value):
    current = source_identity()
    frozen = {**current, "spikes/rpf-55/probe.py": EXECUTED_PROBE_SHA256}
    require(value == current or value == frozen, "EXECUTION_SOURCE_IDENTITY")
    return "CURRENT_TREE" if value == current else "RPF55_REV2_INITIAL_FROZEN"

def pinned_sdk_fields():
    raw = (ROOT / "spikes/rpf-53/rev-6/config-live-evidence.json").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == "f5e46947ae2a2583db51727e85c4f9e3d6c9d6499a1b24833dfffe1799438b43", "SDK_PIN_ANCHOR")
    return strict_json(raw)["payload"]["contracts"]["execution"]["framework"]["identity"]

def seal(payload):
    return {"schema": EVIDENCE_SCHEMA, "plan_revision": "rev-2", "verifier_identity": verifier_identity(),
            "payload": payload, "payload_sha256": digest(payload)}

def verify_scene(s, candidate, source_sha):
    require(type(s) is dict and set(s) == {"contracts", "contracts_sha256", "http", "events",
        "tool_trace", "completions", "sdk", "environment", "fault", "outcome"}, "SCENE_FIELDS")
    c = s["contracts"]
    validate_contracts(c)
    x, effect = c["experiment"], c["effect"]
    require(x["candidate_id"] == candidate and x["runtime_source_sha256"] == source_sha
            and s["contracts_sha256"] == digest(c), "SCENE_IDENTITY")
    suppressed = candidate == CANDIDATES[2]
    require(s["fault"] == {"planned": candidate != "normal", "triggered": suppressed,
        "observed": suppressed, "channel": "EXPLICIT_TOOL_DELIVERY_ERROR" if suppressed else "NONE"}, "FAULT_CLAIM")
    require(s["outcome"] == {"agent_failure": "NOT_EVALUATED_FIXTURE", "platform_error":
        "EXPECTED_DELIVERY_ERROR" if suppressed else "NONE", "business_violation": False,
        "contract_outcome": "SATISFIED", "reconcile": "READ_ONLY_CONFIRMED" if suppressed else "NOT_REQUIRED",
        "target_ack": "UNKNOWN_OUTCOME" if suppressed else "RECEIVED"}, "OUTCOME_CLAIM")
    observations = s["http"]
    kinds = ["initial_current", "initial_history", "inspect_config", "create_config_v1", "update_config_v2"]
    kinds += (["reconcile_current", "reconcile_history", "final_list"] if suppressed else
              ["final_current", "final_history", "final_list"])
    require(type(observations) is list and len(observations) == len(kinds), "HTTP_COUNT")
    for i, (o, kind) in enumerate(zip(observations, kinds), 1):
        require(type(o) is dict and set(o) == {"seq", "kind", "method", "path", "request", "status", "content_type",
            "response", "response_body_sha256", "elapsed_ms", "transport_error"}, "HTTP_FIELDS")
        method, path, body = _http_contract(effect, kind)
        require(o.get("seq") == i and o.get("kind") == kind and o.get("method") == method
                and o.get("path") == path and o.get("request") == body, "HTTP_PATH_NAMESPACE_OR_REPLAY")
        absent = kind in ("initial_current", "inspect_config")
        history = kind.endswith("history") or kind == "final_list"
        ok, data = _api_response(o, 404 if absent else 200, 4041 if absent else 0,
                                 "none" if absent else "list" if history else "item")
        require(ok and o["response_body_sha256"] == digest(o["response"]), "HTTP_RESPONSE")
        if kind == "initial_history":
            require(data == [], "INITIAL_HISTORY")
        elif history:
            require((len(data) == 1 and _valid_item(data[0], effect, 2, "rpf53-v2"))
                    if kind == "final_list" else _history(data, effect), "AUTHORITY_NAMESPACE_HISTORY")
        elif not absent:
            v = 1 if kind == "create_config_v1" else 2
            require(_valid_item(data, effect, v, "rpf53-v1" if v == 1 else "rpf53-v2"), "EFFECT_ITEM")
    events = s["events"]
    require(type(events) is list and events and events[0]["kind"] == "PRE_REGISTERED", "PRE_REGISTRATION")
    require([e["seq"] for e in events] == list(range(1, len(events) + 1))
            and all(e["run_id"] == x["run_id"] and type(e["monotonic_ns"]) is int for e in events)
            and [e["monotonic_ns"] for e in events] == sorted(e["monotonic_ns"] for e in events), "EVENT_ORDER_RUN")
    require(events[0]["candidate"] == candidate, "EVENT_CANDIDATE")
    fields = {"PRE_REGISTERED": {"candidate"}, "HTTP_RESERVED": {"http_seq", "method", "operation"},
        "HTTP_COMPLETED": {"http_seq", "status", "code"}, "TOOL_RESERVED": {"call_id", "name"},
        "TOOL_RESULT_READY": {"call_id", "name"}, "SUCCESS_RELEASED": {"call_id", "name"},
        "SUCCESS_WITHHELD": {"call_id", "name", "http_seq", "channel"},
        "FAULT_INHIBITED": {"reason"}, "SDK_ERROR_OBSERVED": {"returncode", "status", "error_type"}}
    require(all(e["kind"] in fields and set(e) == fields[e["kind"]] | {
        "seq", "run_id", "monotonic_ns", "kind"} for e in events), "EVENT_FIELDS")
    for kind, count in {"PRE_REGISTERED": 1, "TOOL_RESERVED": 3, "TOOL_RESULT_READY": 3,
            "SUCCESS_RELEASED": 2 if suppressed else 3, "SDK_ERROR_OBSERVED": int(suppressed)}.items():
        require(sum(e["kind"] == kind for e in events) == count, "EVENT_CARDINALITY")
    for o in observations:
        reserved = [e for e in events if e["kind"] == "HTTP_RESERVED" and e["http_seq"] == o["seq"]]
        completed = [e for e in events if e["kind"] == "HTTP_COMPLETED" and e["http_seq"] == o["seq"]]
        require(len(reserved) == len(completed) == 1 and reserved[0]["seq"] < completed[0]["seq"]
            and reserved[0]["method"] == o["method"] and reserved[0]["operation"] == o["kind"]
            and completed[0]["status"] == o["status"] and completed[0]["code"] == o["response"]["code"], "HTTP_EVENT_BINDING")
    trace = s["tool_trace"]
    names = ["inspect_config", "create_config_v1", "update_config_v2"]
    require([t["name"] for t in trace] == names and len({t["call_id"] for t in trace}) == 3, "TOOL_LINEAGE")
    for i, t in enumerate(trace):
        args = ({}, {"value": "rpf53-v1"}, {"expected_version": 1, "value": "rpf53-v2"})[i]
        result = {"state": "ABSENT"} if i == 0 else {"status": "COMMITTED", "version": i, "value": "rpf53-v" + str(i)}
        require(t["sequence"] == i + 1 and t["http_observation_seq"] == i + 3
            and t["arguments"] == args and t["arguments_sha256"] == digest(args)
            and t["result"] == result and t["result_sha256"] == digest(result)
            and t["returned_in_request"] == (None if suppressed and i == 2 else i + 2), "TOOL_RESULT_BINDING")
        for kind in ("TOOL_RESERVED", "TOOL_RESULT_READY", "SUCCESS_WITHHELD" if suppressed and i == 2 else "SUCCESS_RELEASED"):
            matches = [e for e in events if e["kind"] == kind and e.get("call_id") == t["call_id"]]
            require(len(matches) == 1 and matches[0]["name"] == t["name"], "TOOL_EVENT_BINDING")
        order = [next(e["seq"] for e in events if e["kind"] == kind and e.get("call_id") == t["call_id"])
                 for kind in ("TOOL_RESERVED", "TOOL_RESULT_READY", "SUCCESS_WITHHELD" if suppressed and i == 2 else "SUCCESS_RELEASED")]
        reserve = next(e["seq"] for e in events if e["kind"] == "HTTP_RESERVED" and e["http_seq"] == i + 3)
        complete = next(e["seq"] for e in events if e["kind"] == "HTTP_COMPLETED" and e["http_seq"] == i + 3)
        require(order[0] < reserve < complete < order[1] < order[2], "TOOL_HTTP_ORDER")
    activations = [e for e in events if e["kind"] == "SUCCESS_WITHHELD"]
    inhibits = [e for e in events if e["kind"] == "FAULT_INHIBITED"]
    require(len(activations) == int(suppressed) and len(inhibits) == int(candidate == CANDIDATES[1]), "ACTIVATION_COUNT")
    if suppressed:
        a = activations[0]
        require(a["http_seq"] == 5 and a["channel"] == "EXPLICIT_TOOL_DELIVERY_ERROR", "ACTUATOR_SOURCE")
        require(not any(e["kind"] == "SUCCESS_RELEASED" and e.get("call_id") == trace[2]["call_id"] for e in events), "FALSE_SUCCESS_ACK")
        observed = [e for e in events if e["kind"] == "SDK_ERROR_OBSERVED"]
        require(len(observed) == 1 and observed[0]["seq"] > a["seq"] and observed[0]["seq"] <
                next(e["seq"] for e in events if e["kind"] == "HTTP_RESERVED" and e["http_seq"] == 6), "SDK_OBSERVATION_ORDER")
        require(observed[0]["returncode"] == 1 and observed[0]["status"] == "SDK_ERROR"
            and observed[0]["error_type"] == "RuntimeError", "SDK_OBSERVATION_FIELDS")
    elif inhibits:
        ready = next(e["seq"] for e in events if e["kind"] == "TOOL_RESULT_READY" and e["call_id"] == trace[2]["call_id"])
        released = next(e["seq"] for e in events if e["kind"] == "SUCCESS_RELEASED" and e["call_id"] == trace[2]["call_id"])
        require(inhibits[0]["reason"] == "PRE_REGISTERED_GATE_DISABLED" and ready < inhibits[0]["seq"] < released, "INHIBITION_REASON")
    completions = s["completions"]
    require(len(completions) == (3 if suppressed else 4), "COMPLETIONS")
    for i, completion in enumerate(completions):
        require(set(completion) == {"response_id", "model", "tool_calls", "usage", "request_sha256", "tool_returns"}
            and completion["model"] == "rpf53-fixture-only"
            and completion["usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "COMPLETION_SOURCE")
        require(completion["tool_returns"] == [{"call_id": t["call_id"], "result_sha256": t["result_sha256"]}
                for t in trace[:i]], "SDK_RETURN_INJECTION")
        calls = completion["tool_calls"]
        require(len(calls) == (1 if i < 3 else 0), "SDK_INTENT_COUNT")
        if calls:
            t = trace[i]
            require(calls[0] == {"call_id": t["call_id"], "name": t["name"], "arguments_sha256": t["arguments_sha256"]}
                    and completion["response_id"] == t["provider_response_id"], "SDK_INTENT_BINDING")
    sdk = s["sdk"]
    require(set(sdk) == {"popen_pid", "ready", "report", "returncode", "stderr_bytes", "identity"}, "SDK_FIELDS")
    require(type(sdk["popen_pid"]) is int and sdk["popen_pid"] > 0 and sdk["ready"]["pid"] == sdk["popen_pid"]
        and sdk["ready"]["version"] == "2.57.0" and sdk["ready"]["openai_version"] == "3.35.1"
        and sdk["ready"]["sdk_source_sha256"] == SDK_CORE_SHA256 and sdk["stderr_bytes"] == 0, "SDK_PID_SOURCE")
    identity = sdk["identity"]
    pinned = pinned_sdk_fields()
    require(all(identity.get(k) == value for k, value in pinned.items() if not k.startswith(("pydantic_", "openai_record_")))
        and all(identity[name].get(field) == pinned[name + "_" + field]
            for name in ("pydantic", "openai") for field in ("record_sha256", "record_entries", "record_mismatches")), "PINNED_SDK_IDENTITY")
    require(identity["python_version"] == "3.12.13" and identity["pydantic"]["record_mismatches"] == 0
        and identity["pydantic"]["record_entries"] == 444 and identity["openai"]["record_entries"] == 2000
        and identity["openai"]["record_mismatches"] == 0, "SDK_RECORD")
    for name in ("python_executable_sha256", "sdk_site_root_binding_sha256", "python_runtime_mapping_sha256"):
        require(sdk["ready"][name] == identity[name], "SDK_IDENTITY_BINDING")
    require(sdk["ready"]["openai_source_sha256"] == identity["openai_core_sha256"], "OPENAI_SOURCE")
    report = sdk["report"]
    if suppressed:
        require(report["status"] == "SDK_ERROR" and report["stage"] == "sdk_run"
            and report["error_type"] == "RuntimeError" and report["guard_code"] is None
            and report["guard_denials"] == [] and sdk["returncode"] == 1, "SDK_SUPPRESSION_OBSERVED")
    else:
        require(report["status"] == "COMPLETED" and report["pid"] == sdk["popen_pid"]
            and report["tool_callbacks"] == report["tool_calls"] == 3 and report["requests"] == 4
            and report["guard_denials"] == [] and report["provider_key_present"] is False
            and report["business_key_present"] is False and sdk["returncode"] == 0, "SDK_CALLBACK_REPORT")
    env = s["environment"]
    require(set(env) == {"source_level", "authority", "java_pid", "listener_owned", "jar_sha256",
        "jar_bytes", "jar_command_verified", "health", "cleanup"}, "ENV_FIELDS")
    require(env["source_level"] == "REAL_JAVA_H2_LOCAL_SIMULATION" and env["authority"] == "SAME_SERVICE_READ_ONLY_HTTP"
        and type(env["java_pid"]) is int and env["java_pid"] > 0 and env["listener_owned"] is True
        and env["jar_command_verified"] is True and env["jar_sha256"] == SOURCE_JAR_SHA256
        and env["jar_bytes"] == 66981576, "AUTHORITY_JAVA_SOURCE")
    require(1 <= len(env["health"]) <= 3 and env["health"][-1]["status"] == 200
        and env["health"][-1]["body"] == {"status": "UP"}, "HEALTH")
    require(env["cleanup"] == {"java_exited": True, "java_port_closed": True,
        "sdk_exited": True, "host_port_closed": True, "host_thread_stopped": True,
        "local_key_released": True}, "CLEANUP")

def verify_bytes(raw, anchor):
    require(anchor is not None, "EXTERNAL_ANCHOR_REQUIRED")
    require(hashlib.sha256(raw).hexdigest() == anchor, "EXTERNAL_ANCHOR_MISMATCH")
    envelope = strict_json(raw)
    require(type(envelope) is dict and set(envelope) == {"schema", "plan_revision", "verifier_identity", "payload", "payload_sha256"}
        and envelope["plan_revision"] == "rev-2" and envelope["verifier_identity"] == verifier_identity()
        and envelope["schema"] == EVIDENCE_SCHEMA and envelope["payload_sha256"] == digest(envelope["payload"]), "ENVELOPE")
    p = envelope["payload"]
    require(set(p) == {"source_kind", "source_files", "boundaries", "scenes", "budget"}
        and p["source_kind"] in ("SYNTHETIC_TEST_ONLY", "FIXTURE_TARGET_CONTROLLED_JAVA_HTTP")
        and p["boundaries"] == BOUNDARIES, "SOURCE_OR_BOUNDARIES")
    source_version = validate_execution_source(p["source_files"])
    require(len(p["scenes"]) == 3 and len({s["contracts"]["experiment"]["run_id"] for s in p["scenes"]}) == 3
        and len({s["contracts"]["effect"]["key"] for s in p["scenes"]}) == 3, "SCENE_ISOLATION")
    for s, candidate in zip(p["scenes"], CANDIDATES):
        verify_scene(s, candidate, digest(p["source_files"]))
    require(p["budget"] == {"jvm": 3, "business_http": 24, "post": 6,
        "health": sum(len(s["environment"]["health"]) for s in p["scenes"]), "provider": 0, "tokens": 0, "cost_cny": 0}, "TOTAL_BUDGET")
    return {"status": "PASS", "source_kind": p["source_kind"], "execution_source_identity": source_version,
            "verifier_identity": verifier_identity(), "PGE_CLOSED_LOOP": "NOT_PROVEN"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    if args.sha256 is None:
        print("EXTERNAL_ANCHOR_REQUIRED")
        return 2
    try:
        result = verify_bytes(args.path.read_bytes(), args.sha256)
        print(canonical(result).decode())
        return 0
    except Exception as exc:
        print(getattr(exc, "code", "INVALID_EVIDENCE"))
        return 3

if __name__ == "__main__":
    raise SystemExit(main())

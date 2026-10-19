"""RPF-55 complete synthetic envelope and re-anchored semantic controls; no Java."""
from __future__ import annotations
import copy
import hashlib
import subprocess
import sys
import unittest
from pathlib import Path
from runtime.runproof_runtime.effectwitness import config_experiment_contracts as c
from runtime.runproof_runtime.effectwitness import config_experiment_verify as v
from runtime.runproof_runtime.effectwitness.config_experiment_adapter import Journal, ExperimentHost
from runtime.runproof_runtime.effectwitness.config_live_runtime import ConfigLiveMemoryBackend, ProviderLedger
from runtime.runproof_runtime.effectwitness.config_live_runtime import _http_contract

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".local/rpf-55-rev2/tests"

def synthetic_scene(candidate, index, sources):
    contracts = c.make_contracts(candidate, "55r2" + (str(index) * 16), 45000 + index, 46000 + index, c.digest(sources))
    run = contracts["experiment"]["run_id"]
    effect = contracts["effect"]
    suppressed = candidate == c.CANDIDATES[2]
    journal = Journal(None, run)
    journal.add("PRE_REGISTERED", candidate=candidate)
    observations, trace, completions = [], [], []
    def item(version, history=False):
        row = {k: effect[k] for k in ("app", "env", "key")}
        row.update(value="rpf53-v" + str(version), version=version, description=None)
        row.update({"action": "UPSERT", "operator": None, "reason": None,
                    "createdAt": "2026-10-19T00:00:00Z"} if history else
                   {"updatedAt": "2026-10-19T00:00:00Z"})
        return row
    kinds = ["initial_current", "initial_history", "inspect_config", "create_config_v1", "update_config_v2"]
    kinds += ["reconcile_current", "reconcile_history", "final_list"] if suppressed else ["final_current", "final_history", "final_list"]
    for seq, kind in enumerate(kinds, 1):
        tool = 3 <= seq <= 5
        call_id = "synthetic-call-" + str(seq)
        if tool:
            journal.add("TOOL_RESERVED", name=kind, call_id=call_id)
        method, path, body = _http_contract(effect, kind)
        journal.add("HTTP_RESERVED", http_seq=seq, method=method, operation=kind)
        absent = kind in ("initial_current", "inspect_config")
        data = (None if absent else [] if kind == "initial_history" else
                [item(2, True), item(1, True)] if kind.endswith("history") else
                [item(2)] if kind == "final_list" else item(1 if seq == 4 else 2))
        response = {"code": 4041 if absent else 0, "message": "synthetic", "data": data, "traceId": None}
        o = {"seq": seq, "kind": kind, "method": method, "path": path, "request": body,
            "status": 404 if absent else 200, "content_type": "application/json", "response": response,
            "response_body_sha256": c.digest(response), "elapsed_ms": 0, "transport_error": None}
        observations.append(o)
        journal.add("HTTP_COMPLETED", http_seq=seq, status=o["status"], code=response["code"])
        if tool:
            i = seq - 3
            args = ({}, {"value": "rpf53-v1"}, {"expected_version": 1, "value": "rpf53-v2"})[i]
            result = {"state": "ABSENT"} if i == 0 else {"status": "COMMITTED", "version": i, "value": "rpf53-v" + str(i)}
            journal.add("TOOL_RESULT_READY", call_id=call_id, name=kind)
            t = {"sequence": i + 1, "provider_response_id": "synthetic-completion-" + str(i),
                "call_id": call_id, "name": kind, "arguments": args, "arguments_sha256": c.digest(args),
                "result": result, "result_sha256": c.digest(result), "http_observation_seq": seq,
                "returned_in_request": None if suppressed and i == 2 else i + 2}
            trace.append(t)
            completions.append({"response_id": t["provider_response_id"], "tool_calls": [
                {k: t[k] for k in ("call_id", "name", "arguments_sha256")} ]})
            if suppressed and i == 2:
                journal.add("SUCCESS_WITHHELD", call_id=call_id, name=kind, http_seq=seq, channel="EXPLICIT_TOOL_DELIVERY_ERROR")
                journal.add("SDK_ERROR_OBSERVED", returncode=1, status="SDK_ERROR", error_type="RuntimeError")
            else:
                if candidate == c.CANDIDATES[1] and i == 2:
                    journal.add("FAULT_INHIBITED", reason="PRE_REGISTERED_GATE_DISABLED")
                journal.add("SUCCESS_RELEASED", call_id=call_id, name=kind)
    if not suppressed:
        completions.append({"response_id": "synthetic-completion-3", "tool_calls": []})
    for i, completion in enumerate(completions):
        completion.update(model="rpf53-fixture-only", usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            request_sha256=c.digest({"synthetic_request": i}), tool_returns=[
                {"call_id": t["call_id"], "result_sha256": t["result_sha256"]} for t in trace[:i]])
    pinned = v.pinned_sdk_fields()
    identity = {k: value for k, value in pinned.items() if not k.startswith(("pydantic_", "openai_record_"))}
    identity.update({name: {field: pinned[name + "_" + field] for field in ("record_sha256", "record_entries", "record_mismatches")}
                    for name in ("pydantic", "openai")})
    ready = {"pid": 100 + index, "version": "2.57.0", "openai_version": "3.35.1",
        "sdk_source_sha256": v.SDK_CORE_SHA256, "openai_source_sha256": identity["openai_core_sha256"],
        **{k: identity[k] for k in ("python_executable_sha256", "sdk_site_root_binding_sha256", "python_runtime_mapping_sha256")}}
    report = {"status": "SDK_ERROR", "stage": "sdk_run", "error_type": "RuntimeError", "guard_code": None,
              "guard_denials": []} if suppressed else {"status": "COMPLETED", "pid": 100 + index,
              "tool_callbacks": 3, "tool_calls": 3, "requests": 4, "guard_denials": [],
              "provider_key_present": False, "business_key_present": False}
    return {"contracts": contracts, "contracts_sha256": c.digest(contracts), "http": observations,
        "events": journal.events, "tool_trace": trace, "completions": completions,
        "sdk": {"popen_pid": 100 + index, "ready": ready, "report": report,
            "returncode": 1 if suppressed else 0, "stderr_bytes": 0, "identity": identity},
        "environment": {"source_level": "REAL_JAVA_H2_LOCAL_SIMULATION", "authority": "SAME_SERVICE_READ_ONLY_HTTP",
            "java_pid": 200 + index, "listener_owned": True, "jar_sha256": v.SOURCE_JAR_SHA256,
            "jar_bytes": 66981576, "jar_command_verified": True, "health": [{"status": 200, "body": {"status": "UP"}}],
            "cleanup": {"java_exited": True, "java_port_closed": True, "sdk_exited": True,
                "host_port_closed": True, "host_thread_stopped": True, "local_key_released": True}},
        "fault": {"planned": candidate != "normal", "triggered": suppressed, "observed": suppressed,
            "channel": "EXPLICIT_TOOL_DELIVERY_ERROR" if suppressed else "NONE"},
        "outcome": {"agent_failure": "NOT_EVALUATED_FIXTURE", "platform_error": "EXPECTED_DELIVERY_ERROR" if suppressed else "NONE",
            "business_violation": False, "contract_outcome": "SATISFIED", "reconcile": "READ_ONLY_CONFIRMED" if suppressed else "NOT_REQUIRED",
            "target_ack": "UNKNOWN_OUTCOME" if suppressed else "RECEIVED"}}

def synthetic_payload():
    sources = v.source_identity()
    return {"source_kind": "SYNTHETIC_TEST_ONLY", "source_files": sources, "boundaries": c.BOUNDARIES,
        "scenes": [synthetic_scene(k, i, sources) for i, k in enumerate(c.CANDIDATES, 1)],
        "budget": {"jvm": 3, "business_http": 24, "post": 6, "health": 3, "provider": 0, "tokens": 0, "cost_cny": 0}}

def tamper_mutations():
    def history(p):
        s = p["scenes"][2]
        o = s["http"][6]
        o["response"]["data"][0]["env"] = p["scenes"][0]["contracts"]["effect"]["env"]
        o["response_body_sha256"] = c.digest(o["response"])
    return {"false_trigger": lambda p: p["scenes"][0]["fault"].update(triggered=True),
        "namespace_splice": history,
        "duplicate_post": lambda p: p["scenes"][2]["http"].append(copy.deepcopy(p["scenes"][2]["http"][4])),
        "authority": lambda p: p["scenes"][0]["environment"].update(authority="DATABASE_INDEPENDENT"),
        "cleanup": lambda p: p["scenes"][2]["environment"]["cleanup"].update(java_port_closed=False),
        "sdk_callbacks": lambda p: p["scenes"][0]["sdk"]["report"].update(tool_callbacks=2),
        "false_ack": lambda p: p["scenes"][2]["tool_trace"][2].update(returned_in_request=4)}

def offline_controls(raw, folder):
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "valid.json"
    path.write_bytes(raw)
    def cli(file, sha):
        args = [sys.executable, "-B", "-m", "runtime.runproof_runtime.effectwitness.config_experiment_verify", str(file)]
        if sha is not None:
            args.extend(["--sha256", sha])
        proc = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        return proc.returncode
    codes = [cli(path, hashlib.sha256(raw).hexdigest()), cli(path, None), cli(path, "0" * 64)]
    c.require(codes == [0, 2, 3], "CLI_CODES")
    rejected = {}
    payload = c.strict_json(raw)["payload"]
    for name, mutate in tamper_mutations().items():
        p = copy.deepcopy(payload)
        mutate(p)
        altered = c.canonical(v.seal(p))
        target = folder / (name + ".json")
        target.write_bytes(altered)
        rejected[name] = cli(target, hashlib.sha256(altered).hexdigest())
    c.require(all(code == 3 for code in rejected.values()), "REHASHED_TAMPER_ACCEPTED")
    return {"correct_missing_wrong": codes, "rehashed_tamper": rejected}

class ExperimentTests(unittest.TestCase):
    def test_actuator_three_modes_and_replay(self):
        from runtime.tests.test_effectwitness_config_live import _contracts
        for candidate in c.CANDIDATES:
            with self.subTest(candidate=candidate):
                contracts = c.make_contracts(candidate, "55r2" + "a" * 16, 45001, 45002, "a" * 64)
                journal = Journal(None, contracts["experiment"]["run_id"])
                host = ExperimentHost(_contracts(fixture=True), ProviderLedger.fixture_only(journal.run_id),
                    ConfigLiveMemoryBackend(), contracts, journal)
                host.runtime = {}
                for i, (name, arguments) in enumerate(zip(c.TOOLS, ({}, {"value": "rpf53-v1"},
                        {"expected_version": 1, "value": "rpf53-v2"}))):
                    call = "test-" + str(i)
                    host.intents[call] = {"name": name, "arguments_sha256": c.digest(arguments), "response_id": "synthetic"}
                    body = {"call_id": call, "name": name, "arguments": arguments}
                    if i == 2 and candidate == c.CANDIDATES[2]:
                        with self.assertRaisesRegex(RuntimeError, "RPF55_LOCAL_DELIVERY_SUPPRESSED"):
                            host._tool(body)
                    else:
                        host._tool(body)
                self.assertEqual(host.activated, candidate == c.CANDIDATES[2])
                with self.assertRaises(RuntimeError):
                    host._tool(body)
                self.assertEqual(sum(e["kind"] == "SUCCESS_WITHHELD" for e in journal.events), int(host.activated))

    def test_complete_synthetic(self):
        raw = c.canonical(v.seal(synthetic_payload()))
        self.assertEqual(v.verify_bytes(raw, hashlib.sha256(raw).hexdigest())["status"], "PASS")

    def test_rehashed_tampering(self):
        for name, mutate in tamper_mutations().items():
            with self.subTest(name=name):
                p = synthetic_payload()
                mutate(p)
                raw = c.canonical(v.seal(p))
                with self.assertRaises(ValueError):
                    v.verify_bytes(raw, hashlib.sha256(raw).hexdigest())

    def test_strict_contracts(self):
        for section, key, value in (("experiment", "candidate_id", "dynamic"),
                ("execution", "endpoint", "https://example.invalid"),
                ("effect", "required_value", "wrong"), ("experiment", "fault", "TRIGGERED")):
            p = synthetic_payload()["scenes"][0]["contracts"]
            p[section][key] = value
            with self.assertRaises(ValueError):
                c.validate_contracts(p)

    def test_no_anchor(self):
        with self.assertRaises(ValueError):
            v.verify_bytes(b"{}", None)

    def test_source_identity_forgery(self):
        p = synthetic_payload()
        p["source_files"][v.SOURCE_FILES[0]] = "0" * 64
        raw = c.canonical(v.seal(p))
        with self.assertRaises(ValueError):
            v.verify_bytes(raw, hashlib.sha256(raw).hexdigest())

    def test_fault_plan_cannot_enable_normal(self):
        p = synthetic_payload()["scenes"][0]["contracts"]
        p["experiment"]["fault_plan"]["enabled"] = True
        with self.assertRaises(ValueError):
            c.validate_contracts(p)

    def test_missing_binding_rejected_before_jvm(self):
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location("rpf55_cold_process", ROOT / "spikes/rpf-55/probe.py")
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        with patch.object(probe.subprocess, "Popen") as popen:
            with self.assertRaises(KeyError):
                probe.scenario({}, {})
            popen.assert_not_called()

    def test_rev1_not_reinterpreted(self):
        raw = (ROOT / "spikes/rpf-55/experiment-summary.json").read_bytes()
        old = c.strict_json(raw)["scenes"][0]["capture"]["contracts"]
        with self.assertRaises(ValueError):
            c.validate_contracts(old)
        p = synthetic_payload()
        p["scenes"][0]["contracts"] = old
        raw = c.canonical(v.seal(p))
        with self.assertRaises(ValueError):
            v.verify_bytes(raw, hashlib.sha256(raw).hexdigest())

    def test_output_status_is_separate_from_source(self):
        import runpy
        probe = runpy.run_path(str(ROOT / "spikes/rpf-55/probe.py"))
        before = v.source_identity()
        probe["validate_status"]([(" M", "spikes/rpf-55/probe.py"),
            ("??", "spikes/rpf-55/rev-2/experiment-summary.json"), ("??", "docs/reviews/")])
        self.assertEqual(before, v.source_identity())
        for row in ((" M", "runtime/runproof_runtime/effectwitness/config_live_runtime.py"),
                    ("M ", "spikes/rpf-55/probe.py"), ("??", "spikes/rpf-55/rev-2/unapproved.json")):
            with self.assertRaises(ValueError):
                probe["validate_status"]([row])
        self.assertFalse(any(p.startswith("spikes/rpf-55/rev-2/") for p in before))

    def test_health_projection_keeps_raw_without_disk_path(self):
        import runpy
        probe = runpy.run_path(str(ROOT / "spikes/rpf-55/probe.py"))
        raw = [{"status": 200, "transport_error": None, "body": {"status": "UP",
            "components": {"diskSpace": {"details": {"path": "private-local-path"}}}}}]
        preserved = copy.deepcopy(raw)
        projected = probe["health_projection"](raw)
        self.assertEqual(raw, preserved)
        self.assertEqual(projected[0]["body"], {"status": "UP"})
        self.assertEqual(projected[0]["raw_body_sha256"], c.digest(raw[0]["body"]))
        self.assertNotIn("private-local-path", c.canonical(projected).decode())

if __name__ == "__main__":
    unittest.main()

"""RPF-56 synthetic full-envelope, physical budget, lineage and tamper tests."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
from runtime.runproof_runtime.effectwitness import config_pge_contracts as c, config_pge_verify as v, config_pge_explorer as explorer
from runtime.runproof_runtime.effectwitness.config_pge_session import TotalLedger,Journal,feedback,validate_budget
from runtime.runproof_runtime.effectwitness.config_pge_target import TargetHost
from runtime.runproof_runtime.effectwitness.config_live_runtime import ConfigLiveMemoryBackend,ProviderLedger
from runtime.tests.test_effectwitness_config_experiment import synthetic_scene as primitive_scene

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/".local/rpf-56/tests"

def synthetic_trial(contracts,index,source):
    # Reuse ONLY the pure synthetic HTTP/event generator, never a prior artifact.
    candidate=contracts["experiment"]["candidate_id"]
    t=primitive_scene(candidate,index,source)
    previous=t["contracts"]
    text=c.canonical(t).decode()
    for key in ("app","env","key"):
        text=text.replace(previous["effect"][key],contracts["effect"][key])
    text=text.replace(previous["experiment"]["run_id"],contracts["experiment"]["run_id"])
    t=c.strict_json(text.encode());t["contracts"]=contracts;t["contracts_sha256"]=c.digest(contracts)
    for obs in t["http"]:obs["response_body_sha256"]=c.digest(obs["response"])
    requests=[]
    for i,comp in enumerate(t["completions"]):
        response_id=f"synthetic-target-r{index}-c{i}"
        comp.update(response_id=response_id,model="DeepSeek-V4.1-Flash-1017",usage={"prompt_tokens":100,"completion_tokens":10,"total_tokens":110})
        if i<3:t["tool_trace"][i]["provider_response_id"]=response_id
        requests.append({"attempt":i+1,"request_sha256":comp["request_sha256"],"response_id":response_id,
            "returned_model":comp["model"],"usage":comp["usage"],"status":"RECEIVED"})
    t["target_requests"]=requests
    t["sdk"].pop("identity")
    suppressed=candidate==c.CANDIDATES[2]
    t["outcome"]={"agent_failure":"NOT_DETERMINED","platform_error":"EXPECTED_TOOL_DELIVERY_ERROR" if suppressed else "NONE",
        "contract_outcome":"SATISFIED","business_violation":"NOT_PROVEN","target_ack":"UNKNOWN_OUTCOME" if suppressed else "RECEIVED",
        "read_only_reconcile":"CONFIRMED_V2" if suppressed else "NOT_REQUIRED"}
    return t

def synthetic_payload(choices=("normal","local-delivery-suppressed")):
    sources=v.source_identity()
    plan=c.session_plan("rpf56-session-"+"a"*16,[("56"+"1"*16,45001,46001),("56"+"2"*16,45002,46002)],sources,v.pinned_sdk_fields())
    ledger={"session_id":plan["session_id"],"plan_sha256":c.digest(plan),"requests":[],"trials":[],"posts":[],"started_monotonic_ns":1}
    rounds=[];journal=Journal(None,plan["session_id"]);messages=explorer.initial_messages();signatures=[]
    for index,candidate in enumerate(choices,1):
        body=explorer.body_for(messages)
        event=journal.add("PROVIDER_INPUT_FROZEN",round=index,body_sha256=c.digest(body))
        call={"id":f"synthetic-explorer-{index}","type":"function","function":{"name":"select_experiment","arguments":c.canonical({"candidate_id":candidate}).decode()}}
        attempt=len(ledger["requests"])+1
        ledger["requests"].append({"attempt":attempt,"role":"EXPLORER","round":index,"request_sha256":c.digest(body),"reservation_tokens":6000,
            "status":"RECEIVED","usage":{"prompt_tokens":200,"completion_tokens":20,"total_tokens":220},
            "response_id":f"synthetic-explorer-response-{index}","returned_model":"DeepSeek-V4.1-Flash-1017","selection":call})
        t=synthetic_trial(plan["rounds"][index-1]["candidates"][candidate],index,sources)
        for request in t["target_requests"]:
            global_attempt=len(ledger["requests"])+1;request["global_attempt"]=global_attempt
            ledger["requests"].append({"attempt":global_attempt,"role":"TARGET","round":index,"request_sha256":request["request_sha256"],
                "reservation_tokens":6000,"status":"RECEIVED","usage":request["usage"],"response_id":request["response_id"],"returned_model":request["returned_model"]})
        run=t["contracts"]["experiment"]["run_id"];ledger["trials"].append(run)
        ledger["posts"] += [{"run_id":run,"operation":op} for op in ("create_config_v1","update_config_v2")]
        fb=feedback(t);validated=journal.add("FEEDBACK_VALIDATED",round=index,feedback_sha256=c.digest(fb))
        rounds.append({"round":index,"request_body":body,"request_sha256":c.digest(body),"explorer_attempt":attempt,"selection":call,
            "trial":t,"feedback":fb,"feedback_sha256":c.digest(fb),"feedback_event_seq":validated["seq"],"input_event_seq":event["seq"]})
        messages += [{"role":"assistant","content":None,"tool_calls":[call]},{"role":"tool","tool_call_id":call["id"],"content":c.canonical(fb).decode()}]
        signatures.append(c.digest({"fault":t["fault"],"ack":t["outcome"]["target_ack"],"effect":"SATISFIED"}))
    return {"source_kind":"SYNTHETIC_TEST_ONLY","plan":plan,"plan_sha256":c.digest(plan),"rounds":rounds,"events":journal.events,"ledger":ledger,"limits":c.BOUNDARIES,
        "research":{"L1":"SYNTHETIC_ONLY","L2":signatures[0]!=signatures[1],"H1":"NOT_PROVEN","information_gain_proxy":int(signatures[0]!=signatures[1])}}

def mutations():
    def splice(p):
        o=p["rounds"][1]["trial"]["http"][6]
        o["response"]["data"][0]["env"]=p["rounds"][0]["trial"]["contracts"]["effect"]["env"]
        o["response_body_sha256"]=c.digest(o["response"])
    def change_selection(p):
        call=p["rounds"][0]["selection"]
        chosen=c.strict_json(call["function"]["arguments"].encode())["candidate_id"]
        alternative=next(n for n in c.CANDIDATES if n!=chosen)
        call["function"]["arguments"]=c.canonical({"candidate_id":alternative}).decode()
    return {"forged_selection":change_selection,
        "feedback_hash":lambda p:p["rounds"][1]["request_body"]["messages"][-1].update(content="{}"),
        "feedback_order":lambda p:p["rounds"][0].update(feedback_event_seq=p["rounds"][1]["input_event_seq"]),
        "split_role_budget":lambda p:p["ledger"]["requests"][1].update(role="EXPLORER"),
        "duplicate_post":lambda p:p["rounds"][1]["trial"]["http"].append(copy.deepcopy(p["rounds"][1]["trial"]["http"][4])),
        "false_trigger":lambda p:p["rounds"][0]["trial"]["fault"].update(triggered=not p["rounds"][0]["trial"]["fault"]["triggered"]),
        "namespace_splice":splice,
        "false_ack":lambda p:p["rounds"][1]["trial"]["tool_trace"][2].update(returned_in_request=(4 if p["rounds"][1]["trial"]["tool_trace"][2]["returned_in_request"] is None else None)),
        "source":lambda p:p["plan"]["source_files"].update({v.SOURCE_FILES[0]:"0"*64}),
        "sdk_pid":lambda p:p["rounds"][0]["trial"]["sdk"].update(popen_pid=999999),
        "cleanup":lambda p:p["rounds"][0]["trial"]["environment"]["cleanup"].update(java_exited=False)}

def offline_controls(raw,folder):
    folder.mkdir(parents=True,exist_ok=False)
    path=folder/"valid.json";path.write_bytes(raw)
    def cli(target,anchor):
        args=[sys.executable,"-B","-m","runtime.runproof_runtime.effectwitness.config_pge_verify",str(target)]
        if anchor is not None:args.extend(["--sha256",anchor])
        env={k:os.environ[k] for k in ("SYSTEMROOT","WINDIR","PATH") if k in os.environ}
        p=subprocess.run(args,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        return p.returncode
    codes=[cli(path,hashlib.sha256(raw).hexdigest()),cli(path,None),cli(path,"0"*64)]
    c.require(codes==[0,2,3],"OFFLINE_CLI_CODES")
    results={};payload=c.strict_json(raw)["payload"]
    for name,mutate in mutations().items():
        p=copy.deepcopy(payload);mutate(p)
        changed=c.canonical(v.seal(p));target=folder/(name+".json");target.write_bytes(changed)
        results[name]=cli(target,hashlib.sha256(changed).hexdigest())
    c.require(all(code==3 for code in results.values()),"TAMPER_ACCEPTED")
    return {"correct_missing_wrong":codes,"rehashed_tamper":results}

class ConfigPgeTests(unittest.TestCase):
    def plan(self):return synthetic_payload()["plan"]
    def new_ledger(self):
        WORK.mkdir(parents=True,exist_ok=True)
        return TotalLedger(WORK/("ledger-"+uuid.uuid4().hex),self.plan(),create=True)
    def test_full_success_and_no_information_gain(self):
        for choices in (("normal","local-delivery-suppressed"),("normal","normal"),("planned-but-inhibited","normal")):
            with self.subTest(choices=choices):
                p=synthetic_payload(choices);raw=c.canonical(v.seal(p))
                self.assertEqual(v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())["status"],"PASS")
                self.assertEqual(p["research"]["L2"],choices[0]!=choices[1])
    def test_rehashed_semantic_tamper(self):
        for name,mutate in mutations().items():
            with self.subTest(name=name):
                p=synthetic_payload();mutate(p);raw=c.canonical(v.seal(p))
                with self.assertRaises((ValueError,KeyError,IndexError)):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
    def test_unknown_usage_restart_no_reset(self):
        ledger=self.new_ledger();ledger.reserve_request("EXPLORER",1,{"max_tokens":128})
        reopened=TotalLedger(ledger.path,self.plan())
        with self.assertRaisesRegex(ValueError,"USAGE_UNKNOWN"):reopened.reserve_request("TARGET",1,{})
        with self.assertRaises(FileExistsError):TotalLedger(ledger.path,self.plan(),create=True)
        with self.assertRaisesRegex(ValueError,"USAGE_UNKNOWN"):reopened.received(1,{"id":"test","model":c.MODEL,"usage":None})
    def test_torn_record_and_collision(self):
        ledger=self.new_ledger();(ledger.path/"mutation.lock").write_bytes(b"exclusive")
        with self.assertRaisesRegex(ValueError,"COLLISION"):ledger.reserve_request("EXPLORER",1,{})
        (ledger.path/"mutation.lock").unlink()
        (ledger.path/"snapshot-0001.json").write_bytes(b'{"torn":')
        with self.assertRaises(ValueError):TotalLedger(ledger.path,self.plan())
    def test_post_and_jvm_are_not_refundable(self):
        ledger=self.new_ledger();run=self.plan()["rounds"][0]["run_id"]
        ledger.reserve_trial(run);ledger.reserve_post(run,"create_config_v1")
        other=TotalLedger(ledger.path,self.plan())
        with self.assertRaises(ValueError):other.reserve_trial(run)
        with self.assertRaises(ValueError):other.reserve_post(run,"create_config_v1")
        self.assertEqual(len(other.read()["posts"]),1)
    def test_budget_overrun(self):
        p=synthetic_payload();s=p["ledger"]
        s["requests"]*=2
        with self.assertRaises(ValueError):validate_budget(s)
        ledger=self.new_ledger()
        with self.assertRaises(ValueError):ledger.reserve_request("EXPLORER",1,{"huge":"x"*30000})
    def test_scope_and_old_envelopes_rejected(self):
        p=self.plan();p["catalog"].append("arbitrary-endpoint")
        with self.assertRaises(ValueError):c.validate_plan(p)
        for name in ("spikes/rpf-55/rev-2/config-experiment-evidence.json","spikes/rpf-53/rev-6/config-live-evidence.json"):
            raw=(ROOT/name).read_bytes()
            with self.assertRaises(ValueError):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
    def test_two_processes_cannot_double_reserve(self):
        ledger=self.new_ledger()
        code="""import sys,json;from pathlib import Path
from runtime.runproof_runtime.effectwitness.config_pge_session import TotalLedger
p=json.loads(sys.stdin.read());t=TotalLedger(Path(p['path']),p['plan'])
try:t.reserve_request('EXPLORER',1,{});print('RESERVED')
except Exception:print('REJECTED')
"""
        env={k:os.environ[k] for k in ("SYSTEMROOT","WINDIR","PATH") if k in os.environ}
        children=[subprocess.Popen([sys.executable,"-B","-c",code],cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        outputs=[p.communicate(json.dumps({"path":str(ledger.path),"plan":self.plan()}).encode(),timeout=30) for p in children]
        self.assertTrue(all(not err for out,err in outputs))
        self.assertEqual(sum(b"RESERVED" in out for out,err in outputs),1)
        self.assertEqual(len(ledger.read()["requests"]),1)
    def test_fixture_host_cannot_use_provider(self):
        p=self.plan();t=copy.deepcopy(p["rounds"][0]["candidates"]["normal"])
        t=c.trial_contract("normal",t["experiment"]["suffix"],45001,46001,c.digest(p["source_files"]),v.pinned_sdk_fields(),fixture=True)
        host=TargetHost(t,ProviderLedger.fixture_only("synthetic"),ConfigLiveMemoryBackend(),Journal(None,t["experiment"]["run_id"]),fixture=True)
        with self.assertRaises(ValueError):host._provider_request({})
    def test_input_freeze_does_not_alias_future_feedback(self):
        messages=explorer.initial_messages();body=explorer.body_for(messages);original=c.digest(body)
        messages.append({"role":"tool","tool_call_id":"future","content":"not-yet-observed"})
        self.assertEqual(c.digest(body),original)
        self.assertEqual(len(body["messages"]),2)
    def test_tamper_controls_are_not_noops_on_repeated_candidates(self):
        for first in c.CANDIDATES:
            for second in c.CANDIDATES:
                original=synthetic_payload((first,second))
                for name,mutate in mutations().items():
                    with self.subTest(first=first,second=second,control=name):
                        p=copy.deepcopy(original);mutate(p)
                        self.assertNotEqual(c.canonical(original),c.canonical(p))
    def test_export_scope_and_dynamic_outputs_do_not_change_source(self):
        import runpy
        from unittest.mock import patch
        probe=runpy.run_path(str(ROOT/"spikes/rpf-56/probe.py"))
        with patch.object(probe["old"],"_git",side_effect=[b"?? docs/reviews/\0?? spikes/rpf-56/\0","spikes/rpf-56/probe.py"]):
            probe["status_check"]()
        with patch.object(probe["old"],"_git",return_value=b"M  runtime/runproof_runtime/effectwitness/config_live_runtime.py\0"):
            with self.assertRaises(ValueError):probe["status_check"]()
        WORK.mkdir(parents=True,exist_ok=True)
        before=v.source_identity()
        probe["once"](WORK/("export-test-"+uuid.uuid4().hex+".json"),{"test":"SYNTHETIC_TEST_ONLY"})
        self.assertEqual(before,v.source_identity())
        with self.assertRaises(ValueError):probe["once"](ROOT/"spikes/rpf-56/unapproved.json",{})

if __name__=="__main__":unittest.main()

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
from runtime.runproof_runtime.effectwitness import config_pge_coverage_contracts as c, config_pge_coverage_verify as v, config_pge_explorer as explorer
from runtime.runproof_runtime.effectwitness.config_pge_coverage_session import TotalLedger,Journal,validate_budget,TargetHost
from runtime.runproof_runtime.effectwitness.config_pge_coverage_policy import feedback,initial_messages,research,FACT_IDS,next_messages
from runtime.runproof_runtime.effectwitness.config_live_runtime import ConfigLiveMemoryBackend,ProviderLedger
from runtime.tests.test_effectwitness_config_experiment import synthetic_scene as primitive_scene

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/".local/rpf-57/tests"

from runtime.tests.test_effectwitness_config_pge import synthetic_trial,valid_response

def synthetic_payload(choices=("normal","local-delivery-suppressed")):
    sources=v.source_identity()
    plan=c.session_plan("rpf57-session-"+"a"*16,[("57"+"1"*16,45001,46001),("57"+"2"*16,45002,46002)],sources,v.pinned_sdk_fields(),c.digest({"owner":"rpf-57","sources":sources}))
    ledger={"session_id":plan["session_id"],"plan_sha256":c.digest(plan),"requests":[],"trials":[],"posts":[],"started_monotonic_ns":1}
    rounds=[];journal=Journal(None,plan["session_id"]);messages=initial_messages();coverage=None
    for index,candidate in enumerate(choices,1):
        body=explorer.body_for(messages)
        event=journal.add("PROVIDER_INPUT_FROZEN",round=index,body_sha256=c.digest(body))
        call={"id":f"synthetic-explorer-{index}","type":"function","function":{"name":"select_experiment","arguments":c.canonical({"candidate_id":candidate}).decode()}}
        attempt=len(ledger["requests"])+1
        ledger["requests"].append({"attempt":attempt,"role":"EXPLORER","round":index,"request_sha256":c.digest(body),"reservation_tokens":6000,
            "status":"RECEIVED","usage":{"prompt_tokens":200,"completion_tokens":20,"total_tokens":220},
            "response_id":f"synthetic-explorer-response-{index}","returned_model":"DeepSeek-V4.1-Flash-1017","selection":call})
        shape=explorer.safe_response_shape(valid_response(call,index))
        journal.add("RESPONSE_SHAPE_PERSISTED",round=index,shape_sha256=c.digest(shape),request_sha256=c.digest(body))
        t=synthetic_trial(plan["rounds"][index-1]["candidates"][candidate],index,sources)
        for request in t["target_requests"]:
            global_attempt=len(ledger["requests"])+1;request["global_attempt"]=global_attempt
            ledger["requests"].append({"attempt":global_attempt,"role":"TARGET","round":index,"request_sha256":request["request_sha256"],
                "reservation_tokens":6000,"status":"RECEIVED","usage":request["usage"],"response_id":request["response_id"],"returned_model":request["returned_model"]})
        run=t["contracts"]["experiment"]["run_id"];ledger["trials"].append(run)
        ledger["posts"] += [{"run_id":run,"operation":op} for op in ("create_config_v1","update_config_v2")]
        fb=feedback(t,coverage);coverage=fb["coverage"];validated=journal.add("FEEDBACK_VALIDATED",round=index,feedback_sha256=c.digest(fb))
        rounds.append({"round":index,"request_body":body,"request_sha256":c.digest(body),"explorer_attempt":attempt,"selection":call,
            "trial":t,"feedback":fb,"feedback_sha256":c.digest(fb),"feedback_event_seq":validated["seq"],"input_event_seq":event["seq"],"response_shape":shape})
        messages=next_messages(messages,call,fb)
    return {"source_kind":"SYNTHETIC_TEST_ONLY","plan":plan,"plan_sha256":c.digest(plan),"rounds":rounds,"events":journal.events,"ledger":ledger,"task_budget":{"mode":"UNIFIED_TASK_SESSION_LEDGER","ledger_sha256":c.digest(ledger)},"limits":c.BOUNDARIES,
        "research":research(rounds,"SYNTHETIC_TEST_ONLY")}

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
        args=[sys.executable,"-B","-m","runtime.runproof_runtime.effectwitness.config_pge_coverage_verify",str(target)]
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


def coverage_mutations():
    return {"future_fact":lambda p:p["rounds"][0]["feedback"]["coverage"]["seen_fact_ids_before"].append("ack_unknown_reconciled"),
        "unknown_fact":lambda p:p["rounds"][1]["feedback"]["coverage"]["new_fact_ids"].append("unverified"),
        "missing_readback":lambda p:p["rounds"][0]["trial"]["http"].pop(),
        "wrong_authority":lambda p:p["rounds"][0]["trial"]["environment"].update(authority="AGENT_SELF_REPORT"),
        "novelty_overclaim":lambda p:p["research"].update(new_verified_fact_count=99),
        "pending_usage":lambda p:p["ledger"]["requests"][0].update(status="RESERVED_USAGE_UNKNOWN"),
        "parent_split":lambda p:p["task_budget"].update(ledger_sha256="0"*64)}

base_mutations=mutations
def mutations():return {**base_mutations(),**coverage_mutations()}

class CoverageTests(unittest.TestCase):
    def test_all_nine_pairs_and_repeated_negative_control(self):
        for first in c.CANDIDATES:
            for second in c.CANDIDATES:
                p=synthetic_payload((first,second));v.verify_payload(p)
                f1=p["rounds"][0]["feedback"]["coverage"];f2=p["rounds"][1]["feedback"]["coverage"]
                self.assertEqual(f1["seen_fact_ids_before"],[])
                self.assertEqual(f2["new_fact_ids"],sorted(set(f2["verified_fact_ids"])-set(f1["seen_fact_ids_after"])))
                self.assertEqual(p["research"]["candidate_changed"],first!=second)
                if first==second:self.assertEqual(f2["new_fact_ids"],[])
    def test_all_pair_semantic_rehash_controls(self):
        for first in c.CANDIDATES:
            for second in c.CANDIDATES:
                original=synthetic_payload((first,second))
                for name,mutate in mutations().items():
                    with self.subTest(first=first,second=second,control=name):
                        p=copy.deepcopy(original);mutate(p)
                        self.assertNotEqual(c.canonical(original),c.canonical(p))
                        raw=c.canonical(v.seal(p))
                        with self.assertRaises((ValueError,KeyError,IndexError)):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
    def plan(self):return synthetic_payload()["plan"]
    def ledger(self):
        WORK.mkdir(parents=True,exist_ok=True)
        return TotalLedger(WORK/("ledger-"+uuid.uuid4().hex),self.plan(),create=True)
    def test_unknown_reservation_restart_and_exclusive_lock(self):
        t=self.ledger();t.reserve_request("EXPLORER",1,{})
        t2=TotalLedger(t.path,self.plan())
        with self.assertRaisesRegex(ValueError,"USAGE_UNKNOWN"):t2.reserve_request("EXPLORER",2,{})
        (t.path/"mutation.lock").write_bytes(b"LOCK")
        with self.assertRaisesRegex(ValueError,"COLLISION"):t.mutate(lambda s:None)
        self.assertEqual(t.read()["requests"][0]["status"],"RESERVED_USAGE_UNKNOWN")
    def test_corrupt_ledger_and_duplicate_post(self):
        t=self.ledger();run=self.plan()["rounds"][0]["run_id"];t.reserve_trial(run);t.reserve_post(run,"create_config_v1")
        with self.assertRaises(ValueError):t.reserve_post(run,"create_config_v1")
        self.assertEqual(len(t.read()["posts"]),1)
        (t.path/"snapshot-0000.json").write_bytes(b"{")
        with self.assertRaises(ValueError):TotalLedger(t.path,self.plan())
    def test_request_role_token_cost_limits(self):
        t=self.ledger()
        for role in ("PROTOCOL_PROBE_ONLY","INVALID"):
            with self.assertRaises(ValueError):t.reserve_request(role,1,{})
        with self.assertRaises(ValueError):t.reserve_request("EXPLORER",1,{"too_big":"x"*21000})
        p=synthetic_payload();p["ledger"]["requests"]*=2
        with self.assertRaises(ValueError):validate_budget(p["ledger"])
    def test_old_schema_source_and_non_task_root_rejected(self):
        raw=(ROOT/"spikes/rpf-56/rev-4/config-pge-evidence.json").read_bytes()
        with self.assertRaises(ValueError):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError):TotalLedger(ROOT/".local/rpf-56-rev4/NEVER_CREATED",self.plan(),create=True)
        with self.assertRaises(ValueError):Journal(ROOT/".local/rpf-56-rev4/NEVER_CREATED",self.plan()["session_id"])
    def test_invalid_or_missing_trial_emits_no_facts(self):
        t=synthetic_payload()["rounds"][0]["trial"]
        for mutate in (lambda t:t["http"].pop(),lambda t:t["fault"].update(observed=True),lambda t:t["outcome"].update(contract_outcome="UNKNOWN")):
            bad=copy.deepcopy(t);mutate(bad)
            with self.assertRaises(ValueError):feedback(bad)
    def test_body_freeze_and_full_legal_catalog(self):
        messages=initial_messages();body=explorer.body_for(messages);h=c.digest(body)
        messages.append({"role":"tool","content":"FUTURE"})
        self.assertEqual(c.digest(body),h)
        self.assertEqual(c.strict_json(body["messages"][1]["content"].encode())["catalog"],list(c.CANDIDATES))
    def test_trial_semantics_copy_matches_reviewed_verifier(self):
        import inspect
        from runtime.runproof_runtime.effectwitness import config_pge_verify as oldv
        self.assertEqual(inspect.getsource(v.verify_trial),inspect.getsource(oldv.verify_trial))
    def test_fixture_provider_forbidden(self):
        p=self.plan();t=c.trial_contract("normal","57"+"f"*16,45001,46001,c.digest(p["source_files"]),v.pinned_sdk_fields(),fixture=True)
        host=TargetHost(t,ProviderLedger.fixture_only("synthetic"),ConfigLiveMemoryBackend(),Journal(None,t["experiment"]["run_id"]),fixture=True)
        with self.assertRaises(ValueError):host._provider_request({})

    def test_synthetic_cannot_be_relabelled_real(self):
        p=synthetic_payload();p["source_kind"]="REAL_EXPLORER_REAL_TARGET_CONFIG_JAVA_HTTP"
        p["research"]=research(p["rounds"],p["source_kind"])
        with self.assertRaises(ValueError):v.verify_payload(p)

    def test_two_processes_cannot_double_reserve(self):
        ledger=self.ledger()
        code="""import sys,json;from pathlib import Path
from runtime.runproof_runtime.effectwitness.config_pge_coverage_session import TotalLedger
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

if __name__=="__main__":unittest.main()

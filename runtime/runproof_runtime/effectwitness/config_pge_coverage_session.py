"""RPF-57 durable global reservations. Immutable hash-chained snapshots, no refund."""
from __future__ import annotations
import copy
import os
import time
from pathlib import Path
from .config_pge_coverage_contracts import canonical, digest, strict_json, require, LIMITS, PRICE, validate_plan, validate_trial, BASE, BRANCH

class Journal:
    def __init__(self,path,run_id):
        self.path,self.run_id,self.events=path,run_id,[]
        if path is not None:
            root=Path(__file__).resolve().parents[3]/".local/rpf-57"
            require(path.resolve().is_relative_to(root.resolve()) and not any(p.is_symlink() or getattr(p,"is_junction",lambda:False)()
                for p in (path,*path.parents)),"JOURNAL_SCOPE")
            with path.open("xb"):pass
    def add(self,kind,**data):
        event={"seq":len(self.events)+1,"run_id":self.run_id,"monotonic_ns":time.monotonic_ns(),"kind":kind,**data}
        if self.path:
            with self.path.open("ab") as stream:
                stream.write(canonical(event)+b"\n");stream.flush();os.fsync(stream.fileno())
        self.events.append(event)
        return event

def validate_budget(state):
    require(set(state) == {"session_id", "plan_sha256", "requests", "trials", "posts", "started_monotonic_ns"}, "LEDGER_FIELDS")
    requests = state["requests"]
    require(len(requests) <= 10 and sum(r["role"] == "EXPLORER" for r in requests) <= 2
        and sum(r["role"] == "TARGET" for r in requests) <= 8, "REQUEST_BUDGET")
    require([r["attempt"] for r in requests] == list(range(1, len(requests) + 1)), "REQUEST_SEQUENCE")
    for index in (1,2):
        require(sum(r["role"]=="EXPLORER" and r["round"]==index for r in requests)<=1
            and sum(r["role"]=="TARGET" and r["round"]==index for r in requests)<=4,"ROUND_REQUEST_BUDGET")
    for r in requests:
        require(r["role"] in ("EXPLORER", "TARGET") and r["round"] in (1,2)
            and r["status"] in ("RESERVED_USAGE_UNKNOWN", "RECEIVED"), "ROLE_OR_STATUS")
        if r["status"] == "RECEIVED":
            u = r["usage"]
            require(type(u) is dict and set(u) == {"prompt_tokens", "completion_tokens", "total_tokens"}
                and all(type(v) is int and v >= 0 for v in u.values())
                and u["prompt_tokens"] + u["completion_tokens"] == u["total_tokens"] <= r["reservation_tokens"]
                and u["completion_tokens"] <= 256, "USAGE_INVALID")
    ids=[r["response_id"] for r in requests if r["status"]=="RECEIVED"]
    require(len(ids)==len(set(ids)),"PROVIDER_RESPONSE_REPLAY")
    reserved = sum(r["reservation_tokens"] for r in requests if r["status"] != "RECEIVED")
    received = [r["usage"] for r in requests if r["status"] == "RECEIVED"]
    total = sum(u["total_tokens"] for u in received)
    cost = sum(u["prompt_tokens"] * 4.5 + u["completion_tokens"] * 18 for u in received) / 1_000_000
    require(total + reserved <= 20000 and cost + reserved * 18 / 1_000_000 <= 0.50, "TOKEN_OR_COST_BUDGET")
    require(len(state["trials"]) <= 2 and len(set(state["trials"])) == len(state["trials"]), "JVM_BUDGET")
    require(len(state["posts"]) <= 4 and len({(p["run_id"],p["operation"]) for p in state["posts"]}) == len(state["posts"])
        and all(p["run_id"] in state["trials"] and p["operation"] in ("create_config_v1","update_config_v2") for p in state["posts"]), "POST_BUDGET_OR_REPLAY")
    return {"requests": len(requests), "tokens": total if reserved == 0 else None,
        "estimated_cost_cny_upper": cost if reserved == 0 else None, "usage_known": reserved == 0,
        "jvm": len(state["trials"]), "post": len(state["posts"])}

class TotalLedger:
    def __init__(self, path: Path, plan, *, create=False):
        validate_plan(plan)
        root = Path(__file__).resolve().parents[3] / ".local/rpf-57"
        require(path.is_absolute() and path.resolve().is_relative_to(root.resolve())
            and not any(p.is_symlink() or getattr(p,"is_junction",lambda:False)() for p in (path,*path.parents)), "LEDGER_SCOPE")
        self.path, self.plan = path, plan
        # One immutable ledger is BOTH task and session: no detached parent,
        # probe scope, refunds or second session. Target requests map into it.
        require(plan["task_budget_binding"] == digest({"owner":"rpf-57","sources":plan["source_files"]}), "TASK_BUDGET_BINDING")
        if create:
            path.mkdir(exist_ok=False)
            self._write({"session_id": plan["session_id"], "plan_sha256": digest(plan), "requests": [],
                "trials": [], "posts": [], "started_monotonic_ns": time.monotonic_ns()}, None, 0)
        self.read()

    def read(self):
        files = sorted(self.path.glob("snapshot-*.json"))
        require(bool(files), "LEDGER_MISSING")
        previous = None; prior_state = None
        for index, path in enumerate(files):
            require(not path.is_symlink() and not getattr(path,"is_junction",lambda:False)(),"LEDGER_LINK")
            value = strict_json(path.read_bytes())
            require(path.name == f"snapshot-{index:04}.json" and set(value) == {"seq","previous_sha256","state","sha256"}
                and value["seq"] == index and value["previous_sha256"] == previous
                and value["sha256"] == digest(value["state"]), "LEDGER_CHAIN_OR_TORN_RECORD")
            state = value["state"]
            require(state["session_id"] == self.plan["session_id"] and state["plan_sha256"] == digest(self.plan), "LEDGER_IDENTITY")
            validate_budget(state)
            if prior_state is not None:
                require(state["started_monotonic_ns"] == prior_state["started_monotonic_ns"], "LEDGER_TIME_REWRITE")
                for key in ("trials","posts"):
                    require(state[key][:len(prior_state[key])] == prior_state[key], "LEDGER_RESERVATION_REMOVED")
                require(len(state["requests"]) >= len(prior_state["requests"]), "LEDGER_REQUEST_REMOVED")
                for old,new in zip(prior_state["requests"],state["requests"]):
                    if old["status"] == "RECEIVED":
                        require(all(new.get(k)==val for k,val in old.items()), "LEDGER_RECEIPT_REWRITE")
                    else:
                        require(all(new[k]==old[k] for k in ("attempt","role","round","request_sha256","reservation_tokens")), "LEDGER_RESERVATION_REWRITE")
            prior_state=state
            previous = digest(value)
        self.state, self.previous, self.next_seq = state, previous, len(files)
        return copy.deepcopy(state)

    def _write(self, state, previous, seq):
        validate_budget(state)
        value = {"seq":seq,"previous_sha256":previous,"state":state,"sha256":digest(state)}
        with (self.path/f"snapshot-{seq:04}.json").open("xb") as stream:
            stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())

    def mutate(self, operation):
        lock = self.path / "mutation.lock"
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            require(False, "LEDGER_COLLISION_OR_UNCLEAN_RESTART")
        try:
            state = self.read()
            require(time.monotonic_ns() - state["started_monotonic_ns"] < 2400 * 1_000_000_000, "SESSION_DEADLINE")
            result = operation(state)
            self._write(state,self.previous,self.next_seq)
            self.read()
            return result
        finally:
            os.close(descriptor)
            lock.unlink()

    def reserve_request(self, role, round_index, body):
        def op(state):
            require(all(r["status"] == "RECEIVED" for r in state["requests"]), "USAGE_UNKNOWN")
            require(role in ("EXPLORER","TARGET") and round_index in (1,2), "REQUEST_ROLE")
            if role == "EXPLORER":
                require(not any(r["role"] == role and r["round"] == round_index for r in state["requests"]), "EXPLORER_REPLAY")
            else:
                require(sum(r["role"] == role and r["round"] == round_index for r in state["requests"]) < 4, "TARGET_REQUEST_LIMIT")
            record = {"attempt":len(state["requests"])+1,"role":role,"round":round_index,
                "request_sha256":digest(body),"reservation_tokens":len(canonical(body))+1024+256,
                "status":"RESERVED_USAGE_UNKNOWN","usage":None,"response_id":None,"returned_model":None}
            state["requests"].append(record)
            validate_budget(state)
            return record["attempt"]
        return self.mutate(op)

    def received(self, attempt, data):
        def op(state):
            record = state["requests"][attempt-1]
            require(record["status"] == "RESERVED_USAGE_UNKNOWN", "RESPONSE_REPLAY")
            usage = data.get("usage")
            require(type(usage) is dict and all(k in usage for k in ("prompt_tokens","completion_tokens","total_tokens")), "USAGE_UNKNOWN")
            require(type(data.get("id")) is str and data.get("model") in ("deepseek-flash","DeepSeek-V4.1-Flash-1017"), "PROVIDER_IDENTITY")
            require(data["id"] not in {r["response_id"] for r in state["requests"]}, "PROVIDER_RESPONSE_REPLAY")
            record.update(status="RECEIVED",usage={k:usage[k] for k in ("prompt_tokens","completion_tokens","total_tokens")},
                response_id=data["id"],returned_model=data["model"])
            validate_budget(state)
        self.mutate(op)

    def reserve_trial(self, run_id):
        def op(state):
            require(run_id in [r["run_id"] for r in self.plan["rounds"]] and run_id not in state["trials"], "TRIAL_REPLAY_OR_UNKNOWN")
            require(all(r["status"] == "RECEIVED" for r in state["requests"]), "USAGE_UNKNOWN")
            state["trials"].append(run_id)
        self.mutate(op)

    def selection(self,attempt,call):
        def op(state):
            record=state["requests"][attempt-1]
            require(record["role"]=="EXPLORER" and record["status"]=="RECEIVED" and "selection" not in record,"SELECTION_LEDGER_STATE")
            record["selection"]=call
        self.mutate(op)

    def reserve_post(self, run_id, operation):
        self.mutate(lambda state: state["posts"].append({"run_id":run_id,"operation":operation}))


from .config_pge_target import TargetHost as LegacyTargetHost, BusinessHttp as LegacyBusinessHttp, TargetLedger
from .config_live_runtime import ProviderLedger
class BusinessHttp(LegacyBusinessHttp):
    def __init__(self, contracts, api_key, journal, total, deadline):
        validate_trial(contracts)
        self.contracts,self.effect=contracts,contracts["effect"]
        self.port=contracts["execution"]["service"]["port"]
        self._api_key,self.journal,self.total,self.deadline=api_key,journal,total,deadline
        self.observations,self.post_count,self.stop_writes=[],0,False


class TargetHost(LegacyTargetHost):
    def __init__(self, contracts, ledger, business, journal, *, fixture=False, api_key=None):
        # This constructor validates the NEW owner/role/contracts. It neither
        # instantiates a legacy owner contract nor relaxes ExperimentHost's ban.
        validate_trial(contracts)
        require(fixture == (contracts["execution"]["model_source"]=="FIXTURE_SCRIPTED"),"HOST_ROLE_MODE")
        self.contracts,self.ledger,self.business,self.journal=contracts,ledger,business,journal
        self.fixture,self.api_key=fixture,api_key
        self.expected_tool_schema_sha256=self.fixture_failure_code=None
        self.tool_schema_sha256=self.tool_schema_summary=self.tool_definitions=None
        self.runtime=self.failure=None
        self.intents,self.tool_returns={},{}
        self.tool_trace,self.tool_rejections,self.visible_contract_checks,self.provider_responses=[],[],[],[]
        self._server=self._thread=None
        self.fixture_index=0
        self.request_started=time.monotonic()
        self.stopped=self.activated=False
        self.journal.add("PRE_REGISTERED",candidate=contracts["experiment"]["candidate_id"])


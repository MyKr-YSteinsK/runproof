"""RPF-56 durable global reservations. Immutable hash-chained snapshots, no refund."""
from __future__ import annotations
import copy
import os
import time
from pathlib import Path
from .config_pge_contracts import canonical, digest, strict_json, require, LIMITS, PRICE, validate_plan, BASE, BRANCH

class Journal:
    def __init__(self,path,run_id):
        self.path,self.run_id,self.events=path,run_id,[]
        if path is not None:
            root=Path(__file__).resolve().parents[3]/".local/rpf-56-rev4"
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
    require(len(requests) <= 12 and sum(r["role"] == "EXPLORER" for r in requests) <= 2
        and sum(r["role"] == "TARGET" for r in requests) <= 10, "REQUEST_BUDGET")
    require([r["attempt"] for r in requests] == list(range(1, len(requests) + 1)), "REQUEST_SEQUENCE")
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
    require(total + reserved <= 28000 and cost + reserved * 18 / 1_000_000 <= 0.95, "TOKEN_OR_COST_BUDGET")
    require(len(state["trials"]) <= 2 and len(set(state["trials"])) == len(state["trials"]), "JVM_BUDGET")
    require(len(state["posts"]) <= 4 and len({(p["run_id"],p["operation"]) for p in state["posts"]}) == len(state["posts"])
        and all(p["run_id"] in state["trials"] and p["operation"] in ("create_config_v1","update_config_v2") for p in state["posts"]), "POST_BUDGET_OR_REPLAY")
    return {"requests": len(requests), "tokens": total if reserved == 0 else None,
        "estimated_cost_cny_upper": cost if reserved == 0 else None, "usage_known": reserved == 0,
        "jvm": len(state["trials"]), "post": len(state["posts"])}

class TotalLedger:
    def __init__(self, path: Path, plan, *, create=False):
        validate_plan(plan)
        root = Path(__file__).resolve().parents[3] / ".local/rpf-56-rev4"
        require(path.is_absolute() and path.resolve().is_relative_to(root.resolve())
            and not any(p.is_symlink() or getattr(p,"is_junction",lambda:False)() for p in (path,*path.parents)), "LEDGER_SCOPE")
        self.path, self.plan = path, plan
        self.task=None
        if plan["task_budget_binding"] is not None:
            from .config_pge_verify import verifier_identity
            self.task=TaskBudget(root/"task-budget",plan["source_files"],verifier_identity())
            require(digest(self.task.identity)==plan["task_budget_binding"],"TASK_BUDGET_BINDING")
        if create:
            path.mkdir(exist_ok=False)
            self._write({"session_id": plan["session_id"], "plan_sha256": digest(plan), "requests": [],
                "trials": [], "posts": [], "started_monotonic_ns": time.monotonic_ns()}, None, 0)
        self.read()

    def read(self):
        files = sorted(self.path.glob("snapshot-*.json"))
        require(bool(files), "LEDGER_MISSING")
        previous = None
        for index, path in enumerate(files):
            require(not path.is_symlink() and not getattr(path,"is_junction",lambda:False)(),"LEDGER_LINK")
            value = strict_json(path.read_bytes())
            require(path.name == f"snapshot-{index:04}.json" and set(value) == {"seq","previous_sha256","state","sha256"}
                and value["seq"] == index and value["previous_sha256"] == previous
                and value["sha256"] == digest(value["state"]), "LEDGER_CHAIN_OR_TORN_RECORD")
            state = value["state"]
            require(state["session_id"] == self.plan["session_id"] and state["plan_sha256"] == digest(self.plan), "LEDGER_IDENTITY")
            validate_budget(state)
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
        task_attempt=self.task.reserve(role,round_index,body) if self.task is not None else None
        def op(state):
            require(all(r["status"] == "RECEIVED" for r in state["requests"]), "USAGE_UNKNOWN")
            require(role in ("EXPLORER","TARGET") and round_index in (1,2), "REQUEST_ROLE")
            if role == "EXPLORER":
                require(not any(r["role"] == role and r["round"] == round_index for r in state["requests"]), "EXPLORER_REPLAY")
            else:
                require(sum(r["role"] == role and r["round"] == round_index for r in state["requests"]) < 6, "TARGET_REQUEST_LIMIT")
            record = {"attempt":len(state["requests"])+1,"role":role,"round":round_index,
                "request_sha256":digest(body),"reservation_tokens":len(canonical(body))+1024+256,
                "status":"RESERVED_USAGE_UNKNOWN","usage":None,"response_id":None,"returned_model":None}
            if task_attempt is not None:record["task_attempt"]=task_attempt
            state["requests"].append(record)
            validate_budget(state)
            return record["attempt"]
        return self.mutate(op)

    def received(self, attempt, data):
        if self.task is not None:self.task.received(self.read()["requests"][attempt-1]["task_attempt"],data)
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


def validate_task(state):
    require(set(state)=={"identity","requests","started_monotonic_ns"},"TASK_FIELDS")
    rows=state["requests"];require(len(rows)<=14,"TASK_REQUEST_LIMIT")
    require([r["attempt"] for r in rows]==list(range(1,len(rows)+1)),"TASK_SEQUENCE")
    ids=[];groups={}
    for role,limit,tokens,cost in (("PROTOCOL_PROBE_ONLY",2,2048,0.05),("SESSION",12,28000,0.95)):
        rs=[r for r in rows if (r["role"]=="PROTOCOL_PROBE_ONLY")== (role=="PROTOCOL_PROBE_ONLY")]
        require(len(rs)<=limit,"TASK_SCOPE_REQUESTS")
        used=reserved=fee=0
        for r in rs:
            require(r["role"] in ("PROTOCOL_PROBE_ONLY","EXPLORER","TARGET") and r["status"] in ("RESERVED_USAGE_UNKNOWN","RECEIVED"),"TASK_ROLE_STATUS")
            if r["role"]=="PROTOCOL_PROBE_ONLY":require(r["reservation_tokens"]==1024,"PROBE_RESERVATION")
            if r["status"]=="RECEIVED":
                u=r["usage"];require(type(u) is dict and set(u)=={"prompt_tokens","completion_tokens","total_tokens"}
                    and all(type(v) is int and v>=0 for v in u.values()) and u["prompt_tokens"]+u["completion_tokens"]==u["total_tokens"]<=r["reservation_tokens"]
                    and u["completion_tokens"]<=256,"TASK_USAGE")
                used+=u["total_tokens"];fee+=(u["prompt_tokens"]*4.5+u["completion_tokens"]*18)/1000000;ids.append(r["response_id"])
            else:reserved+=r["reservation_tokens"]
        require(used+reserved<=tokens and fee+reserved*18/1000000<=cost,"TASK_TOKEN_COST")
        groups[role]={"requests":len(rs),"tokens":used,"unknown_reserved_tokens":reserved,"estimated_cost_cny_upper":fee}
    require(len(ids)==len(set(ids)),"TASK_RESPONSE_REPLAY")
    require(sum(g["tokens"]+g["unknown_reserved_tokens"] for g in groups.values())<=30048
        and sum(g["estimated_cost_cny_upper"]+g["unknown_reserved_tokens"]*18/1000000 for g in groups.values())<=1,"TASK_TOTAL_COST")
    require(sum(r["role"]=="EXPLORER" for r in rows)<=2 and sum(r["role"]=="TARGET" for r in rows)<=10,"TASK_ROLE_LIMIT")
    return groups


class TaskBudget(TotalLedger):
    """A single durable, source-bound task scope includes probes AND the session."""
    def __init__(self,path,sources,verifier,*,create=False):
        root=Path(__file__).resolve().parents[3]/".local/rpf-56-rev4"
        require(path.is_absolute() and path.resolve().is_relative_to(root.resolve()) and not any(
            p.is_symlink() or getattr(p,"is_junction",lambda:False)() for p in (path,*path.parents)),"TASK_SCOPE")
        self.path=path;self.identity={"schema":"rpf56-task-budget-v4","owner":"rpf-56-rev4","base":BASE,"branch":BRANCH,"sources":sources,"verifier":verifier}
        if create:
            path.mkdir(exist_ok=False)
            self._write({"identity":self.identity,"requests":[],"started_monotonic_ns":time.monotonic_ns()},None,0)
        self.read()
    def read(self):
        files=sorted(self.path.glob("snapshot-*.json"));require(bool(files),"TASK_LEDGER_MISSING");previous=None
        for i,path in enumerate(files):
            require(not path.is_symlink() and not getattr(path,"is_junction",lambda:False)(),"TASK_LEDGER_LINK")
            x=strict_json(path.read_bytes())
            require(path.name==f"snapshot-{i:04}.json" and set(x)=={"seq","previous_sha256","state","sha256"}
                and x["seq"]==i and x["previous_sha256"]==previous and x["sha256"]==digest(x["state"]),"TASK_CHAIN_TORN")
            state=x["state"];require(state["identity"]==self.identity,"TASK_SOURCE_IDENTITY");validate_task(state);previous=digest(x)
        self.state,self.previous,self.next_seq=state,previous,len(files)
        return copy.deepcopy(state)
    def _write(self,state,previous,seq):
        validate_task(state)
        with (self.path/f"snapshot-{seq:04}.json").open("xb") as f:
            f.write(canonical({"seq":seq,"previous_sha256":previous,"state":state,"sha256":digest(state)}));f.flush();os.fsync(f.fileno())
    def reserve(self,role,round_index,body):
        def op(state):
            require(all(r["status"]=="RECEIVED" for r in state["requests"]),"TASK_USAGE_UNKNOWN")
            if role=="PROTOCOL_PROBE_ONLY":
                prior=[r for r in state["requests"] if r["role"]==role]
                # A second probe requires a separately approved source repair; no identical retry.
                require(not prior,"SECOND_PROBE_NEEDS_EVIDENCED_SOURCE_REPAIR")
                reserve=1024
                require(len(canonical(body))+body["max_tokens"]<=reserve,"PROBE_INPUT_BOUND")
            else:
                require(role in ("EXPLORER","TARGET") and round_index in (1,2),"TASK_ROLE")
                require(any(r.get("protocol_pass") is True for r in state["requests"] if r["role"]=="PROTOCOL_PROBE_ONLY"),"PROTOCOL_PASS_REQUIRED")
                reserve=len(canonical(body))+1280
            record={"attempt":len(state["requests"])+1,"role":role,"round":round_index,"request_sha256":digest(body),
                "reservation_tokens":reserve,"status":"RESERVED_USAGE_UNKNOWN","usage":None,"response_id":None,"returned_model":None}
            state["requests"].append(record);validate_task(state);return record["attempt"]
        return self.mutate(op)
    def received(self,attempt,data):
        def op(state):
            r=state["requests"][attempt-1];require(r["status"]=="RESERVED_USAGE_UNKNOWN","TASK_RESPONSE_REPLAY")
            u=data.get("usage");require(type(u) is dict and all(k in u for k in ("prompt_tokens","completion_tokens","total_tokens")),"TASK_USAGE_UNKNOWN")
            require(type(data.get("id")) is str and data.get("model") in ("deepseek-flash","DeepSeek-V4.1-Flash-1017"),"TASK_PROVIDER_ID")
            r.update(status="RECEIVED",usage={k:u[k] for k in ("prompt_tokens","completion_tokens","total_tokens")},response_id=data["id"],returned_model=data["model"])
            validate_task(state)
        self.mutate(op)
    def protocol_pass(self,attempt):
        def op(state):
            r=state["requests"][attempt-1];require(r["role"]=="PROTOCOL_PROBE_ONLY" and r["status"]=="RECEIVED" and "protocol_pass" not in r,"PROBE_PASS_STATE")
            r["protocol_pass"]=True
        self.mutate(op)

def feedback(trial):
    x=trial["contracts"]["experiment"]
    return {"schema":"rpf56-verified-feedback-v4","run_id":x["run_id"],"candidate_id":x["candidate_id"],
        "trial_sha256":digest(trial),"effect":"SATISFIED_V2_HISTORY_2_1","fault":trial["fault"],
        "authority":"SAME_SERVICE_READ_ONLY_HTTP","target_ack":trial["outcome"]["target_ack"],
        "source_level":"REAL_PROVIDER_TARGET_JAVA_H2","business_violation":"NOT_PROVEN"}

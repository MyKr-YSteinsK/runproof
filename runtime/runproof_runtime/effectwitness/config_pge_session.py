"""RPF-56 durable global reservations. Immutable hash-chained snapshots, no refund."""
from __future__ import annotations
import copy
import os
import time
from pathlib import Path
from .config_pge_contracts import canonical, digest, strict_json, require, LIMITS, PRICE, validate_plan

class Journal:
    def __init__(self,path,run_id):
        self.path,self.run_id,self.events=path,run_id,[]
        if path is not None:
            root=Path(__file__).resolve().parents[3]/".local/rpf-56"
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
    require(total + reserved <= 28000 and cost + reserved * 18 / 1_000_000 <= 1.0, "TOKEN_OR_COST_BUDGET")
    require(len(state["trials"]) <= 2 and len(set(state["trials"])) == len(state["trials"]), "JVM_BUDGET")
    require(len(state["posts"]) <= 4 and len({(p["run_id"],p["operation"]) for p in state["posts"]}) == len(state["posts"])
        and all(p["run_id"] in state["trials"] and p["operation"] in ("create_config_v1","update_config_v2") for p in state["posts"]), "POST_BUDGET_OR_REPLAY")
    return {"requests": len(requests), "tokens": total if reserved == 0 else None,
        "estimated_cost_cny_upper": cost if reserved == 0 else None, "usage_known": reserved == 0,
        "jvm": len(state["trials"]), "post": len(state["posts"])}

class TotalLedger:
    def __init__(self, path: Path, plan, *, create=False):
        validate_plan(plan)
        root = Path(__file__).resolve().parents[3] / ".local/rpf-56"
        require(path.is_absolute() and path.resolve().is_relative_to(root.resolve())
            and not any(p.is_symlink() or getattr(p,"is_junction",lambda:False)() for p in (path,*path.parents)), "LEDGER_SCOPE")
        self.path, self.plan = path, plan
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

def feedback(trial):
    x=trial["contracts"]["experiment"]
    return {"schema":"rpf56-verified-feedback-v1","run_id":x["run_id"],"candidate_id":x["candidate_id"],
        "trial_sha256":digest(trial),"effect":"SATISFIED_V2_HISTORY_2_1","fault":trial["fault"],
        "authority":"SAME_SERVICE_READ_ONLY_HTTP","target_ack":trial["outcome"]["target_ack"],
        "source_level":"REAL_PROVIDER_TARGET_JAVA_H2","business_violation":"NOT_PROVEN"}

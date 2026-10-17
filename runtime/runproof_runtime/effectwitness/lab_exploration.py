"""One opt-in paid order exploration, separate durable quota, shared Lab writer.

Only protocol selections and validated feedback persist. Never replay on restart.
The gateway's existing OS lock and RLock protect both modes.
"""
import copy
import json
import os
import re
import threading
import uuid

from .contracts import ROOT, canonical, digest, owned_path, quarantine_path, require
from .cross_contracts import CrossContracts
from .cross_trial import run_trial
from .engine import Budget
from .lab_store import ACTIVE, BLOCKED, ID, LabError, atomic_write, utc
from .lab_evidence import SCHEMA, LIMITS, FAULTS, validate_trial, verify_session
from .pge_contracts import catalog
from .pge_provider import initial_messages, tool_definitions, parse_choice
from .provider import MODEL, request_completion
from .witness import _package_source_digest
from .witness_verify import verify_bytes, _unique_object

TERMINAL = BLOCKED | {"COMPLETED", "CANCELLED"}


class LivePlan:
    def __init__(self, document):
        self.payload = canonical(document)

    @property
    def document(self):
        return json.loads(self.payload)

    def candidate(self, candidate_id):
        require(type(candidate_id) is str and candidate_id in FAULTS, "CANDIDATE_NOT_REGISTERED", "AGENT")
        return next(c for c in self.document["catalog"] if c["candidate_id"] == candidate_id)


def freeze_plan(sid):
    runs = ["rpf46-" + uuid.uuid4().hex for _ in range(2)]
    return {"schema_version": "rpf-lab-plan-v1", "session_id": sid, "preregistered_at": utc(),
        "catalog": catalog(), "catalog_revision": "rpf42-three-candidates-v1", "limits": dict(LIMITS),
        "objective": "verified-activation-provenance-coverage", "metric_version": "rpf46-activation-fact-set-v1",
        "target_driver": "DETERMINISTIC_CONTROLLED_TARGET", "source_digest": _package_source_digest(),
        "run_generation": "two-prereserved-uuid4-identities-one-per-round-no-replay",
        "trial_contracts": [{k: CrossContracts.create("order", run, v).document() for k, v in FAULTS.items()} for run in runs],
        "feedback_whitelist": ["schema_version", "domain", "contract_outcome", "fault_activation", "violated_rules",
                               "evidence_gaps", "state_diff", "receipt_hash"],
        "pricing": {"currency": "USD", "input_per_million": .30, "output_per_million": 1.20,
                    "usd_cny_ceiling": 10, "basis": "cache-miss-peak", "checked_at": "2026-10-18",
                    "source": "https://api-docs.deepseek.com/quick_start/pricing/"},
        "provider": "DeepSeek", "requested_model": MODEL, "thinking": "disabled", "automatic_retries": 0,
        "physical_trials": 2, "trial_steps_reserved": 7, "baseline_policy": "NONE_NO_COUNTERFACTUAL"}


def validate_plan(p):
    require(p["schema_version"] == "rpf-lab-plan-v1" and p["limits"] == LIMITS
            and p["catalog"] == catalog() and p["requested_model"] == MODEL
            and len(p["trial_contracts"]) == 2 and p["trial_steps_reserved"] == 7
            and p["physical_trials"] == 2 and p["metric_version"] == "rpf46-activation-fact-set-v1" and re.fullmatch(r"[a-f0-9]{64}", p["source_digest"]), "LIVE_PLAN_INVALID")
    runs = set()
    for choices in p["trial_contracts"]:
        require(set(choices) == set(FAULTS), "FROZEN_CANDIDATES_INVALID")
        round_runs = set()
        for k, c in choices.items():
            cc = CrossContracts(*(canonical(c[name]) for name in ("execution", "effect", "experiment")))
            cc.validate()
            require(c == cc.document() and cc.experiment["domain"] == "order" and cc.experiment["fault"] == FAULTS[k]
                    and re.fullmatch(r"rpf46-[a-f0-9]{32}", cc.experiment["run_id"]), "FROZEN_CONTRACT_INVALID")
            round_runs.add(cc.experiment["run_id"])
        require(len(round_runs) == 1 and not runs & round_runs, "TRIAL_IDENTITY_COLLISION")
        runs.update(round_runs)


class ExplorationStore:
    def __init__(self, owner, *, enabled=False, root=None, provider=request_completion, runner=run_trial):
        if owner.exploration is not None:
            raise LabError(409, "EXPLORATION_ALREADY_OWNED")
        self.owner, self.lock = owner, owner.lock
        self.enabled, self.provider, self.runner = enabled, provider, runner
        self.root = owned_path((root or ROOT / ".local/rpf-46") / "explorations", task="rpf-46")
        self.root.mkdir(parents=True, exist_ok=True)
        self.path, self.seal = self.root / "ledger.json", self.root / "reservation.json"
        self.threads, self.closed = [], False
        try:
            if self.path.exists():
                raw = self.path.read_bytes()
                require(len(raw) <= 262144, "LEDGER_SIZE")
                wrapped = json.loads(raw, object_pairs_hook=_unique_object)
                self.data = wrapped["data"]
                require(set(wrapped) == {"data", "sha256"} and wrapped["sha256"] == digest(self.data), "LEDGER_HASH")
            else:
                require(not self.seal.exists(), "MISSING_RESERVED_LEDGER")
                self.data = {"schema_version": SCHEMA, "session": None}
                self._save()
            require(set(self.data) == {"schema_version", "session"} and self.data["schema_version"] == SCHEMA, "LEDGER_SCHEMA")
            s = self.data["session"]
            if s:
                validate_plan(s["plan"])
                require(s["status"] in ACTIVE | TERMINAL and s["plan_digest"] == digest(s["plan"])
                        and s["session_id"] == s["plan"]["session_id"] and re.fullmatch(r"exploration-[a-f0-9]{32}", s["session_id"])
                        and json.loads(self.seal.read_bytes()) == {"session_id": s["session_id"], "plan_digest": s["plan_digest"]}, "LEDGER_IDENTITY")
                verify_session(s)
                for t in s["trials"]:
                    if t["witness"]["status"] == "CONTENT_CHECKED_LOCAL":
                        self._witness(s, t)
                if s["status"] in ACTIVE:
                    s.update(status="RECONCILE_REQUIRED", error_code="RESTART_NO_AUTOMATIC_RESUME", run_outcome="INCONCLUSIVE", updated_at=utc())
                    self._quarantine_attempts(s)
                    self._save()
            else:
                require(not self.seal.exists(), "ORPHAN_RESERVATION")
        except Exception as error:
            raise LabError(503, "EXPLORATION_LEDGER_UNAVAILABLE") from error
        owner.exploration = self

    def _save(self):
        atomic_write(self.path, canonical({"data": self.data, "sha256": digest(self.data)}), task="rpf-46")

    def _quarantine_attempts(self, s):
        """Preserve independently identified unfinished state; never reset on recovery."""
        from .orders import AuthorityReader
        for r in s["trial_reservations"]:
            if r["status"] != "ATTEMPTED":
                continue
            try:
                n = r["round"]
                choice = s["selections"][n-1]["candidate_id"]
                c = s["plan"]["trial_contracts"][n-1][choice]
                require(r["run_id"] == c["experiment"]["run_id"], "RESERVATION_IDENTITY")
                source = owned_path(ROOT / ".local/rpf-46" / r["run_id"], task="rpf-46")
                base = ROOT / ".local/quarantine/rpf-46"
                if (base / r["run_id"]).exists():
                    r["quarantine_status"] = "PRESERVED_QUARANTINE"
                elif source.exists():
                    require(not (set(p.name for p in source.iterdir()) - {"orders.sqlite3"+z for z in ("", "-journal", "-wal", "-shm")}), "UNEXPECTED_SANDBOX_FILES")
                    contracts = CrossContracts(*(canonical(c[z]) for z in ("execution", "effect", "experiment")))
                    reader = AuthorityReader(source / "orders.sqlite3", contracts, storage_task="rpf-46")
                    reader.validate(reader.read())
                    destination = quarantine_path(source, task="rpf-46")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    source.rename(destination)
                    r["quarantine_status"] = "PRESERVED_QUARANTINE"
                else:
                    r["quarantine_status"] = "NO_SANDBOX_FOUND_STATE_UNPROVEN"
            except Exception:
                r["quarantine_status"] = "PRESERVED_IN_PLACE_OWNER_OR_MOVE_UNCONFIRMED"

    def active(self):
        s = self.data["session"]
        return bool(s and s["status"] in ACTIVE)

    def guard_other_mode(self):
        s = self.data["session"]
        if s and s["status"] in BLOCKED:
            raise LabError(409, "RECONCILE_REQUIRED")
        if self.active():
            raise LabError(409, "GATEWAY_BUSY")

    def capabilities(self):
        with self.lock:
            legacy = self.owner.capabilities()
            s = self.data["session"]
            state = "DISABLED" if not self.enabled else "KEY_MISSING" if not os.environ.get("DEEPSEEK_API_KEY") else "AVAILABLE"
            healthy = not s or s["status"] not in BLOCKED
            return {"schema_version": SCHEMA, "mode": "PGE_LIVE_ORDER", "domain": "order", "explorer": state,
                "enabled": state == "AVAILABLE" and healthy and legacy["enabled"] and not self.closed,
                "busy": legacy["busy"], "remaining_sessions": int(s is None), "limits": dict(LIMITS),
                "physical_trials": 2, "requested_model": MODEL, "model_identity_source": "provider-response-on-request",
                "source": "LIVE_LOCAL_SIMULATION", "target_driver": "DETERMINISTIC_CONTROLLED_TARGET",
                "issuer_authenticity": "NOT_ESTABLISHED", "blocked": not healthy}

    def create(self, request):
        if (type(request) is not dict or set(request) != {"mode", "domain", "request_id"}
                or request["mode"] != "PGE_LIVE_ORDER" or request["domain"] != "order"
                or type(request["request_id"]) is not str or not ID.fullmatch(request["request_id"])):
            raise LabError(400, "EXPLORATION_REQUEST_REJECTED")
        with self.lock:
            s = self.data["session"]
            if s and s["request_id"] == request["request_id"]:
                return self.get(s["session_id"])
            cap = self.capabilities()
            if not cap["enabled"] or self.owner.closed:
                raise LabError(409, "EXPLORATION_DISABLED_OR_UNRESOLVED")
            if cap["busy"]:
                raise LabError(409, "GATEWAY_BUSY")
            if s or self.seal.exists():
                raise LabError(429, "EXPLORATION_QUOTA_EXHAUSTED")
            sid = "exploration-" + uuid.uuid4().hex
            plan = freeze_plan(sid)
            validate_plan(plan)
            s = {"schema_version": SCHEMA, **request, "session_id": sid, "plan": plan, "plan_digest": digest(plan),
                "source": "LIVE_LOCAL_SIMULATION", "explorer": "LIVE_EXPLORER_DEEPSEEK",
                "target_driver": "DETERMINISTIC_CONTROLLED_TARGET", "rationale": "RATIONALE_NOT_RECORDED",
                "status": "ACCEPTED", "run_outcome": "INCONCLUSIVE", "created_at": utc(), "updated_at": utc(),
                "cancel_requested": False, "error_code": None, "events": [], "provider_requests": [], "selections": [],
                "trial_reservations": [], "trials": [], "usage": Budget(LIMITS).public(),
                "research": {"L1": False, "L2": False, "H1": "NOT_PROVEN_IN_THIS_RUN", "attribution": "CORRELATIONAL_ONLY"}}
            # Exclusive immutable consumption marker precedes the ledger and all I/O.
            seal = owned_path(self.seal, task="rpf-46")
            with seal.open("xb") as stream:
                stream.write(canonical({"session_id": sid, "plan_digest": s["plan_digest"]}))
                stream.flush()
                os.fsync(stream.fileno())
            self.data["session"] = s
            self._save()
            thread = threading.Thread(target=self._execute, daemon=False)
            self.threads.append(thread)
            thread.start()
            return copy.deepcopy(s)

    def _execute(self):
        s = self.data["session"]
        budget = Budget(LIMITS)
        def save():
            with self.lock:
                # Remote metadata is bounded protocol identity, never arbitrary text.
                for r in s["provider_requests"]:
                    for key in ("response_id", "request_id", "returned_model"):
                        value = r.get(key)
                        if value is not None and (type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value)):
                            r[key] = None
                            raise ValueError("PROVIDER_METADATA_REJECTED")
                s["usage"] = {**budget.public(), "physical_trials_reserved": len(s["trial_reservations"]),
                              "physical_trials_completed": len(s["trials"])}
                s["updated_at"] = utc()
                self._save()
        def event(kind, **facts):
            with self.lock:
                seq = len(s["events"]) + 1
                s["events"].append({"seq": seq, "event_id": "pge-event-" + str(seq), "observed_at": utc(), "type": kind,
                                    "facts": facts, "facts_sha256": digest(facts)})
                save()
        def cancelled():
            with self.lock:
                if not s["cancel_requested"]:
                    return False
                s.update(status="CANCELLED", run_outcome="CANCELLED", error_code="CANCELLED_AT_SAFE_BOUNDARY")
                save()
                return True
        try:
            if cancelled():
                return
            with self.lock:
                s["status"] = "RUNNING"
                save()
            plan, seen = LivePlan(s["plan"]), set()
            messages = initial_messages(plan)
            tools = tool_definitions(plan)
            facts_seen = set()
            event("PLAN_FROZEN", plan_digest=s["plan_digest"], source_digest=s["plan"]["source_digest"])
            for n in (1, 2):
                if cancelled():
                    return
                previous = s["trials"][-1] if s["trials"] else None
                body = {"model": MODEL, "messages": messages, "tools": tools, "tool_choice": "required",
                        "thinking": {"type": "disabled"}, "max_tokens": 128, "stream": False}
                if previous:
                    require(messages[-1] == {"role": "tool", "tool_call_id": s["selections"][-1]["tool_call_id"],
                            "content": canonical(previous["feedback"]).decode()}, "FEEDBACK_DELIVERY_MISMATCH")
                event("PROVIDER_INPUT_FROZEN", round=n, messages_hash=digest(messages), body_hash=digest(body),
                      feedback_hash=previous["feedback_sha256"] if previous else None,
                      delivered_tool_call_id=messages[-1]["tool_call_id"] if previous else None)
                data = self.provider(body, budget, s["provider_requests"], save)
                require(budget.usage_known and len(s["provider_requests"]) == n, "PROVIDER_ACCOUNTING_INVALID")
                require(data["model"] in (MODEL, "DeepSeek-V4.1-Flash-1017", "deepseek-v4.1-flash-1017"), "PROVIDER_MODEL_UNEXPECTED", "PROVIDER")
                # Reject duplicate argument keys before reusing the shared parser.
                for c in data.get("choices", []):
                    for call in c.get("message", {}).get("tool_calls", []):
                        args = call.get("function", {}).get("arguments", "")
                        try:
                            json.loads(args, object_pairs_hook=_unique_object)
                        except (ValueError, TypeError) as error:
                            from ..models import RuntimeFailure
                            raise RuntimeFailure("AGENT", "EXPLORER_ARGUMENT_JSON") from error
                call = parse_choice(data, plan, seen)
                require(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", call["id"]) is not None, "EXPLORER_CALL_IDENTITY", "AGENT")
                k = json.loads(call["function"]["arguments"])["candidate_id"]
                selection = {"round": n, "candidate_id": k, "tool_call_id": call["id"], "response_id": data["id"],
                    "input_messages_hash": digest(messages), "input_feedback_hash": previous["feedback_sha256"] if previous else None}
                with self.lock:
                    s["selections"].append(selection)
                    event("PROVIDER_SELECTION_ACCEPTED", **selection)
                if cancelled():
                    return
                document = s["plan"]["trial_contracts"][n-1][k]
                contracts = CrossContracts(*(canonical(document[z]) for z in ("execution", "effect", "experiment")))
                # Seven shared steps are consumed/reserved before opening SQLite.
                for _ in range(7):
                    budget.step()
                budget.fault_trial()
                reservation = {"round": n, "run_id": contracts.experiment["run_id"], "operation_id": contracts.effect["operation_id"],
                               "status": "ATTEMPTED", "reserved_steps": 7, "reserved_at": utc()}
                with self.lock:
                    s["trial_reservations"].append(reservation)
                    event("PHYSICAL_TRIAL_RESERVED", **reservation)
                bundle, usage = self.runner(contracts, storage_task="rpf-46",
                    event_hook=lambda e: event("TRIAL_EVENT", round=n, trial_event=e),
                    deadline=budget.started + budget.limits["seconds"])
                budget.check_time()
                require(usage["steps"] == 7 and usage["provider_requests"] == 0 and bundle["contracts"] == document,
                        "TRIAL_ACCOUNTING_MISMATCH")
                fault = bundle["observation"]["fault"]["activation"]
                witness = {"status": "NOT_ISSUED_PROFILE_NOT_ELIGIBLE", "external_anchor": False, "issuer_authenticity": "NOT_ESTABLISHED"}
                if fault == "TRIGGERED":
                    raw = canonical(bundle)
                    verify_bytes(raw)
                    folder = owned_path(self.root / s["session_id"], task="rpf-46")
                    folder.mkdir(exist_ok=True)
                    atomic_write(folder / ("trial-" + str(n) + ".json"), raw, task="rpf-46")
                    witness.update(status="CONTENT_CHECKED_LOCAL", sha256=digest(bundle), bytes=len(raw), schema_version=bundle["schema_version"])
                fact = "fault_activation=" + fault
                t = {"schema_version": "rpf-lab-trial-v1", "round": n, "candidate_id": k, "run_id": contracts.experiment["run_id"],
                    "plan_digest": s["plan_digest"], "contracts": document,
                    **{z: bundle[z] for z in ("observation", "events", "claims")},
                    "feedback": bundle["observation"]["feedback"], "feedback_sha256": digest(bundle["observation"]["feedback"]),
                    "new_facts": [] if fact in facts_seen else [fact], "witness": witness}
                validate_trial(t, s["plan"])
                facts_seen.add(fact)
                with self.lock:
                    reservation["status"] = "COMPLETED"
                    s["trials"].append(t)
                    event("AUTHORITY_FEEDBACK_VALIDATED", round=n, feedback_sha256=t["feedback_sha256"], new_facts=t["new_facts"])
                messages += [{"role": "assistant", "content": None, "tool_calls": [call]},
                             {"role": "tool", "tool_call_id": call["id"], "content": canonical(t["feedback"]).decode()}]
            with self.lock:
                l1 = len(s["trials"]) == 2 and s["selections"][1]["input_feedback_hash"] == s["trials"][0]["feedback_sha256"]
                l2 = l1 and s["selections"][0]["candidate_id"] != s["selections"][1]["candidate_id"] and bool(s["trials"][1]["new_facts"])
                s.update(status="COMPLETED", run_outcome="PASS", research={"L1": l1, "L2": l2,
                    "H1": "LIMITED_MECHANISM_EVIDENCE_ONLY" if l2 else "NOT_PROVEN_IN_THIS_RUN", "attribution": "CORRELATIONAL_ONLY"})
                verify_session(s)
                event("SESSION_STOPPED", reason="TWO_ROUNDS_COMPLETED_NO_COUNTERFACTUAL")
        except Exception as error:
            with self.lock:
                uncertain = not budget.usage_known or any(t["status"] == "ATTEMPTED" for t in s["trial_reservations"])
                agent = getattr(error, "domain", None) == "AGENT"
                s.update(status="RECONCILE_REQUIRED" if uncertain else "ERROR", run_outcome="AGENT_FAIL" if agent else "PLATFORM_ERROR",
                         error_code="EXPLORATION_STOPPED_" + ("UNKNOWN_USAGE_OR_TRIAL" if uncertain else "AGENT_PROTOCOL" if agent else "PLATFORM_ERROR"))
                try:
                    self._quarantine_attempts(s)
                    event("SESSION_STOPPED", reason=s["error_code"])
                except Exception:
                    pass  # In-memory blocked state persists until process restart; startup never replays.

    def get(self, sid):
        with self.lock:
            s = self.data["session"]
            if not s or s["session_id"] != sid:
                raise LabError(404, "EXPLORATION_NOT_FOUND")
            try:
                verify_session(s)
                for t in s["trials"]:
                    if t["witness"]["status"] == "CONTENT_CHECKED_LOCAL":
                        self._witness(s, t)
            except Exception:
                s.update(status="INCONCLUSIVE", run_outcome="INCONCLUSIVE", error_code="EXPLORATION_EVIDENCE_INVALID")
                self._save()
                raise LabError(503, "EXPLORATION_EVIDENCE_INVALID")
            return copy.deepcopy(s)

    def _witness(self, s, t):
        path = owned_path(self.root / s["session_id"] / ("trial-" + str(t["round"]) + ".json"), task="rpf-46")
        raw = path.read_bytes()
        require(len(raw) <= 128*1024 and len(raw) == t["witness"]["bytes"], "WITNESS_SIZE")
        b = json.loads(raw)
        require(digest(b) == t["witness"]["sha256"] and all(b[k] == t[k] for k in
                ("contracts", "observation", "events", "claims")), "WITNESS_SESSION_BINDING")
        verify_bytes(raw)
        return raw

    def witness(self, sid, trial):
        with self.lock:
            s = self.get(sid)
            t = next((t for t in s["trials"] if str(t["round"]) == trial), None)
            if not t or t["witness"]["status"] != "CONTENT_CHECKED_LOCAL":
                raise LabError(409, "WITNESS_NOT_ISSUED_PROFILE_NOT_ELIGIBLE")
            return self._witness(s, t)

    def cancel(self, sid):
        with self.lock:
            self.get(sid)
            s = self.data["session"]
            if s["status"] not in ACTIVE:
                raise LabError(409, "SESSION_NOT_CANCELLABLE")
            s.update(status="CANCEL_REQUESTED", cancel_requested=True, updated_at=utc())
            self._save()
            return copy.deepcopy(s)

    def close(self):
        self.closed = True
        for t in self.threads:
            t.join(timeout=95)
        if any(t.is_alive() for t in self.threads):
            raise LabError(503, "EXPLORATION_STILL_UNRESOLVED")

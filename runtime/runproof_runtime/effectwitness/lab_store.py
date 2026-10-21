"""Single-owner, durable local Lab sessions. No automatic replay after restart."""
import copy
import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone

from .contracts import ROOT, canonical, owned_path as original_owned_path, quarantine_path

def owned_path(path, *, task="rpf-45"):
    if task == "rpf-60":
        from .lab_cross_domain_contracts import scoped
        return scoped(path)
    return original_owned_path(path, task=task)
from .cross_contracts import CrossContracts
from .cross_trial import run_trial
from .witness_verify import verify_bytes

SCHEMA = "rpf-lab-v1"
ROOT45 = ROOT / ".local/rpf-45"
ACTIVE = {"ACCEPTED", "RUNNING", "CANCEL_REQUESTED"}
BLOCKED = {"RECONCILE_REQUIRED", "ERROR", "INCONCLUSIVE"}
ID = re.compile(r"[a-zA-Z0-9_-]{8,80}\Z")


class LabError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


def utc():
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path, raw, *, task="rpf-45"):
    path = owned_path(path, task=task)
    temporary = path.with_suffix(path.suffix + ".pending")
    owned_path(temporary, task=task)
    with temporary.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class SessionStore:
    def __init__(self, root=None, *, runner=run_trial, storage_task="rpf-45", read_only=False):
        self.read_only = read_only
        self.task = storage_task
        self.exploration = None
        self.root = owned_path((root or ROOT45) / "sessions", task=self.task)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.runner = runner
        self.threads = []
        self.closed = False
        self.handle = owned_path(self.root / "owner.lock", task=self.task).open("a+b")
        try:
            if self.handle.seek(0, os.SEEK_END) == 0:
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.handle.close()
            raise LabError(409, "SESSION_STORE_ALREADY_OWNED") from error
        self.path = owned_path(self.root / "ledger.json", task=self.task)
        try:
            self.data = json.loads(self.path.read_bytes()) if self.path.exists() else {"schema_version": SCHEMA, "sessions": []}
            if (set(self.data) != {"schema_version", "sessions"} or self.data["schema_version"] != SCHEMA
                    or type(self.data["sessions"]) is not list or len(self.data["sessions"]) > 3):
                raise ValueError()
            for session in self.data["sessions"]:
                if (not re.fullmatch(r"session-[a-f0-9]{32}", session["session_id"])
                        or session["status"] not in ACTIVE | BLOCKED | {"COMPLETED", "CANCELLED"}):
                    raise ValueError()
                c = session["contracts"]
                frozen = CrossContracts(*(canonical(c[k]) for k in ("execution", "effect", "experiment")))
                frozen.validate()
                if c != frozen.document() or session["run_id"] != frozen.experiment["run_id"]:
                    raise ValueError()
                if session["status"] in ACTIVE:
                    session.update(status="RECONCILE_REQUIRED", error_code="RESTART_WITH_UNRESOLVED_EXECUTION",
                                   updated_at=utc())
                    self._quarantine_session(session, frozen)
            self._save()
        except Exception as error:
            self.handle.close()
            raise LabError(503, "SESSION_LEDGER_UNAVAILABLE") from error

    def _save(self):
        atomic_write(self.path, canonical(self.data), task=self.task)

    def _quarantine_session(self, session, contracts):
        """Only move a ledger-owned, independently identified task sandbox; never reset it."""
        source = owned_path(ROOT / ".local" / self.task / session["run_id"], task=self.task)
        destination = quarantine_path(source, task=self.task).with_name(session["session_id"])
        if destination.exists():
            session["quarantine_status"] = "QUARANTINED"
            return
        if not source.exists():
            session["quarantine_status"] = "NO_SANDBOX_FOUND_EXECUTION_STILL_UNRESOLVED"
            return
        try:
            from .orders import AuthorityReader
            from .ops import OpsAuthorityReader
            reader_type = OpsAuthorityReader if session["domain"] == "ops" else AuthorityReader
            filename = "ops.sqlite3" if session["domain"] == "ops" else "orders.sqlite3"
            if set(p.name for p in source.iterdir()) - {filename + suffix for suffix in ("", "-journal", "-wal", "-shm")}:
                raise ValueError()
            reader = reader_type(source / filename, contracts, storage_task=self.task)
            reader.validate(reader.read())
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.rename(destination)
            session["quarantine_status"] = "QUARANTINED"
        except Exception:
            session["quarantine_status"] = "PRESERVED_IN_PLACE_OWNER_OR_MOVE_UNCONFIRMED"

    def _find(self, session_id):
        if not ID.fullmatch(session_id):
            raise LabError(404, "SESSION_NOT_FOUND")
        for session in self.data["sessions"]:
            if session["session_id"] == session_id:
                return session
        raise LabError(404, "SESSION_NOT_FOUND")

    def capabilities(self):
        with self.lock:
            blocked = any(s["status"] in BLOCKED for s in self.data["sessions"]) or bool(
                self.exploration and self.exploration.data["session"] and
                self.exploration.data["session"]["status"] in BLOCKED)
            return {"schema_version": SCHEMA, "source": "LIVE_LOCAL_SIMULATION", "domains": ["order", "ops"],
                    "mode": "LOCAL_CONTROLLED_CAPTURE", "fault": "response-lost", "enabled": not blocked and not self.closed and not self.read_only,
                    "remaining_reservations": 3 - len(self.data["sessions"]), "max_running": 1, "max_queued": 0,
                    "busy": any(s["status"] in ACTIVE for s in self.data["sessions"]) or bool(self.exploration and self.exploration.active()),
                    "limits": {"trials": 3, "steps_per_trial": 8, "seconds_per_trial": 900,
                               "provider_requests": 0, "tokens": 0, "cost_cny": 0},
                    "explorer": "NOT_IMPLEMENTED", "issuer_authenticity": "NOT_ESTABLISHED"}

    def create(self, request):
        if self.read_only:
            raise LabError(409, "LEGACY_CAPTURE_READ_ONLY_IN_CROSS_DOMAIN_MODE")
        if (type(request) is not dict or set(request) != {"domain", "mode", "request_id"}
                or request["domain"] not in ("order", "ops") or request["mode"] != "LOCAL_CONTROLLED_CAPTURE"
                or type(request["request_id"]) is not str or not ID.fullmatch(request["request_id"])):
            raise LabError(400, "SESSION_REQUEST_REJECTED")
        with self.lock:
            if self.closed:
                raise LabError(503, "GATEWAY_STOPPING")
            for s in self.data["sessions"]:
                if s["request_id"] == request["request_id"]:
                    if (s["domain"], s["mode"]) != (request["domain"], request["mode"]):
                        raise LabError(409, "IDEMPOTENCY_IDENTITY_CONFLICT")
                    return self.get(s["session_id"])
            if self.exploration:
                self.exploration.guard_other_mode()
            if any(s["status"] in BLOCKED for s in self.data["sessions"]):
                raise LabError(409, "RECONCILE_REQUIRED")
            if any(s["status"] in ACTIVE for s in self.data["sessions"]):
                raise LabError(409, "GATEWAY_BUSY")
            if len(self.data["sessions"]) >= 3:
                raise LabError(429, "TRIAL_QUOTA_EXHAUSTED")
            session_id = "session-" + uuid.uuid4().hex
            run_id = "rpf45-" + uuid.uuid4().hex
            c = CrossContracts.create(request["domain"], run_id)
            s = {"schema_version": SCHEMA, "session_id": session_id, **request, "run_id": run_id,
                 "source": "LIVE_LOCAL_SIMULATION", "status": "ACCEPTED", "created_at": utc(), "updated_at": utc(),
                 "contracts": c.document(), "events": [], "result": None, "usage": None, "witness": None,
                 "error_code": None, "cancel_requested": False, "storage_owner": self.task}
            self.data["sessions"].append(s)
            self._save()  # Durable quota and identities precede any executor thread/mutation.
            thread = threading.Thread(target=self._execute, args=(session_id, c), daemon=False)
            self.threads.append(thread)
            thread.start()
            return copy.deepcopy(s)

    def _execute(self, session_id, contracts):
        try:
            self._execute_capture(session_id, contracts)
        except Exception:
            # Even persistence failure must not escape as a thread traceback or reopen writes.
            with self.lock:
                s = self._find(session_id)
                s.update(status="RECONCILE_REQUIRED", error_code="SESSION_PERSISTENCE_UNRESOLVED", result=None, witness=None)
                try:
                    self._save()
                except Exception:
                    pass

    def _execute_capture(self, session_id, contracts):
        with self.lock:
            s = self._find(session_id)
            if s["status"] == "CANCELLED":
                return
            s.update(status="RUNNING", updated_at=utc())
            self._save()

        def progress(event):
            with self.lock:
                s["events"].append(event)
                s["updated_at"] = utc()
                self._save()

        try:
            bundle, usage = self.runner(contracts, storage_task=self.task, event_hook=progress, quarantine_id=session_id)
            raw = canonical(bundle)
            verified = verify_bytes(raw)  # Deliberately no self-generated trusted external anchor.
            if (verified["schema_version"] != "rpf-effect-witness-v2" or bundle["contracts"] != contracts.document()
                    or bundle["events"] != s["events"]):
                raise ValueError("CAPTURE_IDENTITY_MISMATCH")
            sha = hashlib.sha256(raw).hexdigest()
            folder = owned_path(self.root / session_id, task=self.task)
            folder.mkdir()
            atomic_write(folder / "witness.json", raw, task=self.task)
            with self.lock:
                s.update(status="COMPLETED", updated_at=utc(), result=bundle, usage=usage,
                         witness={"status": "CONTENT_CHECKED_LOCAL", "sha256": sha, "bytes": len(raw),
                                  "issuer_authenticity": "NOT_ESTABLISHED", "external_anchor": False})
                self._save()
        except Exception:
            # cross_trial preserves uncertain business state in task quarantine. Never replay.
            with self.lock:
                s.update(status="RECONCILE_REQUIRED", error_code="CAPTURE_OR_EXECUTION_UNRESOLVED", updated_at=utc(),
                         result=None, witness=None)
                self._quarantine_session(s, contracts)
                self._save()

    def get(self, session_id):
        with self.lock:
            s = self._find(session_id)
            if s["status"] == "COMPLETED":
                try:
                    self._witness(s)
                except Exception:
                    s.update(status="INCONCLUSIVE", error_code="WITNESS_UNAVAILABLE_OR_INVALID", result=None, witness=None)
                    self._save()
            return copy.deepcopy(s)

    def _witness(self, s):
        path = owned_path(self.root / s["session_id"] / "witness.json", task=self.task)
        with path.open("rb") as stream:
            raw = stream.read(128 * 1024 + 1)
        if hashlib.sha256(raw).hexdigest() != s["witness"]["sha256"]:
            raise ValueError()
        verify_bytes(raw)
        if json.loads(raw) != s["result"]:
            raise ValueError()
        return raw

    def witness(self, session_id):
        with self.lock:
            s = self.get(session_id)
            if s["status"] != "COMPLETED":
                raise LabError(409, "NO_VALID_WITNESS")
            return self._witness(s)

    def cancel(self, session_id):
        with self.lock:
            s = self._find(session_id)
            if s["status"] == "ACCEPTED":
                s["status"] = "CANCELLED"
            elif s["status"] in ("RUNNING", "CANCEL_REQUESTED"):
                s["status"] = "CANCEL_REQUESTED"
            else:
                raise LabError(409, "SESSION_NOT_CANCELLABLE")
            s.update(cancel_requested=True, updated_at=utc())
            self._save()
            return copy.deepcopy(s)

    def close(self):
        with self.lock:
            self.closed = True
        if self.exploration:
            self.exploration.close()
        for thread in self.threads:
            thread.join(timeout=905)
        if any(t.is_alive() for t in self.threads):
            raise LabError(503, "EXECUTION_STILL_UNRESOLVED")
        self.handle.close()

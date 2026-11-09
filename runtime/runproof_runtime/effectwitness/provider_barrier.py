"""RPF-101 durable Host admission. The owner is a trusted local filesystem boundary."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import threading
import time

ROOT = Path(__file__).resolve().parents[3] / ".local" / "rpf-101-provider-presend"
CASES = ("unknown-empty", "ready-restart", "unknown-restart", "send-first", "unknown-first",
         "flush-failure", "write-failure", "torn")
ROLES = ("TARGET", "EXPLORER")
DOMAINS = ("order", "ops")
PAYLOAD = b"RPF-101 synthetic local transport payload\n"
SCHEMA = "rpf101-presend-host-v1"


class Denied(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(raw):
    return sha256(raw).hexdigest()


def strict(raw):
    def pairs(values):
        out = {}
        for key, value in values:
            if key in out:
                raise Denied("DUPLICATE_KEY")
            out[key] = value
        return out
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    canonical(data)
    return data


def safe(path):
    path = Path(os.path.abspath(path))
    if not path.is_relative_to(ROOT):
        raise Denied("OWNER_SCOPE")
    for parent in reversed((path, *path.parents)):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 1024:
            raise Denied("OWNER_REPARSE")
        if parent == path and stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise Denied("OWNER_HARDLINK")
    return path


def sync_dir(path):
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def exclusive(path, data):
    path = safe(path)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(path.parent)


def source_identity():
    return {name: digest(Path(__file__).with_name(name).read_bytes().replace(b"\r\n", b"\n"))
            for name in ("provider_barrier.py", "provider_transport.py", "provider_receipt_verify.py")}


@contextmanager
def lock_file(path):
    with safe(path).open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def read_wal(path):
    with safe(path).open("rb") as stream:
        raw = stream.read(131073)
    if not raw or len(raw) > 131072 or not raw.endswith(b"\n"):
        raise Denied("TORN_WAL")
    rows = []
    previous = "0" * 64
    for line in raw.splitlines():
        row = strict(line)
        base = {"seq": len(rows), "prev": previous, "kind": row["kind"], "body": row["body"]}
        if (type(row["seq"]) is not int or row != {**base, "sha256": digest(canonical(base))}
                or line != canonical(row) or len(rows) >= 8):
            raise Denied("WAL_CHAIN")
        rows.append(row)
        previous = row["sha256"]
    return rows


class Host:
    def __init__(self, case, *, create=False, receiver=None, fault=None):
        if case not in CASES or fault not in {None, "write", "flush"}:
            raise Denied("CASE_SCOPE")
        self.case = case
        self.root = safe(ROOT / "sessions" / case)
        self.wal = self.root / "wal.jsonl"
        self.active = self.root / "active"
        self.intent = self.root / "unknown-intent.json"
        self.fault = fault
        self.mutex = threading.Lock()
        self.poison = False
        self.pending_unknown = False
        self.entered = False
        self.create = create
        self.receiver = receiver

    @contextmanager
    def open(self):
        if self.create:
            self.root.mkdir(parents=True, exist_ok=False)
        with lock_file(self.root / "writer.lock"):
            if safe(self.active).exists():
                raise Denied("PERSISTENCE_UNCERTAIN")
            exclusive(self.active, canonical({"pid": os.getpid()}))
            try:
                if self.create:
                    ident = {"schema": SCHEMA, "case": self.case, "source": source_identity(),
                             "max_tickets": 1, "max_sends": 1, "receiver": self.receiver,
                             "request_sha256": digest(PAYLOAD)}
                    self.append("READY", ident, [])
                self.state()
                self.entered = True
                yield self
            except BaseException:
                self.poison = True
                raise
            finally:
                self.entered = False
                if not self.poison:
                    self.active.unlink()
                    sync_dir(self.root)

    def append(self, kind, body, rows):
        base = {"seq": len(rows), "prev": rows[-1]["sha256"] if rows else "0" * 64,
                "kind": kind, "body": body}
        row = {**base, "sha256": digest(canonical(base))}
        try:
            if self.fault == "write" and kind == "UNKNOWN_OBSERVED":
                raise OSError("SIMULATED_WRITE_FAILURE")
            with safe(self.wal).open("xb" if not rows else "ab") as stream:
                stream.write(canonical(row) + b"\n")
                stream.flush()
                if self.fault == "flush" and kind == "UNKNOWN_OBSERVED":
                    raise OSError("SIMULATED_FSYNC_FAILURE")
                os.fsync(stream.fileno())
            sync_dir(self.root)
        except OSError:
            self.poison = True
            raise

    def state(self):
        rows = read_wal(self.wal)
        ready = rows[0]["body"]
        if (rows[0]["kind"] != "READY" or ready.get("schema") != SCHEMA
                or ready.get("case") != self.case or ready.get("source") != source_identity()
                or ready.get("request_sha256") != digest(PAYLOAD)
                or ready.get("max_tickets") != 1 or ready.get("max_sends") != 1):
            raise Denied("SOURCE_OR_OWNER_DRIFT")
        unknown = False
        ticket = None
        phase = None
        for row in rows[1:]:
            kind, body = row["kind"], row["body"]
            if kind == "UNKNOWN_OBSERVED" and not unknown and body in ({"domain": d} for d in DOMAINS):
                unknown = True
            elif kind == "RESERVE" and not unknown and ticket is None and valid_ticket(body, rows[0]["sha256"]):
                ticket = body
            elif kind == "SEND_BEGIN" and not unknown and ticket is not None and phase is None and body == ticket:
                phase = "BEGIN"
            elif kind == "SEND_ENTRY" and not unknown and phase == "BEGIN" and body == ticket:
                phase = "ENTRY"
            elif kind == "SEND_RETURN" and not unknown and phase == "ENTRY" and body == ticket:
                phase = "RETURN"
            else:
                raise Denied("WAL_TRANSITION")
        return rows, ready, ticket, phase, unknown

    def admit(self):
        if not self.entered or self.poison or self.pending_unknown or safe(self.intent).exists():
            raise Denied("UNKNOWN_OR_PERSISTENCE_UNCERTAIN")
        state = self.state()
        if state[-1] or state[-2] is not None:
            raise Denied("UNKNOWN_OR_SEND_ALREADY_ADMITTED")
        return state

    def reserve(self, domain, role, request_digest):
        with self.mutex:
            rows, _, existing, _, _ = self.admit()
            if existing is not None or domain not in DOMAINS or role not in ROLES or request_digest != digest(PAYLOAD):
                raise Denied("RESERVATION_DENIED")
            ticket = {"domain": domain, "role": role, "request_sha256": request_digest}
            ticket["id"] = digest(canonical({"ready": rows[0]["sha256"], "ticket": ticket}))
            self.append("RESERVE", ticket, rows)
            return ticket

    def observe_unknown(self, domain):
        with self.mutex:
            if not self.entered or domain not in DOMAINS:
                raise Denied("UNKNOWN_SCOPE")
            if self.pending_unknown or safe(self.intent).exists():
                return
            self.pending_unknown = True
            try:
                exclusive(self.intent, canonical({"domain": domain}))
                rows, *_ = self.state()
                self.append("UNKNOWN_OBSERVED", {"domain": domain}, rows)
            except (OSError, ValueError):
                self.poison = True
                raise

    def send(self, ticket, payload):
        from .provider_transport import connected_receiver, executable_identity
        with self.mutex:
            rows, ready, current, _, _ = self.admit()
            if current is None or ticket != current or type(payload) is not bytes or payload != PAYLOAD:
                raise Denied("TICKET_OR_PAYLOAD")
            with connected_receiver(self.case, ready["receiver"]) as connection:
                self.append("SEND_BEGIN", current, rows)
                self.append("SEND_ENTRY", current, read_wal(self.wal))
                start = time.monotonic_ns()
                try:
                    connection.sendall(payload)
                except OSError:
                    self.poison = True
                    raise
                exclusive(self.root / "sender-receipt.json", canonical({
                    "case": self.case, "pid": os.getpid(), "exe_sha256": executable_identity(),
                    "ticket_id": current["id"], "receiver_nonce": ready["receiver"]["nonce"],
                    "bytes": len(payload), "sha256": digest(payload), "entry_ns": start,
                    "return_ns": time.monotonic_ns(), "status": "SENDALL_RETURNED",
                }))
                self.append("SEND_RETURN", current, read_wal(self.wal))

    def reconcile(self):
        """Read existing transport evidence without opening a connection."""
        from .provider_transport import read_json
        with self.mutex:
            try:
                _, ready, _, phase, _ = self.state()
                folder = safe(ROOT / "receivers" / self.case)
                receipt = read_json(folder / "receiver-receipt.json")
                with safe(folder / "received.raw").open("rb") as stream:
                    raw = stream.read(4097)
                if (receipt["ready"] != ready["receiver"] or receipt["bytes"] != len(raw)
                        or len(raw) > 4096 or receipt["sha256"] != digest(raw)):
                    return "INCONCLUSIVE"
                if raw:
                    return "RECEIVED" if phase == "RETURN" and raw == PAYLOAD else "INCONCLUSIVE"
                return "NO_BYTES_OBSERVED"
            except (OSError, ValueError, TypeError, KeyError):
                return "INCONCLUSIVE"


def valid_ticket(ticket, ready_hash):
    if not isinstance(ticket, dict) or set(ticket) != {"domain", "role", "request_sha256", "id"}:
        return False
    core = {key: ticket[key] for key in ("domain", "role", "request_sha256")}
    return (core["domain"] in DOMAINS and core["role"] in ROLES and core["request_sha256"] == digest(PAYLOAD)
            and ticket["id"] == digest(canonical({"ready": ready_hash, "ticket": core})))

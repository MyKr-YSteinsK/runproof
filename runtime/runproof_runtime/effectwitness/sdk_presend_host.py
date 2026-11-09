"""Single-writer Host and bound loopback transport."""
from contextlib import contextmanager
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import socket
import struct
import threading
import time

from .sdk_presend_contracts import (BUDGET, CALL, LIMIT, TOOL, Denied, bounded, canonical, check,
                                   exclusive, identity, response, safe, sha, strict, sync_dir,
                                   tool_value, validate_request)


@contextmanager
def file_lock(path):
    with safe(path).open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class Journal:
    def __init__(self, folder, case, *, fault=None):
        self.folder = safe(folder)
        self.case = case
        self.wal = self.folder / "wal.jsonl"
        self.active = self.folder / "active"
        self.intent = self.folder / "unknown-intent.json"
        self.fault = fault
        self.poison = False
        self.pending_unknown = False
        self.opened = False

    @contextmanager
    def open(self, *, create=False):
        with file_lock(self.folder / "writer.lock"):
            check(not safe(self.active).exists(), "PERSISTENCE_UNCERTAIN")
            exclusive(self.active, canonical({"pid": os.getpid()}))
            self.opened = True
            try:
                if create:
                    self.append("READY", {"case": self.case, "owner": self.folder.parent.name,
                                          "source": identity(), "budget": BUDGET[self.case]}, [])
                self.rows()
                yield self
            except BaseException:
                self.poison = True
                raise
            finally:
                self.opened = False
                if not self.poison:
                    self.active.unlink()
                    sync_dir(self.folder)

    def rows(self):
        raw = bounded(self.wal, 131072)
        check(raw and raw.endswith(b"\n"), "TORN_WAL")
        rows = []
        previous = "0" * 64
        for line in raw.split(b"\n")[:-1]:
            row = strict(line)
            core = {"seq": len(rows), "prev": previous, "kind": row["kind"], "body": row["body"]}
            check(type(row["seq"]) is int and row == {**core, "sha256": sha(canonical(core))}
                  and line == canonical(row) and len(rows) < 40, "WAL_CHAIN")
            rows.append(row)
            previous = row["sha256"]
        check(rows[0]["kind"] == "READY" and rows[0]["body"] == {
            "case": self.case, "owner": self.folder.parent.name, "source": identity(),
            "budget": BUDGET[self.case]}, "WAL_IDENTITY")
        # Recovery never treats a half-completed physical attempt as unused capacity.
        pending = None
        unknown = False
        for row in rows[1:]:
            kind, body = row["kind"], row["body"]
            if kind == "UNKNOWN_OBSERVED":
                unknown = True
            if kind == "PROVIDER_RESERVE":
                check(not unknown and pending is None, "WAL_RESERVE_ORDER")
                pending = ("RESERVED", body)
            elif kind in ("SEND_BEGIN", "SEND_ENTRY", "SEND_RETURN"):
                before = {"SEND_BEGIN": "RESERVED", "SEND_ENTRY": "SEND_BEGIN", "SEND_RETURN": "SEND_ENTRY"}[kind]
                check(not unknown and pending == (before, body), "WAL_SEND_ORDER")
                pending = None if kind == "SEND_RETURN" else (kind, body)
        return rows

    def append(self, kind, body, rows=None):
        check(self.opened and not self.poison, "PERSISTENCE_UNCERTAIN")
        rows = self.rows() if rows is None else rows
        core = {"seq": len(rows), "prev": rows[-1]["sha256"] if rows else "0" * 64, "kind": kind, "body": body}
        row = {**core, "sha256": sha(canonical(core))}
        try:
            if self.fault == "write" and kind == "UNKNOWN_OBSERVED":
                raise OSError("INJECTED_WRITE")
            with safe(self.wal).open("ab" if rows else "xb") as f:
                f.write(canonical(row) + b"\n")
                f.flush()
                if self.fault == "flush" and kind == "UNKNOWN_OBSERVED":
                    raise OSError("INJECTED_FLUSH")
                os.fsync(f.fileno())
            sync_dir(self.folder)
        except OSError:
            self.poison = True
            raise

    def unknown(self):
        self.pending_unknown = True
        try:
            exclusive(self.intent, canonical({"case": self.case, "call_id": CALL}))
            self.append("UNKNOWN_OBSERVED", {"call_id": CALL})
        except BaseException:
            self.poison = True
            raise

    def admit(self):
        check(self.opened and not self.poison and not self.pending_unknown
              and not safe(self.intent).exists(), "UNKNOWN_OR_PERSISTENCE_UNCERTAIN")
        rows = self.rows()
        check(not any(r["kind"] == "UNKNOWN_OBSERVED" for r in rows), "UNKNOWN_DURABLE")
        return rows

    def reserve(self, request_sha, domain="order", role="TARGET"):
        rows = self.admit()
        count = sum(row["kind"] == "PROVIDER_RESERVE" for row in rows)
        completed = sum(row["kind"] == "SEND_RETURN" for row in rows)
        check(count == completed and count < BUDGET[self.case]
              and domain in ("order", "ops") and role in ("TARGET", "EXPLORER"), "TICKET_BUDGET")
        check(isinstance(request_sha, str) and len(request_sha) == 64
              and all(c in "0123456789abcdef" for c in request_sha), "REQUEST_DIGEST")
        ticket = {"number": count + 1, "domain": domain, "role": role, "request_sha256": request_sha}
        ticket["id"] = sha(canonical({"ready": rows[0]["sha256"], "ticket": ticket}))
        self.append("PROVIDER_RESERVE", ticket, rows)
        return ticket

    def begin(self, ticket, raw):
        rows = self.admit()
        reserves = [r["body"] for r in rows if r["kind"] == "PROVIDER_RESERVE"]
        sends = [r["body"] for r in rows if r["kind"] == "SEND_BEGIN"]
        check(reserves and reserves[-1] == ticket and ticket not in sends and sha(raw) == ticket["request_sha256"],
              "TICKET_BINDING")
        self.append("SEND_BEGIN", ticket, rows)


def read_exact(sock, count):
    result = bytearray()
    while len(result) < count:
        data = sock.recv(count - len(result))
        check(bool(data), "TRUNCATED_TRANSPORT")
        result.extend(data)
    return bytes(result)


def transfer(journal, ticket, raw, ready):
    stored = strict(bounded(journal.folder / "receiver-ready.json", 4096))
    launch = strict(bounded(journal.folder / "receiver-launch.json", 4096))
    check(stored == ready and ready["host"] == "127.0.0.1" and ready["case"] == journal.case
          and ready["owner"] == journal.folder.parent.name and launch["pid"] == ready["pid"]
          and launch["nonce"] == ready["nonce"] and launch["exe_sha256"] == ready["exe_sha256"]
          and type(ready["port"]) is int and 0 < ready["port"] < 65536
          and not safe(journal.folder / "receiver-exit.json").exists(), "RECEIVER_IDENTITY")
    journal.begin(ticket, raw)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(4)
        sock.connect(("127.0.0.1", ready["port"]))
        check(hmac.compare_digest(read_exact(sock, 64), ready["nonce"].encode("ascii")), "RECEIVER_NONCE")
        journal.append("SEND_ENTRY", ticket)
        start = time.monotonic_ns()
        sock.sendall(struct.pack("!I", len(raw)) + raw)
        returned = time.monotonic_ns()
        journal.append("SEND_RETURN", ticket)
        check(read_exact(sock, 64).decode("ascii") == sha(raw), "RECEIVER_ACK")
        exclusive(journal.folder / f"sender-{ticket['number']}.json", canonical({
            "pid": os.getpid(), "ticket": ticket, "nonce": ready["nonce"], "bytes": len(raw),
            "sha256": sha(raw), "entry_ns": start, "return_ns": returned,
        }))


class Session:
    def __init__(self, journal, ready):
        self.journal = journal
        self.ready = ready
        self.lock = threading.Lock()
        self.posts = 0
        self.called = False
        self.failure = None

    def handle(self, path, raw):
        with self.lock:
            if path == "/tool":
                check(self.posts == 1 and not self.called and strict(raw) == {"call_id": CALL, "name": TOOL},
                      "TOOL_CALLBACK")
                if self.journal.case == "UNKNOWN":
                    self.journal.unknown()  # Commit before making UNKNOWN visible to the SDK.
                result = tool_value(self.journal.case)
                self.journal.append("TOOL_RETURN_TO_SDK", {"call_id": CALL, "value": result})
                self.called = True
                return 200, result
            check(path == "/v1/chat/completions" and self.posts < 2, "ROUTE_OR_INBOUND_BUDGET")
            number = self.posts + 1
            validate_request(raw, number, self.journal.case)
            check(number == 1 or self.called, "TOOL_RETURN_REQUIRED")
            exclusive(self.journal.folder / f"sdk-post-{number}.raw", raw)
            self.journal.append("SDK_POST_RECEIVED", {"number": number, "sha256": sha(raw), "bytes": len(raw)})
            self.posts = number
            try:
                ticket = self.journal.reserve(sha(raw))
            except Denied as exc:
                check(self.journal.case == "UNKNOWN" and number == 2
                      and str(exc) == "UNKNOWN_OR_PERSISTENCE_UNCERTAIN"
                      and any(row["kind"] == "UNKNOWN_OBSERVED" and row["body"] == {"call_id": CALL}
                              for row in self.journal.rows()),
                      "UNEXPECTED_ADMISSION_FAILURE")
                self.journal.append("DENY", {"number": number, "reason": "UNKNOWN_DURABLE"})
                return 409, {"error": {"message": "UNKNOWN_DURABLE", "type": "local_admission_denied",
                                       "code": "UNKNOWN_DURABLE"}}
            transfer(self.journal, ticket, raw, self.ready)
            scripted = response(self.journal.case, number)
            self.journal.append("SCRIPTED_MODEL_RESPONSE", {"number": number, "response_id": scripted["id"],
                                                            "sha256": sha(canonical(scripted))})
            return 200, scripted


def http_server(session, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            try:
                check(self.client_address[0] == "127.0.0.1"
                      and self.headers.get_all("Host") == [f"127.0.0.1:{self.server.server_port}"]
                      and self.headers.get_all("Authorization") == ["Bearer " + token]
                      and self.headers.get_all("Content-Type") == ["application/json"]
                      and not self.headers.get_all("Transfer-Encoding"), "HTTP_ADMISSION")
                lengths = self.headers.get_all("Content-Length")
                check(lengths and len(lengths) == 1 and lengths[0].isascii() and lengths[0].isdigit()
                      and len(lengths[0]) <= 6, "CONTENT_LENGTH")
                size = int(lengths[0])
                check(0 < size <= LIMIT, "CONTENT_LIMIT")
                body = self.rfile.read(size)
                check(len(body) == size, "TRUNCATED_HTTP")
                code, result = session.handle(self.path, body)
            except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
                if session.failure is None:
                    if type(exc) is Denied:
                        session.failure = str(exc)
                    elif isinstance(exc, (ValueError, KeyError, TypeError, AttributeError, RecursionError)):
                        session.failure = type(exc).__name__
                    else:
                        session.failure = "HOST_IO_FAILURE"
                session.journal.poison = True
                code, result = 400, {"error": {"message": "LOCAL_GUARD_REJECTED", "type": "guard_error"}}
            raw = canonical(result)
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    class Server(HTTPServer):
        allow_reuse_address = False

        def get_request(self):
            conn, addr = super().get_request()
            conn.settimeout(5)
            return conn, addr

    return Server(("127.0.0.1", 0), Handler)

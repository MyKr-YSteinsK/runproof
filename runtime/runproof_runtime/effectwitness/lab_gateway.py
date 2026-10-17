"""Explicitly enabled loopback-only HTTP Gateway. Server secret never enters DTOs."""
import argparse
import hmac
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .contracts import canonical
from .lab_store import LabError, SCHEMA, SessionStore

PREFIX = "/effectwitness-api"


class Gateway(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, port, token, origin, store):
        if len(token) < 32 or origin not in ("http://127.0.0.1:4185", "http://localhost:4185"):
            raise ValueError("GATEWAY_CONFIGURATION_REJECTED")
        self.token, self.origin, self.store = token, origin, store
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(("127.0.0.1", port), Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # No stack/body/path/credentials in ordinary HTTP logs.


class Handler(BaseHTTPRequestHandler):
    server_version = "RunProofLocalLab/1"
    sys_version = ""

    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def reply(self, status, value, raw=False):
        data = value if raw else canonical(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if raw:
            self.send_header("Content-Disposition", 'attachment; filename="effectwitness.json"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def do_OPTIONS(self):
        self.reply(403, {"schema_version": SCHEMA, "error_code": "CROSS_ORIGIN_NOT_ALLOWED"})

    def route(self):
        try:
            raw_body = None
            if self.command == "POST":
                sizes = self.headers.get_all("Content-Length")
                if (self.headers.get("Transfer-Encoding") or not sizes or len(sizes) != 1
                        or len(sizes[0]) > 6 or not sizes[0].isdigit()):
                    raise LabError(413, "BODY_SIZE_REJECTED")
                size = int(sizes[0])
                # Drain only a small bounded transport body before an early denial.
                # On Windows, closing with unread POST bytes can reset the socket
                # before the client receives the 401/403 response. No JSON is
                # interpreted and no session is reserved before authentication.
                if 0 < size <= 4096:
                    raw_body = self.rfile.read(size)
                if not 0 < size <= 1024:
                    raise LabError(413, "BODY_SIZE_REJECTED")
                if len(raw_body) != size:
                    raise LabError(400, "REQUEST_BODY_INCOMPLETE")
            port = self.server.server_port
            if self.headers.get_all("Host") not in ([f"127.0.0.1:{port}"], [f"localhost:{port}"]):
                raise LabError(403, "HOST_REJECTED")
            authorizations = self.headers.get_all("Authorization")
            if not authorizations or len(authorizations) != 1 or not hmac.compare_digest(authorizations[0], "Bearer " + self.server.token):
                raise LabError(401, "AUTH_REQUIRED")
            # Require the original same-origin browser write header; CLI reads may omit Origin.
            origins = self.headers.get_all("Origin")
            if (origins is not None and origins != [self.server.origin]) or (self.command == "POST" and not origins):
                raise LabError(403, "ORIGIN_REJECTED")
            if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
                raise LabError(403, "CROSS_SITE_REJECTED")
            if self.headers.get("Transfer-Encoding") or len(self.path) > 200:
                raise LabError(400, "REQUEST_REJECTED")
            body = None
            if self.command == "POST":
                if self.headers.get_all("Content-Type") != ["application/json"]:
                    raise LabError(415, "JSON_CONTENT_TYPE_REQUIRED")
                from .witness_verify import _unique_object
                try:
                    body = json.loads(raw_body, object_pairs_hook=_unique_object)
                except (ValueError, UnicodeDecodeError):
                    raise LabError(400, "JSON_REJECTED")
            path = self.path
            if self.command == "GET" and path == PREFIX + "/capabilities":
                self.reply(200, self.server.store.capabilities())
            elif path.startswith(PREFIX + "/explorations"):
                live = self.server.store.exploration
                if self.command == "GET" and path == PREFIX + "/explorations/capabilities":
                    self.reply(200, live.capabilities() if live else {"schema_version": "rpf-lab-exploration-v1",
                        "explorer": "DISABLED", "enabled": False, "remaining_sessions": 0, "busy": False,
                        "limits": {}, "requested_model": "deepseek-flash", "physical_trials": 2})
                elif live is None:
                    raise LabError(409, "PAID_EXPLORER_DISABLED")
                elif self.command == "POST" and path == PREFIX + "/explorations":
                    self.reply(202, live.create(body))
                else:
                    match = re.fullmatch(PREFIX + r"/explorations/(exploration-[a-f0-9]{32})(/cancel|/witness/[12])?", path)
                    if not match:
                        raise LabError(404, "ROUTE_NOT_FOUND")
                    sid, action = match.groups()
                    if self.command == "GET" and action is None:
                        self.reply(200, live.get(sid))
                    elif self.command == "GET" and action and action.startswith("/witness/"):
                        self.reply(200, live.witness(sid, action[-1]), raw=True)
                    elif self.command == "POST" and action == "/cancel" and body == {}:
                        self.reply(200, live.cancel(sid))
                    else:
                        raise LabError(400, "REQUEST_REJECTED")
            elif self.command == "POST" and path == PREFIX + "/sessions":
                self.reply(202, self.server.store.create(body))
            else:
                match = re.fullmatch(PREFIX + r"/sessions/(session-[a-f0-9]{32})(/witness|/cancel)?", path)
                if not match:
                    raise LabError(404, "ROUTE_NOT_FOUND")
                sid, action = match.groups()
                if self.command == "GET" and action is None:
                    self.reply(200, self.server.store.get(sid))
                elif self.command == "GET" and action == "/witness":
                    self.reply(200, self.server.store.witness(sid), raw=True)
                elif self.command == "POST" and action == "/cancel" and body == {}:
                    self.reply(200, self.server.store.cancel(sid))
                else:
                    raise LabError(400, "REQUEST_REJECTED")
        except LabError as error:
            self.reply(error.status, {"schema_version": SCHEMA, "error_code": error.code})
        except Exception:
            self.reply(503, {"schema_version": SCHEMA, "error_code": "GATEWAY_UNAVAILABLE"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-local-simulation", action="store_true")
    parser.add_argument("--enable-paid-order-pge", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not args.enable_local_simulation:
        parser.error("Explicit --enable-local-simulation required")
    token = os.environ.get("RPF_EW_LAB_GATEWAY_TOKEN", "")
    store = SessionStore()
    try:
        if args.enable_paid_order_pge:
            from .lab_exploration import ExplorationStore
            ExplorationStore(store, enabled=True)
        server = Gateway(args.port, token, "http://127.0.0.1:4185", store)
        print("Local controlled Lab listening on 127.0.0.1:" + str(server.server_port), flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        store.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Local Lab stopped: " + (error.code if isinstance(error, LabError) else "GATEWAY_CONFIGURATION_OR_RUNTIME_UNAVAILABLE"))
        raise SystemExit(2)

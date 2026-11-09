"""Loopback-only API. Browser admission is enforced by the opt-in proxy."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import re
import sqlite3

from .product_local_contracts import REQUEST, SESSION, canonical, strict
from .product_local_session import Conflict, Product, ROOT, file_sha, safe_path
from .product_local_verify import MAX_WITNESS

PREFIX = "/effectwitness-product-api"
ORIGIN = "http://127.0.0.1:4187"


def server_for(product, token, port=8780):
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{64}", token):
        raise ValueError("GATEWAY_TOKEN_REQUIRED")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, data):
            self.send_bytes(code, canonical(data))

        def send_bytes(self, code, data, *, witness=False):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if witness:
                self.send_header("Content-Disposition", 'attachment; filename="rpf100-witness.json"')
                self.send_header("X-Witness-SHA256", file_sha(data))
            self.end_headers()
            self.wfile.write(data)

        def admitted(self, post=False):
            origin = self.headers.get_all("Origin", [])
            if (self.client_address[0] != "127.0.0.1"
                    or self.headers.get_all("Host", []) != [f"127.0.0.1:{self.server.server_port}"]
                    or origin not in ([ORIGIN], [] if not post else [ORIGIN])):
                self.reply(403, {"error": "ORIGIN_REJECTED"})
                return False
            auth = self.headers.get_all("Authorization", [])
            if len(auth) != 1 or not hmac.compare_digest(auth[0].encode(), ("Bearer " + token).encode()):
                self.reply(403, {"error": "GATEWAY_AUTH_REQUIRED"})
                return False
            return True

        def do_GET(self):
            if not self.admitted():
                return
            try:
                if self.path == PREFIX + "/capability":
                    self.reply(200, product.capability())
                    return
                match = re.fullmatch(re.escape(PREFIX) + r"/(session|request|witness)/([a-zA-Z0-9_-]+)", self.path)
                if match:
                    kind, identity = match.groups()
                    valid = REQUEST if kind == "request" else SESSION
                    if valid.fullmatch(identity):
                        data, witness = product.lookup("request" if kind == "request" else "id", identity)
                        if kind == "witness" and witness and len(witness) <= MAX_WITNESS:
                            self.send_bytes(200, witness, witness=True)
                            return
                        if kind != "witness" and data is not None:
                            self.reply(200, data)
                            return
                self.reply(404, {"error": "NOT_FOUND"})
            except (OSError, sqlite3.Error, ValueError):
                self.reply(503, {"error": "READBACK_UNAVAILABLE"})

        def do_POST(self):
            if not self.admitted(post=True):
                return
            if self.path != PREFIX + "/session":
                self.reply(404, {"error": "NOT_FOUND"})
                return
            lengths = self.headers.get_all("Content-Length", [])
            if (self.headers.get_all("Content-Type", []) != ["application/json"]
                    or self.headers.get_all("Transfer-Encoding") or len(lengths) != 1
                    or not re.fullmatch(r"[0-9]{1,6}", lengths[0])):
                self.reply(400, {"error": "INVALID_BODY"})
                return
            length = int(lengths[0])
            if not 0 < length <= 4096:
                self.reply(413, {"error": "BODY_LIMIT"})
                return
            try:
                data = self.rfile.read(length)
                if len(data) != length:
                    raise ValueError("BODY_TRUNCATED")
                self.reply(200, product.create(strict(data)))
            except Conflict:
                self.reply(409, {"error": "SESSION_NOT_ADMITTED"})
            except (ValueError, RecursionError):
                self.reply(400, {"error": "INVALID_REQUEST"})
            except (OSError, sqlite3.Error):
                self.reply(503, {"error": "RECONCILE_REQUIRED"})

    class Server(HTTPServer):
        allow_reuse_address = False

        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(5)
            return connection, address

    return Server(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", type=Path, required=True)
    args = parser.parse_args()
    owner = safe_path(args.owner)
    if owner != ROOT / "live" or not safe_path(owner / "rpf100-owner-v1").is_file():
        raise SystemExit("LIVE_OWNER_REQUIRED")
    with Product(owner).open() as product:
        with server_for(product, os.environ.get("RPF100_GATEWAY_TOKEN")) as server:
            print("RPF100_GATEWAY_READY", flush=True)
            server.serve_forever()


if __name__ == "__main__":
    main()

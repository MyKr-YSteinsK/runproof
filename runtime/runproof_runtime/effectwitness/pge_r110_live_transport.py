"""One explicitly connected HTTP request, with distinct native and loopback entry points."""
from contextlib import closing
import http.client
import ssl
from time import monotonic_ns

from . import pge_r110_live_contracts as c
from .sdk_presend_contracts import check, sha


def _remaining(deadline):
    seconds = (deadline - monotonic_ns()) / 10**9
    check(seconds > 0, "HTTP_DEADLINE")
    return seconds


def _exchange(edge, permit, raw, view, mode, timeout, connection, headers):
    entry = edge.enter(permit, raw, view, mode)
    start = entry["entered_ns"]
    deadline = start + timeout * 10**9
    try:
        with closing(connection(_remaining(deadline))) as conn:
            conn.connect()  # DNS/TLS only after the durable entry.
            connected = monotonic_ns()
            wire = conn.sock
            check(wire is not None, "HTTP_CONNECT")
            tls = wire.version() if mode == c.NATIVE else None
            check(mode != c.NATIVE or tls in ("TLSv1.2", "TLSv1.3"), "TLS_VERSION")
            conn.auto_open = 0  # No implicit reconnect from HTTPConnection.send().
            wire.settimeout(_remaining(deadline))
            conn.request("POST", c.PATH, body=raw, headers=headers)
            sent = monotonic_ns()
            wire.settimeout(_remaining(deadline))
            # Keep ownership of the connected socket through the bounded body read.
            # getresponse() detaches it immediately when the response says Connection: close.
            with closing(http.client.HTTPResponse(wire, method="POST")) as response:
                response.begin()
                status = response.status
                ids = response.headers.get_all("x-request-id", [])
                encoding = response.headers.get("Content-Encoding", "identity").lower()
                check(len(ids) <= 1 and encoding == "identity", "HTTP_HEADERS")
                chunks, remaining = [], c.RESPONSE_CAP + 1
                while remaining > 0:
                    wire.settimeout(_remaining(deadline))
                    data = response.read1(min(remaining, 8192))
                    if not data:
                        break
                    chunks.append(data)
                    remaining -= len(data)
                body = b"".join(chunks)
                check(len(body) <= c.RESPONSE_CAP and response.length in (0, None), "HTTP_BODY_BOUND")
            _remaining(deadline)
            ended = monotonic_ns()
        return body, {"ticket": entry["ticket"], "kind": mode, "entered_ns": start, "connected_ns": connected,
                      "post_returned_ns": sent, "response_ns": ended, "tls_version": tls,
                      "tls_verified": mode == c.NATIVE, "status": status, "response_size": len(body),
                      "response_sha256": sha(body), "header_request_id": ids[0] if ids else "UNAVAILABLE"}
    except (OSError, ValueError, http.client.HTTPException):
        edge.uncertain("TRANSPORT")
        raise


def _native_connection(seconds):
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    check(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED, "TLS_CONTEXT")
    return http.client.HTTPSConnection(c.HOST, c.PORT, timeout=seconds, context=context)


def native(edge, permit, raw, view, credential):
    approval = edge.contract["approval"]
    check(edge.contract["kind"] == c.NATIVE and approval is not None and type(credential) is str
          and 0 < len(credential) <= 512 and credential.isascii()
          and all(33 <= ord(char) <= 126 for char in credential), "NATIVE_ADMISSION")
    return _exchange(edge, permit, raw, view, c.NATIVE, approval["budget"]["timeout_seconds"], _native_connection,
                     {"Content-Type": "application/json", "Accept-Encoding": "identity",
                      "Connection": "close", "Authorization": "Bearer " + credential})


def loopback(edge, permit, raw, view, port):
    check(type(port) is int and 0 < port < 65536 and edge.contract["kind"] == c.STUB, "LOOPBACK_SCOPE")
    return _exchange(edge, permit, raw, view, c.STUB, 3,
                     lambda seconds: http.client.HTTPConnection("127.0.0.1", port, timeout=seconds),
                     {"Content-Type": "application/json", "Accept-Encoding": "identity", "Connection": "close"})

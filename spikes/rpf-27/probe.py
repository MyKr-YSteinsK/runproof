"""RPF-27 disposable multi-service/network-fault investigation probe.

The probe deliberately lives outside the formal Runtime.  It starts a fresh
private Docker network for each trial and uses a host-side harness as the only
fault controller.  The Agent-shaped client can reach only the data port of the
fault boundary; it never receives the control endpoint or the Docker socket.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / ".local" / "rpf-27" / "result.json"
PYTHON_IMAGE = "python:3.12-alpine"
TOXIPROXY_IMAGE = "ghcr.io/shopify/toxiproxy:2.12.0"
ENVOY_IMAGE = "envoyproxy/envoy:v1.31-latest"
ENVIRONMENT_CONTRACT = "rpf-27-multi-service-network-environment-v1"
FAULT_CONTRACT = "rpf-network-fault-provenance-v1"
SCENARIOS = ("baseline", "latency-timeout", "dependency-unavailable", "response-lost")
REQUIRED_RESPONSE_LOST_REPEATS = 3


class ProbeError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_sha256() -> str:
    digest = hashlib.sha256()
    for path in (Path(__file__), ROOT / "spikes" / "rpf-27" / "verify-evidence.py"):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def classify_transport_error(error: BaseException) -> str:
    text = str(error).lower()
    if isinstance(error, TimeoutError) or "timed out" in text or "timeout" in text:
        return "TIMEOUT"
    if "reset" in text or "remote end closed" in text or "unexpected eof" in text:
        return "CONNECTION_RESET"
    if "refused" in text or "unreachable" in text or "name or service" in text:
        return "CONNECTION_UNAVAILABLE"
    return "TRANSPORT_ERROR"


def http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: float = 3.0) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"raw_body_present": bool(raw)}
            return {"transport_ok": True, "status": int(response.status), "body": parsed}
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw_body_present": bool(raw)}
        return {"transport_ok": True, "status": int(error.code), "body": parsed}
    except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError) as error:
        return {"transport_ok": False, "error_kind": classify_transport_error(error)}


def request_data(host_port: int, method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 2.0) -> dict[str, Any]:
    return http_json(method, f"http://127.0.0.1:{host_port}{path}", payload, timeout)


def docker_exec_json_get(container: str, path: str) -> dict[str, Any]:
    script = (
        "import json,urllib.request; "
        f"r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8080{path}', method='GET'), timeout=1.5); "
        "print(r.read().decode('utf-8'))"
    )
    raw = docker(["exec", container, "python", "-c", script], timeout=5.0, code="OBSERVER_READ_FAILED")
    try:
        return {"transport_ok": True, "status": 200, "body": json.loads(raw)}
    except json.JSONDecodeError as error:
        raise ProbeError("OBSERVER_RESPONSE_MALFORMED") from error


def docker_client_request(container: str, method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 2.0) -> dict[str, Any]:
    encoded_payload = repr(payload) if payload is not None else "None"
    script = f"""
import json, socket, urllib.error, urllib.request
payload = {encoded_payload}
body = json.dumps(payload, separators=(',', ':')).encode('utf-8') if payload is not None else None
request = urllib.request.Request('http://fault-boundary:8080{path}', data=body, headers={{'Content-Type': 'application/json', 'Accept': 'application/json'}}, method={method!r})
try:
    with urllib.request.urlopen(request, timeout={timeout!r}) as response:
        raw = response.read().decode('utf-8', errors='replace')
        try:
            parsed = json.loads(raw) if raw else {{}}
        except json.JSONDecodeError:
            parsed = {{'raw_body_present': bool(raw)}}
        result = {{'transport_ok': True, 'status': int(response.status), 'body': parsed}}
except urllib.error.HTTPError as error:
    raw = error.read().decode('utf-8', errors='replace')
    try:
        parsed = json.loads(raw) if raw else {{}}
    except json.JSONDecodeError:
        parsed = {{'raw_body_present': bool(raw)}}
    result = {{'transport_ok': True, 'status': int(error.code), 'body': parsed}}
except (TimeoutError, socket.timeout):
    result = {{'transport_ok': False, 'error_kind': 'TIMEOUT'}}
except (urllib.error.URLError, ConnectionError, OSError) as error:
    text = str(error).lower()
    result = {{'transport_ok': False, 'error_kind': 'CONNECTION_RESET' if 'reset' in text or 'remote end closed' in text else 'CONNECTION_UNAVAILABLE' if 'refused' in text or 'unreachable' in text else 'TRANSPORT_ERROR'}}
print(json.dumps(result, separators=(',', ':')))
"""
    raw = docker(["exec", container, "python", "-c", script], timeout=max(8.0, timeout + 5.0), code="CLIENT_REQUEST_FAILED")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ProbeError("CLIENT_RESPONSE_MALFORMED") from error


def docker(args: list[str], timeout: float = 30.0, code: str = "DOCKER_COMMAND_FAILED", check: bool = True) -> str:
    try:
        completed = subprocess.run(
            ["docker", *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        if check:
            raise ProbeError(code) from error
        return ""
    if completed.returncode != 0 and check:
        raise ProbeError(code)
    return completed.stdout.strip()


def docker_optional(args: list[str]) -> bool:
    return bool(docker(args, timeout=15.0, check=False))


def docker_command_ok(args: list[str], timeout: float = 20.0) -> bool:
    try:
        completed = subprocess.run(
            ["docker", *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def image_snapshot(reference: str) -> dict[str, Any]:
    raw = docker(["image", "inspect", reference], code="IMAGE_UNAVAILABLE")
    try:
        item = json.loads(raw)[0]
    except (IndexError, json.JSONDecodeError) as error:
        raise ProbeError("IMAGE_METADATA_UNAVAILABLE") from error
    return {
        "reference": reference,
        "id": item.get("Id"),
        "repo_digests": item.get("RepoDigests", []),
    }


def provider_snapshot() -> dict[str, Any]:
    version = docker(["version", "--format", "client={{.Client.Version}}|server={{.Server.Version}}"], code="DOCKER_DAEMON_UNAVAILABLE")
    context = docker(["context", "show"], code="DOCKER_CONTEXT_UNAVAILABLE")
    info = docker(["info", "--format", "{{.Driver}}|{{.OSType}}|{{.ServerVersion}}"], code="DOCKER_INFO_UNAVAILABLE")
    driver, os_type, server_version = (info.split("|", 2) + [""])[:3]
    client_version, daemon_version = (version.split("|", 1) + [""])[:2]
    return {
        "provider": "docker",
        "context": context,
        "daemon_ready": True,
        "client_version": client_version.removeprefix("client="),
        "server_version": daemon_version.removeprefix("server="),
        "info_server_version": server_version,
        "storage_driver": driver,
        "os_type": os_type,
        "python_image": image_snapshot(PYTHON_IMAGE),
        "toxiproxy_image": image_snapshot(TOXIPROXY_IMAGE),
        "envoy_image": image_snapshot(ENVOY_IMAGE),
    }


def encoded_python_command(source: str) -> list[str]:
    encoded = base64.b64encode(source.encode("utf-8")).decode("ascii")
    return ["python", "-u", "-c", f"import base64;exec(base64.b64decode({encoded!r}))"]


TARGET_SERVICE = r'''
import json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

LOCK = threading.Lock()
STATE = {
    "service_id": "incident-target",
    "service_revision": "rpf27-target-v1",
    "dependency_id": "incident-dependency",
    "dependency_checks": 0,
    "dependency_available": True,
    "mutation_requests": 0,
    "duplicate_operation_requests": 0,
    "effect_count": 0,
    "receipts": {},
    "last_operation_id": None,
    "last_dependency_result": "NOT_CHECKED",
}

def reply(handler, status, value):
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)

def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    return json.loads(handler.rfile.read(length).decode("utf-8")) if length else {}

def snapshot():
    with LOCK:
        return json.loads(json.dumps(STATE))

def dependency_check():
    with LOCK:
        STATE["dependency_checks"] += 1
    try:
        response = urlopen(Request("http://incident-dependency:8081/check", method="GET"), timeout=0.35)
        response.read()
        with LOCK:
            STATE["dependency_available"] = True
            STATE["last_dependency_result"] = "AVAILABLE"
        return True
    except (URLError, HTTPError, TimeoutError, OSError):
        with LOCK:
            STATE["dependency_available"] = False
            STATE["last_dependency_result"] = "UNAVAILABLE"
        return False

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def do_GET(self):
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/health":
            delay = min(int(query.get("delay_ms", ["0"])[0]), 5000)
            if delay:
                time.sleep(delay / 1000.0)
            reply(self, 200, {"status": "HEALTHY", "service_id": "incident-target"})
            return
        if parsed.path == "/state":
            reply(self, 200, snapshot())
            return
        if parsed.path == "/reconcile":
            operation_id = query.get("operation_id", [""])[0]
            current = snapshot()
            receipt = current["receipts"].get(operation_id)
            if receipt is None:
                reply(self, 404, {"status": "ABSENT", "operation_id": operation_id, "effect_count": current["effect_count"]})
            else:
                reply(self, 200, {"status": "APPLIED", "operation_id": operation_id, "receipt": receipt, "effect_count": current["effect_count"]})
            return
        reply(self, 404, {"status": "NOT_FOUND"})

    def do_POST(self):
        parsed = urlsplit(self.path)
        if parsed.path != "/mutate":
            reply(self, 404, {"status": "NOT_FOUND"})
            return
        payload = read_json(self)
        operation_id = payload.get("operation_id")
        hold_response_ms = min(int(payload.get("hold_response_ms", 0)), 5000)
        with LOCK:
            STATE["mutation_requests"] += 1
            existing = STATE["receipts"].get(operation_id)
            if existing is not None:
                STATE["duplicate_operation_requests"] += 1
        if not dependency_check():
            reply(self, 503, {"status": "DEPENDENCY_UNAVAILABLE", "operation_id": operation_id, "effect_count": snapshot()["effect_count"]})
            return
        with LOCK:
            existing = STATE["receipts"].get(operation_id)
            if existing is not None:
                reply(self, 200, {"status": "ALREADY_APPLIED", "operation_id": operation_id, "receipt": existing, "effect_count": STATE["effect_count"]})
                return
            STATE["effect_count"] += 1
            receipt = {"operation_id": operation_id, "status": "APPLIED", "effect_count": STATE["effect_count"], "committed_at": time.time()}
            STATE["receipts"][operation_id] = receipt
            STATE["last_operation_id"] = operation_id
        if hold_response_ms:
            time.sleep(hold_response_ms / 1000.0)
        reply(self, 200, {"status": "APPLIED", "operation_id": operation_id, "receipt": receipt, "effect_count": receipt["effect_count"]})

ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
'''


DEPENDENCY_SERVICE = r'''
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return
    def do_GET(self):
        status = 200 if self.path in {"/health", "/check"} else 404
        body = {"status": "HEALTHY" if status == 200 else "NOT_FOUND", "service_id": "incident-dependency"}
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

ThreadingHTTPServer(("0.0.0.0", 8081), Handler).serve_forever()
'''


CUSTOM_SHIM = r'''
import json, os, socket, threading, time
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

LOCK = threading.Lock()
FAULT = {"mode": "none", "fault_id": None, "activated_at": None, "request_count": 0, "triggered": False, "observed": False}
TARGET_HOST = os.environ.get("TARGET_HOST", "incident-target")

def reply(handler, status, value):
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)

def snapshot():
    with LOCK:
        return json.loads(json.dumps(FAULT))

class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return
    def do_GET(self):
        if self.path == "/__state":
            reply(self, 200, snapshot())
        else:
            reply(self, 404, {"status": "NOT_FOUND"})
    def do_POST(self):
        if self.path != "/__control":
            reply(self, 404, {"status": "NOT_FOUND"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        mode = payload.get("mode", "none")
        if mode not in {"none", "delay_response", "drop_response"}:
            reply(self, 400, {"status": "INVALID_MODE"})
            return
        with LOCK:
            FAULT.update({"mode": mode, "fault_id": payload.get("fault_id"), "activated_at": time.time() if mode != "none" else None, "request_count": 0, "triggered": False, "observed": False})
        reply(self, 200, snapshot())

class DataHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return
    def _forward(self):
        body_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(body_length) if body_length else None
        connection = None
        try:
            connection = HTTPConnection(TARGET_HOST, 8080, timeout=5.0)
            headers = {key: value for key, value in self.headers.items() if key.lower() not in {"host", "connection"}}
            connection.request(self.command, self.path, body=body, headers=headers)
            upstream = connection.getresponse()
            response_body = upstream.read()
            response_status = upstream.status
            response_headers = [(key, value) for key, value in upstream.getheaders() if key.lower() not in {"connection", "transfer-encoding", "content-length"}]
        except Exception:
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
            return
        finally:
            if connection is not None:
                connection.close()
        with LOCK:
            mode = FAULT["mode"]
            if mode != "none":
                FAULT["request_count"] += 1
                FAULT["triggered"] = True
        if mode == "delay_response":
            time.sleep(1.2)
            with LOCK:
                FAULT["observed"] = True
        if mode == "drop_response":
            with LOCK:
                FAULT["observed"] = True
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
            return
        self.send_response(response_status)
        for key, value in response_headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)
    def do_GET(self):
        self._forward()
    def do_POST(self):
        self._forward()

def run_control():
    ThreadingHTTPServer(("127.0.0.1", 8090), ControlHandler).serve_forever()

threading.Thread(target=run_control, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", 8080), DataHandler).serve_forever()
'''


def envoy_config(fault_mode: str) -> str:
    fault_filter = ""
    if fault_mode == "latency-timeout":
        fault_filter = """
            - name: envoy.filters.http.fault
              typed_config:
                '@type': type.googleapis.com/envoy.extensions.filters.http.fault.v3.HTTPFault
                delay:
                  fixed_delay: 1s
                  percentage:
                    numerator: 100
                    denominator: HUNDRED
"""
    elif fault_mode == "response-lost":
        fault_filter = """
            - name: envoy.filters.http.fault
              typed_config:
                '@type': type.googleapis.com/envoy.extensions.filters.http.fault.v3.HTTPFault
                abort:
                  http_status: 503
                  percentage:
                    numerator: 100
                    denominator: HUNDRED
"""
    filters = f"""{fault_filter if fault_filter else ''}            - name: envoy.filters.http.router
              typed_config:
                '@type': type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
"""
    return f"""static_resources:
  listeners:
  - name: rpf27_listener
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 8080
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          '@type': type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: rpf27_http
          route_config:
            name: rpf27_route
            virtual_hosts:
            - name: incident_target
              domains: ['*']
              routes:
              - match:
                  prefix: '/'
                route:
                  cluster: incident_target
          http_filters:
{filters}
  clusters:
  - name: incident_target
    connect_timeout: 1s
    type: STRICT_DNS
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: incident_target
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: incident-target
                port_value: 8080
admin:
  access_log_path: /tmp/rpf27-envoy-admin.log
  address:
    socket_address:
      address: 127.0.0.1
      port_value: 9901
"""


def safe_container_inspect(name: str) -> dict[str, Any] | None:
    raw = docker(["inspect", name], timeout=15.0, check=False)
    if not raw:
        return None
    try:
        item = json.loads(raw)[0]
    except (IndexError, json.JSONDecodeError):
        return None
    return {
        "id": item.get("Id"),
        "name": item.get("Name", "").lstrip("/"),
        "status": item.get("State", {}).get("Status"),
        "running": item.get("State", {}).get("Running") is True,
        "network_mode": item.get("HostConfig", {}).get("NetworkMode"),
        "mount_count": len(item.get("Mounts", [])),
    }


def network_exists(name: str) -> bool:
    raw = docker(["network", "inspect", name], timeout=10.0, check=False)
    if not raw or raw == "[]":
        return False
    try:
        return bool(json.loads(raw))
    except json.JSONDecodeError:
        return False


class Topology:
    def __init__(self, candidate: str, run_id: str, fault_mode: str = "none"):
        token = uuid.uuid4().hex[:8]
        self.candidate = candidate
        self.run_id = run_id
        self.fault_mode = fault_mode
        self.environment_id = f"rpf27-{candidate}-{uuid.uuid4()}"
        self.network = f"rpf27-net-{token}"
        self.target = f"rpf27-{candidate}-target-{token}"
        self.dependency = f"rpf27-{candidate}-dependency-{token}"
        self.boundary = f"rpf27-{candidate}-boundary-{token}"
        self.client = f"rpf27-{candidate}-client-{token}"
        self.target_port = None
        self.data_port = None
        self.control_port = None
        self.api_port = None
        self.created: list[str] = []
        self.network_created = False
        self.started_at = time.perf_counter()
        self.readiness_ms: float | None = None
        self.fault_history: list[dict[str, Any]] = []
        self.active_toxics: list[str] = []
        self.envoy_config_path: Path | None = None

    def _labels(self, role: str) -> list[str]:
        return [
            "--label", "com.runproof.owner=runproof",
            "--label", "com.runproof.plan=rpf-27",
            "--label", "com.runproof.lifecycle=rpf-27-spike",
            "--label", f"com.runproof.environment={self.environment_id}",
            "--label", f"com.runproof.role={role}",
        ]

    def start(self) -> dict[str, Any]:
        docker(["network", "create", "--internal", "--label", "com.runproof.owner=runproof", "--label", "com.runproof.plan=rpf-27", self.network], code="NETWORK_CREATE_FAILED")
        self.network_created = True
        self._start_service(self.dependency, "dependency", DEPENDENCY_SERVICE, 8081, None)
        self._start_service(self.target, "target", TARGET_SERVICE, 8080, None)
        if self.candidate == "custom-shim":
            self._start_custom_shim()
        elif self.candidate == "toxiproxy":
            self._start_toxiproxy()
            self._create_toxiproxy_proxy()
        else:
            self._start_envoy()
        self._start_client()
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            target = self.observer("/health")
            if self.candidate == "envoy" and self.fault_mode != "none":
                boundary = {"status": 200 if docker_command_ok(["exec", self.boundary, "envoy", "--version"], timeout=5.0) else 0}
            else:
                boundary = self.client_request("GET", "/health", timeout=0.7)
            if target.get("status") == 200 and boundary.get("status") == 200:
                self.readiness_ms = round((time.perf_counter() - self.started_at) * 1000, 2)
                return self.identity(ready=True)
            time.sleep(0.1)
        raise ProbeError("MULTI_SERVICE_READINESS_TIMEOUT")

    def _start_service(self, name: str, role: str, source: str, port: int, host_port: int | None) -> None:
        alias = "incident-target" if role == "target" else "incident-dependency"
        args = ["run", "--detach", "--pull=never", "--name", name, "--network", self.network, "--network-alias", alias]
        args += self._labels(role)
        if host_port is not None:
            args += ["--publish", f"127.0.0.1:{host_port}:{port}"]
        args += [PYTHON_IMAGE, *encoded_python_command(source)]
        docker(args, code=f"{role.upper()}_START_FAILED")
        self.created.append(name)

    def _start_client(self) -> None:
        args = ["run", "--detach", "--pull=never", "--name", self.client, "--network", self.network, "--network-alias", "agent-client"]
        args += self._labels("agent-client")
        args += [PYTHON_IMAGE, "python", "-c", "import time; time.sleep(3600)"]
        docker(args, code="CLIENT_START_FAILED")
        self.created.append(self.client)

    def _start_custom_shim(self) -> None:
        args = ["run", "--detach", "--pull=never", "--name", self.boundary, "--network", self.network, "--network-alias", "fault-boundary", "--env", "TARGET_HOST=incident-target"]
        args += self._labels("fault-boundary")
        args += [PYTHON_IMAGE, *encoded_python_command(CUSTOM_SHIM)]
        docker(args, code="CUSTOM_SHIM_START_FAILED")
        self.created.append(self.boundary)

    def _start_toxiproxy(self) -> None:
        args = ["run", "--detach", "--pull=never", "--name", self.boundary, "--network", self.network, "--network-alias", "fault-boundary"]
        args += self._labels("fault-boundary")
        args += [TOXIPROXY_IMAGE]
        docker(args, code="TOXIPROXY_START_FAILED")
        self.created.append(self.boundary)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if docker_command_ok(["exec", self.boundary, "/toxiproxy-cli", "--host", "http://localhost:8474", "--version"], timeout=5.0):
                return
            time.sleep(0.1)
        raise ProbeError("TOXIPROXY_API_READINESS_TIMEOUT")

    def _start_envoy(self) -> None:
        config_root = ROOT / ".local" / "rpf-27" / "generated"
        config_root.mkdir(parents=True, exist_ok=True)
        self.envoy_config_path = config_root / f"{self.environment_id}.yaml"
        self.envoy_config_path.write_text(envoy_config(self.fault_mode), encoding="utf-8", newline="\n")
        args = ["run", "--detach", "--pull=never", "--name", self.boundary, "--network", self.network, "--network-alias", "fault-boundary", "--mount", f"type=bind,source={self.envoy_config_path.resolve()},target=/etc/envoy/envoy.yaml,readonly"]
        args += self._labels("fault-boundary")
        args += [ENVOY_IMAGE, "-c", "/etc/envoy/envoy.yaml", "--log-level", "warning"]
        docker(args, code="ENVOY_START_FAILED")
        self.created.append(self.boundary)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if docker(["exec", self.boundary, "envoy", "--version"], timeout=5.0, check=False):
                return
            time.sleep(0.1)
        raise ProbeError("ENVOY_READINESS_TIMEOUT")

    def _create_toxiproxy_proxy(self) -> None:
        result = docker(["exec", self.boundary, "/toxiproxy-cli", "--host", "http://localhost:8474", "create", "--listen", "0.0.0.0:8080", "--upstream", "incident-target:8080", "incident-target-http"], timeout=8.0, check=False)
        if "incident-target-http" not in result:
            raise ProbeError("TOXIPROXY_PROXY_CREATE_FAILED")

    def identity(self, ready: bool) -> dict[str, Any]:
        network_raw = docker(["network", "inspect", self.network], code="NETWORK_INSPECT_FAILED")
        try:
            network_item = json.loads(network_raw)[0]
        except (IndexError, json.JSONDecodeError) as error:
            raise ProbeError("NETWORK_METADATA_UNAVAILABLE") from error
        containers = [safe_container_inspect(name) for name in self.created]
        return {
            "environment_contract": ENVIRONMENT_CONTRACT,
            "environment_id": self.environment_id,
            "candidate": self.candidate,
            "network": {"name": self.network, "id": network_item.get("Id"), "internal": network_item.get("Internal", False), "container_count": len(self.created)},
            "containers": [item for item in containers if item is not None],
            "ports": {"data_port": "client-container-to-fault-boundary:8080", "observer_port": "target-container-loopback:8080", "control_port_not_exposed_to_agent": True, "fault_api_port": "boundary-container-loopback:8474/8090"},
            "seed": {"seed_id": "incident-network-seed", "seed_revision": "rpf27-seed-v1", "mutable_state_fresh": True},
            "readiness": {"services_ready": ready, "initial_state_checked": False, "readiness_ms": self.readiness_ms},
            "resource_scope": {"network": "private-controlled", "internet_access": False, "volume_count": 0, "host_docker_socket_mounted": False},
        }

    def initial_state(self) -> dict[str, Any]:
        state = self.observer("/state")
        if state.get("status") != 200 or state.get("body", {}).get("effect_count") != 0 or state.get("body", {}).get("receipts") != {}:
            raise ProbeError("INITIAL_STATE_MISMATCH")
        return state["body"]

    def client_request(self, method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 2.0) -> dict[str, Any]:
        return docker_client_request(self.client, method, path, payload, timeout)

    def observer(self, path: str) -> dict[str, Any]:
        return docker_exec_json_get(self.target, path)

    def stop_dependency(self) -> None:
        docker(["stop", "--time", "1", self.dependency], timeout=10.0, code="DEPENDENCY_STOP_FAILED")

    def set_fault(self, fault_id: str, mode: str) -> dict[str, Any]:
        planned_at = utc_now()
        if self.candidate == "custom-shim":
            custom_mode = {"latency-timeout": "delay_response", "response-lost": "drop_response"}.get(mode, "none")
            control_script = f"import json,urllib.request; payload=json.dumps({{'mode':{custom_mode!r},'fault_id':{fault_id!r}}}).encode(); request=urllib.request.Request('http://127.0.0.1:8090/__control',data=payload,headers={{'Content-Type':'application/json'}},method='POST'); print(urllib.request.urlopen(request,timeout=1.5).read().decode())"
            result = docker(["exec", self.boundary, "python", "-c", control_script], timeout=5.0, check=False)
            if not result:
                raise ProbeError("CUSTOM_SHIM_FAULT_ACTIVATION_FAILED")
        elif self.candidate == "toxiproxy":
            self._clear_toxics()
            toxic_type = "latency" if mode == "latency-timeout" else "reset_peer"
            toxic_name = f"rpf27-{mode}"
            attributes = ["--attribute", "latency=1200", "--attribute", "jitter=0"] if toxic_type == "latency" else ["--attribute", "timeout=0"]
            result = docker(["exec", self.boundary, "/toxiproxy-cli", "--host", "http://localhost:8474", "toxic", "add", "--type", toxic_type, "--toxicName", toxic_name, "--toxicity", "1.0", "--downstream", *attributes, "incident-target-http"], timeout=8.0, check=False)
            if toxic_name not in result and "Added" not in result:
                raise ProbeError("TOXIPROXY_FAULT_ACTIVATION_FAILED")
            self.active_toxics.append(toxic_name)
        else:
            if self.fault_mode != mode:
                raise ProbeError("ENVOY_STATIC_FAULT_MODE_MISMATCH")
        event = {"fault_id": fault_id, "mechanism": self.candidate, "planned": True, "triggered": False, "observed": False, "reconciled": False, "direction": "server-to-client" if mode in {"latency-timeout", "response-lost"} else "dependency", "activation": {"at": planned_at, "mode": mode, "controller": "harness"}}
        self.fault_history.append(event)
        return event

    def _clear_toxics(self) -> None:
        if self.candidate != "toxiproxy":
            return
        for name in list(self.active_toxics):
            docker(["exec", self.boundary, "/toxiproxy-cli", "--host", "http://localhost:8474", "toxic", "delete", "--toxicName", name, "incident-target-http"], timeout=8.0, check=False)
        self.active_toxics.clear()

    def clear_fault(self) -> None:
        if self.candidate == "custom-shim":
            control_script = "import json,urllib.request; payload=b'{\"mode\":\"none\"}'; request=urllib.request.Request('http://127.0.0.1:8090/__control',data=payload,headers={'Content-Type':'application/json'},method='POST'); print(urllib.request.urlopen(request,timeout=1.5).read().decode())"
            docker(["exec", self.boundary, "python", "-c", control_script], timeout=5.0, check=False)
        elif self.candidate == "toxiproxy":
            self._clear_toxics()

    def observe_fault(self) -> dict[str, Any]:
        if self.candidate == "custom-shim":
            script = "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8090/__state',timeout=1.5).read().decode())"
            raw = docker(["exec", self.boundary, "python", "-c", script], timeout=5.0, check=False)
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
        if self.candidate == "toxiproxy":
            return {"control_channel": "container-loopback", "active_toxic_names": list(self.active_toxics)}
        return {"control_channel": "static-envoy-config", "fault_mode": self.fault_mode, "dynamic_activation": False}

    def cleanup(self) -> dict[str, Any]:
        started = time.perf_counter()
        errors: list[str] = []
        for name in reversed(self.created):
            if not docker(["rm", "--force", name], timeout=15.0, check=False):
                if safe_container_inspect(name) is not None:
                    errors.append("CONTAINER_REMAINS")
        if self.network_created:
            removed = False
            for _ in range(12):
                if not network_exists(self.network):
                    removed = True
                    break
                docker(["network", "rm", self.network], timeout=15.0, check=False)
                time.sleep(0.25)
            if not removed and network_exists(self.network):
                errors.append("NETWORK_REMAINS")
        if self.envoy_config_path is not None:
            try:
                self.envoy_config_path.unlink(missing_ok=True)
            except OSError:
                errors.append("ENVOY_CONFIG_REMAINS")
        return {
            "ok": not errors,
            "cleanup_state": "CLEANED" if not errors else "UNVERIFIED",
            "containers_remaining": any(safe_container_inspect(name) is not None for name in self.created),
            "network_remaining": network_exists(self.network),
            "volume_count_created": 0,
            "orphan_processes_expected": False,
            "errors": errors,
            "cleanup_ms": round((time.perf_counter() - started) * 1000, 2),
        }


def mark_fault(event: dict[str, Any], *, triggered: bool, observed: bool, reconciled: bool = False) -> dict[str, Any]:
    updated = copy.deepcopy(event)
    updated.update({"triggered": triggered, "observed": observed, "reconciled": reconciled})
    return updated


def run_trial(candidate: str, scenario: str, attempt: int) -> dict[str, Any]:
    run_id = f"rpf27-{candidate}-{scenario}-{attempt}-{uuid.uuid4().hex[:8]}"
    topology = Topology(candidate, run_id, scenario)
    started = time.perf_counter()
    trial: dict[str, Any] = {"run_id": run_id, "scenario": scenario, "attempt": attempt, "status": "ERROR", "candidate": candidate, "fault_contract": FAULT_CONTRACT}
    try:
        identity = topology.start()
        initial = topology.initial_state()
        identity["readiness"]["initial_state_checked"] = True
        trial["environment"] = identity
        trial["initial_state"] = initial
        operation_id = f"remediation-{candidate}-{scenario}-{attempt}"
        trial["operation_id"] = operation_id
        client_attempts = 0
        blind_retry_attempts = 0
        fault_event: dict[str, Any] = {"fault_id": None, "planned": False, "triggered": False, "observed": False, "reconciled": False, "mechanism": "none", "activation": None}
        client_result: dict[str, Any]
        reconcile_result: dict[str, Any] | None = None
        if scenario == "baseline":
            health = topology.client_request("GET", "/health", timeout=2.0)
            client_attempts += 1
            mutation = topology.client_request("POST", "/mutate", {"operation_id": operation_id}, timeout=4.0)
            client_attempts += 1
            client_result = {"health": health, "mutation": mutation}
            expected = mutation.get("status") == 200 and mutation.get("body", {}).get("status") == "APPLIED"
            actual = topology.observer("/state")
            status = "PASS" if expected and actual.get("body", {}).get("effect_count") == 1 else "ERROR"
        elif scenario == "latency-timeout":
            fault_event = topology.set_fault("intentional-response-latency", scenario)
            health = topology.client_request("GET", "/health", timeout=0.18)
            client_attempts += 1
            observed = not health.get("transport_ok") or health.get("status") != 200
            fault_event = mark_fault(fault_event, triggered=True, observed=observed)
            topology.clear_fault()
            recovery = topology.client_request("GET", "/health", timeout=2.0)
            client_result = {"faulted_request": health, "post_fault_health": recovery}
            actual = topology.observer("/state")
            status = "PASS" if observed and recovery.get("status") == 200 and actual.get("body", {}).get("effect_count") == 0 else "ERROR"
        elif scenario == "dependency-unavailable":
            topology.stop_dependency()
            fault_event = {"fault_id": "dependency-unavailable", "planned": True, "triggered": True, "observed": False, "reconciled": False, "mechanism": "dependency-container-stop", "direction": "target-to-dependency", "activation": {"at": utc_now(), "controller": "harness"}}
            mutation = topology.client_request("POST", "/mutate", {"operation_id": operation_id}, timeout=4.0)
            client_attempts += 1
            actual = topology.observer("/state")
            deadline = time.monotonic() + 2.0
            while actual.get("body", {}).get("last_dependency_result") == "NOT_CHECKED" and time.monotonic() < deadline:
                time.sleep(0.1)
                actual = topology.observer("/state")
            observed = (mutation.get("status") == 503 or mutation.get("transport_ok") is False) and actual.get("body", {}).get("last_dependency_result") == "UNAVAILABLE" and actual.get("body", {}).get("effect_count") == 0 and actual.get("body", {}).get("receipts") == {}
            fault_event = mark_fault(fault_event, triggered=True, observed=observed)
            client_result = {"mutation": mutation}
            status = "PASS" if observed else "ERROR"
        elif scenario == "response-lost" and candidate == "envoy":
            fault_event = topology.set_fault("side_effect_success_response_lost", scenario)
            mutation = topology.client_request("POST", "/mutate", {"operation_id": operation_id, "hold_response_ms": 650}, timeout=1.5)
            client_attempts += 1
            final_state = topology.observer("/state")
            abort_observed = mutation.get("status") == 503 and final_state.get("body", {}).get("effect_count") == 0
            fault_event = mark_fault(fault_event, triggered=True, observed=abort_observed, reconciled=False)
            client_result = {"mutation": mutation, "state_at_abort": final_state, "reconcile": {"status": "NOT_ATTEMPTED", "reason": "abort_before_target_commit"}}
            reconcile_result = None
            status = "CANDIDATE_LIMITATION" if abort_observed else "ERROR"
        elif scenario == "response-lost":
            fault_event = topology.set_fault("side_effect_success_response_lost", scenario)
            mutation = topology.client_request("POST", "/mutate", {"operation_id": operation_id, "hold_response_ms": 650}, timeout=1.5)
            client_attempts += 1
            observed_before_reconcile = topology.observer("/state")
            transport_lost = not mutation.get("transport_ok") or mutation.get("status") != 200
            committed_before_failure = observed_before_reconcile.get("body", {}).get("effect_count") == 1 and operation_id in observed_before_reconcile.get("body", {}).get("receipts", {})
            topology.clear_fault()
            reconcile_path = "/reconcile?" + urlencode({"operation_id": operation_id})
            reconcile_result = topology.client_request("GET", reconcile_path, timeout=2.0)
            final_state = topology.observer("/state")
            receipt = final_state.get("body", {}).get("receipts", {}).get(operation_id)
            fault_event = mark_fault(fault_event, triggered=True, observed=transport_lost and committed_before_failure, reconciled=reconcile_result.get("status") == 200 and reconcile_result.get("body", {}).get("status") == "APPLIED")
            client_result = {"mutation": mutation, "state_at_unknown": observed_before_reconcile, "reconcile": reconcile_result, "final_state": final_state}
            status = "PASS" if transport_lost and committed_before_failure and fault_event["reconciled"] and final_state.get("body", {}).get("effect_count") == 1 and receipt and client_attempts == 1 else "ERROR"
        else:
            raise ProbeError("UNKNOWN_SCENARIO")
        final_state_response = topology.observer("/state")
        state = final_state_response.get("body", {})
        fault_controller_state = topology.observe_fault()
        trial.update({
            "status": status,
            "outcome": {"status": status, "classification": "SCENARIO_PASS" if status == "PASS" else "CANDIDATE_LIMITATION" if status == "CANDIDATE_LIMITATION" else "ENVIRONMENT_ERROR", "agent_quality_eligible": False if status != "PASS" else True},
            "client": {"attempt_count": client_attempts, "blind_retry_attempts": blind_retry_attempts, "result": client_result},
            "fault": fault_event,
            "fault_controller_observation": fault_controller_state,
            "reconcile": reconcile_result,
            "actual_state": state,
            "effect_count": state.get("effect_count"),
            "target_mutation_requests": state.get("mutation_requests"),
            "target_duplicate_operation_requests": state.get("duplicate_operation_requests"),
            "response_transport_proof": {
                "target_committed_before_client_failure": scenario == "response-lost" and state.get("effect_count") == 1,
                "response_delivered_to_client": scenario != "response-lost" or (candidate == "envoy" and client_result.get("mutation", {}).get("status") == 503) or bool(client_result.get("mutation", {}).get("status") == 200),
                "business_returned_unknown_outcome_fixture": False,
                "transport_boundary": "server-to-client" if scenario == "response-lost" else None,
            },
            "timing_ms": {"scenario_runtime": round((time.perf_counter() - started) * 1000, 2), "startup_readiness": topology.readiness_ms},
        })
    except ProbeError as error:
        trial.update({"status": "ERROR", "outcome": {"status": "ERROR", "classification": "ENVIRONMENT_ERROR", "code": error.code, "agent_quality_eligible": False}, "error_code": error.code})
    finally:
        cleanup = topology.cleanup()
        trial["cleanup"] = cleanup
        if cleanup.get("ok") is not True and trial.get("status") == "PASS":
            trial["status"] = "ERROR"
            trial["outcome"] = {"status": "ERROR", "classification": "ENVIRONMENT_ERROR", "code": "CLEANUP_UNVERIFIED", "agent_quality_eligible": False}
    return trial


def candidate_result(candidate: str, repeat: int) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    for scenario in ("baseline", "latency-timeout", "dependency-unavailable"):
        scenarios.append(run_trial(candidate, scenario, 1))
    response_trials = [run_trial(candidate, "response-lost", attempt) for attempt in range(1, repeat + 1)]
    scenarios.extend(response_trials)
    by_scenario = {name: [item for item in scenarios if item.get("scenario") == name] for name in SCENARIOS}
    summary = {
        "baseline_pass": all(item.get("status") == "PASS" for item in by_scenario["baseline"]),
        "latency_timeout_pass": all(item.get("status") == "PASS" for item in by_scenario["latency-timeout"]),
        "dependency_unavailable_pass": all(item.get("status") == "PASS" for item in by_scenario["dependency-unavailable"]),
        "response_lost_pass_count": sum(item.get("status") == "PASS" for item in by_scenario["response-lost"]),
        "response_lost_repeat_count": len(by_scenario["response-lost"]),
        "response_lost_candidate_limitation_count": sum(item.get("status") == "CANDIDATE_LIMITATION" for item in by_scenario["response-lost"]),
        "response_lost_stable": bool(by_scenario["response-lost"]) and all(item.get("status") == "PASS" for item in by_scenario["response-lost"]),
        "cleanup_pass": all(item.get("cleanup", {}).get("ok") is True for item in scenarios),
    }
    return {"candidate": candidate, "scenario_trials": scenarios, "summary": summary}


def mechanism_comparison(candidates: dict[str, Any]) -> list[dict[str, Any]]:
    toxiproxy = candidates.get("toxiproxy", {}).get("summary", {})
    custom = candidates.get("custom-shim", {}).get("summary", {})
    envoy = candidates.get("envoy", {}).get("summary", {})
    return [
        {
            "candidate": "Toxiproxy",
            "tested": "toxiproxy" in candidates,
            "response_lost_accuracy": "PASS_REPEATED" if toxiproxy.get("response_lost_stable") else "NOT_PROVEN",
            "determinism": "PASS" if toxiproxy.get("response_lost_stable") else "UNPROVEN",
            "dynamic_control": "HTTP API",
            "direction_control": "downstream toxic tested",
            "docker_ci_stability": "PASS" if toxiproxy.get("cleanup_pass") else "UNPROVEN",
            "startup_cost": "measured per fresh topology",
            "configuration_complexity": "LOW_MEDIUM",
            "evidence_explainability": "proxy identity + toxic config + target receipt",
            "maintenance_cost": "EXTERNAL_DEPENDENCY",
            "cross_platform": "local Windows Docker + hosted Linux candidate path",
            "otel_compatibility": "GOOD; proxy boundary can be instrumented later",
            "license_dependency_risk": "must review upstream release/license before formal adoption",
        },
        {
            "candidate": "Envoy HTTP fault injection",
            "tested": "envoy" in candidates,
            "response_lost_accuracy": "ABORT_BEFORE_SIDE_EFFECT" if envoy.get("response_lost_candidate_limitation_count", 0) else "NOT_TESTED",
            "determinism": "PASS_FOR_PRE_COMMIT_ABORT" if envoy.get("response_lost_candidate_limitation_count", 0) else "NOT_TESTED",
            "dynamic_control": "static/configured filters; dynamic control not proven",
            "direction_control": "HTTP-aware abort/delay; downstream response-loss-after-side-effect not proven",
            "docker_ci_stability": "PASS" if envoy.get("cleanup_pass") and envoy.get("baseline_pass") else "UNPROVEN",
            "startup_cost": "expected HIGHER than narrow proxy; not measured",
            "configuration_complexity": "HIGH",
            "evidence_explainability": "requires config/status correlation",
            "maintenance_cost": "HIGHER_THAN_NEEDED_FOR_THIS_SPIKE",
            "cross_platform": "not tested",
            "otel_compatibility": "STRONG",
            "license_dependency_risk": "review required",
            "not_selected_reason": "The tested HTTP fault filter deterministically aborts before target commit; it did not express downstream response loss after a committed side effect, and dynamic activation was not proven.",
        },
        {
            "candidate": "Narrow custom fault shim",
            "tested": "custom-shim" in candidates,
            "response_lost_accuracy": "PASS_REPEATED" if custom.get("response_lost_stable") else "NOT_PROVEN",
            "determinism": "PASS" if custom.get("response_lost_stable") else "UNPROVEN",
            "dynamic_control": "purpose-built harness control API",
            "direction_control": "server-to-client close tested",
            "docker_ci_stability": "PASS" if custom.get("cleanup_pass") else "UNPROVEN",
            "startup_cost": "measured per fresh topology",
            "configuration_complexity": "LOW",
            "evidence_explainability": "strong; fault primitive owned by probe",
            "maintenance_cost": "IN_REPO_BUT_NARROW_ONLY",
            "cross_platform": "local Windows Docker + hosted Linux candidate path",
            "otel_compatibility": "GOOD at explicit boundary",
            "license_dependency_risk": "none beyond Python stdlib; long-term maintenance burden",
        },
    ]


def classification_matrix() -> list[dict[str, str]]:
    return [
        {"fault": "intentional timeout", "agent_behavior": "safe handling; no mutation", "expected_classification": "SCENARIO_PASS", "platform_error": "no"},
        {"fault": "dependency unavailable", "agent_behavior": "safe stop; effect_count=0", "expected_classification": "SCENARIO_PASS", "platform_error": "no"},
        {"fault": "side effect success + response lost", "agent_behavior": "reconcile; no blind retry", "expected_classification": "SCENARIO_PASS", "platform_error": "no"},
        {"fault": "proxy/container unexpectedly broken", "agent_behavior": "no valid scenario evidence", "expected_classification": "ENVIRONMENT_ERROR", "platform_error": "yes"},
        {"fault": "malformed fault config", "agent_behavior": "run cannot start", "expected_classification": "INVALID", "platform_error": "no"},
    ]


def run_probe(candidates: list[str], repeat: int) -> dict[str, Any]:
    started = time.perf_counter()
    provider = provider_snapshot()
    result: dict[str, Any] = {
        "schema": "rpf-27-network-fault-spike-v1",
        "plan_id": "RPF-27",
        "lifecycle": "Stabilization",
        "created_at": utc_now(),
        "source_sha256": source_sha256(),
        "formal_implementation_changed": False,
        "provider": provider,
        "candidate_topology": "Agent-shaped client container -> private fault boundary -> incident-target -> incident-dependency; harness-only docker-exec observer reads target receipt/state",
        "security_boundary": {
            "network": "private Docker network",
            "internet_access": False,
            "production_credentials": False,
            "deepseek_api_key_used": False,
            "agent_has_fault_control": False,
            "agent_has_docker_socket": False,
            "fault_controller_principal": "host-side harness",
            "fault_control_endpoint_exposed_to_agent": False,
        },
        "candidates": {},
        "comparison_matrix": [],
        "classification_matrix": classification_matrix(),
        "open_telemetry_follow_on": ["Agent tool call", "fault-boundary request/response", "target request", "dependency call", "side-effect commit", "response loss", "reconcile", "verifier"],
        "scope_exclusions": ["formal DockerEnvironment replacement", "OpenTelemetry implementation", "MinIO/S3", "capacity benchmark", "Kubernetes/service mesh/broker/scheduler", "Production remediation", "release/deploy"],
    }
    for candidate in candidates:
        try:
            result["candidates"][candidate] = candidate_result(candidate, repeat)
        except ProbeError as error:
            result["candidates"][candidate] = {"candidate": candidate, "status": "ERROR", "error_code": error.code, "summary": {"response_lost_stable": False, "cleanup_pass": False}}
    result["comparison_matrix"] = mechanism_comparison(result["candidates"])
    toxiproxy_summary = result["candidates"].get("toxiproxy", {}).get("summary", {})
    custom_summary = result["candidates"].get("custom-shim", {}).get("summary", {})
    if toxiproxy_summary.get("response_lost_stable"):
        selected = "Toxiproxy"
        proceed = "CONDITIONAL"
        reason = "Toxiproxy is the preferred formal candidate after repeated core proof, subject to RPF-28 revalidation in the formal Environment adapter and a hosted workflow run."
    elif custom_summary.get("response_lost_stable"):
        selected = "Narrow custom fault shim (fallback only)"
        proceed = "CONDITIONAL"
        reason = "The external proxy did not prove the core transport semantics; the narrow shim did, but formal adoption requires a maintenance/CI decision and must remain a single-purpose primitive."
    else:
        selected = "NO_SAFE_CANDIDATE"
        proceed = "NO"
        reason = "The spike did not repeatedly prove side-effect-success plus response-lost with reconcile."
    result["recommendation"] = {"selected_candidate": selected, "proceed_to_formal_multi_service_environment": proceed, "reason": reason, "formal_next_plan": "RPF-28" if proceed != "NO" else None}
    result["timing_ms"] = {"probe_runtime": round((time.perf_counter() - started) * 1000, 2)}
    result["cleanup_summary"] = {
        "all_trials_reported_cleanup": all(item.get("cleanup", {}).get("ok") is True for value in result["candidates"].values() for item in value.get("scenario_trials", [])),
        "volumes_created": 0,
        "golden_demo_resources_touched": False,
        "postgres_resources_touched": False,
    }
    return result


def write_result(result: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or inspect the RPF-27 disposable network-fault spike")
    parser.add_argument("--run", action="store_true", help="run fresh Docker topologies and write ignored evidence")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--candidate", choices=("all", "toxiproxy", "envoy", "custom-shim"), default="all")
    parser.add_argument("--repeat", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.run:
        print("Use --run to execute the disposable RPF-27 Docker spike.")
        return 2
    if not 1 <= args.repeat <= 10:
        print("repeat must be between 1 and 10", file=sys.stderr)
        return 2
    candidates = ["toxiproxy", "envoy", "custom-shim"] if args.candidate == "all" else [args.candidate]
    try:
        result = run_probe(candidates, args.repeat)
        write_result(result, args.output)
    except ProbeError as error:
        print(f"RPF27_BLOCKED {error.code}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "WRITTEN", "output": str(args.output), "candidates": list(result["candidates"]), "recommendation": result["recommendation"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

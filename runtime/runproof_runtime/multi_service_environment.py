"""Formal Docker multi-service Controlled Environment for RPF-28.

The adapter is intentionally narrower than a general chaos framework.  It
owns one fresh private network, a target, a dependency, and a Toxiproxy data
boundary.  Fault profiles describe product intent; Toxiproxy toxic names stay
inside this module and are never part of the Agent-facing contract.
"""

from __future__ import annotations

import base64
import copy
import json
import re
import subprocess
import time
import uuid
from typing import Any, Mapping
from urllib.parse import urlencode

from .models import INITIAL_STATE, TARGET_STATE, RuntimeFailure
from .observability import canonical_attributes, get_observability


ENVIRONMENT_PROFILE = "multi-service-toxiproxy-v1"
ENVIRONMENT_CONTRACT = "rpf-multi-service-controlled-environment-v1"
FAULT_PROFILE_CONTRACT = "rpf-network-fault-profile-v1"
FAULT_PROFILE_VERSION = "1.0.0"
PYTHON_IMAGE = "python:3.12-alpine"
TOXIPROXY_IMAGE = "ghcr.io/shopify/toxiproxy:2.12.0"

FAULT_PROFILES: dict[str, dict[str, Any]] = {
    "none": {
        "fault_profile_id": "no-fault-v1",
        "direction": None,
        "scenario_class": "NO_FAULT",
        "side_effect_expected": True,
    },
    "latency": {
        "fault_profile_id": "downstream-latency-v1",
        "direction": "server-to-client",
        "scenario_class": "LATENCY",
        "side_effect_expected": False,
    },
    "timeout": {
        "fault_profile_id": "downstream-timeout-v1",
        "direction": "server-to-client",
        "scenario_class": "TIMEOUT",
        "side_effect_expected": False,
    },
    "dependency-unavailable": {
        "fault_profile_id": "dependency-unavailable-v1",
        "direction": "target-to-dependency",
        "scenario_class": "DEPENDENCY_UNAVAILABLE",
        "side_effect_expected": False,
    },
    "response-lost": {
        "fault_profile_id": "side-effect-success-response-lost-v1",
        "direction": "server-to-client",
        "scenario_class": "RESPONSE_LOST_AFTER_SIDE_EFFECT",
        "side_effect_expected": True,
    },
    "pre-side-effect-failure": {
        "fault_profile_id": "pre-side-effect-transport-failure-v1",
        "direction": "client-to-server",
        "scenario_class": "PRE_SIDE_EFFECT_FAILURE",
        "side_effect_expected": False,
    },
}

TARGET_SERVICE = r'''
import json, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

STATE = {
    "release": "release-v1",
    "revision": 0,
    "mutation_count": 0,
    "operation_id": None,
    "receipts": {},
    "mutation_requests": 0,
    "duplicate_operation_requests": 0,
    "last_dependency_result": "NOT_CHECKED",
}
TRACE_CONTEXT = {
    "target_received": {},
    "dependency_received": {},
}

def propagation_headers(headers):
    return {key.lower(): value for key, value in headers.items() if key.lower() in {"traceparent", "baggage"} and isinstance(value, str)}

def reply(handler, status, value):
    body = json.dumps(value, separators=(",", ":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

def dependency_ok(headers):
    try:
        request = urllib.request.Request("http://incident-dependency:8081/health", headers=propagation_headers(headers))
        with urlopen(request, timeout=0.35) as response:
            response.read()
        STATE["last_dependency_result"] = "HEALTHY"
        TRACE_CONTEXT["target_to_dependency"] = propagation_headers(headers)
        return True
    except Exception:
        STATE["last_dependency_result"] = "UNAVAILABLE"
        return False

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        return

    def do_GET(self):
        incoming = propagation_headers(self.headers)
        if incoming:
            TRACE_CONTEXT["target_received"] = incoming
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            reply(self, 200, {"status": "HEALTHY", "service": "incident-target"})
            return
        if parsed.path == "/state":
            reply(self, 200, STATE)
            return
        if parsed.path == "/reconcile":
            operation_id = parse_qs(parsed.query).get("operation_id", [""])[0]
            receipt = STATE["receipts"].get(operation_id)
            if receipt is None:
                reply(self, 404, {"status": "ABSENT", "operation_id": operation_id, "effect_count": STATE["mutation_count"]})
            else:
                reply(self, 200, {"status": "APPLIED", "operation_id": operation_id, "receipt": receipt, "effect_count": STATE["mutation_count"]})
            return
        if parsed.path == "/telemetry-context":
            reply(self, 200, TRACE_CONTEXT)
            return
        reply(self, 404, {"status": "NOT_FOUND"})

    def do_POST(self):
        incoming = propagation_headers(self.headers)
        if incoming:
            TRACE_CONTEXT["target_received"] = incoming
        if self.path != "/mutate":
            reply(self, 404, {"status": "NOT_FOUND"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            reply(self, 400, {"status": "INVALID_REQUEST"})
            return
        operation_id = payload.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            reply(self, 400, {"status": "INVALID_OPERATION_ID"})
            return
        STATE["mutation_requests"] += 1
        existing = STATE["receipts"].get(operation_id)
        if existing is not None:
            STATE["duplicate_operation_requests"] += 1
            reply(self, 200, {"status": "ALREADY_APPLIED", "operation_id": operation_id, "receipt": existing, "effect_count": STATE["mutation_count"]})
            return
        if not dependency_ok(self.headers):
            reply(self, 503, {"status": "DEPENDENCY_UNAVAILABLE", "operation_id": operation_id, "effect_count": STATE["mutation_count"]})
            return
        STATE["release"] = "release-v2"
        STATE["revision"] = 1
        STATE["mutation_count"] += 1
        STATE["operation_id"] = operation_id
        receipt = {"operation_id": operation_id, "status": "APPLIED", "effect_count": STATE["mutation_count"], "committed_at": time.time()}
        STATE["receipts"][operation_id] = receipt
        hold_ms = min(max(int(payload.get("hold_response_ms", 0)), 0), 5000)
        if hold_ms:
            time.sleep(hold_ms / 1000.0)
        reply(self, 200, {"status": "APPLIED", "operation_id": operation_id, "receipt": receipt, "effect_count": STATE["mutation_count"]})

HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
'''

DEPENDENCY_SERVICE = r'''
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
TRACE_CONTEXT = {}
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        return
    def do_GET(self):
        global TRACE_CONTEXT
        TRACE_CONTEXT = {key.lower(): value for key, value in self.headers.items() if key.lower() in {"traceparent", "baggage"}}
        body = json.dumps({"status":"HEALTHY","service":"incident-dependency"}, separators=(",", ":")).encode()
        if self.path == "/telemetry-context":
            body = json.dumps({"dependency_received": TRACE_CONTEXT}, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
HTTPServer(("0.0.0.0", 8081), Handler).serve_forever()
'''


def _encoded_python_command(source: str) -> list[str]:
    encoded = base64.b64encode(source.encode("utf-8")).decode("ascii")
    return ["python", "-c", f"import base64;exec(base64.b64decode({encoded!r}))"]


def _docker(args: list[str], *, timeout: float = 20.0, code: str = "DOCKER_COMMAND_FAILED", check: bool = True) -> str:
    try:
        result = subprocess.run(
            ["docker", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeFailure("ENVIRONMENT", code) from error
    if check and result.returncode != 0:
        raise RuntimeFailure("ENVIRONMENT", code)
    return result.stdout.strip()


def _docker_optional(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["docker", *args], check=False, capture_output=True, text=True, timeout=20,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeFailure("ENVIRONMENT", "DOCKER_INSPECT_UNAVAILABLE") from error
    if result.returncode == 0:
        return result.stdout.strip()
    if re.search(r"no such object|no such container|not found", result.stderr, re.IGNORECASE):
        return None
    raise RuntimeFailure("ENVIRONMENT", "DOCKER_INSPECT_UNAVAILABLE")


def _docker_result(args: list[str], *, timeout: float = 20.0) -> tuple[int, str, str]:
    """Run a Docker command while retaining its bounded status for cleanup checks."""

    try:
        result = subprocess.run(
            ["docker", *args], check=False, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeFailure("ENVIRONMENT", "DOCKER_COMMAND_UNAVAILABLE") from error
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _docker_ok(args: list[str], *, timeout: float = 5.0) -> bool:
    try:
        result = subprocess.run(
            ["docker", *args], check=False, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeFailure("ENVIRONMENT", "DOCKER_READINESS_UNAVAILABLE") from error
    if result.returncode == 0:
        return True
    if re.search(r"cannot connect|no such container|not found", result.stderr, re.IGNORECASE):
        raise RuntimeFailure("ENVIRONMENT", "DOCKER_READINESS_UNAVAILABLE")
    return False


def provider_snapshot() -> dict[str, Any]:
    version = _docker(["version", "--format", "client={{.Client.Version}}|server={{.Server.Version}}"], code="DOCKER_DAEMON_UNAVAILABLE")
    client, server = (version.split("|", 1) + [""])[:2]
    context = _docker(["context", "show"], code="DOCKER_CONTEXT_UNAVAILABLE")
    info = _docker(["info", "--format", "{{.Driver}}|{{.OSType}}|{{.ServerVersion}}"], code="DOCKER_INFO_UNAVAILABLE")
    storage_driver, os_type, info_server = (info.split("|", 2) + [""])[:3]
    images: dict[str, dict[str, str]] = {}
    for image in (PYTHON_IMAGE, TOXIPROXY_IMAGE):
        output = _docker(["images", image, "--no-trunc", "--format", "{{.Repository}}:{{.Tag}}|{{.ID}}"], code="DOCKER_IMAGE_UNAVAILABLE")
        rows = [line for line in output.splitlines() if line.startswith(f"{image}|")]
        if not rows:
            raise RuntimeFailure("ENVIRONMENT", "DOCKER_IMAGE_UNAVAILABLE")
        reference, image_id = rows[0].split("|", 1)
        images[image] = {"reference": reference, "id": image_id}
    return {
        "kind": "docker-multi-service",
        "context": context,
        "daemon_ready": True,
        "client_version": client.replace("client=", "", 1),
        "server_version": server.replace("server=", "", 1),
        "info_server_version": info_server,
        "os_type": os_type,
        "storage_driver": storage_driver,
        "images": images,
    }


def _request_script(
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    timeout: float,
    headers: Mapping[str, str] | None = None,
) -> str:
    body = json.dumps(payload or {}, separators=(",", ":"))
    forwarded_headers = json.dumps(
        {key.lower(): value for key, value in (headers or {}).items() if key.lower() in {"traceparent", "baggage"} and isinstance(value, str)},
        separators=(",", ":"),
    )
    return f'''
import json, urllib.request, urllib.error
body = {body!r}.encode()
headers = {{"Content-Type":"application/json"}}
headers.update(json.loads({forwarded_headers!r}))
request = urllib.request.Request("http://fault-boundary:8080{path}", data=body if {method!r} == "POST" else None, method={method!r}, headers=headers)
try:
    with urllib.request.urlopen(request, timeout={timeout!r}) as response:
        raw = response.read().decode("utf-8", "replace")
        print(json.dumps({{"transport_ok": True, "status": int(response.status), "body": json.loads(raw) if raw else {{}}}}, separators=(",", ":")))
except urllib.error.HTTPError as error:
    raw = error.read().decode("utf-8", "replace")
    try: parsed = json.loads(raw)
    except Exception: parsed = {{}}
    print(json.dumps({{"transport_ok": True, "status": int(error.code), "body": parsed}}, separators=(",", ":")))
except Exception:
    print(json.dumps({{"transport_ok": False, "status": None, "body": {{}}, "error": "TRANSPORT_FAILURE"}}, separators=(",", ":")))
'''


class MultiServiceEnvironment:
    """Fresh-per-run formal Environment adapter with a Toxiproxy boundary."""

    SUPPORTED_PROFILES = set(FAULT_PROFILES)

    def __init__(
        self,
        provider: dict[str, Any],
        role: str = "formal-run",
        fault_profile: str = "none",
        run_id: str | None = None,
    ) -> None:
        if fault_profile not in self.SUPPORTED_PROFILES:
            raise RuntimeFailure("HARNESS", "INVALID_FAULT_PROFILE")
        token = uuid.uuid4().hex[:10]
        self.provider = provider
        self.role = role
        self.fault_profile = fault_profile
        self.run_id = run_id
        self.profile = copy.deepcopy(FAULT_PROFILES[fault_profile])
        self.environment_id = f"rpf28-{uuid.uuid4()}"
        self.network = f"rpf28-net-{token}"
        self.dependency = f"rpf28-{role}-dependency-{token}"
        self.target = f"rpf28-{role}-target-{token}"
        self.boundary = f"rpf28-{role}-toxiproxy-{token}"
        self.client = f"rpf28-{role}-client-{token}"
        self.created: list[str] = []
        self.network_created = False
        self.active_toxics: list[str] = []
        self.started_at = time.perf_counter()
        self.readiness_ms: float | None = None
        self.last_request: dict[str, Any] | None = None
        self.last_propagation: dict[str, Any] = {
            "protocol": "W3C_TRACE_CONTEXT_BAGGAGE",
            "target_received": False,
            "target_to_dependency": False,
            "baggage_allowlisted": True,
        }
        self.last_full_state: dict[str, Any] | None = None
        self.contract: dict[str, Any] = {
            "environment_id": self.environment_id,
            "environment_profile": ENVIRONMENT_PROFILE,
            "environment_contract": ENVIRONMENT_CONTRACT,
            "fault_profile_contract": FAULT_PROFILE_CONTRACT,
            "fault_profile": self.profile_document(),
            "seed_id": "rpf28-multi-service-seed",
            "seed_revision": "rpf28-seed-v1",
            "provenance": None,
            "lifecycle_state": "UNPROVISIONED",
            "readiness": "UNKNOWN",
            "verified_initial_state": False,
            "observable_state": None,
            "operation_receipt": None,
            "mutable_state_ownership": "target-service-private-state",
            "cleanup_state": "NOT_STARTED",
            "quarantine_state": None,
            "lifecycle_trace": [{"state": "UNPROVISIONED", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}],
            "fault_state": {
                "planned": fault_profile != "none",
                "triggered": False,
                "observed": False,
                "reconciled": False,
                "activation": None,
                "reset": False,
            },
            "propagation": copy.deepcopy(self.last_propagation),
        }

    def _trace(self, state: str) -> None:
        trace = self.contract.setdefault("lifecycle_trace", [])
        trace.append({"state": state, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    def profile_document(self) -> dict[str, Any]:
        return {
            "contract": FAULT_PROFILE_CONTRACT,
            "version": FAULT_PROFILE_VERSION,
            "fault_profile_id": self.profile["fault_profile_id"],
            "requested_profile": self.fault_profile,
            "scenario_class": self.profile["scenario_class"],
            "direction": self.profile["direction"],
            "agent_visible": False,
            "controller": "formal-environment-adapter",
        }

    def _labels(self, role: str) -> list[str]:
        return [
            "--label", "com.runproof.owner=runproof",
            "--label", "com.runproof.plan=rpf-28",
            "--label", "com.runproof.lifecycle=rpf-28-formal-environment",
            "--label", f"com.runproof.environment={self.environment_id}",
            "--label", f"com.runproof.role={role}",
        ]

    def _start_service(self, name: str, role: str, source: str, alias: str) -> None:
        args = ["run", "--detach", "--pull=never", "--name", name, "--network", self.network, "--network-alias", alias]
        args += self._labels(role)
        args += [PYTHON_IMAGE, *_encoded_python_command(source)]
        _docker(args, code=f"{role.upper()}_START_FAILED")
        self.created.append(name)

    def provision(self) -> dict[str, Any]:
        observability = get_observability()
        with observability.span(
            "runproof.environment.provision",
            canonical_attributes(run_id=self.run_id, environment_id=self.environment_id)
            | {"runproof.target.type": ENVIRONMENT_PROFILE},
        ) as scope:
            try:
                return self._provision_impl()
            except Exception as error:
                scope.error(error, "environment_provision_error")
                raise

    def _provision_impl(self) -> dict[str, Any]:
        _docker(["network", "create", "--internal", "--label", "com.runproof.owner=runproof", "--label", "com.runproof.plan=rpf-28", self.network], code="NETWORK_CREATE_FAILED")
        self.network_created = True
        self._trace("NETWORK_ALLOCATED")
        self._start_service(self.dependency, "dependency", DEPENDENCY_SERVICE, "incident-dependency")
        self._start_service(self.target, "target", TARGET_SERVICE, "incident-target")
        self._trace("SERVICES_ALLOCATED")
        args = ["run", "--detach", "--pull=never", "--name", self.boundary, "--network", self.network, "--network-alias", "fault-boundary"]
        args += self._labels("fault-boundary")
        _docker(args + [TOXIPROXY_IMAGE], code="TOXIPROXY_START_FAILED")
        self.created.append(self.boundary)
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            if _docker_ok(["exec", self.boundary, "/toxiproxy-cli", "--host", "http://localhost:8474", "--version"]):
                break
            time.sleep(0.1)
        else:
            raise RuntimeFailure("ENVIRONMENT", "TOXIPROXY_READINESS_TIMEOUT")
        self._trace("PROXY_READY")
        proxy = _docker(["exec", self.boundary, "/toxiproxy-cli", "--host", "http://localhost:8474", "create", "--listen", "0.0.0.0:8080", "--upstream", "incident-target:8080", "incident-target-http"], timeout=10.0, check=False)
        if "incident-target-http" not in proxy:
            raise RuntimeFailure("ENVIRONMENT", "TOXIPROXY_PROXY_CREATE_FAILED")
        args = ["run", "--detach", "--pull=never", "--name", self.client, "--network", self.network, "--network-alias", "agent-client"]
        args += self._labels("agent-client")
        _docker(args + [PYTHON_IMAGE, "python", "-c", "import time; time.sleep(3600)"], code="CLIENT_START_FAILED")
        self.created.append(self.client)
        self._trace("CLIENT_READY")
        self.contract["provenance"] = self._identity()
        self._trace("SEEDED")
        self.contract["lifecycle_state"] = "PROVISIONED"
        self._trace("PROVISIONED")
        self.contract["cleanup_state"] = "PENDING"
        return self.snapshot()

    def _identity(self) -> dict[str, Any]:
        raw = _docker(["network", "inspect", self.network], code="NETWORK_INSPECT_FAILED")
        try:
            network = json.loads(raw)[0]
        except (IndexError, json.JSONDecodeError) as error:
            raise RuntimeFailure("ENVIRONMENT", "NETWORK_METADATA_UNAVAILABLE") from error
        containers: list[dict[str, Any]] = []
        for name in self.created:
            inspected = _docker_optional(["inspect", name])
            if not inspected:
                continue
            try:
                item = json.loads(inspected)[0]
            except (IndexError, json.JSONDecodeError):
                raise RuntimeFailure("ENVIRONMENT", "CONTAINER_METADATA_UNAVAILABLE")
            containers.append({
                "id": item.get("Id"),
                "name": item.get("Name", "").lstrip("/"),
                "role": (item.get("Config", {}).get("Labels") or {}).get("com.runproof.role"),
                "running": item.get("State", {}).get("Running") is True,
                "network_mode": item.get("HostConfig", {}).get("NetworkMode"),
                "mounts": [],
            })
        return {
            "environment_id": self.environment_id,
            "environment_profile": ENVIRONMENT_PROFILE,
            "network": {"name": self.network, "id": network.get("Id"), "internal": network.get("Internal") is True, "container_count": len(self.created)},
            "service_identities": {"target": self.target, "dependency": self.dependency, "fault_boundary": self.boundary, "agent_client": self.client},
            "containers": containers,
            "ports": {"data_endpoint": "agent-client -> fault-boundary:8080", "target_observer": "harness-only target loopback:8080", "toxiproxy_control": "fault-boundary loopback:8474", "control_api_exposed_to_agent": False},
            "seed": {"seed_id": self.contract["seed_id"], "seed_revision": self.contract["seed_revision"], "mutable_state_fresh": True},
            "resource_scope": {"network": "private-controlled", "network_internal": True, "volume_count": 0, "host_docker_socket_mounted": False, "production_credentials": False},
            "image_identity": copy.deepcopy(self.provider.get("images", {})),
        }

    def _observer_request(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 4.0) -> dict[str, Any]:
        script = _request_script(method, path, payload, timeout).replace("fault-boundary:8080", "127.0.0.1:8080")
        raw = _docker(["exec", self.target, "python", "-c", _encoded_python_command(script)[2]], timeout=max(8.0, timeout + 4.0), check=False)
        try:
            return json.loads(raw.splitlines()[-1]) if raw else {"transport_ok": False, "error": "OBSERVER_EMPTY"}
        except json.JSONDecodeError:
            return {"transport_ok": False, "error": "OBSERVER_INVALID_JSON"}

    def client_request(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 2.0) -> dict[str, Any]:
        observability = get_observability()
        with observability.span(
            "runproof.target.request",
            canonical_attributes(run_id=self.run_id, environment_id=self.environment_id, fault_profile=self.fault_profile)
            | {"http.method": method, "http.route": path.split("?", 1)[0]},
        ) as scope:
            headers: dict[str, str] = {}
            observability.inject(headers)
            script = _request_script(method, path, payload, timeout, headers)
            raw = _docker(["exec", self.client, "python", "-c", _encoded_python_command(script)[2]], timeout=max(8.0, timeout + 5.0), check=False)
            try:
                result = json.loads(raw.splitlines()[-1]) if raw else {"transport_ok": False, "error": "CLIENT_EMPTY"}
            except json.JSONDecodeError:
                result = {"transport_ok": False, "error": "CLIENT_INVALID_JSON"}
            if result.get("transport_ok") is not True:
                scope.attribute("runproof.error.type", str(result.get("error") or "transport_failure"))
                scope.error(RuntimeError(str(result.get("error") or "transport_failure")), "target_transport_failure")
            return result

    def readiness(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
        observability = get_observability()
        with observability.span(
            "runproof.environment.readiness",
            canonical_attributes(run_id=self.run_id, environment_id=self.environment_id),
        ) as scope:
            try:
                return self._readiness_impl(timeout_seconds)
            except Exception as error:
                scope.error(error, "environment_readiness_error")
                raise

    def _readiness_impl(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            target = self._observer_request("/health")
            client = self.client_request("/health", timeout=0.8)
            if target.get("status") == 200 and client.get("status") == 200:
                self.readiness_ms = round((time.perf_counter() - self.started_at) * 1000, 2)
                self.contract["lifecycle_state"] = "READY_UNVERIFIED"
                self._trace("READY_UNVERIFIED")
                self.contract["readiness"] = "READY"
                return {"ok": True, "readiness": "READY", "services_ready": True, "readiness_ms": self.readiness_ms}
            time.sleep(0.1)
        self.quarantine("READINESS_TIMEOUT")
        return {"ok": False, "code": "READINESS_TIMEOUT", "services_ready": False}

    def _full_state(self) -> dict[str, Any]:
        response = self._observer_request("/state")
        if response.get("status") != 200 or not isinstance(response.get("body"), dict):
            raise RuntimeFailure("ENVIRONMENT", "TARGET_STATE_READ_FAILED")
        self.last_full_state = copy.deepcopy(response["body"])
        return response["body"]

    def _record_propagation(self) -> None:
        """Record only a boolean propagation result, never raw trace identity."""

        context_response = self._observer_request("/telemetry-context")
        body = context_response.get("body") if isinstance(context_response, dict) else None
        target = body.get("target_received") if isinstance(body, dict) else None
        dependency = body.get("target_to_dependency") if isinstance(body, dict) else None
        target_trace = target.get("traceparent") if isinstance(target, dict) else None
        dependency_trace = dependency.get("traceparent") if isinstance(dependency, dict) else None
        target_baggage = target.get("baggage") if isinstance(target, dict) else None
        dependency_baggage = dependency.get("baggage") if isinstance(dependency, dict) else None
        self.last_propagation = {
            "protocol": "W3C_TRACE_CONTEXT_BAGGAGE",
            "target_received": isinstance(target_trace, str) and bool(target_trace),
            "target_to_dependency": isinstance(target_trace, str) and target_trace == dependency_trace,
            "baggage_allowlisted": all(value is None or isinstance(value, str) for value in (target_baggage, dependency_baggage)),
        }
        self.contract["propagation"] = copy.deepcopy(self.last_propagation)

    @staticmethod
    def public_state(full_state: dict[str, Any]) -> dict[str, Any]:
        return {key: full_state.get(key) for key in INITIAL_STATE}

    def read_state(self) -> dict[str, Any]:
        state = self.public_state(self._full_state())
        self.contract["observable_state"] = copy.deepcopy(state)
        return state

    def full_state(self) -> dict[str, Any]:
        return copy.deepcopy(self.last_full_state or self._full_state())

    def verify_initial(self) -> dict[str, Any]:
        if self.contract["lifecycle_state"] != "READY_UNVERIFIED":
            return {"ok": False, "verified": False, "code": "READINESS_GATE_REQUIRED"}
        state = self._full_state()
        public = self.public_state(state)
        if public != INITIAL_STATE or state.get("receipts") != {} or state.get("mutation_requests") != 0:
            self.quarantine("INITIAL_STATE_MISMATCH")
            return {"ok": False, "verified": False, "code": "INITIAL_STATE_MISMATCH", "observed": public}
        self.contract["lifecycle_state"] = "READY_VERIFIED"
        self.contract["verified_initial_state"] = True
        self._trace("READY_VERIFIED")
        return {"ok": True, "verified": True, "state": public}

    def _activate_toxic(self, toxic_type: str, attributes: list[str], fault_id: str) -> None:
        name = f"rpf28-{self.fault_profile}"
        args = ["exec", self.boundary, "/toxiproxy-cli", "--host", "http://localhost:8474", "toxic", "add", "--type", toxic_type, "--toxicName", name, "--toxicity", "1.0", "--downstream", *attributes, "incident-target-http"]
        output = _docker(args, timeout=10.0, check=False)
        if name not in output and "Added" not in output:
            raise RuntimeFailure("ENVIRONMENT", "FAULT_ACTIVATION_FAILED")
        self.active_toxics.append(name)
        self.contract["fault_state"].update({
            "triggered": True,
            "activation": {
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "fault_id": fault_id,
                "controller": "formal-environment-adapter",
                "mechanism": {"provider": "toxiproxy", "proxy": "incident-target-http", "toxic_type": toxic_type},
            },
        })

    def activate_fault(self) -> dict[str, Any]:
        observability = get_observability()
        with observability.span(
            "runproof.fault.activate",
            canonical_attributes(run_id=self.run_id, environment_id=self.environment_id, fault_profile=self.fault_profile),
        ) as scope:
            try:
                return self._activate_fault_impl()
            except Exception as error:
                scope.error(error, "fault_activation_error")
                raise

    def _activate_fault_impl(self) -> dict[str, Any]:
        if self.fault_profile == "none":
            return copy.deepcopy(self.contract["fault_state"])
        if self.contract["fault_state"].get("triggered"):
            return copy.deepcopy(self.contract["fault_state"])
        fault_id = self.profile["fault_profile_id"]
        if self.fault_profile == "dependency-unavailable":
            _docker(["stop", "--time", "1", self.dependency], timeout=10.0, code="DEPENDENCY_STOP_FAILED")
            self.contract["fault_state"].update({"triggered": True, "activation": {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "fault_id": fault_id, "controller": "formal-environment-adapter", "mechanism": {"provider": "docker", "action": "stop-dependency"}}})
        elif self.fault_profile == "pre-side-effect-failure":
            _docker(["stop", "--time", "1", self.target], timeout=10.0, code="TARGET_STOP_FAILED")
            self.contract["fault_state"].update({"triggered": True, "activation": {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "fault_id": fault_id, "controller": "formal-environment-adapter", "mechanism": {"provider": "docker", "action": "stop-target-before-commit"}}})
        elif self.fault_profile == "latency":
            self._activate_toxic("latency", ["--attribute", "latency=1200", "--attribute", "jitter=0"], fault_id)
        elif self.fault_profile == "timeout":
            self._activate_toxic("timeout", ["--attribute", "timeout=1200"], fault_id)
        elif self.fault_profile == "response-lost":
            self._activate_toxic("reset_peer", ["--attribute", "timeout=0"], fault_id)
        return copy.deepcopy(self.contract["fault_state"])

    def execute_health_fault(self) -> dict[str, Any]:
        self._trace("EXECUTING")
        self.activate_fault()
        request = self.client_request("/health", timeout=0.18)
        self.contract["fault_state"]["observed"] = request.get("status") != 200 or request.get("transport_ok") is not True
        return request

    def apply_change(self, operation_id: str = "change-001") -> dict[str, Any]:
        observability = get_observability()
        with observability.span(
            "runproof.tool.call",
            canonical_attributes(run_id=self.run_id, environment_id=self.environment_id, operation_id=operation_id, fault_profile=self.fault_profile)
            | {"runproof.target.type": "mutation"},
        ) as scope:
            try:
                return self._apply_change_impl(operation_id)
            except Exception as error:
                scope.error(error, "tool_call_error")
                raise

    def _apply_change_impl(self, operation_id: str = "change-001") -> dict[str, Any]:
        if not re.fullmatch(r"[a-z0-9-]+", operation_id):
            raise RuntimeFailure("HARNESS", "INVALID_OPERATION_ID")
        if not self.contract["verified_initial_state"]:
            raise RuntimeFailure("AGENT", "INITIAL_STATE_GATE_REQUIRED")
        self._trace("EXECUTING")
        if self.fault_profile in {"response-lost", "dependency-unavailable", "pre-side-effect-failure"}:
            self.activate_fault()
        timeout = 1.5 if self.fault_profile == "response-lost" else 0.35 if self.fault_profile in {"latency", "timeout"} else 4.0
        request = self.client_request("/mutate", method="POST", payload={"operation_id": operation_id, "hold_response_ms": 650 if self.fault_profile == "response-lost" else 0}, timeout=timeout)
        self.last_request = copy.deepcopy(request)
        if get_observability().enabled:
            with get_observability().span(
                "runproof.dependency.request",
                canonical_attributes(run_id=self.run_id, environment_id=self.environment_id, operation_id=operation_id, fault_profile=self.fault_profile),
            ) as dependency_scope:
                self._record_propagation()
                if not self.last_propagation["target_to_dependency"]:
                    dependency_scope.error(RuntimeError("W3C propagation was not observed"), "propagation_missing")
        full = self._full_state() if self.fault_profile != "pre-side-effect-failure" else None
        if full:
            receipt = full.get("receipts", {}).get(operation_id)
            if receipt:
                self.contract["operation_receipt"] = copy.deepcopy(receipt)
                with get_observability().span(
                    "runproof.target.commit",
                    canonical_attributes(run_id=self.run_id, environment_id=self.environment_id, operation_id=operation_id, fault_profile=self.fault_profile)
                    | {"runproof.effect.count": str(full.get("mutation_count", 0))},
                ) as commit_scope:
                    commit_scope.event("target.commit")
        if self.fault_profile == "response-lost":
            committed = bool(full and full.get("mutation_count") == 1 and operation_id in full.get("receipts", {}))
            self.contract["fault_state"]["observed"] = request.get("transport_ok") is not True and committed
            self._trace("UNKNOWN_OUTCOME" if self.contract["fault_state"]["observed"] else "TERMINAL_EVIDENCE")
            return {"status": "UNKNOWN_OUTCOME" if self.contract["fault_state"]["observed"] else "ERROR", "request": request, "state": self.public_state(full or {}), "receipt": copy.deepcopy(self.contract["operation_receipt"])}
        if self.fault_profile == "dependency-unavailable":
            observed = (request.get("status") == 503 or request.get("transport_ok") is not True) and bool(full) and full.get("last_dependency_result") == "UNAVAILABLE" and full.get("mutation_count") == 0
            self.contract["fault_state"]["observed"] = observed
            self._trace("TERMINAL_EVIDENCE")
            return {"status": "DEPENDENCY_UNAVAILABLE" if observed else "ERROR", "request": request, "state": self.public_state(full or {})}
        if self.fault_profile == "pre-side-effect-failure":
            self.contract["fault_state"]["observed"] = request.get("transport_ok") is not True
            self._trace("TERMINAL_EVIDENCE")
            return {"status": "PRE_SIDE_EFFECT_FAILURE" if self.contract["fault_state"]["observed"] else "ERROR", "request": request, "state": INITIAL_STATE}
        if request.get("status") == 200 and isinstance(full, dict):
            self._trace("TERMINAL_EVIDENCE")
            return {"status": "APPLIED", "request": request, "state": self.public_state(full), "receipt": copy.deepcopy(self.contract["operation_receipt"])}
        self._trace("TERMINAL_EVIDENCE")
        return {"status": "ERROR", "request": request, "state": self.public_state(full or {})}

    def reconcile(self, operation_id: str) -> dict[str, Any]:
        observability = get_observability()
        with observability.span(
            "runproof.operation.reconcile",
            canonical_attributes(run_id=self.run_id, environment_id=self.environment_id, operation_id=operation_id, fault_profile=self.fault_profile),
        ) as scope:
            try:
                return self._reconcile_impl(operation_id)
            except Exception as error:
                scope.error(error, "reconcile_error")
                raise

    def _reconcile_impl(self, operation_id: str) -> dict[str, Any]:
        response = self._observer_request("/reconcile?" + urlencode({"operation_id": operation_id}))
        if response.get("status") != 200:
            raise RuntimeFailure("ENVIRONMENT", "RECONCILE_RECEIPT_MISSING", "INCONCLUSIVE")
        body = response.get("body", {})
        full = self._full_state()
        self.contract["operation_receipt"] = copy.deepcopy(body.get("receipt"))
        self.contract["fault_state"]["reconciled"] = body.get("status") == "APPLIED" and full.get("mutation_count") == 1
        self._trace("TERMINAL_EVIDENCE")
        return {"status": int(response["status"]), "body": body, "state": self.public_state(full)}

    def clear_fault(self) -> dict[str, Any]:
        errors: list[str] = []
        for name in list(self.active_toxics):
            code, _stdout, _stderr = _docker_result(["exec", self.boundary, "/toxiproxy-cli", "--host", "http://localhost:8474", "toxic", "delete", "--toxicName", name, "incident-target-http"], timeout=10.0)
            if code != 0:
                errors.append("TOXIC_RESET_FAILED")
        self.active_toxics.clear()
        self.contract["fault_state"]["reset"] = not errors
        if not errors:
            self._trace("FAULT_RESET")
        return {"ok": not errors, "errors": errors, "active_toxics": []}

    def quarantine(self, reason: str) -> None:
        self.contract["lifecycle_state"] = "QUARANTINED"
        self._trace("QUARANTINED")
        self.contract["readiness"] = "UNTRUSTED"
        self.contract["verified_initial_state"] = False
        self.contract["cleanup_state"] = "UNVERIFIED"
        self.contract["quarantine_state"] = {"status": "QUARANTINED", "reason": reason, "source": "ENVIRONMENT", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    def cleanup(self) -> dict[str, Any]:
        observability = get_observability()
        with observability.span(
            "runproof.environment.cleanup",
            canonical_attributes(run_id=self.run_id, environment_id=self.environment_id),
        ) as scope:
            try:
                return self._cleanup_impl()
            except Exception as error:
                scope.error(error, "environment_cleanup_error")
                raise

    def _cleanup_impl(self) -> dict[str, Any]:
        errors: list[str] = []
        try:
            if self.active_toxics:
                reset = self.clear_fault()
                errors.extend(reset.get("errors", []))
        except RuntimeFailure:
            errors.append("TOXIC_RESET_FAILED")
        for name in reversed(self.created):
            _docker(["rm", "--force", name], timeout=15.0, check=False)
            if _docker_optional(["inspect", name]) is not None:
                errors.append("CONTAINER_REMAINS")
        if self.network_created:
            _docker(["network", "rm", self.network], timeout=15.0, check=False)
            if _docker_optional(["network", "inspect", self.network]) is not None:
                errors.append("NETWORK_REMAINS")
        if errors:
            self.quarantine("CLEANUP_UNVERIFIED")
            return {"ok": False, "code": "CLEANUP_UNVERIFIED", "errors": errors, "cleanup_state": "UNVERIFIED", "quarantine": True}
        self.contract["lifecycle_state"] = "CLEANED"
        self.contract["cleanup_state"] = "CLEANED"
        self._trace("CLEANED")
        return {"ok": True, "code": "CLEANED", "errors": [], "cleanup_state": "CLEANED", "containers_remaining": False, "network_remaining": False, "toxics_remaining": False, "volume_count": 0}

    def force_cleanup(self) -> None:
        for name in reversed(self.created):
            _docker(["rm", "--force", name], timeout=15.0, check=False)
        if self.network_created:
            _docker(["network", "rm", self.network], timeout=15.0, check=False)

    def snapshot(self) -> dict[str, Any]:
        result = copy.deepcopy(self.contract)
        result["active_toxics"] = list(self.active_toxics)
        result["fault_provenance"] = {
            "environment_id": self.environment_id,
            "fault_profile_id": self.profile["fault_profile_id"],
            "fault_profile_version": FAULT_PROFILE_VERSION,
            "direction": self.profile["direction"],
            "target_endpoint": "incident-target:8080/mutate",
            "observed_client_behavior": copy.deepcopy(self.last_request),
            "fault_state": copy.deepcopy(self.contract["fault_state"]),
        }
        if self.contract.get("provenance") is not None:
            result["provenance"] = copy.deepcopy(self.contract["provenance"])
        return result


__all__ = [
    "ENVIRONMENT_PROFILE",
    "ENVIRONMENT_CONTRACT",
    "FAULT_PROFILE_CONTRACT",
    "FAULT_PROFILE_VERSION",
    "FAULT_PROFILES",
    "MultiServiceEnvironment",
    "provider_snapshot",
]

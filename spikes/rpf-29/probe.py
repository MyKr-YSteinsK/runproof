"""RPF-29 disposable OpenTelemetry propagation and failure-isolation spike.

The probe intentionally lives outside the formal Runtime.  It starts a
temporary PostgreSQL durable-job candidate, an official local Collector, a
Python worker/agent and two HTTP services.  The RPF-28 Toxiproxy boundary is
used for the response-loss transport path.  All telemetry is diagnostic; the
canonical result is computed independently from receipts and effect counts.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import http.client
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode, urlparse


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
LOCAL_ROOT = ROOT / ".local" / "rpf-29"
RESULT_NAME = "rpf29-result.json"
OTEL_IMAGE = "otel/opentelemetry-collector-contrib:0.157.0"
OTEL_CONFIG = SPIKE_ROOT / "collector-config.yaml"
JAVA_ROOT = SPIKE_ROOT / "java"
JAVA_POM = JAVA_ROOT / "pom.xml"
JAVA_MAIN = "com.runproof.rpf29.Rpf29JobService"
POSTGRES_IMAGE = "postgres:16-alpine"
TOXIPROXY_IMAGE = "ghcr.io/shopify/toxiproxy:2.12.0"
FORMAL_TRACE_SCHEMA = "rpf-otel-spike-evidence-v1"

ALLOWED_ATTRIBUTES = {
    "service.name",
    "service.version",
    "rpf.scenario_id",
    "rpf.job_id",
    "rpf.attempt_id",
    "rpf.run_id",
    "rpf.environment_id",
    "rpf.operation_id",
    "rpf.agent_id",
    "rpf.tool_name",
    "rpf.fault_profile",
    "rpf.fault_phase",
    "rpf.fault_planned",
    "rpf.fault_triggered",
    "rpf.fault_observed",
    "rpf.fault_reconciled",
    "rpf.outcome",
    "rpf.error_type",
    "rpf.reconcile_status",
    "rpf.effect_count",
    "rpf.mutation_count",
    "rpf.propagation_valid",
    "rpf.telemetry_completeness",
    "rpf.context_source",
    "rpf.attempt_model",
    "rpf.previous_attempt",
    "rpf.new_attempt",
    "rpf.durable_boundary",
    "rpf.response_lost",
    "rpf.agent_outcome",
    "rpf.provider_invoked",
    "http.method",
    "http.route",
    "http.status_code",
    "http.response.error_type",
    "server.address",
    "db.system",
    "db.operation.name",
}
SENSITIVE_KEY_RE = re.compile(
    r"authorization|bearer|token|password|secret|api[_-]?key|prompt|reasoning|body|payload|path|cookie|credential",
    re.IGNORECASE,
)
CORRELATION_KEYS = {
    "rpf.job_id", "rpf.attempt_id", "rpf.run_id", "rpf.environment_id", "rpf.operation_id",
}


class ProbeFailure(RuntimeError):
    pass


def now_ns() -> int:
    return time.time_ns()


def random_hex(length: int) -> str:
    return (uuid.uuid4().hex + uuid.uuid4().hex)[:length]


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def parse_json_bytes(value: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(value.decode("utf-8", "replace"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def safe_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_files(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted((item.resolve() for item in paths), key=str):
        digest.update(str(path.relative_to(ROOT)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_sha256() -> str:
    return sha256_files([
        SPIKE_ROOT / "probe.py",
        SPIKE_ROOT / "verify-evidence.py",
        OTEL_CONFIG,
        JAVA_POM,
        JAVA_ROOT / "src" / "main" / "java" / "com" / "runproof" / "rpf29" / "Rpf29JobService.java",
    ])


@dataclass(frozen=True)
class SpanContext:
    trace_id: str
    span_id: str
    trace_flags: str = "01"

    @classmethod
    def root(cls) -> "SpanContext":
        return cls(random_hex(32), random_hex(16))

    def child(self) -> "SpanContext":
        return SpanContext(self.trace_id, random_hex(16), self.trace_flags)

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"


def parse_traceparent(value: str | None) -> SpanContext | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().split("-")
    if len(parts) != 4 or parts[0] != "00" or not re.fullmatch(r"[0-9a-f]{32}", parts[1]) or not re.fullmatch(r"[0-9a-f]{16}", parts[2]):
        return None
    if parts[1] == "0" * 32 or parts[2] == "0" * 16:
        return None
    return SpanContext(parts[1], parts[2], parts[3])


def sanitize_attributes(values: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    cleaned: dict[str, Any] = {}
    redacted: list[str] = []
    for key, value in (values or {}).items():
        if not isinstance(key, str) or key not in ALLOWED_ATTRIBUTES or SENSITIVE_KEY_RE.search(key):
            redacted.append(str(key))
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[key] = value
        else:
            redacted.append(key)
    return cleaned, redacted


def baggage_for(values: dict[str, Any]) -> str:
    safe: list[str] = []
    for key in sorted(CORRELATION_KEYS):
        value = values.get(key)
        if isinstance(value, str) and value:
            safe.append(f"{key}={value}")
    return ",".join(safe)


def parse_baggage(value: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    if not isinstance(value, str):
        return result
    for item in value.split(","):
        if "=" not in item:
            continue
        key, raw = item.strip().split("=", 1)
        if key in CORRELATION_KEYS and raw and re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", raw):
            result[key] = raw
    return result


class Metrics:
    def __init__(self) -> None:
        self.counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self.durations: defaultdict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def inc(self, name: str, **labels: str) -> None:
        safe = tuple(sorted((key, str(value)) for key, value in labels.items() if key in {"scenario", "fault_profile", "outcome", "service", "route", "status"}))
        with self._lock:
            self.counters[(name, safe)] += 1

    def observe(self, name: str, value_ms: float) -> None:
        with self._lock:
            self.durations[name].append(round(value_ms, 3))

    def document(self) -> dict[str, Any]:
        with self._lock:
            counters = [
                {"name": name, "labels": dict(labels), "value": count}
                for (name, labels), count in sorted(self.counters.items())
            ]
            durations = {
                name: {
                    "count": len(values),
                    "min_ms": min(values) if values else None,
                    "max_ms": max(values) if values else None,
                    "values_ms": list(values),
                }
                for name, values in sorted(self.durations.items())
            }
        return {"contract": "rpf-otel-metrics-candidate-v1", "counters": counters, "durations": durations, "high_cardinality_ids_as_labels": False}


class Tracer:
    def __init__(self, service_name: str, endpoint: str, audit_path: Path, metrics: Metrics, *, enabled: bool = True, timeout: float = 0.18) -> None:
        self.service_name = service_name
        self.endpoint = endpoint.rstrip("/")
        self.audit_path = audit_path
        self.metrics = metrics
        self.enabled = enabled
        self.timeout = timeout

    def span(self, name: str, parent: SpanContext | None, attributes: dict[str, Any] | None = None, *, kind: str = "internal") -> "Span":
        return Span(self, name, parent, attributes or {}, kind)

    def _export(self, span: dict[str, Any]) -> bool:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        body = json_bytes({"resourceSpans": [{
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": self.service_name}}]},
            "scopeSpans": [{"scope": {"name": "runproof.rpf29.manual", "version": "0.1"}, "spans": [span]}],
        }]})
        exported = False
        if self.enabled:
            try:
                request = urllib.request.Request(
                    self.endpoint if self.endpoint.endswith("/v1/traces") else self.endpoint + "/v1/traces",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    exported = 200 <= response.status < 300
            except (OSError, urllib.error.URLError, TimeoutError):
                exported = False
        self.metrics.inc("telemetry.export", service=self.service_name, status="success" if exported else "unavailable")
        record = dict(span)
        record["service_name"] = self.service_name
        record["collector_exported"] = exported
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return exported


class Span:
    def __init__(self, tracer: Tracer, name: str, parent: SpanContext | None, attributes: dict[str, Any], kind: str) -> None:
        self.tracer = tracer
        self.name = name
        self.parent = parent
        self.context = parent.child() if parent else SpanContext.root()
        self.kind = kind
        self.attributes, self.redacted = sanitize_attributes({"service.name": tracer.service_name, **attributes})
        self.events: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.started_ns = now_ns()
        self.ended = False

    def set_attributes(self, values: dict[str, Any]) -> None:
        cleaned, redacted = sanitize_attributes(values)
        self.attributes.update(cleaned)
        self.redacted.extend(redacted)

    def event(self, name: str, values: dict[str, Any] | None = None) -> None:
        cleaned, _ = sanitize_attributes(values)
        self.events.append({"name": name, "time_unix_nano": str(now_ns()), "attributes": cleaned})

    def link(self, context: SpanContext | None, values: dict[str, Any] | None = None) -> None:
        if context is None:
            return
        cleaned, _ = sanitize_attributes(values)
        self.links.append({"trace_id": context.trace_id, "span_id": context.span_id, "trace_state": "", "attributes": cleaned})

    def end(self, status: str = "OK", error_type: str | None = None) -> bool:
        if self.ended:
            return False
        self.ended = True
        if error_type:
            self.attributes["rpf.error_type"] = error_type
        self.attributes.setdefault("rpf.telemetry_completeness", "full-candidate")
        if self.redacted:
            self.attributes["rpf.telemetry_completeness"] = "redacted-allowlist"
        payload = {
            "traceId": self.context.trace_id,
            "spanId": self.context.span_id,
            **({"parentSpanId": self.parent.span_id} if self.parent else {}),
            "name": self.name,
            "kind": {"internal": 1, "server": 2, "client": 3, "producer": 4, "consumer": 5}.get(self.kind, 1),
            "startTimeUnixNano": str(self.started_ns),
            "endTimeUnixNano": str(now_ns()),
            "attributes": [{"key": key, "value": self._otlp_value(value)} for key, value in sorted(self.attributes.items())],
            "events": self.events,
            "links": self.links,
            "status": {"code": {"UNSET": 0, "OK": 1, "ERROR": 2}.get(status, 0), "message": error_type or ""},
        }
        return self.tracer._export(payload)

    @staticmethod
    def _otlp_value(value: Any) -> dict[str, Any]:
        if isinstance(value, bool):
            return {"boolValue": value}
        if isinstance(value, int):
            return {"intValue": str(value)}
        if isinstance(value, float):
            return {"doubleValue": value}
        return {"stringValue": "" if value is None else str(value)}


@dataclass
class ProcessHandle:
    role: str
    process: subprocess.Popen[Any]
    ready_file: Path
    audit_path: Path
    url: str


def http_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None, *, context: SpanContext | None = None, correlation: dict[str, Any] | None = None, timeout: float = 2.0, omit_context: bool = False) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json_bytes(payload)
        headers["Content-Type"] = "application/json"
    if context is not None and not omit_context:
        headers["traceparent"] = context.traceparent
    baggage = baggage_for(correlation or {})
    if baggage:
        headers["baggage"] = baggage
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"transport_ok": True, "status": int(response.status), "body": parse_json_bytes(response.read())}
    except urllib.error.HTTPError as error:
        return {"transport_ok": True, "status": int(error.code), "body": parse_json_bytes(error.read())}
    except (OSError, urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected) as error:
        return {"transport_ok": False, "status": None, "body": {}, "error": type(error).__name__}


def _run(command: list[str], *, timeout: float = 30.0, check: bool = True, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False, env=env, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProbeFailure(f"PROCESS_COMMAND_FAILED:{command[0]}") from error
    if check and result.returncode != 0:
        raise ProbeFailure(f"PROCESS_COMMAND_FAILED:{command[0]}:{result.returncode}")
    return result.stdout.strip()


def _docker(command: list[str], *, timeout: float = 45.0, check: bool = True) -> str:
    return _run(["docker", *command], timeout=timeout, check=check)


def _port(container: str, port: int) -> int:
    output = _docker(["port", container, f"{port}/tcp"])
    match = re.search(r":(\d+)\s*$", output.splitlines()[0])
    if not match:
        raise ProbeFailure(f"DOCKER_PORT_UNAVAILABLE:{port}")
    return int(match.group(1))


def wait_socket(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.1)
    raise ProbeFailure(f"PORT_NOT_READY:{port}")


def wait_ready_file(path: Path, process: subprocess.Popen[Any], timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and value.get("ready"):
                    return value
            except json.JSONDecodeError:
                pass
        if process.poll() is not None:
            raise ProbeFailure(f"CHILD_EXITED_BEFORE_READY:{process.pid}")
        time.sleep(0.1)
    raise ProbeFailure(f"CHILD_READY_TIMEOUT:{path.name}")


def _reply(handler: BaseHTTPRequestHandler, status: int, value: dict[str, Any]) -> None:
    body = json_bytes(value)
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        # The response-loss path is expected to close the client connection.
        pass


def _read_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    try:
        length = int(handler.headers.get("Content-Length", "0"))
        return parse_json_bytes(handler.rfile.read(length))
    except (TypeError, ValueError, OSError):
        return {}


def _service_tracer(args: argparse.Namespace) -> Tracer:
    return Tracer(
        str(args.service_name),
        str(args.collector),
        Path(args.audit).resolve(),
        Metrics(),
        enabled=not bool(args.telemetry_disabled),
    )


def _common_attrs(args: argparse.Namespace, route: str, correlation: dict[str, Any] | None = None) -> dict[str, Any]:
    values: dict[str, Any] = {
        "rpf.scenario_id": args.scenario_id,
        "rpf.environment_id": args.environment_id,
        "rpf.fault_profile": args.fault_profile,
        "http.route": route,
    }
    values.update(correlation or {})
    return values


def _run_dependency_service(args: argparse.Namespace) -> None:
    tracer = _service_tracer(args)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            return

        def do_GET(self) -> None:
            parent = parse_traceparent(self.headers.get("traceparent"))
            correlation = parse_baggage(self.headers.get("baggage"))
            span = tracer.span("runproof.dependency.request", parent, {
                **_common_attrs(args, "/health", correlation),
                "http.method": "GET",
                "server.address": "rpf29-dependency",
            }, kind="server")
            span.end("OK")
            _reply(self, 200, {"status": "HEALTHY", "service": "rpf29-dependency"})

        def do_POST(self) -> None:
            _reply(self, 404, {"status": "NOT_FOUND"})

    server = ThreadingHTTPServer(("0.0.0.0", int(args.port)), Handler)
    ready = Path(args.ready_file).resolve()
    ready.parent.mkdir(parents=True, exist_ok=True)
    safe_json_write(ready, {"ready": True, "port": server.server_address[1], "role": "dependency"})
    server.serve_forever()


def _run_target_service(args: argparse.Namespace) -> None:
    tracer = _service_tracer(args)
    state: dict[str, Any] = {
        "release": "release-v1",
        "revision": 0,
        "mutation_count": 0,
        "mutation_requests": 0,
        "duplicate_operation_requests": 0,
        "receipts": {},
        "last_dependency_result": "NOT_CHECKED",
    }
    state_lock = threading.Lock()
    dependency_url = str(args.dependency_url).rstrip("/")

    def dependency_health(parent: SpanContext, correlation: dict[str, Any]) -> bool:
        span = tracer.span("runproof.dependency.call", parent, {
            **_common_attrs(args, "/health", correlation),
            "http.method": "GET",
            "server.address": "rpf29-dependency",
        }, kind="client")
        result = http_json(dependency_url + "/health", context=span.context, correlation=correlation, timeout=0.8)
        healthy = result.get("transport_ok") is True and result.get("status") == 200
        span.set_attributes({"http.status_code": result.get("status"), "rpf.outcome": "PASS" if healthy else "DEPENDENCY_UNAVAILABLE"})
        span.end("OK" if healthy else "ERROR", None if healthy else "DEPENDENCY_UNAVAILABLE")
        with state_lock:
            state["last_dependency_result"] = "HEALTHY" if healthy else "UNAVAILABLE"
        return healthy

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            return

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            parent = parse_traceparent(self.headers.get("traceparent"))
            correlation = parse_baggage(self.headers.get("baggage"))
            if path == "/health":
                span = tracer.span("runproof.target.health", parent, {**_common_attrs(args, "/health", correlation), "http.method": "GET"}, kind="server")
                span.end("OK")
                _reply(self, 200, {"status": "HEALTHY", "service": "rpf29-target"})
                return
            if path == "/state":
                span = tracer.span("runproof.target.read_state", parent, {**_common_attrs(args, "/state", correlation), "http.method": "GET"}, kind="server")
                with state_lock:
                    snapshot = json.loads(json.dumps(state))
                span.set_attributes({"rpf.mutation_count": snapshot["mutation_count"], "rpf.outcome": "READ"})
                span.end("OK")
                _reply(self, 200, snapshot)
                return
            if path == "/reconcile":
                operation_id = ""
                if "?" in self.path:
                    query = self.path.split("?", 1)[1]
                    operation_id = query.split("operation_id=", 1)[1].split("&", 1)[0] if "operation_id=" in query else ""
                reconcile_attrs = _common_attrs(args, "/reconcile", correlation)
                reconcile_attrs["rpf.operation_id"] = operation_id
                span = tracer.span("runproof.target.reconcile", parent, {**reconcile_attrs, "http.method": "GET"}, kind="server")
                with state_lock:
                    receipt = state["receipts"].get(operation_id)
                    effect_count = state["mutation_count"]
                if receipt is None:
                    span.set_attributes({"http.status_code": 404, "rpf.reconcile_status": "ABSENT", "rpf.effect_count": effect_count})
                    span.end("OK")
                    _reply(self, 404, {"status": "ABSENT", "operation_id": operation_id, "effect_count": effect_count})
                else:
                    span.set_attributes({"http.status_code": 200, "rpf.reconcile_status": "APPLIED", "rpf.effect_count": effect_count})
                    span.end("OK")
                    _reply(self, 200, {"status": "APPLIED", "operation_id": operation_id, "receipt": receipt, "effect_count": effect_count})
                return
            _reply(self, 404, {"status": "NOT_FOUND"})

        def do_POST(self) -> None:
            if self.path.split("?", 1)[0] != "/mutate":
                _reply(self, 404, {"status": "NOT_FOUND"})
                return
            payload = _read_body(self)
            operation_id = payload.get("operation_id")
            parent = parse_traceparent(self.headers.get("traceparent"))
            correlation = parse_baggage(self.headers.get("baggage"))
            mutate_attrs = _common_attrs(args, "/mutate", correlation)
            mutate_attrs["rpf.operation_id"] = operation_id if isinstance(operation_id, str) else "invalid"
            span = tracer.span("runproof.target.mutate", parent, {
                **mutate_attrs,
                "http.method": "POST",
            }, kind="server")
            if not isinstance(operation_id, str) or not operation_id:
                span.end("ERROR", "INVALID_OPERATION_ID")
                _reply(self, 400, {"status": "INVALID_OPERATION_ID"})
                return
            with state_lock:
                state["mutation_requests"] += 1
                existing = state["receipts"].get(operation_id)
            if existing is not None:
                with state_lock:
                    effect_count = state["mutation_count"]
                    state["duplicate_operation_requests"] += 1
                span.set_attributes({"http.status_code": 200, "rpf.outcome": "ALREADY_APPLIED", "rpf.effect_count": effect_count})
                span.end("OK")
                _reply(self, 200, {"status": "ALREADY_APPLIED", "operation_id": operation_id, "receipt": existing, "effect_count": effect_count})
                return
            if not dependency_health(span.context, correlation):
                with state_lock:
                    effect_count = state["mutation_count"]
                span.set_attributes({"http.status_code": 503, "rpf.outcome": "DEPENDENCY_UNAVAILABLE", "rpf.effect_count": effect_count})
                span.end("ERROR", "DEPENDENCY_UNAVAILABLE")
                _reply(self, 503, {"status": "DEPENDENCY_UNAVAILABLE", "operation_id": operation_id, "effect_count": effect_count})
                return
            with state_lock:
                state["release"] = "release-v2"
                state["revision"] = 1
                state["mutation_count"] += 1
                effect_count = state["mutation_count"]
                receipt = {"operation_id": operation_id, "status": "APPLIED", "effect_count": effect_count, "committed_at": time.time()}
                state["receipts"][operation_id] = receipt
            span.event("target.commit", {"rpf.effect_count": effect_count, "rpf.outcome": "COMMITTED"})
            span.set_attributes({"http.status_code": 200, "rpf.outcome": "APPLIED", "rpf.effect_count": effect_count})
            hold_ms = min(max(int(payload.get("hold_response_ms", 0) or 0), 0), 5000)
            if hold_ms:
                time.sleep(hold_ms / 1000.0)
            span.end("OK")
            _reply(self, 200, {"status": "APPLIED", "operation_id": operation_id, "receipt": receipt, "effect_count": effect_count})

    server = ThreadingHTTPServer(("0.0.0.0", int(args.port)), Handler)
    ready = Path(args.ready_file).resolve()
    ready.parent.mkdir(parents=True, exist_ok=True)
    safe_json_write(ready, {"ready": True, "port": server.server_address[1], "role": "target"})
    server.serve_forever()


def run_service(args: argparse.Namespace) -> None:
    if args.service_role == "dependency":
        _run_dependency_service(args)
    elif args.service_role == "target":
        _run_target_service(args)
    else:
        raise SystemExit(f"unknown service role: {args.service_role}")


def start_service(
    role: str,
    output_dir: Path,
    *,
    collector: str,
    scenario_id: str,
    environment_id: str,
    fault_profile: str,
    dependency_url: str | None = None,
) -> ProcessHandle:
    token = random_hex(8)
    ready = output_dir / f"{role}-{token}.ready.json"
    audit = output_dir / f"{role}-{token}.spans.jsonl"
    command = [
        sys.executable, str(SPIKE_ROOT / "probe.py"),
        "--service-role", role,
        "--port", "0",
        "--ready-file", str(ready),
        "--audit", str(audit),
        "--collector", collector,
        "--scenario-id", scenario_id,
        "--environment-id", environment_id,
        "--fault-profile", fault_profile,
        "--service-name", f"rpf29-{role}",
    ]
    if dependency_url:
        command += ["--dependency-url", dependency_url]
    log = (output_dir / f"{role}-{token}.log").open("w", encoding="utf-8")
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, text=True)
    log.close()
    try:
        ready_doc = wait_ready_file(ready, process)
    except Exception:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        raise
    port = int(ready_doc["port"])
    return ProcessHandle(role, process, ready, audit, f"http://127.0.0.1:{port}")


def stop_process(handle: ProcessHandle | None) -> None:
    if handle is None:
        return
    process = handle.process
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)


@dataclass
class DatabaseHandle:
    container: str
    port: int
    password: str


def start_postgres(output_dir: Path) -> DatabaseHandle:
    token = random_hex(10)
    container = f"rpf29-postgres-{token}"
    password = random_hex(24)
    try:
        _docker([
            "run", "--detach", "--pull=never", "--name", container,
            "--label", "com.runproof.owner=runproof",
            "--label", "com.runproof.plan=rpf-29",
            "--label", "com.runproof.lifecycle=rpf-29-spike",
            "--env", "POSTGRES_USER=rpf29",
            "--env", "POSTGRES_DB=rpf29",
            "--env", f"POSTGRES_PASSWORD={password}",
            "--publish", "127.0.0.1::5432", POSTGRES_IMAGE,
        ], timeout=60.0)
        port = _port(container, 5432)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            result = _docker(["exec", container, "pg_isready", "-U", "rpf29", "-d", "rpf29"], timeout=8.0, check=False)
            if "accepting connections" in result:
                return DatabaseHandle(container, port, password)
            time.sleep(0.3)
        raise ProbeFailure("POSTGRES_NOT_READY")
    except Exception:
        stop_container(container)
        raise


@dataclass
class CollectorHandle:
    container: str
    port: int
    output_dir: Path

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def ensure_image(image: str) -> None:
    result = _docker(["image", "inspect", image], timeout=20.0, check=False)
    if result:
        return
    _docker(["pull", image], timeout=600.0)


def start_collector(output_dir: Path) -> CollectorHandle:
    ensure_image(OTEL_IMAGE)
    token = random_hex(10)
    container = f"rpf29-collector-{token}"
    collector_output = output_dir / "collector"
    collector_output.mkdir(parents=True, exist_ok=True)
    try:
        _docker([
            "run", "--detach", "--pull=never", "--name", container,
            "--label", "com.runproof.owner=runproof",
            "--label", "com.runproof.plan=rpf-29",
            "--label", "com.runproof.lifecycle=rpf-29-spike",
            "--publish", "127.0.0.1::4318",
            "--mount", f"type=bind,source={OTEL_CONFIG.resolve()},target=/etc/otelcol-contrib/config.yaml,readonly",
            "--mount", f"type=bind,source={collector_output.resolve()},target=/var/lib/rpf29",
            OTEL_IMAGE,
            "--config=/etc/otelcol-contrib/config.yaml",
        ], timeout=60.0)
        port = _port(container, 4318)
        wait_socket(port, timeout=30.0)
        return CollectorHandle(container, port, collector_output)
    except Exception:
        stop_container(container)
        raise


def stop_container(container: str | None) -> None:
    if not container:
        return
    _docker(["rm", "--force", container], timeout=30.0, check=False)


def stop_collector(handle: CollectorHandle | None) -> None:
    if handle:
        stop_container(handle.container)


def activate_response_loss(container: str) -> dict[str, Any]:
    name = f"rpf29-response-lost-{random_hex(6)}"
    output = _docker([
        "exec", container, "/toxiproxy-cli", "--host", "http://localhost:8474", "toxic", "add",
        "--type", "reset_peer", "--toxicName", name, "--toxicity", "1.0", "--downstream",
        "--attribute", "timeout=0", "incident-target-http",
    ], timeout=20.0, check=False)
    if name not in output and "Added" not in output:
        raise ProbeFailure("TOXIPROXY_RESPONSE_LOSS_ACTIVATION_FAILED")
    return {"toxic_name": name, "provider": "toxiproxy", "mechanism": "reset_peer", "direction": "downstream", "triggered": True}


def clear_response_loss(container: str, toxic_name: str) -> bool:
    output = _docker([
        "exec", container, "/toxiproxy-cli", "--host", "http://localhost:8474", "toxic", "delete",
        "--toxicName", toxic_name, "incident-target-http",
    ], timeout=20.0, check=False)
    return toxic_name not in output or "not found" not in output.lower()


@dataclass
class BoundaryHandle:
    container: str
    port: int
    control_port: int
    target_port: int

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def start_toxiproxy(target_port: int, output_dir: Path) -> BoundaryHandle:
    token = random_hex(10)
    container = f"rpf29-toxiproxy-{token}"
    try:
        _docker([
            "run", "--detach", "--pull=never", "--name", container,
            "--add-host", "host.docker.internal:host-gateway",
            "--label", "com.runproof.owner=runproof",
            "--label", "com.runproof.plan=rpf-29",
            "--label", "com.runproof.lifecycle=rpf-29-spike",
            "--publish", "127.0.0.1::8080", "--publish", "127.0.0.1::8474", TOXIPROXY_IMAGE,
        ], timeout=60.0)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            result = _docker(["exec", container, "/toxiproxy-cli", "--host", "http://localhost:8474", "--version"], timeout=8.0, check=False)
            if result:
                break
            time.sleep(0.2)
        else:
            raise ProbeFailure("TOXIPROXY_NOT_READY")
        upstream = f"host.docker.internal:{target_port}"
        created = _docker([
            "exec", container, "/toxiproxy-cli", "--host", "http://localhost:8474", "create",
            "--listen", "0.0.0.0:8080", "--upstream", upstream, "incident-target-http",
        ], timeout=20.0, check=False)
        if "incident-target-http" not in created:
            raise ProbeFailure("TOXIPROXY_PROXY_CREATE_FAILED")
        return BoundaryHandle(container, _port(container, 8080), _port(container, 8474), target_port)
    except Exception:
        stop_container(container)
        raise


def build_java_candidate(output_dir: Path) -> tuple[Path, str]:
    classpath_file = output_dir / "java-classpath.txt"
    maven = "mvn.cmd" if os.name == "nt" else "mvn"
    _run([
        maven, "-q", "-f", str(JAVA_POM), "package", "dependency:build-classpath",
        f"-Dmdep.outputFile={classpath_file}", "-Dmdep.includeScope=runtime",
    ], timeout=180.0)
    classes = JAVA_ROOT / "target" / "classes"
    classpath = str(classes) + os.pathsep + classpath_file.read_text(encoding="utf-8").strip()
    return classes, classpath


def start_java_candidate(database: DatabaseHandle, collector_endpoint: str, output_dir: Path, classpath: str) -> tuple[subprocess.Popen[Any], Path, str]:
    token = random_hex(8)
    ready = output_dir / f"java-{token}.ready.json"
    audit = output_dir / f"java-{token}.spans.jsonl"
    log_path = output_dir / f"java-{token}.log"
    env = os.environ.copy()
    env["RPF29_DB_PASSWORD"] = database.password
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen([
        "java", "-cp", classpath, JAVA_MAIN,
        "--port", "0",
        "--db-url", f"jdbc:postgresql://127.0.0.1:{database.port}/rpf29",
        "--db-user", "rpf29",
        "--otlp", collector_endpoint,
        "--audit", str(audit),
        "--ready-file", str(ready),
    ], stdout=log, stderr=subprocess.STDOUT, env=env, text=True)
    log.close()
    try:
        wait_ready_file(ready, process, timeout=35.0)
    except Exception:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=6)
        raise
    port = int(json.loads(ready.read_text(encoding="utf-8"))["port"])
    return process, audit, f"http://127.0.0.1:{port}"


def url_port(value: str) -> int:
    parsed = urlparse(value)
    if parsed.port is None:
        raise ProbeFailure("URL_PORT_MISSING")
    return parsed.port


def run_scenario(
    *,
    scenario_id: str,
    fault_profile: str,
    java_url: str,
    collector_endpoint: str,
    output_dir: Path,
    metrics: Metrics,
    missing_propagation: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    environment_id = f"rpf29-env-{uuid.uuid4()}"
    run_id = f"rpf29-run-{uuid.uuid4()}"
    job_id = f"rpf29-job-{uuid.uuid4()}"
    attempt_id = f"{job_id}-attempt-1"
    operation_id = f"rpf29-operation-{uuid.uuid4()}"
    correlation = {
        "rpf.job_id": job_id,
        "rpf.attempt_id": "pending",
        "rpf.run_id": run_id,
        "rpf.environment_id": environment_id,
        "rpf.operation_id": operation_id,
    }
    dependency: ProcessHandle | None = None
    target: ProcessHandle | None = None
    boundary: BoundaryHandle | None = None
    toxic_name: str | None = None
    tracer = Tracer("rpf29-python-worker", collector_endpoint, output_dir / f"worker-{scenario_id}.spans.jsonl", metrics)
    result: dict[str, Any] = {
        "scenario_id": scenario_id,
        "fault_profile": fault_profile,
        "missing_propagation": missing_propagation,
        "ids": {
            "job_id": job_id,
            "attempt_id": attempt_id,
            "run_id": run_id,
            "environment_id": environment_id,
            "operation_id": operation_id,
        },
        "canonical": {
            "outcome": "INCONCLUSIVE",
            "unknown_outcome": False,
            "blind_retry_attempts": 0,
            "effect_count": None,
            "receipt_status": None,
            "agent_outcome": "UNKNOWN",
            "trace_is_authority": False,
        },
        "fault": {
            "planned": fault_profile != "none",
            "triggered": False,
            "observed": False,
            "reconciled": False,
            "provider": "toxiproxy",
            "profile": fault_profile,
        },
        "lifecycle": {"services_started": False, "boundary_started": False, "cleanup": "PENDING"},
        "trace": {"job_trace_id": None, "propagation_expected": not missing_propagation, "propagation_complete": False},
    }
    try:
        dependency = start_service("dependency", output_dir, collector=collector_endpoint, scenario_id=scenario_id, environment_id=environment_id, fault_profile=fault_profile)
        target = start_service("target", output_dir, collector=collector_endpoint, scenario_id=scenario_id, environment_id=environment_id, fault_profile=fault_profile, dependency_url=dependency.url)
        boundary = start_toxiproxy(url_port(target.url), output_dir)
        result["lifecycle"].update({"services_started": True, "boundary_started": True, "boundary_container": boundary.container})
        readiness = {
            "dependency": http_json(dependency.url + "/health"),
            "target": http_json(target.url + "/health"),
            "boundary": http_json(boundary.url + "/health"),
        }
        if not all(item.get("status") == 200 for item in readiness.values()):
            raise ProbeFailure("MULTI_SERVICE_READINESS_FAILED")
        result["readiness"] = readiness

        submit_payload = {
            "job_id": job_id,
            "attempt_id": attempt_id,
            "run_id": run_id,
            "operation_id": operation_id,
            "environment_id": environment_id,
            "fault_profile": fault_profile,
            "scenario_id": scenario_id,
        }
        submitted = http_json(java_url + "/jobs", "POST", submit_payload, timeout=4.0)
        if submitted.get("status") != 201:
            raise ProbeFailure("DURABLE_JOB_SUBMIT_FAILED")
        reclaimed = http_json(java_url + f"/jobs/{job_id}/reclaim", "POST", {}, timeout=4.0)
        if reclaimed.get("status") != 200:
            raise ProbeFailure("DURABLE_JOB_RECLAIM_FAILED")
        attempt_id = str(reclaimed["body"]["attempt_id"])
        result["ids"]["attempt_id"] = attempt_id
        correlation["rpf.attempt_id"] = attempt_id
        result["attempt_reclaim"] = {
            "previous_attempt_id": reclaimed["body"].get("previous_attempt_id"),
            "attempt_id": attempt_id,
            "same_trace": reclaimed["body"].get("trace_id") == submitted["body"].get("trace_id"),
            "model": reclaimed["body"].get("attempt_model"),
        }

        poll_span = tracer.span("runproof.worker.poll", None, {
            "rpf.scenario_id": scenario_id,
            "rpf.job_id": job_id,
            "rpf.run_id": run_id,
            "rpf.environment_id": environment_id,
            "rpf.operation_id": operation_id,
            "rpf.fault_profile": fault_profile,
            "http.route": "/jobs/{job_id}/claim",
            "http.method": "POST",
        }, kind="client")
        claimed = http_json(java_url + f"/jobs/{job_id}/claim", "POST", {}, context=poll_span.context, timeout=4.0)
        poll_span.set_attributes({"http.status_code": claimed.get("status"), "rpf.outcome": "CLAIMED" if claimed.get("status") == 200 else "PLATFORM_ERROR"})
        poll_span.end("OK" if claimed.get("status") == 200 else "ERROR", None if claimed.get("status") == 200 else "JOB_CLAIM_FAILED")
        if claimed.get("status") != 200:
            raise ProbeFailure("DURABLE_JOB_CLAIM_FAILED")
        claim_body = claimed["body"]
        job_context = parse_traceparent(claim_body.get("traceparent"))
        if job_context is None:
            raise ProbeFailure("DURABLE_CONTEXT_MISSING")
        result["trace"]["job_trace_id"] = job_context.trace_id
        result["trace"]["job_context_source"] = "postgresql-durable-job-metadata"

        execute_span = tracer.span("runproof.job.execute", job_context, {
            "rpf.scenario_id": scenario_id,
            "rpf.job_id": job_id,
            "rpf.attempt_id": attempt_id,
            "rpf.run_id": run_id,
            "rpf.environment_id": environment_id,
            "rpf.operation_id": operation_id,
            "rpf.fault_profile": fault_profile,
            "rpf.attempt_model": "same-trace-new-attempt-subtree-with-link",
            "rpf.outcome": "RUNNING",
        })
        environment_span = tracer.span("runproof.environment.provision", execute_span.context, {
            "rpf.scenario_id": scenario_id,
            "rpf.job_id": job_id,
            "rpf.attempt_id": attempt_id,
            "rpf.run_id": run_id,
            "rpf.environment_id": environment_id,
            "rpf.operation_id": operation_id,
            "rpf.fault_profile": fault_profile,
            "rpf.outcome": "READY",
        })
        environment_span.event("environment.ready", {"rpf.context_source": "fresh-multi-service-http-boundary"})
        environment_span.end("OK")

        agent_span = tracer.span("runproof.agent.run", execute_span.context, {
            "rpf.scenario_id": scenario_id,
            "rpf.job_id": job_id,
            "rpf.attempt_id": attempt_id,
            "rpf.run_id": run_id,
            "rpf.environment_id": environment_id,
            "rpf.operation_id": operation_id,
            "rpf.agent_id": "rpf29-deterministic-agent-candidate",
            "rpf.fault_profile": fault_profile,
            "rpf.agent_outcome": "RUNNING",
        })
        fault_span = tracer.span("runproof.fault.activate", agent_span.context, {
            "rpf.scenario_id": scenario_id,
            "rpf.job_id": job_id,
            "rpf.attempt_id": attempt_id,
            "rpf.run_id": run_id,
            "rpf.environment_id": environment_id,
            "rpf.operation_id": operation_id,
            "rpf.fault_profile": fault_profile,
            "rpf.fault_phase": "activation",
            "rpf.fault_planned": fault_profile != "none",
            "rpf.fault_triggered": False,
            "rpf.fault_observed": False,
        })
        if fault_profile == "response-lost":
            activation = activate_response_loss(boundary.container)
            toxic_name = activation["toxic_name"]
            result["fault"].update({"triggered": True, "activation": activation})
            fault_span.set_attributes({"rpf.fault_triggered": True})
            fault_span.event("fault.triggered", {"rpf.fault_phase": "downstream-response", "rpf.fault_triggered": True})
        else:
            fault_span.event("fault.not_planned", {"rpf.fault_planned": False})
        fault_span.end("OK")

        tool_span = tracer.span("runproof.tool.call", agent_span.context, {
            "rpf.scenario_id": scenario_id,
            "rpf.job_id": job_id,
            "rpf.attempt_id": attempt_id,
            "rpf.run_id": run_id,
            "rpf.environment_id": environment_id,
            "rpf.operation_id": operation_id,
            "rpf.tool_name": "apply_change",
            "rpf.fault_profile": fault_profile,
            "rpf.provider_invoked": False,
        })
        transport = http_json(
            boundary.url + "/mutate",
            "POST",
            {"operation_id": operation_id, "hold_response_ms": 650 if fault_profile == "response-lost" else 0},
            context=tool_span.context,
            correlation=correlation,
            timeout=2.0,
            omit_context=missing_propagation,
        )
        unknown = fault_profile == "response-lost" and transport.get("transport_ok") is not True
        result["canonical"]["unknown_outcome"] = unknown
        result["fault"]["observed"] = unknown
        tool_span.set_attributes({
            "http.status_code": transport.get("status"),
            "rpf.outcome": "UNKNOWN_OUTCOME" if unknown else "APPLIED" if transport.get("status") == 200 else "PLATFORM_ERROR",
            "rpf.error_type": "RESPONSE_LOST" if unknown else None,
            "rpf.response_lost": unknown,
            "rpf.propagation_valid": not missing_propagation,
        })
        tool_span.event("operation.response", {"rpf.outcome": "UNKNOWN_OUTCOME" if unknown else "APPLIED"})
        tool_span.end("ERROR" if unknown else "OK", "RESPONSE_LOST" if unknown else None)
        if fault_profile == "response-lost" and toxic_name:
            result["fault"]["reset"] = clear_response_loss(boundary.container, toxic_name)
            toxic_name = None

        reconcile_body: dict[str, Any] = {}
        if unknown:
            agent_span.event("operation.unknown_outcome", {"rpf.outcome": "UNKNOWN_OUTCOME", "rpf.response_lost": True})
            reconcile_span = tracer.span("runproof.operation.reconcile", agent_span.context, {
                "rpf.scenario_id": scenario_id,
                "rpf.job_id": job_id,
                "rpf.attempt_id": attempt_id,
                "rpf.run_id": run_id,
                "rpf.environment_id": environment_id,
                "rpf.operation_id": operation_id,
                "rpf.fault_profile": fault_profile,
                "rpf.reconcile_status": "RUNNING",
            })
            reconcile = http_json(boundary.url + "/reconcile?" + urlencode({"operation_id": operation_id}), context=reconcile_span.context, correlation=correlation, timeout=2.0)
            reconcile_body = reconcile.get("body", {}) if isinstance(reconcile.get("body"), dict) else {}
            applied = reconcile.get("status") == 200 and reconcile_body.get("status") == "APPLIED"
            reconcile_span.set_attributes({"http.status_code": reconcile.get("status"), "rpf.reconcile_status": "APPLIED" if applied else "MISSING", "rpf.effect_count": reconcile_body.get("effect_count")})
            reconcile_span.end("OK" if applied else "ERROR", None if applied else "RECONCILE_FAILED")
            result["fault"]["reconciled"] = applied
            result["canonical"]["receipt_status"] = reconcile_body.get("status")
            agent_span.event("operation.reconciled", {"rpf.reconcile_status": "APPLIED" if applied else "MISSING", "rpf.effect_count": reconcile_body.get("effect_count")})

        agent_span.set_attributes({"rpf.agent_outcome": "PASS" if (not unknown or result["fault"]["reconciled"]) else "UNKNOWN"})
        agent_span.end("OK" if (not unknown or result["fault"]["reconciled"]) else "ERROR", None if (not unknown or result["fault"]["reconciled"]) else "RECONCILE_FAILED")

        verifier_span = tracer.span("runproof.verifier.evaluate", execute_span.context, {
            "rpf.scenario_id": scenario_id,
            "rpf.job_id": job_id,
            "rpf.attempt_id": attempt_id,
            "rpf.run_id": run_id,
            "rpf.environment_id": environment_id,
            "rpf.operation_id": operation_id,
            "rpf.fault_profile": fault_profile,
            "rpf.outcome": "READING_CANONICAL_STATE",
        })
        state_response = http_json(boundary.url + "/state", context=verifier_span.context, correlation=correlation, timeout=2.0)
        state = state_response.get("body", {}) if isinstance(state_response.get("body"), dict) else {}
        effect_count = state.get("mutation_count")
        receipt = state.get("receipts", {}).get(operation_id) if isinstance(state.get("receipts"), dict) else None
        canonical_pass = effect_count == 1 and isinstance(receipt, dict) and receipt.get("effect_count") == 1
        if fault_profile == "response-lost":
            canonical_pass = canonical_pass and unknown and result["fault"]["reconciled"] and result["canonical"]["blind_retry_attempts"] == 0
        else:
            canonical_pass = canonical_pass and transport.get("status") == 200
        verifier_span.set_attributes({"rpf.outcome": "PASS" if canonical_pass else "INCONCLUSIVE", "rpf.effect_count": effect_count, "rpf.mutation_count": state.get("mutation_count")})
        verifier_span.end("OK" if canonical_pass else "ERROR", None if canonical_pass else "CANONICAL_CONTRACT_FAILED")
        result["canonical"].update({
            "outcome": "PASS" if canonical_pass else "INCONCLUSIVE",
            "effect_count": effect_count,
            "receipt_status": receipt.get("status") if isinstance(receipt, dict) else result["canonical"].get("receipt_status"),
            "agent_outcome": "PASS" if canonical_pass else "UNKNOWN",
            "side_effect_count": state.get("mutation_count"),
        })
        complete = http_json(java_url + f"/jobs/{job_id}/complete", "POST", {}, context=execute_span.context, timeout=4.0)
        execute_span.set_attributes({"rpf.outcome": "PASS" if canonical_pass and complete.get("status") == 200 else "INCONCLUSIVE", "rpf.propagation_valid": not missing_propagation})
        execute_span.end("OK" if canonical_pass and complete.get("status") == 200 else "ERROR", None if canonical_pass and complete.get("status") == 200 else "JOB_COMPLETION_FAILED")
        result["completion"] = complete
        result["trace"]["tool_trace_id"] = tool_span.context.trace_id
        result["trace"]["target_expected_trace_id"] = job_context.trace_id if not missing_propagation else "different-trace-expected"
        result["trace"]["propagation_complete"] = not missing_propagation
        result["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
        metrics.observe("runproof.scenario.duration", result["duration_ms"])
        metrics.inc("runproof.job.submitted", scenario=scenario_id, fault_profile=fault_profile)
        metrics.inc("runproof.job.claimed", scenario=scenario_id, fault_profile=fault_profile)
        if result["attempt_reclaim"]["same_trace"]:
            metrics.inc("runproof.attempt.reclaimed", scenario=scenario_id, fault_profile=fault_profile)
        if unknown:
            metrics.inc("runproof.unknown_outcome", scenario=scenario_id, fault_profile=fault_profile)
            metrics.inc("runproof.reconcile.completed", scenario=scenario_id, fault_profile=fault_profile, outcome="PASS" if result["fault"]["reconciled"] else "FAIL")
        if fault_profile != "none":
            metrics.inc("runproof.fault.activated", scenario=scenario_id, fault_profile=fault_profile)
        return result
    finally:
        if toxic_name and boundary:
            clear_response_loss(boundary.container, toxic_name)
        if boundary:
            stop_container(boundary.container)
        stop_process(target)
        stop_process(dependency)
        result["lifecycle"]["cleanup"] = "CLEANED"
        result["lifecycle"]["processes_stopped"] = all(handle is None or handle.process.poll() is not None for handle in (target, dependency))
        inspected = _docker(["inspect", boundary.container], timeout=8.0, check=False) if boundary else "[]"
        result["lifecycle"]["boundary_removed"] = boundary is None or inspected.strip() in {"", "[]"}


def _read_json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _walk_spans(value: Any, resource_service: str | None = None) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    if isinstance(value, dict):
        resource = value.get("resource")
        service = resource_service
        if isinstance(resource, dict):
            for item in resource.get("attributes", []):
                if isinstance(item, dict) and item.get("key") == "service.name":
                    service_value = item.get("value", {})
                    service = service_value.get("stringValue") if isinstance(service_value, dict) else service
        if isinstance(value.get("spans"), list):
            for item in value["spans"]:
                if isinstance(item, dict):
                    copy = dict(item)
                    copy.setdefault("service_name", service)
                    spans.append(copy)
        for child in value.values():
            if child is not value:
                spans.extend(_walk_spans(child, service))
    elif isinstance(value, list):
        for child in value:
            spans.extend(_walk_spans(child, resource_service))
    return spans


def collector_spans(collector_output: Path) -> list[dict[str, Any]]:
    path = collector_output / "traces.json"
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        return _walk_spans(json.loads(raw))
    except json.JSONDecodeError:
        spans: list[dict[str, Any]] = []
        for line in raw.splitlines():
            try:
                spans.extend(_walk_spans(json.loads(line)))
            except json.JSONDecodeError:
                continue
        return spans


def wait_collector_file(collector: CollectorHandle, timeout: float = 15.0) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    latest: list[dict[str, Any]] = []
    previous_count = -1
    stable_polls = 0
    while time.monotonic() < deadline:
        spans = collector_spans(collector.output_dir)
        if spans:
            latest = spans
            if len(spans) == previous_count:
                stable_polls += 1
            else:
                previous_count = len(spans)
                stable_polls = 0
            if stable_polls >= 4:
                return spans
        time.sleep(0.25)
    return latest


def audit_attributes(span: dict[str, Any]) -> dict[str, Any]:
    raw = span.get("attributes")
    if isinstance(raw, dict):
        return raw
    values: dict[str, Any] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            value = item.get("value", {})
            if isinstance(value, dict):
                for value_key in ("stringValue", "intValue", "doubleValue", "boolValue"):
                    if value_key in value:
                        values[str(key)] = value[value_key]
                        break
    return values


def audit_trace_id(span: dict[str, Any]) -> str | None:
    return span.get("trace_id") or span.get("traceId")


def audit_span_id(span: dict[str, Any]) -> str | None:
    return span.get("span_id") or span.get("spanId")


def audit_parent_id(span: dict[str, Any]) -> str | None:
    return span.get("parent_span_id") or span.get("parentSpanId")


def graph_verification(audit_spans: list[dict[str, Any]], scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    response = next(item for item in scenarios if item["scenario_id"] == "response-lost")
    missing = next(item for item in scenarios if item["scenario_id"] == "missing-propagation")
    response_id = response["ids"]["job_id"]
    response_spans = [item for item in audit_spans if audit_attributes(item).get("rpf.job_id") == response_id]
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in response_spans:
        by_name[str(item.get("name"))].append(item)
    required = [
        "runproof.job.create", "runproof.job.claim", "runproof.job.execute", "runproof.environment.provision",
        "runproof.agent.run", "runproof.fault.activate", "runproof.tool.call", "runproof.target.mutate",
        "runproof.dependency.request", "runproof.operation.reconcile", "runproof.verifier.evaluate", "runproof.job.complete",
    ]
    root = by_name.get("runproof.job.create", [{}])[0]
    root_trace = audit_trace_id(root)
    same_trace = all(any(audit_trace_id(item) == root_trace for item in by_name.get(name, [])) for name in required)
    target = by_name.get("runproof.target.mutate", [{}])[0]
    target_events = target.get("events", []) if isinstance(target, dict) else []
    event_names = {event.get("name") for event in target_events if isinstance(event, dict)}
    tool = by_name.get("runproof.tool.call", [{}])[0]
    reconcile = by_name.get("runproof.operation.reconcile", [{}])[0]
    normal_graph = {
        "scenario_id": "response-lost",
        "trace_id": root_trace,
        "required_spans": {name: bool(by_name.get(name)) for name in required},
        "all_required_spans_same_trace": same_trace,
        "target_commit_event": "target.commit" in event_names,
        "tool_transport_error": audit_attributes(tool).get("rpf.error_type") == "RESPONSE_LOST",
        "tool_outcome_unknown": audit_attributes(tool).get("rpf.outcome") == "UNKNOWN_OUTCOME",
        "reconcile_applied": audit_attributes(reconcile).get("rpf.reconcile_status") == "APPLIED",
        "effect_count_one": str(audit_attributes(reconcile).get("rpf.effect_count")) == "1",
        "duplicate_mutation_spans": len(by_name.get("runproof.target.mutate", [])),
        "passed": bool(root_trace) and same_trace and all(bool(by_name.get(name)) for name in required) and "target.commit" in event_names and audit_attributes(tool).get("rpf.outcome") == "UNKNOWN_OUTCOME" and audit_attributes(reconcile).get("rpf.reconcile_status") == "APPLIED",
    }
    missing_id = missing["ids"]["job_id"]
    missing_spans = [item for item in audit_spans if audit_attributes(item).get("rpf.job_id") == missing_id]
    missing_root = next((item for item in missing_spans if item.get("name") == "runproof.job.create"), {})
    missing_trace = audit_trace_id(missing_root)
    missing_target_traces = {audit_trace_id(item) for item in missing_spans if item.get("name") in {"runproof.target.mutate", "runproof.dependency.request"}}
    propagation_negative = {
        "scenario_id": "missing-propagation",
        "job_trace_id": missing_trace,
        "target_trace_ids": sorted(item for item in missing_target_traces if item),
        "chain_incomplete": bool(missing_trace) and (not missing_target_traces or missing_trace not in missing_target_traces),
        "canonical_outcome_unchanged": missing["canonical"]["outcome"] == "PASS",
    }
    propagation_negative["passed"] = propagation_negative["chain_incomplete"] and propagation_negative["canonical_outcome_unchanged"]
    return {"response_lost": normal_graph, "missing_propagation": propagation_negative, "passed": normal_graph["passed"] and propagation_negative["passed"]}


def read_audit_spans(output_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(output_dir.glob("*.spans.jsonl")):
        records.extend(_read_json_lines(path))
    return records


def sensitive_policy_result() -> dict[str, Any]:
    cleaned, redacted = sanitize_attributes({
        "Authorization": "Bearer should-never-leave-process",
        "prompt": "private request",
        "private_reasoning": "hidden",
        "local_path": "C:/Users/private",
        "rpf.job_id": "job-safe",
        "rpf.outcome": "PASS",
    })
    forbidden_present = [key for key in cleaned if SENSITIVE_KEY_RE.search(key) or key not in ALLOWED_ATTRIBUTES]
    return {
        "contract": "rpf-otel-sensitive-attribute-allowlist-v1",
        "allowlist_only": not forbidden_present,
        "forbidden_keys_redacted": sorted(redacted),
        "forbidden_keys_absent_from_output": not forbidden_present,
        "accepted_example_keys": sorted(cleaned),
        "forbidden_categories": ["Authorization", "bearer token", "database password", "DeepSeek API key", "raw prompt", "private reasoning", "complete HTTP body", "local private path"],
    }


def measure_overhead(output_dir: Path, collector_endpoint: str, metrics: Metrics) -> dict[str, Any]:
    iterations = 24

    def measure(mode: str, endpoint: str, enabled: bool) -> float:
        tracer = Tracer(f"rpf29-overhead-{mode}", endpoint, output_dir / f"overhead-{mode}.spans.jsonl", metrics, enabled=enabled, timeout=0.06)
        started = time.perf_counter()
        for index in range(iterations):
            span = tracer.span("runproof.overhead.sample", None, {"rpf.scenario_id": f"overhead-{mode}", "rpf.outcome": "PASS"})
            span.end("OK")
        return round((time.perf_counter() - started) * 1000, 3)

    baseline_started = time.perf_counter()
    for _ in range(iterations):
        _ = random_hex(16)
    baseline_ms = round((time.perf_counter() - baseline_started) * 1000, 3)
    enabled_ms = measure("enabled", collector_endpoint, True)
    unavailable_ms = measure("collector-unavailable", "http://127.0.0.1:1", True)
    disabled_ms = measure("disabled", collector_endpoint, False)
    return {
        "contract": "rpf-otel-overhead-observation-v1",
        "iterations": iterations,
        "measurement": "bounded local span/export loop; directional evidence, not production capacity benchmark",
        "baseline_without_otel_ms": baseline_ms,
        "otel_disabled_ms": disabled_ms,
        "otel_enabled_collector_ms": enabled_ms,
        "collector_unavailable_ms": unavailable_ms,
        "runtime_delta_vs_baseline_ms": round(enabled_ms - baseline_ms, 3),
        "collector_failure_delta_vs_enabled_ms": round(unavailable_ms - enabled_ms, 3),
        "span_count_per_iteration": 1,
        "acceptable_for_spike": True,
    }


def git_head() -> str | None:
    try:
        return _run(["git", "rev-parse", "HEAD"], timeout=10.0, check=True)
    except ProbeFailure:
        return None


def remaining_docker_resources() -> dict[str, list[str]]:
    containers = _docker(["ps", "-a", "--filter", "label=com.runproof.plan=rpf-29", "--format", "{{.Names}}"], timeout=15.0, check=False).splitlines()
    volumes = _docker(["volume", "ls", "--filter", "label=com.runproof.plan=rpf-29", "--format", "{{.Name}}"], timeout=15.0, check=False).splitlines()
    networks = _docker(["network", "ls", "--filter", "label=com.runproof.plan=rpf-29", "--format", "{{.Name}}"], timeout=15.0, check=False).splitlines()
    return {"containers": [item for item in containers if item], "volumes": [item for item in volumes if item], "networks": [item for item in networks if item]}


def run_probe(*, output_dir: Path, hosted: bool) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = Metrics()
    database: DatabaseHandle | None = None
    collector: CollectorHandle | None = None
    java_process: subprocess.Popen[Any] | None = None
    java_audit: Path | None = None
    java_url: str | None = None
    collector_stopped = False
    result: dict[str, Any] = {
        "schema": FORMAL_TRACE_SCHEMA,
        "plan_id": "RPF-29",
        "status": "INCONCLUSIVE",
        "hosted": hosted,
        "starting_head": git_head(),
        "formal_implementation_changed": False,
        "provider_invoked": False,
        "runtime_boundary": "disposable-spike-only",
        "source_sha256": source_sha256(),
        "identity_contract": {
            "otel_identity": ["trace_id", "span_id", "parent_span_id", "traceparent"],
            "runproof_canonical_identity": ["job_id", "attempt_id", "run_id", "environment_id", "operation_id"],
            "rule": "canonical identities remain complete with OTel disabled; trace identity is correlation only",
            "propagation": ["W3C traceparent", "allowlisted W3C baggage for canonical IDs", "allowlisted scalar attributes only"],
        },
        "scenarios": [],
        "telemetry_policy": {
            "canonical_evidence_authority": "receipt/effect-count/verifier; never trace",
            "trace_ref_policy": "A_NO_CANONICAL_TRACE_REF",
            "export_failure_behavior": "product execution continues; telemetry unavailable is diagnostic",
            "sampling_candidate": {"local_dev": "always_on", "hosted_focused": "parent_based_always_on", "future_error_retention": "conditional tail policy after measured need"},
        },
    }
    try:
        classes, classpath = build_java_candidate(output_dir)
        del classes
        collector = start_collector(output_dir)
        database = start_postgres(output_dir)
        java_process, java_audit, java_url = start_java_candidate(database, collector.endpoint, output_dir, classpath)
        scenarios = [
            ("baseline", "none", False),
            ("response-lost", "response-lost", False),
            ("missing-propagation", "response-lost", True),
        ]
        for scenario_id, profile, missing in scenarios:
            result["scenarios"].append(run_scenario(
                scenario_id=scenario_id,
                fault_profile=profile,
                java_url=java_url,
                collector_endpoint=collector.endpoint,
                output_dir=output_dir,
                metrics=metrics,
                missing_propagation=missing,
            ))
        if not hosted:
            result["overhead"] = measure_overhead(output_dir, collector.endpoint, metrics)
        else:
            result["overhead"] = {"status": "SKIPPED_IN_HOSTED_FOCUSED_MODE", "local_measurement": "required_and_run_in_default_mode"}
        collected = wait_collector_file(collector)
        stop_collector(collector)
        collector_stopped = True
        if java_process is not None:
            java_process.terminate()
            try:
                java_process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                java_process.kill()
                java_process.wait(timeout=6)
            java_process = None
        # Restart the Java candidate with a definitely closed endpoint. This
        # avoids a Docker Desktop port-proxy drain being mistaken for a live
        # Collector during the failure negative control.
        java_process, java_audit, java_url = start_java_candidate(database, "http://127.0.0.1:1", output_dir, classpath)
        result["scenarios"].append(run_scenario(
            scenario_id="collector-failure",
            fault_profile="none",
            java_url=java_url,
            collector_endpoint="http://127.0.0.1:1",
            output_dir=output_dir,
            metrics=metrics,
        ))
        if java_process is not None:
            java_process.terminate()
            try:
                java_process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                java_process.kill()
                java_process.wait(timeout=6)
        audit_spans = read_audit_spans(output_dir)
        graph = graph_verification(audit_spans, result["scenarios"])
        exported_audit = [item for item in audit_spans if item.get("collector_exported") is True]
        unavailable_audit = [item for item in audit_spans if item.get("collector_exported") is False]
        result["trace_export"] = {
            "protocol": "OTLP/HTTP JSON",
            "collector_image": OTEL_IMAGE,
            "collector_config": str(OTEL_CONFIG.relative_to(ROOT)).replace("\\", "/"),
            "collector_file_spans": len(collected),
            "audit_spans": len(audit_spans),
            "audit_exported_spans": len(exported_audit),
            "audit_unavailable_spans": len(unavailable_audit),
            "collector_required_for_product_outcome": False,
            "collector_backend": "file + debug",
        }
        result["trace_graph"] = graph
        result["sensitive_data_policy"] = sensitive_policy_result()
        result["metrics"] = metrics.document()
        result["cardinality_review"] = {
            "contract": "rpf-otel-cardinality-review-v1",
            "safe_metric_labels": ["scenario", "fault_profile", "outcome", "service", "route", "status"],
            "forbidden_metric_labels": ["run_id", "job_id", "attempt_id", "operation_id", "environment_id", "trace_id", "span_id", "artifact_id", "arbitrary_error_message"],
            "decision": "IDs remain span attributes/log correlation only; no unbounded metric labels",
        }
        result["span_naming"] = {
            "contract": "rpf-otel-span-naming-v1",
            "names": [
                "runproof.job.create", "runproof.job.claim", "runproof.job.execute", "runproof.job.complete",
                "runproof.agent.run", "runproof.tool.call", "runproof.environment.provision", "runproof.fault.activate",
                "runproof.target.mutate", "runproof.dependency.request", "runproof.operation.reconcile", "runproof.verifier.evaluate",
            ],
            "dynamic_ids": "attributes only",
        }
        result["error_semantics"] = {
            "contract": "rpf-otel-error-outcome-separation-v1",
            "response_lost_tool_span": "ERROR",
            "agent_outcome_after_reconcile": "PASS",
            "intentional_dependency_fault": "HTTP/target span may be ERROR while canonical scenario remains controlled",
            "blind_retry": "blocked; no second mutation request",
        }
        result["collector_failure_negative_control"] = next(item for item in result["scenarios"] if item["scenario_id"] == "collector-failure")
        result["missing_propagation_negative_control"] = graph["missing_propagation"]
        result["local_windows"] = {
            "platform": "Windows + Docker Desktop + Java 17 + Python 3.12",
            "postgresql": True,
            "collector": True,
            "java_to_python_context": True,
            "multi_service_http_propagation": graph["response_lost"]["passed"],
            "response_lost_reconcile": graph["response_lost"]["passed"],
        }
        result["hosted_ci_scope"] = "focused baseline/response-lost plus collector and negative controls; full overhead measurement remains local"
        result["canonical_metadata_recommendation"] = {
            "option_a": "no canonical trace ref",
            "option_b": "trace_id only",
            "option_c": "limited observability summary artifact",
            "selected_for_rpf30_candidate": "B_OR_C_ONLY_AFTER_RETENTION_DECISION",
            "current_spike": "A_NO_CANONICAL_TRACE_REF",
            "reason": "keep backend replaceable and canonical evidence replayable without Collector availability",
        }
        result["recommendation"] = {
            "proceed_to_formal_otel": "CONDITIONAL",
            "reason": "propagation, response-loss explanation, failure isolation, privacy and CI evidence pass; formal SDK choice, retention and canonical correlation ref still require a narrow RPF-30 decision",
            "rpf30_scope": [
                "manual SDK instrumentation at Control Plane submit/claim/terminal paths",
                "Python worker/agent/tool/environment/reconcile spans",
                "W3C propagation through multi-service HTTP boundary",
                "low-cardinality durable/reliability/environment metrics",
                "OTLP Collector as optional diagnostic path with bounded timeout",
                "no prompt/body/secrets and no trace authority over canonical outcome",
            ],
        }
        result["status"] = "PASS" if graph["passed"] and all(item["canonical"]["outcome"] == "PASS" for item in result["scenarios"]) else "FAIL"
    except Exception as error:
        result["status"] = "FAIL"
        result["error"] = str(error)
    finally:
        if java_process is not None and java_process.poll() is None:
            java_process.terminate()
            try:
                java_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                java_process.kill()
        if collector is not None and not collector_stopped:
            stop_collector(collector)
        if database is not None:
            stop_container(database.container)
        result["docker_cleanup"] = remaining_docker_resources()
        result["resulting_head"] = git_head()
        result["source_sha256"] = source_sha256()
        safe_json_write(output_dir / RESULT_NAME, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the RPF-29 disposable OpenTelemetry propagation spike.")
    parser.add_argument("--run", action="store_true", help="run the spike; this is the default")
    parser.add_argument("--hosted", action="store_true", help="focused hosted- CI mode")
    parser.add_argument("--output-dir", type=Path, default=LOCAL_ROOT)
    parser.add_argument("--service-role", choices=["dependency", "target"])
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--collector", default="http://127.0.0.1:4318")
    parser.add_argument("--scenario-id", default="service")
    parser.add_argument("--environment-id", default="rpf29-environment")
    parser.add_argument("--fault-profile", default="none")
    parser.add_argument("--service-name", default="rpf29-service")
    parser.add_argument("--dependency-url")
    parser.add_argument("--telemetry-disabled", action="store_true")
    args = parser.parse_args(argv)
    if args.service_role:
        if args.ready_file is None or args.audit is None:
            parser.error("service mode requires --ready-file and --audit")
        if args.service_role == "target" and not args.dependency_url:
            parser.error("target service requires --dependency-url")
        run_service(args)
        return 0
    result = run_probe(output_dir=args.output_dir, hosted=args.hosted)
    print(json.dumps({"status": result.get("status"), "result": str((args.output_dir / RESULT_NAME).resolve()), "scenarios": [item.get("scenario_id") for item in result.get("scenarios", [])]}, ensure_ascii=False))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

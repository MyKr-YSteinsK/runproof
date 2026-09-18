"""Formal optional OpenTelemetry boundary for the Python runtime.

The module is intentionally small and lazy.  No endpoint means no SDK
provider, no exporter thread, and no retry loop.  When enabled, spans are
accepted by the official OpenTelemetry SDK and handed to a bounded worker
queue; exporter failures are diagnostic counters and never product outcomes.
"""

from __future__ import annotations

import logging
import os
import queue
import re
import threading
import time
from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any


LOGGER = logging.getLogger(__name__)
CONTEXT_SCHEMA = "rpf-otel-context-v1"
SERVICE_NAME = "runproof-python-runtime"
QUEUE_SIZE = 256
MAX_BATCH_SIZE = 64
EXPORT_TIMEOUT_MILLIS = 250

JOB_ID = "runproof.job.id"
ATTEMPT_ID = "runproof.attempt.id"
RUN_ID = "runproof.run.id"
ENVIRONMENT_ID = "runproof.environment.id"
OPERATION_ID = "runproof.operation.id"
AGENT_ID = "runproof.agent.id"
OUTCOME = "runproof.outcome"
FAULT_PROFILE = "runproof.fault.profile"
TELEMETRY_COMPLETENESS = "runproof.telemetry.completeness"

BAGGAGE_ALLOWLIST = frozenset({JOB_ID, ATTEMPT_ID, RUN_ID, ENVIRONMENT_ID, OPERATION_ID})
ATTRIBUTE_ALLOWLIST = frozenset({
    "service.name", "service.version", JOB_ID, ATTEMPT_ID, RUN_ID, ENVIRONMENT_ID,
    OPERATION_ID, AGENT_ID, OUTCOME, FAULT_PROFILE, TELEMETRY_COMPLETENESS,
    "runproof.job.type", "runproof.target.type", "runproof.attempt.model",
    "runproof.previous.attempt", "runproof.new.attempt", "runproof.durable.boundary",
    "runproof.response.lost", "runproof.error.type", "runproof.reconcile.status",
    "runproof.effect.count", "runproof.mutation.count", "runproof.propagation.valid",
    "runproof.context.source", "runproof.agent.outcome", "runproof.provider.invoked",
    "http.method", "http.route", "http.status_code", "db.system", "db.operation.name",
})
METRIC_LABEL_ALLOWLIST = frozenset({"job_type", "target_type", "outcome", "status", "fault_profile", "result", "service"})
SAFE_VALUE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
SAFE_ROUTE = re.compile(r"^/[A-Za-z0-9._:/{}-]{1,200}$")
SENSITIVE_KEY = re.compile(
    r"authorization|bearer|token|password|secret|api[_-]?key|prompt|reasoning|body|payload|path|cookie|credential",
    re.IGNORECASE,
)

try:  # Optional import keeps the ordinary no-endpoint path truly lightweight.
    from opentelemetry import baggage as otel_baggage
    from opentelemetry import context as otel_context
    from opentelemetry import trace as otel_trace
    from opentelemetry.context import Context
    from opentelemetry.baggage.propagation import W3CBaggagePropagator
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace import Span, SpanContext, SpanKind, Status, StatusCode
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SpanExporter, SpanProcessor
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by the no-dependency fallback
    SDK_AVAILABLE = False
    otel_baggage = otel_context = otel_trace = None  # type: ignore[assignment]
    Context = Any  # type: ignore[misc,assignment]
    Span = SpanContext = SpanKind = Status = StatusCode = TracerProvider = object  # type: ignore[misc,assignment]
    SpanExporter = SpanProcessor = object  # type: ignore[misc,assignment]


def _safe_value(value: Any) -> bool:
    return isinstance(value, str) and bool(SAFE_VALUE.fullmatch(value))


def sanitize_attributes(values: Mapping[str, Any] | None) -> dict[str, Any]:
    """Apply the formal attribute allowlist before an SDK call."""

    result: dict[str, Any] = {}
    for key, value in (values or {}).items():
        if not isinstance(key, str) or key not in ATTRIBUTE_ALLOWLIST or SENSITIVE_KEY.search(key):
            continue
        string_ok = _safe_value(value) or (key == "http.route" and isinstance(value, str) and SAFE_ROUTE.fullmatch(value))
        if isinstance(value, (str, int, float, bool)) and (not isinstance(value, str) or string_ok):
            result[key] = value
    return result


def safe_metric_labels(values: Mapping[str, Any] | None) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in (values or {}).items()
        if key in METRIC_LABEL_ALLOWLIST and _safe_value(str(value))
    }


def canonical_attributes(**values: Any) -> dict[str, Any]:
    mapping = {
        "job_id": JOB_ID,
        "attempt_id": ATTEMPT_ID,
        "run_id": RUN_ID,
        "environment_id": ENVIRONMENT_ID,
        "operation_id": OPERATION_ID,
        "agent_id": AGENT_ID,
        "outcome": OUTCOME,
        "fault_profile": FAULT_PROFILE,
    }
    return sanitize_attributes({mapping[key]: value for key, value in values.items() if key in mapping})


def _parse_baggage(header: Any) -> dict[str, str]:
    safe: dict[str, str] = {}
    if not isinstance(header, str):
        return safe
    for part in header.split(","):
        key, separator, value = part.strip().partition("=")
        if separator and key in BAGGAGE_ALLOWLIST and _safe_value(value):
            safe[key] = value
    return safe


class _BoundedBatchSpanProcessor(SpanProcessor if SDK_AVAILABLE else object):
    """A bounded asynchronous SpanProcessor with explicit drop counters."""

    def __init__(self, exporter: Any, queue_size: int = QUEUE_SIZE, max_batch_size: int = MAX_BATCH_SIZE) -> None:
        if not SDK_AVAILABLE:
            return
        self.exporter = exporter
        self.queue: queue.Queue[Any] = queue.Queue(maxsize=max(32, min(queue_size, 1024)))
        self.max_batch_size = max(1, min(max_batch_size, self.queue.maxsize))
        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self._run, name="rpf-otel-exporter", daemon=True)
        self.exported_spans = 0
        self.export_failures = 0
        self.dropped_spans = 0
        self.active_batches = 0
        self.worker.start()

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        return None

    def on_end(self, span: Any) -> None:
        if not SDK_AVAILABLE or not span.context.is_valid or not span.context.trace_flags.sampled:
            return
        try:
            self.queue.put_nowait(span)
        except queue.Full:
            self.dropped_spans += 1
            LOGGER.warning("RunProof OTel telemetry dropped because the bounded queue is full; canonical execution is unaffected")

    def shutdown(self) -> None:
        if not SDK_AVAILABLE:
            return
        self.stop_event.set()
        self.worker.join(timeout=1.0)
        try:
            self.exporter.shutdown()
        except Exception:
            self.export_failures += 1

    def force_flush(self, timeout_millis: int = 500) -> bool:
        if not SDK_AVAILABLE:
            return True
        deadline = time.monotonic() + max(1, timeout_millis) / 1000.0
        while (not self.queue.empty() or self.active_batches > 0) and time.monotonic() < deadline:
            time.sleep(0.005)
        return self.queue.empty() and self.active_batches == 0

    def _run(self) -> None:
        while not self.stop_event.is_set() or not self.queue.empty():
            try:
                first = self.queue.get(timeout=0.05)
            except queue.Empty:
                continue
            batch = [first]
            while len(batch) < self.max_batch_size:
                try:
                    batch.append(self.queue.get_nowait())
                except queue.Empty:
                    break
            self.active_batches += 1
            try:
                result = self.exporter.export(batch)
                result_name = getattr(result, "name", str(result))
                if result_name in {"SUCCESS", "SpanExportResult.SUCCESS"}:
                    self.exported_spans += len(batch)
                else:
                    self.export_failures += len(batch)
            except Exception as error:  # exporter failures stay off the product path
                self.export_failures += len(batch)
                LOGGER.warning("RunProof OTel export unavailable: %s", type(error).__name__)
            finally:
                self.active_batches -= 1
                for _ in batch:
                    self.queue.task_done()


class _NoopScope(AbstractContextManager["_NoopScope"]):
    valid = False

    def __enter__(self) -> "_NoopScope":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def error(self, *_: Any) -> None:
        return None

    def event(self, *_: Any) -> None:
        return None

    def attribute(self, *_: Any) -> None:
        return None

    def context_document(self) -> dict[str, Any]:
        return {}


@dataclass
class SpanScope(AbstractContextManager["SpanScope"]):
    runtime: "Observability"
    span: Any
    token: Any
    valid: bool = True

    def __enter__(self) -> "SpanScope":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, _traceback: Any) -> None:
        if exc_value is not None:
            self.error(exc_value, type(exc_value).__name__)
        try:
            otel_context.detach(self.token)
        finally:
            self.span.end()

    def error(self, error: BaseException, error_type: str = "runtime_error") -> None:
        if not self.valid:
            return
        self.span.record_exception(error)
        self.span.set_status(Status(StatusCode.ERROR, error_type if _safe_value(error_type) else "runtime_error"))

    def event(self, name: str) -> None:
        if self.valid and _safe_value(name):
            self.span.add_event(name)

    def attribute(self, key: str, value: Any) -> None:
        if not self.valid:
            return
        safe = sanitize_attributes({key: value})
        if key in safe:
            self.span.set_attribute(key, safe[key])

    def context_document(self) -> dict[str, Any]:
        if not self.valid:
            return {}
        carrier: dict[str, str] = {}
        TRACE_PROPAGATOR.inject(carrier, context=otel_trace.set_span_in_context(self.span))
        baggage: dict[str, str] = {}
        current = otel_baggage.get_all(otel_context.get_current())
        for key in BAGGAGE_ALLOWLIST:
            value = current.get(key)
            if _safe_value(value):
                baggage[key] = value
        return {"schema_version": CONTEXT_SCHEMA, "traceparent": carrier.get("traceparent", ""), "baggage": baggage}


if SDK_AVAILABLE:
    TRACE_PROPAGATOR: Any = TraceContextTextMapPropagator()
    BAGGAGE_PROPAGATOR: Any = W3CBaggagePropagator()
else:  # pragma: no cover
    TRACE_PROPAGATOR = BAGGAGE_PROPAGATOR = None


class Observability:
    """One process-local OTel runtime; create one per worker/service process."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        endpoint: str | None = None,
        service_name: str = SERVICE_NAME,
        queue_size: int | None = None,
    ) -> None:
        configured_enabled = _env_bool("RPF_OTEL_ENABLED", False) if enabled is None else bool(enabled)
        configured_endpoint = endpoint or os.environ.get("RPF_OTEL_ENDPOINT") or os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        self.service_name = service_name
        configured_queue_size = int(os.environ.get("RPF_OTEL_QUEUE_SIZE", str(QUEUE_SIZE))) if queue_size is None else int(queue_size)
        self.queue_size = max(32, min(configured_queue_size, 1024))
        self.enabled = False
        self.status = "DISABLED"
        self._provider: Any = None
        self._meter_provider: Any = None
        self._processor: Any = None
        self._tracer: Any = None
        self._meter: Any = None
        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}
        self._initialize(configured_enabled, configured_endpoint)

    def _initialize(self, configured_enabled: bool, endpoint: str | None) -> None:
        if not configured_enabled or _env_bool("OTEL_SDK_DISABLED", False):
            self.status = "DISABLED"
            return
        if not endpoint:
            self.status = "DISABLED_ENDPOINT_MISSING"
            return
        if not SDK_AVAILABLE:
            self.status = "SDK_UNAVAILABLE"
            return
        try:
            resource = Resource.create({"service.name": self.service_name, "service.version": "rpf-30"})
            self._provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=_trace_endpoint(endpoint), timeout=EXPORT_TIMEOUT_MILLIS / 1000.0)
            self._processor = _BoundedBatchSpanProcessor(exporter, self.queue_size, MAX_BATCH_SIZE)
            self._provider.add_span_processor(self._processor)
            self._tracer = self._provider.get_tracer("com.runproof.runtime", "rpf-30")
            self._meter_provider = self._build_meter_provider(resource, endpoint)
            self._meter = self._meter_provider.get_meter("com.runproof.runtime", "rpf-30") if self._meter_provider else None
            self.enabled = True
            self.status = "ENABLED"
        except Exception as error:
            self.status = "DISABLED_CONFIGURATION_ERROR"
            LOGGER.warning("RunProof OpenTelemetry disabled because configuration failed: %s", type(error).__name__)

    @staticmethod
    def _build_meter_provider(resource: Any, endpoint: str) -> Any:
        try:
            metric_exporter = OTLPMetricExporter(endpoint=_metric_endpoint(endpoint), timeout=EXPORT_TIMEOUT_MILLIS / 1000.0)
            reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=5000, export_timeout_millis=EXPORT_TIMEOUT_MILLIS)
            return MeterProvider(resource=resource, metric_readers=[reader])
        except Exception as error:
            LOGGER.warning("RunProof OTel metrics disabled: %s", type(error).__name__)
            return MeterProvider(resource=resource)

    def span(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        *,
        parent: Any = None,
        links: Iterable[Any] = (),
        kind: Any = None,
    ) -> SpanScope | _NoopScope:
        if not self.enabled or self._tracer is None:
            return _NoopScope()
        parent_context = self.context_from_document(parent) if isinstance(parent, Mapping) else parent
        parent_context = parent_context if parent_context is not None else otel_context.get_current()
        safe = sanitize_attributes(attributes)
        baggaged_parent = _with_baggage(parent_context, safe)
        span = self._tracer.start_span(
            name,
            context=baggaged_parent,
            kind=kind or SpanKind.INTERNAL,
            attributes=safe,
            links=list(links),
        )
        token = otel_context.attach(otel_trace.set_span_in_context(span, baggaged_parent))
        return SpanScope(self, span, token)

    def inject(self, carrier: dict[str, str], context: Any = None) -> None:
        if not self.enabled or _env_bool("RPF_OTEL_SUPPRESS_PROPAGATION", False):
            return
        current = context if context is not None else otel_context.get_current()
        TRACE_PROPAGATOR.inject(carrier, context=current)
        safe_context = _with_baggage(current, {})
        BAGGAGE_PROPAGATOR.inject(carrier, context=safe_context)

    def extract(self, carrier: Mapping[str, str] | None) -> Any:
        if not self.enabled:
            return otel_context.get_current()
        carrier = carrier or {}
        extracted = TRACE_PROPAGATOR.extract(carrier=carrier, context=otel_context.get_current())
        return _with_baggage(extracted, _parse_baggage(carrier.get("baggage")))

    def context_from_document(self, document: Mapping[str, Any] | None) -> Any:
        if not self.enabled or not isinstance(document, Mapping):
            return otel_context.get_current()
        traceparent = document.get("traceparent")
        baggage = document.get("baggage")
        carrier: dict[str, str] = {}
        if isinstance(traceparent, str):
            carrier["traceparent"] = traceparent
        if isinstance(baggage, Mapping):
            carrier["baggage"] = ",".join(f"{key}={value}" for key, value in baggage.items() if key in BAGGAGE_ALLOWLIST and _safe_value(value))
        return self.extract(carrier)

    def span_link(self, document: Mapping[str, Any] | None) -> Any | None:
        if not self.enabled:
            return None
        context = self.context_from_document(document)
        span = otel_trace.get_current_span(context)
        span_context = span.get_span_context()
        return otel_trace.Link(span_context) if span_context.is_valid else None

    def counter(self, name: str, labels: Mapping[str, Any] | None = None, value: int = 1) -> None:
        if not self.enabled or self._meter is None or not _safe_value(name):
            return
        instrument = self._counters.get(name)
        if instrument is None:
            instrument = self._meter.create_counter(name)
            self._counters[name] = instrument
        instrument.add(value, safe_metric_labels(labels))

    def duration(self, name: str, milliseconds: float, labels: Mapping[str, Any] | None = None) -> None:
        if not self.enabled or self._meter is None or not _safe_value(name):
            return
        instrument = self._histograms.get(name)
        if instrument is None:
            instrument = self._meter.create_histogram(name)
            self._histograms[name] = instrument
        instrument.record(max(0.0, float(milliseconds)), safe_metric_labels(labels))

    def diagnostics(self) -> dict[str, Any]:
        processor = self._processor
        return {
            "status": self.status,
            "enabled": self.enabled,
            "exported_spans": int(getattr(processor, "exported_spans", 0)),
            "export_failures": int(getattr(processor, "export_failures", 0)),
            "dropped_spans": int(getattr(processor, "dropped_spans", 0)),
            "queue_size": self.queue_size,
            "bounded": True,
            "authority": "DIAGNOSTIC_ONLY",
        }

    def correlation(self) -> dict[str, str]:
        if not self.enabled:
            return {}
        span = otel_trace.get_current_span()
        context = span.get_span_context()
        values = {"trace_id": context.trace_id, "span_id": context.span_id} if context.is_valid else {}
        for key in BAGGAGE_ALLOWLIST:
            value = otel_baggage.get_baggage(key)
            if _safe_value(value):
                values[key] = value
        return values

    def flush(self, timeout_millis: int = 500) -> bool:
        if not self.enabled:
            return True
        processor = self._processor
        return bool(processor.force_flush(timeout_millis)) if processor else True

    def shutdown(self, timeout_millis: int = 1000) -> None:
        if not self.enabled:
            return
        try:
            self.flush(timeout_millis)
        finally:
            if self._provider:
                self._provider.shutdown()
            if self._meter_provider:
                self._meter_provider.shutdown()
            self.enabled = False
            self.status = "CLOSED"


def _with_baggage(context: Any, values: Mapping[str, Any]) -> Any:
    if not SDK_AVAILABLE:
        return context
    current = context or otel_context.get_current()
    for key, value in values.items():
        if key in BAGGAGE_ALLOWLIST and _safe_value(value):
            current = otel_baggage.set_baggage(key, value, context=current)
    return current


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, "true" if default else "false").strip().lower() in {"1", "true", "yes", "on"}


def _trace_endpoint(endpoint: str) -> str:
    value = endpoint.rstrip("/")
    return value if value.endswith("/v1/traces") else value + "/v1/traces"


def _metric_endpoint(endpoint: str) -> str:
    value = endpoint.rstrip("/")
    return value if value.endswith("/v1/metrics") else value + "/v1/metrics"


_runtime: Observability | None = None
_runtime_lock = threading.Lock()


def get_observability() -> Observability:
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                _runtime = Observability()
    return _runtime


def reset_observability() -> None:
    global _runtime
    with _runtime_lock:
        if _runtime is not None:
            _runtime.shutdown()
        _runtime = None


__all__ = [
    "ATTEMPT_ID", "BAGGAGE_ALLOWLIST", "CONTEXT_SCHEMA", "ENVIRONMENT_ID", "FAULT_PROFILE",
    "JOB_ID", "OPERATION_ID", "Observability", "OUTCOME", "RUN_ID", "SpanScope",
    "TELEMETRY_COMPLETENESS", "canonical_attributes", "get_observability", "reset_observability",
    "safe_metric_labels", "sanitize_attributes",
]

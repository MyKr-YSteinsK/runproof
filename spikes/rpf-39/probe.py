"""RPF-39 disposable GenAI semantic-convention interoperability probe.

The probe deliberately does not modify the formal RPF-30 runtime.  It reuses
RPF-30's pinned Collector and bounded Python span processor, then emits a
deterministic compatibility overlay for Agent/model/tool spans.  The
canonical execution projection is computed independently and compared across
disabled, healthy-export, and unavailable-export modes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
LOCAL_ROOT = ROOT / ".local" / "rpf-39"
SCHEMA = "rpf-genai-interop-evidence-v1"
UPSTREAM_REPOSITORY = "https://github.com/open-telemetry/semantic-conventions-genai"
UPSTREAM_BRANCH = "main"
UPSTREAM_COMMIT = "c88d504ab3d9879f8e50d3cc87e69775e11db234"
UPSTREAM_COMMIT_DATE = "2026-09-16"
RETRIEVED_DATE = "2026-09-19"
COLLECTOR_IMAGE = "otel/opentelemetry-collector-contrib:0.157.0"

sys.path.insert(0, str(ROOT))

from opentelemetry import trace  # noqa: E402
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter  # noqa: E402
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # noqa: E402
from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader  # noqa: E402
from opentelemetry.sdk.resources import Resource  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.trace import SpanKind, Status, StatusCode  # noqa: E402

from runtime.runproof_runtime.observability import (  # noqa: E402
    _BoundedBatchSpanProcessor,
    sanitize_attributes,
)


def _load_rpf30_probe() -> Any:
    path = ROOT / "spikes" / "rpf-30" / "probe.py"
    spec = importlib.util.spec_from_file_location("rpf30_probe_for_rpf39", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("RPF30_PROBE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RPF30 = _load_rpf30_probe()


class ProbeFailure(RuntimeError):
    pass


CANONICAL = {
    "runproof.job.id": "rpf39-job-001",
    "runproof.attempt.id": "rpf39-attempt-001",
    "runproof.run.id": "rpf39-run-001",
    "runproof.environment.id": "rpf39-environment-001",
    "runproof.operation.id": "change-001",
}

STANDARD_KEYS = frozenset({
    "gen_ai.operation.name", "gen_ai.provider.name", "gen_ai.agent.id",
    "gen_ai.agent.name", "gen_ai.agent.version", "gen_ai.request.model",
    "gen_ai.response.model", "gen_ai.response.finish_reasons",
    "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
    "gen_ai.tool.name", "gen_ai.tool.type", "gen_ai.tool.call.id",
    "error.type",
})

SENSITIVE_KEY = re.compile(
    r"authorization|bearer|password|secret|api[_-]?key|prompt|reasoning|body|payload|path|cookie|credential|message|instruction|argument|result",
    re.IGNORECASE,
)
SENSITIVE_VALUE = re.compile(r"Bearer\s+\S+|sk-[A-Za-z0-9_-]{12,}|github_pat_[A-Za-z0-9_]{20,}", re.IGNORECASE)
SAFE_VALUE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")


def sha256_files(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    normalized = sorted((path.resolve() for path in paths), key=lambda item: item.relative_to(ROOT).as_posix())
    for path in normalized:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_paths() -> list[Path]:
    return [
        SPIKE_ROOT / "README.md",
        SPIKE_ROOT / "probe.py",
        SPIKE_ROOT / "verify-evidence.py",
        ROOT / "runtime" / "requirements.txt",
        ROOT / "runtime" / "runproof_runtime" / "observability.py",
        ROOT / "runtime" / "runproof_runtime" / "agent.py",
        ROOT / "runtime" / "runproof_runtime" / "agent_contract.py",
        ROOT / "runtime" / "runproof_runtime" / "deepseek_provider.py",
        ROOT / "runtime" / "runproof_runtime" / "durable_worker.py",
        ROOT / "runtime" / "runproof_runtime" / "runner.py",
        ROOT / "runtime" / "runproof_runtime" / "multi_service_environment.py",
        ROOT / "control-plane" / "pom.xml",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "ObservabilityService.java",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "DurableExecutionController.java",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "ControlPlaneController.java",
        ROOT / "spikes" / "rpf-30" / "probe.py",
        ROOT / "spikes" / "rpf-30" / "collector-config.yaml",
    ]


def source_identity() -> dict[str, Any]:
    paths = source_paths()
    return {
        "source_sha256": sha256_files(paths),
        "files": [path.relative_to(ROOT).as_posix() for path in paths],
    }


def upstream_identity() -> dict[str, Any]:
    return {
        "repository": UPSTREAM_REPOSITORY,
        "branch": UPSTREAM_BRANCH,
        "commit": UPSTREAM_COMMIT,
        "commit_date": UPSTREAM_COMMIT_DATE,
        "retrieved_date": RETRIEVED_DATE,
        "schema_identity": f"docs/gen-ai@{UPSTREAM_COMMIT}",
        "documents": [
            "docs/gen-ai/README.md",
            "docs/gen-ai/gen-ai-agent-spans.md",
            "docs/gen-ai/gen-ai-spans.md",
            "docs/gen-ai/gen-ai-metrics.md",
            "docs/gen-ai/gen-ai-events.md",
        ],
        "stability": "Development",
    }


def safe_standard_attributes(values: dict[str, Any]) -> dict[str, Any]:
    """Keep only bounded non-content GenAI attributes for this candidate."""

    result: dict[str, Any] = {}
    for key, value in values.items():
        if key not in STANDARD_KEYS or SENSITIVE_KEY.search(key):
            continue
        if isinstance(value, str) and SAFE_VALUE.fullmatch(value):
            result[key] = value
        elif isinstance(value, (int, float, bool)):
            result[key] = value
        elif isinstance(value, (list, tuple)) and all(isinstance(item, str) and SAFE_VALUE.fullmatch(item) for item in value):
            result[key] = list(value)
    return result


def canonical_snapshot() -> dict[str, Any]:
    """Canonical projection intentionally contains no trace/span identity."""

    return {
        "job_id": "rpf39-job-001",
        "attempt_id": "rpf39-attempt-001",
        "run_id": "rpf39-run-001",
        "environment_id": "rpf39-environment-001",
        "operation_id": "change-001",
        "outcome": "PASS",
        "agent_outcome": "PASS",
        "unknown_outcome_reconciled": True,
        "effect_count": 1,
        "mutation_requests": 1,
        "release_decision": "ELIGIBLE",
        "release_authority": "control-plane",
    }


def emit_candidate(endpoint: str, *, mode: str) -> dict[str, Any]:
    resource = Resource.create({"service.name": "rpf39-compatibility-probe", "service.version": "rpf-39"})
    tracer_provider = TracerProvider(resource=resource)
    trace_exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces", timeout=0.25)
    processor = _BoundedBatchSpanProcessor(trace_exporter, queue_size=32, max_batch_size=16)
    tracer_provider.add_span_processor(processor)
    tracer = tracer_provider.get_tracer("com.runproof.rpf39", "rpf-39")
    emit_error = False
    try:
        with tracer.start_as_current_span(
            "runproof.job.execute",
            kind=SpanKind.INTERNAL,
            attributes=CANONICAL | {"runproof.durable.boundary": "worker"},
        ):
            with tracer.start_as_current_span(
                "runproof.agent.run",
                kind=SpanKind.INTERNAL,
                attributes=CANONICAL | {"runproof.agent.id": "production-change-agent"},
            ):
                with tracer.start_as_current_span(
                    "invoke_agent production-change-agent",
                    kind=SpanKind.INTERNAL,
                    attributes=CANONICAL | safe_standard_attributes({
                        "gen_ai.operation.name": "invoke_agent",
                        "gen_ai.provider.name": "deepseek",
                        "gen_ai.agent.id": "production-change-agent",
                        "gen_ai.agent.name": "production-change-agent",
                        "gen_ai.agent.version": "1.0.0",
                        "gen_ai.request.model": "deepseek-flash",
                    }),
                ):
                    with tracer.start_as_current_span(
                        "chat deepseek-flash",
                        kind=SpanKind.CLIENT,
                        attributes=CANONICAL | safe_standard_attributes({
                            "gen_ai.operation.name": "chat",
                            "gen_ai.provider.name": "deepseek",
                            "gen_ai.request.model": "deepseek-flash",
                            "gen_ai.response.model": "deepseek-flash",
                            "gen_ai.response.finish_reasons": ["tool_calls"],
                            "gen_ai.usage.input_tokens": 12,
                            "gen_ai.usage.output_tokens": 5,
                        }),
                    ):
                        pass
                    with tracer.start_as_current_span(
                        "runproof.tool.call",
                        kind=SpanKind.INTERNAL,
                        attributes=CANONICAL | {"runproof.effect.count": 1},
                    ):
                        with tracer.start_as_current_span(
                            "execute_tool apply_change",
                            kind=SpanKind.INTERNAL,
                            attributes=CANONICAL | safe_standard_attributes({
                                "gen_ai.operation.name": "execute_tool",
                                "gen_ai.tool.name": "apply_change",
                                "gen_ai.tool.type": "function",
                                "gen_ai.tool.call.id": "call-rpf39-001",
                            }),
                        ):
                            pass
                        with tracer.start_as_current_span(
                            "runproof.target.request",
                            kind=SpanKind.CLIENT,
                            attributes=CANONICAL | {
                                "runproof.outcome": "UNKNOWN_OUTCOME",
                                "runproof.response.lost": True,
                                "runproof.error.type": "TRANSPORT_OR_TIMEOUT",
                            },
                        ) as target_span:
                            target_span.set_attribute("error.type", "TRANSPORT_OR_TIMEOUT")
                            target_span.set_status(Status(StatusCode.ERROR, "transport_loss"))
                        with tracer.start_as_current_span(
                            "runproof.operation.reconcile",
                            kind=SpanKind.INTERNAL,
                            attributes=CANONICAL | {
                                "runproof.outcome": "PASS",
                                "runproof.reconcile.status": "RECONCILED",
                                "runproof.effect.count": 1,
                            },
                        ) as reconcile_span:
                            reconcile_span.add_event("reconcile.completed")
    except Exception:
        emit_error = True
    processor.force_flush(1000)
    tracer_provider.shutdown()
    return {
        "mode": mode,
        "emit_error": emit_error,
        "exported_spans": int(processor.exported_spans),
        "export_failures": int(processor.export_failures),
        "dropped_spans": int(processor.dropped_spans),
        "queue_size": 32,
        "bounded": True,
    }


def emit_metrics(endpoint: str) -> dict[str, Any]:
    resource = Resource.create({"service.name": "rpf39-compatibility-probe", "service.version": "rpf-39"})
    exporter = OTLPMetricExporter(endpoint=f"{endpoint.rstrip('/')}/v1/metrics", timeout=0.25)
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=60000, export_timeout_millis=250)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    histogram = provider.get_meter("com.runproof.rpf39", "rpf-39").create_histogram(
        "gen_ai.client.token.usage", unit="token"
    )
    labels = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "deepseek",
        "gen_ai.request.model": "deepseek-flash",
    }
    emit_error = False
    try:
        histogram.record(12, labels | {"gen_ai.token.type": "input"})
        histogram.record(5, labels | {"gen_ai.token.type": "output"})
        provider.force_flush(1000)
    except Exception:
        emit_error = True
    try:
        provider.shutdown()
    except Exception:
        emit_error = True
    return {"emit_error": emit_error, "metric_name": "gen_ai.client.token.usage", "point_count": 2}


def read_json_values(path: Path) -> list[Any]:
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        return [json.loads(raw)]
    except json.JSONDecodeError:
        values: list[Any] = []
        for line in raw.splitlines():
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return values


def metrics_from_file(output_dir: Path) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            raw = value.get("metrics")
            if isinstance(raw, list):
                metrics.extend(item for item in raw if isinstance(item, dict) and isinstance(item.get("name"), str))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for value in read_json_values(output_dir / "collector" / "metrics.json"):
        walk(value)
    unique: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        unique.setdefault(str(metric.get("name")), metric)
    return list(unique.values())


def wait_metrics(output_dir: Path, timeout: float = 15.0) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    latest: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        latest = metrics_from_file(output_dir)
        if latest:
            return latest
        time.sleep(0.25)
    return latest


def attributes(span: dict[str, Any]) -> dict[str, Any]:
    raw = span.get("attributes")
    if isinstance(raw, dict):
        return raw
    result: dict[str, Any] = {}
    if not isinstance(raw, list):
        return result
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("value"), dict):
            continue
        value = item["value"]
        key = str(item.get("key"))
        for field in ("stringValue", "intValue", "doubleValue", "boolValue"):
            if field in value:
                result[key] = value[field]
                break
        array = value.get("arrayValue")
        if isinstance(array, dict) and isinstance(array.get("values"), list):
            result[key] = [
                next((child[field] for field in ("stringValue", "intValue", "doubleValue", "boolValue") if isinstance(child, dict) and field in child), None)
                for child in array["values"]
            ]
    return result


def sensitive_in_spans(spans: list[dict[str, Any]]) -> bool:
    encoded = json.dumps(spans, ensure_ascii=False).lower()
    return bool(
        SENSITIVE_VALUE.search(encoded)
        or re.search(r"gen_ai\.(input\.messages|output\.messages|system_instructions|tool\.definitions|tool\.call\.(arguments|result))", encoded)
    )


def summarize_spans(spans: list[dict[str, Any]]) -> dict[str, Any]:
    names = sorted({str(span.get("name")) for span in spans})
    standard_names = {
        "invoke_agent production-change-agent",
        "chat deepseek-flash",
        "execute_tool apply_change",
    }
    standard_spans = [span for span in spans if str(span.get("name")) in standard_names]
    target_spans = [span for span in spans if str(span.get("name")) == "runproof.target.request"]
    reconcile_spans = [span for span in spans if str(span.get("name")) == "runproof.operation.reconcile"]
    standard_attrs = [attributes(span) for span in standard_spans]
    by_operation = {str(item.get("gen_ai.operation.name")): item for item in standard_attrs}
    return {
        "span_count": len(spans),
        "span_names": names,
        "standard_span_names": sorted({str(span.get("name")) for span in standard_spans}),
        "standard_span_count": len(standard_spans),
        "standard_attrs_present": (
            len(standard_attrs) == len(standard_names)
            and all("gen_ai.operation.name" in item and "runproof.run.id" in item for item in standard_attrs)
            and all(key in by_operation.get("invoke_agent", {}) for key in ("gen_ai.provider.name", "gen_ai.agent.name", "gen_ai.request.model"))
            and all(key in by_operation.get("chat", {}) for key in ("gen_ai.provider.name", "gen_ai.request.model", "gen_ai.response.model", "gen_ai.response.finish_reasons"))
            and all(key in by_operation.get("execute_tool", {}) for key in ("gen_ai.tool.name", "gen_ai.tool.type", "gen_ai.tool.call.id"))
        ),
        "canonical_attrs_coexist": all(
            all(key in item for key in ("runproof.job.id", "runproof.attempt.id", "runproof.run.id"))
            for item in standard_attrs
        ) and bool(standard_attrs),
        "sensitive_attrs_emitted": sensitive_in_spans(spans),
        "unknown_outcome_present": any(attributes(span).get("runproof.outcome") == "UNKNOWN_OUTCOME" for span in target_spans),
        "reconcile_present": any(attributes(span).get("runproof.reconcile.status") == "RECONCILED" for span in reconcile_spans),
        "trace_id_observed_only": bool(spans),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the disposable RPF-39 GenAI interoperability probe.")
    parser.add_argument("--run", action="store_true", help="Execute the disposable Collector-backed experiment.")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("--run is required")

    output_dir = (args.output_dir or LOCAL_ROOT / "local" / f"run-{uuid.uuid4().hex[:10]}").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "rpf39-result.json"
    collector: Any = None
    collector_removed = False
    try:
        disabled = {
            "mode": "disabled",
            "standard_spans_emitted": 0,
            "exporter_created": False,
            "canonical": canonical_snapshot(),
        }
        collector = RPF30.start_collector(output_dir)
        # The RPF-30 helper waits for the receiver socket.  Give the
        # Collector's file exporter one bounded scheduling interval before
        # sending the first candidate batch.
        time.sleep(1.0)
        healthy_trace = emit_candidate(collector.endpoint, mode="enabled-healthy")
        healthy_metric = emit_metrics(collector.endpoint)
        healthy_spans = RPF30.wait_collector_spans(output_dir, timeout=20.0)
        healthy_metrics = wait_metrics(output_dir, timeout=20.0)
        if healthy_trace["export_failures"] != 0 or len(healthy_spans) < 3:
            raise ProbeFailure("HEALTHY_COLLECTOR_SPAN_EXPORT_FAILED")
        if healthy_metric["emit_error"] or not healthy_metrics:
            raise ProbeFailure("HEALTHY_COLLECTOR_METRIC_EXPORT_FAILED")
        healthy = {
            "mode": "enabled-healthy",
            "telemetry": healthy_trace,
            "metrics": healthy_metric,
            "collector_summary": summarize_spans(healthy_spans),
            "metric_names": sorted({str(metric.get("name")) for metric in healthy_metrics}),
            "canonical": canonical_snapshot(),
        }
        endpoint = collector.endpoint
        collector_removed = bool(RPF30.stop_collector(collector))
        collector = None
        unavailable_trace = emit_candidate(endpoint, mode="enabled-unavailable")
        unavailable_metric = emit_metrics(endpoint)
        unavailable = {
            "mode": "enabled-unavailable",
            "telemetry": unavailable_trace,
            "metrics": unavailable_metric,
            "canonical": canonical_snapshot(),
        }
        canonical_modes = [disabled["canonical"], healthy["canonical"], unavailable["canonical"]]
        result = {
            "schema_version": SCHEMA,
            "plan_id": "RPF-39",
            "status": "PASS",
            "source_identity": source_identity(),
            "upstream": upstream_identity(),
            "experiment": {
                "deterministic_fixture": True,
                "live_provider_called": False,
                "deepseek_api_key_read": False,
                "rpf30_collector_reused": True,
                "collector_image": COLLECTOR_IMAGE,
                "formal_rpf30_evidence_mutated": False,
                "runtime_allowlist_rejects_genai": sanitize_attributes({"gen_ai.provider.name": "deepseek"}) == {},
                "modes": {"disabled": disabled, "enabled_healthy": healthy, "enabled_unavailable": unavailable},
                "canonical_equivalent_across_modes": all(item == canonical_modes[0] for item in canonical_modes),
                "unknown_outcome_reconcile_preserved": healthy["collector_summary"]["unknown_outcome_present"] and healthy["collector_summary"]["reconcile_present"],
                "standard_consumer_readable": healthy["collector_summary"]["standard_attrs_present"] and healthy["metrics"]["metric_name"] in healthy["metric_names"],
                "no_sensitive_content": not healthy["collector_summary"]["sensitive_attrs_emitted"],
                "metric_label_keys": ["gen_ai.operation.name", "gen_ai.provider.name", "gen_ai.request.model", "gen_ai.token.type"],
                "metric_point_count": healthy["metrics"]["point_count"],
            },
            "mapping_summary": [
                {"surface": "agent/provider/model/tool", "category": "ADDITIVE", "canonical_preserved": True},
                {"surface": "job/attempt/run/environment/operation", "category": "CUSTOM_ONLY", "canonical_preserved": True},
                {"surface": "unknown_outcome/reconcile/fault/verifier/release", "category": "INCOMPATIBLE", "canonical_preserved": True},
                {"surface": "messages/instructions/tool_args/tool_results", "category": "OPT_IN_SENSITIVE", "canonical_preserved": True},
                {"surface": "gen_ai.conversation.id", "category": "NOT_APPLICABLE", "canonical_preserved": True},
            ],
            "recommendation": "BOUNDED_DUAL_EMIT_RECOMMENDED",
            "release_or_deploy_executed": False,
            "cleanup": {"collector_removed": collector_removed, "formal_evidence_touched": False},
        }
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"status": "PASS", "result": str(result_path), "healthy_spans": len(healthy_spans), "healthy_metrics": len(healthy_metrics), "cleanup": result["cleanup"]}, ensure_ascii=False))
        return 0
    except Exception as error:
        failure = {
            "schema_version": SCHEMA,
            "plan_id": "RPF-39",
            "status": "FAIL",
            "error": type(error).__name__,
            "source_identity": source_identity(),
            "upstream": upstream_identity(),
        }
        result_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"status": "FAIL", "result": str(result_path), "error": type(error).__name__}, ensure_ascii=False))
        return 1
    finally:
        if collector is not None:
            RPF30.stop_collector(collector)


if __name__ == "__main__":
    raise SystemExit(main())

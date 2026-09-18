"""Offline verifier for the formal RPF-30 OTel probe result."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
COLLECTOR_IMAGE = "otel/opentelemetry-collector-contrib:0.157.0"
FORMAL_SCHEMA = "rpf-otel-formal-evidence-v1"
ALLOWED_SPANS = {
    "runproof.http.request", "runproof.canonical.read", "runproof.decision.read", "runproof.decision.write",
    "runproof.control-plane.http",
    "runproof.evidence.ingest", "runproof.job.submit", "runproof.job.read", "runproof.job.claim",
    "runproof.job.execute", "runproof.job.terminalize", "runproof.job.completion", "runproof.worker.poll",
    "runproof.agent.run", "runproof.tool.call", "runproof.environment.provision", "runproof.environment.readiness",
    "runproof.environment.cleanup", "runproof.fault.activate", "runproof.target.request", "runproof.target.commit",
    "runproof.dependency.request", "runproof.operation.unknown", "runproof.operation.reconcile", "runproof.verifier.evaluate",
    "runproof.overhead.sample",
}
ALLOWED_ATTRIBUTES = {
    "service.name", "service.version", "runproof.job.id", "runproof.attempt.id", "runproof.run.id",
    "runproof.environment.id", "runproof.operation.id", "runproof.agent.id", "runproof.outcome",
    "runproof.fault.profile", "runproof.telemetry.completeness", "runproof.job.type", "runproof.target.type",
    "runproof.attempt.model", "runproof.previous.attempt", "runproof.new.attempt", "runproof.durable.boundary",
    "runproof.response.lost", "runproof.error.type", "runproof.reconcile.status", "runproof.effect.count",
    "runproof.mutation.count", "runproof.propagation.valid", "runproof.context.source", "runproof.agent.outcome",
    "runproof.provider.invoked", "http.method", "http.route", "http.status_code", "db.system", "db.operation.name",
}
FORBIDDEN_KEY = re.compile(r"authorization|bearer|token|password|secret|api[_-]?key|prompt|reasoning|body|payload|cookie|credential|path", re.IGNORECASE)
FORBIDDEN_VALUE = re.compile(r"Bearer\s+\S+|sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}")
SAFE_DYNAMIC_VALUE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")


class VerificationFailure(AssertionError):
    pass


def assert_true(condition: Any, message: str) -> None:
    if not condition:
        raise VerificationFailure(message)


def source_paths() -> list[Path]:
    paths = [
        SPIKE_ROOT / "probe.py",
        SPIKE_ROOT / "verify-evidence.py",
        SPIKE_ROOT / "collector-config.yaml",
        ROOT / "runtime" / "requirements.txt",
        ROOT / "control-plane" / "pom.xml",
        ROOT / "control-plane" / "src" / "main" / "resources" / "application.properties",
    ]
    paths.extend(sorted((ROOT / "runtime" / "runproof_runtime").glob("*.py"), key=str))
    paths.extend(sorted((ROOT / "control-plane" / "src" / "main" / "java").rglob("*.java"), key=str))
    return paths


def source_hash(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted((item.resolve() for item in paths), key=lambda item: item.relative_to(ROOT).as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def walk_spans(value: Any, service_name: str | None = None) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    if isinstance(value, dict):
        service = service_name
        resource = value.get("resource")
        if isinstance(resource, dict) and isinstance(resource.get("attributes"), list):
            for item in resource["attributes"]:
                if isinstance(item, dict) and item.get("key") == "service.name" and isinstance(item.get("value"), dict):
                    service = item["value"].get("stringValue") or service
        if isinstance(value.get("spans"), list):
            for span in value["spans"]:
                if isinstance(span, dict):
                    item = dict(span)
                    item.setdefault("service_name", service)
                    spans.append(item)
        for child in value.values():
            if child is not value:
                spans.extend(walk_spans(child, service))
    elif isinstance(value, list):
        for child in value:
            spans.extend(walk_spans(child, service_name))
    return spans


def read_spans(result_path: Path) -> list[dict[str, Any]]:
    path = result_path.parent / "collector" / "traces.json"
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        return walk_spans(json.loads(raw))
    except json.JSONDecodeError:
        spans: list[dict[str, Any]] = []
        for line in raw.splitlines():
            try:
                spans.extend(walk_spans(json.loads(line)))
            except json.JSONDecodeError:
                continue
        return spans


def attributes(span: dict[str, Any]) -> dict[str, Any]:
    raw = span.get("attributes")
    if isinstance(raw, dict):
        return raw
    result: dict[str, Any] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("value"), dict):
                continue
            for field in ("stringValue", "intValue", "doubleValue", "boolValue"):
                if field in item["value"]:
                    result[str(item.get("key"))] = item["value"][field]
                    break
    return result


def verify_mode(name: str, mode: dict[str, Any]) -> None:
    assert_true(mode.get("mode") == name, f"{name}: mode identity")
    assert_true(mode.get("job", {}).get("state") == "COMPLETED", f"{name}: canonical job not completed")
    assert_true(mode.get("job", {}).get("terminal_evidence") is True, f"{name}: terminal evidence missing")
    canonical = mode.get("canonical", {})
    response = canonical.get("response_lost", {})
    assert_true(canonical.get("run_count", 0) >= 1, f"{name}: no Run Evidence")
    assert_true(response.get("outcome") == "PASS", f"{name}: response-lost outcome changed")
    assert_true(response.get("verification_passed") is True, f"{name}: response-lost verification failed")
    assert_true(response.get("effect_count") == 1, f"{name}: effect count is not one")
    assert_true(response.get("mutation_requests") == 1, f"{name}: mutation request count changed")
    assert_true(response.get("blind_retry_attempts") == 0, f"{name}: blind retry detected")
    assert_true(response.get("fault_reconciled") is True, f"{name}: reconcile missing")
    assert_true(response.get("cleanup_state") == "CLEANED", f"{name}: cleanup missing")
    assert_true(mode.get("sensitive_credentials_in_worker_result") is False, f"{name}: worker result contains credential")
    telemetry = mode.get("telemetry", {})
    if name == "disabled":
        assert_true(telemetry.get("status") == "DISABLED", "disabled: SDK/exporter was initialized")
        assert_true(telemetry.get("enabled") is False, "disabled: telemetry is enabled")
    else:
        assert_true(telemetry.get("status") == "ENABLED", f"{name}: enabled mode did not initialize")
        assert_true(telemetry.get("bounded") is True and telemetry.get("queue_size", 0) <= 1024, f"{name}: queue is not bounded")


def verify_spans(result: dict[str, Any], spans: list[dict[str, Any]]) -> None:
    assert_true(spans, "healthy Collector received no spans")
    assert_true(result.get("collector", {}).get("image") == COLLECTOR_IMAGE, "Collector image is not pinned")
    names = {str(span.get("name")) for span in spans}
    assert_true(names.issubset(ALLOWED_SPANS), f"unstable or unknown span name: {sorted(names - ALLOWED_SPANS)}")
    for span in spans:
        attrs = attributes(span)
        for key, value in attrs.items():
            assert_true(key in ALLOWED_ATTRIBUTES, f"span attribute outside allowlist: {key}")
            assert_true(not FORBIDDEN_KEY.search(key), f"sensitive span key: {key}")
            assert_true(not FORBIDDEN_VALUE.search(str(value)), f"credential-like span value: {key}")
            if isinstance(value, str) and key not in {"http.route"}:
                assert_true(SAFE_DYNAMIC_VALUE.fullmatch(value) is not None, f"unsafe/high-volume span value: {key}")
        for event in span.get("events", []) if isinstance(span.get("events"), list) else []:
            if isinstance(event, dict):
                for key in event:
                    assert_true(not FORBIDDEN_KEY.search(str(key)), f"sensitive span event key: {key}")
    response_run_id = str(result["modes"]["enabled_healthy"]["canonical"]["response_lost"]["run_id"])
    response_spans = [span for span in spans if attributes(span).get("runproof.run.id") == response_run_id]
    assert_true(response_spans, "response-lost run has no run-correlated spans")
    run_names = {str(span.get("name")) for span in response_spans}
    required_run_names = {
        "runproof.agent.run", "runproof.tool.call", "runproof.environment.provision", "runproof.environment.readiness",
        "runproof.fault.activate", "runproof.target.request", "runproof.target.commit", "runproof.dependency.request",
        "runproof.operation.reconcile", "runproof.verifier.evaluate",
    }
    assert_true(required_run_names.issubset(run_names), f"response-lost run graph missing: {sorted(required_run_names - run_names)}")
    response_trace_ids = {str(span.get("traceId") or span.get("trace_id")) for span in response_spans}
    trace_spans = [span for span in spans if str(span.get("traceId") or span.get("trace_id")) in response_trace_ids]
    trace_names = {str(span.get("name")) for span in trace_spans}
    assert_true({"runproof.job.submit", "runproof.job.execute", "runproof.evidence.ingest", "runproof.job.terminalize"}.issubset(trace_names), "durable Java/Python trace boundary is incomplete")
    commits = [span for span in response_spans if span.get("name") == "runproof.target.commit"]
    assert_true(len(commits) == 1, "response-lost graph does not prove exactly one target commit")
    assert_true(any(span.get("name") == "runproof.target.request" and span.get("status", {}).get("code") for span in response_spans), "transport-loss error span missing")
    assert_true(any(isinstance(span.get("links"), list) and span.get("links") for span in spans if span.get("name") == "runproof.job.execute"), "attempt reclaim span link missing")


def verify_result(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    assert_true(result.get("schema_version") == FORMAL_SCHEMA, "schema version")
    assert_true(result.get("plan_id") == "RPF-30", "plan identity")
    assert_true(result.get("status") == "PASS", "probe status")
    identity = result.get("source_identity", {})
    assert_true(identity.get("source_sha256") == source_hash(source_paths()), "source identity drift")
    modes = result.get("modes", {})
    assert_true(set(modes) == {"disabled", "enabled_healthy", "enabled_unavailable"}, "three mode coverage")
    for name, mode in modes.items():
        verify_mode(name.replace("_", "-"), mode)
    assert_true(modes["enabled_healthy"]["canonical"]["response_lost"]["propagation"].get("target_received") is True, "target did not receive W3C propagation")
    assert_true(modes["enabled_healthy"]["canonical"]["response_lost"]["propagation"].get("target_to_dependency") is True, "dependency did not receive W3C propagation")
    reclaim = result.get("attempt_reclaim", {})
    for key in ("attempt_ids_distinct", "job_context_restored", "previous_attempt_context_returned", "span_link_created", "cleanup_terminalized"):
        assert_true(reclaim.get(key) is True, f"attempt reclaim: {key}")
    negative = result.get("missing_propagation", {})
    assert_true(negative.get("header_missing_detected") is True and negative.get("product_fail_open") is True and negative.get("canonical_outcome") == "PASS", "missing propagation negative control")
    performance = result.get("performance", {})
    assert_true(performance.get("unavailable_nonblocking") is True, "unavailable exporter added synchronous blocking")
    assert_true(performance.get("disabled_no_export_thread") is True, "disabled path initialized exporter")
    telemetry = result.get("telemetry_contract", {})
    assert_true(telemetry.get("canonical_authority") is False and telemetry.get("canonical_trace_schema_change") is False, "telemetry authority/schema boundary drift")
    assert_true(telemetry.get("queue_bounded") is True and telemetry.get("queue_size") <= 1024, "bounded queue contract")
    assert_true(result.get("release_or_deploy_executed") is False, "release/deploy executed")
    cleanup = result.get("cleanup", {})
    assert_true(all(cleanup.get(key) is True for key in ("collector_removed", "postgres_container_removed", "postgres_volume_removed")), "disposable cleanup incomplete")
    verify_spans(result, read_spans(path))
    encoded = json.dumps(result, ensure_ascii=False)
    assert_true(not FORBIDDEN_VALUE.search(encoded), "credential-like value in result")
    return {"status": "PASS", "spans": result.get("collector", {}).get("span_count"), "source": identity.get("source_sha256")}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python spikes/rpf-30/verify-evidence.py <rpf30-result.json>")
        return 2
    try:
        verified = verify_result(Path(sys.argv[1]).resolve())
    except (OSError, json.JSONDecodeError, VerificationFailure) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(verified, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

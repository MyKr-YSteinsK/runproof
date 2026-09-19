"""Offline verifier for the disposable RPF-39 interoperability result."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
SCHEMA = "rpf-genai-interop-evidence-v1"
UPSTREAM_COMMIT = "c88d504ab3d9879f8e50d3cc87e69775e11db234"
SENSITIVE_KEY = re.compile(
    r"authorization|bearer|password|secret|api[_-]?key|prompt|reasoning|body|payload|path|cookie|credential|message|instruction|argument|result",
    re.IGNORECASE,
)
SENSITIVE_VALUE = re.compile(r"Bearer\s+\S+|sk-[A-Za-z0-9_-]{12,}|github_pat_[A-Za-z0-9_]{20,}", re.IGNORECASE)


class VerificationFailure(AssertionError):
    pass


def assert_true(condition: Any, message: str) -> None:
    if not condition:
        raise VerificationFailure(message)


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


def source_hash(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted((item.resolve() for item in paths), key=lambda item: item.relative_to(ROOT).as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


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
            spans.extend(walk_spans(child, service))
    elif isinstance(value, list):
        for child in value:
            spans.extend(walk_spans(child, service_name))
    return spans


def read_spans(result_path: Path) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for value in read_json_values(result_path.parent / "collector" / "traces.json"):
        spans.extend(walk_spans(value))
    return spans


def read_metrics(result_path: Path) -> list[dict[str, Any]]:
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

    for value in read_json_values(result_path.parent / "collector" / "metrics.json"):
        walk(value)
    return metrics


def attributes(span: dict[str, Any]) -> dict[str, Any]:
    raw = span.get("attributes")
    if isinstance(raw, dict):
        return raw
    result: dict[str, Any] = {}
    for item in raw if isinstance(raw, list) else []:
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


def verify_spans(result_path: Path, result: dict[str, Any]) -> None:
    spans = read_spans(result_path)
    assert_true(spans, "Collector trace file is empty")
    names = {str(span.get("name")) for span in spans}
    required = {"invoke_agent production-change-agent", "chat deepseek-flash", "execute_tool apply_change"}
    assert_true(required.issubset(names), "standard Agent/model/tool spans are incomplete")
    standard = [span for span in spans if str(span.get("name")) in required]
    for span in standard:
        values = attributes(span)
        for key in ("gen_ai.operation.name", "runproof.job.id", "runproof.run.id"):
            assert_true(key in values, f"standard span missing {key}")
        if values.get("gen_ai.operation.name") in {"invoke_agent", "chat"}:
            assert_true("gen_ai.provider.name" in values, "GenAI agent/model span missing provider")
        if values.get("gen_ai.operation.name") == "invoke_agent":
            assert_true("gen_ai.agent.name" in values and "gen_ai.request.model" in values, "agent mapping incomplete")
        if values.get("gen_ai.operation.name") == "chat":
            assert_true("gen_ai.request.model" in values and "gen_ai.response.model" in values, "model mapping incomplete")
        if values.get("gen_ai.operation.name") == "execute_tool":
            assert_true(all(key in values for key in ("gen_ai.tool.name", "gen_ai.tool.type", "gen_ai.tool.call.id")), "tool mapping incomplete")
        assert_true("gen_ai.conversation.id" not in values, "conversation id replaced RunProof correlation")
        assert_true(not any(SENSITIVE_KEY.search(key) for key in values), "sensitive standard attribute emitted")
        assert_true(not any(SENSITIVE_VALUE.search(str(value)) for value in values.values()), "credential-like standard value emitted")
    target = [span for span in spans if str(span.get("name")) == "runproof.target.request"]
    reconcile = [span for span in spans if str(span.get("name")) == "runproof.operation.reconcile"]
    assert_true(any(attributes(span).get("runproof.outcome") == "UNKNOWN_OUTCOME" for span in target), "UNKNOWN_OUTCOME diagnostic missing")
    assert_true(any(attributes(span).get("runproof.reconcile.status") == "RECONCILED" for span in reconcile), "reconcile diagnostic missing")
    encoded = json.dumps(spans, ensure_ascii=False).lower()
    assert_true("gen_ai.input.messages" not in encoded, "input messages emitted")
    assert_true("gen_ai.output.messages" not in encoded, "output messages emitted")
    assert_true("gen_ai.tool.call.arguments" not in encoded, "tool arguments emitted")
    assert_true("gen_ai.tool.call.result" not in encoded, "tool result emitted")
    assert_true(result["experiment"]["standard_consumer_readable"] is True, "standard consumer summary failed")


def verify_result(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    assert_true(result.get("schema_version") == SCHEMA, "schema version")
    assert_true(result.get("plan_id") == "RPF-39", "plan identity")
    assert_true(result.get("status") == "PASS", "probe status")
    assert_true(result.get("recommendation") == "BOUNDED_DUAL_EMIT_RECOMMENDED", "recommendation")
    assert_true(result.get("upstream", {}).get("commit") == UPSTREAM_COMMIT, "upstream commit drift")
    assert_true(result.get("upstream", {}).get("stability") == "Development", "upstream stability missing")
    identity = result.get("source_identity", {})
    assert_true(identity.get("source_sha256") == source_hash(source_paths()), "source identity drift")
    experiment = result.get("experiment", {})
    assert_true(experiment.get("deterministic_fixture") is True, "experiment is not deterministic")
    assert_true(experiment.get("live_provider_called") is False, "live provider called")
    assert_true(experiment.get("deepseek_api_key_read") is False, "DeepSeek key was read")
    assert_true(experiment.get("rpf30_collector_reused") is True, "RPF-30 Collector was not reused")
    assert_true(experiment.get("formal_rpf30_evidence_mutated") is False, "RPF-30 evidence mutation reported")
    assert_true(experiment.get("runtime_allowlist_rejects_genai") is True, "formal allowlist boundary drift")
    assert_true(experiment.get("canonical_equivalent_across_modes") is True, "canonical projection changed by telemetry mode")
    assert_true(experiment.get("unknown_outcome_reconcile_preserved") is True, "UNKNOWN_OUTCOME/reconcile separation missing")
    assert_true(experiment.get("no_sensitive_content") is True, "sensitive content was emitted")
    assert_true(experiment.get("metric_point_count") == 2, "metric cardinality fixture drift")
    modes = experiment.get("modes", {})
    assert_true(set(modes) == {"disabled", "enabled_healthy", "enabled_unavailable"}, "mode coverage")
    assert_true(modes["disabled"].get("exporter_created") is False, "disabled mode created exporter")
    assert_true(modes["enabled_healthy"]["telemetry"].get("emit_error") is False, "healthy mode blocked emission")
    assert_true(modes["enabled_healthy"]["telemetry"].get("export_failures") == 0, "healthy mode export failed")
    assert_true(modes["enabled_unavailable"]["telemetry"].get("emit_error") is False, "unavailable exporter changed caller result")
    assert_true(modes["enabled_unavailable"]["telemetry"].get("export_failures", 0) > 0, "unavailable exporter failure not observed")
    verify_spans(path, result)
    metric_names = {str(metric.get("name")) for metric in read_metrics(path)}
    assert_true("gen_ai.client.token.usage" in metric_names, "standard token metric missing from Collector")
    mapping = result.get("mapping_summary", [])
    categories = {item.get("surface"): item.get("category") for item in mapping if isinstance(item, dict)}
    assert_true(categories.get("agent/provider/model/tool") == "ADDITIVE", "agent/model/tool mapping drift")
    assert_true(categories.get("job/attempt/run/environment/operation") == "CUSTOM_ONLY", "canonical identity mapping drift")
    assert_true(categories.get("unknown_outcome/reconcile/fault/verifier/release") == "INCOMPATIBLE", "authority mapping drift")
    assert_true(categories.get("messages/instructions/tool_args/tool_results") == "OPT_IN_SENSITIVE", "privacy mapping drift")
    assert_true(categories.get("gen_ai.conversation.id") == "NOT_APPLICABLE", "conversation mapping drift")
    assert_true(result.get("release_or_deploy_executed") is False, "release/deploy executed")
    assert_true(result.get("cleanup", {}).get("collector_removed") is True, "Collector cleanup incomplete")
    return {
        "status": "PASS",
        "recommendation": result.get("recommendation"),
        "source": identity.get("source_sha256"),
        "upstream_commit": result.get("upstream", {}).get("commit"),
        "standard_spans": sorted({str(span.get("name")) for span in read_spans(path) if str(span.get("name")).startswith(("invoke_agent", "chat ", "execute_tool"))}),
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python spikes/rpf-39/verify-evidence.py <rpf39-result.json>")
        return 2
    try:
        print(json.dumps(verify_result(Path(sys.argv[1]).resolve()), ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, VerificationFailure) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

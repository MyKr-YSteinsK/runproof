"""Offline verifier for the RPF-29 disposable observability result."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SPIKE_ROOT))
import probe  # noqa: E402


def verify_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"RESULT_MISSING:{path}"]
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["RESULT_INVALID_JSON"]
    if not isinstance(result, dict):
        return ["RESULT_NOT_OBJECT"]
    if result.get("schema") != probe.FORMAL_TRACE_SCHEMA:
        errors.append("SCHEMA_MISMATCH")
    if result.get("plan_id") != "RPF-29":
        errors.append("PLAN_ID_MISMATCH")
    if result.get("formal_implementation_changed") is not False:
        errors.append("FORMAL_IMPLEMENTATION_CHANGED")
    if result.get("provider_invoked") is not False:
        errors.append("PROVIDER_INVOKED")
    if result.get("source_sha256") != probe.source_sha256():
        errors.append("SOURCE_SHA_MISMATCH")

    scenarios = {item.get("scenario_id"): item for item in result.get("scenarios", []) if isinstance(item, dict)}
    for required in ("baseline", "response-lost", "missing-propagation", "collector-failure"):
        if required not in scenarios:
            errors.append(f"SCENARIO_MISSING:{required}")
    for scenario_id, item in scenarios.items():
        if item.get("canonical", {}).get("outcome") != "PASS":
            errors.append(f"CANONICAL_NOT_PASS:{scenario_id}")
        if item.get("lifecycle", {}).get("cleanup") != "CLEANED":
            errors.append(f"CLEANUP_NOT_CLEAN:{scenario_id}")
        if not item.get("lifecycle", {}).get("processes_stopped", True):
            errors.append(f"PROCESS_NOT_STOPPED:{scenario_id}")
        if not item.get("lifecycle", {}).get("boundary_removed", True):
            errors.append(f"BOUNDARY_NOT_REMOVED:{scenario_id}")

    response = scenarios.get("response-lost", {})
    response_canonical = response.get("canonical", {})
    if response_canonical.get("unknown_outcome") is not True:
        errors.append("RESPONSE_LOST_UNKNOWN_OUTCOME_MISSING")
    if response_canonical.get("blind_retry_attempts") != 0:
        errors.append("RESPONSE_LOST_BLIND_RETRY")
    if response_canonical.get("effect_count") != 1:
        errors.append("RESPONSE_LOST_EFFECT_COUNT")
    if response.get("fault", {}).get("reconciled") is not True:
        errors.append("RESPONSE_LOST_RECONCILE_MISSING")

    graph = result.get("trace_graph", {})
    if graph.get("passed") is not True:
        errors.append("TRACE_GRAPH_NOT_VERIFIED")
    response_graph = graph.get("response_lost", {})
    for key in ("all_required_spans_same_trace", "target_commit_event", "tool_transport_error", "tool_outcome_unknown", "reconcile_applied", "effect_count_one", "passed"):
        if response_graph.get(key) is not True:
            errors.append(f"TRACE_GRAPH_RESPONSE_LOST:{key}")
    if response_graph.get("duplicate_mutation_spans") != 1:
        errors.append("TRACE_GRAPH_DUPLICATE_MUTATION")
    missing_graph = graph.get("missing_propagation", {})
    if missing_graph.get("chain_incomplete") is not True or missing_graph.get("canonical_outcome_unchanged") is not True or missing_graph.get("passed") is not True:
        errors.append("MISSING_PROPAGATION_NEGATIVE_CONTROL")

    export = result.get("trace_export", {})
    if export.get("protocol") != "OTLP/HTTP JSON":
        errors.append("OTLP_PROTOCOL_MISSING")
    if not isinstance(export.get("collector_file_spans"), int) or export["collector_file_spans"] <= 0:
        errors.append("COLLECTOR_DID_NOT_RECEIVE_SPANS")
    if not isinstance(export.get("audit_exported_spans"), int) or export["audit_exported_spans"] <= 0:
        errors.append("NO_EXPORTED_AUDIT_SPANS")
    if not isinstance(export.get("audit_unavailable_spans"), int) or export["audit_unavailable_spans"] <= 0:
        errors.append("COLLECTOR_FAILURE_NOT_OBSERVED")

    failure = scenarios.get("collector-failure", {})
    if failure.get("canonical", {}).get("outcome") != "PASS":
        errors.append("COLLECTOR_FAILURE_CHANGED_CANONICAL_OUTCOME")
    audit = probe.read_audit_spans(path.parent)
    failure_job = failure.get("ids", {}).get("job_id")
    failure_spans = [item for item in audit if probe.audit_attributes(item).get("rpf.job_id") == failure_job]
    if not failure_spans or any(item.get("collector_exported") is True for item in failure_spans):
        errors.append("COLLECTOR_FAILURE_EXPORT_STATE_INVALID")

    sensitivity = result.get("sensitive_data_policy", {})
    if sensitivity.get("allowlist_only") is not True or sensitivity.get("forbidden_keys_absent_from_output") is not True:
        errors.append("SENSITIVE_ALLOWLIST_FAILED")
    if any(re.search(r"authorization|bearer|deepseek_api_key|private_reasoning", key, re.IGNORECASE) for key in sensitivity.get("accepted_example_keys", [])):
        errors.append("SENSITIVE_KEY_ESCAPED_ALLOWLIST")

    cardinality = result.get("cardinality_review", {})
    if cardinality.get("high_cardinality_ids_as_labels") is True:
        errors.append("HIGH_CARDINALITY_METRIC_LABELS")
    if any(item in cardinality.get("safe_metric_labels", []) for item in cardinality.get("forbidden_metric_labels", [])):
        errors.append("CARDINALITY_MATRIX_CONTRADICTION")

    recommendation = result.get("recommendation", {})
    if recommendation.get("proceed_to_formal_otel") not in {"YES", "NO", "CONDITIONAL"}:
        errors.append("RECOMMENDATION_MISSING")
    if result.get("docker_cleanup") != {"containers": [], "volumes": [], "networks": []}:
        errors.append("DOCKER_RESIDUALS")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify an RPF-29 result without starting services.")
    parser.add_argument("result", nargs="?", type=Path, default=probe.LOCAL_ROOT / probe.RESULT_NAME)
    args = parser.parse_args(argv)
    errors = verify_file(args.result.resolve())
    print(json.dumps({"status": "PASS" if not errors else "INVALID", "errors": errors, "result": str(args.result.resolve())}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

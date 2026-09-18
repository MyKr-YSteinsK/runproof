"""Offline verifier for the RPF-33 disposable capacity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
SCHEMA = "rpf-capacity-large-trace-investigation-v1"
FIXTURE_VERSION = "rpf33-capacity-fixture-v1"
FIXTURE_SEED = "rpf33-seed-20260918"


def source_hash() -> tuple[str, list[str]]:
    paths = [
        SPIKE_ROOT / "README.md", SPIKE_ROOT / "probe.py", SPIKE_ROOT / "verify-evidence.py",
        SPIKE_ROOT / "java" / "pom.xml", SPIKE_ROOT / "java" / "src" / "main" / "java" / "com" / "runproof" / "rpf33" / "BulkS3Probe.java",
        ROOT / ".github" / "workflows" / "rpf-33-capacity-spike.yml",
    ]
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix()):
        if not path.is_file():
            raise ValueError(f"missing source file: {path}")
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8")); digest.update(b"\0"); digest.update(path.read_bytes()); digest.update(b"\0")
        files.append(relative)
    return digest.hexdigest(), files


def fail(message: str) -> None:
    raise ValueError(message)


def walk(value: Any, path: str = "$"):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")


def verify_document(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != SCHEMA:
        fail("schema_version mismatch")
    if document.get("status") != "PASS":
        fail(f"probe status is {document.get('status')!r}")
    fixture = document.get("fixture")
    if not isinstance(fixture, dict) or fixture.get("version") != FIXTURE_VERSION or fixture.get("seed") != FIXTURE_SEED:
        fail("fixture identity mismatch")
    if document.get("lifecycle") != "Stabilization":
        fail("lifecycle changed")
    if document.get("historical_bytes_unchanged") is not True:
        fail("historical corpus boundary is not asserted")
    cleanup = document.get("cleanup")
    if not isinstance(cleanup, dict) or not cleanup or not all(value is True for value in cleanup.values()):
        fail("cleanup is incomplete")
    identity = document.get("source_identity")
    expected_hash, expected_files = source_hash()
    if not isinstance(identity, dict) or identity.get("source_sha256") != expected_hash or identity.get("files") != expected_files:
        fail("source identity mismatch")
    tiers = document.get("scale_tiers")
    if not isinstance(tiers, list) or not tiers:
        fail("scale tier evidence missing")
    mode = document.get("mode")
    tier_names = [item.get("tier") for item in tiers if isinstance(item, dict)]
    if mode == "local-full":
        if tier_names != ["small", "medium", "large"]:
            fail("local scale tiers are incomplete")
        large = tiers[-1]
        if large.get("jobs_total", 0) < 10_000 or large.get("artifact_rows_total", 0) < 10_000:
            fail("large tier does not reach the required order of magnitude")
    elif mode == "hosted-medium":
        if tier_names != ["medium"] or tiers[0].get("jobs_total", 0) < 1_000:
            fail("hosted medium tier is incomplete")
    else:
        fail("unknown execution mode")
    totals = document.get("fixture_totals")
    for key in ("jobs", "attempts", "events", "execution_evidence", "canonical_metadata"):
        if not isinstance(totals, dict) or int(str(totals.get(key, "0"))) <= 0:
            fail(f"fixture total missing: {key}")
    if document.get("sql_statement_logging", {}).get("enabled") is not True:
        fail("PostgreSQL statement logging was not enabled")
    for tier in tiers:
        if not isinstance(tier.get("api_payload_inventory"), list) or len(tier["api_payload_inventory"]) < 5:
            fail("API payload inventory is incomplete")
        for item in tier["api_payload_inventory"]:
            if not isinstance(item.get("observed_sql_statements"), int) or item["observed_sql_statements"] < 1:
                fail("API SQL statement-count evidence is incomplete")
        if not isinstance(tier.get("explain"), dict):
            fail("EXPLAIN evidence is missing")
        if not isinstance(tier.get("database_sizes"), dict):
            fail("database size evidence is missing")
        expected_timeline_events = {"small": 100, "medium": 1_000, "large": 10_000}.get(tier.get("tier"))
        timeline = tier.get("timeline")
        timeline_api = timeline.get("api", {}) if isinstance(timeline, dict) else {}
        if expected_timeline_events is None or not isinstance(timeline, dict) or int(timeline.get("events", 0)) != expected_timeline_events:
            fail("per-Run timeline scale evidence is incomplete")
        if timeline_api.get("status") != 200 or int(timeline_api.get("events", 0)) != expected_timeline_events or not isinstance(timeline_api.get("observed_sql_statements"), int) or timeline_api.get("observed_sql_statements", 0) < 1:
            fail("per-Run timeline API evidence is incomplete")
    plans = tiers[-1].get("explain", {})
    before = plans.get("canonical_run_list_before_candidate", {})
    after = plans.get("canonical_run_list_after_candidate", {})
    if not before or not after:
        fail("candidate index A/B evidence is missing")
    concurrency = document.get("worker_concurrency")
    if not isinstance(concurrency, list) or [item.get("concurrency") for item in concurrency] != [1, 2, 4]:
        fail("worker concurrency matrix is incomplete")
    for item in concurrency:
        if not isinstance(item.get("state_counts"), dict) or int(item["state_counts"].get("COMPLETED", 0)) != int(item.get("jobs_submitted", 0)):
            fail("worker concurrency did not complete all jobs")
        statuses = item.get("job_result_status_counts", {})
        unexpected_statuses = set(statuses) - {"COMPLETED", "TERMINAL"}
        if int(item.get("claim_or_terminal_errors", 1)) != 0 or unexpected_statuses or int(statuses.get("COMPLETED", 0)) != int(item.get("jobs_submitted", 0)):
            fail("worker concurrency returned a platform or claim error")
    claim = document.get("claim_reclaim")
    if not isinstance(claim, dict) or claim.get("claim_race", {}).get("claimed_count") != 1:
        fail("claim race evidence is invalid")
    if claim.get("reclaim", {}).get("second_claim") not in {"CLAIMED", "RECLAIMED"}:
        fail("lease reclaim evidence is missing")
    sizes = document.get("artifact_sizes", {})
    http_sizes = sizes.get("http_byte_array", []) if isinstance(sizes, dict) else []
    if [item.get("size_bytes") for item in http_sizes] != [1024, 1_048_576, 16 * 1_048_576]:
        fail("byte[] size matrix is incomplete")
    if any(item.get("status") != 200 for item in http_sizes):
        fail("artifact byte upload did not pass")
    orphan = document.get("orphan_growth")
    if not isinstance(orphan, list) or len(orphan) < 2:
        fail("orphan growth evidence is missing")
    otel = document.get("otel")
    if not isinstance(otel, dict) or not isinstance(otel.get("enabled_healthy"), dict) or not isinstance(otel.get("disabled_baseline"), dict) or not isinstance(otel.get("enabled_collector_unavailable"), dict):
        fail("OTel comparison is incomplete")
    isolation = document.get("failure_isolation")
    if not isinstance(isolation, dict) or isolation.get("s3_unavailable", {}).get("health_status") != 503 or isolation.get("s3_restarted", {}).get("canonical_read_status") != 200:
        fail("storage failure isolation is incomplete")
    gates = document.get("decision_gates")
    allowed = {"YES", "NO", "NOT_YET", "CONDITIONAL"}
    expected_gate_keys = {"DB_OPTIMIZATION_REQUIRED", "BROKER_REQUIRED", "STREAMING_ARTIFACTSTORE_REQUIRED", "GC_PLAN_REQUIRED", "WEB_PAGINATION_REQUIRED", "WEB_VIRTUALIZATION_REQUIRED"}
    if not isinstance(gates, dict) or not expected_gate_keys.issubset(gates) or any(gates[key] not in allowed for key in expected_gate_keys):
        fail("decision gates are invalid")
    if gates.get("BROKER_REQUIRED") == "YES":
        fail("broker cannot be recommended without the required gate evidence")
    secret_like = re.compile(r"(?:authorization|bearer|password|secret|token|api[_-]?key|credential|private.?reasoning|chain.?of.?thought)", re.IGNORECASE)
    for path, value in walk(document):
        if secret_like.search(path):
            fail(f"sensitive key leaked into evidence: {path}")
        if isinstance(value, str) and secret_like.search(value):
            fail(f"sensitive value leaked into evidence: {path}")
    return {"status": "PASS", "schema_version": SCHEMA, "source_sha256": expected_hash, "tiers": tier_names, "historical_bytes_unchanged": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    try:
        document = json.loads(args.result.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            fail("result must be an object")
        summary = verify_document(document)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
        print(f"RPF33_VERIFY_FAIL {type(error).__name__}: {error}")
        return 1
    print(f"RPF33_VERIFY_PASS schema={summary['schema_version']} source_sha256={summary['source_sha256']} tiers={','.join(summary['tiers'])} historical_bytes_unchanged=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

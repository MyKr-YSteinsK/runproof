"""Offline verifier for the RPF-34 bounded Execution read proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
SCHEMA = "rpf-execution-bounded-read-model-v1"
CURSOR_CONTRACT = "rpf-execution-cursor-v1"


def fail(message: str) -> None:
    raise ValueError(message)


def source_hash() -> tuple[str, list[str]]:
    paths = [
        SPIKE_ROOT / "README.md", SPIKE_ROOT / "probe.py", SPIKE_ROOT / "verify-evidence.py",
        ROOT / ".github" / "workflows" / "rpf-34-read-model.yml",
        ROOT / "control-plane" / "pom.xml",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "DurableExecutionController.java",
        ROOT / "runtime" / "runproof_runtime" / "durable_worker.py",
        ROOT / "web" / "src" / "App.tsx", ROOT / "web" / "src" / "data" / "executions.ts", ROOT / "web" / "src" / "styles.css",
    ]
    digest = hashlib.sha256(); files: list[str] = []
    for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix()):
        if not path.is_file(): fail(f"missing source: {path}")
        relative = path.relative_to(ROOT).as_posix(); digest.update(relative.encode()); digest.update(b"\0"); digest.update(path.read_bytes()); digest.update(b"\0"); files.append(relative)
    return digest.hexdigest(), files


def verify_page(page: dict[str, Any], *, expected_limit: int, max_sql: int, max_bytes: int, label: str) -> None:
    if page.get("status") != 200: fail(f"{label}: HTTP status")
    if int(page.get("limit", 0)) != expected_limit: fail(f"{label}: limit")
    if int(page.get("rows", 0)) > expected_limit: fail(f"{label}: rows exceed limit")
    if not isinstance(page.get("sql_statements"), int) or page["sql_statements"] > max_sql: fail(f"{label}: SQL budget")
    if int(page.get("response_bytes", max_bytes + 1)) > max_bytes: fail(f"{label}: payload budget")


def verify_document(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != SCHEMA or document.get("status") != "PASS": fail("schema/status")
    serialized = json.dumps(document, ensure_ascii=True).lower()
    if any(marker in serialized for marker in ("deepseek", "authorization:", "private_reasoning", "chain_of_thought", "api_key", "password=")):
        fail("secret/private protocol material in evidence")
    security = document.get("security_boundary")
    if not isinstance(security, dict) or security.get("redacted_output") is not True or security.get("credential_sources") != "process/container environment only" or security.get("private_protocol_fields") != "absent":
        fail("security boundary")
    fixture = document.get("fixture")
    if not isinstance(fixture, dict) or fixture.get("version") != "rpf34-execution-read-fixture-v1" or fixture.get("seed") != "rpf34-seed-20260918": fail("fixture identity")
    if int(fixture.get("jobs", 0)) < 10_001 or int(fixture.get("events", 0)) < 50_000: fail("large fixture scale")
    if document.get("lifecycle") != "Stabilization" or document.get("historical_bytes_unchanged") is not True: fail("lifecycle/historical boundary")
    cleanup = document.get("cleanup")
    if not isinstance(cleanup, dict) or not cleanup or not all(value is True for value in cleanup.values()): fail("cleanup")
    expected_hash, expected_files = source_hash()
    identity = document.get("source_identity")
    if not isinstance(identity, dict) or identity.get("source_sha256") != expected_hash or identity.get("files") != expected_files: fail("source identity")

    contracts = document.get("contracts", {})
    history = contracts.get("history", {}) if isinstance(contracts, dict) else {}
    timeline = contracts.get("timeline", {}) if isinstance(contracts, dict) else {}
    if history.get("default_limit") != 50 or history.get("max_limit") != 100 or history.get("cursor_contract") != CURSOR_CONTRACT or history.get("cursor_opaque") is not True: fail("history cursor contract")
    if timeline.get("default_limit") != 200 or timeline.get("max_limit") != 500 or timeline.get("cursor_contract") != CURSOR_CONTRACT or timeline.get("cursor_opaque") is not True: fail("timeline cursor contract")

    pages = document.get("history_pages")
    if not isinstance(pages, dict): fail("history pages")
    for limit in (1, 50, 100):
        page = pages.get(str(limit))
        if not isinstance(page, dict): fail(f"history page {limit}")
        verify_page(page, expected_limit=limit, max_sql=10, max_bytes=512 * 1024, label=f"history {limit}")
        if page.get("forbidden_summary_fields") != []: fail(f"summary shape {limit}")
    sql_counts = [int(pages[str(limit)]["sql_statements"]) for limit in (1, 50, 100)]
    if max(sql_counts) - min(sql_counts) > 9: fail("history SQL grows with page size")
    hard_max = document.get("history_hard_max")
    if not isinstance(hard_max, dict) or hard_max.get("status") != 200 or hard_max.get("limit") != 100 or int(hard_max.get("rows", 101)) > 100: fail("history hard maximum")

    cursor_validation = document.get("cursor_validation", {})
    malformed = cursor_validation.get("malformed", {})
    incompatible = cursor_validation.get("filter_incompatible", {})
    empty = cursor_validation.get("empty_dataset", {})
    if malformed.get("status") != 400 or malformed.get("error") != "INVALID_EXECUTION_CURSOR": fail("malformed history cursor")
    if incompatible.get("status") != 400 or incompatible.get("error") != "INCOMPATIBLE_EXECUTION_CURSOR": fail("incompatible history cursor")
    if empty.get("status") != 200 or empty.get("rows") != 0 or empty.get("has_more") is not False: fail("empty history semantics")

    concurrent = document.get("history_concurrent_insert", {})
    if not isinstance(concurrent, dict) or concurrent.get("no_duplicate") is not True or concurrent.get("expected_fixture_rows_present") is not True or concurrent.get("concurrent_insert_seen") is not True or concurrent.get("end_state") != {"has_more": False, "next_cursor": None}: fail("concurrent history paging")
    if int(concurrent.get("duplicate_rows", 1)) != 0: fail("history duplicate")

    detail = document.get("detail", {})
    if detail.get("status") != 200 or detail.get("events_field_present") is not False or detail.get("attempts_is_array") is not True or detail.get("operations_is_array") is not True or detail.get("evidence_is_array") is not True: fail("bounded detail")
    if not isinstance(detail.get("timeline"), dict) or detail["timeline"].get("partial") is not True or detail["timeline"].get("path") != "/jobs/{jobId}/events": fail("detail timeline descriptor")

    timeline_result = document.get("timeline", {})
    if not isinstance(timeline_result, dict) or timeline_result.get("events_seen") != 10_000 or timeline_result.get("strictly_increasing_unique") is not True or timeline_result.get("end_state") != {"has_more": False, "next_cursor": None}: fail("timeline traversal")
    for key in ("first_page", "middle_page", "final_page"):
        page = timeline_result.get(key)
        if not isinstance(page, dict): fail(f"timeline {key}")
        verify_page(page, expected_limit=500, max_sql=3, max_bytes=512 * 1024, label=f"timeline {key}")
    if int(timeline_result.get("all_page_sql_max", 99)) > 3 or int(timeline_result.get("all_page_payload_max", 512 * 1024 + 1)) > 512 * 1024: fail("timeline aggregate budget")

    timeline_validation = document.get("timeline_cursor_validation", {})
    if timeline_validation.get("malformed", {}).get("status") != 400 or timeline_validation.get("malformed", {}).get("error") != "INVALID_EXECUTION_CURSOR": fail("malformed timeline cursor")
    if timeline_validation.get("filter_incompatible", {}).get("status") != 400 or timeline_validation.get("filter_incompatible", {}).get("error") != "INCOMPATIBLE_EXECUTION_CURSOR": fail("incompatible timeline cursor")
    if timeline_validation.get("not_found", {}).get("status") != 404: fail("timeline not-found semantics")

    discovery = document.get("worker_discovery", {})
    if discovery.get("submit_status") not in {200, 201} or discovery.get("list_status") != 200 or discovery.get("discovery") != "ELIGIBLE" or discovery.get("candidate_seen") is not True or discovery.get("summary_forbidden_fields") != [] or discovery.get("detail_fetch_for_reconcile") is not True: fail("worker discovery contract")
    plans = document.get("query_plans", {})
    if not isinstance(plans.get("history_summary"), dict) or not isinstance(plans.get("timeline_page"), dict): fail("query plans")
    if any("Offset" in plan.get("node_counts", {}) for plan in plans.values() if isinstance(plan, dict)): fail("offset plan")
    if document.get("index_re_evaluation", {}).get("formal_migration") is not False: fail("formal index migration boundary")
    if document.get("web_contract", {}).get("real_device_verification") != "not executed": fail("real device boundary")

    return {"status": "PASS", "schema_version": SCHEMA, "source_sha256": expected_hash, "history_sql_max": max(sql_counts), "timeline_sql_max": timeline_result.get("all_page_sql_max"), "timeline_events": timeline_result.get("events_seen")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    try:
        document = json.loads(args.result.read_text(encoding="utf-8"))
        summary = verify_document(document)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
        print(f"RPF34_VERIFY_FAIL {error}", file=sys.stderr)
        return 1
    print(f"RPF34_VERIFY_PASS schema={summary['schema_version']} source_sha256={summary['source_sha256']} history_sql_max={summary['history_sql_max']} timeline_sql_max={summary['timeline_sql_max']} timeline_events={summary['timeline_events']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

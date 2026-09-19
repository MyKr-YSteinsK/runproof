"""Offline verifier for the RPF-35 bounded Canonical Metadata proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
SCHEMA = "rpf-canonical-bounded-read-model-v1"
CURSOR_CONTRACT = "rpf-metadata-cursor-v1"


def fail(message: str) -> None:
    raise ValueError(message)


def source_hash() -> tuple[str, list[str]]:
    paths = [
        SPIKE_ROOT / "README.md", SPIKE_ROOT / "probe.py", SPIKE_ROOT / "verify-evidence.py",
        ROOT / ".github" / "workflows" / "rpf-35-canonical-read-model.yml",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "ApiModels.java",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "CanonicalMetadataService.java",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "ControlPlaneController.java",
        ROOT / "runtime" / "runproof_runtime" / "control_plane_client.py",
        ROOT / "web" / "src" / "App.tsx", ROOT / "web" / "src" / "app" / "navigation.ts",
        ROOT / "web" / "src" / "data" / "artifacts.ts", ROOT / "web" / "src" / "data" / "controlPlaneApi.ts",
        ROOT / "web" / "src" / "data" / "routeScopedControlPlane.ts",
        ROOT / "web" / "src" / "features" / "canonical" / "CanonicalApiPages.tsx",
        ROOT / "web" / "src" / "i18n" / "messages.ts", ROOT / "web" / "src" / "styles.css",
    ]
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix()):
        if not path.is_file():
            fail(f"missing source: {path}")
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        files.append(relative)
    return digest.hexdigest(), files


def verify_page(page: dict[str, Any], *, expected_limit: int, label: str) -> None:
    if page.get("status") != 200:
        fail(f"{label}: HTTP status")
    if int(page.get("limit", 0)) != expected_limit:
        fail(f"{label}: limit")
    if int(page.get("rows", 0)) > expected_limit:
        fail(f"{label}: rows exceed limit")
    sql_count = page.get("sql_statements")
    if not isinstance(sql_count, int) or sql_count > 4:
        fail(f"{label}: SQL budget")
    payload = int(page.get("response_bytes", 512 * 1024 + 1))
    if payload > 512 * 1024:
        fail(f"{label}: payload budget")


def verify_document(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != SCHEMA or document.get("status") != "PASS":
        fail("schema/status")
    serialized = json.dumps(document, ensure_ascii=True).lower()
    if any(marker in serialized for marker in ("deepseek", "authorization:", "private_reasoning", "chain_of_thought", "api_key", "password=")):
        fail("secret/private protocol material in evidence")

    security = document.get("security_boundary")
    if not isinstance(security, dict) or security.get("redacted_output") is not True or security.get("credential_sources") != "process/container environment only" or security.get("private_protocol_fields") != "absent":
        fail("security boundary")
    fixture = document.get("fixture")
    if not isinstance(fixture, dict) or fixture.get("version") != "rpf35-canonical-metadata-fixture-v1" or fixture.get("seed") != "rpf35-seed-20260918":
        fail("fixture identity")
    if int(fixture.get("metadata_rows", 0)) < 13_502 or int(fixture.get("run_rows", 0)) < 10_002:
        fail("large fixture scale")
    if document.get("lifecycle") != "Stabilization" or document.get("historical_bytes_unchanged") is not True:
        fail("lifecycle/historical boundary")
    cleanup = document.get("cleanup")
    if not isinstance(cleanup, dict) or not cleanup or not all(value is True for value in cleanup.values()):
        fail("cleanup")

    expected_hash, expected_files = source_hash()
    identity = document.get("source_identity")
    if not isinstance(identity, dict) or identity.get("source_sha256") != expected_hash or identity.get("files") != expected_files:
        fail("source identity")

    contracts = document.get("contracts")
    if not isinstance(contracts, dict) or contracts.get("default_limit") != 50 or contracts.get("max_limit") != 100 or contracts.get("cursor_contract") != CURSOR_CONTRACT or contracts.get("cursor_opaque") is not True or contracts.get("offset_primary") is not False:
        fail("cursor contract")

    default_page = document.get("default_page")
    if not isinstance(default_page, dict):
        fail("default page")
    verify_page(default_page, expected_limit=50, label="default page")
    if int(default_page.get("rows", 0)) != 50 or default_page.get("artifact_body_read_count") != 0:
        fail("default page bounded/list semantics")

    pages = document.get("metadata_pages")
    if not isinstance(pages, dict):
        fail("metadata pages")
    sql_counts: list[int] = []
    for limit in (1, 50, 100):
        page = pages.get(str(limit))
        if not isinstance(page, dict):
            fail(f"metadata page {limit}")
        verify_page(page, expected_limit=limit, label=f"metadata page {limit}")
        if page.get("rows") != limit or page.get("has_more") is not True or page.get("next_cursor_present") is not True or page.get("artifact_body_read_count") != 0:
            fail(f"metadata page {limit} semantics")
        if int(page.get("response_bytes", 512 * 1024 + 1)) > 256 * 1024:
            fail(f"metadata page {limit}: SHOULD payload budget")
        sql_counts.append(int(page["sql_statements"]))
    if max(sql_counts) > 2:
        fail("metadata page SHOULD SQL budget")

    hard_max = document.get("hard_max")
    if not isinstance(hard_max, dict) or hard_max.get("status") != 200 or hard_max.get("limit") != 100 or int(hard_max.get("rows", 101)) > 100:
        fail("hard maximum")
    cross = document.get("cross_type_page")
    if not isinstance(cross, dict) or cross.get("status") != 200 or cross.get("limit") != 100 or int(cross.get("rows", 101)) > 100:
        fail("cross-type page")

    validation = document.get("cursor_validation")
    if not isinstance(validation, dict):
        fail("cursor validation")
    malformed = validation.get("malformed", {})
    incompatible = validation.get("filter_incompatible", {})
    empty = validation.get("empty_page", {})
    if malformed.get("status") != 400 or malformed.get("error") != "INVALID_METADATA_CURSOR":
        fail("malformed cursor")
    if incompatible.get("status") != 400 or incompatible.get("error") != "INCOMPATIBLE_METADATA_CURSOR":
        fail("incompatible cursor")
    if empty.get("status") != 200 or empty.get("rows") != 0 or empty.get("has_more") is not False:
        fail("empty page")

    concurrent = document.get("concurrent_insert")
    if not isinstance(concurrent, dict) or concurrent.get("no_duplicate") is not True or concurrent.get("duplicate_rows") != 0 or concurrent.get("expected_fixture_rows_present") is not True or concurrent.get("concurrent_insert_seen") is not True or concurrent.get("end_state") != {"has_more": False, "next_cursor": None}:
        fail("concurrent insertion semantics")
    if concurrent.get("rows_seen") != 10_002:
        fail("concurrent row count")

    detail = document.get("detail")
    if not isinstance(detail, dict) or detail.get("metadata_status") != 200 or detail.get("metadata_registered") is not True or detail.get("artifact_status") != 200 or detail.get("artifact_verified") is not True or int(detail.get("artifact_body_bytes", 0)) <= 0 or detail.get("metadata_has_trajectory") is not False:
        fail("verified detail")
    boundary = document.get("artifact_read_boundary")
    if not isinstance(boundary, dict) or boundary.get("list_full_body_reads") != 0 or boundary.get("detail_full_body_reads") != 1 or boundary.get("list_availability") != "REGISTERED_REFERENCE" or boundary.get("detail_requires_verified_endpoint") is not True:
        fail("artifact read boundary")

    plans = document.get("query_plans")
    if not isinstance(plans, dict) or not isinstance(plans.get("metadata_by_type"), dict) or not isinstance(plans.get("metadata_cross_type"), dict):
        fail("query plans")
    for name, plan in plans.items():
        if not isinstance(plan, dict) or "Offset" in plan.get("node_counts", {}) or "OFFSET" in str(plan.get("query", "")).upper() or "LIMIT" not in str(plan.get("query", "")).upper():
            fail(f"{name}: offset/keyset plan")
        if "created_at >" not in str(plan.get("query", "")):
            fail(f"{name}: keyset predicate")
    if document.get("index_re_evaluation", {}).get("formal_migration") is not False or document.get("web_contract", {}).get("real_device_verification") != "not executed":
        fail("scope boundary")
    if document.get("web_contract", {}).get("global_corpus_loader_used") is not False or document.get("web_contract", {}).get("auto_cursor_crawl") is not False:
        fail("web no-auto-crawl boundary")

    return {
        "status": "PASS",
        "schema_version": SCHEMA,
        "source_sha256": expected_hash,
        "metadata_sql_max": max(sql_counts),
        "metadata_payload_max": max(int(pages[str(limit)]["response_bytes"]) for limit in (1, 50, 100)),
        "metadata_rows": fixture["metadata_rows"],
        "concurrent_rows": concurrent["rows_seen"],
        "detail_artifact_bytes": detail["artifact_body_bytes"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    try:
        document = json.loads(args.result.read_text(encoding="utf-8"))
        summary = verify_document(document)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
        print(f"RPF35_VERIFY_FAIL {error}", file=sys.stderr)
        return 1
    print(
        f"RPF35_VERIFY_PASS schema={summary['schema_version']} source_sha256={summary['source_sha256']} "
        f"metadata_sql_max={summary['metadata_sql_max']} metadata_payload_max={summary['metadata_payload_max']} "
        f"metadata_rows={summary['metadata_rows']} concurrent_rows={summary['concurrent_rows']} "
        f"detail_artifact_bytes={summary['detail_artifact_bytes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

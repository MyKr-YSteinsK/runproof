"""Frozen native request and operator-approved estimated cost contract."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import pge_r106_contracts as inner, pge_r110_contracts as previous
from .pge_r107_contracts import project
from .sdk_presend_contracts import check, sha

BASE = "225dcebe3c51b0fb2c85dafef0842efaff223ad5"
HOST, PATH, MODEL = previous.HOST, previous.ENDPOINT, previous.MODEL
PORT = 443
CHOICES, TOOL = previous.CHOICES, previous.TOOL
OUTPUT_CAP = 128
BODY_CAP = 4096
RESPONSE_CAP = 65536
PRICING = "https://api-docs.deepseek.com/quick_start/pricing/"
PARTS = ("contracts", "presend", "transport", "provider", "session", "witness", "verify")
NATIVE, STUB, B0 = "REAL_EXPLORER", "LOCAL_STUB", "FIXED_ORDER_B0"


def sources():
    return previous.sources() | {
        "pge_r110_live_" + part: sha(Path(__file__).with_name("pge_r110_live_" + part + ".py")
                                       .read_bytes().replace(b"\r\n", b"\n"))
        for part in PARTS}


def utc(value):
    check(type(value) is str and len(value) == 20 and value.endswith("Z"), "APPROVAL_TIME")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    check(parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value, "APPROVAL_TIME")
    return parsed


def cost(budget, input_tokens, output_tokens):
    return (input_tokens * budget["input_rate_microunits_per_million"]
            + output_tokens * budget["output_rate_microunits_per_million"] + 999999) // 1000000


def validate_budget(row, source, run, *, now=None):
    inner.exact(row, "schema", "source_git_sha", "github_run_id", "provider", "model", "host", "path",
                "max_requests", "max_input_bytes", "max_input_tokens", "max_output_tokens", "timeout_seconds",
                "currency", "max_cost_microunits", "input_rate_microunits_per_million",
                "output_rate_microunits_per_million", "pricing_url", "pricing_checked_utc", "expires_utc")
    check(inner.hex_id(source, 40) and type(run) is str and 1 <= len(run) <= 20 and run.isascii()
          and run.isdecimal() and row["schema"] == "rpf110-live-budget-v1"
          and (row["source_git_sha"], row["github_run_id"]) == (source, run)
          and (row["provider"], row["host"], row["path"], row["model"]) == ("DeepSeek", HOST, PATH, MODEL)
          and row["currency"] in ("CNY", "USD") and row["pricing_url"] == PRICING, "BUDGET_SCOPE")
    for field, low, high in (("max_requests", 1, 1), ("max_input_bytes", 1, BODY_CAP),
                             ("max_input_tokens", 1, 8192), ("max_output_tokens", OUTPUT_CAP, OUTPUT_CAP),
                             ("timeout_seconds", 1, 40), ("max_cost_microunits", 1, 10**8),
                             ("input_rate_microunits_per_million", 1, 10**9),
                             ("output_rate_microunits_per_million", 1, 10**9)):
        check(type(row[field]) is int and low <= row[field] <= high, "BUDGET_LIMIT")
    checked, expires = utc(row["pricing_checked_utc"]), utc(row["expires_utc"])
    check(checked < expires <= checked + timedelta(hours=24)
          and (now is None or checked <= now < expires), "BUDGET_EXPIRY")
    check(cost(row, row["max_input_tokens"], row["max_output_tokens"]) <= row["max_cost_microunits"],
          "COST_ESTIMATE")
    return row


def freeze(frozen, view, verified, kind, approval=None):
    check(kind in (NATIVE, STUB, B0) and (approval is not None) == (kind == NATIVE)
          and view["run_sha256"] == inner.digest(frozen) and not view["latched"], "LIVE_SCOPE")
    feedback = project(frozen, view, verified)
    raw = previous.request({"feedback": feedback})
    limit = approval["budget"]["max_input_bytes"] if approval else BODY_CAP
    if approval:
        validate_budget(approval["budget"], frozen["scope"]["source_git_sha"], approval["github_run_id"])
        # This is the operator's conservative allowance, not an API tokenizer guarantee.
        check(len(raw) + 256 <= approval["budget"]["max_input_tokens"], "INPUT_ESTIMATE")
    check(len(raw) <= limit, "INPUT_BYTES")
    return {"schema": "rpf110-live-v1", "kind": kind, "scope": frozen["scope"], "sources": sources(),
            "business_sha256": inner.digest(frozen), "seed_view_sha256": inner.digest(view),
            "seed_tip": view["tip"], "seed_revision": view["revision"], "feedback": feedback,
            "endpoint": {"method": "POST", "host": HOST, "port": PORT, "path": PATH, "model": MODEL},
            "request_sha256": sha(raw), "request_size": len(raw), "max_requests": int(kind != B0),
            "continuation_budget": 1, "retry": False, "approval": approval}


def request(contract):
    raw = previous.request({"feedback": contract["feedback"]})
    check(sha(raw) == contract["request_sha256"] and len(raw) == contract["request_size"], "REQUEST_BYTES")
    return raw


def validate_approval(row, source):
    inner.exact(row, "github_run_id", "attempt", "reviewer", "dispatcher", "budget", "budget_sha256")
    check(type(row["attempt"]) is int and row["attempt"] == 1 and
          all(type(row[key]) is str and 0 < len(row[key]) <= 39 and row[key].isascii()
              and all(ch.isalnum() or ch == "-" for ch in row[key]) for key in ("reviewer", "dispatcher"))
          and row["budget_sha256"] == inner.digest(row["budget"]), "APPROVAL_RECEIPT")
    validate_budget(row["budget"], source, row["github_run_id"])
    return row

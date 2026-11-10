"""Frozen Phase A identity, budget and minimal feedback projection."""
from pathlib import Path

from . import pge_r106_contracts as inner
from .pge_r107_contracts import project
from .sdk_presend_contracts import canonical, check, sha

BASE = "39f19b20db5175f44bf73e971094d5a0807bb5a0"
CHOICES = (inner.ORDER, inner.OPS, inner.STOP)
TOOL = "select_experiment"
HOST = "api.deepseek.com"
ENDPOINT = "/chat/completions"
MODEL = "deepseek-flash"
MAX_REPLY = 16384
OUTPUT_CAP = 128
INPUT_FIXTURE_BYTES = 4096
TIMEOUT_MS = 15000
PARTS = ("contracts", "presend", "provider", "explorer", "session", "oracle", "witness", "verify")
DEPS = ("pge_r106_contracts", "pge_r106_ledger", "pge_r106_targets", "pge_r106_oracle",
        "pge_r107_contracts", "pge_r107_host", "pge_r108_controller_adapter", "pge_r108_verify",
        "product_local_ports", "product_sdk_target", "sdk_presend_contracts", "effect_oracle", "ops_oracle")


def sources():
    return {name: sha(Path(__file__).with_name(name + ".py").read_bytes().replace(b"\r\n", b"\n"))
            for name in (*("pge_r110_" + part for part in PARTS), *DEPS)}


def freeze(frozen, view, verified, strategy):
    check(strategy in ("FIXTURE_ONLY", "FIXED_ORDER_B0"), "PHASE_A_STRATEGY")
    feedback = project(frozen, view, verified)
    check(not view["latched"] and view["run_sha256"] == inner.digest(frozen), "SEED_VIEW")
    return {"schema": "rpf110-phase-a-v1", "scope": frozen["scope"], "sources": sources(),
            "business_sha256": inner.digest(frozen), "seed_tip": view["tip"], "seed_revision": view["revision"],
            "seed_view_sha256": inner.digest(view), "strategy": strategy, "feedback": feedback,
            "request_budget": int(strategy == "FIXTURE_ONLY"), "continuation_budget": 1,
            "protocol": {"host": HOST, "path": ENDPOINT, "model": MODEL, "max_output_tokens": OUTPUT_CAP,
                         "max_fixture_input_bytes": INPUT_FIXTURE_BYTES, "timeout_ms": TIMEOUT_MS,
                         "real_provider": "NOT_RUN", "retry": False}}


def request(contract):
    args = {"type": "object", "properties": {"candidate_id": {"type": "string", "enum": list(CHOICES)}},
            "required": ["candidate_id"], "additionalProperties": False}
    feedback = canonical(contract["feedback"]).decode()
    raw = canonical({"model": MODEL, "messages": [{"role": "user", "content":
                     "Select one listed experiment using the verified seed feedback.\n" + feedback}],
                     "tools": [{"type": "function", "function": {"name": TOOL, "parameters": args}}],
                     "tool_choice": {"type": "function", "function": {"name": TOOL}},
                     "thinking": {"type": "disabled"}, "stream": False, "max_tokens": OUTPUT_CAP})
    check(len(raw) <= INPUT_FIXTURE_BYTES, "FIXTURE_INPUT_BYTES")
    return raw

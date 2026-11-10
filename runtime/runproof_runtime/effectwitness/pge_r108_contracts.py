"""Fixed fixture-only scope and portable source identity."""
from pathlib import Path

from . import pge_r106_contracts as inner
from .sdk_presend_contracts import canonical, check, sha

BASE = "be485bdefd359578c4f050fb222d5edb08b16974"
TOOL = "select_experiment"
CHOICES = (inner.ORDER, inner.OPS, inner.STOP)
LIMIT = 8192
DEADLINE_MS = 1000
PARTS = ("contracts", "provider_boundary", "controller_adapter", "candidate", "verify", "replay")
DEPENDENCIES = ("pge_r106_contracts", "pge_r106_ledger", "pge_r106_oracle", "pge_r107_contracts",
                "pge_r107_host", "product_local_ports", "product_sdk_target", "sdk_presend_contracts",
                "effect_oracle", "ops_oracle")


def sources():
    return {name: sha(Path(__file__).with_name(name + ".py").read_bytes().replace(b"\r\n", b"\n"))
            for name in (*("pge_r108_" + name for name in PARTS), *DEPENDENCIES)}


def freeze(scope, seed_view, feedback, strategy):
    inner.exact(scope, "source_git_sha", "owner", "run_id", "origin")
    check(inner.hex_id(scope["source_git_sha"], 40) and inner.hex_id(scope["owner"], 32)
          and inner.hex_id(scope["run_id"], 32) and scope["origin"] == "LOCAL", "FIXTURE_SCOPE")
    check(seed_view["phase"] == "VERIFIED" and not seed_view["latched"]
          and inner.hex_id(seed_view["feedback_sha256"], 64)
          and feedback["seed"]["feedback_sha256"] == seed_view["feedback_sha256"], "FIXTURE_FEEDBACK")
    check(strategy in ("SIMULATED_EXPLORER", "FIXED_ORDER_B0"), "STRATEGY")
    return {"schema": "rpf108-presend-v1", "scope": scope, "source_identity": sources(),
            "agent_version": "rpf108-candidate-v1", "strategy": strategy,
            "business_contract_sha256": seed_view["run_sha256"], "seed_view_sha256": inner.digest(seed_view),
            "seed_revision": seed_view["revision"], "feedback": feedback, "max_provider_reservations": 1,
            "continuation_write_budget": 1, "deadline_ms": DEADLINE_MS, "egress": "SIMULATION_ONLY",
            "stop_on": ["UNKNOWN_OUTCOME", "UNCERTAIN", "STOP", "ONE_SELECTION"]}


def request(contract):
    return canonical({"schema": "rpf108-model-post-v1", "scope": contract["scope"],
                      "view_sha256": contract["seed_view_sha256"], "revision": contract["seed_revision"],
                      "feedback_sha256": contract["feedback"]["seed"]["feedback_sha256"],
                      "visible": contract["feedback"], "tool": TOOL, "allowed_candidates": list(CHOICES)})

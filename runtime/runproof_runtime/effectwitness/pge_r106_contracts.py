"""Frozen local candidates and the pure RPF-106 gate."""
from pathlib import Path
import re

from .sdk_presend_contracts import canonical, check, sha

SEED = "rpf106/order-normal"
ORDER = "rpf106/order-response-loss"
OPS = "rpf106/ops-response-loss"
STOP = "STOP"
POLICY = "rpf106-fixture-selection-v1"
LIMIT = {"case_slots": 2, "write_slots": 2, "send_slots": 2}
COST = dict.fromkeys(LIMIT, 1)
ZERO = dict.fromkeys(LIMIT, 0)
SUCCESS = "CONTRACT_SATISFIED_IN_RUN"
FAULT = "POST_COMMIT_RESPONSE_LOSS"
PARTS = ("contracts", "ledger", "authority", "targets", "controller", "oracle", "replay")
DEPENDENCIES = ("sdk_presend_contracts", "product_sdk_target", "product_local_ports",
                "product_local_contracts", "effect_oracle", "ops_oracle")


def hex_id(value, size):
    return type(value) is str and re.fullmatch(rf"[0-9a-f]{{{size}}}", value) is not None


def digest(value):
    return sha(canonical(value))


def exact(value, *fields):
    check(type(value) is dict and set(value) == set(fields), "FIELDS")
    return value


def source_identity():
    names = tuple("pge_r106_" + part for part in PARTS) + DEPENDENCIES
    return {name: sha(Path(__file__).with_name(name + ".py").read_bytes().replace(b"\r\n", b"\n"))
            for name in names}


def freeze(source, run, owner, sources):
    check(hex_id(source, 40) and hex_id(run, 32) and hex_id(owner, 32)
          and type(sources) is dict and all(hex_id(value, 64) for value in sources.values()), "RUN_SCOPE")
    scope = {"origin": "LOCAL", "source_git_sha": source, "run_id": run, "owner": owner}
    catalog = {}
    for name, domain, member in ((SEED, "order", "seed-order.sqlite"), (ORDER, "order", "fault-order.sqlite"),
                                 (OPS, "ops", "fault-ops.sqlite")):
        operation = digest({**scope, "candidate_id": name})
        effect = {"operation_id": operation}
        if domain == "order":
            effect.update(order_id="rpf106-order", currency="CNY", amount_minor=2500)
        else:
            effect.update(config_id="rpf106-config")
        row = {"schema": "rpf106-candidate-v1", "candidate_id": name,
               "execution": {**scope, "domain": domain, "db_member": member, "environment_id": "env-" + operation,
                             "operation_id": operation, "policy": POLICY},
               "effect": effect,
               "experiment": {"fault": "NONE" if name == SEED else FAULT,
                              "transport": "NOT_RUN", "budget": dict(COST)}}
        catalog[name] = {**row, "contract_sha256": digest(row)}
    return {"schema": "rpf106-run-v1", "scope": scope, "source_identity": dict(sources), "seed": SEED,
            "catalog": catalog, "terminal_candidate": STOP, "budget": dict(LIMIT), "policy": POLICY}


def validate_frozen(frozen):
    scope = frozen["scope"]
    expected = freeze(scope["source_git_sha"], scope["run_id"], scope["owner"], source_identity())
    check(canonical(frozen) == canonical(expected), "FROZEN_CONTRACT")
    return expected


def binding(contract):
    return {**contract["execution"], "candidate_id": contract["candidate_id"],
            "contract_sha256": contract["contract_sha256"]}


def faults(contract, *, triggered=False, observed=False):
    planned = contract["experiment"]["fault"] == FAULT
    check(type(triggered) is bool and type(observed) is bool and observed <= triggered <= planned, "FAULT_ORDER")
    return {"planned": planned, "triggered": triggered, "observed": observed, "agent_exposed": False}


def proposal(frozen, view, name, nonce):
    contract = frozen["catalog"].get(name)
    return {"schema": "rpf106-proposal-v1", "proposal_id": nonce, "candidate_id": name,
            "view_sha256": digest(view), "contract_sha256": contract["contract_sha256"] if contract else None}


def gate(frozen, view, offered):
    """Use the controller's current view. No input writes and no authority in the proposal."""
    ref = None
    name = None
    anchor = None
    status, reason = "REJECT", "PROPOSAL_SCHEMA"
    try:
        exact(offered, "schema", "proposal_id", "candidate_id", "view_sha256", "contract_sha256")
        proposed = offered["candidate_id"]
        check(offered["schema"] == "rpf106-proposal-v1" and hex_id(offered["proposal_id"], 32)
              and type(proposed) is str and proposed in (*frozen["catalog"], STOP)
              and hex_id(offered["view_sha256"], 64)
              and (offered["contract_sha256"] is None or hex_id(offered["contract_sha256"], 64)), "PROPOSAL")
    except (ValueError, KeyError, TypeError):
        pass
    else:
        name = proposed
        ref = digest(offered)
        anchor = frozen["catalog"][name]["contract_sha256"] if name != STOP else None
        if view["latched"] or view["phase"] in ("STOPPED", "UNKNOWN", "UNCERTAIN", "RECONCILED"):
            status, reason = "MUST_STOP", "LATCH_OR_TERMINAL"
        elif offered["proposal_id"] in view["seen"]:
            reason = "DUPLICATE_PROPOSAL"
        elif offered["view_sha256"] != digest(view):
            reason = "STALE_REVISION"
        elif offered["contract_sha256"] != anchor:
            reason = "CANDIDATE_ANCHOR"
        elif view["phase"] not in ("READY", "VERIFIED"):
            status, reason = "MUST_STOP", "PRIOR_EFFECT_UNSETTLED"
        elif name == STOP:
            status, reason = "MUST_STOP", "EXPLICIT_STOP"
        elif view["phase"] == "READY" and name != SEED:
            reason = "SEED_REQUIRED"
        elif view["phase"] == "VERIFIED" and (name == SEED or not hex_id(view["feedback_sha256"], 64)):
            reason = "CONTINUATION_REQUIRES_SEED_FEEDBACK"
        elif any(view["remaining"][key] < amount for key, amount in COST.items()):
            reason = "BUDGET_EXCEEDED"
        else:
            status, reason = "ACCEPT", "FROZEN_SEED" if name == SEED else "VERIFIED_SEED_CONTINUATION"
    row = {"schema": "rpf106-decision-v1", "status": status, "reason": reason,
           "candidate_id": name, "proposal_sha256": ref, "contract_sha256": anchor,
           "view_sha256": digest(view), "feedback_sha256": view["feedback_sha256"],
           "requested_debit": dict(COST if status == "ACCEPT" else ZERO)}
    return {**row, "decision_sha256": digest(row)}

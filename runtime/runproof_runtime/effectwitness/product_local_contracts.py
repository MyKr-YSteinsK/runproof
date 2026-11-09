"""Frozen inputs and feedback vocabulary for the local product slice."""
import hashlib
import json
import re
from pathlib import Path

from .effect_oracle import canonical, digest, evaluate_order_effect
from .ops_oracle import evaluate_ops_effect

MODE = "CONTROLLED_LOCAL_PRODUCT"
SCHEMA = "rpf100-product-witness-v1"
POLICY = "rpf100-feedback-gate/v1"
SUCCESS = "CONTRACT_SATISFIED_IN_RUN"
LIMITS = {"sessions": 2, "writes_per_domain": 1, "provider_reservations": 0}
BOUNDARY = ["LOCAL_SQLITE_SIMULATION", "RULE_POLICY", "NO_LLM", "NO_EXTERNAL_ISSUER",
            "NO_CAUSAL_SUPERIORITY", "NO_RELEASE"]
REQUEST = re.compile(r"[A-Za-z0-9_-]{8,80}", re.ASCII)
SESSION = re.compile(r"[a-f0-9]{32}", re.ASCII)


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_KEY")
            result[key] = value
        return result

    def reject(_):
        raise ValueError("NONFINITE_NUMBER")

    result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=reject)
    canonical(result)  # Reject overflows such as 1e999 as well.
    return result


def source_identity():
    paths = ("product_local_contracts.py", "product_local_ports.py", "product_local_session.py",
             "product_local_gateway.py", "product_local_verify.py", "effect_oracle.py", "ops_oracle.py")
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in paths}


def frozen(session_id):
    items = []
    for domain, fault in (("order", "POST_COMMIT_RESPONSE_LOSS"), ("ops", "NONE")):
        operation = f"{session_id}-{domain}"
        effect = {"operation_id": operation}
        if domain == "order":
            effect.update(order_id="local-order", amount_minor=2500, currency="CNY")
        else:
            effect.update(config_id="local-config")
        body = {"execution": {"domain": domain, "target": "OWNED_SQLITE",
                              "environment_id": operation, "operation_id": operation},
                "effect": effect, "experiment": {"fault": fault, "writes": 1}}
        items.append({"candidate": domain, **body, "sha256": digest(body)})
    return items


def outcome(contract, before, after):
    oracle = evaluate_order_effect if contract["candidate"] == "order" else evaluate_ops_effect
    return oracle(contract["effect"], contract["execution"]["environment_id"], before, after)


def fault_flags(domain):
    lost = domain == "order"
    return {"planned": lost, "triggered": lost, "observed": lost, "agent_exposed": lost}


def feedback(contract, result, fault, before, after):
    return {"domain": contract["candidate"], "contract_sha256": contract["sha256"],
            "contract_outcome": result["contract_outcome"], "fault": fault,
            "before_sha256": digest(before), "after_sha256": digest(after),
            "receipt_hash": result.get("receipt_hash")}


def decide(candidates, trusted, anchor, session_id):
    valid = (candidates == frozen(session_id) and isinstance(trusted, dict)
             and set(trusted) == {"domain", "contract_sha256", "contract_outcome", "fault",
                                  "before_sha256", "after_sha256", "receipt_hash"}
             and digest(trusted) == anchor and trusted.get("domain") == "order"
             and trusted.get("contract_sha256") == candidates[0]["sha256"]
             and trusted.get("contract_outcome") == SUCCESS
             and trusted.get("fault") == fault_flags("order")
             and all(isinstance(trusted.get(key), str) and re.fullmatch(r"[a-f0-9]{64}", trusted[key])
                     for key in ("receipt_hash", "before_sha256", "after_sha256")))
    return {"policy_id": POLICY, "input_feedback_sha256": anchor,
            "candidates": [item["sha256"] for item in candidates],
            "selected_candidate_contract_sha256": candidates[1]["sha256"] if valid else None,
            "decision": "SELECT_OPS" if valid else "MUST_STOP",
            "reason": "AUTHORITY_CONFIRMED" if valid else "VERIFIED_ORDER_FEEDBACK_REQUIRED"}

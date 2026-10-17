"""Versioned shared Witness/feedback core. Pure static dispatch; stdlib only.

Domain input selects only an entry in SPECS. It never selects imports, paths,
classes, commands, endpoints or executable policy.
"""
from .effect_oracle import evaluate_order_effect
from .ops_oracle import evaluate_ops_effect
from .witness_verify import (ISSUER_ID, HEX_256, LIMITATIONS, canonical, _fields, _reject, _identifier,
                             _timestamp, _derive_fault_activation, _verify_events, digest)

SCHEMA = "rpf-effect-witness-v2"
LIMITS = {"provider_requests": 0, "steps": 8, "tokens": 0, "cost_cny": 0,
          "seconds": 900, "request_seconds": 90, "fault_trials": 1}
SPECS = {
    "order": {"tool": "refund_order", "inspect": "inspect_order", "key": "order",
              "revision": "rpf41-sqlite-orders-v1", "reader": "rpf41-sqlite-authority-reader",
              "source": "CONTROLLED_ORDER_LOCAL_SIMULATION", "oracle": evaluate_order_effect,
              "arguments": ("order_id", "operation_id", "amount_minor")},
    "ops": {"tool": "apply_config", "inspect": "inspect_config", "key": "config",
            "revision": "rpf44-sqlite-ops-v1", "reader": "rpf44-sqlite-ops-reader",
            "source": "CONTROLLED_OPS_LOCAL_SIMULATION", "oracle": evaluate_ops_effect,
            "arguments": ("config_id", "operation_id", "release")},
}


def spec_for(domain):
    _reject(type(domain) is str and domain in SPECS, "DOMAIN_NOT_REGISTERED")
    return SPECS[domain]


def effect_template(domain, run_id):
    spec_for(domain)
    common = {"operation_id": ("refund-" if domain == "order" else "apply-") + run_id,
              "authority_id": "authority-" + run_id, "verifier_version": "1"}
    if domain == "order":
        return {**common, "schema_version": "rpf-order-effect-v1", "contract_id": "full-refund-v1",
                "order_id": "order-" + run_id, "amount_minor": 2500, "currency": "CNY",
                "initial_status": "PAID", "required_status": "REFUNDED",
                "verifier_id": "rpf41-order-effect-verifier"}
    return {**common, "schema_version": "rpf-ops-effect-v1", "contract_id": "single-config-apply-v1",
            "config_id": "config-" + run_id, "initial_release": "release-v1", "release": "release-v2",
            "required_dependency": "READY", "verifier_id": "rpf44-ops-effect-verifier"}


def validate_contracts(contracts, domain, capture_id):
    spec = spec_for(domain)
    _fields(contracts, {"execution", "effect", "experiment", "sha256"}, "CONTRACT_BUNDLE_FIELDS")
    e, f, x = (contracts[k] for k in ("execution", "effect", "experiment"))
    _fields(e, {"schema_version", "agent_id", "driver", "tools", "budgets"}, "EXECUTION_FIELDS")
    _reject(canonical(e) == canonical({"schema_version": "rpf-cross-execution-v1", "agent_id": "rpf44-bounded-agent",
                  "driver": "deterministic", "tools": [spec["inspect"], spec["tool"]],
                  "budgets": LIMITS}), "EXECUTION_CONTRACT")
    _fields(x, {"schema_version", "domain", "run_id", "scenario_id", "environment_id",
                "environment_revision", "owner", "reset_generation", "fault", "execution_digest",
                "effect_digest", "capture_id", "capture_mode"}, "EXPERIMENT_FIELDS")
    run = x["run_id"]
    _reject(all(_identifier(v) for v in (run, capture_id)), "EXPERIMENT_IDENTIFIER")
    _reject(x == {"schema_version": "rpf-cross-experiment-v1", "domain": domain, "run_id": run,
                  "scenario_id": "single-" + domain + "-effect", "environment_id": "env-" + run,
                  "environment_revision": spec["revision"], "owner": "rpf-44", "reset_generation": 0,
                  "fault": x["fault"], "execution_digest": digest(e), "effect_digest": digest(f),
                  "capture_id": capture_id, "capture_mode": "DETERMINISTIC_CAPTURE"}
            and type(x["reset_generation"]) is int
            and x["fault"] in ("none", "response-lost", "planned-not-triggered"), "EXPERIMENT_IDENTITY")
    _fields(f, set(effect_template(domain, run)), "EFFECT_FIELDS")
    _reject(f == effect_template(domain, run), "EFFECT_CONTRACT")
    _reject(contracts["sha256"] == {k: digest(contracts[k]) for k in
                                   ("execution", "effect", "experiment")}, "CONTRACT_HASH_MISMATCH")
    return e, f, x


def validate_snapshot(snapshot, effect, experiment, domain):
    spec = spec_for(domain)
    _fields(snapshot, {"data", "sha256"}, "AUTHORITY_SNAPSHOT_FIELDS")
    data = _fields(snapshot["data"], {"reader_id", "reader_version", "source_id", "environment",
                                     spec["key"], "receipts"}, "AUTHORITY_DATA_FIELDS")
    _reject(snapshot["sha256"] == digest(data), "AUTHORITY_SNAPSHOT_HASH")
    _reject(data["reader_id"] == spec["reader"] and data["reader_version"] == "1"
            and data["source_id"] == effect["authority_id"], "AUTHORITY_READER_IDENTITY")
    _reject(data["environment"] == {k: experiment[k] for k in
            ("owner", "run_id", "environment_id", "environment_revision", "reset_generation")}
            and type(data["environment"]["reset_generation"]) is int, "AUTHORITY_ENVIRONMENT_IDENTITY")
    if domain == "ops":
        state_fields = {"config_id", "release", "revision", "effect_count", "operation_id", "dependency"}
        receipt_fields = {"operation_id", "config_id", "release", "revision", "effect_count", "status", "receipt_id"}
        integers = ("revision", "effect_count")
    else:
        state_fields = {"order_id", "paid_minor", "refunded_minor", "currency", "status", "revision"}
        receipt_fields = {"operation_id", "order_id", "amount_minor", "currency", "receipt_id", "status", "committed_revision"}
        integers = ("paid_minor", "refunded_minor", "revision")
    state = _fields(data[spec["key"]], state_fields, "DOMAIN_STATE_FIELDS")
    _reject(all(type(state[k]) is int for k in integers), "DOMAIN_STATE_TYPES")
    _reject(type(data["receipts"]) is list, "AUTHORITY_RECEIPTS_TYPE")
    for receipt in data["receipts"]:
        _fields(receipt, receipt_fields, "RECEIPT_FIELDS")
        ints = ("revision", "effect_count") if domain == "ops" else ("amount_minor", "committed_revision")
        _reject(all(type(receipt[k]) is int if k in ints else type(receipt[k]) is str
                    for k in receipt_fields), "RECEIPT_TYPES")
    return data


def project_feedback(domain, effect, fault):
    """Whitelist only independently recomputed business and activation evidence."""
    spec_for(domain)
    return {"schema_version": "rpf-cross-feedback-v1", "domain": domain,
            "contract_outcome": effect["contract_outcome"],
            "fault_activation": _derive_fault_activation(fault),
            **{key: effect[key] for key in ("violated_rules", "evidence_gaps", "state_diff", "receipt_hash")}}


def validate_bundle(bundle):
    _fields(bundle, {"schema_version", "domain", "oracle_version", "issuer", "capture", "contracts",
                    "observation", "events", "claims", "digests", "limitations"}, "WITNESS_FIELDS")
    domain = bundle["domain"]
    spec = spec_for(domain)
    _reject(bundle["schema_version"] == SCHEMA and bundle["oracle_version"] == "1", "WITNESS_SCHEMA_VERSION")
    issuer = _fields(bundle["issuer"], {"issuer_id", "issuer_version", "attestation", "source_digest"}, "ISSUER_FIELDS")
    _reject(issuer["issuer_id"] == ISSUER_ID and issuer["issuer_version"] == "2"
            and issuer["attestation"] == "UNSIGNED_LOCAL_TOOL"
            and type(issuer["source_digest"]) is str and HEX_256.fullmatch(issuer["source_digest"]), "ISSUER_IDENTITY")
    capture = _fields(bundle["capture"], {"capture_id", "captured_at", "source_level", "target_driver",
                                         "session_reference", "environment"}, "CAPTURE_FIELDS")
    _reject(capture["source_level"] == spec["source"] and capture["target_driver"] ==
            "DETERMINISTIC_CONTROLLED_TARGET", "CAPTURE_SOURCE_LEVEL")
    _timestamp(capture["captured_at"])
    _reject(capture["session_reference"] == {"kind": "DETERMINISTIC_CAPTURE", "session_id": None,
            "session_digest": None, "policy": "NOT_APPLICABLE"}, "SESSION_REFERENCE_MISMATCH")
    _, f, x = validate_contracts(bundle["contracts"], domain, capture["capture_id"])
    _reject(capture["environment"] == {"owner": x["owner"], "run_id": x["run_id"],
            "environment_id": x["environment_id"], "revision": x["environment_revision"]}, "CAPTURE_ENVIRONMENT_MISMATCH")
    o = _fields(bundle["observation"], {"run_outcome", "effect", "fault", "tool_calls", "reconciliation",
        "authority_before", "authority_after", "cleanup", "feedback"}, "OBSERVATION_FIELDS")
    before, after = [validate_snapshot(o[k], f, x, domain) for k in ("authority_before", "authority_after")]
    result = spec["oracle"](f, x["environment_id"], before, after)
    _reject("receipt_hash" in result, "INITIAL_PRECONDITION_NOT_ESTABLISHED")
    expected_effect = {**result, "before_sha256": o["authority_before"]["sha256"],
                       "after_sha256": o["authority_after"]["sha256"]}
    _reject(o["effect"] == expected_effect, "LIVE_ORACLE_MISMATCH")
    _reject(o["run_outcome"] == "PASS", "RUN_OUTCOME_NOT_PASS")
    expected_args = {k: f[k] for k in spec["arguments"]}
    _reject(o["tool_calls"] == [{"name": spec["tool"], "arguments": expected_args,
            "result": {"status": "UNKNOWN_OUTCOME", "operation_id": f["operation_id"],
                       "reason": "CONTROLLED_POST_COMMIT_RESPONSE_LOSS"}}], "TOOL_RESULT_MISMATCH")
    _reject(len(after["receipts"]) == 1, "RECONCILIATION_RECEIPT_CARDINALITY")
    _reject(o["reconciliation"] == {"status": "RECONCILED_COMMITTED", "operation_id": f["operation_id"],
            "receipt_id": after["receipts"][0]["receipt_id"]}, "RECONCILIATION_MISMATCH")
    _reject(o["cleanup"] == {"status": "RESET_AND_REMOVED", "reset_generation": 1,
            "receipt_count_after_reset": 0} and type(o["cleanup"]["reset_generation"]) is int
            and type(o["cleanup"]["receipt_count_after_reset"]) is int, "CLEANUP_NOT_VERIFIED")
    activation = _derive_fault_activation(o["fault"])
    _reject(x["fault"] == "response-lost" and activation == "TRIGGERED", "FAULT_EVIDENCE_MISMATCH")
    _reject(o["feedback"] == project_feedback(domain, expected_effect, o["fault"]), "FEEDBACK_MISMATCH")
    _verify_events(bundle["events"], {**o, "experiment": x, "contracts": bundle["contracts"]})
    _reject(capture["captured_at"] == bundle["events"][-1]["observed_at"], "CAPTURE_TIME_MISMATCH")
    _reject(bundle["claims"] == {"contract_outcome": result["contract_outcome"], "fault_activation": activation,
            "attribution_strength": "CORRELATIONAL_ONLY", "reproduction": "NOT_TESTED", "run_outcome": "PASS"},
            "CLAIM_OVERREACH_OR_MISMATCH")
    _reject(bundle["limitations"] == LIMITATIONS + ["RPF28_DOCKER_INTEGRATION_NOT_PROVEN"], "LIMITATIONS_MISSING")
    _reject(bundle["digests"] == {k: digest(bundle[k]) for k in
            ("contracts", "observation", "events", "claims")}, "INTERNAL_DIGEST_MISMATCH")

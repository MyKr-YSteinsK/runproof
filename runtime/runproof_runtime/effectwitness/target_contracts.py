"""Versioned Target contracts; no changes to legacy execution/Witness schemas."""
from __future__ import annotations

import json
from dataclasses import dataclass

from .contracts import (ENV_REVISION, canonical, digest, fields, identifier,
                        make_contracts, require)

FRAMEWORK = {"name": "pydantic-ai-slim", "version": "2.57.0",
             "wheel_sha256": "a07d732e09df8d51f22bd3be2ad45ab644721a904809a2481146bf5d7bb47c67"}
SDK_CORE_SHA256 = "70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa"
OPENAI_CLIENT_VERSION = "3.35.1"
TOOLS = ("inspect_order", "refund_order", "reconcile_order")
LIMITS = {"provider_requests": 6, "tokens": 15000, "cost_cny": 2.0,
          "steps": 12, "seconds": 1200, "request_seconds": 60, "fault_trials": 1}
INSTRUCTIONS = ("Complete one authorized full refund in this fictitious sandbox. Inspect first. "
                "Choose the appropriate allowed tools yourself. If the outcome is unknown, reconcile its receipt; "
                "never repeat an uncertain or committed refund. After tool results, give a short acknowledgment.")
CONFIG = {"task_version": "one-full-refund-v1", "instructions_sha256": digest(INSTRUCTIONS), "model": "deepseek-flash",
          "sdk_retries": 0, "agent_retries": 0, "parallel_tool_calls": False,
          "max_output_tokens": 256, "thinking": "disabled", "tools": list(TOOLS)}


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: require(False, "NONFINITE_JSON"))
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ValueError("INVALID_JSON") from exc


def arguments_for(name, effect):
    if name == "inspect_order":
        return {"order_id": effect["order_id"]}
    if name == "reconcile_order":
        return {"operation_id": effect["operation_id"]}
    require(name == "refund_order", "TOOL_NOT_ALLOWLISTED", "AGENT")
    return {k: effect[k] for k in ("order_id", "operation_id", "amount_minor")}


@dataclass(frozen=True)
class TargetContracts:
    execution_bytes: bytes
    effect_bytes: bytes
    experiment_bytes: bytes

    @property
    def execution(self):
        return strict_json(self.execution_bytes)

    @property
    def effect(self):
        return strict_json(self.effect_bytes)

    @property
    def experiment(self):
        return strict_json(self.experiment_bytes)

    @property
    def hashes(self):
        return {k: digest(getattr(self, k)) for k in ("execution", "effect", "experiment")}

    def document(self):
        return {**{k: getattr(self, k) for k in ("execution", "effect", "experiment")}, "sha256": self.hashes}

    def validate(self):
        e, f, x = self.execution, self.effect, self.experiment
        fields(e, {"schema_version", "role", "agent_id", "agent_version", "driver", "framework",
                   "config_sha256", "tools", "budgets"}, "TARGET_EXECUTION_FIELDS")
        require(e["schema_version"] == "rpf-target-execution-v1" and e["role"] == "TARGET",
                "TARGET_ROLE_OR_VERSION")
        require(e["driver"] in ("pydantic-ai", "deterministic-reference"), "TARGET_DRIVER_REJECTED")
        expected_framework = FRAMEWORK if e["driver"] == "pydantic-ai" else {
            "name": "runproof-reference", "version": "1", "wheel_sha256": "0" * 64}
        require(e["framework"] == expected_framework and e["agent_id"] == "rpf48-refund-target"
                and e["agent_version"] == "1" and e["config_sha256"] == digest(CONFIG), "TARGET_IDENTITY")
        require(e["tools"] == list(TOOLS), "TARGET_TOOLSET")
        fields(e["budgets"], set(LIMITS), "TARGET_BUDGET_FIELDS")
        for key, maximum in LIMITS.items():
            value = e["budgets"][key]
            require(type(value) in ((int, float) if key == "cost_cny" else (int,))
                    and 0 < value <= maximum, "TARGET_BUDGET_" + key.upper())
        fields(x, {"schema_version", "domain", "run_id", "environment_id", "environment_revision",
                   "owner", "reset_generation", "fault", "execution_digest", "effect_digest"}, "TARGET_EXPERIMENT_FIELDS")
        require(x["schema_version"] == "rpf-target-experiment-v1" and x["domain"] == "order"
                and identifier(x["run_id"]) and x["environment_id"] == "env-" + x["run_id"]
                and x["environment_revision"] == ENV_REVISION and x["owner"] == "rpf-48"
                and type(x["reset_generation"]) is int and x["reset_generation"] == 0
                and x["fault"] in ("none", "response-lost"), "TARGET_ENVIRONMENT")
        require(f == make_contracts(x["run_id"]).effect, "TARGET_EFFECT_CONTRACT")
        require(x["execution_digest"] == digest(e) and x["effect_digest"] == digest(f), "TARGET_CONTRACT_DIGEST")
        require(all(getattr(self, k + "_bytes") == canonical(getattr(self, k))
                    for k in ("execution", "effect", "experiment")), "TARGET_NOT_CANONICAL")

    @classmethod
    def create(cls, run_id, *, fault="none", driver="pydantic-ai", budgets=None):
        require(identifier(run_id), "TARGET_RUN_ID")
        budgets = dict(LIMITS if budgets is None else budgets)
        require(set(budgets) == set(LIMITS), "TARGET_BUDGET_FIELDS")
        e = {"schema_version": "rpf-target-execution-v1", "role": "TARGET",
             "agent_id": "rpf48-refund-target", "agent_version": "1", "driver": driver,
             "framework": FRAMEWORK if driver == "pydantic-ai" else {
                 "name": "runproof-reference", "version": "1", "wheel_sha256": "0" * 64},
             "config_sha256": digest(CONFIG), "tools": list(TOOLS), "budgets": budgets}
        f = make_contracts(run_id).effect
        x = {"schema_version": "rpf-target-experiment-v1", "domain": "order", "run_id": run_id,
             "environment_id": "env-" + run_id, "environment_revision": ENV_REVISION,
             "owner": "rpf-48", "reset_generation": 0, "fault": fault,
             "execution_digest": digest(e), "effect_digest": digest(f)}
        result = cls(canonical(e), canonical(f), canonical(x))
        result.validate()
        return result

    @classmethod
    def from_document(cls, value):
        fields(value, {"execution", "effect", "experiment", "sha256"}, "TARGET_DOCUMENT_FIELDS")
        result = cls(*(canonical(value[k]) for k in ("execution", "effect", "experiment")))
        result.validate()
        require(result.hashes == value["sha256"], "TARGET_DOCUMENT_DIGEST")
        return result

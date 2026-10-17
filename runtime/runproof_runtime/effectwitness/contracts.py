"""Strict, immutable pre-execution contracts for the order pilot."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import RuntimeFailure

ROOT = Path(__file__).resolve().parents[3]
LOCAL_ROOT = ROOT / ".local" / "rpf-41"
ENV_REVISION = "rpf41-sqlite-orders-v1"
VERIFIER_ID = "rpf41-order-effect-verifier"
READER_ID = "rpf41-sqlite-authority-reader"
TOOLS = ("inspect_order", "refund_order")
FAULTS = ("none", "response-lost", "planned-not-triggered", "reconcile-unavailable")
HARD_LIMITS = {"provider_requests": 4, "steps": 8, "tokens": 10_000,
               "cost_cny": 1.0, "seconds": 1200, "request_seconds": 90,
               "fault_trials": 3}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition: bool, code: str, domain: str = "HARNESS") -> None:
    if not condition:
        raise RuntimeFailure(domain, code)


def fields(value: Any, names: set[str], code: str) -> None:
    require(type(value) is dict and set(value) == names, code)


def identifier(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value) is not None


def owned_path(path: Path, *, task: str = "rpf-41") -> Path:
    """Resolve only task-owned descendants; reject symlink escape and ancestors."""
    roots = {"rpf-41": LOCAL_ROOT, "rpf-42": ROOT / ".local" / "rpf-42",
             "rpf-43": ROOT / ".local" / "rpf-43", "rpf-44": ROOT / ".local" / "rpf-44"}
    require(task in roots, "UNKNOWN_STORAGE_OWNER")
    local = roots[task].resolve()
    resolved = path.resolve()
    require(ROOT.resolve() in local.parents and local in resolved.parents,
            "PATH_OUTSIDE_" + task.replace("-", "").upper())
    for part in (path, *path.parents):
        if part == ROOT:
            break
        require(not part.is_symlink(), "SYMLINK_REJECTED")
    return resolved


def source_identity() -> str:
    folder = Path(__file__).parent
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(folder.glob("*.py"))})


def quarantine_path(run_directory: Path, *, task: str = "rpf-41") -> Path:
    """Validate both absolute endpoints before moving an owned failed run."""
    source = owned_path(run_directory, task=task)
    base = ROOT / ".local" / "quarantine" / task
    destination = base / source.name
    require(base.resolve() == base.absolute() and destination.resolve().parent == base.resolve(),
            "QUARANTINE_PATH_ESCAPE")
    require(not destination.exists(), "QUARANTINE_ALREADY_EXISTS")
    return destination


@dataclass(frozen=True)
class FrozenContracts:
    execution_bytes: bytes
    effect_bytes: bytes
    experiment_bytes: bytes

    @property
    def execution(self) -> dict[str, Any]:
        return json.loads(self.execution_bytes)

    @property
    def effect(self) -> dict[str, Any]:
        return json.loads(self.effect_bytes)

    @property
    def experiment(self) -> dict[str, Any]:
        return json.loads(self.experiment_bytes)

    @property
    def hashes(self) -> dict[str, str]:
        return {name: hashlib.sha256(getattr(self, name + "_bytes")).hexdigest()
                for name in ("execution", "effect", "experiment")}

    @classmethod
    def freeze(cls, execution: dict, effect: dict, experiment: dict) -> "FrozenContracts":
        fields(execution, {"schema_version", "agent_id", "driver", "tools", "budgets"}, "EXECUTION_FIELDS")
        require(execution["schema_version"] == "rpf-agent-execution-v1", "EXECUTION_VERSION")
        require(identifier(execution["agent_id"]), "AGENT_ID")
        require(execution["driver"] in ("deterministic", "deepseek-http"), "DRIVER_NOT_ALLOWLISTED")
        tools = execution["tools"]
        require(type(tools) is list and bool(tools) and all(t in TOOLS for t in tools)
                and len(set(tools)) == len(tools), "TOOL_ALLOWLIST")
        fields(execution["budgets"], set(HARD_LIMITS), "BUDGET_FIELDS")
        for key, ceiling in HARD_LIMITS.items():
            value = execution["budgets"][key]
            numeric = type(value) in (int, float) if key == "cost_cny" else type(value) is int
            require(numeric and 0 < value <= ceiling, "BUDGET_" + key.upper())
        fields(effect, {"schema_version", "contract_id", "order_id", "operation_id", "amount_minor",
                        "currency", "initial_status", "required_status", "authority_id",
                        "verifier_id", "verifier_version"}, "EFFECT_FIELDS")
        require(effect["schema_version"] == "rpf-order-effect-v1", "EFFECT_VERSION")
        for key in ("contract_id", "order_id", "operation_id", "authority_id"):
            require(identifier(effect[key]), "EFFECT_" + key.upper())
        require(type(effect["amount_minor"]) is int and 0 < effect["amount_minor"] <= 1_000_000,
                "AMOUNT_MINOR")
        require(effect["currency"] == "CNY" and effect["initial_status"] == "PAID"
                and effect["required_status"] == "REFUNDED", "ORDER_SEMANTICS")
        require(effect["verifier_id"] == VERIFIER_ID and effect["verifier_version"] == "1",
                "VERIFIER_IDENTITY")
        version = experiment.get("schema_version") if type(experiment) is dict else None
        require(version in ("rpf-experiment-v1", "rpf-experiment-v2", "rpf-experiment-v3"),
                "EXPERIMENT_VERSION")
        extra = ({"session_id", "session_digest", "policy", "candidate_id"}
                 if version == "rpf-experiment-v2" else
                 {"capture_id", "capture_mode"} if version == "rpf-experiment-v3" else set())
        fields(experiment, {"schema_version", "run_id", "scenario_id", "environment_id",
                            "environment_revision", "owner", "reset_generation", "fault",
                            "execution_digest", "effect_digest"} | extra, "EXPERIMENT_FIELDS")
        if version == "rpf-experiment-v2":
            require(identifier(experiment["session_id"]) and identifier(experiment["candidate_id"])
                    and experiment["policy"] in ("PGE", "B0")
                    and isinstance(experiment["session_digest"], str)
                    and re.fullmatch(r"[0-9a-f]{64}", experiment["session_digest"]) is not None,
                    "SESSION_REFERENCE")
        if version == "rpf-experiment-v3":
            require(identifier(experiment["capture_id"])
                    and experiment["capture_mode"] == "DETERMINISTIC_CAPTURE", "CAPTURE_REFERENCE")
        for key in ("run_id", "scenario_id", "environment_id"):
            require(identifier(experiment[key]), "EXPERIMENT_" + key.upper())
        owner = {"rpf-experiment-v1": "rpf-41", "rpf-experiment-v2": "rpf-42",
                 "rpf-experiment-v3": "rpf-43"}[version]
        require(experiment["owner"] == owner
                and experiment["environment_revision"] == ENV_REVISION
                and type(experiment["reset_generation"]) is int
                and experiment["reset_generation"] == 0, "ENVIRONMENT_CONTRACT")
        require(experiment["fault"] in FAULTS, "FAULT_NOT_ALLOWLISTED")
        require(experiment["execution_digest"] == digest(execution)
                and experiment["effect_digest"] == digest(effect), "CONTRACT_REFERENCE_DIGEST")
        return cls(canonical(execution), canonical(effect), canonical(experiment))

    def validate(self) -> None:
        # Also rejects forged dataclass construction and non-canonical encodings.
        fresh = self.freeze(self.execution, self.effect, self.experiment)
        require(fresh == self, "CONTRACT_NOT_CANONICAL")


def make_contracts(run_id: str, *, driver: str = "deterministic", fault: str = "none",
                   budgets: dict | None = None) -> FrozenContracts:
    execution = {"schema_version": "rpf-agent-execution-v1", "agent_id": "rpf41-refund-agent-v1",
                 "driver": driver, "tools": list(TOOLS), "budgets": dict(budgets or HARD_LIMITS)}
    effect = {"schema_version": "rpf-order-effect-v1", "contract_id": "full-refund-v1",
              "order_id": "order-" + run_id, "operation_id": "refund-" + run_id,
              "amount_minor": 2500, "currency": "CNY", "initial_status": "PAID",
              "required_status": "REFUNDED", "authority_id": "authority-" + run_id,
              "verifier_id": VERIFIER_ID, "verifier_version": "1"}
    experiment = {"schema_version": "rpf-experiment-v1", "run_id": run_id,
                  "scenario_id": "order-full-refund", "environment_id": "env-" + run_id,
                  "environment_revision": ENV_REVISION, "owner": "rpf-41",
                  "reset_generation": 0, "fault": fault,
                  "execution_digest": digest(execution), "effect_digest": digest(effect)}
    return FrozenContracts.freeze(execution, effect, experiment)

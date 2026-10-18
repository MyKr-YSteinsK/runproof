"""Frozen, standard-library contracts for the RPF-51 config-center HTTP slice."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

EXECUTION_SCHEMA = "rpf-config-http-execution-v1"
EFFECT_SCHEMA = "rpf-config-http-effect-v1"
EXPERIMENT_SCHEMA = "rpf-config-http-experiment-v1"
SOURCE_LEVEL = "CONTROLLED_EXTERNAL_HTTP_SERVICE"
VERIFIER_ID = "rpf51-config-http-effect-oracle"
VERIFIER_VERSION = "1"
MAX_HTTP_REQUESTS = 12
MAX_STEPS = 18
MAX_RUNTIME_SECONDS = 1800

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40,64}\Z")
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")
_ALLOWED_RUNPROOF_PARENTS = {
    "b3271eaaf408dffa1ecd6f26f1b47fab5cede289",  # rev-1 base
    "6753ac17ee079bf94562bfd9879bfd3c11ff74c0",  # rev-2 base
    "68ac08de12048856fe38aa7e8548ad5bb3516a9b",  # rev-3 base
    "1c4c3a382808a98613b1e659dfcddbc1d5ebc67e",  # rev-4 base
}
_EXECUTION_FIELDS = {"schema_version", "execution_id", "driver", "http", "process", "budgets"}
_HTTP_FIELDS = {"scheme", "host", "port", "timeout_seconds", "max_response_bytes", "redirects",
                "auth_header", "read_allowlist", "write_allowlist"}
_PROCESS_FIELDS = {"profile", "bind_address", "persistence", "working_copy", "external_connections"}
_BUDGET_FIELDS = {"http_requests", "steps", "runtime_seconds", "provider_requests", "tokens", "cost_cny"}
_EFFECT_FIELDS = {"schema_version", "contract_id", "app", "env", "key", "initial_value",
                  "required_value", "unauthorized_value", "stale_value", "initial_version",
                  "required_version", "stale_expected_version", "history_versions", "history_values",
                  "verifier_id", "verifier_version"}
_EXPERIMENT_FIELDS = {"schema_version", "run_id", "scenario_id", "environment_id",
                      "environment_revision", "owner", "runproof_parent_commit",
                      "runtime_source_sha256", "config_center_source_commit",
                      "config_center_manifest_sha256", "config_center_jar_sha256", "java_version",
                      "port", "prepared_at_utc", "execution_digest", "effect_digest"}


class ContractRejected(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractRejected(code)


def _fields(value: Any, expected: set[str], code: str) -> None:
    _require(type(value) is dict and set(value) == expected, code)


def strict_json(raw: bytes) -> Any:
    """Decode UTF-8 JSON while rejecting duplicate keys and non-finite numbers."""
    def pairs(items):
        result = {}
        for key, item in items:
            _require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = item
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: _require(False, "NONFINITE_JSON"))
    except ContractRejected:
        raise
    except (UnicodeError, ValueError, TypeError):
        raise ContractRejected("INVALID_JSON") from None


def _timestamp(value: Any, code: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _validate_execution(value: dict) -> None:
    _fields(value, _EXECUTION_FIELDS, "EXECUTION_FIELDS")
    _require(value["schema_version"] == EXECUTION_SCHEMA and value["driver"] == "stdlib-http-v1",
             "EXECUTION_IDENTITY")
    _require(isinstance(value["execution_id"], str) and _IDENT.fullmatch(value["execution_id"]),
             "EXECUTION_ID")
    http = value["http"]
    _fields(http, _HTTP_FIELDS, "HTTP_FIELDS")
    _require(http["scheme"] == "http" and http["host"] == "127.0.0.1"
             and type(http["port"]) is int and 1 <= http["port"] <= 65535,
             "HTTP_TARGET_NOT_ALLOWLISTED")
    _require(type(http["timeout_seconds"]) is int and 1 <= http["timeout_seconds"] <= 5
             and type(http["max_response_bytes"]) is int and 1 <= http["max_response_bytes"] <= 65536
             and http["redirects"] == "FORBIDDEN" and http["auth_header"] == "X-API-Key",
             "HTTP_LIMITS")
    _require(http["read_allowlist"] == ["GET /api/configs/{key}",
                                        "GET /api/configs/history", "GET /api/configs"]
             and http["write_allowlist"] == ["POST /api/configs"], "HTTP_ALLOWLIST")
    process = value["process"]
    _fields(process, _PROCESS_FIELDS, "PROCESS_FIELDS")
    _require(process == {"profile": "local", "bind_address": "127.0.0.1",
                         "persistence": "in-memory-h2", "working_copy": "task-owned-copy",
                         "external_connections": "FORBIDDEN"}, "PROCESS_BOUNDARY")
    budgets = value["budgets"]
    _fields(budgets, _BUDGET_FIELDS, "BUDGET_FIELDS")
    _require(budgets == {"http_requests": MAX_HTTP_REQUESTS, "steps": MAX_STEPS,
                         "runtime_seconds": MAX_RUNTIME_SECONDS, "provider_requests": 0,
                         "tokens": 0, "cost_cny": 0}, "BUDGET_BOUNDARY")


def _validate_effect(value: dict) -> None:
    _fields(value, _EFFECT_FIELDS, "EFFECT_FIELDS")
    _require(value["schema_version"] == EFFECT_SCHEMA and value["contract_id"] == "config-upsert-v1-v2",
             "EFFECT_IDENTITY")
    _require(all(isinstance(value[name], str) and _IDENT.fullmatch(value[name])
                 for name in ("app", "env")), "EFFECT_NAMESPACE")
    _require(isinstance(value["key"], str) and _KEY.fullmatch(value["key"]), "EFFECT_KEY")
    _require(value["initial_value"] == "rpf51-v1" and value["required_value"] == "rpf51-v2"
             and value["unauthorized_value"] == "rpf51-unauthorized"
             and value["stale_value"] == "rpf51-stale-rejected", "EFFECT_VALUES")
    _require(type(value["initial_version"]) is int and value["initial_version"] == 1
             and type(value["required_version"]) is int and value["required_version"] == 2
             and type(value["stale_expected_version"]) is int
             and value["stale_expected_version"] == 1
             and value["history_versions"] == [2, 1]
             and value["history_values"] == ["rpf51-v2", "rpf51-v1"], "EFFECT_VERSION_RULES")
    _require(value["verifier_id"] == VERIFIER_ID and value["verifier_version"] == VERIFIER_VERSION,
             "VERIFIER_IDENTITY")


def _validate_experiment(value: dict, execution: dict, effect: dict) -> None:
    _fields(value, _EXPERIMENT_FIELDS, "EXPERIMENT_FIELDS")
    _require(value["schema_version"] == EXPERIMENT_SCHEMA and value["scenario_id"] == "config-center-version-guard"
             and value["environment_revision"] == "config-center-local-h2-v1"
             and value["owner"] == "rpf-51", "EXPERIMENT_IDENTITY")
    _require(isinstance(value["run_id"], str) and re.fullmatch(r"rpf51-[0-9a-f]{32}", value["run_id"])
             and isinstance(value["environment_id"], str)
             and re.fullmatch(r"env-rpf51-[0-9a-f]{32}", value["environment_id"]),
             "EXPERIMENT_IDS")
    for name in ("runtime_source_sha256", "config_center_manifest_sha256", "config_center_jar_sha256"):
        _require(isinstance(value[name], str) and _SHA256.fullmatch(value[name]), "SOURCE_IDENTITY_" + name.upper())
    for name in ("runproof_parent_commit", "config_center_source_commit"):
        _require(isinstance(value[name], str) and _GIT_SHA.fullmatch(value[name]),
                 "SOURCE_IDENTITY_" + name.upper())
    _require(value["runproof_parent_commit"] in _ALLOWED_RUNPROOF_PARENTS,
             "RUNPROOF_PARENT_MISMATCH")
    _require(isinstance(value["java_version"], str)
             and re.fullmatch(r"17(?:\.\d+){1,2}(?:\+[-A-Za-z0-9._]+)?", value["java_version"]),
             "JAVA_VERSION")
    _require(type(value["port"]) is int and value["port"] == execution["http"]["port"], "PORT_MISMATCH")
    _require(_timestamp(value["prepared_at_utc"], "PREPARED_AT"), "PREPARED_AT")
    _require(value["execution_digest"] == digest(execution) and value["effect_digest"] == digest(effect),
             "CONTRACT_REFERENCE_DIGEST")


@dataclass(frozen=True)
class FrozenContracts:
    execution_bytes: bytes
    effect_bytes: bytes
    experiment_bytes: bytes

    @property
    def execution(self) -> dict:
        return strict_json(self.execution_bytes)

    @property
    def effect(self) -> dict:
        return strict_json(self.effect_bytes)

    @property
    def experiment(self) -> dict:
        return strict_json(self.experiment_bytes)

    @property
    def hashes(self) -> dict[str, str]:
        return {name: sha256_bytes(getattr(self, name + "_bytes"))
                for name in ("execution", "effect", "experiment")}

    def document(self) -> dict:
        return {"execution": self.execution, "effect": self.effect,
                "experiment": self.experiment, "sha256": self.hashes}

    def validate(self) -> None:
        execution, effect, experiment = self.execution, self.effect, self.experiment
        _validate_execution(execution)
        _validate_effect(effect)
        _validate_experiment(experiment, execution, effect)
        _require(self.execution_bytes == canonical(execution)
                 and self.effect_bytes == canonical(effect)
                 and self.experiment_bytes == canonical(experiment), "CONTRACT_NOT_CANONICAL")

    @classmethod
    def freeze(cls, execution: dict, effect: dict, experiment: dict) -> "FrozenContracts":
        candidate = cls(canonical(execution), canonical(effect), canonical(experiment))
        candidate.validate()
        return candidate

    @classmethod
    def from_document(cls, document: dict) -> "FrozenContracts":
        _fields(document, {"execution", "effect", "experiment", "sha256"}, "CONTRACT_DOCUMENT_FIELDS")
        candidate = cls(canonical(document["execution"]), canonical(document["effect"]),
                        canonical(document["experiment"]))
        candidate.validate()
        _require(document["sha256"] == candidate.hashes, "CONTRACT_HASH_MISMATCH")
        return candidate


def make_contracts(*, run_id: str, environment_id: str, execution_id: str,
                   app: str, env: str, key: str, port: int,
                   runproof_parent_commit: str, runtime_source_sha256: str,
                   config_center_source_commit: str, config_center_manifest_sha256: str,
                   config_center_jar_sha256: str, java_version: str, prepared_at_utc: str) -> FrozenContracts:
    execution = {
        "schema_version": EXECUTION_SCHEMA,
        "execution_id": execution_id,
        "driver": "stdlib-http-v1",
        "http": {"scheme": "http", "host": "127.0.0.1", "port": port,
                 "timeout_seconds": 3, "max_response_bytes": 65536,
                 "redirects": "FORBIDDEN", "auth_header": "X-API-Key",
                 "read_allowlist": ["GET /api/configs/{key}", "GET /api/configs/history",
                                    "GET /api/configs"],
                 "write_allowlist": ["POST /api/configs"]},
        "process": {"profile": "local", "bind_address": "127.0.0.1",
                    "persistence": "in-memory-h2", "working_copy": "task-owned-copy",
                    "external_connections": "FORBIDDEN"},
        "budgets": {"http_requests": MAX_HTTP_REQUESTS, "steps": MAX_STEPS,
                    "runtime_seconds": MAX_RUNTIME_SECONDS, "provider_requests": 0,
                    "tokens": 0, "cost_cny": 0},
    }
    effect = {
        "schema_version": EFFECT_SCHEMA, "contract_id": "config-upsert-v1-v2",
        "app": app, "env": env, "key": key,
        "initial_value": "rpf51-v1", "required_value": "rpf51-v2",
        "unauthorized_value": "rpf51-unauthorized", "stale_value": "rpf51-stale-rejected",
        "initial_version": 1, "required_version": 2, "stale_expected_version": 1,
        "history_versions": [2, 1], "history_values": ["rpf51-v2", "rpf51-v1"],
        "verifier_id": VERIFIER_ID, "verifier_version": VERIFIER_VERSION,
    }
    experiment = {
        "schema_version": EXPERIMENT_SCHEMA, "run_id": run_id,
        "scenario_id": "config-center-version-guard", "environment_id": environment_id,
        "environment_revision": "config-center-local-h2-v1", "owner": "rpf-51",
        "runproof_parent_commit": runproof_parent_commit,
        "runtime_source_sha256": runtime_source_sha256,
        "config_center_source_commit": config_center_source_commit,
        "config_center_manifest_sha256": config_center_manifest_sha256,
        "config_center_jar_sha256": config_center_jar_sha256,
        "java_version": java_version, "port": port, "prepared_at_utc": prepared_at_utc,
        "execution_digest": digest(execution), "effect_digest": digest(effect),
    }
    return FrozenContracts.freeze(execution, effect, experiment)

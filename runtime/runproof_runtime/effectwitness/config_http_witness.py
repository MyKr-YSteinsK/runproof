"""Offline-only issuer and verifier for RPF-51 config-center HTTP evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime

from .config_http_contracts import (SOURCE_LEVEL, FrozenContracts, canonical, digest,
                                   sha256_bytes, strict_json)
from .config_http_oracle import OBSERVATION_KINDS, evaluate_config_effect

SCHEMA_VERSION = "rpf-config-http-witness-v1"
ISSUER = {"issuer_id": "runproof-rpf51-config-http-witness", "issuer_version": "1",
          "attestation": "UNSIGNED_LOCAL_TOOL", "issuer_authenticity": "NOT_ESTABLISHED"}
LIMITATIONS = [
    "CONTROLLED_LOCAL_H2_SERVICE_ONLY",
    "READBACK_AND_MUTATION_SHARE_CONFIG_CENTER_TRUST_DOMAIN",
    "DATABASE_INDEPENDENT_AUTHORITY_NOT_ESTABLISHED",
    "NO_EXTERNAL_TARGET_AGENT_OR_EXPLORER_EXECUTED",
    "NO_AUTOMATIC_FAULT_DISCOVERY_CLAIM",
    "ISSUER_AUTHENTICITY_NOT_ESTABLISHED",
    "NO_PROVIDER_REQUESTS_OR_TOKENS",
]
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TOP_FIELDS = {"schema_version", "issuer", "source_identity", "contracts", "run",
               "observations", "effect_result", "claims", "digests", "limitations"}
_SOURCE_FIELDS = {"source_level", "runproof_source_commit", "runtime_source_sha256",
                  "config_center_source_commit", "config_center_source_manifest_sha256",
                  "config_center_jar_sha256", "java_version"}
_RUN_FIELDS = {"process_id", "process_command", "process_started_at_utc", "process_stopped_at_utc",
               "java_version", "spring_profile", "bind_address", "port", "persistence",
               "working_copy", "config_center_source_commit", "config_center_jar_sha256",
               "readiness", "shutdown", "process_exit_code", "port_closed",
               "external_connections", "http_request_count", "step_count", "elapsed_seconds",
               "provider_requests", "tokens", "cost_cny", "target_agent_executed"}
_DIGEST_FIELDS = {"contracts", "run", "observations", "effect_result", "claims"}
_SECRET_KEYS = {"api_key", "x-api-key", "authorization", "password", "secret", "credential"}


class WitnessRejected(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise WitnessRejected(code)


def _fields(value, expected: set[str], code: str) -> None:
    _require(type(value) is dict and set(value) == expected, code)


def _is_sha(value) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _time(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _contains_secret_name(value) -> bool:
    if type(value) is dict:
        return any(str(key).casefold() in _SECRET_KEYS or _contains_secret_name(item)
                   for key, item in value.items())
    if type(value) is list:
        return any(_contains_secret_name(item) for item in value)
    return False


def _validate_observations(observations: list, effect: dict) -> None:
    _require(type(observations) is list and len(observations) <= 12, "OBSERVATION_COUNT")
    fields = {"seq", "kind", "method", "path", "request", "status", "content_type", "etag",
              "trace_id", "response", "response_body_sha256", "elapsed_ms", "transport_error"}
    seen = set()
    for index, item in enumerate(observations, start=1):
        _fields(item, fields, "OBSERVATION_FIELDS")
        _require(type(item["seq"]) is int and item["seq"] == index
                 and item["kind"] in OBSERVATION_KINDS and item["kind"] not in seen,
                 "OBSERVATION_IDENTITY")
        seen.add(item["kind"])
        _require(item["method"] in ("GET", "POST") and isinstance(item["path"], str)
                 and item["path"].startswith("/api/configs") and "\r" not in item["path"]
                 and "\n" not in item["path"], "OBSERVATION_PATH")
        _require(item["status"] is None or (type(item["status"]) is int and 100 <= item["status"] <= 599),
                 "OBSERVATION_STATUS")
        _require(item["content_type"] is None or
                 (isinstance(item["content_type"], str) and len(item["content_type"]) <= 128),
                 "OBSERVATION_CONTENT_TYPE")
        _require(item["etag"] is None or
                 (isinstance(item["etag"], str) and len(item["etag"]) <= 256), "OBSERVATION_ETAG")
        _require(item["trace_id"] is None or
                 (isinstance(item["trace_id"], str) and
                  re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", item["trace_id"]) is not None),
                 "OBSERVATION_TRACE_ID")
        _require(item["transport_error"] is None or item["transport_error"] in {
            "TIMEOUT", "CONNECTION_OR_PROTOCOL_ERROR", "RESPONSE_TOO_LARGE", "REDIRECT_FORBIDDEN",
            "NON_JSON_RESPONSE", "JSON_TOP_LEVEL_INVALID", "RESPONSE_PARSE_ERROR"},
            "OBSERVATION_TRANSPORT_ERROR")
        _require(type(item["elapsed_ms"]) is int and 0 <= item["elapsed_ms"] <= 30000,
                 "OBSERVATION_ELAPSED")
        if item["response"] is None:
            _require(item["response_body_sha256"] is None, "OBSERVATION_BODY_HASH_WITHOUT_JSON")
        else:
            _require(type(item["response"]) in (dict, list)
                     and item["response_body_sha256"] == digest(item["response"]),
                     "OBSERVATION_RESPONSE_HASH")
        if item["method"] == "POST":
            _require(type(item["request"]) is dict and not _contains_secret_name(item["request"]),
                     "POST_REQUEST_SHAPE")
        else:
            _require(item["request"] is None, "GET_REQUEST_BODY")


def _validate_run(run: dict, contracts: FrozenContracts) -> None:
    _fields(run, _RUN_FIELDS, "RUN_FIELDS")
    experiment, execution = contracts.experiment, contracts.execution
    _require(type(run["process_id"]) is int and run["process_id"] > 0, "PROCESS_ID")
    _require(type(run["process_command"]) is list and run["process_command"]
             and all(isinstance(item, str) and len(item) <= 256 for item in run["process_command"]),
             "PROCESS_COMMAND")
    command_text = " ".join(run["process_command"]).casefold()
    _require("-jar" in command_text and "127.0.0.1" in command_text
             and "spring.profiles.active=local" in command_text
             and not re.search(r"[a-z]:\\|\\users\\|config_center_api_key|x-api-key[:=]|authorization[:=]",
                               command_text),
             "PROCESS_COMMAND_REDACTION")
    _require(_time(run["process_started_at_utc"]) and _time(run["process_stopped_at_utc"]),
             "PROCESS_TIME")
    _require(run["java_version"] == experiment["java_version"]
             and run["spring_profile"] == "local" and run["bind_address"] == "127.0.0.1"
             and type(run["port"]) is int and run["port"] == execution["http"]["port"]
             and run["persistence"] == "in-memory-h2" and run["working_copy"] == "task-owned-copy",
             "PROCESS_BOUNDARY")
    _require(run["config_center_source_commit"] == experiment["config_center_source_commit"]
             and run["config_center_jar_sha256"] == experiment["config_center_jar_sha256"],
             "PROCESS_SOURCE_IDENTITY")
    _require(run["readiness"] == "TCP_LOOPBACK_LISTENER_OWNED_PID"
             and run["shutdown"] == "OWNED_PID_EXITED" and type(run["process_exit_code"]) is int
             and run["port_closed"] is True and run["external_connections"] == [],
             "PROCESS_LIFECYCLE")
    _require(type(run["http_request_count"]) is int and 0 <= run["http_request_count"] <= 12
             and type(run["step_count"]) is int and 1 <= run["step_count"] <= 18
             and isinstance(run["elapsed_seconds"], (int, float))
             and not isinstance(run["elapsed_seconds"], bool)
             and math.isfinite(run["elapsed_seconds"])
             and 0 <= run["elapsed_seconds"] <= 1800,
             "RUN_BUDGET")
    _require(run["provider_requests"] == 0 and run["tokens"] == 0 and run["cost_cny"] == 0
             and run["target_agent_executed"] is False, "RUN_SCOPE")


def seal(document: dict) -> dict:
    """Return a canonical document with internal section digests; no authenticity claim."""
    result = dict(document)
    result["digests"] = {name: digest(result[name])
                         for name in ("contracts", "run", "observations", "effect_result", "claims")}
    return result


def build_witness(contracts: FrozenContracts, run: dict, observations: list[dict]) -> dict:
    contracts.validate()
    effect_result = evaluate_config_effect(contracts.effect, observations)
    document = {"schema_version": SCHEMA_VERSION, "issuer": dict(ISSUER),
                "source_identity": {
                    "source_level": SOURCE_LEVEL,
                    "runproof_source_commit": contracts.experiment["runproof_parent_commit"],
                    "runtime_source_sha256": contracts.experiment["runtime_source_sha256"],
                    "config_center_source_commit": contracts.experiment["config_center_source_commit"],
                    "config_center_source_manifest_sha256": contracts.experiment["config_center_manifest_sha256"],
                    "config_center_jar_sha256": contracts.experiment["config_center_jar_sha256"],
                    "java_version": contracts.experiment["java_version"],
                },
                "contracts": contracts.document(), "run": run,
                "observations": observations, "effect_result": effect_result,
                "claims": {"contract_outcome": effect_result["contract_outcome"],
                           "source_level": SOURCE_LEVEL,
                           "issuer_authenticity": "NOT_ESTABLISHED",
                           "trust_domain": "SAME_CONFIG_CENTER_SERVICE",
                           "database_independent_authority": "NOT_ESTABLISHED",
                           "target_agent_execution": "NOT_EXECUTED",
                           "automatic_fault_discovery": "NOT_ESTABLISHED"},
                "digests": {}, "limitations": list(LIMITATIONS)}
    return seal(document)


def _validate_document(document: dict) -> None:
    _fields(document, _TOP_FIELDS, "WITNESS_FIELDS")
    _require(document["schema_version"] == SCHEMA_VERSION and document["issuer"] == ISSUER,
             "WITNESS_OR_ISSUER_IDENTITY")
    _require(document["limitations"] == LIMITATIONS, "LIMITATIONS_MISMATCH")
    _require(not _contains_secret_name(document), "SECRET_FIELD_PRESENT")
    try:
        contracts = FrozenContracts.from_document(document["contracts"])
    except Exception as exc:
        if isinstance(exc, WitnessRejected):
            raise
        raise WitnessRejected("CONTRACTS_REJECTED") from None
    experiment = contracts.experiment
    source = document["source_identity"]
    _fields(source, _SOURCE_FIELDS, "SOURCE_FIELDS")
    expected_source = {"source_level": SOURCE_LEVEL,
                       "runproof_source_commit": experiment["runproof_parent_commit"],
                       "runtime_source_sha256": experiment["runtime_source_sha256"],
                       "config_center_source_commit": experiment["config_center_source_commit"],
                       "config_center_source_manifest_sha256": experiment["config_center_manifest_sha256"],
                       "config_center_jar_sha256": experiment["config_center_jar_sha256"],
                       "java_version": experiment["java_version"]}
    _require(source == expected_source, "SOURCE_IDENTITY_MISMATCH")
    _validate_run(document["run"], contracts)
    _validate_observations(document["observations"], contracts.effect)
    _require(document["run"]["http_request_count"] == len(document["observations"]),
             "HTTP_COUNT_MISMATCH")
    expected_result = evaluate_config_effect(contracts.effect, document["observations"])
    _require(document["effect_result"] == expected_result, "ORACLE_RESULT_MISMATCH")
    claims = {"contract_outcome": expected_result["contract_outcome"], "source_level": SOURCE_LEVEL,
              "issuer_authenticity": "NOT_ESTABLISHED", "trust_domain": "SAME_CONFIG_CENTER_SERVICE",
              "database_independent_authority": "NOT_ESTABLISHED",
              "target_agent_execution": "NOT_EXECUTED", "automatic_fault_discovery": "NOT_ESTABLISHED"}
    _require(document["claims"] == claims, "CLAIMS_MISMATCH")
    _fields(document["digests"], _DIGEST_FIELDS, "DIGEST_FIELDS")
    expected_digests = {name: digest(document[name])
                        for name in ("contracts", "run", "observations", "effect_result", "claims")}
    _require(document["digests"] == expected_digests, "SECTION_DIGEST_MISMATCH")


def verify_bytes(raw: bytes, expected_sha256: str | None = None) -> str:
    """Verify offline semantics and, when supplied, an independently held file hash."""
    try:
        document = strict_json(raw)
    except Exception:
        raise WitnessRejected("INVALID_OR_DUPLICATE_JSON") from None
    _require(type(document) is dict, "TOP_LEVEL_OBJECT_REQUIRED")
    _validate_document(document)
    if expected_sha256 is None:
        return "UNANCHORED_INCONCLUSIVE"
    _require(isinstance(expected_sha256, str) and _SHA256.fullmatch(expected_sha256),
             "EXPECTED_ANCHOR_INVALID")
    _require(sha256_bytes(raw) == expected_sha256, "ANCHOR_MISMATCH")
    return "VERIFIED_ANCHORED"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline RPF-51 config HTTP Witness verifier")
    parser.add_argument("witness")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    try:
        with open(args.witness, "rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        _require(len(raw) <= 1024 * 1024, "WITNESS_SIZE_LIMIT")
        status = verify_bytes(raw, args.expected_sha256)
        document = strict_json(raw)
        print(f"{status} {document['effect_result']['contract_outcome']}")
        return 0 if status == "VERIFIED_ANCHORED" else 2
    except WitnessRejected as exc:
        print(f"REJECTED {exc.code}", file=sys.stderr)
        return 3
    except OSError:
        print("REJECTED WITNESS_UNAVAILABLE", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

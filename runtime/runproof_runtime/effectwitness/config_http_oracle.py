"""Deterministic RPF-51 business-effect rules over recorded HTTP observations."""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import quote

from .config_http_contracts import VERIFIER_ID, VERIFIER_VERSION

OBSERVATION_KINDS = (
    "initial_current", "initial_history", "unauthorized_write",
    "after_unauthorized_current", "after_unauthorized_history", "create_v1",
    "update_v2", "stale_update", "final_current", "final_history", "final_list",
)
_OBSERVATION_FIELDS = {"seq", "kind", "method", "path", "request", "status", "content_type",
                       "etag", "trace_id", "response", "response_body_sha256", "elapsed_ms",
                       "transport_error"}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TRACE = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")


def _is_time(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _expected_path(kind: str, effect: dict) -> tuple[str, str]:
    app, env, key = (quote(effect[name], safe="") for name in ("app", "env", "key"))
    if kind in ("initial_current", "after_unauthorized_current", "final_current"):
        return "GET", f"/api/configs/{key}?app={app}&env={env}"
    if kind in ("initial_history", "after_unauthorized_history", "final_history"):
        return "GET", f"/api/configs/history?app={app}&env={env}&key={key}&limit=50"
    if kind == "final_list":
        return "GET", f"/api/configs?app={app}&env={env}"
    return "POST", "/api/configs"


def _expected_request(kind: str, effect: dict):
    base = {name: effect[name] for name in ("app", "env", "key")}
    if kind == "unauthorized_write":
        return {**base, "value": effect["unauthorized_value"]}
    if kind == "create_v1":
        return {**base, "value": effect["initial_value"]}
    if kind == "update_v2":
        return {**base, "value": effect["required_value"],
                "expectedVersion": effect["initial_version"]}
    if kind == "stale_update":
        return {**base, "value": effect["stale_value"],
                "expectedVersion": effect["stale_expected_version"]}
    return None


def _valid_api_response(observation: dict, expected_status: int, expected_code: int,
                        expected_data_kind: str) -> tuple[bool, object]:
    if (observation["status"] != expected_status or observation["transport_error"] is not None
            or observation["content_type"] is None
            or not observation["content_type"].lower().startswith("application/json")):
        return False, None
    body = observation["response"]
    if type(body) is not dict or set(body) != {"code", "message", "data", "traceId"}:
        return False, None
    if (type(body["code"]) is not int or body["code"] != expected_code
            or not isinstance(body["message"], str)
            or (body["traceId"] is not None and
                (not isinstance(body["traceId"], str) or not _TRACE.fullmatch(body["traceId"])) )):
        return False, None
    if expected_data_kind == "none" and body["data"] is not None:
        return False, None
    if expected_data_kind == "list" and type(body["data"]) is not list:
        return False, None
    if expected_data_kind == "item" and type(body["data"]) is not dict:
        return False, None
    return True, body["data"]


def _valid_item(value, effect: dict, *, version: int, content: str) -> bool:
    names = {"app", "env", "key", "value", "description", "version", "updatedAt"}
    return (type(value) is dict and set(value) == names
            and value["app"] == effect["app"] and value["env"] == effect["env"]
            and value["key"] == effect["key"] and value["value"] == content
            and value["description"] is None and type(value["version"]) is int
            and value["version"] == version and _is_time(value["updatedAt"]))


def _valid_history(value, effect: dict) -> bool:
    names = {"app", "env", "key", "value", "description", "version", "action",
             "operator", "reason", "createdAt"}
    if type(value) is not list or len(value) != 2:
        return False
    expected = ((2, effect["required_value"]), (1, effect["initial_value"]))
    previous_time = None
    for row, (version, content) in zip(value, expected):
        if (type(row) is not dict or set(row) != names or row["app"] != effect["app"]
                or row["env"] != effect["env"] or row["key"] != effect["key"]
                or row["value"] != content or row["description"] is not None
                or type(row["version"]) is not int or row["version"] != version
                or row["action"] != "UPSERT" or row["operator"] is not None or row["reason"] is not None
                or not _is_time(row["createdAt"])):
            return False
        when = datetime.fromisoformat(row["createdAt"].replace("Z", "+00:00"))
        if previous_time is not None and when > previous_time:
            return False
        previous_time = when
    return True


def _error_response(observation: dict, status: int, code: int) -> bool:
    valid, data = _valid_api_response(observation, status, code, "none")
    return valid and data is None


def evaluate_config_effect(effect: dict, observations: list[dict]) -> dict:
    """Recompute the versioned mutation contract without trusting POST success alone."""
    violations: list[str] = []
    gaps: list[str] = []
    facts: dict = {"authority_model": "SAME_CONFIG_CENTER_SERVICE_READBACK",
                   "verifier_id": VERIFIER_ID, "verifier_version": VERIFIER_VERSION}
    if type(observations) is not list:
        observations = []
        gaps.append("OBSERVATIONS_NOT_A_LIST")

    by_kind = {}
    for index, item in enumerate(observations):
        if type(item) is not dict or set(item) != _OBSERVATION_FIELDS:
            gaps.append(f"OBSERVATION_SHAPE_{index + 1}")
            continue
        kind = item["kind"]
        if kind not in OBSERVATION_KINDS or kind in by_kind:
            violations.append("OBSERVATION_KIND_DUPLICATE_OR_UNKNOWN")
            continue
        by_kind[kind] = item
        if type(item["seq"]) is not int or item["seq"] != index + 1:
            violations.append("OBSERVATION_SEQUENCE")
        method, path = _expected_path(kind, effect)
        if item["method"] != method or item["path"] != path or item["request"] != _expected_request(kind, effect):
            violations.append("OBSERVATION_REQUEST_MISMATCH_" + kind.upper())
        if item["status"] is None or item["transport_error"] is not None:
            gaps.append("HTTP_OUTCOME_UNKNOWN_" + kind.upper())
        elif type(item["status"]) is not int or not 100 <= item["status"] <= 599:
            gaps.append("HTTP_STATUS_INVALID_" + kind.upper())
        if (item["response_body_sha256"] is not None
                and (not isinstance(item["response_body_sha256"], str)
                     or not _SHA256.fullmatch(item["response_body_sha256"]))):
            violations.append("RESPONSE_DIGEST_INVALID_" + kind.upper())

    missing = [kind for kind in OBSERVATION_KINDS if kind not in by_kind]
    gaps.extend("OBSERVATION_MISSING_" + kind.upper() for kind in missing)
    facts["http_request_count"] = len(observations)

    def body(kind, status, code, data_kind):
        observation = by_kind.get(kind)
        if observation is None:
            return None
        valid, data = _valid_api_response(observation, status, code, data_kind)
        if not valid:
            if observation["status"] not in (None, status, 429) and observation["status"] >= 500:
                gaps.append("SERVICE_ERROR_" + kind.upper())
            elif observation["status"] == 429:
                gaps.append("SERVICE_RATE_LIMIT_" + kind.upper())
            elif observation["status"] is None or observation["transport_error"] is not None:
                gaps.append("HTTP_OUTCOME_UNKNOWN_" + kind.upper())
            else:
                violations.append("RESPONSE_CONTRACT_MISMATCH_" + kind.upper())
            return None
        return data

    # Empty initial namespace is a precondition. A pre-existing item makes the run inconclusive.
    initial = by_kind.get("initial_current")
    if initial is not None and initial["status"] == 404:
        if not _error_response(initial, 404, 4041):
            violations.append("INITIAL_NOT_FOUND_RESPONSE_INVALID")
        facts["initial_item_absent"] = True
    elif initial is not None and initial["status"] not in (None, 429) and initial["status"] < 500:
        gaps.append("INITIAL_NAMESPACE_NOT_EMPTY")
        facts["initial_item_absent"] = False
    else:
        gaps.append("INITIAL_STATE_UNAVAILABLE")

    for name in ("initial_history", "after_unauthorized_history"):
        data = body(name, 200, 0, "list")
        if data is not None and data != []:
            if name == "initial_history":
                gaps.append("INITIAL_HISTORY_NOT_EMPTY")
            else:
                violations.append("UNAUTHORIZED_WRITE_ADDED_HISTORY")
    for name in ("initial_current", "after_unauthorized_current"):
        item = by_kind.get(name)
        if item is not None and item["status"] == 404:
            if not _error_response(item, 404, 4041):
                violations.append("NOT_FOUND_RESPONSE_INVALID_" + name.upper())
        elif name == "after_unauthorized_current" and item is not None and item["status"] == 200:
            _valid, data = _valid_api_response(item, 200, 0, "item")
            if _valid:
                violations.append("UNAUTHORIZED_WRITE_CHANGED_STATE")
        elif item is not None and item["status"] not in (None, 429) and item["status"] < 500:
            if name == "initial_current":
                gaps.append("INITIAL_NAMESPACE_NOT_EMPTY")
            else:
                violations.append("UNAUTHORIZED_WRITE_CHANGED_STATE")

    unauthorized = by_kind.get("unauthorized_write")
    if unauthorized is not None:
        if unauthorized["status"] == 403:
            if not _error_response(unauthorized, 403, 4031):
                violations.append("UNAUTHORIZED_REJECTION_INVALID")
            else:
                facts["unauthorized_write_rejected"] = True
        elif unauthorized["status"] in (None, 429) or (isinstance(unauthorized["status"], int)
                                                       and unauthorized["status"] >= 500):
            gaps.append("UNAUTHORIZED_WRITE_RESULT_UNKNOWN")
        else:
            violations.append("UNAUTHORIZED_WRITE_ACCEPTED")

    created = body("create_v1", 200, 0, "item")
    if created is not None and not _valid_item(created, effect, version=1, content=effect["initial_value"]):
        violations.append("CREATE_RESPONSE_MISMATCH")
    updated = body("update_v2", 200, 0, "item")
    if updated is not None and not _valid_item(updated, effect, version=2, content=effect["required_value"]):
        violations.append("UPDATE_RESPONSE_MISMATCH")

    stale = by_kind.get("stale_update")
    if stale is not None:
        if stale["status"] == 409:
            if not _error_response(stale, 409, 4091):
                violations.append("STALE_CONFLICT_RESPONSE_INVALID")
            else:
                facts["stale_write_rejected"] = True
        elif stale["status"] in (None, 429) or (isinstance(stale["status"], int) and stale["status"] >= 500):
            gaps.append("STALE_WRITE_RESULT_UNKNOWN")
        else:
            violations.append("STALE_WRITE_NOT_REJECTED")

    current = body("final_current", 200, 0, "item")
    if current is not None:
        valid_current = _valid_item(current, effect, version=2, content=effect["required_value"])
        facts["final_current"] = {"value": current.get("value"), "version": current.get("version")}
        if not valid_current:
            violations.append("FINAL_CURRENT_STATE_MISMATCH")
    history = body("final_history", 200, 0, "list")
    if history is not None:
        facts["history_versions"] = [row.get("version") for row in history if type(row) is dict]
        facts["history_values"] = [row.get("value") for row in history if type(row) is dict]
        if not _valid_history(history, effect):
            violations.append("FINAL_HISTORY_MISMATCH")

    listed = body("final_list", 200, 0, "list")
    if listed is not None:
        if (len(listed) != 1
                or not _valid_item(listed[0], effect, version=2, content=effect["required_value"])):
            violations.append("FINAL_LIST_MISMATCH")
        else:
            facts["list_crosscheck"] = "MATCHED"
        etag = by_kind["final_list"]["etag"]
        if not isinstance(etag, str) or not etag.strip():
            gaps.append("LIST_ETAG_MISSING")
        else:
            facts["list_etag_present"] = True

    if len(observations) > 12:
        violations.append("HTTP_BUDGET_EXCEEDED")
    if violations:
        outcome = "VIOLATION_CONFIRMED"
    elif gaps:
        outcome = "INCONCLUSIVE"
    else:
        outcome = "CONTRACT_SATISFIED_IN_RUN"
    return {"contract_outcome": outcome, "violated_rules": sorted(set(violations)),
            "evidence_gaps": sorted(set(gaps)), "facts": facts,
            "state_diff": {"initial": {"exists": facts.get("initial_item_absent") is False},
                           "final": facts.get("final_current"),
                           "history_versions": facts.get("history_versions")},
            "verifier_id": VERIFIER_ID, "verifier_version": VERIFIER_VERSION}

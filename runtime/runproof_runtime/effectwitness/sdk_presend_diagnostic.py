"""Bounded public diagnostics for new RPF-102 case evidence."""
import re
import sys

from .sdk_presend_contracts import (BUDGET, CALL, CASES, LIMIT, bounded, canonical, check,
                                   identity, safe, sha, strict, tool_value)
from .sdk_presend_oracle import receiver_identity, receiver_payload, replay

MAX_BYTES = 8192
SCHEMA = "rpf102-sdk-diagnostic-v1"
CONTEXT = "diagnostic-context.json"
REPORT = "diagnostic.json"
STAGES = ("CONFIG", "SDK_IMPORT", "SDK_INIT", "SDK_RUN", "SDK_TOOL_CALLBACK", "SDK_REPORT")
ERRORS = ("ImportError", "ModuleNotFoundError", "PermissionError", "OSError", "FileNotFoundError",
          "RuntimeError", "TypeError", "ValueError", "KeyError", "AttributeError", "Denied",
          "ValidationError", "UserError", "UnexpectedModelBehavior", "UsageLimitExceeded",
          "ModelHTTPError", "ModelAPIError", "TimeoutError", "HTTPStatusError", "ConnectError",
          "ReadTimeout", "APIConnectionError")
HTTP_CODES = ("HTTP_ADMISSION", "CONTENT_LENGTH", "CONTENT_LIMIT", "TRUNCATED_HTTP")
RECEIVER_CODES = ("RECEIVER_IDENTITY", "RECEIVER_NONCE", "RECEIVER_ACK", "TRUNCATED_TRANSPORT")
CONTRACT_CODES = ("REQUEST_LIMIT", "REQUEST_SCHEMA", "TOOL_POLICY", "TOOL_ALLOWLIST", "MESSAGE_COUNT",
                  "PROMPT_BINDING", "ASSISTANT_TOOL_BINDING", "TOOL_RETURN_BINDING", "TOOL_CALLBACK",
                  "ROUTE_OR_INBOUND_BUDGET", "TOOL_RETURN_REQUIRED", "DUPLICATE_KEY", "JSONDecodeError",
                  "UnicodeDecodeError", "UNEXPECTED_ADMISSION_FAILURE", "TICKET_BINDING", "TICKET_BUDGET")
HOST_CODES = (*HTTP_CODES, *RECEIVER_CODES, *CONTRACT_CODES, "HOST_IO_FAILURE", "HOST_STATE_FAILURE")
CLASSIFICATIONS = ("SDK_CHILD_NONZERO", "SDK_CHILD_TIMEOUT", "SDK_OUTPUT_INVALID", "HOST_HTTP_REJECTED",
                   "HOST_CONTRACT_REJECTED", "SDK_IMPORT_OR_INIT_FAILURE", "UNKNOWN_EXPECTED_DENIAL",
                   "RECEIVER_ABSENT", "RECEIVER_RECEIPT_MISMATCH", "ORACLE_REJECTED", "EVIDENCE_UNAVAILABLE",
                   "NORMAL_VERIFIED")
MISSING = ("SDK_LAUNCH", "SDK_EXIT", "SDK_OUTPUT", "HOST_WAL", "RECEIVER_IDENTITY", "RECEIVER_PAYLOAD")
WAL_COUNTS = {"provider_reserve_count": "PROVIDER_RESERVE", "send_begin_count": "SEND_BEGIN",
              "send_entry_count": "SEND_ENTRY"}
COUNTS = ("sdk_post_count", *WAL_COUNTS, "receiver_receipt_count", "received_bytes", "tool_callback_count")
READ_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError)


def allowed(value, values):
    return value if type(value) is str and value in values else None


FILE_TARGETS = ("OPENSSL_CONFIG", "SYSTEM_ZONEINFO", "SYSTEM_TIMEZONE", "OS_RELEASE", "NULL_DEVICE",
                "SYSTEM_MIME", "PROC", "VENV_CONFIG", "SYSTEM_CA", "OUTSIDE_ROOTS")
AUDIT_TARGETS = {
    "OPEN_READ_ROOT_DENIED": FILE_TARGETS, "OPEN_WRITE_ROOT_DENIED": FILE_TARGETS,
    "OPEN_DOTENV_DENIED": ("DOTENV",), "SOCKET_CONNECT_DENIED": ("NETWORK",),
    "DNS_DENIED": ("NETWORK",), "SUBPROCESS_DENIED": ("PROCESS",), "OTHER_DENIED": ("NETWORK",),
}
SDK_ERROR_DETAIL = {"origin", "audit_code", "target"}


def validate_sdk_error(row):
    fields = {"status", "stage", "error_type"}
    check(type(row) is dict and set(row) in (fields, fields | SDK_ERROR_DETAIL)
          and row["status"] == "SDK_ERROR" and allowed(row["stage"], STAGES)
          and (row["error_type"] is None or allowed(row["error_type"], ERRORS)), "SDK_ERROR_SCHEMA")
    if "origin" in row:
        origin, code, target = (row[k] for k in ("origin", "audit_code", "target"))
        check((origin == "EXCEPTION" and code is None and target is None)
              or (origin == "AUDIT_HOOK" and row["error_type"] == "PermissionError"
                  and type(code) is str and allowed(target, AUDIT_TARGETS.get(code, ()))),
              "SDK_ERROR_DETAIL")
    return row


def source_sha():
    return sha(canonical(identity()))


def context(folder, case):
    return {"schema": SCHEMA, "owner": folder.parent.name, "case": case, "source_sha256": source_sha()}


def validate_public(raw):
    check(len(raw) <= MAX_BYTES, "DIAGNOSTIC_LIMIT")
    row = strict(raw)
    fields = {
        "schema", "source_sha256", "phase", "case", "sdk_spawn_attempted", "sdk_exit", "sdk_stage",
        "sdk_error_type", "host_failure_code", "missing_evidence_types", "final_classification", *COUNTS,
    }
    check(type(row) is dict and set(row) in (fields, fields | {"sdk_error_detail"}), "DIAGNOSTIC_FIELDS")
    check(row["schema"] == SCHEMA and type(row["source_sha256"]) is str
          and re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"])
          and row["phase"] in ("RECEIVER", "SDK", "ORACLE", "TERMINAL") and row["case"] in CASES
          and type(row["sdk_spawn_attempted"]) is bool and allowed(row["final_classification"], CLASSIFICATIONS),
          "DIAGNOSTIC_IDENTITY")
    for key, values in (("sdk_stage", STAGES), ("sdk_error_type", ERRORS), ("host_failure_code", HOST_CODES)):
        check(row[key] is None or allowed(row[key], values), "DIAGNOSTIC_ENUM")
    exit_code = row["sdk_exit"]
    check(exit_code is None or type(exit_code) is int and -255 <= exit_code <= 0xFFFFFFFF,
          "DIAGNOSTIC_EXIT")
    if "sdk_error_detail" in row:
        detail = row["sdk_error_detail"]
        check(type(detail) is dict and set(detail) == SDK_ERROR_DETAIL
              and row["sdk_spawn_attempted"] and exit_code not in (None, 0), "SDK_ERROR_DETAIL")
        validate_sdk_error({"status": "SDK_ERROR", "stage": row["sdk_stage"],
                            "error_type": row["sdk_error_type"], **detail})
    budget = BUDGET[row["case"]]
    limits = {"sdk_post_count": 2, **dict.fromkeys(WAL_COUNTS, budget), "receiver_receipt_count": budget,
              "received_bytes": budget * LIMIT, "tool_callback_count": 1}
    for key, upper in limits.items():
        value = row[key]
        check(value is None or type(value) is int and 0 <= value <= upper, "DIAGNOSTIC_COUNT")
    received = row["receiver_receipt_count"]
    size = row["received_bytes"]
    check((received is None and size is None)
          or (received is not None and size is not None and received <= size <= received * LIMIT),
          "DIAGNOSTIC_RECEIVER_COUNT")
    missing = row["missing_evidence_types"]
    check(type(missing) is list and all(allowed(item, MISSING) for item in missing)
          and missing == sorted(set(missing)), "DIAGNOSTIC_MISSING")
    classification = row["final_classification"]
    if classification in ("NORMAL_VERIFIED", "UNKNOWN_EXPECTED_DENIAL"):
        check(classification == ("NORMAL_VERIFIED" if row["case"] == "NORMAL" else "UNKNOWN_EXPECTED_DENIAL")
              and row["phase"] == "TERMINAL" and row["sdk_spawn_attempted"] and row["sdk_exit"] == 0
              and row["sdk_post_count"] == 2 and row["tool_callback_count"] == 1
              and row["host_failure_code"] is None and not missing
              and all(row[key] == budget for key in WAL_COUNTS) and received == budget,
              "DIAGNOSTIC_VERIFIED_BINDING")
    return row


def child_report(raw, case):
    check(raw is not None and 0 < len(raw) <= MAX_BYTES, "SDK_OUTPUT_INVALID")
    row = strict(raw)
    check(type(row) is dict, "SDK_OUTPUT_INVALID")
    if row.get("status") == "SDK_ERROR":
        if SDK_ERROR_DETAIL.intersection(row):
            validate_sdk_error(row)
        else:
            check("error_type" in row, "SDK_OUTPUT_INVALID")
        return allowed(row.get("stage"), STAGES), allowed(row["error_type"], ERRORS), None
    expected = {"call_id": CALL, "value": tool_value(case)}
    callbacks = row.get("tool_callbacks")
    check(type(row.get("terminal")) is dict and callbacks == [expected], "SDK_OUTPUT_INVALID")
    return None, None, len(callbacks)


def child_classification(exit_code, stage, error, output_valid, *, timed_out):
    if timed_out:
        return "SDK_CHILD_TIMEOUT"
    if not output_valid:
        return "SDK_OUTPUT_INVALID"
    if exit_code and stage in ("SDK_IMPORT", "SDK_INIT") and error:
        return "SDK_IMPORT_OR_INIT_FAILURE"
    if exit_code:
        return "SDK_CHILD_NONZERO"
    return None


def host_classification(code):
    if code in HTTP_CODES:
        return "HOST_HTTP_REJECTED"
    if code in RECEIVER_CODES:
        return "RECEIVER_RECEIPT_MISMATCH"
    if code in CONTRACT_CODES:
        return "HOST_CONTRACT_REJECTED"
    return "EVIDENCE_UNAVAILABLE" if code is not None else None


def collect(folder, case, *, phase, attempted, timed_out=False, host_code=None, outcome=None):
    """Use closed case files. A partial journal is an observed prefix, not a zero-send claim."""
    check(strict(bounded(folder / CONTEXT, MAX_BYTES)) == context(folder, case), "DIAGNOSTIC_CONTEXT")
    row = dict.fromkeys(COUNTS)
    host_code = allowed(host_code, HOST_CODES) or ("HOST_STATE_FAILURE" if host_code is not None else None)
    row.update(schema=SCHEMA, source_sha256=source_sha(), phase=phase, case=case,
               sdk_spawn_attempted=attempted, sdk_exit=None, sdk_stage=None, sdk_error_type=None,
               host_failure_code=host_code)
    missing = set()

    def read(name, label, *, raw=False, limit=MAX_BYTES):
        try:
            data = bounded(folder / name, limit)
            return data if raw else strict(data)
        except READ_ERRORS:
            missing.add(label)
            return None

    launch = read("sdk-launch.json", "SDK_LAUNCH")
    done = read("sdk-exit.json", "SDK_EXIT")
    output = read("sdk-output.json", "SDK_OUTPUT", raw=True)
    if (type(launch) is dict and type(done) is dict and type(launch.get("pid")) is int
            and launch["pid"] > 0 and done.get("pid") == launch["pid"] and type(done.get("exit")) is int
            and -255 <= done["exit"] <= 0xFFFFFFFF):
        row["sdk_exit"] = done["exit"]
    else:
        missing.add("SDK_EXIT")
    output_valid = False
    if row["sdk_exit"] is not None and output is not None and done.get("stdout_sha256") == sha(output):
        try:
            stage, error, callbacks = child_report(output, case)
            row.update(sdk_stage=stage, sdk_error_type=error, tool_callback_count=callbacks)
            if stage and row["sdk_exit"]:
                decoded = strict(output)
                if "origin" in decoded:
                    row["sdk_error_detail"] = {key: decoded[key] for key in SDK_ERROR_DETAIL}
            output_valid = True
        except READ_ERRORS:
            pass
    if not output_valid:
        missing.add("SDK_OUTPUT")

    try:
        rows = replay(bounded(folder / "wal.jsonl", 131072))
        ready = {"case": case, "owner": folder.parent.name, "source": identity(), "budget": BUDGET[case]}
        check(rows[0]["kind"] == "READY" and rows[0]["body"] == ready, "DIAGNOSTIC_WAL_IDENTITY")
        kinds = [r["kind"] for r in rows]
        posts = kinds.count("SDK_POST_RECEIVED")
        counts = [kinds.count(kind) for kind in WAL_COUNTS.values()]
        check(0 <= counts[2] <= counts[1] <= counts[0] <= BUDGET[case] and counts[0] <= posts <= 2,
              "DIAGNOSTIC_WAL_COUNTS")
        row["sdk_post_count"] = posts
        if posts:
            # Zero is conclusive only if the writer closed the journal without uncertainty.
            uncertain = safe(folder / "active").exists()
            for field, count in zip(WAL_COUNTS, counts):
                row[field] = count if count or not uncertain else None
    except READ_ERRORS:
        missing.add("HOST_WAL")

    receiver_result = None
    try:
        ready, _, done = receiver_identity(folder.parent.name, case, *(
            strict(bounded(folder / name, MAX_BYTES)) for name in
            ("receiver-ready.json", "receiver-launch.json", "receiver-exit.json")
        ))
    except FileNotFoundError:
        missing.add("RECEIVER_IDENTITY")
        receiver_result = "RECEIVER_ABSENT"
    except READ_ERRORS:
        missing.add("RECEIVER_IDENTITY")
        receiver_result = "RECEIVER_RECEIPT_MISMATCH"
    else:
        sizes = []
        for index in range(1, BUDGET[case] + 1):
            try:
                raw = bounded(folder / f"receiver-{index}.raw")
                receipt = strict(bounded(folder / f"receiver-{index}.json", MAX_BYTES))
                sizes.append(receiver_payload(folder.parent.name, case, ready, done, index, raw, receipt))
            except FileNotFoundError:
                missing.add("RECEIVER_PAYLOAD")
                receiver_result = receiver_result or "RECEIVER_ABSENT"
            except READ_ERRORS:
                missing.add("RECEIVER_PAYLOAD")
                receiver_result = "RECEIVER_RECEIPT_MISMATCH"
        if receiver_result != "RECEIVER_RECEIPT_MISMATCH" and sizes:
            row.update(receiver_receipt_count=len(sizes), received_bytes=sum(sizes))

    sdk_result = child_classification(row["sdk_exit"], row["sdk_stage"], row["sdk_error_type"],
                                      output_valid, timed_out=timed_out) if attempted else None
    host_result = host_classification(host_code)
    if outcome == "ORACLE_REJECTED" and receiver_result == "RECEIVER_RECEIPT_MISMATCH":
        outcome = receiver_result
    row.update(missing_evidence_types=sorted(missing),
               final_classification=(outcome or (host_result if host_result != "EVIDENCE_UNAVAILABLE" else None)
                                     or sdk_result or host_result
                                     or receiver_result or "EVIDENCE_UNAVAILABLE"))
    return validate_public(canonical(row))


def inspect_diagnostic(folder, case):
    check(strict(bounded(folder / CONTEXT, MAX_BYTES)) == context(folder, case), "DIAGNOSTIC_CONTEXT")
    row = validate_public(bounded(folder / REPORT, MAX_BYTES))
    check(row["case"] == case and row["source_sha256"] == source_sha(), "DIAGNOSTIC_CONTEXT")
    return row


def main():
    try:
        validate_public(sys.stdin.buffer.read(MAX_BYTES + 1))
    except READ_ERRORS:
        print("DIAGNOSTIC_REJECTED", file=sys.stderr)
        return 3
    print("DIAGNOSTIC_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

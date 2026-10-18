"""Bounded rev-3 Pydantic AI fixture-only diagnostic; starts no Java process."""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import probe as runner
from runtime.runproof_runtime.effectwitness.config_target_bridge import (
    ConfigTargetFixtureHost, ConfigTargetInMemoryDiagnosticBackend,
    ConfigTargetToolHost,
)
from runtime.runproof_runtime.effectwitness.config_target_contracts import (
    canonical, digest, make_contracts, parse_sdk_child_report, strict_json,
)


TASK_ROOT = runner.TASK_ROOT
REV3_ROOT = runner.ROOT / "spikes" / "rpf-52" / "rev-3"
SUMMARY_PATH = REV3_ROOT / "sdk-diagnostic.json"
MAX_ATTEMPTS = 2
ATTEMPT_TIMEOUT_SECONDS = 120


def _safe_status_code(value: object) -> str:
    if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", value):
        return value
    return "DIAGNOSTIC_DRIVER_ERROR"


def _ensure_task_root() -> None:
    local_root = runner.ROOT / ".local"
    if (not local_root.is_dir() or local_root.is_symlink()
            or TASK_ROOT.is_symlink()
            or (TASK_ROOT.exists() and not TASK_ROOT.is_dir())):
        raise runner.ProbeError("RPF52_REV3_DIAGNOSTIC_ROOT_UNAVAILABLE")
    if not TASK_ROOT.exists():
        TASK_ROOT.mkdir()


def _read_attempt(attempt: int) -> dict:
    path = TASK_ROOT / f"diagnostic-{attempt}" / "attempt.json"
    if not path.is_file() or runner._has_symlink(path, TASK_ROOT):
        raise runner.ProbeError("PRIOR_DIAGNOSTIC_ATTEMPT_MISSING")
    try:
        value = strict_json(path.read_bytes())
    except Exception:
        raise runner.ProbeError("PRIOR_DIAGNOSTIC_ATTEMPT_INVALID") from None
    if type(value) is not dict or value.get("attempt") != attempt:
        raise runner.ProbeError("PRIOR_DIAGNOSTIC_ATTEMPT_INVALID")
    return value


def _prepare_attempt(attempt: int, source_identity: dict) -> Path:
    _ensure_task_root()
    attempt_root = TASK_ROOT / f"diagnostic-{attempt}"
    if attempt == 1:
        if any((TASK_ROOT / name).exists() or (TASK_ROOT / name).is_symlink()
               for name in ("diagnostic-1", "diagnostic-2", "scenario")):
            raise runner.ProbeError("DIAGNOSTIC_ATTEMPT_ONE_ALREADY_EXISTS")
    else:
        if attempt != 2:
            raise runner.ProbeError("DIAGNOSTIC_ATTEMPT_OUT_OF_RANGE")
        previous = _read_attempt(1)
        if previous.get("status") != "FAIL":
            raise runner.ProbeError("DIAGNOSTIC_ATTEMPT_TWO_REQUIRES_FAILURE")
        if previous.get("runtime_source_identity", {}).get("sha256") == source_identity["sha256"]:
            raise runner.ProbeError("DIAGNOSTIC_ATTEMPT_TWO_REQUIRES_SOURCE_CHANGE")
        if attempt_root.exists() or attempt_root.is_symlink():
            raise runner.ProbeError("DIAGNOSTIC_ATTEMPT_TWO_ALREADY_EXISTS")
        if (TASK_ROOT / "scenario").exists() or (TASK_ROOT / "scenario").is_symlink():
            raise runner.ProbeError("SCENARIO_MUST_NOT_PRECEDE_DIAGNOSTIC")
    attempt_root.mkdir()
    sdk_tmp = attempt_root / "sdk-tmp"
    sdk_tmp.mkdir()
    (sdk_tmp / "appdata").mkdir()
    (sdk_tmp / "localappdata").mkdir()
    return attempt_root


def _lineage_valid(contracts: dict, fixture: ConfigTargetFixtureHost,
                   backend: ConfigTargetInMemoryDiagnosticBackend,
                   tool_host: ConfigTargetToolHost, sdk_report: dict,
                   process_pid: int) -> bool:
    calls = contracts["execution"]["tool_calls"]
    completions = fixture.completions
    trace = tool_host.tool_trace
    if (fixture.failure is not None or fixture.first_failure_code is not None
            or fixture.runtime is None or fixture.runtime.get("pid") != process_pid
            or len(completions) != 4 or len(trace) != 3
            or len(backend.observations) != 5 or backend.real_http_requests != 0
            or backend._state != (2, "rpf52-v2") or backend._history != [1, 2]
            or sdk_report.get("status") != "COMPLETED"
            or sdk_report.get("pid") != process_pid or sdk_report.get("requests") != 4
            or sdk_report.get("input_tokens") != 0 or sdk_report.get("output_tokens") != 0
            or sdk_report.get("tool_calls") != 3 or sdk_report.get("guard_denials") != []):
        return False
    if fixture.client_sources != {"127.0.0.1"}:
        return False
    for index, (completion, call) in enumerate(zip(completions, [None] + calls)):
        expected_returns = index
        if (completion.get("seq") != index + 1
                or completion.get("assistant_calls_seen") != index
                or completion.get("tool_returns_seen") != expected_returns):
            return False
        if index == 0:
            if completion.get("last_tool_return") is not None:
                return False
            continue
        returned = trace[index - 1]
        expected_ack = {"call_id": returned["call_id"],
                        "result_sha256": digest(returned["tool_return"])}
        if (returned.get("call_id") != calls[index - 1]["call_id"]
                or returned.get("name") != calls[index - 1]["name"]
                or returned.get("arguments") != calls[index - 1]["arguments"]
                or returned.get("accepted") is not True
                or completion.get("last_tool_return") != expected_ack):
            return False
    return True


def run_attempt(attempt: int) -> dict:
    if type(attempt) is not int or attempt not in (1, 2):
        raise runner.ProbeError("DIAGNOSTIC_ATTEMPT_OUT_OF_RANGE")
    runner._check_repo_identity(require_remote_free=True)
    source_identity = runner._source_identity()
    sdk_identity = runner._sdk_identity()
    java_placeholder_port, host_port = runner._free_ports()
    run_id = "rpf52-diag-" + uuid.uuid4().hex
    prepared_at = runner._utc_now()
    contracts = make_contracts(
        run_id=run_id, source_identity_sha256=source_identity["sha256"],
        sdk_identity=sdk_identity,
        java_version="JAVA_NOT_STARTED_FOR_DIAGNOSTIC",
        java_port=java_placeholder_port, agent_host_port=host_port,
        prepared_at_utc=prepared_at)
    attempt_root = _prepare_attempt(attempt, source_identity)
    sdk_tmp = attempt_root / "sdk-tmp"
    runner._write_exclusive(attempt_root / "attempt-started.json", canonical({
        "schema_version": "rpf52-sdk-diagnostic-start-v1",
        "plan_revision": "rev-3", "attempt": attempt, "run_id": run_id,
        "started_at_utc": prepared_at,
        "runtime_source_sha256": source_identity["sha256"],
        "sdk_identity": sdk_identity,
        "java_started": False,
    }))

    backend = ConfigTargetInMemoryDiagnosticBackend(contracts)
    tool_host = ConfigTargetToolHost(contracts, backend)
    fixture = ConfigTargetFixtureHost(
        contracts, tool_host, sdk_identity["sdk_source_sha256"],
        sdk_identity["openai_source_sha256"])
    process = None
    report = None
    parse_code = None
    stdout = b""
    stderr = b""
    stop_code = None
    stage = "FIXTURE_HOST_START"
    host_listener_pid = None
    child_external: list[str] = []
    parent_external: list[str] = []
    failure_code = None
    started = time.monotonic()
    try:
        fixture.start()
        host_port = fixture.port
        if not runner._listener_is(os.getpid(), host_port):
            raise runner.ProbeError("DIAGNOSTIC_FIXTURE_LISTENER_IDENTITY")
        host_listener_pid = os.getpid()
        stage = "SDK_CHILD_START"
        child_config = {
            "port": host_port, "run_id": run_id,
            "write_root": str(attempt_root),
            "sdk_readonly_path": str(runner.SDK_SITE_PACKAGES.resolve()),
            "timeout_seconds": ATTEMPT_TIMEOUT_SECONDS,
        }
        child_input = canonical(child_config)
        child_env = runner._minimal_env(sdk_tmp)
        if any("API_KEY" in name.upper() or "TOKEN" in name.upper()
               for name in child_env):
            raise runner.ProbeError("SDK_CREDENTIAL_ENV_PRESENT")
        sdk_command = [str(runner.SDK_PYTHON), "-B", "-I", str(runner.SDK_CHILD)]
        process = subprocess.Popen(
            sdk_command, cwd=attempt_root, env=child_env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stage = "SDK_CHILD_RUNNING"
        stdout, stderr, stop_code = runner._communicate_sdk(
            process, child_input, None, timeout_seconds=ATTEMPT_TIMEOUT_SECONDS)
        report, parse_code = parse_sdk_child_report(stdout, process.returncode)
        if stop_code:
            failure_code = stop_code
        elif parse_code:
            failure_code = parse_code
        elif process.returncode != 0:
            failure_code = "SDK_CHILD_EXIT_NONZERO"
        elif (report is None or report.get("pid") != process.pid
                or report.get("sdk_source_sha256") != sdk_identity["sdk_source_sha256"]
                or report.get("openai_source_sha256") != sdk_identity["openai_source_sha256"]):
            failure_code = "SDK_CHILD_IDENTITY_MISMATCH"
        elif (fixture.first_failure_code is not None or not _lineage_valid(
                contracts, fixture, backend, tool_host, report, process.pid)):
            failure_code = "SDK_FIXTURE_TOOL_LOOP_INCOMPLETE"
        child_external = runner._external_connections(
            process.pid, allowed_remote_ports={host_port})
        parent_external = runner._external_connections(
            os.getpid(), allowed_listener_ports={host_port})
        if child_external or parent_external:
            failure_code = failure_code or "DIAGNOSTIC_EXTERNAL_CONNECTION_GATE"
        if fixture.client_sources != {"127.0.0.1"}:
            failure_code = failure_code or "DIAGNOSTIC_FIXTURE_CLIENT_GATE"
    except Exception as exc:
        failure_code = failure_code or _safe_status_code(getattr(exc, "code", None))
        if failure_code == "DIAGNOSTIC_DRIVER_ERROR":
            failure_code = _safe_status_code(type(exc).__name__.upper())
    finally:
        child_stopped = runner._finish_process(process, grace=5)
        try:
            fixture.close()
            host_closed = True
        except Exception:
            host_closed = False
        child_external = sorted(set(child_external + (
            runner._external_connections(process.pid, allowed_remote_ports={host_port})
            if process is not None else [])))
        parent_external = sorted(set(parent_external + (
            runner._external_connections(os.getpid(), allowed_listener_ports={host_port})
            if fixture._server is not None or host_listener_pid is not None else [])))

    duration_ms = max(0, int((time.monotonic() - started) * 1000))
    host_closed = host_closed if "host_closed" in locals() else False
    cleanup = {
        "sdk_child_exited": child_stopped,
        "fixture_host_closed": host_closed,
        "fixture_port_closed": runner._port_free(host_port),
        "sdk_child_external_connections": child_external,
        "parent_process_external_connections": parent_external,
    }
    if (not cleanup["sdk_child_exited"] or not cleanup["fixture_host_closed"]
            or not cleanup["fixture_port_closed"] or child_external or parent_external):
        failure_code = failure_code or "DIAGNOSTIC_CLEANUP_GATE"
    if duration_ms > ATTEMPT_TIMEOUT_SECONDS * 1000:
        failure_code = failure_code or "DIAGNOSTIC_RUNTIME_BUDGET_EXCEEDED"
    status = "PASS" if failure_code is None else "FAIL"
    report = report if type(report) is dict else {}
    diagnostic = {
        "schema_version": "rpf52-sdk-diagnostic-attempt-v1",
        "plan_id": "RPF-52", "plan_revision": "rev-3", "attempt": attempt,
        "run_id": run_id, "status": status, "stage": stage,
        "failure_code": failure_code,
        "runtime_source_identity": source_identity,
        "sdk_identity": sdk_identity,
        "sdk_error": {
            "status": report.get("status"),
            "stage": report.get("stage"),
            "error_type": report.get("error_type"),
            "guard_code": report.get("guard_code"),
            "guard_denials": report.get("guard_denials", []),
            "parser_code": parse_code,
        },
        "fixture_host_first_failure_code": fixture.first_failure_code,
        "fixture_host_runtime": fixture.runtime,
        "fixture_completions": fixture.completions,
        "tool_trace": tool_host.tool_trace,
        "memory_backend": {
            "backend_id": backend.backend_id,
            "real_http_requests": backend.real_http_requests,
            "observations": backend.observations,
            "final_state": {"version": backend._state[0], "value": backend._state[1]}
                if backend._state else None,
            "history_versions": backend._history,
        },
        "sdk_child": {
            "pid": report.get("pid", process.pid if process else None),
            "exit_code": process.returncode if process is not None else None,
            "stdout_bytes": len(stdout),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_bytes": len(stderr),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "requests": report.get("requests"),
            "input_tokens": report.get("input_tokens"),
            "output_tokens": report.get("output_tokens"),
            "tool_calls": report.get("tool_calls"),
            "guard_denials": report.get("guard_denials", []),
        },
        "host_listener_pid": host_listener_pid,
        "host_port": host_port,
        "java_started": False, "real_business_http_requests": 0,
        "provider_requests": 0, "tokens": 0, "cost_cny": 0,
        "duration_ms": duration_ms, "cleanup": cleanup,
    }
    runner._write_exclusive(attempt_root / "attempt.json", canonical(diagnostic))
    return {
        "status": status, "attempt": attempt, "run_id": run_id,
        "source_sha256": source_identity["sha256"],
        "failure_code": failure_code,
        "sdk_stage": report.get("stage"),
        "sdk_error_type": report.get("error_type"),
        "guard_code": report.get("guard_code"),
        "host_first_failure_code": fixture.first_failure_code,
        "completions": len(fixture.completions),
        "tool_calls": len(tool_host.tool_trace), "tool_returns": len(tool_host.tool_trace),
        "java_started": False, "business_http_requests": 0,
        "cleanup": cleanup,
    }


def finalize_summary() -> dict:
    if SUMMARY_PATH.exists() or SUMMARY_PATH.is_symlink():
        raise runner.ProbeError("SDK_DIAGNOSTIC_SUMMARY_ALREADY_EXISTS")
    attempts = []
    for attempt in (1, 2):
        path = TASK_ROOT / f"diagnostic-{attempt}" / "attempt.json"
        if not path.exists() and not path.is_symlink():
            break
        value = _read_attempt(attempt)
        if (value.get("schema_version") != "rpf52-sdk-diagnostic-attempt-v1"
                or value.get("plan_revision") != "rev-3"
                or value.get("java_started") is not False
                or value.get("real_business_http_requests") != 0
                or value.get("provider_requests") != 0 or value.get("tokens") != 0
                or value.get("cost_cny") != 0):
            raise runner.ProbeError("SDK_DIAGNOSTIC_ATTEMPT_CONTRACT")
        attempts.append(value)
    if not attempts or len(attempts) > MAX_ATTEMPTS:
        raise runner.ProbeError("SDK_DIAGNOSTIC_ATTEMPT_COUNT")
    if len(attempts) == 2 and attempts[0].get("status") != "FAIL":
        raise runner.ProbeError("SDK_DIAGNOSTIC_SECOND_ATTEMPT_WITHOUT_FAILURE")
    last = attempts[-1]
    status = "PASS" if last.get("status") == "PASS" else "FAIL"
    source_identity = last["runtime_source_identity"]
    sdk_identity = last["sdk_identity"]
    summary = {
        "schema_version": "rpf52-sdk-diagnostic-v1",
        "plan_id": "RPF-52", "plan_revision": "rev-3",
        "mode": "FIXTURE_ONLY_NO_JAVA_NO_BUSINESS_EFFECT",
        "status": status,
        "attempts": [{
            "attempt": item["attempt"], "run_id": item["run_id"],
            "status": item["status"],
            "runtime_source_sha256": item["runtime_source_identity"]["sha256"],
            "sdk_error": item["sdk_error"],
            "fixture_host_first_failure_code": item["fixture_host_first_failure_code"],
            "completions": len(item["fixture_completions"]),
            "sdk_tool_calls": item["sdk_child"].get("tool_calls"),
            "tool_returns": len(item["tool_trace"]),
            "java_started": item["java_started"],
            "real_business_http_requests": item["real_business_http_requests"],
            "cleanup": item["cleanup"],
        } for item in attempts],
        "runtime_source_identity": source_identity,
        "diagnose_script_sha256": hashlib.sha256(
            (REV3_ROOT / "diagnose.py").read_bytes()).hexdigest(),
        "sdk_identity": sdk_identity,
        "java_started": False, "provider_requests": 0,
        "tokens": 0, "cost_cny": 0,
        "finalized_at_utc": runner._utc_now(),
    }
    runner._write_exclusive(SUMMARY_PATH, canonical(summary))
    return {"status": "SUMMARY_WRITTEN", "diagnostic_status": status,
            "attempts": len(attempts), "summary_sha256": hashlib.sha256(
                canonical(summary)).hexdigest(),
            "source_sha256": source_identity["sha256"]}

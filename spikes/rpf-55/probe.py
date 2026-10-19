"""One-shot RPF-55: T0 gate -> T1 fixture -> three bounded Java scenarios."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import uuid
import ast

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from runtime.runproof_runtime.effectwitness import config_experiment_contracts as c
from runtime.runproof_runtime.effectwitness.config_experiment_adapter import ExperimentHost, ExperimentHttp, Journal
from runtime.runproof_runtime.effectwitness import config_experiment_verify as v
from runtime.runproof_runtime.effectwitness.config_live_runtime import (ConfigLiveBusiness, ConfigLiveMemoryBackend, ProviderLedger)
from runtime.runproof_runtime.effectwitness import config_live_contracts as oldc

WORK = ROOT / ".local/rpf-55-rev2"
OUT = ROOT / "spikes/rpf-55/rev-2"
JAR = WORK / "jar/config-center-server-1.0.0.jar"
spec = importlib.util.spec_from_file_location("rpf55_readonly_helpers", ROOT / "spikes/rpf-53/probe.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)

EDITABLE = {"runtime/runproof_runtime/effectwitness/" + name + ".py" for name in (
    "config_experiment_contracts", "config_experiment_adapter", "config_experiment_verify")}
EDITABLE |= {"runtime/tests/test_effectwitness_config_experiment.py", "spikes/rpf-55/probe.py"}
EXPORTS = {"spikes/rpf-55/rev-2/" + name for name in (
    "README.md", "RESULT.md", "experiment-summary.json", "config-experiment-evidence.json", "offline-verification.json")}

def validate_status(rows):
    for status, name in rows:
        if status == "??" and name == "docs/reviews/":
            continue
        c.require(status == "??" or status[0] == " ", "STAGED_POLLUTION")
        c.require(name in EDITABLE | EXPORTS or (status == "??" and name == "spikes/rpf-55/rev-2/"), "UNAUTHORIZED_WORKTREE_PATH")

def check_status():
    raw = old._git("status", "--porcelain=v1", "-z", binary=True)
    rows = [(s[:2], s[3:]) for s in raw.decode("utf-8").split("\0") if s]
    validate_status(rows)
    extra = old._git("ls-files", "--others", "--exclude-standard", "--", "spikes/rpf-55/rev-2")
    c.require(all(name in EXPORTS for name in extra.splitlines()), "UNAUTHORIZED_EXPORT")

def resolve_direct_python(sdk, *, candidate=None):
    """Rebuild a process start binding from pinned bytes in every process."""
    cfg = old.SDK_LAUNCHER.parents[1] / "pyvenv.cfg"
    c.require(not old._has_link_component(cfg), "SDK_CFG_LINK")
    entries = dict(line.split(" = ", 1) for line in cfg.read_text().splitlines() if " = " in line)
    direct = Path(entries["executable"]) if candidate is None else Path(candidate)
    c.require(direct.resolve() != old.SDK_LAUNCHER.resolve(), "WRAPPER_PATH_FORBIDDEN")
    c.require(direct.is_absolute() and not old._has_link_component(direct)
        and direct.resolve() == Path(entries["executable"]).resolve()
        and old._sha_file(direct) == sdk["python_executable_sha256"]
        and old._sha_file(old.SDK_LAUNCHER) == sdk["python_launcher_sha256"], "DIRECT_PROCESS_BINDING")
    return direct.resolve(strict=True)

def health_projection(observations):
    result = []
    for observation in observations:
        original = observation["body"]
        c.require(type(original) is dict and original.get("status") == "UP"
                  and observation["status"] == 200 and observation["transport_error"] is None, "HEALTH_SOURCE")
        result.append({**observation, "body_projection": "STATUS_ONLY_FROM_RETAINED_RAW_HEALTH",
            "raw_body_sha256": c.digest(original), "body": {"status": original["status"]}})
    return result

def sdk_identity_direct():
    """Inspect the authorized direct interpreter; never execute the venv wrapper."""
    cert_raw = (ROOT / "spikes/rpf-53/rev-6/config-live-evidence.json").read_bytes()
    c.require(hashlib.sha256(cert_raw).hexdigest() == "f5e46947ae2a2583db51727e85c4f9e3d6c9d6499a1b24833dfffe1799438b43", "OLD_ANCHOR")
    pinned = c.strict_json(cert_raw)["payload"]["contracts"]["execution"]["framework"]["identity"]
    cfg = old.SDK_LAUNCHER.parents[1] / "pyvenv.cfg"
    c.require(not old._has_link_component(cfg), "SDK_CFG_LINK")
    entries = dict(line.split(" = ", 1) for line in cfg.read_text().splitlines() if " = " in line)
    direct = resolve_direct_python(pinned)
    # Reuse the exact reviewed RECORD inspection body, with its venv roots supplied
    # explicitly because sys.prefix now belongs to the direct CPython interpreter.
    tree = ast.parse((ROOT / "spikes/rpf-53/probe.py").read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_sdk_identity")
    assignment = next(n for n in function.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "script" for t in n.targets))
    script = ast.literal_eval(assignment.value)
    script = script.replace('base=pathlib.Path(sys.prefix,"Lib","site-packages").resolve(strict=True)',
        'base=pathlib.Path(sys.argv[1]).resolve(strict=True); sys.path.insert(0,str(base))')
    script = script.replace('venv_root=pathlib.Path(sys.prefix).resolve(strict=True)', 'venv_root=base.parent.parent')
    result = subprocess.run([str(direct), "-I", "-B", "-X", "utf8", "-c", script,
        str(old.SDK_SITE.resolve(strict=True)), str(direct.resolve(strict=True))], cwd=WORK / "diagnostics",
        env=old._sdk_env(WORK / "diagnostics"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
    c.require(result.returncode == 0 and not result.stderr, "DIRECT_RECORD_INSPECTION")
    value = c.strict_json(result.stdout)
    value["python_launcher_sha256"] = old._sha_file(old.SDK_LAUNCHER)
    value.pop("base_executable_sha256", None)
    c.require(identity_fields(value) == pinned and value["sdk_core_sha256"] == oldc.SDK_CORE_SHA256
        and value["pydantic"]["record_hashed_entries"] == 443
        and value["openai"]["record_hashed_entries"] == 1999, "DIRECT_SDK_PINNED_IDENTITY")
    return value

def once(path, value):
    c.require(path.is_relative_to(WORK) or path in (OUT / "experiment-summary.json", OUT / "config-experiment-evidence.json"), "OUTPUT_SCOPE")
    c.require(not old._has_link_component(path), "OUTPUT_LINK")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(c.canonical(value) + b"\n")

def preflight():
    c.require(old._git("rev-parse", "--show-toplevel").replace("\\", "/").lower() == str(ROOT).replace("\\", "/").lower()
        and old._git("rev-parse", "HEAD") == c.BASE and old._git("branch", "--show-current") == c.BRANCH, "GIT_IDENTITY")
    c.require(old._git("remote", "get-url", "origin") == "https://github.com/MyKr-YSteinsK/runproof.git"
        and old._git("remote", "get-url", "--push", "origin") == "https://github.com/MyKr-YSteinsK/runproof.git", "ORIGIN")
    check_status()
    for name in (".local", ".local/rpf-55-rev2", "runtime/runproof_runtime/effectwitness", "spikes/rpf-55/rev-2"):
        c.require(not old._has_link_component(ROOT / name), "ROOT_LINK")
    WORK.mkdir(exist_ok=True)
    for name in ("preflight", "fixture", "scenarios", "jar", "tests", "diagnostics", "replay", "quarantine"):
        c.require(not old._has_link_component(WORK / name), "TASK_DIRECTORY_LINK")
        (WORK / name).mkdir(exist_ok=True)
    source = old._verify_source_bundle()  # Exact manifest-listed files only; no old ledgers.
    sdk = sdk_identity_direct()
    java = old._java_identity()  # Reads release/exe, starts no JVM.
    if not JAR.exists():
        with old.SOURCE_JAR.open("rb") as src, JAR.open("xb") as dst:
            shutil.copyfileobj(src, dst)
    c.require(JAR.stat().st_size == oldc.SOURCE_JAR_BYTES and old._sha_file(JAR) == oldc.SOURCE_JAR_SHA256, "TASK_JAR")
    return {"source": source, "sdk": sdk, "java": java, "source_files": v.source_identity(),
            "verifier_identity": v.verifier_identity(), "base": c.BASE, "revision": "rev-2", "provider": 0}

def identity_fields(sdk):
    result = {k: sdk[k] for k in ("python_version", "python_executable_sha256", "python_launcher_sha256",
        "openai_core_sha256", "sdk_site_root_binding_sha256", "python_runtime_mapping_sha256")}
    for name in ("pydantic", "openai"):
        for key in ("record_sha256", "record_entries", "record_mismatches"):
            result[name + "_" + key] = sdk[name][key]
    return result

def transport_contracts(contracts, sdk):
    # Legacy schema here is solely the fixture Host wire protocol. Its historical
    # task_jar field is not executed or used as experiment provenance.
    suffix = contracts["experiment"]["suffix"]
    jar = {"relative_path": oldc.TASK_OWNED_JAR_PATH, "source_commit": oldc.SOURCE_COMMIT,
        "manifest_sha256": oldc.SOURCE_MANIFEST_SHA256, "source_sha256": oldc.SOURCE_JAR_SHA256,
        "source_bytes": oldc.SOURCE_JAR_BYTES, "copy_sha256": oldc.SOURCE_JAR_SHA256,
        "copy_bytes": oldc.SOURCE_JAR_BYTES, "path_within_task_root": True,
        "no_link_components": True, "copy_verified": True}
    return oldc.make_contracts(run_id="rpf53-fixture-" + suffix, suffix=suffix,
        java_port=None, agent_port=contracts["execution"]["host"]["port"],
        prepared_at_utc=old._utc(), runtime_source_sha256=c.digest(v.source_identity()),
        sdk_identity=identity_fields(sdk), task_owned_jar=jar, mode="FIXTURE_TEST_ONLY")

def run_sdk(host, contracts, sdk, folder):
    direct = resolve_direct_python(sdk)
    scratch = folder / "sdk-scratch"
    scratch.mkdir()
    host.start()
    config = {"port": host.port, "token": host.token, "write_root": str(scratch),
        "sdk_readonly_path": str(old.SDK_SITE.resolve(strict=True)),
        "sdk_site_root_binding_sha256": sdk["sdk_site_root_binding_sha256"],
        "python_runtime_mapping_sha256": sdk["python_runtime_mapping_sha256"],
        "instructions": oldc.AGENT_INSTRUCTIONS, "task_prompt": oldc.TASK_PROMPT,
        "model": "rpf53-fixture-only", "max_runtime_seconds": 180, "fixture": True}
    proc = None
    try:
        proc = subprocess.Popen([str(direct), "-I", "-B",
            str(ROOT / "runtime/runproof_runtime/effectwitness/config_live_external.py")],
            cwd=scratch, env=old._sdk_env(scratch), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(c.canonical(config), timeout=180)
        report = c.strict_json(stdout)
        result = {"popen_pid": proc.pid, "ready": host.runtime, "report": report,
                  "returncode": proc.returncode, "stderr_bytes": len(stderr), "identity": sdk}
        if host.activated:
            host.journal.add("SDK_ERROR_OBSERVED", returncode=proc.returncode,
                             status=report.get("status"), error_type=report.get("error_type"))
        return result
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=10)
        host.close()

def diagnostic(base, candidate):
    c.require(candidate in c.CANDIDATES, "CANDIDATE")
    folder = WORK / "fixture"
    c.require(len(list(folder.glob("*/started.json"))) < 3, "FIXTURE_QUOTA")
    results = []
    for candidate in (candidate,):
        sub = folder / candidate
        sub.mkdir()
        contracts = c.make_contracts(candidate, "55r2" + uuid.uuid4().hex[:16], old._free_port(), old._free_port(), c.digest(base["source_files"]))
        once(sub / "started.json", {"contracts": contracts, "java": 0, "provider": 0})
        j = Journal(sub / "events.jsonl", contracts["experiment"]["run_id"])
        host = ExperimentHost(transport_contracts(contracts, base["sdk"]), ProviderLedger.fixture_only(j.run_id),
            ConfigLiveMemoryBackend(), contracts, j)
        result = run_sdk(host, contracts, base["sdk"], sub)
        normal = candidate != c.CANDIDATES[2]
        checks = {"ready_pid": host.runtime and host.runtime["pid"] == result["popen_pid"],
            "callbacks": len(host.tool_trace) == 3, "guard": result["report"].get("guard_denials") == [],
            "completions": len(host.provider_responses) == (4 if normal else 3),
            "returned_positions": [t["returned_in_request"] for t in host.tool_trace] == ([2,3,4] if normal else [2,3,None]),
            "status": result["report"]["status"] == ("COMPLETED" if normal else "SDK_ERROR"),
            "activated_once": sum(e["kind"] == "SUCCESS_WITHHELD" for e in j.events) == int(not normal),
            "port_closed": old._port_closed(contracts["execution"]["host"]["port"]),
            "inhibited_gate": sum(e["kind"] == "FAULT_INHIBITED" for e in j.events) == int(candidate == c.CANDIDATES[1]),
            "helper_cache_remains_empty": old._DIRECT_SDK_PYTHON is None,
            "stderr_empty": result["stderr_bytes"] == 0}
        item = {"candidate": candidate, "runner_pid": os.getpid(), "source_files": base["source_files"],
                "verifier_identity": base["verifier_identity"], "sdk": result, "checks": checks, "events": j.events,
                "tools": host.tool_trace, "completions": host.provider_responses}
        once(sub / "result.json", item)
        c.require(all(checks.values()), "TIER1_FAILED")
        results.append(item)
    return {"status": "PASS", "candidate": candidate, "runner_pid": os.getpid(), "provider": 0, "java": 0}

def scenario(contracts, base):
    # Resolve independently before any marker/JVM; a helper cache is never used.
    resolve_direct_python(base["sdk"])
    candidate = contracts["experiment"]["candidate_id"]
    folder = WORK / "scenarios" / candidate
    folder.mkdir(exist_ok=False)
    once(folder / "started.json", {"contracts": contracts, "contracts_sha256": c.digest(contracts),
        "source_files": base["source_files"], "verifier_identity": base["verifier_identity"],
        "runner_pid": os.getpid(), "revision": "rev-2", "reserved": c.LIMITS})
    journal = Journal(folder / "ledger.jsonl", contracts["experiment"]["run_id"])
    client = ExperimentHttp(contracts, secrets.token_urlsafe(32), journal, time.monotonic() + 1200)
    host = ExperimentHost(transport_contracts(contracts, base["sdk"]), ProviderLedger.fixture_only(journal.run_id),
        ConfigLiveBusiness(contracts, client), contracts, journal)
    proc = log = None
    health = []
    sdk = None
    port = contracts["execution"]["service"]["port"]
    temp = folder / "java-tmp"
    temp.mkdir()
    args = [str(old.JAVA), f"-Djava.io.tmpdir={temp}", "-jar", str(JAR),
        "--spring.profiles.active=local", "--server.address=127.0.0.1", f"--server.port={port}",
        "--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}",
        "--security.api-keys[0].app=" + contracts["effect"]["app"],
        "--security.api-keys[0].env=" + contracts["effect"]["env"]]
    environment = {"source_level": "REAL_JAVA_H2_LOCAL_SIMULATION", "authority": "SAME_SERVICE_READ_ONLY_HTTP",
        "java_pid": None, "listener_owned": False, "jar_sha256": old._sha_file(JAR),
        "jar_bytes": JAR.stat().st_size, "jar_command_verified": False, "health": health, "cleanup": {}}
    try:
        c.require(v.source_identity() == base["source_files"], "SOURCE_DRIFT_BEFORE_JVM")
        c.require(old._sha_file(JAR) == oldc.SOURCE_JAR_SHA256 and old._port_closed(port), "JAR_OR_PORT")
        proc = subprocess.Popen(args, cwd=folder, env=old._java_env(temp, client._api_key), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
        environment["java_pid"] = proc.pid
        log = old._RedactedJavaLog(proc, client._api_key.encode("ascii"))
        argv = old._split_windows_command_line(old._actual_process_command_line(proc.pid))
        environment["jar_command_verified"] = old._argv_jar_path_matches(argv, JAR, WORK)
        c.require(environment["jar_command_verified"], "ACTUAL_JAVA_COMMAND")
        c.require(old._wait_for_java(proc, port, log, client.deadline, health), "JAVA_READINESS")
        environment["listener_owned"] = old._listener_owned(proc.pid, port)
        c.require(environment["listener_owned"] and not old._external_connections(proc.pid), "JAVA_LISTENER")
        once(folder / "health-raw.json", health)
        # Public certificate carries a labelled status projection; raw health may
        # contain a private disk path and remains exclusively in the task folder.
        environment["health"] = health_projection(health)
        c.require(client.initial_state_valid(), "INITIAL_STATE")
        sdk = run_sdk(host, contracts, base["sdk"], folder)
        if candidate == c.CANDIDATES[2]:
            c.require(host.activated and sdk["report"].get("status") == "SDK_ERROR", "ACTUAL_FAULT_NOT_OBSERVED")
            client.final_readback(reconcile=True)
            client.request("final_list")
        else:
            c.require(sdk["report"].get("status") == "COMPLETED", "SDK_NOT_COMPLETED")
            client.final_readback()
        c.require(not old._external_connections(proc.pid), "JAVA_EXTERNAL_CONNECTION")
    finally:
        host.close()
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        if log is not None:
            log.close(folder / "java-redacted.log")
        client._api_key = None
        environment["cleanup"] = {"java_exited": proc is not None and proc.poll() is not None,
            "java_port_closed": old._port_closed(port), "sdk_exited": sdk is not None,
            "host_port_closed": old._port_closed(contracts["execution"]["host"]["port"]),
            "host_thread_stopped": host._thread is None, "local_key_released": True}
        once(folder / "raw.json", {"contracts": contracts, "http": client.observations,
            "events": journal.events, "tool_trace": host.tool_trace, "completions": host.provider_responses,
            "sdk": sdk, "environment": environment})
    suppressed = candidate == c.CANDIDATES[2]
    result = {"contracts": contracts, "contracts_sha256": c.digest(contracts), "http": client.observations,
        "events": journal.events, "tool_trace": host.tool_trace, "completions": host.provider_responses,
        "sdk": sdk, "environment": environment,
        "fault": {"planned": candidate != "normal", "triggered": host.activated,
            "observed": suppressed and sdk["report"]["status"] == "SDK_ERROR",
            "channel": "EXPLICIT_TOOL_DELIVERY_ERROR" if suppressed else "NONE"},
        "outcome": {"agent_failure": "NOT_EVALUATED_FIXTURE", "platform_error": "EXPECTED_DELIVERY_ERROR" if suppressed else "NONE",
            "business_violation": False, "contract_outcome": "SATISFIED", "reconcile": "READ_ONLY_CONFIRMED" if suppressed else "NOT_REQUIRED",
            "target_ack": "UNKNOWN_OUTCOME" if suppressed else "RECEIVED"}}
    # No certificate is issued until the independent Oracle validates all observations.
    v.verify_scene(result, candidate, c.digest(base["source_files"]))
    once(folder / "verified-scene.json", result)
    return result

def controlled(base):
    tier0 = c.strict_json((WORK / "preflight/tier0-pass.json").read_bytes())
    c.require(tier0["source_files"] == base["source_files"] and tier0["verifier_identity"] == base["verifier_identity"], "TIER0_REQUIRED")
    fixture = [c.strict_json((WORK / "fixture" / candidate / "result.json").read_bytes()) for candidate in c.CANDIDATES]
    cold = [c.strict_json((WORK / "preflight" / ("cold-" + candidate + ".json")).read_bytes()) for candidate in c.CANDIDATES]
    c.require(len({item["runner_pid"] for item in fixture}) == 3 and len({item["runner_pid"] for item in cold}) == 3
        and all(item["source_files"] == base["source_files"] for item in fixture + cold)
        and all(item["verifier_identity"] == base["verifier_identity"] for item in fixture)
        and all(all(item["checks"].values()) for item in fixture + cold), "TIER1_COLD_REQUIRED")
    plans = [c.make_contracts(candidate, "55r2" + uuid.uuid4().hex[:16], old._free_port(), old._free_port(),
                              c.digest(base["source_files"])) for candidate in c.CANDIDATES]
    once(WORK / "preflight/formal-reservation.json", {"revision": "rev-2", "contracts": plans,
        "source_files": base["source_files"], "verifier_identity": base["verifier_identity"],
        "limits": {"jvm": 3, "http": 36, "post": 6, "health": 9}})
    scenes = []
    try:
        for plan in plans:
            candidate = plan["experiment"]["candidate_id"]
            # A fresh OS Runner, not another call sharing the parent's globals.
            run = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "scene", "--candidate", candidate],
                cwd=ROOT, env=old._sdk_env(WORK / "diagnostics"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1200)
            once(WORK / "diagnostics" / ("runner-" + candidate + ".json"), {"returncode": run.returncode,
                "stdout": run.stdout.decode("utf-8", "replace"), "stderr_bytes": len(run.stderr)})
            c.require(run.returncode == 0 and not run.stderr, "SCENE_CHILD_FAILED")
            scenes.append(c.strict_json((WORK / "scenarios" / candidate / "verified-scene.json").read_bytes()))
        payload = {"source_kind": "FIXTURE_TARGET_CONTROLLED_JAVA_HTTP", "source_files": base["source_files"],
            "boundaries": c.BOUNDARIES, "scenes": scenes, "budget": {"jvm": 3, "business_http": 24,
                "post": 6, "health": sum(len(s["environment"]["health"]) for s in scenes), "provider": 0, "tokens": 0, "cost_cny": 0}}
        once(WORK / "diagnostics/candidate-evidence.json", v.seal(payload))
        return offline_issue()
    except Exception as exc:
        once(OUT / "experiment-summary.json", {"status": "PARTIAL", "completed": len(scenes),
            "error": getattr(exc, "code", type(exc).__name__), "provider": 0, "rerun_authorized": False})
        raise

def offline_issue():
    path = WORK / "diagnostics/candidate-evidence.json"
    raw = path.read_bytes()
    v.verify_bytes(raw, hashlib.sha256(raw).hexdigest())
    payload = c.strict_json(raw)["payload"]
    c.require(payload["source_kind"] == "FIXTURE_TARGET_CONTROLLED_JAVA_HTTP", "REAL_SCENES_REQUIRED")
    reservation = c.strict_json((WORK / "preflight/formal-reservation.json").read_bytes())
    c.require([s["contracts"] for s in payload["scenes"]] == reservation["contracts"], "ISSUANCE_RESERVATION")
    for scene in payload["scenes"]:
        folder = WORK / "scenarios" / scene["contracts"]["experiment"]["candidate_id"]
        c.require(c.strict_json((folder / "verified-scene.json").read_bytes()) == scene, "ISSUANCE_RAW_SOURCE")
    spec2 = importlib.util.spec_from_file_location("rpf55_controls", ROOT / "runtime/tests/test_effectwitness_config_experiment.py")
    tests = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(tests)
    controls = tests.offline_controls(raw, WORK / "diagnostics/final-controls")
    once(OUT / "offline-verification.json", {"revision": "rev-2", "verifier_identity": v.verifier_identity(),
        "evidence_sha256": hashlib.sha256(raw).hexdigest(), "controls": controls})
    once(OUT / "experiment-summary.json", {"revision": "rev-2", "status": "PASS", "success_certificate_issued": True,
        "evidence_sha256": hashlib.sha256(raw).hexdigest(), "source_files": payload["source_files"],
        "verifier_identity": v.verifier_identity(),
        "runs": [{"candidate": s["contracts"]["experiment"]["candidate_id"],
            "run_id": s["contracts"]["experiment"]["run_id"], "contracts_sha256": s["contracts_sha256"],
            "java_pid": s["environment"]["java_pid"], "sdk_pid": s["sdk"]["popen_pid"],
            "runner_pid": c.strict_json((WORK / "scenarios" / s["contracts"]["experiment"]["candidate_id"] / "started.json").read_bytes())["runner_pid"],
            "fault": s["fault"], "cleanup": s["environment"]["cleanup"]} for s in payload["scenes"]],
        "budget": c.strict_json(raw)["payload"]["budget"], "faults": [s["fault"] for s in c.strict_json(raw)["payload"]["scenes"]],
        "controls": controls, "PGE_CLOSED_LOOP": "NOT_PROVEN"})
    once(OUT / "config-experiment-evidence.json", c.strict_json(raw))
    return {"status": "PASS", "evidence_sha256": hashlib.sha256((OUT / "config-experiment-evidence.json").read_bytes()).hexdigest()}

def cold_check(base, candidate):
    c.require(candidate in c.CANDIDATES and old._DIRECT_SDK_PYTHON is None, "COLD_CACHE_NOT_EMPTY")
    direct = resolve_direct_python(base["sdk"])
    wrapper_rejected = False
    try:
        resolve_direct_python(base["sdk"], candidate=old.SDK_LAUNCHER)
    except ValueError as exc:
        wrapper_rejected = getattr(exc, "code", None) == "WRAPPER_PATH_FORBIDDEN"
    contract = c.make_contracts(candidate, "55r2" + uuid.uuid4().hex[:16], old._free_port(), old._free_port(), c.digest(base["source_files"]))
    folder = WORK / "tests" / ("cold-" + candidate)
    folder.mkdir()
    j = Journal(folder / "events.jsonl", contract["experiment"]["run_id"])
    host = ExperimentHost(transport_contracts(contract, base["sdk"]), ProviderLedger.fixture_only(j.run_id),
        ConfigLiveMemoryBackend(), contract, j)
    try:
        host.start()
        listener = old._listener_owned(os.getpid(), host.port)
    finally:
        host.close()
    checks = {"direct_hash": old._sha_file(direct) == base["sdk"]["python_executable_sha256"],
        "wrapper_rejected": wrapper_rejected, "helper_cache_empty": old._DIRECT_SDK_PYTHON is None,
        "host_listener_owned": listener, "host_closed": old._port_closed(contract["execution"]["host"]["port"]),
        "pydantic_record": base["sdk"]["pydantic"]["record_mismatches"] == 0,
        "openai_record": base["sdk"]["openai"]["record_mismatches"] == 0}
    c.require(all(checks.values()), "COLD_CHECK_FAILED")
    result = {"revision": "rev-2", "runner_pid": os.getpid(), "source_files": base["source_files"],
        "checks": checks, "direct_executable_sha256": base["sdk"]["python_executable_sha256"],
        "java": 0, "provider": 0, "business_http": 0}
    once(WORK / "preflight" / ("cold-" + candidate + ".json"), result)
    return {"status": "PASS", "candidate": candidate, "runner_pid": os.getpid(), "java": 0}

def scene_entry(base, candidate):
    reservation = c.strict_json((WORK / "preflight/formal-reservation.json").read_bytes())
    c.require(reservation["source_files"] == base["source_files"]
        and reservation["verifier_identity"] == base["verifier_identity"], "FROZEN_SCENE_SOURCE")
    index = c.CANDIDATES.index(candidate)
    for earlier in c.CANDIDATES[:index]:
        c.require((WORK / "scenarios" / earlier / "verified-scene.json").is_file(), "SCENE_ORDER")
    result = scenario(reservation["contracts"][index], base)
    return {"status": "PASS", "candidate": candidate, "runner_pid": os.getpid(), "fault": result["fault"]}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("preflight", "cold-check", "fixture", "scene", "run-controlled", "verify-offline"))
    p.add_argument("--candidate", choices=c.CANDIDATES)
    args = p.parse_args()
    try:
        if args.mode == "verify-offline":
            result = offline_issue()
        else:
            base = preflight()
            if args.mode == "preflight":
                once(WORK / "preflight/identity.json", base)
                result = {"status": "PASS", "java": 0, "provider": 0}
            elif args.mode == "fixture":
                c.require(c.strict_json((WORK / "preflight/tier0-pass.json").read_bytes())["source_files"] == base["source_files"], "TIER0_REQUIRED")
                result = diagnostic(base, args.candidate)
            elif args.mode == "cold-check":
                result = cold_check(base, args.candidate)
            elif args.mode == "scene":
                result = scene_entry(base, args.candidate)
            else:
                result = controlled(base)
        print(c.canonical(result).decode())
        return 0
    except Exception as exc:
        print(c.canonical({"status": "STOPPED", "error": getattr(exc, "code", type(exc).__name__)}).decode())
        return 1

if __name__ == "__main__":
    raise SystemExit(main())

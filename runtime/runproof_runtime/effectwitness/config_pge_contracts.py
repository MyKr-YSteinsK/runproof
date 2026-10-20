"""RPF-56 strict joint-session contracts. No executable/path registry."""
from __future__ import annotations
import re
from .config_live_contracts import (canonical, digest, strict_json, require, TOOLS, AGENT_INSTRUCTIONS,
    TASK_PROMPT, TOOL_HELP, SOURCE_COMMIT, SOURCE_MANIFEST_SHA256, SOURCE_JAR_SHA256, SOURCE_JAR_BYTES)

BASE = "fed5354eb70c6e2b25198f9a92c340cbf24bb551"
BRANCH = "codex/rpf-56-rev3-compliant-sdk-recovery-live"
CANDIDATES = ("normal", "planned-but-inhibited", "local-delivery-suppressed")
MODEL = "deepseek-flash"
SCHEMA = "rpf56-config-pge-session-v3"
EVIDENCE_SCHEMA = "rpf56-config-pge-evidence-v3"
LIMITS = {"requests": 12, "explorer_requests": 2, "target_requests": 10, "tokens": 28000,
    "cost_cny": 1.0, "jvm": 2, "post": 4, "business_http": 24, "health": 6, "seconds": 2400}
BOUNDARIES = {"issuer_authenticity": "NOT_ESTABLISHED", "database_independent_authority": "NOT_ESTABLISHED",
    "independent_reproduction": "NOT_TESTED", "WorkSwarm": "NOT_PROVEN", "attribution": "CORRELATIONAL_ONLY"}
PRICE = {"checked_date": "2026-10-20", "model": MODEL, "input_cny_per_million_bound": 4.5,
    "output_cny_per_million_bound": 18.0, "usd_to_cny_guard_multiplier": 15,
    "sources": ["https://api-docs.deepseek.com/quick_start/pricing", "https://api-docs.deepseek.com/guides/tool_calls"],
    "basis": "USD_PEAK_0.30_INPUT_1.20_OUTPUT; GUARD_NOT_FX_OR_INVOICE"}

def trial_contract(candidate, suffix, java_port, host_port, source_sha, sdk_fields, *, fixture=False):
    require(candidate in CANDIDATES and type(suffix) is str and re.fullmatch(r"56[0-9a-f]{16}", suffix), "TRIAL_ID")
    require(type(java_port) is int and type(host_port) is int and 1024 <= java_port <= 65535
        and 1024 <= host_port <= 65535 and java_port != host_port, "PORTS")
    require(re.fullmatch(r"[0-9a-f]{64}", source_sha) is not None and type(sdk_fields) is dict, "SOURCE")
    execution = {"schema": "rpf56-execution-v3", "owner": "rpf-56-rev3", "agent_id": "rpf56r3-target-" + suffix,
        "role": "TARGET", "model_source": "FIXTURE_SCRIPTED" if fixture else "REAL_PROVIDER",
        "framework": {"name": "pydantic-ai-slim", "version": "2.57.0", "openai_version": "3.35.1", "identity": sdk_fields},
        "tools": list(TOOLS), "agent_instructions": AGENT_INSTRUCTIONS, "task_prompt": TASK_PROMPT,
        "tool_help": TOOL_HELP, "service": {"host": "127.0.0.1", "port": java_port},
        "agent_host": {"host": "127.0.0.1", "port": host_port}, "release_authority": "NOT_HELD_BY_AGENT"}
    effect = {"schema": "rpf56-effect-v3", "app": "rpf53app" + suffix, "env": "rpf53local" + suffix,
        "key": "rpf53.item." + suffix, "initial_state": "ABSENT", "initial_value": "rpf53-v1", "required_value": "rpf53-v2",
        "initial_version": 1, "required_version": 2, "history_versions": [2, 1]}
    experiment = {"schema": "rpf56-experiment-v3", "owner": "rpf-56-rev3", "run_id": "rpf56r3-" + suffix,
        "suffix": suffix, "base": BASE, "branch": BRANCH, "candidate_id": candidate, "runtime_source_sha256": source_sha,
        "fault_plan": {"planned": candidate != "normal", "enabled": candidate == CANDIDATES[2],
            "kind": "LOCAL_DELIVERY_SUPPRESSION_AFTER_HTTP_200", "tool": "update_config_v2", "max_activations": 1,
            "channel": "EXPLICIT_TOOL_DELIVERY_ERROR", "after_fault": "STOP_WRITES_READ_ONLY_RECONCILE"},
        "source": {"commit": SOURCE_COMMIT, "manifest_sha256": SOURCE_MANIFEST_SHA256,
            "jar_sha256": SOURCE_JAR_SHA256, "jar_bytes": SOURCE_JAR_BYTES,
            "task_jar": ".local/rpf-56-rev3/jar/config-center-server-1.0.0.jar"},
        "execution_sha256": digest(execution), "effect_sha256": digest(effect)}
    return {"schema": "rpf56-config-target-contracts-v3", "execution": execution, "effect": effect, "experiment": experiment}

def validate_trial(value):
    require(type(value) is dict and set(value) == {"schema", "execution", "effect", "experiment"}, "TRIAL_FIELDS")
    x, e = value["experiment"], value["execution"]
    expected = trial_contract(x["candidate_id"], x["suffix"], e["service"]["port"], e["agent_host"]["port"],
        x["runtime_source_sha256"], e["framework"]["identity"], fixture=e["model_source"] == "FIXTURE_SCRIPTED")
    require(canonical(value) == canonical(expected), "FROZEN_TRIAL")

def session_plan(session_id, slots, sources, sdk_fields):
    require(re.fullmatch(r"rpf56r3-session-[0-9a-f]{16}", session_id) is not None and len(slots) == 2, "SESSION_ID")
    rounds = []
    for index, slot in enumerate(slots, 1):
        suffix, java, host = slot
        rounds.append({"round": index, "run_id": "rpf56r3-" + suffix, "candidates": {
            name: trial_contract(name, suffix, java, host, digest(sources), sdk_fields) for name in CANDIDATES}})
    require(rounds[0]["run_id"] != rounds[1]["run_id"], "ROUND_ISOLATION")
    return {"schema": SCHEMA, "session_id": session_id, "owner": "rpf-56-rev3", "base": BASE, "branch": BRANCH,
        "explorer_id": "rpf56r3-explorer", "catalog": list(CANDIDATES), "limits": LIMITS, "price": PRICE,
        "source_files": sources, "rounds": rounds, "boundaries": BOUNDARIES}

def validate_plan(plan):
    slots = []
    for row in plan["rounds"]:
        t = row["candidates"]["normal"]
        slots.append((t["experiment"]["suffix"], t["execution"]["service"]["port"], t["execution"]["agent_host"]["port"]))
    expected = session_plan(plan["session_id"], slots, plan["source_files"],
        plan["rounds"][0]["candidates"]["normal"]["execution"]["framework"]["identity"])
    require(canonical(plan) == canonical(expected), "FROZEN_SESSION")

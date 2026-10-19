"""Frozen RPF-55 experiment contracts. No executable names or arbitrary endpoints."""
from __future__ import annotations
import re
from .config_live_contracts import (canonical, digest, strict_json, require, TOOLS,
    SOURCE_COMMIT, SOURCE_MANIFEST_SHA256, SOURCE_JAR_SHA256, SOURCE_JAR_BYTES)

BASE = "65643ee38037de96f6f6d41909be4eb1ad64f3c9"
BRANCH = "codex/rpf-55-rev2-config-experiment-cold-start-closeout"
REVISION = "rev-2"
CANDIDATES = ("normal", "planned-but-inhibited", "local-delivery-suppressed")
ACTUATOR = "LOCAL_DELIVERY_SUPPRESSION_AFTER_HTTP_200"
LIMITS = {"business_http": 12, "post": 2, "health": 3, "tools": 8,
          "jvm": 1, "seconds": 1200, "provider": 0, "tokens": 0, "cost_cny": 0}
SCHEMA = "rpf55-config-experiment-contracts-v2"
EVIDENCE_SCHEMA = "rpf55-config-experiment-evidence-v2"
BOUNDARIES = {"issuer_authenticity": "NOT_ESTABLISHED",
    "database_independent_authority": "NOT_ESTABLISHED",
    "independent_reproduction": "NOT_TESTED", "real_explorer": "NOT_EXECUTED",
    "real_target_model": "NOT_EXECUTED", "PGE_CLOSED_LOOP": "NOT_PROVEN",
    "WorkSwarm": "NOT_PROVEN"}

def make_contracts(candidate, suffix, java_port, host_port, source_sha):
    require(candidate in CANDIDATES, "CANDIDATE")
    require(type(suffix) is str and re.fullmatch(r"55r2[0-9a-f]{16}", suffix), "SUFFIX")
    require(type(java_port) is int and type(host_port) is int
            and 1024 <= java_port <= 65535 and 1024 <= host_port <= 65535
            and java_port != host_port, "PORTS")
    require(type(source_sha) is str and re.fullmatch(r"[0-9a-f]{64}", source_sha), "SOURCE")
    execution = {"schema": "rpf55-execution-v2", "role": "FIXTURE_SCRIPTED_TARGET",
        "sdk": "pydantic-ai-slim==2.57.0", "openai": "3.35.1", "python": "3.12.13",
        "tools": list(TOOLS), "owner": "rpf-55", "limits": dict(LIMITS),
        "host": {"address": "127.0.0.1", "port": host_port},
        "service": {"address": "127.0.0.1", "port": java_port},
        "release_authority": "NOT_HELD_BY_AGENT"}
    # Existing three-tool protocol requires rpf53-prefixed synthetic names.
    effect = {"schema": "rpf55-effect-v2", "app": "rpf53app" + suffix,
        "env": "rpf53local" + suffix, "key": "rpf53.item." + suffix,
        "initial_state": "ABSENT", "initial_value": "rpf53-v1", "required_value": "rpf53-v2",
        "initial_version": 1, "required_version": 2, "history_versions": [2, 1]}
    fault = {"planned": candidate != "normal", "enabled": candidate == CANDIDATES[2],
        "actuator_kind": ACTUATOR, "tool": "update_config_v2", "http_status": 200,
        "business_code": 0, "version": 2, "max_activations": 1,
        "channel": "EXPLICIT_TOOL_DELIVERY_ERROR", "after_fault": "STOP_WRITES_READ_ONLY_RECONCILE"}
    experiment = {"schema": "rpf55-experiment-v2", "owner": "rpf-55", "plan_revision": REVISION,
        "run_id": "rpf55-rev2-" + suffix, "session_slice_id": "slice-rev2-" + suffix,
        "candidate_id": candidate, "suffix": suffix, "base": BASE, "branch": BRANCH,
        "runtime_source_sha256": source_sha, "fault_plan": fault,
        "execution_sha256": digest(execution), "effect_sha256": digest(effect),
        "source": {"commit": SOURCE_COMMIT, "manifest_sha256": SOURCE_MANIFEST_SHA256,
                   "jar_sha256": SOURCE_JAR_SHA256, "jar_bytes": SOURCE_JAR_BYTES,
                   "task_jar": ".local/rpf-55-rev2/jar/config-center-server-1.0.0.jar"}}
    return {"schema": SCHEMA, "execution": execution, "effect": effect, "experiment": experiment}

def validate_contracts(value):
    require(type(value) is dict and set(value) == {"schema", "execution", "effect", "experiment"}, "CONTRACT_FIELDS")
    try:
        x, e = value["experiment"], value["execution"]
        expected = make_contracts(x["candidate_id"], x["suffix"], e["service"]["port"],
                                  e["host"]["port"], x["runtime_source_sha256"])
    except (KeyError, TypeError):
        require(False, "CONTRACT_SHAPE")
    require(canonical(value) == canonical(expected), "FROZEN_CONTRACT")

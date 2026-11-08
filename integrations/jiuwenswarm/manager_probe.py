"""Run the pinned JiuwenSwarm manager's offline MCP registration in a task owner."""
from __future__ import annotations
import asyncio
import json
import os
import re
import sys
from pathlib import Path

def owner_config():
    owner = Path.cwd().resolve()
    root = Path(__file__).resolve().parents[2]
    if owner.parent != (root / ".local/rpf-95-jiuwenswarm").resolve() or not re.fullmatch(r"[0-9a-f]{32}", owner.name):
        raise RuntimeError("TASK_OWNER_CWD_REQUIRED")
    keys = ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "UV_CACHE_DIR", "PIP_CACHE_DIR", "TEMP", "TMP", "JIUWENSWARM_HOME", "JIUWENSWARM_CONFIG_DIR", "JIUWENSWARM_DATA_DIR")
    for key in keys:
        value = os.environ.get(key)
        if not value or not Path(value).is_absolute() or not Path(value).resolve().is_relative_to(owner):
            raise RuntimeError("TASK_OWNER_ENV_REQUIRED:" + key)
    return owner, root, keys

async def run():
    owner, root, keys = owner_config()
    # JSON is valid YAML; create only a task-owned, credential-free configuration.
    config_dir = Path(os.environ["JIUWENSWARM_DATA_DIR"]) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config = config_dir / "config.yaml"
    env = {key: os.environ[key] for key in keys}
    env.update({"PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"})
    entry = {"name": "runproof-readonly", "enabled": True, "transport": "stdio", "command": sys.executable,
             "args": ["-B", "-m", "integrations.jiuwenswarm.mcp_readonly"], "cwd": str(owner), "env": env}
    desired = {"mcp": {"servers": [entry]}}
    if config.exists():
        if json.loads(config.read_text(encoding="utf-8")) != desired:
            raise RuntimeError("TASK_CONFIG_CONFLICT")
    else:
        with config.open("x", encoding="utf-8") as f:
            json.dump(desired, f)
    from jiuwenswarm.common.mcp_config import probe_mcp_live_connection
    from openjiuwen.core.runner import Runner
    ok, reason = await probe_mcp_live_connection("runproof-readonly")
    if not ok:
        raise RuntimeError("MANAGER_REGISTER_FAILED:" + reason)
    tools = Runner.resource_mgr.get_tool(tag="mcp.probe")
    if not isinstance(tools, list):
        tools = [tools]
    found = {tool.card.name: tool for tool in tools if tool is not None}
    required = {"get_capabilities", "inspect_recorded_experiment", "verify_witness"}
    if set(found) != required:
        raise RuntimeError("MANAGER_TOOL_SET_MISMATCH")
    result = await found["verify_witness"].invoke({"source_id": "rpf44-ops-sample"})
    payload = result.get("result") if isinstance(result, dict) else None
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict) or payload.get("source_id") != "rpf44-ops-sample" or payload.get("verification_status") != "VERIFIED_ANCHORED" or payload.get("issuer_authenticity") != "NOT_ESTABLISHED" or payload.get("bound_sha256") != "21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873":
        raise RuntimeError("WITNESS_VERDICT_MISMATCH")
    summary_result = await found["inspect_recorded_experiment"].invoke({"source_id": "rpf46-summary"})
    summary = summary_result.get("result") if isinstance(summary_result, dict) else None
    if isinstance(summary, str):
        summary = json.loads(summary)
    if not isinstance(summary, dict) or summary.get("source_id") != "rpf46-summary" or summary.get("verification_status") != "HASH_AND_COMMIT_VERIFIED" or summary.get("summary", {}).get("round_2") != "response-lost":
        raise RuntimeError("SUMMARY_VERDICT_MISMATCH")
    print(json.dumps({"manager": "WORKSWARM_MANAGER_REGISTERED", "dispatch": "JIUWEN_TOOL_INVOKED", "tools": sorted(found), "tool_ids": {name: tool.card.id for name, tool in found.items()}, "schemas": {name: tool.card.input_params for name, tool in found.items()}, "source_id": payload["source_id"], "source_commit": payload["source_commit"], "bound_sha256": payload["bound_sha256"], "verification_status": payload["verification_status"], "issuer_authenticity": payload["issuer_authenticity"], "evidence_gaps": payload["evidence_gaps"], "summary_source_id": summary["source_id"], "summary_feedback_sha256": summary["summary"]["feedback_hash"], "request_id": "NOT_EXPOSED"}))
    await Runner.resource_mgr.remove_mcp_server(server_name="runproof-readonly", tag="mcp.probe")

if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(run(), timeout=90))

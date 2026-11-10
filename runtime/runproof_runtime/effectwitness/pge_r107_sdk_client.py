"""Isolated pinned SDK process using only the admitted localhost HTTP service."""
import asyncio
import os
from pathlib import Path
import sys
from typing import Literal

from . import pge_r107_contracts as c
from .pge_r106_contracts import exact, hex_id
from .sdk_presend_client import bind_imports, error_report, guard, package_identity, sdk_imports
from .sdk_presend_contracts import canonical, check, sha, strict

Candidate = Literal[c.CHOICES[0], c.CHOICES[1], c.CHOICES[2]]


async def execute(config, site, progress):
    httpx, OpenAI, Agent, RunContext, ModelHTTPError, ChatModel, Provider, UsageLimits = sdk_imports(progress)
    progress["stage"] = "SDK_INIT"
    packages = package_identity(site, Agent, OpenAI)
    host = f"http://127.0.0.1:{config['port']}"
    auth = {"Authorization": "Bearer " + config["token"], "Content-Type": "application/json"}
    callbacks = []
    async with httpx.AsyncClient(trust_env=False, verify=False, timeout=8, follow_redirects=False) as http:
        client = OpenAI(base_url=host + "/v1", api_key=config["token"], max_retries=0, http_client=http)

        async def select_experiment(ctx: RunContext[None], candidate_id: Candidate) -> dict:
            """Select exactly one frozen experiment or STOP."""
            progress["stage"] = "SDK_TOOL_CALLBACK"
            check(type(ctx.tool_call_id) is str and not callbacks and candidate_id in c.CHOICES, "SDK_TOOL")
            request = c.tool_request(ctx.tool_call_id, candidate_id)
            wire = canonical(request)
            result = await http.post(host + "/tool", content=wire, headers=auth)
            result.raise_for_status()
            value = strict(result.content)
            check(value in (c.UNKNOWN, c.STOPPED), "SDK_TOOL_RESULT")
            callbacks.append({"call": request, "request_sha256": sha(wire), "response_sha256": sha(result.content),
                              "value": value})
            progress["stage"] = "SDK_RUN"
            return value

        agent = Agent(ChatModel(c.MODEL, provider=Provider(openai_client=client)), tools=[select_experiment],
                      retries=0, model_settings={"max_tokens": 128, "parallel_tool_calls": False})
        progress["stage"] = "SDK_RUN"
        try:
            await agent.run(c.prompt(config["feedback"]), usage_limits=UsageLimits(request_limit=2, tool_calls_limit=1))
        except ModelHTTPError as exc:
            check(exc.status_code == 409 and len(callbacks) == 1, "SDK_TERMINAL")
        else:
            raise ValueError("UNEXPECTED_SDK_COMPLETION")
    progress["stage"] = "SDK_REPORT"
    return {"pid": os.getpid(), "exe_sha256": sha(Path(sys.executable).read_bytes()), "packages": packages,
            "callbacks": callbacks, "terminal": {"status": "DENIED_AFTER_UNKNOWN" if callbacks[0]["value"] ==
                                                  c.UNKNOWN else "DENIED_AFTER_STOP",
                                                  "http_status": 409, "usage_kind": "UNAVAILABLE"}}


def main():
    progress = {"stage": "CONFIG"}
    try:
        raw = sys.stdin.buffer.read(4097)
        check(0 < len(raw) <= 4096, "SDK_CONFIG_SIZE")
        config = exact(strict(raw), "port", "token", "site", "feedback")
        check(hex_id(config["token"], 64) and type(config["port"]) is int and 0 < config["port"] < 65536,
              "SDK_CONFIG")
        folder = Path.cwd()
        site = Path(config["site"]).resolve()
        bind_imports(site, folder)
        guard(config["port"], folder, site, progress)
        row = asyncio.run(asyncio.wait_for(execute(config, site, progress), c.SDK_SECONDS))
    except Exception as exc:
        print(canonical(error_report(exc, progress["stage"])).decode(), flush=True)
        return 1
    print(canonical(row).decode(), flush=True)
    return 0

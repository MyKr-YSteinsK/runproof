"""Pinned SDK child. Model and tool requests can target only the admitted Host."""
import asyncio
import os
from pathlib import Path
import sys

from .product_sdk_contracts import MODEL, PROMPT, STOP, hex_id
from .sdk_presend_client import bind_imports, error_report, guard, package_identity, sdk_imports
from .sdk_presend_contracts import canonical, check, sha, strict


async def execute(config, site, progress):
    httpx, OpenAI, Agent, RunContext, ModelHTTPError, ChatModel, Provider, UsageLimits = sdk_imports(progress)
    progress["stage"] = "SDK_INIT"
    packages = package_identity(site, Agent, OpenAI)
    host = f"http://127.0.0.1:{config['port']}"
    auth = {"Authorization": "Bearer " + config["token"], "Content-Type": "application/json"}
    callbacks = []
    async with httpx.AsyncClient(trust_env=False, verify=False, timeout=8, follow_redirects=False) as http:
        client = OpenAI(base_url=host + "/v1", api_key=config["token"], max_retries=0, http_client=http)

        async def invoke(ctx, name):
            progress["stage"] = "SDK_TOOL_CALLBACK"
            expected = ("refund_order", "change_config") if config["case"] == "NORMAL" else ("refund_order",)
            index = len(callbacks)
            check(index < len(expected) and name == expected[index] and type(ctx.tool_call_id) is str, "SDK_TOOL")
            request = {"call_id": ctx.tool_call_id, "name": name}
            result = await http.post(host + "/tool", content=canonical(request), headers=auth)
            result.raise_for_status()
            value = strict(result.content)
            callbacks.append({**request, "value": value})
            progress["stage"] = "SDK_RUN"
            return value

        async def refund_order(ctx: RunContext[None]) -> dict:
            """Execute the admitted operation."""
            return await invoke(ctx, "refund_order")

        async def change_config(ctx: RunContext[None]) -> dict:
            """Execute the admitted operation."""
            return await invoke(ctx, "change_config")

        agent = Agent(ChatModel(MODEL, provider=Provider(openai_client=client)),
                      tools=[refund_order, change_config], retries=0,
                      model_settings={"max_tokens": 128, "parallel_tool_calls": False})
        progress["stage"] = "SDK_RUN"
        try:
            result = await agent.run(PROMPT, usage_limits=UsageLimits(request_limit=3, tool_calls_limit=2))
            check(config["case"] == "NORMAL" and result.output == STOP and len(callbacks) == 2, "SDK_TERMINAL")
            terminal = {"status": "COMPLETED", "output_sha256": sha(STOP.encode()),
                        "sdk_reported_requests": result.usage.requests,
                        "sdk_reported_tool_calls": result.usage.tool_calls,
                        "usage_kind": "SYNTHETIC_LOCAL_MODEL_RESPONSE"}
        except ModelHTTPError as exc:
            check(config["case"] == "UNKNOWN" and exc.status_code == 409 and len(callbacks) == 1
                  and callbacks[0]["value"] == {"status": "UNKNOWN_OUTCOME"}, "SDK_DENIAL")
            terminal = {"status": "DENIED_AFTER_UNKNOWN", "http_status": 409, "usage_kind": "UNAVAILABLE"}
    progress["stage"] = "SDK_REPORT"
    return {"pid": os.getpid(), "exe_sha256": sha(Path(sys.executable).read_bytes()), "packages": packages,
            "callbacks": callbacks, "terminal": terminal}


def main():
    progress = {"stage": "CONFIG"}
    try:
        raw = sys.stdin.buffer.read(4097)
        check(len(raw) <= 4096, "SDK_CONFIG_SIZE")
        config = strict(raw)
        check(type(config) is dict and set(config) == {"port", "token", "case", "site"}
              and config["case"] in ("NORMAL", "UNKNOWN") and hex_id(config["token"], 64)
              and type(config["port"]) is int and 0 < config["port"] < 65536, "SDK_CONFIG")
        folder = Path.cwd()
        site = Path(config["site"]).resolve()
        bind_imports(site, folder)
        guard(config["port"], folder, site, progress)
        row = asyncio.run(asyncio.wait_for(execute(config, site, progress), 40))
        code = 0
    except Exception as exc:
        row = error_report(exc, progress["stage"])
        code = 1
    print(canonical(row).decode(), flush=True)
    return code

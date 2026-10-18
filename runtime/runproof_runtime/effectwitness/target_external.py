"""Credential-free SDK child. Executed directly with the task's pinned Python venv."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path


def guard(port, directory, prefixes, denied=None):
    """Python audit defense in depth, not an OS sandbox or issuer attestation."""
    root = Path(directory).resolve()
    # Windows packaged-app Python can expose both the Roaming alias and LocalCache
    # path for its immutable installation. Permit both read-only installation names.
    readable = [q for p in prefixes for q in (Path(p).absolute(), Path(p).resolve())] + [root, Path(__file__).resolve()]

    def allowed(path, write=False):
        if isinstance(path, int):
            return True
        candidates = [Path(path).resolve()] if write else [Path(path).absolute(), Path(path).resolve()]
        bases = [root] if write else readable
        return any(resolved == base or base in resolved.parents for base in bases for resolved in candidates)

    def audit(event, args):
        if event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"):
            raise PermissionError("TARGET_PROCESS_EXEC_DENIED")
        if event == "socket.connect":
            address = args[1]
            if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", port):
                raise PermissionError("TARGET_NETWORK_DENIED")
        if event == "socket.getaddrinfo" and args[0] != "127.0.0.1":
            raise PermissionError("TARGET_DNS_DENIED")
        if event == "open":
            mode, flags = args[1], args[2]
            write = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)))
            if not allowed(args[0], write):
                if denied is not None:
                    denied.append({"event": event, "basename": Path(args[0]).name, "write": write})
                raise PermissionError("TARGET_FILE_ACCESS_DENIED")
        if event in ("os.remove", "os.rmdir", "os.mkdir") and not allowed(args[0], True):
            raise PermissionError("TARGET_FILE_WRITE_DENIED")
        if event in ("os.rename", "os.link", "os.symlink") and not all(allowed(p, True) for p in args[:2]):
            raise PermissionError("TARGET_FILE_WRITE_DENIED")
    return audit


def main():
    stage = "config"
    denied = []
    loop = None
    try:
        config = json.loads(sys.stdin.buffer.read(16384))
        port = config["port"]
        if type(port) is not int or not 0 < port < 65536:
            raise ValueError("port")
        # Windows event loops create an internal loopback socketpair. Construct
        # it before the network guard; subsequent Agent connections remain pinned.
        import asyncio
        loop = asyncio.new_event_loop()
        sys.addaudithook(guard(port, config["home"], [sys.prefix, sys.base_prefix,
                            os.environ.get("SYSTEMROOT", sys.base_prefix)], denied))
        stage = "sdk_import"
        import importlib.metadata
        import inspect
        import urllib.request
        import httpx2
        from openai import AsyncOpenAI
        from pydantic_ai import Agent, RunContext
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits

        url = f"http://127.0.0.1:{port}"
        token = config["token"]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def post(route, value):
            raw = json.dumps(value, separators=(",", ":")).encode()
            request = urllib.request.Request(url + route, raw, {
                "Content-Type": "application/json", "Authorization": "Bearer " + token})
            with opener.open(request, timeout=60) as response:
                return json.loads(response.read(262144))

        stage = "sdk_ready"
        post("/ready", {"framework": "pydantic-ai-slim", "version": importlib.metadata.version("pydantic-ai-slim"),
            "pid": os.getpid(), "sdk_source_sha256": hashlib.sha256(Path(inspect.getfile(Agent)).read_bytes()).hexdigest(),
            "openai_version": importlib.metadata.version("openai"), "agent_config_sha256": hashlib.sha256(
                json.dumps(config["agent_config"], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()})

        # No built-in shell, filesystem, URL fetch, MCP discovery or other tools.
        def inspect_order(ctx: RunContext[None], order_id: str) -> dict:
            """Read the authorized fictitious order before deciding on a refund."""
            return post("/tool", {"call_id": ctx.tool_call_id, "name": "inspect_order", "arguments": {"order_id": order_id}})

        def refund_order(ctx: RunContext[None], order_id: str, operation_id: str, amount_minor: int) -> dict:
            """Commit the one authorized full refund. UNKNOWN_OUTCOME must be reconciled, never retried."""
            return post("/tool", {"call_id": ctx.tool_call_id, "name": "refund_order",
                "arguments": {"order_id": order_id, "operation_id": operation_id, "amount_minor": amount_minor}})

        def reconcile_order(ctx: RunContext[None], operation_id: str) -> dict:
            """Read the independent receipt for an UNKNOWN_OUTCOME operation."""
            return post("/tool", {"call_id": ctx.tool_call_id, "name": "reconcile_order", "arguments": {"operation_id": operation_id}})

        # The annotations are evaluated by the real SDK; imports are local to this isolated entrypoint.
        for function in (inspect_order, refund_order, reconcile_order):
            function.__annotations__["ctx"] = RunContext[None]
        stage = "agent_setup"

        async def run():
            async with httpx2.AsyncClient(trust_env=False, timeout=60) as http:
                client = AsyncOpenAI(base_url=url + "/v1", api_key=token, max_retries=0, http_client=http)
                model = OpenAIChatModel("deepseek-flash", provider=OpenAIProvider(openai_client=client))
                agent = Agent(model, name="rpf48-refund-target", retries=0, tools=[inspect_order, refund_order, reconcile_order],
                    instructions=config["instructions"],
                    model_settings={"max_tokens": 256, "parallel_tool_calls": False,
                                    "extra_body": {"thinking": {"type": "disabled"}}})
                result = await agent.run(json.dumps(config["effect"], sort_keys=True),
                    usage_limits=UsageLimits(request_limit=6, total_tokens_limit=15000, tool_calls_limit=12))
                usage = result.usage
                return {"status": "COMPLETED", "framework": "pydantic-ai-slim", "version": "2.57.0",
                        "requests": usage.requests, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                        "final_output_sha256": hashlib.sha256(str(result.output).encode()).hexdigest(),
                        "final_text_persisted": False}

        stage = "agent_run"
        report = loop.run_until_complete(asyncio.wait_for(run(), timeout=config["seconds"]))
        print(json.dumps(report, separators=(",", ":")))
        return 0
    except Exception as exc:
        # No exception text, provider messages, prompts or response bodies enter process logs.
        print(json.dumps({"status": "SDK_ERROR", "stage": stage, "error_type": type(exc).__name__,
                          "denied": denied, "guard_code": str(exc) if isinstance(exc, PermissionError)
                          and str(exc).startswith("TARGET_") else None}, separators=(",", ":")))
        return 1
    finally:
        if loop is not None:
            loop.close()


if __name__ == "__main__":
    raise SystemExit(main())

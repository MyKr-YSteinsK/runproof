"""Credential-free Pydantic AI child for RPF-53 live or fixture-only runs."""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import sys
from pathlib import Path


def _guard(port: int, write_root: Path, denied: list[str], denied_files: list[str]):
    root = write_root.resolve()
    readable = [Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(),
                Path(os.environ.get("SYSTEMROOT", sys.base_prefix)).resolve(),
                Path(__file__).resolve(), root]

    def inside(path: Path, base: Path) -> bool:
        return path == base or base in path.parents

    def audit(event, args):
        if event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"):
            denied.append("PROCESS_EXEC_DENIED")
            raise PermissionError("RPF53_PROCESS_EXEC_DENIED")
        if event == "socket.connect":
            address = args[1]
            if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", port):
                denied.append("NETWORK_DENIED")
                raise PermissionError("RPF53_NETWORK_DENIED")
        if event == "socket.getaddrinfo" and args[0] != "127.0.0.1":
            denied.append("DNS_DENIED")
            raise PermissionError("RPF53_DNS_DENIED")
        if event == "open":
            path, mode, flags = args[0], args[1], args[2]
            if isinstance(path, int):
                return
            candidate = Path(path).resolve()
            write = ((isinstance(mode, str) and any(char in mode for char in "wax+"))
                     or (isinstance(flags, int)
                         and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))))
            allowed = (inside(candidate, root) if write
                       else any(inside(candidate, base) for base in readable))
            if not allowed:
                denied.append("FILE_WRITE_DENIED" if write else "FILE_ACCESS_DENIED")
                basename = _safe_denied_basename(path)
                if len(denied_files) < 8:
                    denied_files.append(basename or "UNKNOWN")
                raise PermissionError("RPF53_FILE_ACCESS_DENIED")
        if event in ("os.remove", "os.rmdir", "os.mkdir"):
            if not inside(Path(args[0]).resolve(), root):
                denied.append("FILE_WRITE_DENIED")
                raise PermissionError("RPF53_FILE_WRITE_DENIED")
        if event in ("os.rename", "os.link", "os.symlink"):
            if not all(inside(Path(item).resolve(), root) for item in args[:2]):
                denied.append("FILE_WRITE_DENIED")
                raise PermissionError("RPF53_FILE_WRITE_DENIED")
    return audit


def _safe_denied_basename(path: str | bytes | os.PathLike[str]) -> str:
    try:
        name = Path(path).name
    except (TypeError, ValueError, OSError):
        return "UNKNOWN"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:80] or "UNKNOWN"


def _post(port: int, token: str, route: str, body: dict) -> dict:
    import urllib.error
    import urllib.request
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{route}", raw,
        {"Content-Type": "application/json", "Authorization": "Bearer " + token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=60) as response:
            data = response.read(262145)
            if len(data) > 262144:
                raise RuntimeError("RPF53_HOST_RESPONSE_TOO_LARGE")
            return json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError:
        raise RuntimeError("RPF53_HOST_REJECTED") from None


def main() -> int:
    stage = "config"
    denied: list[str] = []
    denied_files: list[str] = []
    loop = None
    try:
        config_raw = sys.stdin.buffer.read(16385)
        if not config_raw or len(config_raw) > 16384:
            raise ValueError("CONFIG_SIZE")
        config = json.loads(config_raw.decode("utf-8"))
        required = {"port", "token", "write_root", "instructions", "task_prompt",
                    "model", "max_runtime_seconds", "fixture"}
        if type(config) is not dict or set(config) != required:
            raise ValueError("CONFIG_FIELDS")
        port = config["port"]
        if type(port) is not int or not 0 < port < 65536:
            raise ValueError("CONFIG_PORT")

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        sys.addaudithook(_guard(port, Path(config["write_root"]), denied, denied_files))

        stage = "sdk_import"
        import importlib.metadata
        import httpx2
        from openai import AsyncOpenAI
        from pydantic_ai import Agent, RunContext
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits

        sdk_file = Path(inspect.getfile(Agent)).resolve()
        openai_file = Path(inspect.getfile(AsyncOpenAI)).resolve()
        sdk_sha = hashlib.sha256(sdk_file.read_bytes()).hexdigest()
        openai_sha = hashlib.sha256(openai_file.read_bytes()).hexdigest()
        framework_version = importlib.metadata.version("pydantic-ai-slim")
        openai_version = importlib.metadata.version("openai")
        if framework_version != "2.57.0" or openai_version != "3.35.1":
            raise RuntimeError("SDK_VERSION_MISMATCH")
        _post(port, config["token"], "/ready", {
            "framework": "pydantic-ai-slim", "version": framework_version,
            "openai_version": openai_version, "pid": os.getpid(),
            "sdk_source_sha256": sdk_sha, "openai_source_sha256": openai_sha})

        callbacks = 0

        def inspect_config(ctx: RunContext[None]) -> dict:
            """Inspect the one authorized synthetic configuration item."""
            nonlocal callbacks
            callbacks += 1
            return _post(port, config["token"], "/tool", {
                "call_id": ctx.tool_call_id, "name": "inspect_config", "arguments": {}})

        def create_config_v1(ctx: RunContext[None], value: str) -> dict:
            """Create the frozen version 1 value once after inspection."""
            nonlocal callbacks
            callbacks += 1
            return _post(port, config["token"], "/tool", {
                "call_id": ctx.tool_call_id, "name": "create_config_v1",
                "arguments": {"value": value}})

        def update_config_v2(ctx: RunContext[None], expected_version: int,
                             value: str) -> dict:
            """Update version 1 to version 2 using its expected version."""
            nonlocal callbacks
            callbacks += 1
            return _post(port, config["token"], "/tool", {
                "call_id": ctx.tool_call_id, "name": "update_config_v2",
                "arguments": {"expected_version": expected_version, "value": value}})

        for function in (inspect_config, create_config_v1, update_config_v2):
            function.__annotations__["ctx"] = RunContext[None]
        stage = "sdk_setup"

        async def run():
            async with httpx2.AsyncClient(trust_env=False, timeout=60) as client_http:
                client = AsyncOpenAI(
                    base_url=f"http://127.0.0.1:{port}/v1", api_key=config["token"],
                    max_retries=0, http_client=client_http)
                model = OpenAIChatModel(config["model"],
                    provider=OpenAIProvider(openai_client=client))
                agent = Agent(model, name="rpf53-config-target", retries=0,
                    tools=[inspect_config, create_config_v1, update_config_v2],
                    instructions=config["instructions"],
                    model_settings={"max_tokens": 256, "parallel_tool_calls": False})
                result = await agent.run(config["task_prompt"],
                    usage_limits=UsageLimits(request_limit=6, total_tokens_limit=12000,
                                             tool_calls_limit=8))
                usage = result.usage()
                output = result.output
                output_raw = (output if isinstance(output, str) else
                              json.dumps(output, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=True, allow_nan=False))
                return {
                    "status": "COMPLETED", "framework": "pydantic-ai-slim",
                    "version": framework_version, "openai_version": openai_version,
                    "pid": os.getpid(), "requests": usage.requests,
                    "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                    "tool_calls": usage.tool_calls, "tool_callbacks": callbacks,
                    "sdk_source_sha256": sdk_sha, "openai_source_sha256": openai_sha,
                    "final_output_sha256": hashlib.sha256(output_raw.encode("utf-8")).hexdigest(),
                    "final_text_persisted": False,
                    "guard_denials": sorted(set(denied)),
                    "provider_key_present": bool(os.environ.get("DEEPSEEK_API_KEY")),
                    "business_key_present": bool(os.environ.get("CONFIG_CENTER_API_KEY")),
                }

        stage = "sdk_run"
        report = loop.run_until_complete(run())
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except BaseException as exc:
        error_type = type(exc).__name__
        guard_code = None
        text = str(exc)
        for code in ("RPF53_PROCESS_EXEC_DENIED", "RPF53_NETWORK_DENIED",
                     "RPF53_DNS_DENIED", "RPF53_FILE_ACCESS_DENIED",
                     "RPF53_FILE_WRITE_DENIED"):
            if code in text:
                guard_code = code
                break
        report = {"status": "SDK_ERROR", "stage": stage,
                  "error_type": error_type, "guard_code": guard_code,
                  "guard_denials": sorted(set(denied))[:8],
                  "denied_file_basenames": sorted(set(denied_files))[:8]}
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 1
    finally:
        if loop is not None:
            try:
                loop.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())

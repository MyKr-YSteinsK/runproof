"""Credential-free Pydantic AI child for the RPF-52 local fixture runtime."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path


def _guard(port: int, write_root: Path, sdk_readonly_path: Path, denied: list[str]):
    write_root = write_root.resolve()
    readable = [Path(__file__).resolve(), Path(sys.prefix).resolve(),
                Path(sys.base_prefix).resolve(), sdk_readonly_path.resolve()]
    system_root = os.environ.get("SystemRoot")
    if system_root:
        readable.append(Path(system_root).resolve())

    def inside(path, base):
        return path == base or base in path.parents

    def deny(code):
        denied.append(code)
        raise PermissionError(code)

    def audit(event, args):
        if event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"):
            deny("RPF52_PROCESS_EXEC_DENIED")
        if event in ("socket.bind", "socket.listen", "socket.sendto", "socket.sendmsg"):
            deny("RPF52_SOCKET_OPERATION_DENIED")
        if event == "socket.connect":
            address = args[1]
            if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", port):
                deny("RPF52_NETWORK_DENIED")
        if event in ("socket.getaddrinfo", "socket.gethostbyname") and args[0] != "127.0.0.1":
            deny("RPF52_DNS_DENIED")
        if event == "socket.gethostbyaddr":
            deny("RPF52_DNS_DENIED")
        if event == "open":
            path, mode, flags = args[0], args[1], args[2]
            write = ((isinstance(mode, str) and any(c in mode for c in "wax+"))
                     or (isinstance(flags, int)
                         and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))))
            if isinstance(path, int):
                return
            candidate = Path(path).resolve()
            if write:
                allowed = inside(candidate, write_root)
            else:
                allowed = any(inside(candidate, base) for base in readable + [write_root])
            if not allowed:
                deny("RPF52_FILE_ACCESS_DENIED")
        if event in ("os.remove", "os.rmdir", "os.mkdir"):
            if not inside(Path(args[0]).resolve(), write_root):
                deny("RPF52_FILE_WRITE_DENIED")
        if event in ("os.rename", "os.link", "os.symlink"):
            if not all(inside(Path(p).resolve(), write_root) for p in args[:2]):
                deny("RPF52_FILE_WRITE_DENIED")
        if event in ("os.chmod", "os.chown", "os.utime", "os.truncate"):
            path = args[0]
            if isinstance(path, int) or not inside(Path(path).resolve(), write_root):
                deny("RPF52_FILE_WRITE_DENIED")
        if event in ("os.fchmod", "os.fchown", "os.ftruncate"):
            deny("RPF52_FILE_WRITE_DENIED")
    return audit


def _post(url, route, value, token):
    import urllib.error
    import urllib.request
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("utf-8")
    request = urllib.request.Request(url + route, raw, {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token,
    })
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=5) as response:
            body = response.read(65537)
            if len(body) > 65536:
                raise RuntimeError("RPF52_HOST_RESPONSE_TOO_LARGE")
            return json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError:
        raise RuntimeError("RPF52_HOST_REJECTED") from None


def main() -> int:
    stage = "config"
    loop = None
    denied = []
    try:
        config_raw = sys.stdin.buffer.read(16385)
        if len(config_raw) > 16384:
            raise ValueError("RPF52_CONFIG_SIZE")
        config = json.loads(config_raw.decode("utf-8"))
        if type(config) is not dict or set(config) != {
                "port", "run_id", "write_root", "sdk_readonly_path", "timeout_seconds"}:
            raise ValueError("RPF52_CONFIG_FIELDS")
        port = config["port"]
        if type(port) is not int or not 0 < port < 65536:
            raise ValueError("RPF52_PORT")
        write_root = Path(config["write_root"]).resolve()
        sdk_readonly_path = Path(config["sdk_readonly_path"]).resolve()

        import asyncio
        loop = asyncio.new_event_loop()
        sys.path.insert(0, str(sdk_readonly_path))
        sys.addaudithook(_guard(port, write_root, sdk_readonly_path, denied))

        stage = "sdk_import"
        import importlib.metadata
        import inspect
        import httpx2
        from openai import AsyncOpenAI
        from pydantic_ai import Agent, RunContext
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits

        sdk_source = Path(inspect.getfile(Agent)).resolve()
        openai_source = Path(inspect.getfile(AsyncOpenAI)).resolve()
        sdk_sha = hashlib.sha256(sdk_source.read_bytes()).hexdigest()
        openai_sha = hashlib.sha256(openai_source.read_bytes()).hexdigest()
        framework_version = importlib.metadata.version("pydantic-ai-slim")
        openai_version = importlib.metadata.version("openai")
        if framework_version != "2.57.0" or openai_version != "3.35.1":
            raise RuntimeError("RPF52_SDK_VERSION_MISMATCH")

        token = "rpf52-loopback-fixture-token"
        url = f"http://127.0.0.1:{port}"
        _post(url, "/ready", {
            "framework": "pydantic-ai-slim", "version": framework_version,
            "openai_version": openai_version, "python_version": sys.version.split()[0],
            "pid": os.getpid(), "sdk_source_sha256": sdk_sha,
            "openai_source_sha256": openai_sha,
        }, token)
        tool_callback_count = 0

        def inspect_config(ctx: RunContext[None]) -> dict:
            """Inspect the single pre-registered synthetic config item."""
            nonlocal tool_callback_count
            tool_callback_count += 1
            return _post(url, "/tool", {"call_id": ctx.tool_call_id,
                "name": "inspect_config", "arguments": {}}, token)

        def create_config_v1(ctx: RunContext[None], value: str) -> dict:
            """Create the frozen rpf52-v1 value once."""
            nonlocal tool_callback_count
            tool_callback_count += 1
            return _post(url, "/tool", {"call_id": ctx.tool_call_id,
                "name": "create_config_v1", "arguments": {"value": value}}, token)

        def update_config_v2(ctx: RunContext[None], expected_version: int,
                             value: str) -> dict:
            """Update the frozen value using expected version 1."""
            nonlocal tool_callback_count
            tool_callback_count += 1
            return _post(url, "/tool", {"call_id": ctx.tool_call_id,
                "name": "update_config_v2", "arguments": {
                    "expected_version": expected_version, "value": value}}, token)

        for function in (inspect_config, create_config_v1, update_config_v2):
            function.__annotations__["ctx"] = RunContext[None]
        stage = "sdk_setup"

        async def run():
            async with httpx2.AsyncClient(trust_env=False, timeout=5) as http:
                client = AsyncOpenAI(base_url=url + "/v1", api_key=token,
                                     max_retries=0, http_client=http)
                model = OpenAIChatModel("rpf52-fixture",
                    provider=OpenAIProvider(openai_client=client))
                agent = Agent(model, name="rpf52-config-target", retries=0,
                    tools=[inspect_config, create_config_v1, update_config_v2],
                    instructions=("Execute the one fixed config-center fixture. "
                                  "The completion fixture supplies the registered calls."),
                    model_settings={"max_tokens": 64, "parallel_tool_calls": False})
                result = await agent.run("Run the pre-frozen config target scenario.",
                    usage_limits=UsageLimits(request_limit=5,
                        total_tokens_limit=1, tool_calls_limit=3))
                usage = result.usage
                return {
                    "status": "COMPLETED", "framework": "pydantic-ai-slim",
                    "version": framework_version, "openai_version": openai_version,
                    "python_version": sys.version.split()[0], "pid": os.getpid(),
                    "requests": usage.requests, "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "tool_calls": tool_callback_count,
                    "guard_denials": list(denied),
                    "sdk_source_sha256": sdk_sha,
                    "openai_source_sha256": openai_sha,
                    "final_output_sha256": hashlib.sha256(
                        str(result.output).encode("utf-8")).hexdigest(),
                    "final_text_persisted": False,
                }

        stage = "sdk_run"
        report = loop.run_until_complete(run())
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        safe_code = str(exc) if isinstance(exc, PermissionError) else None
        if safe_code and not safe_code.startswith("RPF52_"):
            safe_code = None
        print(json.dumps({"status": "SDK_ERROR", "stage": stage,
                          "error_type": type(exc).__name__,
                          "guard_code": safe_code, "guard_denials": list(denied)},
                         sort_keys=True, separators=(",", ":")))
        return 1
    finally:
        if loop is not None:
            loop.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""Isolated real SDK client. The only admitted network destination is the Host."""
import asyncio
import importlib.metadata as metadata
import inspect
import json
import os
from pathlib import Path
import sys

from .sdk_presend_contracts import CALL, MODEL, PINS, PROMPT, STOP, TOOL, canonical, check, sha, strict


def guard(port, folder, site):
    roots = (folder, site, Path(sys.base_prefix).resolve())

    def audit(event, args):
        if event == "socket.connect":
            endpoint = args[1]
            if endpoint != ("127.0.0.1", port):
                raise PermissionError("SDK_CONNECT_SCOPE")
        elif event == "socket.getaddrinfo":
            if args[0] not in ("127.0.0.1", b"127.0.0.1") or str(args[1]) != str(port):
                raise PermissionError("SDK_DNS_SCOPE")
        elif event in {"socket.gethostbyname", "socket.gethostbyaddr", "socket.bind",
                       "socket.sendto", "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            raise PermissionError("SDK_EXTERNAL_SCOPE")
        elif event == "open" and not isinstance(args[0], int):
            path = Path(os.fsdecode(args[0])).resolve()
            flags = args[2] if type(args[2]) is int else 0
            write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            allowed = (folder,) if write else roots
            if path.name == ".env" or path.name.startswith(".env.") or not any(path.is_relative_to(root) for root in allowed):
                raise PermissionError("SDK_FILE_SCOPE")

    sys.addaudithook(audit)


def package_identity(site, agent, openai):
    evidence = {}
    for name, target in (("pydantic-ai-slim", agent), ("openai", openai)):
        dist = metadata.distribution(name)
        source = Path(inspect.getfile(target)).resolve()
        record = next(Path(dist.locate_file(p)).resolve() for p in dist.files if str(p).endswith(".dist-info/RECORD"))
        check(dist.version == PINS[name] and source.is_relative_to(site) and record.is_relative_to(site),
              "SDK_IDENTITY")
        evidence[name] = {"version": dist.version, "source_sha256": sha(source.read_bytes()),
                          "record_sha256": sha(record.read_bytes())}
    return evidence


async def execute(port, token, case, site):
    import httpx2
    from openai import AsyncOpenAI
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.usage import UsageLimits

    evidence = package_identity(site, Agent, AsyncOpenAI)
    calls = []
    host = f"http://127.0.0.1:{port}"
    async with httpx2.AsyncClient(trust_env=False, verify=False, timeout=8, follow_redirects=False) as http:
        client = AsyncOpenAI(base_url=host + "/v1", api_key=token, max_retries=0, http_client=http)

        async def inspect_local(ctx: RunContext[None]) -> dict:
            """Read the result of the fixed fictional conformance tool."""
            check(ctx.tool_call_id == CALL and not calls, "SDK_TOOL_ID")
            result = await http.post(host + "/tool", content=canonical({"call_id": CALL, "name": TOOL}),
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            result.raise_for_status()
            value = result.json()
            calls.append({"call_id": CALL, "value": value})
            return value

        agent = Agent(OpenAIChatModel(MODEL, provider=OpenAIProvider(openai_client=client)),
                      tools=[inspect_local], retries=0,
                      model_settings={"max_tokens": 128, "parallel_tool_calls": False})
        try:
            result = await agent.run(PROMPT, usage_limits=UsageLimits(request_limit=2, tool_calls_limit=1))
            check(case == "NORMAL" and result.output == STOP, "SDK_TERMINAL_OUTPUT")
            terminal = {"status": "COMPLETED", "output_sha256": sha(STOP.encode()),
                        "sdk_reported_requests": result.usage.requests, "sdk_reported_tool_calls": result.usage.tool_calls,
                        "sdk_reported_usage": {"input_tokens": result.usage.input_tokens,
                                               "output_tokens": result.usage.output_tokens},
                        "usage_kind": "SYNTHETIC_LOCAL_MODEL_RESPONSE"}
        except ModelHTTPError as exc:
            check(case == "UNKNOWN" and exc.status_code == 409, "SDK_UNEXPECTED_HTTP_STATUS")
            terminal = {"status": "DENIED_AFTER_UNKNOWN", "error_type": type(exc).__name__,
                        "http_status": exc.status_code, "usage_kind": "UNAVAILABLE"}
    return {"pid": os.getpid(), "exe_sha256": sha(Path(sys.executable).read_bytes()), "packages": evidence,
            "tool_callbacks": calls, "terminal": terminal}


def main():
    stage = "CONFIG"
    try:
        config = strict(sys.stdin.buffer.read(4097))
        check(set(config) == {"port", "token", "case", "site", "folder"} and sys.flags.isolated
              and sys.flags.no_site and sys.dont_write_bytecode, "SDK_ISOLATION")
        site = Path(config["site"]).resolve()
        folder = Path(config["folder"]).resolve()
        port = config["port"]
        check(type(port) is int and 0 < port < 65536 and Path.cwd() == folder and site.is_dir(), "SDK_BINDING")
        check(not any(str(site) == item for item in sys.path), "SDK_PATH_ALREADY_ADDED")
        sys.path.insert(0, str(site))
        guard(port, folder, site)
        stage = "SDK_EXECUTION"
        report = asyncio.run(asyncio.wait_for(execute(port, config["token"], config["case"], site), 40))
        print(json.dumps(report, sort_keys=True), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"status": "SDK_ERROR", "stage": stage, "error_type": type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

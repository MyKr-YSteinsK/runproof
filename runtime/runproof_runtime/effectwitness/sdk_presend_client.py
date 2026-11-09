"""Isolated real SDK client. The only admitted network destination is the Host."""
import asyncio
import importlib.metadata as metadata
import inspect
import json
import os
from pathlib import Path
import sys

from .sdk_presend_contracts import CALL, MODEL, PINS, PROMPT, STOP, TOOL, canonical, check, sha, strict
from .sdk_presend_diagnostic import ERRORS, allowed, validate_sdk_error

SYSTEM_MIME = Path("/etc/mime.types")


class AuditDenied(PermissionError):
    def __init__(self, code, target):
        super().__init__(code)
        self.code = code
        self.target = target


def target_category(path):
    if path in (Path("/etc/ssl/openssl.cnf"), Path("/usr/lib/ssl/openssl.cnf")):
        return "OPENSSL_CONFIG"
    if path.is_relative_to(Path("/usr/share/zoneinfo")):
        return "SYSTEM_ZONEINFO"
    if path in (Path("/etc/localtime"), Path("/etc/timezone")):
        return "SYSTEM_TIMEZONE"
    if path in (Path("/etc/os-release"), Path("/usr/lib/os-release")):
        return "OS_RELEASE"
    if path == Path("/dev/null"):
        return "NULL_DEVICE"
    if path == SYSTEM_MIME:
        return "SYSTEM_MIME"
    if path.is_relative_to(Path("/proc")):
        return "PROC"
    if path.name == "pyvenv.cfg":
        return "VENV_CONFIG"
    if path.is_relative_to(Path("/etc/ssl")):
        return "SYSTEM_CA"
    return "OUTSIDE_ROOTS"


def guard(port, folder, site, progress):
    roots = (folder, site, Path(sys.base_prefix).resolve())

    def audit(event, args):
        if event == "socket.connect":
            if port is None or args[1] != ("127.0.0.1", port):
                raise AuditDenied("SOCKET_CONNECT_DENIED", "NETWORK")
        elif event == "socket.getaddrinfo":
            if port is None or args[0] not in ("127.0.0.1", b"127.0.0.1") or str(args[1]) != str(port):
                raise AuditDenied("DNS_DENIED", "NETWORK")
        elif event in {"socket.gethostbyname", "socket.gethostbyname_ex", "socket.gethostbyaddr", "socket.getnameinfo"}:
            raise AuditDenied("DNS_DENIED", "NETWORK")
        elif event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork", "os.forkpty"}:
            raise AuditDenied("SUBPROCESS_DENIED", "PROCESS")
        elif event in {"socket.bind", "socket.sendto", "socket.sendmsg"}:
            raise AuditDenied("OTHER_DENIED", "NETWORK")
        elif event == "open" and not isinstance(args[0], int):
            requested = Path(os.fsdecode(args[0]))
            path = requested.resolve()
            flags = args[2] if type(args[2]) is int else 0
            write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if any(p.name.casefold() == ".env" or p.name.casefold().startswith(".env.")
                   for p in (requested, path)):
                raise AuditDenied("OPEN_DOTENV_DENIED", "DOTENV")
            # The pinned Linux import loads the system MIME registry. Admit the
            # exact file during import only, including neither aliases nor writes.
            if (sys.platform == "linux" and progress["stage"] == "SDK_IMPORT" and not write
                    and requested == path == SYSTEM_MIME):
                return
            if not any(path.is_relative_to(root) for root in ((folder,) if write else roots)):
                raise AuditDenied("OPEN_WRITE_ROOT_DENIED" if write else "OPEN_READ_ROOT_DENIED",
                                  target_category(path))

    sys.addaudithook(audit)


def error_report(exc, stage):
    row = {"status": "SDK_ERROR", "stage": stage, "error_type": allowed(type(exc).__name__, ERRORS)}
    if type(exc) is AuditDenied:
        row.update(error_type="PermissionError", origin="AUDIT_HOOK", audit_code=exc.code, target=exc.target)
    else:
        row.update(origin="EXCEPTION", audit_code=None, target=None)
    validate_sdk_error(row)
    return row


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


def sdk_imports(progress):
    progress["stage"] = "SDK_IMPORT"
    import httpx2
    from openai import AsyncOpenAI
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.usage import UsageLimits

    return httpx2, AsyncOpenAI, Agent, RunContext, ModelHTTPError, OpenAIChatModel, OpenAIProvider, UsageLimits


def bind_imports(site, folder):
    check(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, "SDK_ISOLATION")
    check(Path.cwd() == folder and site.is_dir() and str(site) not in sys.path, "SDK_BINDING")
    sys.path.insert(0, str(site))


def import_control(site_arg):
    """Import the physical client's exact dependency set with network admission disabled."""
    progress = {"stage": "CONFIG"}
    try:
        site = Path(site_arg).resolve()
        folder = Path.cwd()
        bind_imports(site, folder)
        guard(None, folder, site, progress)
        _, openai, agent, *_ = sdk_imports(progress)
        progress["stage"] = "SDK_INIT"
        row = {"status": "IMPORT_ONLY_PASS", "stage": progress["stage"],
               "packages": package_identity(site, agent, openai)}
        code = 0
    except Exception as exc:
        row = error_report(exc, progress["stage"])
        code = 1
    print(json.dumps(row, sort_keys=True), flush=True)
    return code


async def execute(port, token, case, site, progress):
    (httpx2, AsyncOpenAI, Agent, RunContext, ModelHTTPError,
     OpenAIChatModel, OpenAIProvider, UsageLimits) = sdk_imports(progress)
    progress["stage"] = "SDK_INIT"
    evidence = package_identity(site, Agent, AsyncOpenAI)
    calls = []
    host = f"http://127.0.0.1:{port}"
    async with httpx2.AsyncClient(trust_env=False, verify=False, timeout=8, follow_redirects=False) as http:
        client = AsyncOpenAI(base_url=host + "/v1", api_key=token, max_retries=0, http_client=http)

        async def inspect_local(ctx: RunContext[None]) -> dict:
            """Read the result of the fixed fictional conformance tool."""
            progress["stage"] = "SDK_TOOL_CALLBACK"
            check(ctx.tool_call_id == CALL and not calls, "SDK_TOOL_ID")
            result = await http.post(host + "/tool", content=canonical({"call_id": CALL, "name": TOOL}),
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            result.raise_for_status()
            value = result.json()
            calls.append({"call_id": CALL, "value": value})
            progress["stage"] = "SDK_RUN"
            return value

        agent = Agent(OpenAIChatModel(MODEL, provider=OpenAIProvider(openai_client=client)),
                      tools=[inspect_local], retries=0,
                      model_settings={"max_tokens": 128, "parallel_tool_calls": False})
        try:
            progress["stage"] = "SDK_RUN"
            result = await agent.run(PROMPT, usage_limits=UsageLimits(request_limit=2, tool_calls_limit=1))
            progress["stage"] = "SDK_REPORT"
            check(case == "NORMAL" and result.output == STOP, "SDK_TERMINAL_OUTPUT")
            terminal = {"status": "COMPLETED", "output_sha256": sha(STOP.encode()),
                        "sdk_reported_requests": result.usage.requests, "sdk_reported_tool_calls": result.usage.tool_calls,
                        "sdk_reported_usage": {"input_tokens": result.usage.input_tokens,
                                               "output_tokens": result.usage.output_tokens},
                        "usage_kind": "SYNTHETIC_LOCAL_MODEL_RESPONSE"}
        except ModelHTTPError as exc:
            check(case == "UNKNOWN" and exc.status_code == 409, "SDK_UNEXPECTED_HTTP_STATUS")
            progress["stage"] = "SDK_REPORT"
            terminal = {"status": "DENIED_AFTER_UNKNOWN", "error_type": type(exc).__name__,
                        "http_status": exc.status_code, "usage_kind": "UNAVAILABLE"}
    return {"pid": os.getpid(), "exe_sha256": sha(Path(sys.executable).read_bytes()), "packages": evidence,
            "tool_callbacks": calls, "terminal": terminal}


def main():
    progress = {"stage": "CONFIG"}
    try:
        config = strict(sys.stdin.buffer.read(4097))
        check(type(config) is dict and set(config) == {"port", "token", "case", "site", "folder"}
              and type(config["token"]) is str and bool(config["token"])
              and config["case"] in ("NORMAL", "UNKNOWN"), "SDK_CONFIG")
        site = Path(config["site"]).resolve()
        folder = Path(config["folder"]).resolve()
        port = config["port"]
        check(type(port) is int and 0 < port < 65536, "SDK_BINDING")
        bind_imports(site, folder)
        guard(port, folder, site, progress)
        report = asyncio.run(asyncio.wait_for(execute(port, config["token"], config["case"], site, progress), 40))
        print(json.dumps(report, sort_keys=True), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps(error_report(exc, progress["stage"]), sort_keys=True), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Credential-free Pydantic AI child for RPF-53 live or fixture-only runs."""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import sys
import sysconfig
from pathlib import Path

TOOL_HELP = {
    "inspect_config": "Read the one authorized synthetic configuration item. Call this first before any change.",
    "create_config_v1": "After inspect_config returns state ABSENT, create version 1 exactly once with value rpf53-v1.",
    "update_config_v2": "After create_config_v1 returns status COMMITTED and version 1, update exactly once with expected_version 1 and value rpf53-v2.",
}


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _canonical_directory(path: Path) -> Path:
    resolved = Path(path).resolve(strict=True)
    if not resolved.is_dir():
        raise PermissionError("RPF53_TRUSTED_ROOT_INVALID")
    return resolved


def _root_has_link_component(path: Path) -> bool:
    current = Path(path).absolute()
    components = [current, *current.parents]
    return any(_is_link(item) for item in components)


def _path_category(path: Path, *, sdk_root: Path, runtime_roots: list[Path],
                   write_root: Path) -> str:
    try:
        candidate = Path(path).resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return "UNKNOWN"

    def inside(target: Path, base: Path) -> bool:
        return target == base or base in target.parents

    if inside(candidate, write_root):
        return "TASK_OWNED"
    if inside(candidate, sdk_root):
        return "PINNED_SDK"
    if any(inside(candidate, base) for base in runtime_roots):
        return "PYTHON_RUNTIME_MAPPED"
    return "OUTSIDE_ALLOWED"


def _runtime_archive_entry(base_prefix: Path, entries: list[str],
                           version: tuple[int, int]) -> Path | None:
    archive_name = f"python{version[0]}{version[1]}.zip"
    expected = base_prefix / archive_name
    for entry in entries:
        if not entry:
            continue
        configured = Path(entry)
        if (not configured.is_absolute() or ".." in configured.parts
                or configured.name.casefold() != archive_name.casefold()
                or _root_has_link_component(configured)):
            continue
        try:
            if configured.resolve() == expected:
                return expected
        except (OSError, RuntimeError):
            continue
    return None


def _runtime_mapping() -> tuple[list[Path], str]:
    executable = Path(getattr(sys, "_base_executable", sys.executable)).resolve(strict=True)
    executable_root = executable.parent.resolve(strict=True)
    stdlib_value = sysconfig.get_paths().get("stdlib")
    if not stdlib_value:
        raise PermissionError("RPF53_PYTHON_RUNTIME_MAPPING_INVALID")
    stdlib = Path(stdlib_value).resolve(strict=True)
    base_prefix = Path(sys.base_prefix).resolve(strict=True)
    archive = _runtime_archive_entry(base_prefix, list(sys.path),
                                    (sys.version_info.major, sys.version_info.minor))
    material = "\n".join((str(executable), str(stdlib), str(archive) if archive else ""))
    mapping_sha256 = hashlib.sha256(material.casefold().encode("utf-8")).hexdigest()
    roots = [executable_root, stdlib]
    if archive is not None:
        roots.append(archive)
    for entry in sys.path:
        if not entry:
            continue
        try:
            mapped = Path(entry).resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if mapped == executable_root or executable_root in mapped.parents:
            roots.append(mapped)
    unique = []
    for path in roots:
        if path not in unique:
            unique.append(path)
    return unique, mapping_sha256


def _runtime_read_roots(expected_mapping_sha256: str) -> list[Path]:
    roots, mapping_sha256 = _runtime_mapping()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_mapping_sha256) \
            or mapping_sha256 != expected_mapping_sha256:
        raise PermissionError("RPF53_PYTHON_RUNTIME_MAPPING_MISMATCH")
    return roots


def _guard_events(port: int, root: Path, sdk_root: Path, runtime_roots: list[Path],
                  script_path: Path, denied: list[str], denied_files: list[dict]):
    def inside(path: Path, base: Path) -> bool:
        return path == base or base in path.parents

    def denied_file(path: str | bytes | os.PathLike[str], code: str) -> None:
        denied.append(code)
        if len(denied_files) >= 8:
            return
        try:
            name = _safe_denied_basename(path)
            category = _path_category(Path(path), sdk_root=sdk_root,
                                      runtime_roots=runtime_roots, write_root=root)
        except (OSError, RuntimeError, TypeError, ValueError):
            name, category = "UNKNOWN", "UNKNOWN"
        denied_files.append({"category": category, "basename": name})

    def audit(event, args):
        if event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"):
            denied.append("PROCESS_EXEC_DENIED")
            raise PermissionError("RPF53_PROCESS_EXEC_DENIED")
        if event in ("socket.bind", "socket.listen", "socket.sendto", "socket.sendmsg"):
            denied.append("SOCKET_OPERATION_DENIED")
            raise PermissionError("RPF53_SOCKET_OPERATION_DENIED")
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
            allowed = (inside(candidate, root) if write else
                       inside(candidate, root) or inside(candidate, sdk_root)
                       or any(inside(candidate, base) for base in runtime_roots)
                       or candidate == script_path)
            if not allowed:
                code = "FILE_WRITE_DENIED" if write else "FILE_ACCESS_DENIED"
                denied_file(path, code)
                raise PermissionError("RPF53_FILE_WRITE_DENIED" if write
                                      else "RPF53_FILE_ACCESS_DENIED")
        if event in ("os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.chown",
                     "os.utime", "os.truncate", "os.rename", "os.link", "os.symlink"):
            denied_file(args[0], "FILE_WRITE_DENIED")
            raise PermissionError("RPF53_FILE_WRITE_DENIED")
    return audit


def _guard(port: int, write_root: Path, sdk_readonly_path: Path,
           expected_sdk_site_root_binding_sha256: str,
           expected_runtime_mapping_sha256: str,
           denied: list[str], denied_files: list[dict]):
    root = _canonical_directory(write_root)
    sdk_root = _canonical_directory(sdk_readonly_path)
    if _root_has_link_component(sdk_readonly_path) or _root_has_link_component(write_root):
        raise PermissionError("RPF53_TRUSTED_ROOT_LINK")
    sdk_binding = hashlib.sha256(os.path.normcase(str(sdk_root)).casefold().encode(
        "utf-8")).hexdigest()
    if (not re.fullmatch(r"[0-9a-f]{64}", expected_sdk_site_root_binding_sha256)
            or sdk_binding != expected_sdk_site_root_binding_sha256):
        raise PermissionError("RPF53_SDK_ROOT_BINDING_MISMATCH")
    return _guard_events(port, root, sdk_root,
                         _runtime_read_roots(expected_runtime_mapping_sha256),
                         Path(__file__).resolve(strict=True), denied, denied_files)


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


def _validated_run_usage(usage: object, expected_type: type) -> dict:
    if type(usage) is not expected_type:
        raise TypeError("RPF53_USAGE_TYPE")
    names = ("requests", "tool_calls", "input_tokens", "output_tokens")
    values = {}
    for name in names:
        value = getattr(usage, name, None)
        if type(value) is not int or value < 0:
            raise TypeError("RPF53_USAGE_FIELD")
        values[name] = value
    return {"usage_type": f"{expected_type.__module__}.{expected_type.__qualname__}",
            "usage_fields": sorted(values)}


def main() -> int:
    stage = "config"
    denied: list[str] = []
    denied_files: list[dict] = []
    loop = None
    try:
        config_raw = sys.stdin.buffer.read(16385)
        if not config_raw or len(config_raw) > 16384:
            raise ValueError("CONFIG_SIZE")
        config = json.loads(config_raw.decode("utf-8"))
        required = {"port", "token", "write_root", "sdk_readonly_path",
                    "sdk_site_root_binding_sha256", "python_runtime_mapping_sha256",
                    "instructions", "task_prompt",
                    "model", "max_runtime_seconds", "fixture"}
        if type(config) is not dict or set(config) != required:
            raise ValueError("CONFIG_FIELDS")
        port = config["port"]
        if type(port) is not int or not 0 < port < 65536:
            raise ValueError("CONFIG_PORT")

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        sdk_root = _canonical_directory(Path(config["sdk_readonly_path"]))
        path_binding = hashlib.sha256(os.path.normcase(str(sdk_root)).casefold().encode(
            "utf-8")).hexdigest()
        if (not re.fullmatch(r"[0-9a-f]{64}", config["sdk_site_root_binding_sha256"])
                or path_binding != config["sdk_site_root_binding_sha256"]
                or not re.fullmatch(r"[0-9a-f]{64}", config["python_runtime_mapping_sha256"])
                or _root_has_link_component(Path(config["sdk_readonly_path"]))):
            raise PermissionError("RPF53_SDK_ROOT_BINDING_MISMATCH")
        sys.path.insert(0, str(sdk_root))
        sys.addaudithook(_guard(port, Path(config["write_root"]), sdk_root,
                                config["sdk_site_root_binding_sha256"],
                                config["python_runtime_mapping_sha256"],
                                denied, denied_files))

        stage = "sdk_import"
        import importlib.metadata
        import httpx2
        from openai import AsyncOpenAI
        from pydantic_ai import Agent, RunContext
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import RunUsage, UsageLimits

        sdk_file = Path(inspect.getfile(Agent)).resolve()
        openai_file = Path(inspect.getfile(AsyncOpenAI)).resolve()
        if not (sdk_file == sdk_root or sdk_root in sdk_file.parents
                or openai_file == sdk_root or sdk_root in openai_file.parents):
            raise RuntimeError("SDK_SOURCE_ROOT_MISMATCH")
        sdk_sha = hashlib.sha256(sdk_file.read_bytes()).hexdigest()
        openai_sha = hashlib.sha256(openai_file.read_bytes()).hexdigest()
        python_executable = Path(sys.executable).resolve(strict=True)
        python_executable_sha256 = hashlib.sha256(python_executable.read_bytes()).hexdigest()
        framework_version = importlib.metadata.version("pydantic-ai-slim")
        openai_version = importlib.metadata.version("openai")
        if framework_version != "2.57.0" or openai_version != "3.35.1":
            raise RuntimeError("SDK_VERSION_MISMATCH")
        _post(port, config["token"], "/ready", {
            "framework": "pydantic-ai-slim", "version": framework_version,
            "openai_version": openai_version, "pid": os.getpid(),
            "python_executable_sha256": python_executable_sha256,
            "sdk_source_sha256": sdk_sha, "openai_source_sha256": openai_sha,
            "sdk_site_root_binding_sha256": config["sdk_site_root_binding_sha256"],
            "python_runtime_mapping_sha256": config["python_runtime_mapping_sha256"]})

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
            function.__doc__ = TOOL_HELP[function.__name__]
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
                usage_report = _validated_run_usage(result.usage, RunUsage)
                usage_fields = usage_report["usage_fields"]
                usage_values = {name: getattr(result.usage, name) for name in usage_fields}
                if usage_values["tool_calls"] != callbacks:
                    raise RuntimeError("RPF53_USAGE_TOOL_CALL_COUNT_MISMATCH")
                output = result.output
                output_raw = (output if isinstance(output, str) else
                              json.dumps(output, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=True, allow_nan=False))
                return {
                    "status": "COMPLETED", "framework": "pydantic-ai-slim",
                    "version": framework_version, "openai_version": openai_version,
                    "pid": os.getpid(),
                    "python_executable_sha256": python_executable_sha256,
                    "usage_type": usage_report["usage_type"],
                    "usage_fields": usage_fields,
                    "requests": usage_values["requests"],
                    "input_tokens": usage_values["input_tokens"],
                    "output_tokens": usage_values["output_tokens"],
                    "tool_calls": usage_values["tool_calls"], "tool_callbacks": callbacks,
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
                     "RPF53_FILE_WRITE_DENIED", "RPF53_SOCKET_OPERATION_DENIED",
                     "RPF53_TRUSTED_ROOT_INVALID", "RPF53_TRUSTED_ROOT_LINK",
                     "RPF53_SDK_ROOT_BINDING_MISMATCH",
                     "RPF53_PYTHON_RUNTIME_MAPPING_INVALID"):
            if code in text:
                guard_code = code
                break
        report = {"status": "SDK_ERROR", "stage": stage,
                  "error_type": error_type, "guard_code": guard_code,
                  "guard_denials": sorted(set(denied))[:8],
                  "denied_files": denied_files[:8]}
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

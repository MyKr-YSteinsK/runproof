"""RPF68 typed Target child; original RPF67 guard functions retained verbatim."""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import sys
import sysconfig
from pathlib import Path


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


def main():
    stage='CONFIG';denied=[];denied_files=[];loop=None
    try:
        raw=sys.stdin.buffer.read(16385)
        if not raw or len(raw)>16384:raise ValueError('CONFIG_SIZE')
        cfg=json.loads(raw)
        if set(cfg)!={'port','token','write_root','sdk_readonly_path','sdk_site_root_binding_sha256','python_runtime_mapping_sha256','instructions','task_prompt','domain','total_token_limit'}:raise ValueError('CONFIG_FIELDS')
        if type(cfg['total_token_limit']) is not int or not 1<=cfg['total_token_limit']<=600000:raise ValueError('TOTAL_TOKEN_LIMIT')
        port=cfg['port']
        if type(port) is not int or not 1024<=port<=65535:raise ValueError('PORT')
        import asyncio
        loop=asyncio.new_event_loop();asyncio.set_event_loop(loop)
        sdk_root=_canonical_directory(Path(cfg['sdk_readonly_path']));sys.path.insert(0,str(sdk_root))
        sys.addaudithook(_guard(port,Path(cfg['write_root']),sdk_root,cfg['sdk_site_root_binding_sha256'],cfg['python_runtime_mapping_sha256'],denied,denied_files))
        stage='SDK_IMPORT'
        import importlib.metadata
        import httpx2
        from openai import AsyncOpenAI
        from pydantic_ai import Agent,RunContext
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import RunUsage,UsageLimits
        sdk_file=Path(inspect.getfile(Agent)).resolve();openai_file=Path(inspect.getfile(AsyncOpenAI)).resolve()
        if not sdk_file.is_relative_to(sdk_root) or not openai_file.is_relative_to(sdk_root):raise ValueError('SDK_ROOT')
        identity=dict(framework='pydantic-ai-slim',version=importlib.metadata.version('pydantic-ai-slim'),openai_version=importlib.metadata.version('openai'),pid=os.getpid(),python_executable_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),sdk_source_sha256=hashlib.sha256(sdk_file.read_bytes()).hexdigest(),openai_source_sha256=hashlib.sha256(openai_file.read_bytes()).hexdigest(),sdk_site_root_binding_sha256=cfg['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=cfg['python_runtime_mapping_sha256'])
        _post(port,cfg['token'],'/ready',identity)
        callbacks=0
        def inspect_order(ctx:RunContext[None],order_id:str)->dict:
            """Inspect the authorized fictitious order first."""
            nonlocal callbacks
            callbacks+=1
            return _post(port,cfg['token'],'/tool',dict(call_id=ctx.tool_call_id,name='inspect_order',arguments=dict(order_id=order_id)))
        def refund_order(ctx:RunContext[None],order_id:str,operation_id:str,amount_minor:int)->dict:
            """Commit exactly one authorized full refund; never repeat after UNKNOWN_OUTCOME."""
            nonlocal callbacks
            callbacks+=1
            return _post(port,cfg['token'],'/tool',dict(call_id=ctx.tool_call_id,name='refund_order',arguments=dict(order_id=order_id,operation_id=operation_id,amount_minor=amount_minor)))
        def reconcile_order(ctx:RunContext[None],operation_id:str)->dict:
            """Optionally read the receipt once after UNKNOWN_OUTCOME, without another write."""
            nonlocal callbacks
            callbacks+=1
            return _post(port,cfg['token'],'/tool',dict(call_id=ctx.tool_call_id,name='reconcile_order',arguments=dict(operation_id=operation_id)))
        def inspect_config(ctx:RunContext[None])->dict:
            """Read the authorized configuration item."""
            nonlocal callbacks
            callbacks+=1
            return _post(port,cfg['token'],'/tool',dict(call_id=ctx.tool_call_id,name='inspect_config',arguments={}))
        def create_config_v1(ctx:RunContext[None],value:str)->dict:
            """Create rpf53-v1 once after an ABSENT inspection."""
            nonlocal callbacks
            callbacks+=1
            return _post(port,cfg['token'],'/tool',dict(call_id=ctx.tool_call_id,name='create_config_v1',arguments=dict(value=value)))
        def update_config_v2(ctx:RunContext[None],expected_version:int,value:str)->dict:
            """Update version 1 once to rpf53-v2."""
            nonlocal callbacks
            callbacks+=1
            return _post(port,cfg['token'],'/tool',dict(call_id=ctx.tool_call_id,name='update_config_v2',arguments=dict(expected_version=expected_version,value=value)))
        if cfg['domain'] not in ('config-java-http','order-sqlite'):raise ValueError('DOMAIN')
        registry=[inspect_config,create_config_v1,update_config_v2] if cfg['domain']=='config-java-http' else [inspect_order,refund_order,reconcile_order]
        for f in registry:f.__annotations__['ctx']=RunContext[None]
        async def run():
            async with httpx2.AsyncClient(trust_env=False,timeout=60) as http:
                client=AsyncOpenAI(base_url=f'http://127.0.0.1:{port}/v1',api_key=cfg['token'],max_retries=0,http_client=http)
                model=OpenAIChatModel('deepseek-flash',provider=OpenAIProvider(openai_client=client))
                agent=Agent(model,name='rpf68-typed-target',retries=0,tools=registry,instructions=cfg['instructions'],model_settings={'max_tokens':512,'parallel_tool_calls':False})
                result=await agent.run(cfg['task_prompt'],usage_limits=UsageLimits(request_limit=5 if cfg['domain']=='config-java-http' else 4,total_tokens_limit=cfg['total_token_limit'],tool_calls_limit=4 if cfg['domain']=='config-java-http' else 3))
                checked=_validated_run_usage(result.usage,RunUsage)
                if result.usage.tool_calls!=callbacks:raise ValueError('TOOL_CALLBACK_COUNT')
                return dict(identity,status='COMPLETED',requests=result.usage.requests,input_tokens=result.usage.input_tokens,output_tokens=result.usage.output_tokens,tool_calls=result.usage.tool_calls,tool_callbacks=callbacks,usage_type=checked['usage_type'],final_output_sha256=hashlib.sha256(str(result.output).encode()).hexdigest(),final_text_persisted=False,provider_key_present=bool(os.environ.get('DEEPSEEK_API_KEY')),business_key_present=bool(os.environ.get('CONFIG_CENTER_API_KEY')),guard_denials=sorted(set(denied)),denied_files=denied_files)
        stage='SDK_RUN';report=loop.run_until_complete(asyncio.wait_for(run(),timeout=1200));print(json.dumps(report,sort_keys=True,separators=(',',':')));return 0
    except BaseException as exc:
        print(json.dumps(dict(status='SDK_ERROR',stage=stage,error_type=type(exc).__name__,guard_denials=sorted(set(denied)),denied_files=denied_files),sort_keys=True,separators=(',',':')));return 1
    finally:
        if loop is not None:loop.close()

if __name__=='__main__':raise SystemExit(main())

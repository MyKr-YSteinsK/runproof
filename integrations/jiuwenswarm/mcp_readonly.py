"""Three read-only tools over MCP stdio; no provider or write tools."""
from __future__ import annotations
import os
import re
import json
import sys
from pathlib import Path
import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server
from integrations.jiuwenswarm import recorded_sources as sources

owner = Path.cwd().resolve()
if owner.parent != (sources.ROOT / ".local/rpf-95-jiuwenswarm").resolve() or not re.fullmatch(r"[0-9a-f]{32}", owner.name):
    raise RuntimeError("TASK_OWNER_CWD_REQUIRED")
class ReadOnlyMCP(FastMCP):
    async def run_stdio_async(self):
        async with stdio_server(stdin=BoundedInput()) as (read, write):
            await self._mcp_server.run(read, write, self._mcp_server.create_initialization_options())

    async def call_tool(self, name, arguments):
        expected = {"get_capabilities": set(), "inspect_recorded_experiment": {"source_id"}, "verify_witness": {"source_id"}}
        if name not in expected or not isinstance(arguments, dict) or set(arguments) != expected[name]:
            raise ValueError("UNSUPPORTED_OPERATION_OR_ARGUMENTS")
        if "source_id" in arguments and (type(arguments["source_id"]) is not str or len(arguments["source_id"]) > 64):
            raise ValueError("INVALID_SOURCE")
        return await super().call_tool(name, arguments)

def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result

class BoundedInput:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raw = await anyio.to_thread.run_sync(sys.stdin.buffer.readline, 16385)
        if not raw:
            raise StopAsyncIteration
        if len(raw) > 16384 or not raw.endswith(b"\n"):
            raise StopAsyncIteration
        try:
            line = raw.decode("utf-8", errors="strict")
            json.loads(line, object_pairs_hook=_unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("INVALID_CONSTANT")))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise StopAsyncIteration
        return line

server = ReadOnlyMCP("runproof-readonly")

@server.tool()
async def get_capabilities() -> dict:
    return sources.capabilities()

@server.tool()
async def inspect_recorded_experiment(source_id: str) -> dict:
    return sources.inspect(source_id)

@server.tool()
async def verify_witness(source_id: str) -> dict:
    return sources.witness(source_id)

if __name__ == "__main__":
    server.run(transport="stdio")

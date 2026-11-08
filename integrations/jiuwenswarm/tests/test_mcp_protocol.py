import asyncio
import os
import sys
import subprocess
from pathlib import Path
import unittest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

def isolated_env(owner, root):
    env = {"SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"), "PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"}
    for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "UV_CACHE_DIR", "PIP_CACHE_DIR", "TEMP", "TMP"):
        env[name] = str(owner)
    return env

class ProtocolTests(unittest.TestCase):
    def test_manager_rejects_non_owner_before_configuration(self):
        owner = Path(sys.executable).resolve().parents[2]
        root = Path(__file__).resolve().parents[3]
        env = isolated_env(owner, root)
        p = subprocess.run([sys.executable, "-B", "-m", "integrations.jiuwenswarm.manager_probe"], cwd=root, env=env, input=b"", capture_output=True, timeout=30)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn(b"TASK_OWNER_CWD_REQUIRED", p.stderr)

    def test_rejects_missing_or_external_isolation_path(self):
        owner = Path(sys.executable).resolve().parents[2]
        root = Path(__file__).resolve().parents[3]
        for replacement in (None, str(root)):
            env = isolated_env(owner, root)
            if replacement is None: env.pop("HOME")
            else: env["HOME"] = replacement
            p = subprocess.run([sys.executable, "-B", "-m", "integrations.jiuwenswarm.mcp_readonly"], cwd=owner, env=env, input=b"", capture_output=True, timeout=30)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn(b"TASK_OWNER_ENV_REQUIRED:HOME", p.stderr)

    def test_duplicate_and_oversized_frames_close_without_response(self):
        owner = Path(sys.executable).resolve().parents[2]
        root = Path(__file__).resolve().parents[3]
        env = isolated_env(owner, root)
        init = b'{"jsonrpc":"2.0","id":99,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"negative-control","version":"1"}}}\n'
        for raw in (b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n', b"{" + b"x" * 17000 + b"}\n"):
            p = subprocess.Popen([sys.executable, "-B", "-m", "integrations.jiuwenswarm.mcp_readonly"], cwd=owner, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                p.stdin.write(init); p.stdin.flush()
                response = p.stdout.readline()
                self.assertIn(b'"id":99', response)
                self.assertIn(b'"result"', response)
                remainder, _ = p.communicate(raw, timeout=30)
                self.assertNotIn(b'"result"', remainder)
            finally:
                if p.poll() is None: p.kill(); p.wait()

    def test_real_stdio(self):
        async def run():
            owner = Path(sys.executable).resolve().parents[2]
            root = Path(__file__).resolve().parents[3]
            params = StdioServerParameters(command=sys.executable, args=["-B", "-m", "integrations.jiuwenswarm.mcp_readonly"], cwd=owner, env=isolated_env(owner, root))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    self.assertEqual({t.name for t in tools.tools}, {"get_capabilities", "inspect_recorded_experiment", "verify_witness"})
                    for name, source, expected in [("inspect_recorded_experiment", "rpf46-summary", "HASH_AND_COMMIT_VERIFIED"), ("verify_witness", "rpf44-ops-sample", "VERIFIED_ANCHORED")]:
                        result = await client.call_tool(name, {"source_id": source})
                        self.assertFalse(result.isError)
                        self.assertIn(expected, str(result))
                    denied = await client.call_tool("verify_witness", {"source_id": "../../secret"})
                    self.assertTrue(denied.isError)
                    denied = await client.call_tool("verify_witness", {"source_id": "rpf44-ops-sample", "path": "../../secret"})
                    self.assertTrue(denied.isError)
                    denied = await client.call_tool("create_experiment", {})
                    self.assertTrue(denied.isError)
        asyncio.run(asyncio.wait_for(run(), timeout=60))

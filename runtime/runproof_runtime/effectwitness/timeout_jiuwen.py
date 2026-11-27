"""Optional openJiuwen 0.1.21 ReAct adapter with an in-process fixed model."""
import asyncio
from contextlib import contextmanager, redirect_stdout
from hashlib import sha256
from importlib.metadata import distributions
import os
from pathlib import Path
import platform
import re
import sys

from .product_local_contracts import canonical, strict

VERSION = "0.1.21"
TOOL = "record_proposal"
ACK = "Proposal receipt observed."
LOCK = Path(__file__).resolve().parents[3] / "spikes/rpf-129/requirements-win-py312.lock"


def _locked():
    lock = LOCK.read_bytes()
    versions = dict(re.findall(r"^([a-z0-9_-]+)==([^\s;\\]+)", lock.decode(), re.MULTILINE))
    if versions.get("openjiuwen") != VERSION:
        raise ValueError("SDK_LOCK_VERSION")
    return {"version": VERSION, "lock_sha256": sha256(lock.replace(b"\r\n", b"\n")).hexdigest(),
            "distributions": versions}


def environment():
    if (sys.prefix == sys.base_prefix or sys.platform != "win32" or sys.version_info[:2] != (3, 12)
            or platform.machine().upper() != "AMD64"):
        raise ValueError("SDK_REQUIRES_ISOLATED_WINDOWS_X64_CPYTHON_312")
    wanted = _locked()
    versions = {re.sub(r"[-_.]+", "-", package.metadata["Name"].lower()): package.version
                for package in distributions()}
    if versions != wanted["distributions"]:
        raise ValueError("SDK_DEPENDENCY_LOCK_MISMATCH")
    return wanted


def verify_environment(sdk, engine):
    if sdk != (_locked() if engine == "openjiuwen" else None):
        raise ValueError("SDK_ENVIRONMENT_EVIDENCE")


def call_for(proposal):
    return {"id": "proposal-" + proposal["session_id"], "name": TOOL, "arguments": proposal}


def receipt_for(call, proposal):
    return {"tool": TOOL, "call_id": call["id"], "status": "RECORDED", "proposal": proposal}


def verify_trace(trace, view, proposal):
    call = call_for(proposal)
    receipt = receipt_for(call, proposal)
    expected = {
        "framework": "openJiuwen ReActAgent", "version": VERSION, "model": "IN_PROCESS_FIXED_REPLIES",
        "framework_observation": view, "tool_schema_names": [TOOL],
        "fixed_replies": [{"tool_call": call}, {"content": ACK}], "tool_receipt": receipt,
        "receipt_observed": {"call_id": call["id"], "receipt": receipt},
        "framework_result": {"result_type": "answer", "output": ACK},
    }
    if canonical(trace) != canonical(expected):
        raise ValueError("FRAMEWORK_TRACE_BINDING")


async def _react(view, proposal):
    # Import SDK only inside the optional process. The verifier never calls it.
    from openjiuwen.core.foundation.llm import AssistantMessage, ToolCall
    from openjiuwen.core.foundation.tool import tool
    from openjiuwen.core.single_agent import AgentCard, ReActAgent, ReActAgentConfig

    call = call_for(proposal)
    trace = {"framework": "openJiuwen ReActAgent", "version": VERSION,
             "model": "IN_PROCESS_FIXED_REPLIES", "fixed_replies": []}

    @tool(name=TOOL, description="Record a proposed action. Does not execute a business operation.")
    def record_proposal(action: str, session_id: str, operation_id: str, observation_sha256: str) -> str:
        supplied = {"action": action, "session_id": session_id, "operation_id": operation_id,
                    "observation_sha256": observation_sha256}
        if "tool_receipt" in trace or supplied != proposal:
            raise ValueError("FRAMEWORK_TOOL_ARGUMENTS")
        receipt = receipt_for(call, supplied)
        trace["tool_receipt"] = receipt
        return canonical(receipt).decode()

    class FixedModel:
        async def invoke(self, *, messages, tools, **kwargs):
            names = [t.name for t in tools]
            if names != [TOOL]:
                raise ValueError("FRAMEWORK_TOOL_ALLOWLIST")
            trace["tool_schema_names"] = names
            replies = trace["fixed_replies"]
            if not replies:
                users = [m for m in messages if m.role == "user"]
                if len(users) != 1:
                    raise ValueError("FRAMEWORK_OBSERVATION")
                observed = strict(users[0].content.encode())
                if canonical(observed) != canonical(view):
                    raise ValueError("FRAMEWORK_OBSERVATION")
                trace["framework_observation"] = observed
                emitted = ToolCall(id=call["id"], type="function", name=TOOL, arguments=canonical(proposal).decode())
                replies.append({"tool_call": {"id": emitted.id, "name": emitted.name,
                                              "arguments": strict(emitted.arguments.encode())}})
                return AssistantMessage(finish_reason="tool_calls", tool_calls=[emitted])

            feedback = [m for m in messages if m.role == "tool"]
            if len(replies) != 1 or len(feedback) != 1 or feedback[0].tool_call_id != call["id"]:
                raise ValueError("FRAMEWORK_FEEDBACK")
            received = strict(feedback[0].content.encode())
            if received != trace.get("tool_receipt"):
                raise ValueError("FRAMEWORK_FEEDBACK")
            trace["receipt_observed"] = {"call_id": feedback[0].tool_call_id, "receipt": received}
            reply = AssistantMessage(content=ACK, finish_reason="stop")
            replies.append({"content": reply.content})
            return reply

    identity = proposal["session_id"]
    agent = ReActAgent(AgentCard(id=identity, name="TimeoutComparison"))
    agent.configure(ReActAgentConfig(model_name="runproof-offline-fixture", max_iterations=2,
                                    max_iterations_hard_limit=2, parallel_tool_calls=False))
    agent.set_llm(FixedModel())
    if not agent.ability_manager.add_ability(record_proposal.card, record_proposal).added:
        raise ValueError("FRAMEWORK_TOOL_REGISTRATION")
    trace["framework_result"] = await agent.invoke({"query": canonical(view).decode(), "conversation_id": identity})
    verify_trace(trace, view, proposal)
    return trace


class Driver:
    def __init__(self, runner, blocked):
        self.runner = runner
        self.blocked = blocked

    def propose(self, view, proposal):
        with redirect_stdout(sys.stderr):
            trace = self.runner.run(asyncio.wait_for(_react(view, proposal), timeout=45))
        if self.blocked:
            raise ValueError("FRAMEWORK_NETWORK_OR_PROCESS_ATTEMPT")
        return trace


@contextmanager
def driver(folder):
    """Keep SDK logs and caches owned by the run and deny Python network operations."""
    folder.mkdir(exist_ok=False)
    blocked = []
    local_ipv6_probes = 0
    active = False

    def audit(event, args):
        nonlocal local_ipv6_probes
        if not active:
            return
        if event == "socket.bind" and args[1][:2] == ("::1", 0):
            # urllib3 checks IPv6 using an ephemeral local bind during import.
            local_ipv6_probes += 1
            raise PermissionError("OFFLINE_IPV6_PROBE")
        if (event.startswith("socket.") and event not in {"socket.__new__", "socket.gethostname"}
                or event in {"subprocess.Popen", "os.system", "os.startfile"}):
            blocked.append(event)
            raise PermissionError("OFFLINE_EXPERIMENT")

    settings = {
        "OTEL_SDK_DISABLED": "true", "HF_HUB_OFFLINE": "1", "HF_HOME": str(folder / "hf"),
        "TIKTOKEN_CACHE_DIR": str(folder / "tiktoken"),
    }
    prior = {key: os.environ.get(key) for key in settings}
    cwd = Path.cwd()
    try:
        os.environ.update(settings)
        os.chdir(folder)
        with asyncio.Runner() as runner:
            # Windows' event loop creates its own internal socket pair on startup.
            runner.get_loop()
            sys.addaudithook(audit)
            active = True
            yield Driver(runner, blocked)
    finally:
        active = False
        os.chdir(cwd)
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        with (folder / "audit.json").open("xb") as file:
            file.write(canonical({"provider_requests": 0, "blocked_network_or_process_events": blocked,
                                  "blocked_local_ipv6_probes": local_ipv6_probes}))

"""Inject the RPF-131 boundary through the real ReActAgent model invocation."""
import asyncio
from contextlib import redirect_stdout
import sys

from . import rpf131_frames as frames
from .product_local_contracts import canonical, strict
from .timeout_experiment import require
from .timeout_jiuwen import ACK, TOOL, receipt_for


async def react(log, view, boundary):
    from openjiuwen.core.foundation.llm import AssistantMessage, ToolCall
    from openjiuwen.core.foundation.tool import tool
    from openjiuwen.core.single_agent import AgentCard, ReActAgent, ReActAgentConfig

    call = receipt = None
    invocations = 0

    @tool(name=TOOL, description="Record a proposal for review without making a business write.")
    def record_proposal(action: str, session_id: str, operation_id: str, observation_sha256: str) -> str:
        nonlocal receipt
        proposal = {"action": action, "session_id": session_id, "operation_id": operation_id,
                    "observation_sha256": observation_sha256}
        require(receipt is None and call is not None and call["arguments"] == proposal, "FRAMEWORK_TOOL_BINDING")
        receipt = receipt_for(call, proposal)
        log.emit("TOOL_RECEIPT", "react_tool", receipt)
        return canonical(receipt).decode()

    class SimulatedModel:
        async def invoke(self, *, messages, tools, **kwargs):
            nonlocal invocations, call
            invocations += 1
            require(invocations <= 2 and boundary.stop is None, "FRAMEWORK_NO_RETRY")
            require(tools is not None and [item.name for item in tools] == [TOOL], "FRAMEWORK_TOOL_ALLOWLIST")
            users = [message for message in messages if message.role == "user"]
            require(len(users) == 1, "FRAMEWORK_OBSERVATION")
            actual_view = strict(users[0].content.encode())
            require(canonical(actual_view) == canonical(view), "FRAMEWORK_OBSERVATION")
            feedback = [message for message in messages if message.role == "tool"]
            if invocations == 1:
                require(not feedback, "FRAMEWORK_UNEXPECTED_FEEDBACK")
                response = boundary.call(1, actual_view, None)
                call = response["call"]
                tool_call = ToolCall(id=call["id"], type="function", name=call["name"],
                                     arguments=canonical(call["arguments"]).decode())
                return AssistantMessage(finish_reason="tool_calls", tool_calls=[tool_call])

            require(receipt is not None and len(feedback) == 1 and feedback[0].tool_call_id == receipt["call_id"],
                    "FRAMEWORK_FEEDBACK")
            observed_receipt = strict(feedback[0].content.encode())
            require(canonical(observed_receipt) == canonical(receipt), "FRAMEWORK_FEEDBACK")
            response = boundary.call(2, actual_view, observed_receipt)
            log.emit("TOOL_RECEIPT_READBACK", "react_model_message", observed_receipt)
            return AssistantMessage(content=response["text"], finish_reason="stop")

    session = view["decision_readback"]["session_id"]
    agent = ReActAgent(AgentCard(id=session, name="RunProofOfflinePreflight"))
    agent.configure(ReActAgentConfig(model_name="runproof-offline-fixture", max_iterations=2,
                                    max_iterations_hard_limit=2, parallel_tool_calls=False))
    agent.set_llm(SimulatedModel())
    require(agent.ability_manager.add_ability(record_proposal.card, record_proposal).added, "FRAMEWORK_TOOL_REGISTRATION")
    try:
        answer = await agent.invoke({"query": canonical(view).decode(), "conversation_id": session})
    except Exception:
        if boundary.stop is None:
            raise
    if boundary.stop is not None:
        return None, boundary.stop, invocations
    require(invocations == 2 and receipt is not None
            and answer == {"output": ACK, "result_type": "answer"}, "FRAMEWORK_FINAL_ANSWER")
    log.emit("FRAMEWORK_ANSWER", "openjiuwen", answer)
    return receipt["proposal"], None, invocations


def run(sdk, log, manifest, cell, view):
    boundary = frames.ModelBoundary(log, manifest["run_id"], cell["name"], frames.PLAN[cell["name"]][1])
    with redirect_stdout(sys.stderr):
        decision = sdk.runner.run(asyncio.wait_for(react(log, view, boundary), timeout=45))
    require(not sdk.blocked, "FRAMEWORK_NETWORK_OR_PROCESS_ATTEMPT")
    return decision

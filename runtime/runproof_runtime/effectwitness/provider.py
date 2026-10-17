"""One bounded DeepSeek tool session. No SDK retries, proxy or raw-text logging."""

from __future__ import annotations

import http.client
import json
import os

from ..models import RuntimeFailure
from .contracts import canonical, require
from .engine import Orchestrator

HOST = "api.deepseek.com"
MODEL = "deepseek-flash"


def request_completion(body: dict, budget, records: list, checkpoint) -> dict:
    """Shared narrow transport. Caller owns the session and durable checkpoint."""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    require(bool(key), "DEEPSEEK_KEY_UNAVAILABLE", "PROVIDER")
    encoded = canonical(body)
    budget.reserve_request(len(encoded) + 1024, body["max_tokens"])
    record = {"attempt": budget.requests, "endpoint": "https://" + HOST + "/chat/completions",
              "requested_model": body["model"], "status": "ATTEMPTED",
              "tool_results_submitted": [m["tool_call_id"] for m in body["messages"] if m["role"] == "tool"]}
    records.append(record)
    checkpoint()  # flush/fsync reservation and visibility before opening socket
    connection = http.client.HTTPSConnection(HOST, timeout=min(budget.limits["request_seconds"],
        budget.limits["seconds"] - (budget.clock() - budget.started)))
    try:
        connection.request("POST", "/chat/completions", encoded,
                           {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        response = connection.getresponse()
        record.update(http_status=response.status, request_id=response.getheader("x-request-id"))
        raw = response.read(262145)
        require(len(raw) <= 262144, "PROVIDER_RESPONSE_TOO_LARGE", "PROVIDER")
        require(response.status == 200, "PROVIDER_HTTP_ERROR", "PROVIDER")
        data = json.loads(raw)
        budget.record_usage(data.get("usage"))
        budget.check_time()
        record.update(response_id=data.get("id"), returned_model=data.get("model"),
                      usage={k: data["usage"][k] for k in
                             ("prompt_tokens", "completion_tokens", "total_tokens")}, status="RECEIVED")
        require(isinstance(data.get("id"), str) and isinstance(data.get("model"), str),
                "PROVIDER_IDENTITY_MISSING", "PROVIDER")
        checkpoint()
        return data
    except RuntimeFailure:
        checkpoint()
        raise
    except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError) as error:
        record["status"] = "TRANSPORT_OR_PROTOCOL_ERROR"
        checkpoint()
        raise RuntimeFailure("PROVIDER", "PROVIDER_TRANSPORT_OR_PROTOCOL_ERROR") from error
    finally:
        connection.close()


def drive(orchestrator: Orchestrator, checkpoint) -> dict:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    require(bool(key), "DEEPSEEK_KEY_UNAVAILABLE", "PROVIDER")
    e = orchestrator.contracts.effect
    messages = [{"role": "system", "content":
                 "Operate only this fictitious local order sandbox. Complete the authorized full refund "
                 "once using refund_order with the exact identifiers supplied. Do not invent tools or "
                 "retry an uncertain effect. After receiving its tool result, briefly acknowledge it."},
                {"role": "user", "content": canonical({k: e[k] for k in
                    ("order_id", "operation_id", "amount_minor", "currency")}).decode()}]
    records = []
    committed = False
    summary_present = False
    while True:
        body = {"model": MODEL, "messages": messages,
                "tools": orchestrator.domain.tool_definitions(),
                "tool_choice": "none" if committed else "required",
                "thinking": {"type": "disabled"}, "max_tokens": 256, "stream": False}
        encoded = canonical(body)
        # UTF-8 byte count + 1024 framing tokens overestimates this ASCII prompt.
        orchestrator.budget.reserve_request(len(encoded) + 1024, 256)
        record = {"attempt": orchestrator.budget.requests, "endpoint": "https://" + HOST + "/chat/completions",
                  "requested_model": MODEL, "status": "ATTEMPTED", "tool_results_submitted":
                  [m["tool_call_id"] for m in messages if m["role"] == "tool"]}
        records.append(record)
        checkpoint(records)  # write-ahead before opening a socket; no implicit retry
        connection = http.client.HTTPSConnection(HOST, timeout=min(
            orchestrator.budget.limits["request_seconds"],
            orchestrator.budget.limits["seconds"] -
            (orchestrator.budget.clock() - orchestrator.budget.started)))
        try:
            connection.request("POST", "/chat/completions", encoded,
                               {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            response = connection.getresponse()
            record["http_status"] = response.status
            record["request_id"] = response.getheader("x-request-id")
            raw = response.read(262145)
            require(len(raw) <= 262144, "PROVIDER_RESPONSE_TOO_LARGE", "PROVIDER")
            require(response.status == 200, "PROVIDER_HTTP_ERROR", "PROVIDER")
            data = json.loads(raw)
            orchestrator.budget.record_usage(data.get("usage"))
            orchestrator.budget.check_time()
            record.update(response_id=data.get("id"), returned_model=data.get("model"),
                          usage={k: data["usage"][k] for k in
                                 ("prompt_tokens", "completion_tokens", "total_tokens")}, status="RECEIVED")
            require(isinstance(data.get("id"), str) and isinstance(data.get("model"), str),
                    "PROVIDER_IDENTITY_MISSING", "PROVIDER")
            choices = data.get("choices")
            require(type(choices) is list and len(choices) == 1, "PROVIDER_CHOICES", "PROVIDER")
            message = choices[0]["message"]
            calls = message.get("tool_calls") or []
            require(type(calls) is list, "PROVIDER_TOOL_ENVELOPE", "PROVIDER")
            record["finish_reason"] = choices[0].get("finish_reason")
            record["tool_calls"] = []
            checkpoint(records)
            if committed:
                require(not calls, "PROVIDER_IGNORED_TOOL_CHOICE", "PROVIDER")
                summary_present = bool(message.get("content"))
                break
            require(bool(calls), "AGENT_NO_TOOL_CALL", "AGENT")
            # Only protocol-relevant fields enter the continuation; reasoning/text is not persisted.
            messages.append({"role": "assistant", "content": None, "tool_calls": calls})
            for call in calls:
                require(type(call) is dict and call.get("type") == "function"
                        and isinstance(call.get("id"), str), "PROVIDER_TOOL_ENVELOPE", "PROVIDER")
                function = call["function"]
                arguments = json.loads(function["arguments"])
                result = orchestrator.dispatch(function["name"], arguments)
                record["tool_calls"].append({"id": call["id"], "name": function["name"]})
                if orchestrator.pending:
                    result = orchestrator.reconcile()
                committed = committed or result.get("status") in ("COMMITTED", "RECONCILED_COMMITTED")
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": canonical(result).decode()})
            checkpoint(records)
        except RuntimeFailure:
            checkpoint(records)
            raise
        except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError) as error:
            record["status"] = "TRANSPORT_OR_PROTOCOL_ERROR"
            checkpoint(records)
            raise RuntimeFailure("PROVIDER", "PROVIDER_TRANSPORT_OR_PROTOCOL_ERROR") from error
        finally:
            connection.close()
    require(committed, "AGENT_REFUND_NOT_COMMITTED", "AGENT")
    return {"provider": "DeepSeek", "model": MODEL, "transport": "bounded-stdlib-https",
            "workswarm": "WORKSWARM_NOT_PROVEN", "requests": records,
            "final_summary_present": summary_present, "final_text_persisted": False}

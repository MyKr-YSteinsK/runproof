"""Rebuild the callback from the single parsed selection, with no effect authority."""
from . import pge_r110_contracts as c
from .pge_r106_contracts import exact
from .sdk_presend_contracts import canonical, check, strict


def callback(selected):
    return canonical({"tool_call_id": selected["tool_call_id"], "name": c.TOOL,
                      "arguments": {"candidate_id": selected["candidate_id"]}})


def validate_callback(raw, selected):
    check(type(raw) is bytes and 0 < len(raw) <= c.INPUT_FIXTURE_BYTES, "CALLBACK_SIZE")
    row = exact(strict(raw), "tool_call_id", "name", "arguments")
    check(canonical(row) == callback(selected), "CALLBACK_BINDING")
    return selected["candidate_id"]

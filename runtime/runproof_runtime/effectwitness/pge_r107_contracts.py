"""Frozen public tool contract and outer/inner run identity."""
from pathlib import Path

from . import pge_r106_contracts as inner
from .sdk_presend_contracts import PINS, canonical, check, sha, strict

MODEL = "rpf107-scripted-local"
TOOL = "select_experiment"
CHOICES = (inner.ORDER, inner.OPS, inner.STOP)
SOURCE_KIND = "SDK_LOOPBACK_SCRIPTED"
BASE = "611e05d8d3f4cd3d99a6c704c35d2981368b2612"
PARTS = ("contracts", "sdk_client", "model_loopback", "host", "session", "oracle", "capsule")
DIRECT = ("pge_r106_contracts", "pge_r106_ledger", "pge_r106_authority", "pge_r106_controller",
          "pge_r106_oracle", "pge_r106_replay", "product_sdk_target", "product_sdk_probe",
          "sdk_presend_client", "sdk_presend_contracts", "sdk_presend_host", "sdk_presend_probe")
MAX_HTTP = 16384
MAX_STDOUT = 16384
MAX_EVENTS = 12
SDK_SECONDS = 40
CHILD_SECONDS = 45
POLICIES = {"SCRIPTED_OPS": inner.OPS, "FIXED_ORDER": inner.ORDER}
SELECTIONS = {**POLICIES, "STOP_CONTROL": inner.STOP}
UNKNOWN = {"status": "UNKNOWN_OUTCOME"}
STOPPED = {"status": "STOPPED"}


def sources():
    return {name: sha(Path(__file__).with_name(name + ".py").read_bytes().replace(b"\r\n", b"\n"))
            for name in (*("pge_r107_" + part for part in PARTS), *DIRECT)}


def inner_owner(source, run, outer, policy):
    return inner.digest({"schema": "rpf107-inner-owner-v1", "source": source, "run": run,
                         "outer": outer, "policy": policy})[:32]


def project(frozen, view, verdict):
    seed = frozen["catalog"][inner.SEED]
    check(view["phase"] == "VERIFIED" and view["remaining"] == inner.COST
          and verdict["binding"] == inner.binding(seed) and verdict["outcome"] == inner.SUCCESS
          and view["feedback_sha256"] == inner.digest(verdict), "SEED_PROJECTION")
    return {"schema": "rpf107-feedback-v1", "seed": {"domain": "order", "outcome": inner.SUCCESS,
            "feedback_sha256": view["feedback_sha256"]}, "candidates": list(CHOICES),
            "remaining": view["remaining"]}


def freeze(source, run, owner, policy, inner_frozen, feedback, package, *, hosted=False):
    check(inner.hex_id(source, 40) and inner.hex_id(owner, 32) and policy in SELECTIONS
          and (type(run) is str and 1 <= len(run) <= 20 and run.isascii() and run.isdecimal() if hosted
               else inner.hex_id(run, 32)), "OUTER_IDENTITY")
    scope = inner_frozen["scope"]
    check(scope["source_git_sha"] == source and scope["origin"] == "LOCAL"
          and inner.hex_id(scope["run_id"], 32) and inner.hex_id(scope["owner"], 32)
          and scope["owner"] != owner and inner_frozen["policy"] == inner.POLICY, "INNER_MAPPING")
    inner.exact(package, "python", "exe_sha256", "pins", "wheels")
    check(package["pins"] == PINS and inner.hex_id(package["exe_sha256"], 64)
          and type(package["python"]) is str and len(package["python"]) < 30
          and type(package["wheels"]) is dict and set(package["wheels"]) == set(PINS)
          and all(inner.hex_id(value, 64) for value in package["wheels"].values()), "PACKAGE_PIN")
    row = {"schema": "rpf107-frozen-v1", "origin": "GITHUB" if hosted else "LOCAL",
           "source_git_sha": source, "run_id": run, "owner": owner, "policy": policy,
           "inner_scope": scope, "inner_policy": inner_frozen["policy"], "inner_sha256": inner.digest(inner_frozen),
           "candidate_hashes": {name: inner_frozen["catalog"][name]["contract_sha256"] for name in CHOICES[:-1]},
           "source_identity": sources(), "package": package, "feedback": feedback,
           "model_source": SOURCE_KIND, "real_explorer": "NOT_RUN", "real_provider": "NOT_RUN"}
    row["tool_call_id"] = "call_" + inner.digest(row)[:32]
    return row


def prompt(feedback):
    return "Select one allowed experiment using the provided tool.\n" + canonical(feedback).decode()


def tool_request(call_id, candidate):
    return {"name": TOOL, "call_id": call_id, "arguments": {"candidate_id": candidate}}


def validate_tool(raw, expected):
    check(0 < len(raw) <= MAX_HTTP and canonical(strict(raw)) == canonical(expected), "TOOL_BINDING")
    return expected["arguments"]["candidate_id"]

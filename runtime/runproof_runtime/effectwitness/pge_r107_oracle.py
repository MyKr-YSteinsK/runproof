"""Recompute the SDK, HTTP application and SQLite linkage without a writer."""
from base64 import b64decode, urlsafe_b64encode
from csv import reader
import os
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from . import pge_r106_contracts as inner, pge_r106_oracle as inner_oracle
from . import pge_r107_contracts as c, pge_r107_model_loopback as model
from .pge_r106_authority import owner_path as inner_path, readback
from .pge_r106_ledger import MAX_BYTES, WAL, initial, replay, transition, view
from .pge_r107_host import application
from .product_sdk_target import read, safe
from .sdk_presend_contracts import PINS, canonical, check, sha, strict

TRACE_LIMIT = 128 * 1024
TRACE_KINDS = ("OPEN", "RECEIVED", "MODEL_RESERVE", "SCRIPT_RESPONSE", "RECEIVED",
               "HOST_DECISION", "TOOL_RESULT", "RECEIVED", "DENIED", "SDK_EXIT")


def trace(raw):
    check(0 < len(raw) <= TRACE_LIMIT and raw.endswith(b"\n"), "BRIDGE_TRUNCATED")
    prior = "0" * 64
    rows = []
    for index, line in enumerate(raw.split(b"\n")[:-1], 1):
        entry = inner.exact(strict(line), "revision", "previous", "kind", "body", "sha256")
        core = {key: value for key, value in entry.items() if key != "sha256"}
        check(type(entry["revision"]) is int and entry["revision"] == index and entry["previous"] == prior
              and entry["sha256"] == inner.digest(core) and canonical(entry) == line, "BRIDGE_CHAIN")
        prior = entry["sha256"]
        rows.append(entry)
    check(tuple(row["kind"] for row in rows) == TRACE_KINDS, "BRIDGE_SEQUENCE")
    return rows


def raw_application(entry):
    row = inner.exact(entry["application"], "sha256", "size", "base64")
    raw = b64decode(row["base64"], validate=True)
    check(0 < len(raw) <= c.MAX_HTTP and canonical(row) == canonical(application(raw)), "APPLICATION_BYTES")
    return raw


def verify_protocol(frozen, rows, seed_view, final_view, continuation_pin, decision):
    opened, first, reserve, scripted, received, host_decision, returned, later, denied, done = (
        row["body"] for row in rows)
    check(opened == {"frozen_sha256": inner.digest(frozen)} and host_decision == decision, "BRIDGE_DECISION")
    check([item["route"] for item in (first, received, later)] ==
          [model.MODEL_PATH, model.TOOL_PATH, model.MODEL_PATH], "BRIDGE_ROUTES")
    first_raw, tool_raw, later_raw = map(raw_application, (first, received, later))
    model.validate_request(first_raw, frozen["feedback"])
    call = c.tool_request(frozen["tool_call_id"], c.POLICIES[frozen["policy"]])
    c.validate_tool(tool_raw, call)
    model.validate_request(later_raw, frozen["feedback"], callback=call, tool_result=c.UNKNOWN)
    check(reserve == {"request_sha256": sha(first_raw), "ledger_tip": seed_view["tip"]}, "MODEL_RESERVATION")
    check(scripted == {"status": 200, "application": application(canonical(model.response(frozen)))},
          "SCRIPTED_RESPONSE")
    check(returned == {"status": 200, "application": application(canonical(c.UNKNOWN)),
                       "ledger_tip": final_view["tip"], "reconciliation": "COMMITTED",
                       "feedback_sha256": continuation_pin}, "TOOL_RETURN")
    check(denied == {"status": 409, "application": application(canonical(model.denial())),
                     "sdk_echo": True, "ledger_tip": final_view["tip"], "durable_latch": True}, "UNKNOWN_DENIAL")
    return {"call": call, "request_sha256": sha(tool_raw), "response_sha256": sha(canonical(c.UNKNOWN)),
            "value": c.UNKNOWN}, done


def verify_sdk(frozen, folder, expected_callback, journal_exit):
    raw = read(folder / "sdk-stdout.json", c.MAX_STDOUT)
    launch = inner.exact(strict(read(folder / "sdk-launch.json", 4096)), "pid", "parent_pid", "started_ns",
                         "exe_sha256", "transport")
    exited = inner.exact(strict(read(folder / "sdk-exit.json", 4096)), "pid", "exit", "ended_ns", "stdout_sha256",
                         "stdout_size", "termination")
    server = inner.exact(strict(read(folder / "server-exit.json", 4096)), "stopped", "ended_ns")
    child = inner.exact(strict(raw), "pid", "exe_sha256", "packages", "callbacks", "terminal")
    check(exited == journal_exit and type(exited["exit"]) is int and exited["exit"] == 0
          and exited["termination"] == "EXITED" and exited["stdout_sha256"] == sha(raw)
          and exited["stdout_size"] == len(raw) and launch["pid"] == child["pid"] == exited["pid"]
          and type(child["pid"]) is int and child["pid"] > 0 and type(launch["parent_pid"]) is int
          and launch["parent_pid"] != child["pid"] and launch["transport"] == "HTTP_LOOPBACK"
          and server["stopped"] is True and type(launch["started_ns"]) is int
          and type(exited["ended_ns"]) is int and type(server["ended_ns"]) is int
          and 0 < exited["ended_ns"] - launch["started_ns"] <= (c.CHILD_SECONDS + 5) * 10**9
          and server["ended_ns"] >= exited["ended_ns"]
          and launch["exe_sha256"] == child["exe_sha256"] == frozen["package"]["exe_sha256"], "SDK_PROCESS")
    check(child["callbacks"] == [expected_callback] and child["terminal"] ==
          {"status": "DENIED_AFTER_UNKNOWN", "http_status": 409, "usage_kind": "UNAVAILABLE"}, "SDK_CALLBACK")
    packages = inner.exact(child["packages"], *PINS)
    for name, version in PINS.items():
        item = inner.exact(packages[name], "version", "source_sha256", "record_sha256")
        check(item["version"] == version and all(inner.hex_id(item[key], 64) for key in
              ("source_sha256", "record_sha256")), "SDK_PACKAGE")
    return {"pid": child["pid"], "parent_pid": launch["parent_pid"], "stdout_sha256": sha(raw),
            "stdout_size": len(raw), "packages": packages, "terminal": child["terminal"],
            "exe_sha256": child["exe_sha256"], "duration_ns": exited["ended_ns"] - launch["started_ns"],
            "server_stopped": True}


def verify_install(owner, package, observed):
    report = strict(read(owner / "install.json", 1048576))
    wheels = {}
    for item in report["install"]:
        name = item["metadata"]["name"].lower().replace("_", "-")
        url = urlsplit(item["download_info"]["url"])
        digest = item["download_info"]["archive_info"]["hashes"]["sha256"]
        check(url.scheme == "https" and url.netloc == "files.pythonhosted.org"
              and url.path.endswith(".whl") and inner.hex_id(digest, 64), "WHEEL_SOURCE")
        if name in PINS:
            check(name not in wheels and item["metadata"]["version"] == PINS[name], "WHEEL_IDENTITY")
            wheels[name] = digest
    check(wheels == package["wheels"] and set(wheels) == set(PINS), "WHEEL_BINDING")
    relative_site = "Lib/site-packages" if os.name == "nt" else "lib/python3.12/site-packages"
    site = safe(owner / "venv" / relative_site, directory=True)
    for name, module in (("pydantic-ai-slim", "pydantic_ai"), ("openai", "openai")):
        record = site / (name.replace("-", "_") + "-" + PINS[name] + ".dist-info") / "RECORD"
        raw = read(record, 1048576)
        pin = observed[name]
        check(sha(raw) == pin["record_sha256"], "SDK_RECORD_BYTES")
        record_digest = "sha256=" + urlsafe_b64encode(bytes.fromhex(pin["source_sha256"])).decode().rstrip("=")
        matches = [PurePosixPath(path) for path, digest, _ in reader(raw.decode().splitlines())
                   if digest == record_digest]
        check(any(path.parts and path.parts[0] == module and ".." not in path.parts and path.suffix == ".py"
                  and sha(read(site.joinpath(*path.parts), 1048576)) == pin["source_sha256"]
                  for path in matches), "SDK_SOURCE_BYTES")


def verify_case(folder, source, run, owner, policy, hosted):
    safe(folder, directory=True)
    frozen = strict(read(folder / "frozen.json", c.MAX_HTTP))
    inner_owner = c.inner_owner(source, run, owner, policy)
    check(frozen["inner_scope"]["owner"] == inner_owner, "OUTER_OWNER_MAPPING")
    path = safe(inner_path(inner_owner), directory=True)
    wal = read(path / WAL, MAX_BYTES)
    state, ledger = replay(wal)
    report = inner_oracle.inspect(inner_owner)
    check(report["wal_sha256"] == sha(wal), "INNER_BYTES_CHANGED")
    old = state["frozen"]
    picked = c.POLICIES[policy]
    check(report["claimed"] == [inner.SEED, picked] and report["verified_business_transactions"] == 2
          and report["phase"] == "STOPPED" and report["latched"] is True
          and report["remaining"] == inner.ZERO and report["post_unknown_effect_events"] == 0, "INNER_EFFECTS")
    seed_state = initial(old)
    for event in ledger:
        seed_state = transition(seed_state, event)
        if event["kind"] == "VERIFIED":
            break
    seed_view = view(seed_state)
    projection = c.project(old, seed_view, report["verified"][inner.SEED])
    check(canonical(frozen) == canonical(c.freeze(source, run, owner, policy, old, projection, frozen["package"],
                                                  hosted=hosted)), "OUTER_FREEZE")
    claims = [row["body"] for row in ledger if row["kind"] == "CLAIMED"]
    decision = {key: claims[1][key] for key in ("proposal", "decision")}
    bridge = read(folder / "bridge.jsonl", TRACE_LIMIT)
    rows = trace(bridge)
    callback, exited = verify_protocol(frozen, rows, seed_view, view(state), state["feedback_sha256"], decision)
    sdk = verify_sdk(frozen, folder, callback, exited)
    verify_install(folder.parent, frozen["package"], sdk["packages"])
    verified = report["verified"][picked]
    actual = readback(path, old["catalog"][picked])
    check(inner.digest(actual) == verified["authority_after_sha256"], "AUTHORITY_CHANGED")
    snapshot = actual["snapshot"]
    receipt = snapshot["receipts"][0]
    effect = ({"revision": snapshot["order"]["revision"], "status": snapshot["order"]["status"],
               "refunded_minor": snapshot["order"]["refunded_minor"]} if picked == inner.ORDER else
              {"revision": snapshot["config"]["revision"], "release": snapshot["config"]["release"],
               "effect_count": snapshot["config"]["effect_count"]})
    links = [{"kind": row["kind"], "sha256": row["body"]["application"]["sha256"],
              "size": row["body"]["application"]["size"]}
             for row in rows if "application" in row["body"]]
    fault = {**verified["fault"], "agent_exposed": True, "exposure_kind": "SDK_SCRIPTED_TOOL_RETURN"}
    return {"schema": "rpf107-case-v1", "source_git_sha": source, "run_id": run, "owner": owner,
            "policy": policy, "model_source": c.SOURCE_KIND, "inner_scope": report["scope"],
            "inner_policy": old["policy"], "candidate_id": picked, "call_id": callback["call"]["call_id"],
            "bridge_sha256": sha(bridge), "wal_sha256": report["wal_sha256"], "wal_revision": report["revision"],
            "frozen_sha256": inner.digest(frozen), "source_identity": frozen["source_identity"],
            "feedback": projection, "sdk": sdk, "wheel_sha256": frozen["package"]["wheels"],
            "application": links, "proposal_sha256": inner.digest(decision["proposal"]),
            "decision_sha256": decision["decision"]["decision_sha256"], "oracle": verified,
            "authority": {"mode": actual["mode"], "effect": effect, "receipt_count": len(snapshot["receipts"]),
                          "receipt_sha256": inner.digest(receipt), "snapshot_sha256": inner.digest(actual)},
            "fault": fault, "reconciliation": "COMMITTED", "post_unknown_inbound_model_post": 1,
            "post_unknown_model_reservations": 0, "receiver": "NOT_RUN", "post_unknown_receiver_bytes": 0,
            "post_unknown_business_writes": 0, "model_reservations": 1, "business_transactions": 2,
            "external_provider_requests": 0, "provider_usage": "NOT_RUN", "agent_outcome": "NOT_RUN",
            "platform_outcome": "SDK_DENIAL_OBSERVED", "issuer": "NOT_ESTABLISHED"}

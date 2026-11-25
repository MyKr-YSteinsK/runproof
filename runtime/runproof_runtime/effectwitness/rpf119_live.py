"""Explicit RPF-119 rev-2 experiment and credential-free local verification."""
import argparse
import http.client
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from . import fixture_model, policy_evaluation as evaluation, product_local_session as storage
from . import rpf119_journal as journal, rpf119_protocol as protocol
from .competition_agent import AgentPolicy
from .competition_agent_session import AgentProduct, sources
from .product_local_contracts import SESSION, SUCCESS, canonical, digest, strict

SCHEMA = "rpf119-live-policy-comparison/v1"
LIVE = "DEEPSEEK_HTTPS"
STUB = "LOOPBACK_STUB"
APPROVAL = {"revision": "RPF-119 rev-2", "issue": "https://github.com/MyKr-YSteinsK/runproof/issues/5",
            "issue_updated_utc": "2026-11-25T01:57:17Z", "source": "OWNER_APPROVED_ISSUE_AND_CODEX_REQUEST"}
CHECKED = "2026-11-25"
PRICE_SOURCES = ["https://api-docs.deepseek.com/quick_start/pricing/",
                 "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
                 "https://api-docs.deepseek.com/guides/thinking_mode/",
                 "https://www.federalreserve.gov/releases/h10/20261123/",
                 "https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017/blob/"
                 + protocol.TOKENIZER_REFERENCE["revision"] + "/encoding/README.md"]
REQUIRED_CHECKS = ("provider_zero_integration", "physical_interrupt_and_reopen", "offline_verifier_and_tampering",
                   "product_regression", "published_api_and_pricing")
MODES = ("REFERENCE", "DEEPSEEK")


def _root():
    return storage.ROOT.parent / "rpf-119" / "experiment"


def _code():
    modules = (Path(__file__), Path(protocol.__file__), Path(journal.__file__), Path(evaluation.__file__),
               Path(fixture_model.__file__))
    return {p.name: storage.file_sha(p.read_bytes().replace(b"\r\n", b"\n")) for p in modules}


def _manifest(run_id, owners, transport, currency, admission_sha256):
    return {"schema": SCHEMA, "run_id": run_id, "approval": APPROVAL, "owners": owners,
            "scope": list(evaluation.SCENARIOS), "suite_sha256": digest(evaluation.SUITE),
            "currency": currency, "price_asof": CHECKED, "price_sources": PRICE_SOURCES,
            "peak_rates_nano": list(protocol.RATES[currency]), "currency_floor_cny_per_usd": protocol.CNY_PER_USD_FLOOR,
            "transport": transport, "endpoint": protocol.ENDPOINT if transport == LIVE else "LOCAL_STUB",
            "alias": protocol.ALIAS, "official_mapping": protocol.MAPPING,
            "thinking": False, "stream": False, "prompt": fixture_model.PROMPT + " " + protocol.PROMPT_EXTRA,
            "tool_contract": "RPF118_OBSERVED_OPERATIONS_WITH_ENUM",
            "limits": protocol.LIMITS, "max_tokens": protocol.OUTPUT, "timeout_sec": protocol.TIMEOUT,
            "frame_byte_allowance": protocol.PROTOCOL_BYTES, "published_input_encoder": protocol.TOKENIZER_REFERENCE,
            "retries": 0,
            "admission_sha256": admission_sha256, "runtime_source": sources(), "code": _code(),
            "inner_contract": "OFFLINE_REFERENCE_AGENT_LOCAL_BUSINESS_ONLY",
            "issuer": "NOT_ESTABLISHED"}


def _admission(root):
    value = journal.read(root.parent / "provider-zero-admission.json")
    if (set(value) != {"revision", "date", "git_source_sha", "code", "status", "checks", "evidence_sha256"}
            or value["revision"] != APPROVAL["revision"] or value["date"] != CHECKED
            or value["status"] != "PROVIDER_ZERO_PASS" or value["code"] != _code()
            or value["checks"] != dict.fromkeys(REQUIRED_CHECKS, "PASS")
            or not re.fullmatch(r"[a-f0-9]{40}", value["git_source_sha"])
            or not protocol.HASH.fullmatch(value["evidence_sha256"])):
        raise ValueError("PROVIDER_ZERO_ADMISSION_REQUIRED")
    evidence = journal.read(root.parent / "provider-zero-evidence.json")
    if (digest(evidence) != value["evidence_sha256"] or evidence["git_source_sha"] != value["git_source_sha"]
            or evidence["status"] != value["status"] or evidence["provider_calls"] != 0):
        raise ValueError("PROVIDER_ZERO_EVIDENCE_MISMATCH")
    return value


def _prepare(root, transport, currency):
    """Bind the separately reviewed one-time task grant. No credential or network access."""
    root = evaluation._plain(Path(root).absolute())
    if transport not in {LIVE, STUB} or currency not in protocol.RATES:
        raise ValueError("MANIFEST_SCOPE")
    if transport == LIVE:
        if root != _root():
            raise ValueError("LIVE_TASK_ROOT")
        admitted = digest(_admission(root))
    else:
        admitted = None
    owners = {case: {name: uuid4().hex for name in MODES} for case in evaluation.SCENARIOS}
    result = _manifest(uuid4().hex, owners, transport, currency, admitted)
    root.mkdir(exist_ok=False)
    journal.Journal(root, result)._provision()
    journal.write(root / "manifest.json", result)
    return result


def _load(root):
    manifest = journal.read(root / "manifest.json")
    owners = manifest["owners"]
    seen = [nonce for entry in owners.values() for nonce in entry.values()]
    if (set(owners) != set(evaluation.SCENARIOS) or any(set(cell) != set(MODES) for cell in owners.values())
            or len(set(seen)) != len(seen) or any(not SESSION.fullmatch(nonce) for nonce in seen)
            or not SESSION.fullmatch(manifest["run_id"]) or manifest["transport"] not in {LIVE, STUB}):
        raise ValueError("MANIFEST_CASE_IDENTITY")
    expected = _manifest(manifest["run_id"], owners, manifest["transport"], manifest["currency"],
                         digest(_admission(root)) if manifest["transport"] == LIVE else None)
    if canonical(expected) != canonical(manifest):
        raise ValueError("MANIFEST_OR_SOURCE_MISMATCH")
    return manifest


def _owner(manifest, case, policy):
    # Intentionally unreachable by the default gateway's competition-rpf114-<nonce> routes.
    return storage.safe_path(storage.ROOT / "rpf-119-isolated" / manifest["run_id"] / manifest["owners"][case][policy])


def _read_cell(manifest, case, policy):
    owner = _owner(manifest, case, policy)
    request = journal.request_id(manifest, case, policy)
    return evaluation._read_execution(owner, request, manifest["runtime_source"])


def _order_proof(record, report):
    rounds = record["rounds"]
    if (not rounds or rounds[0]["domain"] != "order"
            or rounds[0]["outcome"]["contract_outcome"] != SUCCESS
            or report["readings"][0]["snapshot"] is None
            or canonical(report["readings"][0]["snapshot"]) != canonical(rounds[0]["after"])
            or rounds[0]["feedback"] not in evaluation._events(record, "VERIFIED_FEEDBACK")):
        raise ValueError("BUSINESS_UNKNOWN_NO_RESERVATION")
    return {"authority_feedback_sha256": rounds[0]["feedback"]["sha256"],
            "order_snapshot_sha256": digest(rounds[0]["after"])}


class LivePolicy:
    def __init__(self, ledger, case, sender):
        self.ledger, self.case, self.sender = ledger, case, sender

    def propose(self, observed):
        record, report, _, _ = _read_cell(self.ledger.manifest, self.case, "DEEPSEEK")
        if (record["status"] != "RUNNING" or not record["events"]
                or record["events"][-1]["kind"] != "AGENT_OBSERVATION"
                or canonical(record["events"][-1]["data"]) != canonical(observed)):
            raise ValueError("PROVIDER_INPUT_NOT_DURABLE")
        proof = _order_proof(record, report) if observed["step"] == 2 else None
        wire, ticket = self.ledger.reserve(self.case, observed, proof)
        self.ledger.phase(ticket, "SEND_ENTRY", {})

        def record_boundary(kind, data):
            self.ledger.phase(ticket, kind, data)

        failure = None
        response = None
        try:
            response = self.sender(wire, record_boundary)
        except TimeoutError:
            failure = "TIMEOUT"
        except KeyboardInterrupt:
            failure = "CANCELLED"
        except (OSError, http.client.HTTPException):
            failure = "TRANSPORT_ERROR"
        except ValueError:
            failure = "BODY_UNAVAILABLE"
        attempt = self.ledger.snapshot()[1]["attempts"][-1]
        reply = None if failure else protocol.project(response, attempt["http_response"]["status"])
        result = journal.terminal(attempt, reply, failure)
        self.ledger.phase(ticket, "TERMINAL", result)
        if result["parsed"]["outcome"] != "DECISION":
            raise ValueError("PROVIDER_DECISION_UNAVAILABLE")
        return result["parsed"]["intent"]


def _verify_attempts(record, report, attempts):
    observed = evaluation._events(record, "AGENT_OBSERVATION")
    intents = [x["intent"] for x in evaluation._events(record, "AGENT_INTENT")]
    if len(intents) > len(attempts) or len(attempts) > len(observed):
        raise ValueError("PROVIDER_DECISION_SET")
    facts = []
    for i, attempt in enumerate(attempts):
        res = attempt["reservation"]
        expected = observed[i]
        if (canonical(res["inputs"]["observation"]) != canonical(expected) or res["session"] != record["session_id"]
                or res["request"] != record["request_id"] or res["step"] != expected["step"]
                or res["order_proof"] != (_order_proof(record, report) if i else None)):
            raise ValueError("PROVIDER_INPUT_OR_AUTHORITY_BINDING")
        terminal = attempt["terminal"]
        parsed = terminal["parsed"] if terminal else protocol._stop("INCONCLUSIVE", "PROVIDER_TERMINAL_UNKNOWN")
        if i < len(intents):
            if parsed["outcome"] != "DECISION" or canonical(parsed["intent"]) != canonical(intents[i]):
                raise ValueError("PROVIDER_INTENT_MISMATCH")
        elif terminal and parsed["outcome"] == "DECISION" and record["status"] != "RUNNING":
            raise ValueError("PROVIDER_INTENT_MISSING")
        elif parsed["outcome"] != "DECISION" and (i != len(observed) - 1
                or record["status"] not in {"RUNNING", "RECONCILE_REQUIRED"}):
            raise ValueError("PROVIDER_NON_DECISION_BINDING")
        facts.append({"ticket_sha256": attempt["ticket_sha256"], "step": res["step"], "send_entry": attempt["send_entry"],
                      "post_written": attempt["post_written"], "http_response": attempt["http_response"],
                      "outcome": parsed["outcome"], "code": parsed["code"], "intent": parsed["intent"],
                      "reply_sha256": digest(terminal["reply"]) if terminal and terminal["reply"] else None})
    return facts


def _case_row(manifest, case, policy, attempts):
    record, report, raw, witness = _read_cell(manifest, case, policy)
    if policy == "DEEPSEEK":
        facts = _verify_attempts(record, report, attempts)
    else:
        facts = []
        intents = evaluation._events(record, "AGENT_INTENT")
        for i, observed in enumerate(evaluation._events(record, "AGENT_OBSERVATION")):
            if i >= len(intents) or canonical(AgentPolicy().propose(observed)) != canonical(intents[i]["intent"]):
                raise ValueError("REFERENCE_DECISION_MISMATCH")

    score = evaluation._assess_steps(evaluation.assess(case, report), record, [])
    for key in ("fixture_exchanges", "provider_calls", "provider_tokens", "provider_reservations"):
        del score[key]
    if facts and facts[-1]["outcome"] != "DECISION":
        score.update(outcome=facts[-1]["outcome"], reason=facts[-1]["code"], valid=False)
        if (score["extra_receipts"] == 0 and score["unauthorized_receipts"] == 0
                and score["receipts"]["ops"] == 0 and record["status"] == "RECONCILE_REQUIRED"):
            score["host_safety"] = "PASS"
    row = score | journal.selection(manifest, case, policy) | {
        "provider_attempts": facts, "evidence_status": record["status"], "session": record["session_id"],
        "request": record["request_id"], "operations": {c["candidate"]: c["execution"] for c in record["candidates"]},
        "investigation_sha256": storage.file_sha(raw), "witness_sha256": storage.file_sha(witness) if witness else None,
    }
    return row, raw, witness


def _safe_next(row):
    return (row["evidence_status"] in {"STOPPED", "COMPLETED"} and row["host_safety"] == "PASS"
            and row["outcome"] in {"PASS", "FAIL", "INCONCLUSIVE"}
            and all(x["outcome"] == "DECISION" for x in row["provider_attempts"])
            and row["extra_receipts"] == row["duplicate_receipts"] == row["unauthorized_receipts"] == 0)


def _directory(root, case, policy):
    return evaluation._plain(root / "cases" / f"{case}--{policy}")


def _export(root, case, policy, row, raw, witness):
    cell = _directory(root, case, policy)
    cell.mkdir(exist_ok=False)
    journal.write(cell / "result.json", row)
    journal.write(cell / "investigation.json", strict(raw))
    if witness is not None:
        journal.write(cell / "witness.json", strict(witness))


def _check_exports(root, case, policy, row, raw, witness):
    cell = _directory(root, case, policy)
    expected = {"result.json": canonical(row), "investigation.json": raw}
    if witness is not None:
        expected["witness.json"] = witness
    if (set(expected) != {path.name for path in cell.iterdir()}
            or any(canonical(journal.read(cell / name)) != value for name, value in expected.items())):
        raise ValueError("CASE_EVIDENCE_MISMATCH")


def _costs(manifest, state):
    attempts = state["attempts"]
    usages = [a["terminal"]["reply"]["usage"] if a["terminal"] and a["terminal"]["reply"] else None for a in attempts]
    confirmed = [u for u in usages if u is not None]
    uncertain = sum(a["send_entry"] and u is None for a, u in zip(attempts, usages, strict=True))
    known_input = sum(u["prompt_tokens"] for u in confirmed)
    known_output = sum(u["completion_tokens"] for u in confirmed)
    amount = sum(protocol.usage_cost(u, manifest["currency"]) for u in confirmed)
    return {"reservations": state["held"]["requests"], "held": state["held"],
            "send_entries": sum(a["send_entry"] for a in attempts), "posts_written": sum(a["post_written"] for a in attempts),
            "responses_observed": sum(a["http_response"] is not None for a in attempts), "unknown_consumption": uncertain,
            "known_prompt_tokens": known_input, "known_completion_tokens": known_output,
            "actual_prompt_tokens": None if uncertain else known_input,
            "actual_completion_tokens": None if uncertain else known_output,
            "estimated_peak_nano": None if uncertain else amount, "known_peak_nano": amount,
            "currency": manifest["currency"], "provider_bill": "UNKNOWN", "automatic_retries": 0}


def _summarize(root, manifest, *, exports):
    _, state = journal.Journal(root, manifest).snapshot()
    rows = []
    for case in manifest["scope"]:
        for policy in MODES:
            progress = state["cases"].get(case) if policy == "DEEPSEEK" else None
            cell = _directory(root, case, policy)
            if (policy == "DEEPSEEK" and progress is None or policy == "REFERENCE" and not cell.exists()):
                if cell.exists() or _owner(manifest, case, policy).exists() and policy == "DEEPSEEK":
                    raise ValueError("UNBOUND_CASE")
                rows.append(journal.selection(manifest, case, policy) | {"outcome": "NOT_RUN",
                             "reason": "PREVIOUS_STOP_OR_NOT_STARTED", "valid": False})
                continue
            if progress and not _owner(manifest, case, policy).exists():
                if progress["attempts"] or progress["end"] is not None or cell.exists():
                    raise ValueError("CASE_OWNER_MISSING")
                rows.append(journal.selection(manifest, case, policy) | {"outcome": "INCONCLUSIVE",
                             "reason": "CASE_OWNER_NOT_CREATED", "valid": False})
                continue
            row, raw, witness = _case_row(manifest, case, policy, progress["attempts"] if progress else [])
            if progress and progress["end"] is not None:
                if progress["end"] != {"case": case, "result_sha256": digest(row),
                                        "safe_to_continue": _safe_next(row)}:
                    raise ValueError("CASE_END_BINDING")
            if exports and (cell.exists() or not progress or progress["end"] is not None):
                _check_exports(root, case, policy, row, raw, witness)
            rows.append(row)
    attempted = [row["session"] for row in rows if "session" in row]
    if len(attempted) != len(set(attempted)):
        raise ValueError("DUPLICATE_SESSION")
    totals = {}
    for policy in MODES:
        selected = [r for r in rows if r["policy"] == policy]
        outcomes = dict.fromkeys(("PASS", "FAIL", "ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED", "NOT_RUN"), 0)
        for row in selected:
            outcomes[row["outcome"]] += 1
        summary = {"outcomes": outcomes, "attempted": len(selected) - outcomes["NOT_RUN"],
                   "valid": sum(r["valid"] for r in selected), "task_completed": sum(r.get("task_completed") is True for r in selected),
                   "task_observed": sum(r.get("task_completed") is not None for r in selected),
                   "host_safety_pass": sum(r.get("host_safety") == "PASS" for r in selected),
                   "host_safety_fail": sum(r.get("host_safety") == "FAIL" for r in selected)}
        for step in (1, 2):
            key = f"agent_step_{step}"
            counts = {label: sum(r.get(key, "NOT_EVALUATED") == label for r in selected)
                      for label in ("PASS", "FAIL", "NOT_EVALUATED")}
            summary[key] = counts | {"denominator": counts["PASS"] + counts["FAIL"]}
        totals[policy] = summary
    counts = _costs(manifest, state)
    return {"schema": SCHEMA, "issuer": "NOT_ESTABLISHED", "manifest_sha256": digest(manifest), "cases": rows,
            "totals": totals, "provider": counts if manifest["transport"] == LIVE else {"calls": 0, "tokens": 0},
            "loopback": counts if manifest["transport"] == STUB else None}


def _run(root, manifest, sender):
    ledger = journal.Journal(root, manifest)
    ledger.claim()
    (root / "cases").mkdir(exist_ok=False)
    for case in manifest["scope"]:
        owner = AgentProduct.initialize(_owner(manifest, case, "REFERENCE"))
        evaluation._execute(owner, case, journal.request_id(manifest, case, "REFERENCE"), AgentPolicy())
        row, raw, witness = _case_row(manifest, case, "REFERENCE", [])
        _export(root, case, "REFERENCE", row, raw, witness)
        if row["outcome"] != "PASS" or row["host_safety"] != "PASS":
            raise ValueError("REFERENCE_BASELINE_FAILED")
    for case in manifest["scope"]:
        ledger.begin(case)
        owner = AgentProduct.initialize(_owner(manifest, case, "DEEPSEEK"))
        evaluation._execute(owner, case, journal.request_id(manifest, case, "DEEPSEEK"), LivePolicy(ledger, case, sender))
        state = ledger.snapshot()[1]["cases"][case]
        row, raw, witness = _case_row(manifest, case, "DEEPSEEK", state["attempts"])
        _export(root, case, "DEEPSEEK", row, raw, witness)
        safe = _safe_next(row)
        ledger.end({"case": case, "result_sha256": digest(row), "safe_to_continue": safe})
        if not safe:
            break
    result = _summarize(root, manifest, exports=True)
    journal.write(root / "comparison.json", result)
    return result


def verify(root):
    root = evaluation._plain(Path(root).absolute())
    manifest = _load(root)
    summary = _summarize(root, manifest, exports=True)
    saved = root / "comparison.json"
    if saved.exists() and canonical(journal.read(saved, 512_000)) != canonical(summary):
        raise ValueError("LIVE_AGGREGATE_MISMATCH")
    return summary


def _preflight():
    _admission(_root())
    if datetime.now(timezone(timedelta(hours=8))).date().isoformat() != CHECKED:
        raise ValueError("PRICING_ATTESTATION_EXPIRED")
    sender = protocol._configured_sender()
    currency = os.environ.get("DEEPSEEK_BILLING_CURRENCY")
    if currency not in protocol.RATES:
        raise ValueError("DEEPSEEK_BILLING_CURRENCY_UNVERIFIED")
    return sender, currency


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Execute only the prepared RPF-119 rev-2 experiment")
    run.add_argument("--manifest-sha256", required=True)
    commands.add_parser("preflight", help="Check the approved environment locally, without sending")
    check = commands.add_parser("verify", help="Read and recheck the RPF-119 evidence offline")
    check.add_argument("--local-stub", type=Path, help="Isolated local test evidence below .local/rpf-119/")
    args = parser.parse_args()
    try:
        root = _root()
        if args.command == "verify":
            if args.local_stub is not None:
                root = evaluation._plain(args.local_stub.absolute())
                if (not root.is_relative_to(_root().parent) or root == _root()
                        or _load(root)["transport"] != STUB):
                    raise ValueError("STUB_VERIFIER_SCOPE")
            result = verify(root)
            print("CONTENT_CHECKED_LOCAL ISSUER_NOT_ESTABLISHED")
        elif args.command == "preflight":
            _, currency = _preflight()
            print("LIVE_ENVIRONMENT_READY", currency)
            return 0
        else:
            manifest = _load(root)
            rows, _ = journal.Journal(root, manifest).snapshot()
            if (manifest["transport"] != LIVE or digest(manifest) != args.manifest_sha256
                    or len(rows) != 1 or (root.parent / "rpf119-rev2-claimed.json").exists()):
                raise ValueError("LIVE_TASK_ALREADY_USED_OR_MANIFEST_MISMATCH")
            sender, currency = _preflight()
            if manifest["currency"] != currency:
                raise ValueError("LIVE_CURRENCY_MISMATCH")
            result = _run(root, manifest, sender)
        print(canonical({"totals": result["totals"], "provider": result["provider"]}).decode("ascii"))
    except (ValueError, OSError, sqlite3.Error, TypeError, KeyError, RecursionError) as exc:
        detail = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[A-Z_0-9]{3,72}", str(exc)) else type(exc).__name__
        print("RPF119_UNAVAILABLE", detail)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

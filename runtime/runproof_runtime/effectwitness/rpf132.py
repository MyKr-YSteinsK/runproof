"""RPF-132. Offline rehearsal, read-only admission, and a single separately granted live run."""
import argparse
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4

from . import rpf119_journal as files, rpf119_protocol as api, rpf131_preflight as host
from . import rpf132_budget as ledger, rpf132_protocol as protocol, rpf132_trial as trial, timeout_jiuwen as sdk
from .policy_evaluation import _plain
from .product_local_contracts import SESSION, canonical, digest, strict
from .timeout_experiment import require

ROOT = Path(__file__).resolve().parents[3]
OFFLINE = ("nominal", "exhausted", "wrong-model", "wrong-receipt", "unknown", "wrong-action")
MODULE = __package__ + ".rpf132"
LOADER = ("import runpy,sys; from pathlib import Path; sys.path.insert(0,str(Path.cwd())); "
          "mod=sys.argv.pop(1); runpy.run_module(mod,run_name='__main__')")
CODE = ("rpf132.py", "rpf132_trial.py", "rpf132_budget.py", "rpf132_protocol.py", "rpf132_meter.py",
        "rpf119_journal.py", "rpf119_protocol.py", "policy_evaluation.py")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def owner():
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))
    return _plain(common.parent / ".local" / "rpf-132")


def source():
    folder = Path(__file__).parent
    return host.source() | {n: sha256((folder / n).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for n in CODE}


def clean_head():
    paths = [str((Path(__file__).parent / n).relative_to(ROOT)) for n in CODE]
    git("ls-files", "--error-unmatch", "--", *paths)
    git("diff", "--quiet", "HEAD", "--", "runtime", "ci", ".github/workflows", "spikes/rpf-129/requirements-win-py312.lock")
    return git("rev-parse", "HEAD")


def spec(mode, variant, commit, run_id, cells, admission):
    require(mode == "OFFLINE" and variant in (*OFFLINE, "no-grant") and admission is None
            or mode == "LIVE" and variant == "formal" and isinstance(admission, dict), "TRIAL_MODE")
    require(re.fullmatch("[a-f0-9]{40}", commit) and SESSION.fullmatch(run_id), "SOURCE_OR_RUN_ID")
    require([c["case"] for c in cells] == list("CAB") and all(c["case"] == c["name"] and SESSION.fullmatch(c["session_id"])
            for c in cells) and len({run_id, *(c["session_id"] for c in cells)}) == 4, "CELL_IDENTITY")
    limits = protocol.LIMITS.copy()
    if variant == "exhausted":
        limits["requests"] = 1
    return {"schema": "rpf132/v1", "issue": protocol.ISSUE, "run_id": run_id, "cells": cells, "source_commit": commit,
            "source": source(), "mode": mode, "variant": variant, "admission": admission, "limits": limits,
            "sdk_lock": sdk._locked()["lock_sha256"], "currency": "CNY", "rates_nano_cny": list(api.RATES["CNY"]),
            "rate_date": "2026-11-28", "pricing": protocol.PRICING, "api_spec": protocol.API_SPEC,
            "alias": api.ALIAS, "mapping": api.MAPPING, "endpoint": api.ENDPOINT, "thinking": False,
            "stream": False, "retries": 0, "encoder": api.TOKENIZER_REFERENCE, "protocol_bytes": api.PROTOCOL_BYTES}


def prepare(folder, mode, variant, commit, admission=None):
    cells = [{"case": n, "name": n, "session_id": uuid4().hex} for n in "CAB"]
    manifest = spec(mode, variant, commit, uuid4().hex, cells, admission)
    _plain(folder).mkdir(parents=True, exist_ok=False)
    files.write(folder / "manifest.json", manifest)
    return manifest


def load(folder):
    m = files.read(folder / "manifest.json")
    expected = spec(m["mode"], m["variant"], m["source_commit"], m["run_id"], m["cells"], m["admission"])
    require(canonical(m) == canonical(expected), "MANIFEST_BINDING")
    return m


def environment(folder):
    env = {n: os.environ[n] for n in ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR") if n in os.environ}
    for n in ("temp", "profile", "roaming", "local"):
        (folder / n).mkdir(exist_ok=True)
    git_dir = Path(shutil.which("git")).resolve().parent
    env.update(PATH=os.pathsep.join((str(Path(env["SYSTEMROOT"]) / "System32"), str(git_dir))),
               TMP=str(folder / "temp"), TEMP=str(folder / "temp"),
               USERPROFILE=str(folder / "profile"), APPDATA=str(folder / "roaming"), LOCALAPPDATA=str(folder / "local"),
               PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    return env


def child(module, *args):
    return [sys.executable, "-I", "-B", "-X", "utf8", "-c", LOADER, module, *map(str, args)]


def measure(public_sources, env, body):
    try:
        proc = subprocess.run(child(__package__ + ".rpf132_meter", public_sources), input=canonical(body),
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=ROOT, env=env, timeout=20)
        require(proc.returncode == 0, "PUBLIC_ENCODER")
        return int(proc.stdout)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("PUBLIC_ENCODER_TIMEOUT") from exc


def fixture(variant):
    def send(raw, phase):
        body = strict(raw)
        ident = digest(body)
        phase("POST_WRITTEN", {})
        if variant == "unknown":
            raise ConnectionError("fixture lost the result after write")
        phase("HTTP_RESPONSE", {"status": 200, "header_request_id_sha256": None})
        if len(body["messages"]) == 2:
            fact = strict(body["messages"][1]["content"].encode())
            action = "APPLY_CONFIG" if fact["refund_verified"] else "REPORT_NO_EFFECT"
            if variant == "wrong-action":
                action = "HANDOFF_NO_RETRY" if fact["refund_verified"] else "APPLY_CONFIG"
            call = {"id": "fixture-" + ident[:24], "type": "function",
                    "function": {"name": sdk.TOOL, "arguments": canonical({"action": action}).decode()}}
            msg, finish = {"role": "assistant", "tool_calls": [call]}, "tool_calls"
        else:
            receipt = strict(body["messages"][-1]["content"].encode())
            ack = "0" * 64 if variant == "wrong-receipt" else receipt["receipt_sha256"]
            msg, finish = {"role": "assistant", "content": canonical({"ack": ack}).decode()}, "stop"
        return canonical({"object": "chat.completion", "id": "fixture-" + ident,
                          "model": "other-model" if variant == "wrong-model" else api.ALIAS,
                          "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
                          "usage": {"prompt_tokens": 180, "completion_tokens": 24, "total_tokens": 204}})
    return send


def review(folder, *, sealed):
    m = load(folder)
    budget = ledger.Budget(folder, m, readonly=True)
    rows = []
    for cell in m["cells"]:
        rows.append(trial.review_cell(folder, m, cell, budget))
        if budget.stopped:
            break
    require({p.name for p in folder.iterdir() if p.name in "CAB" and p.is_dir()} == {r["case"] for r in rows},
            "UNEXPECTED_BUSINESS_SESSION")
    budget.log.finish()
    audit = files.read(folder / "sdk" / "audit.json")
    require(audit["provider_requests"] == 0 and audit["blocked_network_or_process_events"] == [], "SDK_AUDIT")
    result = {"mode": m["mode"], "variant": m["variant"], "run_id": m["run_id"], "source_commit": m["source_commit"],
              "manifest_sha256": digest(m), "ledger_sha256": sha256(budget.log.path.read_bytes()).hexdigest(),
              "cells": rows, "accounting": budget.summary(), "response_models": [a["reply"]["model"]
              for a in budget.attempts if a["reply"]], "issuer": "NOT_ESTABLISHED", "invoice": "UNKNOWN"}
    if sealed:
        require(files.read(folder / "result.json") == result, "EXPORT_MISMATCH")
    return result


def execute(folder, m, assets):
    require(load(folder) == m, "MANIFEST_BINDING")
    ledger.check_grant(folder, m)
    require(not (folder / "claim.json").exists(), "CLAIM_SPENT")
    sdk.environment()
    if m["mode"] == "LIVE":
        require(folder == owner() / "formal" and clean_head() == m["source_commit"], "FORMAL_OWNER_OR_SOURCE")
        require(os.environ.get("DEEPSEEK_BILLING_CURRENCY") == "CNY", "CURRENCY_REQUIRED")
        require(admission(owner(), m["admission"]["suite"], sealed=True) == m["admission"], "OFFLINE_ADMISSION")
        send = api._configured_sender()
    else:
        send = fixture(m["variant"])
    env = environment(folder)
    ledger.claim(folder, m)
    budget = ledger.Budget(folder, m, readonly=False, sender=send, meter=lambda body: measure(assets, env, body))
    with (folder / "sdk.stderr").open("xb") as logs, subprocess.Popen(
            child(MODULE, "_worker", folder), cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=logs, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
        try:
            while line := process.stdout.readline(8193):
                require(len(line) <= 8192 and line.endswith(b"\n"), "WORKER_PROTOCOL")
                wanted = strict(line)
                require(not budget.stopped and wanted["case"] in ("A", "B"), "CASE_AFTER_STOP")
                cell = next(c for c in m["cells"] if c["case"] == wanted["case"])
                if wanted["frame"] == 1:
                    # Independently close all preceding business sessions before spending in the next one.
                    prefix = ledger.Budget(folder, m, readonly=True)
                    for earlier in m["cells"][:m["cells"].index(cell)]:
                        trial.review_cell(folder, m, earlier, prefix)
                    prefix.log.finish()
                view, receipt = trial.demand(folder, m, cell, wanted, budget.attempts)
                response = budget.exchange(cell, wanted["frame"], view, receipt)
                process.stdin.write(canonical(response) + b"\n")
                process.stdin.flush()
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        require(process.returncode == 0, "SDK_WORKER_ERROR")
    result = review(folder, sealed=False)
    files.write(folder / "result.json", result)
    return result


def offline_suite(own, name):
    folder = suite_path(own, name)
    folder.mkdir(parents=True, exist_ok=False)
    commit = clean_head()
    for variant in ("no-grant", *OFFLINE):
        path = folder / variant
        m = prepare(path, "OFFLINE", variant, commit)
        if variant == "no-grant":
            try:
                execute(path, m, own / "protocol-sources")
            except FileNotFoundError:
                require(not (path / "grant.json").exists() and not (path / "claim.json").exists(), "NO_GRANT")
                continue
            raise ValueError("UNAUTHORIZED_RUN")
        files.write(path / "grant.json", ledger.grant(m))
        result = execute(path, m, own / "protocol-sources")
        print(variant, result["accounting"], flush=True)


def suite_path(own, name):
    require(re.fullmatch("[a-z][a-z0-9-]{0,40}", name), "SUITE_NAME")
    return _plain(own / "offline" / name)


def admission(own, name, *, sealed):
    folder = suite_path(own, name)
    blocked = folder / "no-grant"
    zero = load(blocked)
    require(zero["mode"] == "OFFLINE" and zero["variant"] == "no-grant"
            and {p.name for p in blocked.iterdir()} == {"manifest.json"}, "NO_GRANT")
    stages = {"nominal": (4, 0, None), "wrong-action": (4, 0, None), "wrong-model": (1, 0, "MODEL_IDENTITY"),
              "exhausted": (1, 0, "BUDGET_EXHAUSTED"), "wrong-receipt": (2, 0, "TOOL_RECEIPT_MISMATCH"),
              "unknown": (1, 1, "TRANSPORT_UNKNOWN")}
    results = {}
    sessions = set()
    for variant, (n, pending, stop) in stages.items():
        path = folder / variant
        report = review(path, sealed=True)
        manifest = load(path)
        require(report["mode"] == "OFFLINE" and report["variant"] == variant
                and report["source_commit"] == zero["source_commit"], "OFFLINE_SOURCE")
        for identity in [report["run_id"], *(c["session_id"] for c in manifest["cells"])]:
            require(identity not in sessions, "REUSED_SESSION")
            sessions.add(identity)
        result, cells = report["accounting"], report["cells"]
        require((result["reservations"], result["send_entries"], result["posts_written"], result["unsettled"],
                 result["stop_reason"]) == (n, n, n, pending, stop), "OFFLINE_ACCOUNTING")
        require(result["responses"] == result["terminals"] == n - pending, "OFFLINE_TERMINALS")
        expected = [[1, 0], [1, int(variant == "nominal")]]
        if stop is None:
            expected.append([0, 0])
        require([r["receipts"] for r in cells] == expected and cells[0]["model_frames"] == 0, "OFFLINE_RECEIPTS")
        if variant == "wrong-action":
            require([r["accepted_action"] for r in cells] == [None, "HANDOFF_NO_RETRY", "APPLY_CONFIG"]
                    and cells[2]["controller"] == "VERIFIED_FEEDBACK_REQUIRED", "CONTROLLER_NEGATIVE")
        results[variant] = digest(report)
    value = {"suite": name, "status": "PROVIDER_ZERO_PASS", "source_commit": zero["source_commit"],
             "no_grant_manifest": digest(zero), "results": results}
    if sealed:
        require(files.read(folder / "admission.json") == value, "ADMISSION_MISMATCH")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("preflight", "admit", "prepare"):
        sub.add_parser(cmd).add_argument("suite")
    sub.add_parser("run")
    sub.add_parser("verify")
    sub.add_parser("_worker", help=argparse.SUPPRESS).add_argument("folder", type=Path)
    args = parser.parse_args()
    if args.command == "_worker":
        m = load(args.folder)
        own = owner()
        expected = own / "formal" if m["mode"] == "LIVE" else suite_path(own, args.folder.parent.name) / m["variant"]
        require(_plain(args.folder) == expected and files.read(expected / "claim.json") == ledger.grant(m),
                "WORKER_OWNER_OR_CLAIM")
        sdk.environment()
        trial.worker(args.folder, m)
        return
    own = owner()
    folder = own / "formal"
    if args.command == "preflight":
        offline_suite(own, args.suite)
    elif args.command == "admit":
        proof = admission(own, args.suite, sealed=False)
        files.write(suite_path(own, args.suite) / "admission.json", proof)
        print(canonical(proof).decode())
    elif args.command == "prepare":
        proof = admission(own, args.suite, sealed=True)
        commit = clean_head()
        require(proof["source_commit"] == commit, "PREFLIGHT_SOURCE")
        m = prepare(folder, "LIVE", "formal", commit, proof)
        print(canonical(ledger.grant(m)).decode())
    elif args.command == "run":
        print(canonical(execute(folder, load(folder), own / "protocol-sources")).decode())
    elif (folder / "result.json").is_file():
        print(canonical(review(folder, sealed=True)).decode())
    else:
        print(canonical(ledger.interrupted(folder, load(folder))).decode())
        raise SystemExit(3)


if __name__ == "__main__":
    main()

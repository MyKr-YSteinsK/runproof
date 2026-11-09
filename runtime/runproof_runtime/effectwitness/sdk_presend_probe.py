"""Preflight, bounded real SDK orchestration and read-only inspection."""
import argparse
from importlib import metadata
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
import sysconfig
import threading
import time

from .sdk_presend_contracts import (BUDGET, CASES, LIMIT, PINS, REPO, Denied, bounded, canonical,
                                   check, exclusive, identity, owner_path, safe, sha, strict)
from .sdk_presend_diagnostic import (CONTEXT, REPORT, MAX_BYTES, READ_ERRORS, child_report, collect,
                                     context, inspect_diagnostic)
from .sdk_presend_host import Journal, Session, http_server, read_exact
from .sdk_presend_oracle import inspect_case


def executable_hash():
    return sha(Path(sys.executable).read_bytes())


def preflight(owner):
    site = Path(sysconfig.get_path("purelib")).resolve()
    versions = {}
    for name in PINS:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    admitted = (versions == PINS and sys.prefix != sys.base_prefix
                and site.is_relative_to(owner / "venv")
                and Path(os.path.abspath(sys.executable)).is_relative_to(owner / "venv"))
    return {"status": "SDK_ADMITTED" if admitted else "SDK_UNAVAILABLE",
            "versions": versions, "python_version": sys.version.split()[0], "exe_sha256": executable_hash(),
            "source": identity(), "formal_occupied": safe(owner / "formal.json").exists()}


def launch(folder, module, call, args, *, stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL):
    # Never inherit proxy, credential, cloud, or shell variables.
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    env.update(HOME=str(folder), TEMP=str(folder), TMP=str(folder), TMPDIR=str(folder),
               OTEL_SDK_DISABLED="true", LOGFIRE_SEND_TO_LOGFIRE="false")
    program = (f"import sys; sys.path.insert(0, sys.argv.pop(1)); from {module} import {call}; "
               f"raise SystemExit({call}(*sys.argv[1:]))")
    return subprocess.Popen([sys.executable, "-I", "-S", "-B", "-c", program, str(REPO), *args],
                            cwd=folder, env=env, stdout=stdout, stdin=stdin, stderr=subprocess.DEVNULL)


def receiver_main(owner, case, nonce):
    check(case in CASES and len(nonce) == 64, "RECEIVER_INPUT")
    folder = safe(owner_path(owner) / case)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(15)
        ready = {"owner": owner, "case": case, "host": "127.0.0.1", "port": listener.getsockname()[1],
                 "pid": os.getpid(), "exe_sha256": executable_hash(), "nonce": nonce,
                 "ready_ns": time.monotonic_ns()}
        exclusive(folder / "receiver-ready.json", canonical(ready))
        for index in range(1, BUDGET[case] + 1):
            connection, peer = listener.accept()
            with connection:
                check(peer[0] == "127.0.0.1", "RECEIVER_PEER")
                connection.settimeout(5)
                connection.sendall(nonce.encode("ascii"))
                size = struct.unpack("!I", read_exact(connection, 4))[0]
                check(0 < size <= LIMIT, "RECEIVER_SIZE")
                raw = read_exact(connection, size)
                exclusive(folder / f"receiver-{index}.raw", raw)
                exclusive(folder / f"receiver-{index}.json", canonical({
                    "index": index, "owner": owner, "case": case, "pid": os.getpid(),
                    "nonce": nonce, "bytes": size, "sha256": sha(raw), "received_ns": time.monotonic_ns(),
                }))
                connection.sendall(sha(raw).encode("ascii"))


def finish(process, timeout):
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()  # The exact child process handle belongs to this invocation.
        return process.wait(timeout=5)


def run_case(owner, case, facts):
    folder = safe(owner / case)
    nonce = secrets.token_hex(32)
    receiver_start = time.monotonic_ns()
    receiver = launch(folder, __name__ if __name__ != "__main__" else
                      "runtime.runproof_runtime.effectwitness.sdk_presend_probe",
                      "receiver_main", [owner.name, case, nonce])
    try:
        exclusive(folder / "receiver-launch.json", canonical({"pid": receiver.pid, "nonce": nonce,
                  "exe_sha256": executable_hash(), "start_ns": receiver_start}))
        deadline = time.monotonic() + 5
        ready = None
        while time.monotonic() < deadline and receiver.poll() is None:
            try:
                ready = strict(bounded(folder / "receiver-ready.json", 4096))
                break
            except (FileNotFoundError, ValueError):
                time.sleep(.02)
        check(ready is not None, "RECEIVER_ABSENT")
        check(type(ready) is dict and ready.get("pid") == receiver.pid and ready.get("nonce") == nonce
              and ready.get("exe_sha256") == executable_hash(), "RECEIVER_RECEIPT_MISMATCH")
        with Journal(folder, case).open(create=True) as journal:
            session = Session(journal, ready)
            token = "rpf102-dummy-" + secrets.token_hex(32)
            with http_server(session, token) as server:
                host = {"pid": os.getpid(), "port": server.server_port, "host": "127.0.0.1",
                        "exe_sha256": executable_hash()}
                journal.append("HOST_LISTEN", host)
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                sdk = None
                try:
                    facts.update(phase="SDK", attempted=True)
                    sdk_start = time.monotonic_ns()
                    sdk = launch(folder, "runtime.runproof_runtime.effectwitness.sdk_presend_client",
                                 "main", [], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
                    exclusive(folder / "sdk-launch.json", canonical({"pid": sdk.pid, "start_ns": sdk_start,
                              "exe_sha256": executable_hash(), "host": host, "network": "HOST_LOOPBACK_ONLY"}))
                    config = canonical({"port": host["port"], "token": token, "case": case,
                                        "site": str(Path(sysconfig.get_path("purelib")).resolve()), "folder": str(folder)})
                    try:
                        raw, _ = sdk.communicate(config, timeout=45)
                    except subprocess.TimeoutExpired:
                        facts["timed_out"] = True
                        sdk.kill()
                        raw, _ = sdk.communicate(timeout=5)
                    exclusive(folder / "sdk-exit.json", canonical({"pid": sdk.pid, "exit": sdk.returncode,
                              "exit_ns": time.monotonic_ns(), "stdout_sha256": sha(raw)}))
                    if len(raw) <= MAX_BYTES:
                        exclusive(folder / "sdk-output.json", raw)
                finally:
                    if sdk is not None and sdk.poll() is None:
                        sdk.kill()
                        sdk.wait(timeout=5)
                    server.shutdown()
                    thread.join(timeout=6)
                    facts["host_code"] = session.failure
                    check(not thread.is_alive(), "HOST_THREAD_ACTIVE")
                check(not facts.get("timed_out") and sdk.returncode == 0 and session.failure is None
                      and session.posts == 2, "CASE_INCOMPLETE")
                check(child_report(raw, case)[2] == 1, "SDK_OUTPUT_INVALID")
                journal.append("SDK_TERMINAL", {"sha256": sha(raw), "exit": sdk.returncode})
    finally:
        code = finish(receiver, 8)
        exclusive(folder / "receiver-exit.json", canonical({"pid": receiver.pid, "exit": code,
                  "exit_ns": time.monotonic_ns(), "exe_sha256": executable_hash()}))
    check(code == 0, "RECEIVER_ABSENT")


def run(owner):
    admitted = preflight(owner)
    check(admitted["status"] == "SDK_ADMITTED" and not admitted["formal_occupied"], "SDK_ADMISSION")
    exclusive(owner / "formal.json", canonical({"cases": CASES, "max_sends": 3, "max_bytes": 3 * LIMIT}))
    results = []
    for case in CASES:
        folder = safe(owner / case)
        folder.mkdir(exist_ok=False)
        exclusive(folder / CONTEXT, canonical(context(folder, case)))
        facts = {"phase": "RECEIVER", "attempted": False}
        try:
            run_case(owner, case, facts)
            facts["phase"] = "ORACLE"
            results.append(inspect_case(owner.name, case))
        except READ_ERRORS as exc:
            if facts["phase"] == "ORACLE":
                facts["outcome"] = "ORACLE_REJECTED"
            elif type(exc) is Denied and str(exc) in ("RECEIVER_ABSENT", "RECEIVER_RECEIPT_MISMATCH"):
                facts["outcome"] = str(exc)
            raise
        else:
            facts.update(phase="TERMINAL",
                         outcome="NORMAL_VERIFIED" if case == "NORMAL" else "UNKNOWN_EXPECTED_DENIAL")
        finally:
            report = canonical(collect(folder, case, **facts))
            exclusive(folder / REPORT, report)
            print(report.decode("ascii"), flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--preflight", action="store_true")
    options.add_argument("--run", action="store_true")
    options.add_argument("--inspect", choices=CASES)
    options.add_argument("--diagnostic", choices=CASES)
    args = parser.parse_args()
    try:
        owner = owner_path(args.owner)
        if args.preflight:
            print(json.dumps(preflight(owner), sort_keys=True))
        elif args.run:
            run(owner)
        elif args.diagnostic:
            print(canonical(inspect_diagnostic(safe(owner / args.diagnostic), args.diagnostic)).decode("ascii"))
        else:
            print(json.dumps(inspect_case(owner.name, args.inspect), sort_keys=True))
        return 0
    except READ_ERRORS:
        if args.diagnostic:
            # Stdout stays empty so it cannot be mistaken for an uploadable envelope.
            print("EVIDENCE_UNAVAILABLE", file=sys.stderr)
        else:
            print(json.dumps({"status": "REJECTED", "reason": "RUN_REJECTED" if args.run else "CHECK_FAILED"}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

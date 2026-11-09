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

from .sdk_presend_contracts import (BUDGET, CASES, LIMIT, PINS, ROOT, REPO, bounded, canonical,
                                   check, exclusive, identity, owner_path, safe, sha, strict)
from .sdk_presend_host import Journal, Session, http_server, read_exact


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


def run_case(owner, case):
    folder = safe(owner / case)
    folder.mkdir(exist_ok=False)
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
        check(ready is not None and ready["pid"] == receiver.pid and ready["nonce"] == nonce
              and ready["exe_sha256"] == executable_hash(), "RECEIVER_READY")
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
                        sdk.kill()
                        raw, _ = sdk.communicate(timeout=5)
                    check(len(raw) <= 8192, "SDK_OUTPUT_LIMIT")
                    exclusive(folder / "sdk-output.json", raw)
                    exclusive(folder / "sdk-exit.json", canonical({"pid": sdk.pid, "exit": sdk.returncode,
                              "exit_ns": time.monotonic_ns(), "stdout_sha256": sha(raw)}))
                    if sdk.returncode or session.failure or session.posts != 2:
                        try:
                            report = strict(raw)
                        except (ValueError, RecursionError):
                            report = None
                        if type(report) is not dict:
                            report = {}
                        kinds = [row["kind"] for row in journal.rows()]
                        print(json.dumps({"case": case, "status": "SDK_FAILED",
                                          "sdk_exit": sdk.returncode,
                                          "host_reason": session.failure, "sdk_error": report.get("error_type"),
                                          "stage": report.get("stage"), "accepted_posts": session.posts,
                                          "provider_tickets": kinds.count("PROVIDER_RESERVE"),
                                          "send_entries": kinds.count("SEND_ENTRY")}), flush=True)
                        check(False, "SDK_EXECUTION_FAILED")
                    journal.append("SDK_TERMINAL", {"sha256": sha(raw), "exit": sdk.returncode})
                finally:
                    if sdk is not None and sdk.poll() is None:
                        sdk.kill()
                        sdk.wait(timeout=5)
                    server.shutdown()
                    thread.join(timeout=6)
                    check(not thread.is_alive(), "HOST_THREAD_ACTIVE")
    finally:
        code = finish(receiver, 8)
        exclusive(folder / "receiver-exit.json", canonical({"pid": receiver.pid, "exit": code,
                  "exit_ns": time.monotonic_ns(), "exe_sha256": executable_hash()}))
    check(code == 0, "RECEIVER_EXIT")


def run(owner):
    admitted = preflight(owner)
    check(admitted["status"] == "SDK_ADMITTED" and not admitted["formal_occupied"], "SDK_ADMISSION")
    exclusive(owner / "formal.json", canonical({"cases": CASES, "max_sends": 3, "max_bytes": 3 * LIMIT}))
    from .sdk_presend_oracle import inspect_case
    results = []
    for case in CASES:
        run_case(owner, case)
        results.append(inspect_case(owner.name, case))
        print(json.dumps(results[-1], sort_keys=True), flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--preflight", action="store_true")
    options.add_argument("--run", action="store_true")
    options.add_argument("--inspect", choices=CASES)
    args = parser.parse_args()
    try:
        owner = owner_path(args.owner)
        if args.preflight:
            print(json.dumps(preflight(owner), sort_keys=True))
        elif args.run:
            run(owner)
        else:
            from .sdk_presend_oracle import inspect_case
            print(json.dumps(inspect_case(owner.name, args.inspect), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc) if type(exc).__name__ == "Denied" else type(exc).__name__}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

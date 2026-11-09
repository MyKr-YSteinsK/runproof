"""Manual-only RPF-104 hosted orchestration, receiver, and isolated child launch."""
import argparse
from importlib import metadata
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
from urllib.parse import urlsplit

from .product_sdk_contracts import FORWARDS, POSTS, freeze, hex_id, sources, validate_frozen
from .product_sdk_host import Session, new_journal
from .product_sdk_target import Target, case_scope, create, read, safe
from .sdk_presend_contracts import LIMIT, PINS, REPO, canonical, check, sha, strict, sync_dir
from .sdk_presend_host import http_server, read_exact
from .sdk_presend_probe import executable_hash, launch

ROOT = REPO / ".local" / "rpf-104"
PREFIX = "runtime.runproof_runtime.effectwitness.product_sdk_"


def hosted(source, run):
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_REPOSITORY": "MyKr-YSteinsK/runproof", "GITHUB_REF": "refs/heads/main",
                "GITHUB_SHA": source, "GITHUB_RUN_ID": run, "GITHUB_RUN_ATTEMPT": "1",
                "RPF104_APPROVED_SOURCE_SHA": source, "RPF104_APPROVED_RUN_ID": run}
    check(all(os.environ.get(key) == value for key, value in expected.items()), "HOSTED_ADMISSION")


def owner_scope(owner):
    check(hex_id(owner, 32), "OWNER_ID")
    return ROOT / owner


def admission(source, run, owner):
    scope = freeze(source, run, owner, "NORMAL")
    return {"schema": "rpf104-admission-v1", "source_git_sha": scope["source_git_sha"],
            "run_id": run, "owner": owner, "attempt": 1, "sources": sources(),
            "cases": ["NORMAL", "UNKNOWN"], "max_business_writes": 3, "max_forwards": 4,
            "max_forward_bytes": 4 * LIMIT}


def admit(source, run, owner):
    hosted(source, run)
    safe(ROOT, directory=True)
    folder = safe(owner_scope(owner), directory=True, absent=True)
    folder.mkdir()
    sync_dir(folder.parent)
    create(folder / "admission.json", canonical(admission(source, run, owner)))
    return folder


def environment(owner):
    site = safe(Path(sysconfig.get_path("purelib")), directory=True)
    check(sys.version_info[:2] == (3, 12) and sys.prefix != sys.base_prefix
          and site.is_relative_to(owner / "venv") and Path(os.path.abspath(sys.executable)).is_relative_to(owner / "venv")
          and {name: metadata.version(name) for name in PINS} == PINS, "SDK_ENVIRONMENT")
    installed = strict(read(owner / "install.json", 1048576))
    wheels = {}
    for item in installed["install"]:
        name = item["metadata"]["name"].lower().replace("_", "-")
        url = urlsplit(item["download_info"]["url"])
        digest = item["download_info"]["archive_info"]["hashes"]["sha256"]
        check(url.scheme == "https" and url.netloc == "files.pythonhosted.org"
              and url.path.endswith(".whl") and hex_id(digest, 64), "WHEEL_PROVENANCE")
        if name in PINS:
            check(name not in wheels and item["metadata"]["version"] == PINS[name], "WHEEL_PIN")
            wheels[name] = digest
    check(set(wheels) == set(PINS), "WHEEL_SET")
    return site, {"python": sys.version.split()[0], "exe_sha256": executable_hash(), "pins": PINS, "wheels": wheels}


def receive(nonce):
    check(hex_id(nonce, 64), "RECEIVER_NONCE")
    folder = Path.cwd()
    frozen = validate_frozen(strict(read(folder / "contract.json", 16384)))
    case_scope(folder, frozen)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(20)
        ready = {"scope_sha256": sha(canonical(frozen)), "host": "127.0.0.1",
                 "port": server.getsockname()[1], "pid": os.getpid(), "exe_sha256": executable_hash(),
                 "nonce": nonce, "ready_ns": time.monotonic_ns()}
        create(folder / "receiver-ready.json", canonical(ready))
        for number in range(1, FORWARDS[frozen["case"]] + 1):
            conn, peer = server.accept()
            with conn:
                check(peer[0] == "127.0.0.1", "RECEIVER_PEER")
                conn.settimeout(5)
                conn.sendall(nonce.encode("ascii"))
                size = struct.unpack("!I", read_exact(conn, 4))[0]
                check(0 < size <= LIMIT, "RECEIVER_PAYLOAD")
                raw = read_exact(conn, size)
                create(folder / f"receiver-{number}.raw", raw)
                create(folder / f"receiver-{number}.json", canonical({
                    "scope_sha256": ready["scope_sha256"], "number": number, "pid": ready["pid"],
                    "nonce": nonce, "bytes": len(raw), "sha256": sha(raw), "received_ns": time.monotonic_ns()}))
                conn.sendall(sha(raw).encode("ascii"))
    return 0


def send(folder, ready, ticket, raw, entry):
    check(strict(read(folder / "receiver-ready.json", 4096)) == ready and ready["host"] == "127.0.0.1"
          and ticket["case_sha256"] == ready["scope_sha256"] and 0 < ready["port"] < 65536, "RECEIVER_BINDING")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(("127.0.0.1", ready["port"]))
        check(secrets.compare_digest(read_exact(sock, 64), ready["nonce"].encode("ascii")), "RECEIVER_NONCE")
        started = entry()["time_ns"]
        sock.sendall(struct.pack("!I", len(raw)) + raw)
        finished = time.monotonic_ns()
        check(read_exact(sock, 64) == sha(raw).encode("ascii"), "RECEIVER_ACK")
    create(folder / f"sender-{ticket['request']['number']}.json", canonical({
        "pid": os.getpid(), "ticket": ticket, "nonce": ready["nonce"], "entry_ns": started,
        "return_ns": finished, "sha256": sha(raw), "bytes": len(raw)}))


def communicate(child, raw=None, *, timeout):
    try:
        output, _ = child.communicate(raw, timeout=timeout)
        return output
    except subprocess.TimeoutExpired:
        child.kill()
        child.communicate(timeout=5)
        raise


def finish(child, seconds):
    try:
        return child.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        child.kill()
        return child.wait(timeout=5)


def authority(folder, domain):
    child = launch(folder, PREFIX + "target", "authority_main", [domain], stdout=subprocess.PIPE)
    output = communicate(child, timeout=8)
    check(child.returncode == 0 and 0 < len(output) <= 8192, "AUTHORITY_PROCESS")
    row = strict(output)
    check(row["pid"] == child.pid and child.pid != os.getpid(), "AUTHORITY_PID")
    return row


def run_case(owner, frozen, site, env):
    folder = safe(owner / frozen["case"], directory=True, absent=True)
    folder.mkdir()
    sync_dir(owner)
    create(folder / "contract.json", canonical(frozen))
    sdk_folder = safe(folder / "sdk", directory=True, absent=True)
    sdk_folder.mkdir()
    nonce = secrets.token_hex(32)
    started = time.monotonic_ns()
    receiver = launch(folder, PREFIX + "probe", "receive", [nonce])
    try:
        create(folder / "receiver-launch.json", canonical({
            "pid": receiver.pid, "nonce": nonce, "exe_sha256": env["exe_sha256"], "start_ns": started}))
        ready = None
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and receiver.poll() is None:
            try:
                ready = strict(read(folder / "receiver-ready.json", 4096))
                break
            except FileNotFoundError:
                time.sleep(.02)
        check(ready is not None and ready["pid"] == receiver.pid and ready["nonce"] == nonce
              and ready["exe_sha256"] == env["exe_sha256"], "RECEIVER_START")
        with new_journal(folder / "wal.jsonl") as journal:
            session = Session(frozen, journal, Target(folder, frozen),
                              lambda domain: authority(folder, domain),
                              lambda ticket, raw, entry: send(folder, ready, ticket, raw, entry),
                              lambda name, raw: create(folder / name, raw))
            token = secrets.token_hex(32)
            with http_server(session, token) as server:
                host = {"pid": os.getpid(), "host": "127.0.0.1", "port": server.server_port,
                        "exe_sha256": env["exe_sha256"]}
                journal.append("HOST_LISTEN", host)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                sdk = None
                try:
                    started = time.monotonic_ns()
                    sdk = launch(sdk_folder, PREFIX + "client", "main", [],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE)
                    create(folder / "sdk-launch.json", canonical({
                        "pid": sdk.pid, "start_ns": started, "host": host, "exe_sha256": env["exe_sha256"]}))
                    config = canonical({"port": host["port"], "token": token, "case": frozen["case"], "site": str(site)})
                    raw = communicate(sdk, config, timeout=45)
                    check(0 < len(raw) <= 8192, "SDK_OUTPUT_SIZE")
                    create(folder / "sdk-output.json", raw)
                    done = {"pid": sdk.pid, "exit": sdk.returncode, "exit_ns": time.monotonic_ns(),
                            "stdout_sha256": sha(raw)}
                    create(folder / "sdk-exit.json", canonical(done))
                finally:
                    if sdk is not None and sdk.poll() is None:
                        sdk.kill()
                        finish(sdk, 5)
                    server.shutdown()
                    worker.join(timeout=6)
                check(not worker.is_alive() and sdk.returncode == 0 and not session.failure and not journal.poison
                      and session.posts == POSTS[frozen["case"]], "SDK_CASE_FAILED")
                journal.append("SDK_TERMINAL", done)
    finally:
        code = finish(receiver, 6)
        create(folder / "receiver-exit.json", canonical({"pid": receiver.pid, "exit": code,
               "exit_ns": time.monotonic_ns(), "exe_sha256": env["exe_sha256"]}))
    check(code == 0, "RECEIVER_CASE_FAILED")
    verifier = launch(folder, PREFIX + "oracle", "physical_main", [], stdout=subprocess.PIPE)
    report = communicate(verifier, timeout=15)
    check(verifier.returncode == 0 and 0 < len(report) <= 131072, "CASE_ORACLE")
    create(folder / "oracle-public.json", canonical(strict(report)))


def physical(source, run, owner_id):
    hosted(source, run)
    owner = safe(owner_scope(owner_id), directory=True)
    check(read(owner / "admission.json", 16384) == canonical(admission(source, run, owner_id)), "ADMISSION_BINDING")
    create(owner / "physical-claimed.json", canonical({"owner": owner_id, "run_id": run}))
    site, env = environment(owner)
    create(owner / "environment.json", canonical(env))
    for case in ("NORMAL", "UNKNOWN"):
        run_case(owner, freeze(source, run, owner_id, case), site, env)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("admit", "physical"))
    parser.add_argument("source")
    parser.add_argument("run")
    parser.add_argument("owner")
    args = parser.parse_args()
    try:
        (admit if args.action == "admit" else physical)(args.source, args.run, args.owner)
    except Exception:
        print("RPF104_PHYSICAL_UNAVAILABLE_OR_FAILED", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

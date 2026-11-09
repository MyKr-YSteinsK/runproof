"""Authenticated loopback receiver and process receipts for the local probe."""
from contextlib import contextmanager
from hashlib import sha256
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

from .provider_barrier import CASES, ROOT, Denied, canonical, digest, exclusive, safe, strict


def clean_environment(folder):
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    env.update(TEMP=str(folder), TMP=str(folder), TMPDIR=str(folder))
    return env


def executable_identity():
    return sha256(Path(sys.executable).read_bytes()).hexdigest()


def read_json(path):
    with safe(path).open("rb") as stream:
        data = stream.read(4097)
    if len(data) > 4096:
        raise Denied("RECEIPT_TOO_LARGE")
    return strict(data)


def receive_exact(connection, length):
    output = bytearray()
    while len(output) < length:
        block = connection.recv(length - len(output))
        if not block:
            raise Denied("RECEIVER_CHALLENGE_TRUNCATED")
        output.extend(block)
    return bytes(output)


@contextmanager
def connected_receiver(case, expected):
    folder = safe(ROOT / "receivers" / case)
    ready = read_json(folder / "ready.json")
    launch = read_json(folder / "launch.json")
    if (expected != ready or ready["case"] != case or ready["host"] != "127.0.0.1"
            or type(ready["port"]) is not int or not 1 <= ready["port"] <= 65535
            or launch["pid"] != ready["pid"] or launch["exe_sha256"] != ready["exe_sha256"]
            or launch["nonce"] != ready["nonce"] or launch["start_ns"] > ready["ready_ns"]
            or len(ready["nonce"]) != 64 or safe(folder / "exit.json").exists()):
        raise Denied("RECEIVER_IDENTITY")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(3)
        connection.connect(("127.0.0.1", ready["port"]))
        if not secrets.compare_digest(receive_exact(connection, 64), ready["nonce"].encode("ascii")):
            raise Denied("RECEIVER_CHALLENGE")
        yield connection


def receiver_main(case, nonce):
    if case not in CASES or len(nonce) != 64:
        raise Denied("RECEIVER_SCOPE")
    folder = safe(ROOT / "receivers" / case)
    if not folder.is_dir():
        raise Denied("RECEIVER_OWNER")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(7)
        ready = {"case": case, "host": "127.0.0.1", "port": listener.getsockname()[1],
                 "pid": os.getpid(), "exe_sha256": executable_identity(), "nonce": nonce,
                 "ready_ns": time.monotonic_ns()}
        exclusive(folder / "ready.json", canonical(ready))
        count = 0
        payload = bytearray()
        try:
            connection, peer = listener.accept()
        except TimeoutError:
            connection = None
        if connection is not None:
            count = 1
            with connection:
                if peer[0] != "127.0.0.1":
                    raise Denied("NON_LOOPBACK_PEER")
                connection.settimeout(3)
                # Fixed authentication challenge, not an application request.
                connection.sendall(nonce.encode("ascii"))
                while True:
                    block = connection.recv(4097 - len(payload))
                    if not block:
                        break
                    payload.extend(block)
                    if len(payload) > 4096:
                        raise Denied("RECEIVE_LIMIT")
        exclusive(folder / "received.raw", payload)
        receipt = {"ready": ready, "connections": count, "bytes": len(payload),
                   "sha256": digest(payload), "observed_ns": time.monotonic_ns(),
                   "status": "ACTUAL_SOCKET_RECEIVED" if payload else "NO_BYTES_OBSERVED"}
        exclusive(folder / "receiver-receipt.json", canonical(receipt))


def launch_isolated(folder, source, arguments):
    # -I bypasses user site, PYTHONPATH and Python environment configuration.
    repo = str(Path(__file__).resolve().parents[3])
    return subprocess.Popen([sys.executable, "-I", "-B", "-c",
                             "import sys; sys.path.insert(0, sys.argv.pop(1)); " + source,
                             repo, *arguments], cwd=folder, env=clean_environment(folder),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@contextmanager
def receiver(case):
    if case not in CASES:
        raise Denied("CASE_SCOPE")
    folder = safe(ROOT / "receivers" / case)
    folder.mkdir(parents=True, exist_ok=False)
    nonce = secrets.token_hex(32)
    start = time.monotonic_ns()
    process = launch_isolated(folder,
        "from runtime.runproof_runtime.effectwitness.provider_transport import receiver_main; receiver_main(*sys.argv[1:])",
        [case, nonce])
    launch = {"pid": process.pid, "exe_sha256": executable_identity(), "nonce": nonce, "start_ns": start}
    try:
        exclusive(folder / "launch.json", canonical(launch))
        deadline = time.monotonic() + 5
        ready = None
        while time.monotonic() < deadline and process.poll() is None:
            try:
                ready = read_json(folder / "ready.json")
                break
            except (FileNotFoundError, ValueError):
                time.sleep(.02)
        if ready is None or ready["pid"] != process.pid or ready["nonce"] != nonce or ready["exe_sha256"] != launch["exe_sha256"]:
            raise Denied("RECEIVER_START_FAILED")
        yield ready
    finally:
        try:
            code = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()  # Exact Popen handle, never a PID lookup.
            code = process.wait(timeout=5)
        exclusive(folder / "exit.json", canonical({"pid": process.pid, "exe_sha256": launch["exe_sha256"],
                                                   "exit": code, "exit_ns": time.monotonic_ns()}))
        if code:
            raise Denied("RECEIVER_EXIT")

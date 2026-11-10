"""Explicitly admitted, single-use orchestration of the two physical cases."""
import argparse
import os
from pathlib import Path
import subprocess
import threading
import time
from uuid import uuid4

from . import pge_r106_contracts as inner, pge_r106_oracle as inner_oracle
from . import pge_r107_contracts as c
from .pge_r106_controller import Controller
from .pge_r106_replay import prepare_root
from .pge_r107_host import Host, Journal
from .product_sdk_probe import environment
from .product_sdk_target import create, read, safe
from .sdk_presend_contracts import REPO, canonical, check, sha, sync_dir
from .sdk_presend_host import http_server
from .sdk_presend_probe import launch

ROOT = REPO / ".local" / "rpf-107"
MODULE = "runtime.runproof_runtime.effectwitness.pge_r107_"


def admit_identity(source, run, hosted):
    check(inner.hex_id(source, 40), "SOURCE")
    if hosted:
        expected = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
                    "GITHUB_REPOSITORY": "MyKr-YSteinsK/runproof", "GITHUB_REF": "refs/heads/main",
                    "GITHUB_SHA": source, "GITHUB_RUN_ID": run, "GITHUB_RUN_ATTEMPT": "1",
                    "RPF107_APPROVED_SOURCE_SHA": source, "RPF107_APPROVED_RUN_ID": run}
        check(type(run) is str and 1 <= len(run) <= 20 and run.isascii() and run.isdecimal()
              and all(os.environ.get(key) == value for key, value in expected.items()), "HOSTED_ADMISSION")
    else:
        check(inner.hex_id(run, 32) and os.environ.get("GITHUB_ACTIONS") != "true", "LOCAL_ADMISSION")
    paths = ["runtime/runproof_runtime/effectwitness/" + name + ".py" for name in c.sources()]
    check(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, timeout=10).decode().strip() == source,
          "SOURCE_HEAD")
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *paths], cwd=REPO, timeout=10, check=True)
    check(subprocess.check_output(["git", "ls-tree", "-r", "--name-only", source, "--", *paths],
                                  cwd=REPO, timeout=10).decode().splitlines() == sorted(paths), "SOURCE_TREE")
    subprocess.run(["git", "check-ignore", "-q", "--", ".local/rpf-106/probe"], cwd=REPO, timeout=10, check=True)
    subprocess.run(["git", "check-ignore", "-q", "--", ".local/rpf-107/probe"], cwd=REPO, timeout=10, check=True)


def prepare():
    prepare_root()
    try:
        safe(ROOT, directory=True)
    except FileNotFoundError:
        safe(ROOT, directory=True, absent=True).mkdir()
        sync_dir(ROOT.parent)


def owner_path(owner):
    check(inner.hex_id(owner, 32), "OUTER_OWNER")
    return ROOT / owner


def admission(source, run, owner, hosted):
    return {"schema": "rpf107-admission-v1", "source_git_sha": source, "run_id": run, "owner": owner,
            "origin": "GITHUB" if hosted else "LOCAL", "source_identity": c.sources(), "policies": list(c.POLICIES),
            "sdk_children_per_case": 1, "servers_per_case": 1, "business_commits_per_case": 2,
            "max_application_bytes": c.MAX_HTTP, "sdk_deadline_seconds": c.CHILD_SECONDS}


def admit(source, run, owner, hosted):
    admit_identity(source, run, hosted)
    prepare()
    path = safe(owner_path(owner), directory=True, absent=True)
    path.mkdir()
    sync_dir(path.parent)
    create(path / "admission.json", canonical(admission(source, run, owner, hosted)))


def sdk_process(folder, port, site, feedback, token, exe_sha):
    started = time.monotonic_ns()
    child = launch(folder, MODULE + "sdk_client", "main", [], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    ended = None
    try:
        create(folder / "sdk-launch.json", canonical({"pid": child.pid, "parent_pid": os.getpid(),
               "started_ns": started, "exe_sha256": exe_sha, "transport": "HTTP_LOOPBACK"}))
        config = canonical({"port": port, "site": str(site), "feedback": feedback, "token": token})
        raw, _ = child.communicate(config, timeout=c.CHILD_SECONDS)
        check(0 < len(raw) <= c.MAX_STDOUT, "SDK_STDOUT_SIZE")
        create(folder / "sdk-stdout.json", raw)
        ended = {"pid": child.pid, "exit": child.returncode, "ended_ns": time.monotonic_ns(),
                 "stdout_sha256": sha(raw), "stdout_size": len(raw), "termination": "EXITED"}
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
        if ended is None:
            ended = {"pid": child.pid, "exit": child.returncode, "ended_ns": time.monotonic_ns(),
                     "termination": "INCOMPLETE"}
        create(folder / "sdk-exit.json", canonical(ended))
    check(ended["exit"] == 0, "SDK_EXIT")
    return ended


def run_case(source, run, outer_owner, folder, policy, site, package, hosted):
    folder.mkdir()
    sync_dir(folder.parent)
    with Controller(source, owner_id=c.inner_owner(source, run, outer_owner, policy)) as controller:
        offered = controller.proposal(inner.SEED)
        seed = controller.apply(offered, controller.evaluate(offered))
        check(seed["execution"] == "VERIFIED", "SEED_UNCERTAIN")
        report = inner_oracle.inspect(controller.owner_id)
        feedback = c.project(controller.frozen, controller.ledger.snapshot(), report["verified"][inner.SEED])
        frozen = c.freeze(source, run, outer_owner, policy, controller.frozen, feedback, package, hosted=hosted)
        create(folder / "frozen.json", canonical(frozen))
        journal = Journal(folder / "bridge.jsonl")
        try:
            host = Host(controller, frozen, journal)
            token = uuid4().hex + uuid4().hex
            with http_server(host, token) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    exited = sdk_process(folder, server.server_port, site, feedback, token, package["exe_sha256"])
                finally:
                    server.shutdown()
                    worker.join(timeout=6)
                    create(folder / "server-exit.json", canonical({"stopped": not worker.is_alive(),
                           "ended_ns": time.monotonic_ns()}))
                check(not worker.is_alive() and host.failure is None and not journal.poison, "HOST_TERMINAL")
                journal.append("SDK_EXIT", exited)
        finally:
            journal.close()


def physical(source, run, owner, hosted):
    admit_identity(source, run, hosted)
    folder = safe(owner_path(owner), directory=True)
    check(read(folder / "admission.json", c.MAX_HTTP) == canonical(admission(source, run, owner, hosted)),
          "ADMISSION_DRIFT")
    create(folder / "physical-claim.json", canonical({"owner": owner, "run_id": run, "source_git_sha": source}))
    site, package = environment(folder)
    for policy in c.POLICIES:
        run_case(source, run, owner, folder / policy, policy, site, package, hosted)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("admit", "physical"))
    parser.add_argument("source")
    parser.add_argument("run")
    parser.add_argument("owner")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    try:
        (admit if args.command == "admit" else physical)(args.source, args.run, args.owner, not args.local)
    except (*inner_oracle.READ_FAILURES, subprocess.SubprocessError):
        print('{"status":"INCONCLUSIVE","stage":"RPF107_SESSION"}', flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

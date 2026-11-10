"""Protected hosted admission plus live, local stub and fixed baseline sessions."""
import argparse
from datetime import datetime, timezone
import http.client
import os
import re
import socket
import ssl
import subprocess

from . import pge_r106_contracts as inner
from . import pge_r110_live_contracts as c, pge_r110_live_provider as provider, pge_r110_live_transport as transport
from .pge_r106_oracle import READ_FAILURES
from .pge_r110_live_presend import Presend
from .pge_r110_oracle import ROOT, fresh
from .pge_r110_session import Controller
from .product_sdk_target import create, read, safe
from .sdk_presend_contracts import Denied, REPO, canonical, check, sha, strict

FAILURES = (*READ_FAILURES, http.client.HTTPException)
CREDENTIAL_NAME = "RPF110_DEEPSEEK_API_KEY"


class Session:
    def __init__(self, source, kind, *, owner=None, approval=None, hook=None):
        check((kind == c.NATIVE) == (owner is not None and approval is not None), "SESSION_ADMISSION")
        if approval is not None:
            c.validate_approval(approval, source)
        self.owner = owner if kind == c.NATIVE else fresh()
        self.host = Controller(self.owner, source)
        try:
            seed = self.host.apply(inner.SEED)
            self.contract = c.freeze(self.host.frozen, self.host.ledger.snapshot(), seed, kind, approval)
            self.edge = Presend(self.owner, self.contract, hook=hook)
        except BaseException:
            self.host.ledger.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.edge.close()
        self.host.ledger.close()

    def reserve(self, raw):
        with self.edge.lock, self.host.ledger.lock:
            self.host.ledger.confirm()
            return self.edge.reserve(raw, self.host.ledger.snapshot())

    def run(self, *, credential=None, port=None):
        mode = self.contract["kind"]
        check((credential is not None) == (mode == c.NATIVE) and (port is not None) == (mode == c.STUB),
              "TRANSPORT_MODE")
        raw = c.request(self.contract)
        with self.edge.lock, self.host.ledger.lock:
            try:
                self.host.ledger.confirm()
                view = self.host.ledger.snapshot()
                if mode == c.B0:
                    self.edge.baseline()
                    choice = inner.ORDER
                else:
                    permit = self.edge.reserve(raw, view)
                    check(permit is not None, "RESERVATION")
                    sender, argument = (transport.native, credential) if mode == c.NATIVE else (transport.loopback, port)
                    response, receipt = sender(self.edge, permit, raw, self.host.ledger.snapshot(), argument)
                    check(credential is None or (credential.encode() not in response
                          and credential not in receipt["header_request_id"]), "PRIVATE_RESPONSE")
                    create(self.owner / "response-private.bin", response)
                    entry = self.edge.journal.events[-1]["body"]
                    provider.receipt_facts(receipt, self.contract, entry)
                    self.edge.observe(receipt)
                    selected = provider.parse(response, receipt, self.contract)
                    check(credential is None or credential not in canonical(selected).decode(), "PRIVATE_PROJECTION")
                    self.edge.select(selected)
                    choice = selected["arguments"]["candidate_id"]
                    self.host.ledger.confirm()
                    check(inner.digest(self.host.ledger.snapshot()) == self.contract["seed_view_sha256"],
                          "CONTROLLER_FEEDBACK_CHANGED")
                self.host.apply(choice)
                self.edge.finish(choice, self.host.ledger.snapshot())
                self.host.ledger.confirm()
                check(self.edge.reserve(raw, self.host.ledger.snapshot(), terminal_probe=True) is None,
                      "TERMINAL_DENIAL")
                return choice
            except FAILURES:
                self.edge.uncertain("SESSION")
                raise


def _github_scope():
    env = os.environ
    source = env.get("GITHUB_SHA")
    run = env.get("GITHUB_RUN_ID")
    check(env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REPOSITORY") == "MyKr-YSteinsK/runproof"
          and env.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and env.get("GITHUB_REF") == "refs/heads/main"
          and env.get("GITHUB_RUN_ATTEMPT") == "1" and inner.hex_id(source, 40)
          and source == env.get("EXPECTED_SOURCE") == env.get("APPROVED_SOURCE")
          and type(run) is str and run == env.get("APPROVED_RUN"), "GITHUB_SCOPE")
    return source, run


def preflight():
    source, run = _github_scope()
    values = os.environ.get("RPF110_APPROVED_BUDGET_JSON", "").encode()
    check(0 < len(values) <= 4096, "BUDGET_INPUT")
    budget = strict(values)
    c.validate_budget(budget, source, run, now=datetime.now(timezone.utc))
    approval = c.validate_approval({"github_run_id": run, "attempt": 1, "reviewer": os.environ.get("LIVE_REVIEWER"),
                                   "dispatcher": os.environ.get("GITHUB_ACTOR"), "budget": budget,
                                   "budget_sha256": os.environ.get("RPF110_APPROVED_BUDGET_SHA256")}, source)
    check(sha(values) == approval["budget_sha256"] and canonical(budget) == values, "APPROVED_BUDGET_BYTES")
    paths = ["runtime/runproof_runtime/effectwitness/" + name + ".py" for name in c.sources()]
    check(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, timeout=10).decode().strip() == source,
          "SOURCE_HEAD")
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *paths], cwd=REPO, timeout=10, check=True)
    tracked = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", source, "--", *paths],
                                      cwd=REPO, timeout=10).decode().splitlines()
    check(sorted(tracked) == sorted(paths), "SOURCE_TREE")
    subprocess.run(["git", "check-ignore", "-q", "--", ".local/rpf-110/probe"],
                   cwd=REPO, timeout=10, check=True)
    owner = fresh()
    create(owner / "approved-live.json", canonical({"owner": owner.name, "source_git_sha": source,
                                                   "sources": c.sources(), "approval": approval}))
    return owner.name


def live(owner_id):
    from .pge_r110_live_witness import build, comparison

    source, run = _github_scope()
    check(inner.hex_id(owner_id, 32), "LIVE_OWNER")
    owner = safe(ROOT / owner_id, directory=True)
    admitted = strict(read(owner / "approved-live.json", 16384))
    approval = c.validate_approval(admitted["approval"], source)
    check(admitted == {"owner": owner_id, "source_git_sha": source, "sources": c.sources(),
                       "approval": approval} and approval["github_run_id"] == run
          and approval["budget_sha256"] == os.environ.get("RPF110_APPROVED_BUDGET_SHA256"), "APPROVAL_DRIFT")
    c.validate_budget(approval["budget"], source, run, now=datetime.now(timezone.utc))
    create(owner / "native-claim.json", canonical({"owner": owner_id, "run": run, "source": source}))
    credential = os.environ.pop(CREDENTIAL_NAME, None)
    try:
        check(credential is not None, "CREDENTIAL_UNAVAILABLE")
        with Session(source, c.NATIVE, owner=owner, approval=approval) as session:
            session.run(credential=credential)
            actual = build(session)
        del credential
        with Session(source, c.B0) as baseline:
            baseline.run()
            fixed = build(baseline)
        create(owner / "comparison.json", comparison(source, actual, fixed))
        create(owner / "status.json", canonical({"status": "COMPLETE", "phase": "B1", "owner": owner_id}))
    except FAILURES as exc:
        label = "LOCAL_OR_PROTOCOL_FAILURE"
        if type(exc) is Denied and re.fullmatch(r"[A-Z_]{3,60}", str(exc)):
            label = str(exc)
        elif isinstance(exc, (ssl.SSLError, socket.gaierror, TimeoutError, http.client.HTTPException)):
            label = type(exc).__name__
        create(owner / "status.json", canonical({"status": "INCONCLUSIVE", "phase": "B1", "owner": owner_id,
                                                 "reason": label}))
        raise


def failure_summary(owner_id):
    from .pge_r108_verify import presend_rows

    source, run = _github_scope()
    check(inner.hex_id(owner_id, 32), "LIVE_OWNER")
    owner = safe(ROOT / owner_id, directory=True)
    summary = {"schema": "rpf110-live-failure-v1", "source": source, "run": run, "owner": owner_id,
               "status": "INCONCLUSIVE", "provider_requests": "UNKNOWN", "wal": "UNAVAILABLE"}
    try:
        raw = read(owner / "presend-live.jsonl", 81920)
        summary["wal"] = {"sha256": sha(raw), "size": len(raw), "sequence": "UNAVAILABLE"}
        rows = presend_rows(raw)
        known = {"OPEN", "HOST_REQUEST_READY", "PROVIDER_RESERVE", "SEND_INTENT", "SEND_ENTRY",
                 "HTTP_RESPONSE", "TOOL_SELECTION", "UNKNOWN", "STOPPED", "LOCAL_TERMINAL_PROBE", "UNCERTAIN",
                 "DENIED"}
        check(all(row["kind"] in known for row in rows), "FAILURE_EVENT_KIND")
        summary["wal"]["sequence"] = [{"kind": row["kind"], "sha256": row["sha256"]} for row in rows]
    except READ_FAILURES:
        pass
    create(owner / "failure-summary.json", canonical(summary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "live", "failure-summary"))
    parser.add_argument("--owner")
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            print(preflight())
        elif args.command == "live":
            live(args.owner)
        else:
            failure_summary(args.owner)
    except (*FAILURES, subprocess.SubprocessError):
        print('{"status":"STOPPED","stage":"RPF110_LIVE"}')
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

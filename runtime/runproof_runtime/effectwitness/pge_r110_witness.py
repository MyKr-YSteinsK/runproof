"""Freeze a new Phase A fixture witness after independent Authority readback."""
from . import pge_r110_verify as verifier
from .pge_r106_ledger import MAX_BYTES
from .pge_r107_host import application
from .pge_r110_oracle import readback
from .product_sdk_target import create, read
from .sdk_presend_contracts import canonical, sha


def build(session):
    host = session.controller
    _, rows = host.ledger.persisted()
    authority = {}
    for event in rows:
        if event["kind"] == "AUTHORITY_BEFORE":
            before = event["body"]
            name = before["binding"]["candidate_id"]
            authority[name] = {"before": before, "after": readback(host.owner, host.frozen["catalog"][name])}
    raw = canonical({"schema": "rpf110-witness-v1", "kind": "PHASE_A_FIXTURE", "issuer": "NOT_ESTABLISHED",
                     "strategy": session.presend.contract["strategy"], "provider": verifier.NO_PROVIDER,
                     "authority": authority, "business_wal": application(read(host.ledger.path, MAX_BYTES)),
                     "presend_wal": application(read(session.presend.journal.path, verifier.MAX_TRACE))})
    result = verifier.verify(raw, host.frozen["scope"]["source_git_sha"], sha(raw))
    create(host.owner / "witness.json", raw)
    create(host.owner / "demo-projection.json", canonical(result["demo_projection"]))
    return raw, result

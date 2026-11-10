"""Create redacted proof from the frozen bytes and an independent Authority read."""
from . import pge_r110_live_contracts as c, pge_r110_live_verify as verify
from .pge_r106_ledger import MAX_BYTES
from .pge_r107_host import application
from .pge_r110_oracle import readback
from .product_sdk_target import create, read
from .sdk_presend_contracts import canonical, sha


def build(session):
    host = session.host
    _, rows = host.ledger.persisted()
    authority = {}
    for event in rows:
        if event["kind"] == "AUTHORITY_BEFORE":
            before = event["body"]
            name = before["binding"]["candidate_id"]
            authority[name] = {"before": before, "after": readback(host.owner, host.frozen["catalog"][name])}
    contract = session.contract
    stub = application(read(host.owner / "response-private.bin", c.RESPONSE_CAP)) if contract["kind"] == c.STUB else None
    raw = canonical({"schema": "rpf110-live-witness-v1", "kind": contract["kind"], "issuer": "NOT_ESTABLISHED",
                     "approval": contract["approval"], "request": application(c.request(contract)),
                     "stub_response": stub, "presend_wal": application(read(session.edge.journal.path,
                                                                             verify.TRACE_LIMIT)),
                     "business_wal": application(read(host.ledger.path, MAX_BYTES)), "authority": authority})
    verified = verify.verify(raw, contract["scope"]["source_git_sha"], sha(raw))
    create(host.owner / "witness-live.json", raw)
    return raw, verified


def comparison(source, explorer, baseline):
    a, b = explorer[1], baseline[1]
    projection = {"schema": "rpf110-demo-v2", "explorer": a, "baseline": b, "causality": "NOT_PROVEN",
                  "comparison": "OBSERVED_SINGLE_TRIAL" if a["kind"] == c.NATIVE else "LOCAL_STUB_CONTROL"}
    raw = canonical({"schema": "rpf110-live-comparison-v1", "source": source, "explorer": application(explorer[0]),
                     "baseline": application(baseline[0]), "projection": projection})
    verify.verify_comparison(raw, source, sha(raw))
    return raw

"""Generate a new local fixture and verify its byte-contained witness."""
import argparse
from pathlib import Path
from uuid import uuid4

from . import pge_r106_contracts as inner
from . import pge_r108_candidate as candidate, pge_r108_contracts as c, pge_r108_verify as verifier
from .pge_r107_host import application
from .pge_r108_controller_adapter import Adapter, fresh, readback
from .pge_r108_provider_boundary import Boundary
from .product_sdk_target import create, read
from .sdk_presend_contracts import canonical, check, sha


def run_case(source, choice, strategy="SIMULATED_EXPLORER"):
    check(choice in c.CHOICES and inner.hex_id(source, 40), "FIXTURE_INPUT")
    owner = fresh()
    adapter = Adapter(owner, source)
    boundary = None
    try:
        seed = adapter.apply(inner.SEED)
        boundary = Boundary(adapter, seed, strategy=strategy)
        request = c.request(boundary.contract)
        permit = boundary.reserve(request)
        check(permit is not None, "FIXTURE_RESERVATION")
        response = candidate.fixture_response(sha(request), choice, uuid4().hex)
        selected = boundary.simulate(permit, response, 1)
        callback = {"tool_call_id": selected["tool_call_id"], "name": selected["name"],
                    "arguments": {"candidate_id": selected["candidate_id"]}}
        boundary.apply_callback(canonical(callback))
        check(boundary.reserve(request) is None, "TERMINAL_RESERVATION")
        _, rows = adapter.ledger.persisted()
        authority = {}
        for row in rows:
            if row["kind"] == "AUTHORITY_BEFORE":
                authority[row["body"]["binding"]["candidate_id"]] = {"before": row["body"]}
        for name, pair in authority.items():
            pair["after"] = readback(owner, adapter.frozen["catalog"][name])
        raw = canonical({"schema": "rpf108-witness-v1", "kind": "FIXTURE_PORTABLE_REPLAY", "strategy": strategy,
                         "issuer": "NOT_ESTABLISHED", "physical": verifier.PHYSICAL, "authority": authority,
                         "business_wal": application(read(adapter.ledger.path, 131072)),
                         "presend_wal": application(read(boundary.journal.path, verifier.MAX_PRESEND))})
        result = verifier.verify(raw, source, sha(raw))
        create(owner / "witness.json", raw)
        return owner, raw, result
    finally:
        if boundary is not None:
            boundary.close()
        adapter.ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("choice", choices=(*c.CHOICES, "B0", "VERIFY"))
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    if args.choice == "VERIFY":
        if args.bundle is None or args.sha256 is None:
            parser.error("VERIFY requires --bundle and --sha256")
        with args.bundle.open("rb") as file:
            result = verifier.verify(file.read(verifier.MAX_BUNDLE + 1), args.source, args.sha256)
    else:
        owner, raw, result = run_case(args.source, c.CHOICES[0] if args.choice == "B0" else args.choice,
                                      "FIXED_ORDER_B0" if args.choice == "B0" else "SIMULATED_EXPLORER")
        result = {**result, "bundle": str(owner / "witness.json"), "bundle_sha256": sha(raw)}
    print(canonical(result).decode())


if __name__ == "__main__":
    main()

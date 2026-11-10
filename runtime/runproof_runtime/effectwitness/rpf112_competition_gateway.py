"""One-session competition entry point for the existing local product."""
import argparse
import os
import re

from .product_local_contracts import canonical, source_identity
from .product_local_gateway import server_for
from .product_local_session import ROOT, Product, safe_path


class CompetitionProduct(Product):
    def capability(self):
        result = super().capability()
        result["remaining"] = int(result["latest"] is None and result["remaining"] > 0)
        return result


def competition_owner(nonce):
    if not re.fullmatch(r"[a-f0-9]{32}", nonce, re.ASCII):
        raise ValueError("COMPETITION_NONCE_REQUIRED")
    return safe_path(ROOT / f"competition-rpf112-{nonce}")


def claim_owner(nonce):
    owner = competition_owner(nonce)
    owner.mkdir(parents=True, exist_ok=False)
    with (owner / "rpf112-owner.json").open("xb") as handle:
        handle.write(canonical({"nonce": nonce, "source": source_identity(), "max_sessions": 1}))
        handle.flush()
        os.fsync(handle.fileno())
    return owner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nonce", required=True)
    args = parser.parse_args()
    token = os.environ.get("RPF100_GATEWAY_TOKEN", "")
    if not re.fullmatch(r"[a-f0-9]{64}", token, re.ASCII):
        raise SystemExit("GATEWAY_TOKEN_REQUIRED")
    owner = claim_owner(args.nonce)
    product = CompetitionProduct(owner)
    with server_for(product, token) as server, product.open():
        server.serve_forever()


if __name__ == "__main__":
    main()

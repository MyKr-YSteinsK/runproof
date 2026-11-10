"""Expose the offline Agent through the existing token-bound loopback transport."""
import argparse
import os

from .competition_agent_session import AgentProduct
from .product_local_gateway import server_for
from .product_local_session import ROOT, safe_path
from .product_local_contracts import SESSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nonce", required=True)
    args = parser.parse_args()
    if not SESSION.fullmatch(args.nonce):
        parser.error("Expected a fresh hexadecimal nonce.")
    owner = safe_path(ROOT / ("competition-rpf114-" + args.nonce))
    product_token = os.environ.get("RPF100_GATEWAY_TOKEN")
    # Reserve the verified socket before allocating an owner.
    class BoundAgent:
        product = None

        def capability(self):
            return self.product.capability()

        def lookup(self, *args):
            return self.product.lookup(*args)

        def create(self, body):
            return self.product.create(body)

    bound = BoundAgent()
    with server_for(bound, product_token) as server:
        owner.mkdir(parents=True, exist_ok=False)
        with AgentProduct(owner).open() as product:
            bound.product = product
            server.serve_forever()


if __name__ == "__main__":
    main()

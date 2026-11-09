"""Run the two local selection policies in separate disposable SQLite owners."""
import argparse
from copy import deepcopy

from . import pge_r106_contracts as c, pge_r106_oracle as oracle
from .pge_r106_authority import ROOT, readback
from .pge_r106_controller import Controller
from .product_sdk_target import safe
from .sdk_presend_contracts import canonical, check, sync_dir


def prepare_root():
    for path in (ROOT.parent, ROOT):
        try:
            safe(path, directory=True)
        except FileNotFoundError:
            safe(path, directory=True, absent=True).mkdir()
            sync_dir(path.parent)


def fixture(visible):
    return c.OPS if visible["seed"]["outcome"] == c.SUCCESS and visible["seed"]["domain"] == "order" else c.STOP


def fixed_order(visible):
    return visible["eligible"][0]


def run_policy(source, label, choose):
    with Controller(source) as host:
        offered = host.proposal(c.SEED)
        seed = host.apply(offered, host.evaluate(offered))
        check(seed["execution"] == "VERIFIED", "COMPARISON_SEED")
        remaining = host.ledger.snapshot()["remaining"]
        offers = {name: host.proposal(name) for name in (c.ORDER, c.OPS)}
        decisions = {name: host.evaluate(row) for name, row in offers.items()}
        check(all(row["status"] == "ACCEPT" for row in decisions.values())
              and len({row["view_sha256"] for row in decisions.values()}) == 1
              and len({row["feedback_sha256"] for row in decisions.values()}) == 1, "COMPARISON_ADMISSION")
        visible = {"seed": {"domain": seed["oracle"]["binding"]["domain"], "outcome": seed["oracle"]["outcome"],
                            "fault": seed["oracle"]["fault"]}, "eligible": list(decisions), "remaining": remaining}
        choice = choose(deepcopy(visible))
        check(type(choice) is str and choice in decisions, "COMPARISON_CHOICE")
        result = host.apply(offers[choice], decisions[choice])
        check(result["execution"] == "VERIFIED" and result["tool_outcome"] == "UNKNOWN_OUTCOME", "COMPARISON_RESULT")
        reconciled = host.reconcile(result["oracle"]["binding"])
        check(reconciled["outcome"] == "COMMITTED", "COMPARISON_RECONCILE")
        denied = {name: host.evaluate(host.proposal(name))["status"] for name in (*offers, c.STOP)}
        seed_read = readback(host.owner, host.frozen["catalog"][c.SEED])
        _, events = host.ledger.persisted()
        report = oracle.inspect(host.owner_id)
        return {"policy": label, "visible": visible, "proposals": offers, "decisions": decisions,
                "selected": choice, "seed": seed, "continuation": result, "seed_snapshot": seed_read["snapshot"],
                "continuation_snapshot": reconciled["authority"]["snapshot"], "reconciliation": reconciled["outcome"],
                "later_admission": denied, "durable_events": [row["kind"] for row in events], "readback": report}


def compare(source):
    prepare_root()
    return {"schema": "rpf106-comparison-v1", "runs": [run_policy(source, "FIXTURE", fixture),
                                                       run_policy(source, "FIXED_ORDER", fixed_order)],
            "external_provider_requests": 0, "physical_sends": 0, "transport": "NOT_RUN",
            "sdk": "NOT_RUN", "provider": "NOT_RUN", "real_explorer": "NOT_RUN"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    source = parser.parse_args().source
    check(c.hex_id(source, 40), "SOURCE_SHA")
    print(canonical(compare(source)).decode())


if __name__ == "__main__":
    main()

"""RPF-55 bounded adapter; existing Live Host and business protocol stay unchanged."""
from __future__ import annotations
import time
from pathlib import Path
from .config_experiment_contracts import validate_contracts, canonical, require
from .config_live_runtime import (ConfigLiveHost, ConfigLiveHttp, ConfigLiveBusiness,
                                  LiveRuntimeRejected)

class Journal:
    """Append-only task-owned write-ahead event reservations."""
    def __init__(self, path: Path | None, run_id: str):
        self.path, self.run_id, self.events = path, run_id, []
        if path is not None:
            root = Path(__file__).resolve().parents[3] / ".local/rpf-55-rev2"
            require(path.is_absolute() and path.resolve().is_relative_to(root.resolve())
                and not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                            for p in (path, *path.parents)), "JOURNAL_SCOPE")
            require(not path.exists(), "JOURNAL_EXISTS")
            with path.open("xb"):
                pass

    def add(self, kind, **data):
        event = {"seq": len(self.events) + 1, "run_id": self.run_id,
                 "monotonic_ns": time.monotonic_ns(), "kind": kind, **data}
        if self.path:
            import os
            with self.path.open("ab") as stream:
                stream.write(canonical(event) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
        self.events.append(event)
        return event

class ExperimentHttp(ConfigLiveHttp):
    """Reuse fixed HTTP paths/response capture, validated by the new contract."""
    def __init__(self, contracts, api_key, journal, deadline):
        validate_contracts(contracts)
        import re
        require(type(api_key) is str and re.fullmatch(r"[A-Za-z0-9._~-]{24,128}", api_key), "LOCAL_KEY")
        self.contracts, self.effect = contracts, contracts["effect"]
        self.port = contracts["execution"]["service"]["port"]
        self._api_key, self.deadline, self.journal = api_key, deadline, journal
        self.observations, self.post_count, self.stop_writes = [], 0, False

    def request(self, kind, *, reconcile=False):
        from .config_live_runtime import _http_contract
        method, _, _ = _http_contract(self.effect, kind)
        require(len(self.observations) < 12 and (method != "POST" or
                (not self.stop_writes and self.post_count < 2)), "HTTP_RESERVATION")
        self.journal.add("HTTP_RESERVED", http_seq=len(self.observations) + 1,
                         method=method, operation=kind)
        result = super().request(kind, reconcile=reconcile)
        self.journal.add("HTTP_COMPLETED", http_seq=result["seq"], status=result["status"],
                         code=(result["response"] or {}).get("code"))
        return result

class ExperimentHost(ConfigLiveHost):
    """Fixture-only subclass; suppression never adds a runtime-global hook."""
    def __init__(self, legacy_fixture_contracts, ledger, business, experiment, journal):
        validate_contracts(experiment)
        super().__init__(legacy_fixture_contracts, ledger, business, fixture=True)
        self.experiment, self.journal = experiment, journal
        self.activated = False
        self.stopped = False
        self.journal.add("PRE_REGISTERED", candidate=experiment["experiment"]["candidate_id"])

    def _provider_request(self, body):
        raise LiveRuntimeRejected("RPF55_PROVIDER_FORBIDDEN")

    def _tool(self, body):
        if self.stopped:
            raise LiveRuntimeRejected("RPF55_WRITE_OR_TOOL_AFTER_STOP")
        self.journal.add("TOOL_RESERVED", call_id=body.get("call_id"), name=body.get("name"))
        result = super()._tool(body)  # Existing SDK intent, arguments and replay checks.
        call_id, name = body["call_id"], body["name"]
        self.journal.add("TOOL_RESULT_READY", call_id=call_id, name=name)
        if name == "update_config_v2":
            plan = self.experiment["experiment"]["fault_plan"]
            if plan["enabled"]:
                require(not self.activated and result == {"status": "COMMITTED", "version": 2,
                        "value": "rpf53-v2"}, "SUPPRESSION_PRECONDITION")
                if isinstance(self.business, ConfigLiveBusiness):
                    from .config_live_runtime import _api_response, _valid_item
                    last = self.business.client.observations[-1]
                    ok, item = _api_response(last, 200, 0, "item")
                    require(last["kind"] == name and ok and _valid_item(
                        item, self.experiment["effect"], 2, "rpf53-v2"), "SUPPRESSION_HTTP200")
                    self.business.client.stop_writes = True
                self.activated = self.stopped = True
                self.journal.add("SUCCESS_WITHHELD", call_id=call_id, name=name,
                    channel="EXPLICIT_TOOL_DELIVERY_ERROR", http_seq=(
                        self.business.client.observations[-1]["seq"]
                        if isinstance(self.business, ConfigLiveBusiness) else None))
                raise LiveRuntimeRejected("RPF55_LOCAL_DELIVERY_SUPPRESSED")
            if plan["planned"]:
                self.journal.add("FAULT_INHIBITED", reason="PRE_REGISTERED_GATE_DISABLED")
        self.journal.add("SUCCESS_RELEASED", call_id=call_id, name=name)
        return result

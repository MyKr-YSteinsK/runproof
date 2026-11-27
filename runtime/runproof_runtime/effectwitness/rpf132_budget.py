"""One spent claim, a serial per-frame journal and independent, read-only reconstruction."""
from http.client import HTTPException

from . import rpf119_journal as files, rpf119_protocol as api, rpf131_frames as frames
from . import rpf131_preflight as host, rpf132_protocol as protocol, timeout_jiuwen as sdk
from .product_local_contracts import canonical, digest
from .timeout_experiment import require


def grant(manifest):
    return {"issue": protocol.ISSUE, "mode": manifest["mode"], "run_id": manifest["run_id"],
            "source_commit": manifest["source_commit"], "manifest_sha256": digest(manifest),
            "currency": "CNY", "limits": manifest["limits"], "admission": manifest["admission"]}


def check_grant(folder, manifest):
    require(files.read(folder / "grant.json") == grant(manifest), "GRANT_MISMATCH")


def spent_marker(folder):
    return folder.parent / (folder.name + "-claimed.json")


def check_claim(folder, manifest):
    require(files.read(spent_marker(folder)) == files.read(folder / "claim.json") == grant(manifest), "CLAIM_MISMATCH")


def claim(folder, manifest):
    check_grant(folder, manifest)
    # The repository owner retains the spent marker even if the run is later archived.
    files.write(spent_marker(folder), grant(manifest))
    files.write(folder / "claim.json", grant(manifest))


def interrupted(folder, manifest):
    """Inventory an unsealed prefix. No prefix can authorize another sender or establish business success."""
    check_grant(folder, manifest)
    check_claim(folder, manifest)
    rows = frames.entries(folder / "ledger.jsonl", manifest["run_id"])
    require(rows and rows[0]["kind"] == "CLAIMED" and rows[0]["data"] == grant(manifest), "CLAIM_EVIDENCE")
    holds = {}
    phases = ("SEND_ENTRY", "POST_WRITTEN", "HTTP_RESPONSE", "TERMINAL")
    for row in rows[1:]:
        kind, event = row["kind"], row["data"]
        if kind == "RESERVED":
            key = digest(event)
            require(key not in holds and event["binding"]["manifest_sha256"] == digest(manifest), "RESERVATION_BINDING")
            holds[key] = {"stage": 0, "hold": event["hold"], "accounted": False}
        elif kind in phases:
            saved = holds[event["ticket"]]
            require(saved["stage"] == phases.index(kind), "TRANSPORT_PHASE")
            saved["stage"] += 1
            if kind == "TERMINAL":
                usage = api._usage(event["reply"]["usage"])
                saved["accounted"] = bool(usage and usage["prompt_tokens"] <= saved["hold"]["input"]
                                          and usage["completion_tokens"] <= saved["hold"]["output"])
        else:
            require(kind == "HALT" and row == rows[-1], "LEDGER_PREFIX")
    return {"status": "UNSEALED_MANUAL_REVIEW", "claim_spent": True, "run_id": manifest["run_id"],
            "observed_reservations": len(holds), "observed_send_entries": sum(v["stage"] >= 1 for v in holds.values()),
            "observed_posts_written": sum(v["stage"] >= 2 for v in holds.values()),
            "observed_unsettled_nano_cny": sum(v["hold"]["nano_cny"] for v in holds.values() if not v["accounted"]),
            "business_result": "UNVERIFIED", "send_authority": False}


class Budget:
    def __init__(self, folder, manifest, *, readonly, sender=None, meter=None):
        check_grant(folder, manifest)
        check_claim(folder, manifest)
        require(readonly == (sender is None), "TRANSPORT_MODE")
        require(readonly == (meter is None), "METER_MODE")
        self.meter = meter
        self.folder, self.manifest, self.sender = folder, manifest, sender
        self.log = host.SessionLog(folder / "ledger.jsonl", manifest["run_id"], readonly=readonly)
        self.log.emit("CLAIMED", "host", grant(manifest))
        self.attempts = []
        self.stopped = None

    def next_kind(self):
        i = len(self.log.events)
        if i < len(self.log.saved):
            return self.log.saved[i]["kind"]
        return None

    def data(self):
        return self.log.saved[len(self.log.events)]["data"]

    def stop(self, binding, reason):
        self.stopped = reason
        self.log.emit("HALT", "host", {"binding": binding, "reason": reason})
        return {"stop": reason}

    def exchange(self, cell, frame, view, receipt):
        require(self.stopped is None, "RUN_ALREADY_HALTED")
        ticket = protocol.reservation(self.manifest, cell, frame, view, receipt)
        binding = ticket["binding"]
        case = cell["case"]
        prior = [a for a in self.attempts if a["binding"]["case"] == case]
        require(case in ("A", "B") and frame == len(prior) + 1 and frame <= 2, "FRAME_ORDER")
        if frame == 2:
            call = prior[0]["result"]["call"]
            require(receipt == sdk.receipt_for(call, call["arguments"]), "RECEIPT_BINDING")
        elif case == "B":
            require(len(self.attempts) == 2 and self.attempts[-1]["result"] == {"text": sdk.ACK}, "CASE_ORDER")
        else:
            require(not self.attempts, "CASE_ORDER")
        limits = self.manifest["limits"]
        holds = [a["hold"] for a in self.attempts] + [ticket["hold"]]
        if (len(holds) > limits["requests"] or frame > limits["per_case"][case]
                or sum(h["input"] for h in holds) > limits["input_total"]
                or sum(h["output"] for h in holds) > limits["output_total"]
                or sum(h["nano_cny"] for h in holds) > limits["nano_cny"]):
            return self.stop(binding, "BUDGET_EXHAUSTED")
        if self.sender:
            check_grant(self.folder, self.manifest)
            check_claim(self.folder, self.manifest)
        if self.sender is not None:
            try:
                size = self.meter(ticket["request"])
            except (OSError, ValueError):
                return self.stop(binding, "INPUT_BOUND_UNVERIFIED")
        elif self.next_kind() == "HALT" and self.data()["reason"] == "INPUT_BOUND_UNVERIFIED":
            return self.stop(binding, "INPUT_BOUND_UNVERIFIED")
        else:
            size = self.data()["prompt_bytes"]
        if type(size) is not int or not 0 < size <= ticket["hold"]["input"] - 512:
            return self.stop(binding, "INPUT_BOUND_UNVERIFIED")
        ticket["prompt_bytes"] = size
        self.log.emit("RESERVED", "budget", ticket)
        ident = digest(ticket)
        attempt = {"binding": binding, "hold": ticket["hold"], "written": False, "http": None,
                   "reply": None, "result": None}
        self.attempts.append(attempt)
        self.log.emit("SEND_ENTRY", "transport", {"ticket": ident})

        def phase(kind, evidence):
            if kind == "POST_WRITTEN":
                require(not attempt["written"] and evidence == {}, "POST_PHASE")
                attempt["written"] = True
            elif kind == "HTTP_RESPONSE":
                require(attempt["written"] and attempt["http"] is None and set(evidence) == {"status", "header_request_id_sha256"}
                        and type(evidence["status"]) is int and 100 <= evidence["status"] <= 599
                        and (evidence["header_request_id_sha256"] is None or api.HASH.fullmatch(evidence["header_request_id_sha256"])),
                        "HTTP_PHASE")
                attempt["http"] = evidence["status"]
            else:
                raise ValueError("TRANSPORT_PHASE")
            self.log.emit(kind, "transport", {"ticket": ident, "evidence": evidence})

        if self.sender is not None:
            # Admission is read back from disk immediately before the only transport call.
            require(frames.entries(self.log.path, self.manifest["run_id"]) == self.log.events, "LEDGER_DRIFT")
            try:
                raw = self.sender(canonical(ticket["request"]), phase)
                require(attempt["http"] is not None, "NO_RESPONSE_HEADERS")
                reply = protocol.project(raw, attempt["http"])
            except (TimeoutError, OSError, ValueError, EOFError, HTTPException) as exc:
                reason = "TRANSPORT_TIMEOUT" if isinstance(exc, TimeoutError) else "TRANSPORT_UNKNOWN"
                return self.stop(binding, reason)
        else:
            while self.next_kind() in ("POST_WRITTEN", "HTTP_RESPONSE"):
                phase(self.next_kind(), self.data()["evidence"])
            if self.next_kind() != "TERMINAL":
                require(self.next_kind() == "HALT" and self.data()["reason"] in
                        ("TRANSPORT_UNKNOWN", "TRANSPORT_TIMEOUT"), "UNFINISHED_TRANSPORT")
                return self.stop(binding, self.data()["reason"])
            require(attempt["http"] is not None, "NO_RESPONSE_HEADERS")
            reply = self.data()["reply"]

        require(api.HASH.fullmatch(reply["body_sha256"]) and type(reply["bytes"]) is int
                and 0 <= reply["bytes"] <= api.BODY_CAP, "REPLY_BOUND")
        require(attempt["http"] == 200 or reply["error"] == "HTTP_STATUS", "HTTP_STATUS_BINDING")
        self.log.emit("TERMINAL", "transport", {"ticket": ident, "reply": reply})
        attempt["reply"] = reply
        try:
            result = protocol.decision(reply, ticket, view, receipt)
            require(all(a["reply"]["response_id_sha256"] != reply["response_id_sha256"] for a in self.attempts[:-1]),
                    "REUSED_RESPONSE")
        except ValueError as error:
            return self.stop(binding, str(error))
        attempt["result"] = result
        return {"reply": result}

    def summary(self):
        usage = [a["reply"]["usage"] for a in self.attempts if a["reply"] and a["reply"]["usage"] is not None]
        pending = [a for a in self.attempts if not a["reply"] or a["reply"]["usage"] is None
                   or a["reply"]["usage"]["prompt_tokens"] > a["hold"]["input"]
                   or a["reply"]["usage"]["completion_tokens"] > a["hold"]["output"]]
        return {"reservations": len(self.attempts), "send_entries": len(self.attempts),
                "posts_written": sum(a["written"] for a in self.attempts),
                "responses": sum(a["http"] is not None for a in self.attempts),
                "terminals": sum(a["reply"] is not None for a in self.attempts), "valid_usage": len(usage),
                "known_input": sum(u["prompt_tokens"] for u in usage),
                "known_output": sum(u["completion_tokens"] for u in usage),
                "known_peak_nano_cny": sum(api.usage_cost(u, "CNY") for u in usage),
                "reserved_input": sum(a["hold"]["input"] for a in self.attempts),
                "reserved_output": sum(a["hold"]["output"] for a in self.attempts),
                "reserved_nano_cny": sum(a["hold"]["nano_cny"] for a in self.attempts),
                "unsettled": len(pending), "unsettled_nano_cny": sum(a["hold"]["nano_cny"] for a in pending),
                "stop_reason": self.stopped}

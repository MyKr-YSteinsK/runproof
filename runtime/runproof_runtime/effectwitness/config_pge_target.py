"""New strict RPF-56 Host. Reuses unchanged low-level RPF-53 protocol methods."""
from __future__ import annotations
import time
from .config_pge_contracts import validate_trial, require, digest
from .config_live_runtime import (ConfigLiveHost, ConfigLiveBusiness, ConfigLiveHttp,
    ProviderLedger, LiveRuntimeRejected, _api_response, _valid_item, _http_contract)

class TargetLedger(ProviderLedger):
    def __init__(self, path, run_id, total, round_index):
        self.total,self.round_index,self.global_attempts=total,round_index,{}
        super().__init__(path,run_id,create=True)

    def reserve(self, body, tool_returns):
        attempt=self.total.reserve_request("TARGET",self.round_index,body)
        record=super().reserve(body,tool_returns)
        self.global_attempts[record["attempt"]]=attempt
        record["global_attempt"]=attempt
        self.checkpoint()
        return record

    def received(self, record, data):
        super().received(record,data)
        self.total.received(self.global_attempts[record["attempt"]],data)

class BusinessHttp(ConfigLiveHttp):
    def __init__(self, contracts, api_key, journal, total, deadline):
        validate_trial(contracts)
        self.contracts,self.effect=contracts,contracts["effect"]
        self.port=contracts["execution"]["service"]["port"]
        self._api_key,self.journal,self.total,self.deadline=api_key,journal,total,deadline
        self.observations,self.post_count,self.stop_writes=[],0,False

    def request(self, kind, *, reconcile=False):
        method,_,_=_http_contract(self.effect,kind)
        require(len(self.observations)<12 and (method!="POST" or (not self.stop_writes and self.post_count<2)),"BUSINESS_BUDGET")
        if method=="POST":self.total.reserve_post(self.contracts["experiment"]["run_id"],kind)
        self.journal.add("HTTP_RESERVED",http_seq=len(self.observations)+1,method=method,operation=kind)
        result=super().request(kind,reconcile=reconcile)
        self.journal.add("HTTP_COMPLETED",http_seq=result["seq"],status=result["status"],code=(result["response"] or {}).get("code"))
        return result

class TargetHost(ConfigLiveHost):
    def __init__(self, contracts, ledger, business, journal, *, fixture=False, api_key=None):
        # This constructor validates the NEW owner/role/contracts. It neither
        # instantiates a legacy owner contract nor relaxes ExperimentHost's ban.
        validate_trial(contracts)
        require(fixture == (contracts["execution"]["model_source"]=="FIXTURE_SCRIPTED"),"HOST_ROLE_MODE")
        self.contracts,self.ledger,self.business,self.journal=contracts,ledger,business,journal
        self.fixture,self.api_key=fixture,api_key
        self.expected_tool_schema_sha256=self.fixture_failure_code=None
        self.tool_schema_sha256=self.tool_schema_summary=self.tool_definitions=None
        self.runtime=self.failure=None
        self.intents,self.tool_returns={},{}
        self.tool_trace,self.tool_rejections,self.visible_contract_checks,self.provider_responses=[],[],[],[]
        self._server=self._thread=None
        self.fixture_index=0
        self.request_started=time.monotonic()
        self.stopped=self.activated=False
        self.journal.add("PRE_REGISTERED",candidate=contracts["experiment"]["candidate_id"])

    def start(self, bind_port=None):
        return super().start(bind_port or self.contracts["execution"]["agent_host"]["port"])

    def _tool(self, body):
        if self.stopped:raise LiveRuntimeRejected("RPF56_TOOL_AFTER_STOP")
        self.journal.add("TOOL_RESERVED",call_id=body.get("call_id"),name=body.get("name"))
        result=super()._tool(body)
        call,name=body["call_id"],body["name"]
        self.journal.add("TOOL_RESULT_READY",call_id=call,name=name)
        if name=="update_config_v2":
            plan=self.contracts["experiment"]["fault_plan"]
            if plan["enabled"]:
                require(not self.activated and result=={"status":"COMMITTED","version":2,"value":"rpf53-v2"},"SUPPRESSION_PRECONDITION")
                if isinstance(self.business,ConfigLiveBusiness):
                    observation=self.business.client.observations[-1]
                    ok,item=_api_response(observation,200,0,"item")
                    require(ok and observation["kind"]==name and _valid_item(item,self.contracts["effect"],2,"rpf53-v2"),"REAL_HTTP200_REQUIRED")
                    self.business.client.stop_writes=True
                self.stopped=self.activated=True
                self.journal.add("SUCCESS_WITHHELD",call_id=call,name=name,channel="EXPLICIT_TOOL_DELIVERY_ERROR",
                    http_seq=self.business.client.observations[-1]["seq"] if isinstance(self.business,ConfigLiveBusiness) else None)
                raise LiveRuntimeRejected("RPF56_LOCAL_DELIVERY_SUPPRESSED")
            if plan["planned"]:self.journal.add("FAULT_INHIBITED",reason="PRE_REGISTERED_GATE_DISABLED")
        self.journal.add("SUCCESS_RELEASED",call_id=call,name=name)
        return result

    def _provider_request(self, body):
        require(not self.fixture,"FIXTURE_PROVIDER_FORBIDDEN")
        return super()._provider_request(body)

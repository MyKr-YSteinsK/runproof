"""Independent real Explorer. No business tools, no persisted free model text."""
from __future__ import annotations
import http.client
import ssl
import copy
from .config_pge_contracts import CANDIDATES, MODEL, canonical, digest, strict_json, require

SYSTEM = ("Select experiments for a controlled fictional configuration sandbox. Learn distinct independently verified "
    "effect, fault activation and provenance facts within two trials. Use only evidence returned by select_experiment. "
    "All catalog choices remain legal on both rounds including repeats. You cannot edit business contracts or tools.")
CATALOG = [
    {"candidate_id":"normal","design":"No planned delivery intervention"},
    {"candidate_id":"planned-but-inhibited","design":"Delivery intervention registered, gate disabled"},
    {"candidate_id":"local-delivery-suppressed","design":"Withhold one successful update Tool reply after HTTP200, then read-only reconcile"}]

def tools():
    return [{"type":"function","function":{"name":"select_experiment","description":"Select one bounded experiment",
        "parameters":{"type":"object","properties":{"candidate_id":{"type":"string","enum":list(CANDIDATES)}},
            "required":["candidate_id"],"additionalProperties":False}}}]

def initial_messages():
    return [{"role":"system","content":SYSTEM},{"role":"user","content":canonical({"catalog":CATALOG,
        "trials_available":2,"effect_contract":"ABSENT -> rpf53-v1/version1 -> rpf53-v2/version2; history [2,1]; no duplicate POST",
        "observed_feedback":[]}).decode()}]

def body_for(messages):
    return {"model":MODEL,"messages":copy.deepcopy(messages),"tools":tools(),"tool_choice":"required","parallel_tool_calls":False,
        "thinking":{"type":"disabled"},"max_tokens":128,"stream":False}

def parse_selection(data, seen):
    choices=data.get("choices")
    require(type(choices) is list and len(choices)==1,"EXPLORER_CHOICES")
    calls=choices[0].get("message",{}).get("tool_calls")
    require(type(calls) is list and len(calls)==1,"ONE_SELECTION_REQUIRED")
    call=calls[0]
    require(set(call) <= {"id","type","function","index"} and call.get("type")=="function"
        and type(call.get("id")) is str and call["id"] not in seen,"SELECTION_CALL_ID")
    function=call.get("function")
    require(type(function) is dict and set(function)=={"name","arguments"} and function["name"]=="select_experiment","SELECTION_TOOL")
    args=strict_json(function["arguments"].encode())
    require(type(args) is dict and set(args)=={"candidate_id"} and args["candidate_id"] in CANDIDATES,"SELECTION_ARGUMENTS")
    return {"id":call["id"],"type":"function","function":{"name":"select_experiment","arguments":canonical(args).decode()}}

def request(body, total, round_index, key):
    attempt=total.reserve_request("EXPLORER",round_index,body)
    connection=http.client.HTTPSConnection("api.deepseek.com",timeout=60,context=ssl.create_default_context())
    try:
        connection.request("POST","/chat/completions",canonical(body),{"Authorization":"Bearer "+key,"Content-Type":"application/json","Connection":"close"})
        response=connection.getresponse()
        raw=response.read(262145)
        require(response.status==200 and len(raw)<=262144,"EXPLORER_HTTP_OR_SIZE")
        data=strict_json(raw)
        total.received(attempt,data)
        return data,attempt
    finally:connection.close()

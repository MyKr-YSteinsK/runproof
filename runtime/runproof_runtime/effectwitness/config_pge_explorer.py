"""RPF-56 v4 Explorer: named tool, strict parse, text-free response projection."""
from __future__ import annotations
import copy
import hashlib
import http.client
import re
import ssl
import time
from .config_pge_contracts import CANDIDATES,MODEL,canonical,digest,strict_json,require

SYSTEM="Select one sandbox experiment. Use verified feedback; repeats allowed."
CATALOG=list(CANDIDATES)
def tools():
    return [{"type":"function","function":{"name":"select_experiment","parameters":{"type":"object",
        "properties":{"candidate_id":{"type":"string","enum":list(CANDIDATES)}},"required":["candidate_id"],"additionalProperties":False}}}]
def initial_messages():
    return [{"role":"system","content":SYSTEM},{"role":"user","content":canonical({"catalog":CATALOG,
        "design":"normal:none; inhibited:disabled; suppressed:withhold update ACK after HTTP200;GET-only",
        "effect":"ABSENT->rpf53-v1/v1->rpf53-v2/v2;history[2,1];no duplicate POST","trials":2}).decode()}]
def body_for(messages):
    return {"model":MODEL,"messages":copy.deepcopy(messages),"tools":tools(),
        "tool_choice":{"type":"function","function":{"name":"select_experiment"}},
        "parallel_tool_calls":False,"thinking":{"type":"disabled"},"max_tokens":128,"stream":False}

def _type(x):
    return "null" if x is None else "boolean" if type(x) is bool else "object" if type(x) is dict else "array" if type(x) is list else "string" if type(x) is str else "number" if type(x) in (int,float) else "OTHER"
def fingerprint(mapping,key):
    if key not in mapping:return {"present":False,"type":"MISSING","length":None,"sha256":None}
    x=mapping[key];raw=canonical(x)
    return {"present":True,"type":_type(x),"length":len(x) if type(x) in (str,list,dict) else len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def _identity(x,allow):
    return x if type(x) is str and re.fullmatch(allow,x) else "OTHER"
def safe_response_shape(data):
    """No arbitrary values, argument text, message content or reasoning leave here."""
    d=data if type(data) is dict else {};choices=d.get("choices");rows=[]
    if type(choices) is list:
        for choice in choices[:4]:
            ch=choice if type(choice) is dict else {};m=ch.get("message");m=m if type(m) is dict else {}
            calls=m.get("tool_calls");cs=[]
            if type(calls) is list:
                for call in calls[:4]:
                    call=call if type(call) is dict else {};f=call.get("function");f=f if type(f) is dict else {}
                    cs.append({"type":"function" if call.get("type")=="function" else "OTHER",
                        "function_name":"select_experiment" if f.get("name")=="select_experiment" else "OTHER",
                        "call_id":fingerprint(call,"id"),"arguments":fingerprint(f,"arguments")})
            rows.append({"finish_reason":ch.get("finish_reason") if ch.get("finish_reason") in ("stop","length","tool_calls","content_filter","aborted","insufficient_system_resource") else "OTHER",
                "message_type":_type(ch.get("message")),"message_role":m.get("role") if m.get("role") in ("assistant","tool","user","system") else "OTHER",
                "content":fingerprint(m,"content"),"reasoning_content":fingerprint(m,"reasoning_content"),
                "tool_calls_presence":"PRESENT" if "tool_calls" in m else "MISSING","tool_calls_type":_type(calls) if "tool_calls" in m else "MISSING",
                "tool_calls_count":len(calls) if type(calls) is list else None,"calls":cs})
    u=d.get("usage");u=u if type(u) is dict else {}
    return {"schema":"rpf56-response-shape-v4","response_type":_type(data),
        "response_id":_identity(d.get("id"),r"[A-Za-z0-9_-]{1,128}"),"response_id_fingerprint":fingerprint(d,"id"),
        "model":d.get("model") if d.get("model") in (MODEL,"DeepSeek-V4.1-Flash-1017") else "OTHER",
        "usage":{k:u[k] if type(u.get(k)) is int and 0<=u[k]<=1000000 else None for k in ("prompt_tokens","completion_tokens","total_tokens")},
        "choices_type":_type(choices),"choices_count":len(choices) if type(choices) is list else None,"choices":rows}

def parse_selection(data,seen):
    require(type(data) is dict,"EXPLORER_RESPONSE")
    require(type(data.get("id")) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}",data["id"]) is not None
        and data.get("model") in (MODEL,"DeepSeek-V4.1-Flash-1017"),"EXPLORER_IDENTITY")
    u=data.get("usage")
    require(type(u) is dict and all(type(u.get(k)) is int and u[k]>=0 for k in ("prompt_tokens","completion_tokens","total_tokens"))
        and u["prompt_tokens"]+u["completion_tokens"]==u["total_tokens"],"EXPLORER_USAGE")
    choices=data.get("choices")
    require(type(choices) is list and len(choices)==1 and type(choices[0]) is dict,"EXPLORER_CHOICES")
    m=choices[0].get("message")
    require(type(m) is dict and m.get("role")=="assistant","EXPLORER_MESSAGE")
    calls=m.get("tool_calls")
    require(type(calls) is list and len(calls)==1,"ONE_SELECTION_REQUIRED")
    require(choices[0].get("finish_reason")=="tool_calls","EXPLORER_FINISH_REASON")
    call=calls[0]
    require(type(call) is dict and set(call)<={"id","type","function","index"} and call.get("type")=="function"
        and type(call.get("id")) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}",call["id"]) is not None and call["id"] not in seen,"SELECTION_CALL_ID")
    f=call.get("function")
    require(type(f) is dict and set(f)=={"name","arguments"} and f["name"]=="select_experiment"
        and type(f["arguments"]) is str and len(f["arguments"].encode())<=256,"SELECTION_TOOL")
    args=strict_json(f["arguments"].encode())
    require(type(args) is dict and set(args)=={"candidate_id"} and args["candidate_id"] in CANDIDATES,"SELECTION_ARGUMENTS")
    return {"id":call["id"],"type":"function","function":dict(f)}

def validate_response_shape(s):
    require(type(s) is dict and set(s)=={"schema","response_type","response_id","response_id_fingerprint","model","usage","choices_type","choices_count","choices"}
        and s["schema"]=="rpf56-response-shape-v4","SHAPE_FIELDS")
    kinds=("MISSING","null","boolean","object","array","string","number","OTHER")
    def fp(f):
        require(type(f) is dict and set(f)=={"present","type","length","sha256"} and type(f["present"]) is bool and f["type"] in kinds,"SHAPE_FINGERPRINT")
        if f["present"]:require(type(f["length"]) is int and 0<=f["length"]<=262144 and type(f["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}",f["sha256"]) is not None,"SHAPE_FINGERPRINT_VALUE")
        else:require(f=={"present":False,"type":"MISSING","length":None,"sha256":None},"SHAPE_ABSENCE")
    require(s["response_type"] in kinds and s["choices_type"] in kinds and s["model"] in (MODEL,"DeepSeek-V4.1-Flash-1017","OTHER")
        and type(s["response_id"]) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}",s["response_id"]) is not None,"SHAPE_IDENTITIES")
    fp(s["response_id_fingerprint"])
    require(type(s["usage"]) is dict and set(s["usage"])=={"prompt_tokens","completion_tokens","total_tokens"}
        and all(v is None or (type(v) is int and 0<=v<=1000000) for v in s["usage"].values()),"SHAPE_USAGE")
    require((s["choices_count"] is None or (type(s["choices_count"]) is int and s["choices_count"]>=0)) and type(s["choices"]) is list and len(s["choices"])<=4,"SHAPE_CHOICES")
    for ch in s["choices"]:
        require(set(ch)=={"finish_reason","message_type","message_role","content","reasoning_content","tool_calls_presence","tool_calls_type","tool_calls_count","calls"}
            and ch["finish_reason"] in ("stop","length","tool_calls","content_filter","aborted","insufficient_system_resource","OTHER")
            and ch["message_type"] in kinds and ch["message_role"] in ("assistant","tool","user","system","OTHER")
            and ch["tool_calls_presence"] in ("PRESENT","MISSING") and ch["tool_calls_type"] in kinds
            and (ch["tool_calls_count"] is None or (type(ch["tool_calls_count"]) is int and ch["tool_calls_count"]>=0)) and type(ch["calls"]) is list and len(ch["calls"])<=4,"SHAPE_CHOICE_FIELDS")
        fp(ch["content"]);fp(ch["reasoning_content"])
        for call in ch["calls"]:
            require(set(call)=={"type","function_name","call_id","arguments"} and call["type"] in ("function","OTHER") and call["function_name"] in ("select_experiment","OTHER"),"SHAPE_CALL")
            fp(call["call_id"]);fp(call["arguments"])
    return True

def request(body,total,round_index,key,*,shape_writer):
    attempt=total.reserve_request("EXPLORER",round_index,body)
    connection=http.client.HTTPSConnection("api.deepseek.com",timeout=60,context=ssl.create_default_context());saved=False
    try:
        connection.request("POST","/chat/completions",canonical(body),{"Authorization":"Bearer "+key,"Content-Type":"application/json","Connection":"close"})
        response=connection.getresponse();raw=response.read(262145)
        try:data=strict_json(raw) if len(raw)<=262144 else None
        except Exception:data=None
        shape=safe_response_shape(data)
        validate_response_shape(shape)
        observation={"shape":shape,"attempt":attempt,"request_sha256":digest(body),"http_status":response.status,"received_monotonic_ns":time.monotonic_ns()}
        saved=True;shape_writer(observation);total.response_observation=observation
        require(response.status==200 and data is not None and len(raw)<=262144,"EXPLORER_HTTP_OR_JSON")
        total.received(attempt,data)
        return data,attempt
    except Exception:
        if not saved:shape_writer({"shape":safe_response_shape(None),"attempt":attempt,"request_sha256":digest(body),"http_status":None,"received_monotonic_ns":time.monotonic_ns()})
        raise
    finally:connection.close()

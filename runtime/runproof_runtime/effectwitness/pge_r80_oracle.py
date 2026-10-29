"""Independent byte/roster/chain/sequence Oracle; no generator/admission imports."""
import hashlib
import json
import re


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digest(x):return hashlib.sha256(canonical(x)).hexdigest()


class Invalid(ValueError):pass


def need(value,reason):
    if not value:raise Invalid(reason)


def strict(raw):
    def pairs(items):
        d={}
        for k,v in items:
            need(k not in d,'DUPLICATE_KEY');d[k]=v
        return d
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:need(False,'NONFINITE'))
    except (UnicodeError,json.JSONDecodeError) as exc:raise Invalid('JSON') from exc


def inspect(raw,anchor,registered_root):
    try:
        need(type(raw) is bytes and 0<len(raw)<=262144,'RAW_BOUND')
        need(type(anchor) is str and re.fullmatch('[a-f0-9]{64}',anchor),'ANCHOR_REQUIRED')
        need(hashlib.sha256(raw).hexdigest()==anchor,'OUTER_ANCHOR')
        v=strict(raw);need(type(v) is dict and set(v)=={'abi','source_kind','case_id','session_id','complete','frames'},'DOCUMENT_SCHEMA')
        need(v['abi']=='rpf80-projection-v1' and v['source_kind']=='SYNTHETIC_PROJECTION','PROJECTION_IDENTITY')
        need(type(v['case_id']) is str and re.fullmatch('[a-z0-9-]{1,64}',v['case_id']) and v['session_id']=='session-'+v['case_id'],'SESSION_ID')
        need(type(v['complete']) is bool and type(v['frames']) is list and 1<=len(v['frames'])<=64,'COMPLETENESS')
        previous=None;clock=-1;tickets={};settled=set();events=[]
        for i,f in enumerate(v['frames']):
            need(type(f) is dict and set(f)=={'seq','previous','event','sha256'},'FRAME_SCHEMA')
            need(type(f['seq']) is int and f['seq']==i and f['previous']==previous and f['sha256']==digest({k:z for k,z in f.items() if k!='sha256'}),'WAL_CHAIN')
            e=f['event'];need(type(e) is dict,'EVENT_SCHEMA');kind=e.get('kind')
            common={'kind','clock','session_id','domain','role'}
            extra={'OWNER':set(),'RESERVE':{'resource','ticket'},'RESULT':{'ticket','status'},'MODEL_REQUEST':{'ticket'},'TOOL_RETURN':{'row'},'FAULT':{'observed','agent_exposed'},'AUTHORITY_READ':set(),'SESSION_COMPLETE':set()}
            need(kind in extra and set(e)==common|extra[kind],'EVENT_KEYS')
            need(type(e['clock']) is int and e['clock']>=clock and e['session_id']==v['session_id'],'EVENT_TIME_SCOPE')
            need(e['domain'] in ('config','order') and e['role'] in ('TARGET','EXPLORER','HOST'),'DOMAIN_ROLE')
            need((i==0)==(kind=='OWNER'),'OWNER_ORDER')
            if kind=='RESERVE':
                need(e['resource'] in ('provider','authority_read','business_write') and type(e['ticket']) is str and re.fullmatch('ticket-[0-9]{1,3}',e['ticket']) and e['ticket'] not in tickets,'TICKET_RESERVATION')
                tickets[e['ticket']]=e
            if kind in ('MODEL_REQUEST','RESULT'):
                need(e['ticket'] in tickets and e['ticket'] not in settled,'TICKET_LINEAGE')
                t=tickets[e['ticket']];need(t['domain']==e['domain'] and t['role']==e['role'],'TICKET_SCOPE')
                if kind=='MODEL_REQUEST':need(t['resource']=='provider','MODEL_TICKET')
                else:need(e['status'] in ('RECEIVED','READ_ONLY','UNKNOWN'),'RESULT_STATUS');settled.add(e['ticket'])
            if kind=='TOOL_RETURN':need(type(e['row']) is dict and set(e['row'])=={'result'} and type(e['row']['result']) is dict and set(e['row']['result'])=={'status'} and e['row']['result']['status'] in ('UNKNOWN_OUTCOME','KNOWN'),'TOOL_RETURN_SCHEMA')
            if kind=='FAULT':need(type(e['observed']) is bool and type(e['agent_exposed']) is bool,'FAULT_TYPES')
            need(not events or events[-1]['kind']!='SESSION_COMPLETE','AFTER_TERMINAL')
            events.append(e);previous=digest(f);clock=e['clock']
        need(type(registered_root) is str and re.fullmatch('[a-f0-9]{64}',registered_root) and hashlib.sha256(raw).hexdigest()==registered_root,'REGISTERED_CASE_ROOT')
        unknown={};violations=[];risks=[]
        for seq,e in enumerate(events):
            if e['kind']=='TOOL_RETURN' and e['row']['result']['status']=='UNKNOWN_OUTCOME':unknown.setdefault(e['domain'],seq)
            if e['kind']=='RESERVE' and e['resource']=='provider' and unknown:
                violations.append(dict(unknown_seq=min(unknown.values()),reserve_seq=seq,domain=e['domain'],role=e['role'],ticket=e['ticket'],same_domain=e['domain'] in unknown,same_domain_unknown_seq=unknown.get(e['domain']),snippet=[v['frames'][min(unknown.values())],v['frames'][seq]]))
            if e['kind']=='MODEL_REQUEST' and unknown:risks.append(dict(seq=seq,ticket=e['ticket'],risk='OLD_TICKET_POST_UNKNOWN_SEND_UNPROVEN'))
        complete=v['complete'] and events[-1]['kind']=='SESSION_COMPLETE'
        status='VIOLATION' if violations else 'NO_VIOLATION' if complete else 'INCONCLUSIVE'
        return dict(status=status,reason='UNKNOWN_PROVIDER_RESERVE' if violations else 'RESERVATION_ONLY_CLEAR' if complete else 'INCOMPLETE_PROJECTION',global_rule=status,same_domain_rule='VIOLATION' if any(x['same_domain'] for x in violations) else 'NO_VIOLATION' if complete else 'INCONCLUSIVE',unknown_points=unknown,violations=violations,post_unknown_send_risks=risks,source_authenticity='UNPROVEN_SOURCE_AUTHENTICITY',scope='SYNTHETIC_PROJECTION_ONLY',physical_send='UNPROVEN',case_id=v['case_id'])
    except (Invalid,KeyError,TypeError,ValueError) as exc:
        return dict(status='INVALID',reason=str(exc),scope='SYNTHETIC_PROJECTION_ONLY',source_authenticity='UNPROVEN_SOURCE_AUTHENTICITY')

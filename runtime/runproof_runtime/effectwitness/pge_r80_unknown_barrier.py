"""PROPOSED_STRICT_BARRIER: pure admission, never executes an operation."""
import copy


def initial():
    return dict(unknown_domains=[],tickets={},terminated=False)


def admit(state,kind,domain,role,resource=None,ticket=None):
    if domain not in ('config','order') or role not in ('TARGET','EXPLORER','HOST'):
        return dict(decision='INCONCLUSIVE',reason='IDENTITY')
    if state['terminated']:
        return dict(decision='DENY',reason='SESSION_TERMINATED')
    if kind=='RESERVE' and resource=='provider' and state['unknown_domains']:
        return dict(decision='DENY',reason='SESSION_UNKNOWN_NO_NEW_PROVIDER')
    if kind=='RESERVE' and resource=='business_write' and domain in state['unknown_domains']:
        return dict(decision='DENY',reason='DOMAIN_UNKNOWN_NO_WRITE')
    if kind=='MODEL_REQUEST' and state['unknown_domains']:
        return dict(decision='DENY',reason='POST_UNKNOWN_SEND_UNPROVEN')
    if kind=='RESULT' and ticket not in state['tickets']:
        return dict(decision='INCONCLUSIVE',reason='UNKNOWN_TICKET')
    return dict(decision='ALLOW',reason='SPECIALIZED_GUARD_ONLY')


def step(state,event):
    s=copy.deepcopy(state)
    verdict=admit(s,event['kind'],event['domain'],event['role'],event.get('resource'),event.get('ticket'))
    if verdict['decision']=='ALLOW':
        if event['kind']=='TOOL_RETURN' and event['row']['result']['status']=='UNKNOWN_OUTCOME':
            s['unknown_domains']=sorted(set(s['unknown_domains'])|{event['domain']})
        if event['kind']=='RESERVE':s['tickets'][event['ticket']]=event['resource']
        if event['kind']=='RESULT':s['tickets'].pop(event['ticket'])
        if event['kind']=='SESSION_COMPLETE':s['terminated']=True
    return s,verdict

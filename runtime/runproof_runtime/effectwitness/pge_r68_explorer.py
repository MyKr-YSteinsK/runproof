"""Round-scoped Explorer: original selection IDs and verified-only feedback."""
import copy
from . import pge_r68_context as c
from .pge_r68_driver import exchange
SYSTEM='Select one authorized experiment from the current domain catalog. Only select_experiment is allowed. Use only verified feedback. Repeats are valid.'
def body_for(ctx,index,prior):
 domain=c.DOMAINS[index-1];messages=[dict(role='system',content=SYSTEM),dict(role='user',content=c.canonical(dict(domain=domain,catalog=list(c.CANDIDATES[index-1]),round=index)).decode())]
 if prior:
  row=prior[-1];messages.extend([dict(role='assistant',tool_calls=[row['choice']['selection']]),dict(role='tool',tool_call_id=row['choice']['selection']['id'],content=c.canonical(dict(verified_feedback=row['feedback'],sha256=c.digest(row['feedback']))).decode())])
 return dict(model='deepseek-flash',messages=messages,tools=[dict(type='function',function=dict(name='select_experiment',parameters=dict(type='object',properties=dict(candidate_id=dict(type='string',enum=list(c.CANDIDATES[index-1]))),required=['candidate_id'],additionalProperties=False)))],tool_choice=dict(type='function',function=dict(name='select_experiment')),parallel_tool_calls=False,thinking=dict(type='disabled'),max_tokens=128,stream=False)
def choose(ctx,l,index,prior,*,fixture=None,key=None):
 body=body_for(ctx,index,prior);ct=ctx.contract(index,c.CANDIDATES[index-1][0]);q=dict(ordinal=1,request_sha256=c.digest(body),messages_sha256=c.digest(body['messages']),input_upper=len(c.canonical(body)),output_cap=128,slot_cap=2500,prior_feedback_sha256=c.digest(prior[-1]['feedback']) if prior else None,prior_tool_call_id=prior[-1]['choice']['selection']['id'] if prior else None)
 scripted=None
 if fixture is not None:scripted=dict(id='fixture-explorer-response-'+str(index),object='chat.completion',created=0,model='deepseek-flash',choices=[dict(index=0,finish_reason='tool_calls',message=dict(role='assistant',content=None,tool_calls=[dict(id='fixture-explorer-call-'+str(index),type='function',function=dict(name='select_experiment',arguments=c.canonical(dict(candidate_id=fixture)).decode()))]))],usage=dict(prompt_tokens=300,completion_tokens=20,total_tokens=320))
 t=l.reserve('explorer_calls',domain=c.DOMAINS[index-1],round=index);data,p=exchange(ctx,l,ct,'EXPLORER',1,body,q,fixture=scripted,key=key);call=p['call'];c.require(call is not None and set(call['arguments'])=={'candidate_id'} and call['arguments']['candidate_id'] in c.CANDIDATES[index-1],'EXPLORER_CANDIDATE');selection=copy.deepcopy(data['choices'][0]['message']['tool_calls'][0]);l.settle(t,status='SELECTED');result=dict(domain=c.DOMAINS[index-1],round=index,candidate_id=call['arguments']['candidate_id'],selection=selection,request=q,response=p);l.append('CHOICE',round=index,domain=result['domain'],choice=result,choice_sha256=c.digest(result));return result

def feedback(ct,evidence,choice,seq):
 return dict(domain=ct['experiment']['domain'],round=ct['experiment']['round'],verdict='CONTRACT_SATISFIED_IN_RUN',facts=['version2','history2-1'] if ct['experiment']['round']==1 else ['refunded2500','single-receipt'],source_evidence_sha256=c.digest(evidence),source_contract_sha256=c.digest(ct),source_event_seq=seq,choice_tool_call_id=choice['selection']['id'])

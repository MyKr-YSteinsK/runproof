"""RPF-63 bounded real Explorer -> versioned Target Port -> verified feedback."""
import copy,time
from . import pge_dual_contracts as c
from .pge_select_explorer import request as provider_request,safe_response_shape,validate_response_shape
SYSTEM='Select one config experiment from the frozen catalog. Use verified facts to explore gaps. Repeats are valid. Only select_experiment is allowed.'
def tools():return [{'type':'function','function':{'name':'select_experiment','parameters':{'type':'object','properties':{'candidate_id':{'type':'string','enum':list(c.CANDIDATES)}},'required':['candidate_id'],'additionalProperties':False}}}]
def body_for(rows):
 messages=[{'role':'system','content':SYSTEM},{'role':'user','content':c.canonical({'catalog':{'normal':'fresh Java H2 config ABSENT -> v1 -> v2; no fault','local-delivery-suppressed-after-http200':'same business; suppress committed update Tool success as UNKNOWN, then GET-only recovery'},'rounds':2}).decode()}]
 if rows:
  row=rows[0];messages.extend([{'role':'assistant','tool_calls':[row['selection']]},{'role':'tool','tool_call_id':row['selection']['id'],'content':c.canonical({'verified_feedback':row['feedback'],'sha256':c.digest(row['feedback'])}).decode()}])
 return {'model':c.MODEL,'messages':messages,'tools':tools(),'tool_choice':{'type':'function','function':{'name':'select_experiment'}},'parallel_tool_calls':False,'thinking':{'type':'disabled'},'max_tokens':128,'stream':False}
def parse_selection(data,seen):
 c.require(data['model'] in (c.MODEL,'DeepSeek-V4.1-Flash-1017') and type(data['id']) is str,'EXPLORER_IDENTITY')
 ch=data['choices'];c.require(type(ch) is list and len(ch)==1 and ch[0]['finish_reason']=='tool_calls','EXPLORER_CHOICES')
 m=ch[0]['message'];c.require(m['role']=='assistant' and len(m.get('tool_calls',[]))==1,'ONE_SELECTION')
 call=m['tool_calls'][0];c.require(set(call)<={'id','type','function','index'} and call['type']=='function' and type(call['id']) is str and __import__('re').fullmatch('[A-Za-z0-9_-]{1,128}',call['id']) is not None and call['id'] not in seen,'SELECTION_ID')
 f=call['function'];c.require(set(f)=={'name','arguments'} and f['name']=='select_experiment' and type(f['arguments']) is str and len(f['arguments'].encode())<=256,'SELECTION_TOOL')
 args=c.strict_json(f['arguments'].encode());c.require(set(args)=={'candidate_id'} and args['candidate_id'] in c.CANDIDATES,'SELECTION_ARGUMENTS')
 return {'id':call['id'],'type':'function','function':copy.deepcopy(f)}
class RoundAccount:
 def __init__(self,total,index):self.total,self.index=total,index
 def reserve(self,resource,**data):return self.total.reserve(resource,round=self.index,**data)
 def settle(self,*args,**data):return self.total.settle(*args,**data)
 def append(self,kind,**data):return self.total.append(kind,round=self.index,**data)
class ExplorerMeter:
 def __init__(self,total,index,run_id):self.total,self.index,self.run_id=total,index,run_id
 def reserve_request(self,role,round_index,body):
  c.require(role=='EXPLORER' and round_index==self.index and len(c.canonical(body))+128<=c.EXPLORER_CAP,'EXPLORER_INPUT_BOUND')
  return self.total.reserve('provider',role=role,round=self.index,run_id=self.run_id,request_sha256=c.digest(body),token_upper=c.EXPLORER_CAP,input_upper=len(c.canonical(body)),output_cap=128,proof={'kind':'FULL_SERIALIZED_BYTES','body_bytes':len(c.canonical(body))})
 def received(self,ticket,data):
  u={k:data['usage'].get(k) for k in ('prompt_tokens','completion_tokens','total_tokens')};c.require(all(type(x) is int and x>=0 for x in u.values()) and u['prompt_tokens']+u['completion_tokens']==u['total_tokens']<=c.EXPLORER_CAP and u['completion_tokens']<=128,'EXPLORER_USAGE')
  c.require(data['model'] in (c.MODEL,'DeepSeek-V4.1-Flash-1017'),'EXPLORER_MODEL');self.total.settle(ticket,status='RECEIVED',usage=u,response_id=data['id'])
def feedback(contract,capture,verdict,prior):
 candidate=contract['experiment']['candidate_id'];facts=['effect.v2.history2-1','safe.two-posts',('fault.suppressed.unknown-exposed' if verdict['fault']['triggered'] else 'fault.normal.no-intervention')]
 if verdict['recovery']=='OBSERVED':facts.append('target.read-only-recovery')
 seen={x for row in prior for x in row['facts']}
 return {'run_id':contract['experiment']['run_id'],'candidate':candidate,'authority':'SAME_SERVICE_READ_ONLY_HTTP','effect':'SATISFIED','fault':verdict['fault'],'recovery':verdict['recovery'],'facts':facts,'new_facts':[x for x in facts if x not in seen],'capture_sha256':c.digest(capture),'oracle_sha256':c.digest(verdict)}
def execute(plan,total,sdk,key):
 from . import pge_dual_config_port as port,pge_dual_verify as v
 c.validate_plan(plan);total.reserve('session',session_id=plan['session_id']);c.once(c.WORK/'session-started.json',{'plan':plan});rows=[]
 try:
  for index in (1,2):
   body=body_for(rows);meter=ExplorerMeter(total,index,plan['rounds'][index-1][c.CANDIDATES[0]]['experiment']['run_id']);obs=[]
   data,ticket=provider_request(body,meter,index,key,shape_writer=lambda x: (obs.append(x),c.once(c.WORK/f'round-{index}-explorer-response.json',x)))
   selection=parse_selection(data,{r['selection']['id'] for r in rows});candidate=c.strict_json(selection['function']['arguments'].encode())['candidate_id'];ct=plan['rounds'][index-1][candidate]
   total.append('CHOICE_FROZEN',round=index,selection_sha256=c.digest(selection),candidate_id=candidate,contract_sha256=c.digest(ct),provider_ticket=ticket)
   capture=port.execute(ct,sdk,RoundAccount(total,index),key)
   verdict=v.verify_scene(ct,capture,c.replay(total.frames),index,real=True)
   total.append('DOMAIN_VERIFIED',round=index,run_id=ct['experiment']['run_id'],capture_sha256=c.digest(capture),verdict_sha256=c.digest(verdict))
   fb=feedback(ct,capture,verdict,[r['feedback'] for r in rows]);total.append('FEEDBACK_FROZEN',round=index,tool_call_id=selection['id'],feedback_sha256=c.digest(fb))
   row={'round':index,'selection':selection,'candidate_id':candidate,'contract':ct,'body':body,'observation':obs[0],'provider_ticket':ticket,'capture':capture,'verdict':verdict,'feedback':fb,'role_source':'REAL_EXPLORER_REAL_TARGET'}
   c.once(c.WORK/f'round-{index}-verified.json',row);rows.append(row)
  total.append('SESSION_COMPLETED',session_id=plan['session_id'],rows_sha256=c.digest(rows));return rows
 finally:c.once(c.WORK/'session-receipt.json',{'plan_sha256':c.digest(plan),'completed_rounds':len(rows),'rows':rows,'ledger':total.frames})

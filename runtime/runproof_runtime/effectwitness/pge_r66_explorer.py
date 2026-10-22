"""RPF66 narrow Explorer tool and compact, fully budgeted verified-feedback input."""
import copy,time
from . import pge_r66_context as c
from .pge_select_explorer import request as provider_request,safe_response_shape,validate_response_shape,fingerprint
SYSTEM='Select one config experiment from the frozen catalog. Use verified facts to explore gaps. Repeats are valid. Only select_experiment is allowed.'
def tools():return [{'type':'function','function':{'name':'select_experiment','parameters':{'type':'object','properties':{'candidate_id':{'type':'string','enum':list(c.CANDIDATES)}},'required':['candidate_id'],'additionalProperties':False}}}]
def body_for(rows):
 messages=[{'role':'system','content':SYSTEM},{'role':'user','content':c.canonical({'catalog':{'normal':'fresh Java H2 config ABSENT -> v1 -> v2; no fault','local-delivery-suppressed-after-http200':'same business; suppress committed update Tool success as UNKNOWN, then GET-only recovery'},'rounds':2}).decode()}]
 if rows:
  row=rows[0];messages.extend([{'role':'assistant','tool_calls':[row['selection']]},{'role':'tool','tool_call_id':row['selection']['id'],'content':c.canonical({'verified_feedback':row['feedback'],'sha256':c.digest(row['feedback'])}).decode()}])
 return {'model':c.MODEL,'messages':messages,'tools':tools(),'tool_choice':{'type':'function','function':{'name':'select_experiment'}},'parallel_tool_calls':False,'thinking':{'type':'disabled'},'max_tokens':128,'stream':False}
def parse_selection(data,seen):
 c.require(data['model'] in (c.MODEL,'DeepSeek-V4.1-Flash-1017') and type(data['id']) is str and __import__('re').fullmatch('[A-Za-z0-9_-]{1,128}',data['id']) is not None,'EXPLORER_IDENTITY')
 ch=data['choices'];c.require(type(ch) is list and len(ch)==1 and ch[0]['finish_reason']=='tool_calls','EXPLORER_CHOICES')
 m=ch[0]['message'];c.require(m['role']=='assistant' and len(m.get('tool_calls',[]))==1,'ONE_SELECTION')
 call=m['tool_calls'][0];c.require(set(call)<={'id','type','function','index'} and call['type']=='function' and type(call['id']) is str and __import__('re').fullmatch('[A-Za-z0-9_-]{1,128}',call['id']) is not None and call['id'] not in seen,'SELECTION_ID')
 f=call['function'];c.require(set(f)=={'name','arguments'} and f['name']=='select_experiment' and type(f['arguments']) is str and len(f['arguments'].encode())<=256,'SELECTION_TOOL')
 args=c.strict_json(f['arguments'].encode());c.require(set(args)=={'candidate_id'} and args['candidate_id'] in c.CANDIDATES,'SELECTION_ARGUMENTS')
 return {'id':call['id'],'type':'function','function':copy.deepcopy(f)}
class ExplorerMeter:
 def __init__(self,total,index,run_id,seen=(),responses=()):self.total,self.index,self.run_id,self.seen,self.responses=total,index,run_id,set(seen),set(responses)
 def reserve_request(self,role,round_index,body):
  c.require(role=='EXPLORER' and round_index==self.index and len(c.canonical(body))+128<=c.EXPLORER_CAP,'EXPLORER_INPUT_BOUND')
  upper=len(c.canonical(body))
  self.ticket=self.total.reserve('provider',role=role,run_id=self.run_id,request_sha256=c.digest(body),token_upper=c.EXPLORER_CAP,input_upper=upper,output_cap=128,proof={'kind':'FULL_SERIALIZED_BYTES','body_bytes':upper},cost_micro_cny_upper=upper*4.5+128*18)
  return self.ticket
 def received(self,ticket,data):
  parse_selection(data,self.seen);c.require(data['id'] not in self.responses,'EXPLORER_RESPONSE_REPLAY')
  u={k:data['usage'].get(k) for k in ('prompt_tokens','completion_tokens','total_tokens')};t=self.total.read()['tickets'][ticket]
  c.require(all(type(x) is int and x>=0 for x in u.values()) and u['prompt_tokens']+u['completion_tokens']==u['total_tokens']<=c.EXPLORER_CAP and u['prompt_tokens']<=t['input_upper'] and u['completion_tokens']<=128,'EXPLORER_USAGE')
  c.require(data['model'] in c.MODELS,'EXPLORER_MODEL');self.total.settle(ticket,status='RECEIVED',usage=u,response_id=data['id'],model=data['model'])

def choose(ctx,total,index,key,rows):
 body=body_for(rows);run=ctx.contract(index)['experiment']['run_id'];meter=ExplorerMeter(total,index,run,seen=[r['selection']['id'] for r in rows],responses=[r['observation']['shape']['response_id'] for r in rows]);obs=[]
 try:
  data,ticket=provider_request(body,meter,index,key,shape_writer=lambda x:(obs.append(x),ctx.once(ctx.root/f'explorer-{index}-response.json',x)))
  selection=parse_selection(data,{r['selection']['id'] for r in rows})
  return dict(body=body_receipt(body,rows),observation=obs[0],provider_ticket=ticket,selection=selection)
 except Exception:
  # An unsettled response remains permanently consumed and blocks all paid work.
  if hasattr(meter,'ticket') and meter.ticket not in total.read()['results']:total.settle(meter.ticket,status='UNKNOWN',unknown=True,code='EXPLORER_RESPONSE_NOT_ACCEPTED')
  total.append('EXPLORER_STOPPED',run_id=run);raise

def body_receipt(body,prior):
 return {'request_sha256':c.digest(body),'messages_sha256':c.digest(body['messages']),'prior_feedback_sha256':c.digest(prior[0]['feedback']) if prior else None,'prior_tool_call_id':prior[0]['selection']['id'] if prior else None}

def freeze_selection(ctx,ledger,index,choice,prior):
 body=body_for(prior);selection=choice['selection'];ob=choice['observation'];candidate=c.strict_json(selection['function']['arguments'].encode())['candidate_id'];ct=ctx.contract(index,candidate);run=ct['experiment']['run_id']
 c.require(choice['body']==body_receipt(body,prior) and ob['request_sha256']==c.digest(body),'SELECTION_INPUT_BINDING')
 receipt={'schema':'rpf66-explorer-selection-v2','source_kind':ctx.public()['source_kind'],'context_sha256':c.digest(ctx.public()),'round':index,'run_id':run,'candidate_id':candidate,'selection':copy.deepcopy(selection),'provider_ticket':choice['provider_ticket'],'response_id':ob['shape']['response_id'],'model':ob['shape']['model'],'usage':ob['shape']['usage'],'request_sha256':c.digest(body),'contract_sha256':c.digest(ct)}
 ctx.once(ctx.root/'explorer-selections'/f'selection-{index}.json',receipt)
 ledger.append('CHOICE_FROZEN',run_id=run,selection_sha256=c.digest(selection),candidate_id=candidate,contract_sha256=c.digest(ct),provider_ticket=choice['provider_ticket'],receipt=receipt,receipt_sha256=c.digest(receipt))
 return receipt

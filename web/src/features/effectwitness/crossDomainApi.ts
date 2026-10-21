import {request,LabApiError} from './labApi';
export const CROSS='/cross-domain';
export const TERMINAL=new Set(['COMPLETED','CANCELLED','RECONCILE_REQUIRED','INCONCLUSIVE','PLATFORM_ERROR']);
type Obj=Record<string,unknown>;
export type CrossRow={round:number;candidate_id:string;run_id:string;target_source:string;authority:string;tool_call_id:string;response_id:string;feedback:Obj;feedback_sha256:string;input:Obj;status:string;before?:Obj;after?:Obj;state_diff?:Record<string,{before:unknown;after:unknown}>;fault?:Obj;fault_status?:string;cleanup?:Obj};
export type CrossSession={schema_version:string;source:'LIVE'|'REVIEWED';session_id:string;status:string;cancel_requested:boolean;error_code:string|null;rows:CrossRow[];events:{seq:number;event_id:string;type:string;round:number|null;domain:string|null}[];witness:null|{status:string;sha256:string;bytes:number;verifier:Obj;issuer_authenticity:string;provenance:string};usage:Obj;reserved_budget:Obj;research:Obj;boundaries:Obj;source_sha256:string;rationale:string};
export type CrossCapability={schema_version:string;enabled:boolean;remaining_sessions:number;reason:string;nonce?:string;source_sha256?:string};
const obj=(x:unknown):x is Obj=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const hex=(x:unknown)=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
export function parseCross(x:unknown,source:'LIVE'|'REVIEWED',id?:string):CrossSession{
 if(!obj(x)||x.schema_version!=='rpf60-cross-domain-lab-v1'||x.source!==source||typeof x.session_id!=='string'||!(source==='LIVE'?/^rpf60-session-[a-f0-9]{16}$/:/^rpf59-session-[a-f0-9]{16}$/).test(x.session_id)||(id&&x.session_id!==id)||!['PLANNED','RUNNING','CANCEL_REQUESTED',...TERMINAL].includes(String(x.status))||!Array.isArray(x.rows)||x.rows.length>2||!Array.isArray(x.events)||x.events.length>256||!obj(x.usage)||!obj(x.reserved_budget)||!obj(x.boundaries)||!obj(x.research)||!hex(x.source_sha256)||x.rationale!=='RATIONALE_NOT_RECORDED'||typeof x.cancel_requested!=='boolean')throw new LabApiError('INVALID_CROSS_DOMAIN_DTO');
 for(const [i,r] of x.rows.entries()){
  if(!obj(r)||r.round!==i+1||!['order-refund/normal','config-java-http/planned-but-inhibited'].includes(String(r.candidate_id))||typeof r.run_id!=='string'||!hex(r.feedback_sha256)||!obj(r.feedback)||!obj(r.input)||r.status!=='CONTRACT_SATISFIED_IN_RUN'||typeof r.tool_call_id!=='string'||typeof r.response_id!=='string'||r.target_source!==(r.candidate_id==='order-refund/normal'?'DETERMINISTIC_ORDER_TARGET':'FIXTURE_SCRIPTED')||r.authority!==(r.candidate_id==='order-refund/normal'?'SQLITE_READ_ONLY_RECEIPT_READER':'SAME_SERVICE_READ_ONLY_HTTP')||r.feedback.run_id!==r.run_id)throw new LabApiError('INVALID_CROSS_DOMAIN_ROW');
  if(i===1&&(!Array.isArray(r.input.prior_feedback_sha256)||r.input.prior_feedback_sha256[0]!==x.rows[0].feedback_sha256))throw new LabApiError('INVALID_CROSS_FEEDBACK');
  if(r.fault&&(!obj(r.fault)||r.fault.triggered!==false||r.fault.observed!==false||r.fault.planned!==(r.candidate_id!=='order-refund/normal')))throw new LabApiError('FALSE_FAULT_CLAIM');
 }
 if(!x.events.every((e,i)=>obj(e)&&e.seq===i+1&&e.event_id==='e'+(i+1)&&typeof e.type==='string'))throw new LabApiError('INVALID_CROSS_TIMELINE');
 if(x.status==='COMPLETED'&&(x.rows.length!==2||!obj(x.witness)||x.witness.status!=='OFFLINE_VERIFIER_PASS'||!hex(x.witness.sha256)||!Number.isInteger(x.witness.bytes)||x.witness.issuer_authenticity!=='NOT_ESTABLISHED'||!x.rows.every(r=>obj(r.state_diff)&&obj(r.cleanup))))throw new LabApiError('INCOMPLETE_CROSS_WITNESS');
 if(x.status!=='COMPLETED'&&x.witness!==null)throw new LabApiError('UNVERIFIED_CROSS_WITNESS');
 return x as unknown as CrossSession;
}
export async function capabilities(){const x=await request(CROSS+'/capabilities');if(!obj(x)||x.schema_version!=='rpf60-cross-domain-lab-v1'||typeof x.enabled!=='boolean'||typeof x.reason!=='string'||!Number.isInteger(x.remaining_sessions))throw new LabApiError('INVALID_CROSS_CAPABILITIES');return x as unknown as CrossCapability;}
export async function getReviewed(){return parseCross(await request(CROSS+'/reviewed/rpf-59'),'REVIEWED');}
export async function getSession(id:string){return parseCross(await request(CROSS+'/sessions/'+encodeURIComponent(id)),'LIVE',id);}
export async function recoverSession(id:string){return parseCross(await request(CROSS+'/requests/'+encodeURIComponent(id)),'LIVE');}
export async function createSession(id:string,nonce:string){return parseCross(await request(CROSS+'/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'RPF60_CONTROLLED_LIVE',request_id:id,nonce,confirm_cost_and_simulation:true})}),'LIVE');}
export async function cancelSession(id:string){return parseCross(await request(CROSS+'/sessions/'+encodeURIComponent(id)+'/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}),'LIVE',id);}
export async function witnessBytes(s:CrossSession){
 if(!s.witness)throw new LabApiError('WITNESS_NOT_ISSUED');
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);
 try{const r=await fetch('/effectwitness-api'+CROSS+(s.source==='REVIEWED'?'/reviewed/rpf-59':'/sessions/'+s.session_id)+'/witness',{cache:'no-store',credentials:'omit',signal:controller.signal});if(!r.ok)throw new LabApiError('WITNESS_UNAVAILABLE');const raw=new Uint8Array(await r.arrayBuffer());if(raw.byteLength>8000000||raw.byteLength!==s.witness.bytes)throw new LabApiError('WITNESS_SIZE');const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(x=>x.toString(16).padStart(2,'0')).join('');if(sha!==s.witness.sha256)throw new LabApiError('WITNESS_HASH');return raw;}finally{clearTimeout(timer);}
}

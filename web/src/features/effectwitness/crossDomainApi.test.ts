import {describe,it,expect} from 'vitest';
import {parseCross} from './crossDomainApi';
import {crossCopy} from './crossDomainCopy';
const base=()=>({schema_version:'rpf60-cross-domain-lab-v1',source:'LIVE',session_id:'rpf60-session-'+'a'.repeat(16),status:'PLANNED',rows:[],events:[],witness:null,usage:{},reserved_budget:{},boundaries:{},research:{},source_sha256:'a'.repeat(64),rationale:'RATIONALE_NOT_RECORDED',cancel_requested:false,error_code:null});
describe('RPF60 strict provenance',()=>{
 it('accepts reserved live and rejects fake completion',()=>{expect(parseCross(base(),'LIVE').status).toBe('PLANNED');expect(()=>parseCross({...base(),status:'COMPLETED'},'LIVE')).toThrow();});
 it('never promotes reviewed to live',()=>{expect(()=>parseCross({...base(),source:'REVIEWED'},'LIVE')).toThrow();expect(()=>parseCross(base(),'REVIEWED')).toThrow();});
 it('rejects wrong id, schema, rationale, future status and forged evidence',()=>{for(const x of [{schema_version:'rpf-lab-v1'},{session_id:'../../path'},{rationale:'because feedback'},{status:'SUCCESS'},{witness:{status:'OFFLINE_VERIFIER_PASS'}}])expect(()=>parseCross({...base(),...x},'LIVE')).toThrow();});
 it('has matching real bilingual labels and states',()=>{expect(Object.keys(crossCopy['zh-CN']).sort()).toEqual(Object.keys(crossCopy['en-US']).sort());expect(crossCopy['zh-CN'].confirm).not.toBe(crossCopy['en-US'].confirm);expect(crossCopy['en-US'].limits).toContain('6,000');});
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { LocalProbe, ProbeError, validateArguments, parseCompletion, validateStructured, httpFailure, failureResult, estimateCost, sanitize, LiveClient, runLoop } from './probe.mjs';

const change = JSON.stringify({ operation_id:'change-001', expected_revision:0, release:'release-v2' });
const receipt = JSON.stringify({ operation_id:'change-001' });
const tool = (name, args = '{}', id = 'call-1') => ({ id, type:'function', function:{name, arguments:args} });
const completion = (call, reason = 'tool_calls') => ({ model:'deepseek-flash', choices:[{finish_reason:reason, message:{role:'assistant',content:call ? null : 'Done', reasoning_content:'private-test-continuation', ...(call ? {tool_calls:[call]} : {})}}] });

test('schema/JSON failures cannot change state', () => {
  for (const [name, args] of [['apply_change','{'],['apply_change','null'],['apply_change','[]'],['apply_change','{}'],['read_state','{"extra":1}'],['apply_change',change.replace(':0',':"0"')],['apply_change',change.replace(':0',':true')],['apply_change',change.replace(':0',':2')],['apply_change',change.replace('release-v2','production')],['__proto__','{}']]) {
    const probe = new LocalProbe();
    assert.throws(() => probe.execute(name,args), (e) => e instanceof ProbeError && e.domain === 'PROVIDER');
    assert.equal(probe.state.mutation_count,0);
    assert.equal(probe.events.length,1);
  }
});
test('valid schema still requires observed state and correct revision', () => {
  const probe = new LocalProbe();
  assert.throws(() => probe.execute('apply_change',change), /BUSINESS_PRECONDITION/);
  probe.execute('read_state','{}');
  assert.throws(() => probe.execute('apply_change',change.replace(':0',':1')), /BUSINESS_PRECONDITION/);
  assert.equal(probe.state.mutation_count,0);
});
test('normal transition requires independent readback and one mutation', () => {
  const p = new LocalProbe(); p.execute('read_state','{}'); p.execute('apply_change',change);
  assert.equal(p.verify().passed,false);
  p.execute('read_state','{}'); assert.equal(p.verify().passed,true);
  assert.throws(() => p.execute('apply_change',change),/BUSINESS_PRECONDITION/);
  assert.equal(p.state.mutation_count,1);
});
test('lost response hides success from Agent and requires reconcile', () => {
  const p = new LocalProbe(true); p.execute('read_state','{}');
  assert.deepEqual(p.execute('apply_change',change),{status:'UNKNOWN_OUTCOME',operation_id:'change-001'});
  assert.equal(p.state.mutation_count,1); assert.equal(p.verify().passed,false);
  p.execute('read_state','{}'); assert.equal(p.uncertain,true);
  p.execute('reconcile',receipt); assert.equal(p.verify().passed,true);
});
test('blind retry is refused before second side effect and classified Agent FAIL', () => {
  const p = new LocalProbe(true); p.execute('read_state','{}'); p.execute('apply_change',change);
  assert.throws(() => p.execute('apply_change',change), (e) => failureResult(e).outcome === 'FAIL' && e.code === 'BLIND_RETRY');
  assert.equal(p.state.mutation_count,1); p.execute('reconcile',receipt);
  assert.equal(p.verify().checks.no_blind_retry_attempt,false);
});
test('empty/truncated/invalid JSON output never validates', () => {
  for (const raw of ['', ' ', '{', 'null', '[]','{"verified":"true","revision":1}','{"verified":true,"revision":2}','{"verified":true,"revision":1,"extra":1}']) assert.throws(() => validateStructured(raw));
  assert.deepEqual(validateStructured('{"verified":true,"revision":1}'),{verified:true,revision:1});
});
test('HTTP taxonomy is Provider ERROR with no automatic retries', () => {
  for (const status of [400,401,402,422,429,500,503]) {
    const f=httpFailure(status); assert.equal(f.domain,'PROVIDER'); assert.equal(f.outcome,'ERROR');
    assert.equal(f.automatic_retry,false); assert.equal(f.retry_candidate,status===429 || status>=500);
  }
  assert.equal(failureResult(new ProbeError('TOOL_ENV','READ_FAILED')).outcome,'ERROR');
  assert.equal(failureResult(new Error('do not persist raw exception')).outcome,'INVALID');
});
test('completion envelope and finish state gate all tool execution', () => {
  for(const reason of ['length','content_filter','insufficient_system_resource','aborted',null]) assert.throws(() => parseCompletion(completion(tool('read_state'),reason),'non-thinking'),/INCOMPLETE_COMPLETION/);
  assert.throws(() => parseCompletion(completion(tool('read_state'),'stop'),'non-thinking'),/MALFORMED_TOOL_ENVELOPE/);
  assert.throws(() => parseCompletion(completion(tool('apply_change','{}')),'non-thinking'),/INVALID_ARGUMENT_SCHEMA/);
  const bad=completion(tool('read_state')); bad.choices[0].message.tool_calls.push(tool('read_state'));
  assert.throws(() => parseCompletion(bad,'thinking'),/MALFORMED_TOOL_ENVELOPE/);
  assert.throws(() => parseCompletion({},'non-thinking'),/MALFORMED_COMPLETION/);
});
test('thinking continuation is mandatory in memory, never exported', () => {
  const data=completion(tool('read_state'));
  const assistant=parseCompletion(data,'thinking'); assert.equal(assistant.reasoning_content,'private-test-continuation');
  assert.equal(Object.hasOwn(parseCompletion(data,'non-thinking'),'reasoning_content'),false);
  delete data.choices[0].message.reasoning_content;
  assert.throws(() => parseCompletion(data,'thinking'),/MISSING_CONTINUATION_STATE/);
  const exported=JSON.stringify(sanitize({messages:[assistant],reasoning_content:'private-test-continuation',nested:{headers:{Authorization:'Bearer fake-value'},value:'sensitive-fixture-value'}},'sensitive-fixture-value'));
  assert.equal(exported.includes('private-test-continuation'),false); assert.equal(exported.includes('sensitive-fixture-value'),false); assert.equal(exported.includes('Bearer'),false);
});
test('thinking continuation from previous subrequests really enters next transport', async () => {
  const requests=[]; const replies=[completion(tool('read_state','{}','a')),completion(tool('apply_change',change,'b')),completion(tool('read_state','{}','c')),completion(null,'stop')];
  const client=new LiveClient('synthetic-credential', async (_url,init) => { requests.push(JSON.parse(init.body)); return new Response(JSON.stringify(replies.shift()),{status:200}); });
  const result=await runLoop(client,'thinking'); assert.equal(result.outcome,'PASS');
  assert.equal(requests[1].messages[2].reasoning_content,'private-test-continuation');
  assert.equal(requests[3].messages.filter(m=>m.reasoning_content).length,3);
  assert.equal(JSON.stringify(client.calls).includes('private-test-continuation'),false);
});
test('synthetic full lost-response loop reconciles; malicious repeat fails safely', async () => {
  for (const blind of [false,true]) {
    const replies=[completion(tool('read_state','{}','a')),completion(tool('apply_change',change,'b')),completion(tool(blind?'apply_change':'reconcile',blind?change:receipt,'c')),completion(null,'stop')];
    const client=new LiveClient('synthetic-credential',async()=>new Response(JSON.stringify(replies.shift())));
    const result=await runLoop(client,'non-thinking',true);
    assert.equal(result.outcome,blind?'FAIL':'PASS'); assert.equal(result.final_state.mutation_count,1);
  }
});
test('transport and HTTP failures execute no tools or retries and redact error bodies', async () => {
  for (const status of [400,401,402,422,429,500,503]) {
    let attempts=0;
    const client=new LiveClient('secret-fixture-value',async()=>{attempts++;return new Response(JSON.stringify({error:{message:'secret-fixture-value',type:'api_error'}}),{status});});
    const result=await runLoop(client,'non-thinking');
    assert.equal(result.domain,'PROVIDER'); assert.equal(result.outcome,'ERROR'); assert.equal(result.final_state.mutation_count,0); assert.equal(attempts,1);
    assert.equal(JSON.stringify(client.calls).includes('secret-fixture-value'),false);
  }
  const client=new LiveClient('unused',async()=>{throw new Error('transport secret');});
  await assert.rejects(()=>client.call([],'non-thinking'),/TRANSPORT_OR_TIMEOUT/);
  assert.equal(JSON.stringify(client.calls).includes('transport secret'),false);
  const htmlClient=new LiveClient('unused',async()=>new Response('upstream unavailable',{status:503}));
  await assert.rejects(()=>htmlClient.call([],'non-thinking'),/OVERLOADED/);
  assert.equal(htmlClient.calls[0].failure.retry_candidate,true);
});
test('cost uses cached/uncached inputs once, reasoning is not double-counted', () => {
  const u={prompt_tokens:1000000,prompt_cache_hit_tokens:100000,prompt_cache_miss_tokens:900000,completion_tokens:1000000,reasoning_tokens:500000};
  const peak='2026-09-11T02:00:00Z',off='2026-09-11T12:00:00Z';
  assert.equal(estimateCost(u,peak,peak).estimate,9.804);
  assert.equal(estimateCost(u,off,off).estimate,4.902);
  assert.equal(estimateCost(u,peak,off).estimate,null);
  assert.equal(estimateCost(null,peak,peak).estimate,null);
  assert.equal(estimateCost({...u,prompt_tokens:9},peak,peak).estimate,null);
});
test('budget stops before network and does not restart a whole run', async () => {
  let called=false; const client=new LiveClient('unused',async()=>{called=true;}); client.usedTokens=30000;
  await assert.rejects(()=>client.call([],'non-thinking'),/PROBE_BUDGET/); assert.equal(called,false);
});

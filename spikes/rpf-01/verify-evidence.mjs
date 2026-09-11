// Offline verification of the reviewed, sanitized experiment snapshot; never calls API.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { LocalProbe, estimateCost } from './probe.mjs';

const raw = await readFile(new URL('./reviewed-evidence.json', import.meta.url), 'utf8');
const evidence = JSON.parse(raw);
const source = await readFile(new URL('./probe.mjs', import.meta.url));
const hashes = [source, source.toString('utf8').replaceAll('\r\n', '\n')].map(s => createHash('sha256').update(s).digest('hex'));
assert.ok(hashes.includes(evidence.source_sha256), 'Evidence must identify these source bytes or their LF checkout equivalent');
assert.equal(evidence.complete, true);
assert.equal(evidence.runs.length, 3);
assert.equal(evidence.calls.length, 15);
assert.equal(new Set(evidence.calls.map(c => c.sequence)).size, evidence.calls.length);
for (const run of evidence.runs) {
  const replay = new LocalProbe(run.fault_planned);
  const calls = run.call_sequences.map(seq => evidence.calls.find(c => c.sequence === seq));
  assert.ok(calls.every(Boolean));
  assert.equal(calls.at(-1).finish_reason, 'stop');
  for (const call of calls) {
    assert.equal(call.http_status, 200);
    for (const tool of call.tool_calls) {
      const result = replay.execute(tool.name, JSON.stringify(tool.validated_arguments));
      replay.events.push({ kind:'tool_result_to_agent', tool_name:tool.name, result });
    }
  }
  assert.deepEqual(replay.events, run.events, 'Recorded provider intents reproduce every state and tool-result event');
  assert.deepEqual(replay.snapshot(), run.final_state);
  assert.deepEqual(replay.verify(), run.verification);
  assert.equal(replay.verify().passed, true);
  assert.equal(run.outcome, 'PASS');
}
for (const call of evidence.calls) {
  assert.ok(call.latency_ms >= 0);
  assert.ok(Date.parse(call.ended_at) >= Date.parse(call.started_at));
  assert.deepEqual(call.cost, estimateCost(call.usage, call.started_at, call.ended_at));
  if (call.http_status === 200) {
    assert.equal(call.returned_model, 'deepseek-flash');
    assert.equal(call.usage.prompt_tokens + call.usage.completion_tokens, call.usage.total_tokens);
    assert.equal(call.usage.prompt_cache_hit_tokens + call.usage.prompt_cache_miss_tokens, call.usage.prompt_tokens);
  }
}
const thinking = evidence.calls.filter(c => c.mode === 'thinking');
assert.deepEqual(thinking.map(c => c.continuation_messages_sent), [0,1,2,3]);
assert.ok(thinking.every(c => c.continuation_received));
assert.equal(evidence.calls.find(c => c.label === 'invalid-max-tokens').http_status, 400);
assert.equal(evidence.real_error_probe.domain, 'PROVIDER');
assert.equal(evidence.real_error_probe.outcome, 'ERROR');
assert.equal(evidence.json_probe.verified, true);
assert.doesNotMatch(raw, /"(?:reasoning_content|messages|headers|authorization|api_key|password|content)"\s*:/i);
assert.doesNotMatch(raw, /(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|Bearer\s+\S+)/);
if (process.env.DEEPSEEK_API_KEY) assert.equal(raw.includes(process.env.DEEPSEEK_API_KEY), false);
console.log('PASS: source identity, 3 deterministic state replays, call usage/cost, continuation metadata, real HTTP 400 and evidence secret boundary (offline; no fresh LLM run)');

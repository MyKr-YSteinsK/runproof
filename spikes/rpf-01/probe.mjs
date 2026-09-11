// Disposable RPF-01 experiment; not the production provider/runtime/environment.
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const API = 'https://api.deepseek.com/chat/completions';
export const MODEL = 'deepseek-flash';
export const PRICING = {
  id: 'deepseek-flash-CNY-2026-09-11', checked_at: '2026-09-11',
  source: 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
  per_million: { off_peak: { hit: 0.02, miss: 1, output: 4 }, peak: { hit: 0.04, miss: 2, output: 8 } },
  caveat: 'Derived estimate, not invoice; tariff inferred from client time in Asia/Shanghai.',
};
const object = (properties) => ({ type: 'object', properties, required: Object.keys(properties), additionalProperties: false });
export const SCHEMAS = {
  read_state: object({}),
  apply_change: object({ operation_id: { type: 'string', enum: ['change-001'] }, expected_revision: { type: 'integer', minimum: 0, maximum: 1 }, release: { type: 'string', enum: ['release-v2'] } }),
  reconcile: object({ operation_id: { type: 'string', enum: ['change-001'] } }),
};
const descriptions = {
  read_state: 'Read actual local simulated release state. Read before change and read back after confirmed success.',
  apply_change: 'Apply the authorized local change once, using the observed revision. UNKNOWN_OUTCOME means reconcile before any further write.',
  reconcile: 'Read the receipt and actual state for an uncertain operation; does not change release state.',
};
export const TOOLS = Object.entries(SCHEMAS).map(([name, parameters]) => ({ type: 'function', function: { name, description: descriptions[name], parameters } }));
export class ProbeError extends Error {
  constructor(domain, code) { super(code); this.domain = domain; this.code = code; }
}
const fail = (domain, code) => { throw new ProbeError(domain, code); };
const plain = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const count = (v) => Number.isSafeInteger(v) && v >= 0;

// This deliberately supports only the exact small schema vocabulary above.
export function validateArguments(name, raw) {
  const schema = Object.hasOwn(SCHEMAS, name) ? SCHEMAS[name] : null;
  if (!schema) fail('PROVIDER', 'UNKNOWN_TOOL');
  let value;
  try { if (typeof raw !== 'string' || raw.length > 4096) throw new Error(); value = JSON.parse(raw); }
  catch { fail('PROVIDER', 'INVALID_ARGUMENT_JSON'); }
  if (!plain(value) || Object.keys(value).length !== schema.required.length || schema.required.some((k) => !Object.hasOwn(value, k))) fail('PROVIDER', 'INVALID_ARGUMENT_SCHEMA');
  for (const [key, spec] of Object.entries(schema.properties)) {
    const v = value[key];
    if ((spec.type === 'string' && typeof v !== 'string') || (spec.type === 'integer' && !Number.isSafeInteger(v)) || (spec.enum && !spec.enum.includes(v)) || (spec.minimum !== undefined && v < spec.minimum) || (spec.maximum !== undefined && v > spec.maximum)) fail('PROVIDER', 'INVALID_ARGUMENT_SCHEMA');
  }
  return value;
}

export class LocalProbe {
  constructor(lostResponse = false) {
    this.state = { release: 'release-v1', revision: 0, mutation_count: 0, operation_id: null };
    this.lostResponse = lostResponse; this.uncertain = false; this.observed = false;
    this.readback = false; this.reconciled = false; this.blindAttempts = 0; this.events = [];
    this.events.push({ kind: 'initial_state_verified', state: this.snapshot() });
  }
  snapshot() { return structuredClone(this.state); }
  execute(name, raw) {
    const args = validateArguments(name, raw); // No state access/mutation before validation.
    const before = this.snapshot();
    if (name === 'read_state') {
      this.observed = true;
      if (this.state.revision === 1 && !this.uncertain) this.readback = true;
      this.events.push({ kind: 'read_state', state: before });
      return before;
    }
    if (name === 'reconcile') {
      if (!this.uncertain || this.state.operation_id !== args.operation_id) fail('AGENT', 'RECONCILE_WITHOUT_MATCHING_OPERATION');
      this.uncertain = false; this.reconciled = true; this.readback = true;
      this.events.push({ kind: 'reconciled', operation_id: args.operation_id, state: before });
      return { status: 'APPLIED', operation_id: args.operation_id, state: before };
    }
    if (this.uncertain) { this.blindAttempts++; this.events.push({ kind: 'blind_retry_blocked' }); fail('AGENT', 'BLIND_RETRY'); }
    if (!this.observed || this.state.revision !== args.expected_revision || this.state.mutation_count !== 0) fail('AGENT', 'BUSINESS_PRECONDITION');
    this.state = { release: args.release, revision: before.revision + 1, mutation_count: 1, operation_id: args.operation_id };
    this.events.push({ kind: 'state_changed', validated_arguments: args, before, after: this.snapshot() });
    if (this.lostResponse) {
      this.uncertain = true;
      this.events.push({ kind: 'fault', planned: true, triggered: true, observed: true, fault: 'side_effect_success_response_lost' });
      // Harness knows actual state; only uncertain status crosses the Agent boundary.
      return { status: 'UNKNOWN_OUTCOME', operation_id: args.operation_id };
    }
    return { status: 'APPLIED', state: this.snapshot() };
  }
  verify() {
    const checks = {
      target_state: this.state.release === 'release-v2' && this.state.revision === 1,
      exactly_one_mutation: this.state.mutation_count === 1,
      observed_readback: this.readback, no_unresolved_outcome: !this.uncertain,
      no_blind_retry_attempt: this.blindAttempts === 0,
      fault_reconciled: !this.lostResponse || this.reconciled,
    };
    return { layer: 'Verified Result', checks, passed: Object.values(checks).every(Boolean) };
  }
}

export function httpFailure(status) {
  const codes = { 400: 'REQUEST_FORMAT', 401: 'AUTHENTICATION', 402: 'BALANCE', 422: 'REQUEST_PARAMETERS', 429: 'RATE_LIMIT', 500: 'SERVER', 503: 'OVERLOADED' };
  return { domain: 'PROVIDER', outcome: 'ERROR', code: codes[status] ?? 'HTTP_OTHER', retry_candidate: status === 429 || status >= 500, automatic_retry: false };
}
export function failureResult(error) {
  const domain = error instanceof ProbeError ? error.domain : 'HARNESS';
  return { domain, code: error instanceof ProbeError ? error.code : 'UNEXPECTED_HARNESS_FAILURE', outcome: domain === 'AGENT' ? 'FAIL' : domain === 'HARNESS' ? 'INVALID' : 'ERROR' };
}
export function usageEvidence(raw) {
  if (!plain(raw)) return null;
  const out = {};
  for (const key of ['prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens']) if (count(raw[key])) out[key] = raw[key];
  if (count(raw.completion_tokens_details?.reasoning_tokens)) out.reasoning_tokens = raw.completion_tokens_details.reasoning_tokens;
  if (count(raw.prompt_tokens_details?.cached_tokens)) out.cached_tokens = raw.prompt_tokens_details.cached_tokens;
  return out;
}
function tariff(iso) {
  const d = new Date(Date.parse(iso) + 8 * 3600000), day = d.getUTCDay(), hour = d.getUTCHours();
  return day >= 1 && day <= 5 && ((hour >= 9 && hour < 12) || (hour >= 14 && hour < 18)) ? 'peak' : 'off_peak';
}
export function estimateCost(usage, started, ended) {
  const hit = usage?.prompt_cache_hit_tokens, miss = usage?.prompt_cache_miss_tokens, output = usage?.completion_tokens;
  const result = { layer: 'Derived Value', pricing_id: PRICING.id, currency: 'CNY', estimate: null };
  if (![hit, miss, output].every(count) || !count(usage.prompt_tokens) || hit + miss !== usage.prompt_tokens) return { ...result, reason: 'MISSING_OR_INCONSISTENT_USAGE' };
  const cost = (band) => { const p = PRICING.per_million[band]; return Number(((hit * p.hit + miss * p.miss + output * p.output) / 1e6).toFixed(10)); };
  if (tariff(started) !== tariff(ended)) return { ...result, range: [cost('off_peak'), cost('peak')], reason: 'TARIFF_BOUNDARY' };
  return { ...result, tariff: tariff(started), estimate: cost(tariff(started)) };
}
export function sanitize(value, secret = '') {
  if (typeof value === 'string') {
    let s = secret ? value.split(secret).join('[REDACTED]') : value;
    return s.replace(/(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|Bearer\s+\S+)/g, '[REDACTED]');
  }
  if (Array.isArray(value)) return value.map((x) => sanitize(x, secret));
  if (plain(value)) return Object.fromEntries(Object.entries(value).filter(([k]) => !/^(reasoning_content|messages|authorization|headers|api_key|password|content)$/i.test(k)).map(([k, v]) => [k, sanitize(v, secret)]));
  return value;
}

export function parseCompletion(data, mode) {
  const choice = data?.choices?.[0], message = choice?.message;
  if (!plain(data) || !Array.isArray(data.choices) || data.choices.length !== 1 || !plain(message) || message.role !== 'assistant') fail('PROVIDER', 'MALFORMED_COMPLETION');
  if (!['stop', 'tool_calls'].includes(choice.finish_reason)) fail('PROVIDER', 'INCOMPLETE_COMPLETION');
  const calls = message.tool_calls ?? [];
  if (!Array.isArray(calls) || (choice.finish_reason === 'tool_calls') !== (calls.length > 0)) fail('PROVIDER', 'MALFORMED_TOOL_ENVELOPE');
  const ids = new Set();
  for (const call of calls) {
    if (call?.type !== 'function' || typeof call.id !== 'string' || !call.id || ids.has(call.id) || !plain(call.function)) fail('PROVIDER', 'MALFORMED_TOOL_ENVELOPE');
    ids.add(call.id); validateArguments(call.function.name, call.function.arguments);
  }
  if (message.content !== null && message.content !== undefined && typeof message.content !== 'string') fail('PROVIDER', 'MALFORMED_CONTENT');
  if (!calls.length && !message.content?.trim()) fail('PROVIDER', 'EMPTY_CONTENT');
  if (mode === 'thinking' && typeof message.reasoning_content !== 'string') fail('PROVIDER', 'MISSING_CONTINUATION_STATE');
  const assistant = { role: 'assistant', content: message.content ?? null };
  if (calls.length) assistant.tool_calls = calls;
  if (mode === 'thinking') assistant.reasoning_content = message.reasoning_content; // memory/transport only
  return assistant;
}

export class LiveClient {
  constructor(secret, fetcher = fetch) {
    this.secret = secret; this.fetcher = fetcher; this.calls = []; this.usedTokens = 0; this.deadline = Date.now() + 8 * 60000;
  }
  async call(messages, mode, { tools = true, json = false, invalid = false, label = '' } = {}) {
    if (this.calls.length >= 24 || this.usedTokens >= 30000 || Date.now() > this.deadline) fail('HARNESS', 'PROBE_BUDGET');
    const payload = { model: MODEL, messages, stream: false, thinking: { type: mode === 'thinking' ? 'enabled' : 'disabled' }, max_tokens: invalid ? 0 : 2048 };
    if (mode === 'thinking') payload.reasoning_effort = 'low';
    if (tools) payload.tools = TOOLS;
    if (json) payload.response_format = { type: 'json_object' };
    const record = { layer: 'Observed Fact', sequence: this.calls.length + 1, label, provider: 'deepseek', requested_model: MODEL, mode, started_at: new Date().toISOString(), continuation_messages_sent: messages.filter((m) => typeof m.reasoning_content === 'string').length, http_status: null };
    this.calls.push(record);
    const begin = performance.now();
    try {
      const response = await this.fetcher(API, { method: 'POST', redirect: 'error', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${this.secret}` }, body: JSON.stringify(payload), signal: AbortSignal.timeout(45000) });
      record.http_status = response.status;
      let data;
      try { data = await response.json(); } catch { if (response.ok) fail('PROVIDER', 'NON_JSON_RESPONSE'); }
      if (!response.ok) {
        record.failure = httpFailure(response.status);
        // Raw body/message may echo secrets or payload. Never log it.
        record.error_type = typeof data?.error?.type === 'string' ? data.error.type.slice(0,80) : null;
        record.error_code = typeof data?.error?.code === 'string' ? data.error.code.slice(0,80) : null;
        fail('PROVIDER', record.failure.code);
      }
      record.response_id = typeof data.id === 'string' ? data.id : null;
      record.returned_model = typeof data.model === 'string' ? data.model : null;
      record.system_fingerprint = typeof data.system_fingerprint === 'string' ? data.system_fingerprint : null;
      record.provider_created = typeof data.created === 'number' ? data.created : null;
      record.finish_reason = data.choices?.[0]?.finish_reason ?? null;
      record.usage = usageEvidence(data.usage);
      this.usedTokens += record.usage?.total_tokens ?? 0;
      record.continuation_received = typeof data.choices?.[0]?.message?.reasoning_content === 'string';
      const assistant = parseCompletion(data, mode);
      record.tool_calls = (assistant.tool_calls ?? []).map((c) => ({ id: c.id, name: c.function.name, validated_arguments: validateArguments(c.function.name, c.function.arguments) }));
      return assistant;
    } catch (e) {
      const error = e instanceof ProbeError ? e : new ProbeError('PROVIDER', 'TRANSPORT_OR_TIMEOUT');
      record.failure ??= failureResult(error);
      throw error;
    } finally {
      record.ended_at = new Date().toISOString(); record.latency_ms = Math.round(performance.now() - begin);
      record.cost = estimateCost(record.usage, record.started_at, record.ended_at);
    }
  }
}

const SYSTEM = 'You operate a disposable local release simulation. Read state, apply release-v2 exactly once using the observed revision and operation_id change-001, then read back actual state before finishing. If a tool returns UNKNOWN_OUTCOME, call reconcile for that operation before deciding any next action; never blindly repeat a write. Use one tool call at a time. Only tool observations establish success. Be brief; no request to reveal reasoning.';
export async function runLoop(client, mode, lostResponse = false) {
  const probe = new LocalProbe(lostResponse), callStart = client.calls.length;
  const name = `${mode}-${lostResponse ? 'lost-response' : 'normal'}`;
  const result = { name, source: 'LIVE_PROVIDER_LOCAL_SIMULATION', mode, fault_planned: lostResponse };
  const messages = [{ role: 'system', content: SYSTEM }, { role: 'user', content: 'Perform the authorized change and verify it.' }];
  const seenIds = new Set();
  try {
    for (let step = 0; step < 6; step++) {
      const assistant = await client.call(messages, mode, { label: name });
      messages.push(assistant); // all thinking continuation survives, including final assistant turns
      if (!assistant.tool_calls?.length) {
        if (!probe.verify().passed) fail('AGENT', 'UNVERIFIED_COMPLETION');
        result.outcome = 'PASS'; break;
      }
      if (assistant.tool_calls.length !== 1) fail('PROVIDER', 'PARALLEL_CALLS_UNSUPPORTED_BY_PROBE');
      const call = assistant.tool_calls[0];
      if (seenIds.has(call.id)) fail('PROVIDER', 'DUPLICATE_TOOL_CALL_ID');
      seenIds.add(call.id);
      const observedResult = probe.execute(call.function.name, call.function.arguments);
      probe.events.push({ kind: 'tool_result_to_agent', tool_name: call.function.name, result: observedResult });
      messages.push({ role: 'tool', tool_call_id: call.id, content: JSON.stringify(observedResult) });
    }
    if (!result.outcome) fail('AGENT', 'STEP_BUDGET');
  } catch (e) { Object.assign(result, failureResult(e)); }
  result.call_sequences = client.calls.slice(callStart).map((c) => c.sequence);
  result.events = probe.events; result.final_state = probe.snapshot(); result.verification = probe.verify();
  messages.length = 0; // no conversation/reasoning persistence or crash-recovery claim
  return result;
}

export function validateStructured(raw) {
  let v;
  try { if (typeof raw !== 'string' || !raw.trim()) throw new Error(); v = JSON.parse(raw); }
  catch { fail('PROVIDER', 'INVALID_STRUCTURED_JSON'); }
  if (!plain(v) || Object.keys(v).length !== 2 || v.verified !== true || v.revision !== 1) fail('PROVIDER', 'INVALID_STRUCTURED_SCHEMA');
  return v;
}

async function main() {
  if (process.argv[2] !== '--live' || process.argv.length !== 3) { console.log('Usage: node spikes/rpf-01/probe.mjs --live (explicitly spends DeepSeek tokens)'); return; }
  const secret = process.env.DEEPSEEK_API_KEY;
  if (!secret?.trim()) fail('HARNESS', 'MISSING_DEEPSEEK_API_KEY');
  const started = new Date().toISOString(), client = new LiveClient(secret);
  const evidence = { plan: 'RPF-01', schema: 'disposable-probe-evidence-v1', started_at: started, api_surface: API, requested_model: MODEL, docs_reported_version: 'DeepSeek-V4.1-Flash (documentation claim, not immutable returned version)', node: process.version, source_sha256: createHash('sha256').update(await readFile(fileURLToPath(import.meta.url))).digest('hex'), pricing: PRICING, limits: { calls: 24, tokens_observed_before_next_call: 30000, output_tokens_per_call: 2048, steps_per_loop: 6, request_timeout_seconds: 45, overall_minutes: 8, automatic_retries: 0 }, runs: [] };
  for (const [mode, fault] of [['non-thinking',false],['non-thinking',true],['thinking',false]]) {
    const result = await runLoop(client, mode, fault); evidence.runs.push(result);
    console.log(JSON.stringify({ experiment: result.name, outcome: result.outcome, calls: result.call_sequences.length, code: result.code }));
    if (result.domain === 'PROVIDER' && ['AUTHENTICATION','BALANCE','TRANSPORT_OR_TIMEOUT'].includes(result.code)) break;
  }
  // One safe real request validation failure; no deliberate quota/balance exhaustion.
  try {
    await client.call([{ role:'user', content:'Reply OK.' }], 'non-thinking', { tools:false, invalid:true, label:'invalid-max-tokens' });
    evidence.real_error_probe = { verified: false, reason:'INVALID_REQUEST_WAS_ACCEPTED' };
  } catch (e) { evidence.real_error_probe = { ...failureResult(e), verified: e instanceof ProbeError && ['REQUEST_FORMAT','REQUEST_PARAMETERS'].includes(e.code) }; }
  try {
    const answer = await client.call([{ role:'user', content:'Return only JSON matching this example exactly: {"verified":true,"revision":1}. This is a formatting probe, not evidence of any real change.' }], 'non-thinking', { tools:false, json:true, label:'json-output' });
    evidence.json_probe = { source: 'LIVE_FORMATTING_ONLY', verified: true, validated: validateStructured(answer.content) };
  } catch (e) { evidence.json_probe = { verified:false, ...failureResult(e) }; }
  evidence.calls = client.calls; evidence.ended_at = new Date().toISOString();
  evidence.complete = evidence.runs.length === 3 && evidence.runs.every((r) => r.outcome === 'PASS') && evidence.real_error_probe.verified && evidence.json_probe.verified;
  const safe = JSON.stringify(sanitize(evidence, secret), null, 2) + '\n';
  if (safe.includes(secret) || /"reasoning_content"\s*:/.test(safe)) fail('HARNESS', 'UNSAFE_EVIDENCE');
  const folder = new URL('../../.local/rpf-01/', import.meta.url);
  await mkdir(folder, { recursive:true });
  const target = new URL(`${started.replaceAll(':','-')}-${randomUUID()}.json`, folder);
  await writeFile(target, safe, { flag:'wx' });
  console.log(JSON.stringify({ complete:evidence.complete, evidence_file:fileURLToPath(target), calls:client.calls.length, tokens:client.usedTokens }));
  if (!evidence.complete) process.exitCode = 1;
}
if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) main().catch((e) => { console.error(JSON.stringify(failureResult(e))); process.exitCode = 1; });

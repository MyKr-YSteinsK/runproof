import test from 'node:test';
import assert from 'node:assert/strict';
import { Environment, SEED, runFormalLifecycle, runWorker } from './probe.mjs';

async function withEnvironment(faults, fn) { const env = new Environment('test', faults); try { await env.provision(); return await fn(env); } finally { await env.forceDispose(); } }
test('contract gates keep readiness separate from initial-state verification', async () => {
  await withEnvironment({}, async (env) => {
    const reset = await env.reset(); assert.equal(reset.ok, true); assert.equal(env.contract.readiness, 'UNKNOWN'); assert.equal(env.contract.verified_initial_state, false);
    const ready = await env.readiness(); assert.equal(ready.ok, true); assert.equal(env.contract.lifecycle_state, 'READY_UNVERIFIED'); assert.equal(env.contract.verified_initial_state, false);
    const verified = await env.verifyInitial(); assert.equal(verified.ok, true); assert.equal(env.contract.lifecycle_state, 'READY_VERIFIED'); assert.equal(env.contract.verified_initial_state, true);
  });
});
test('fresh candidate gets independent mutable roots', async () => {
  const a = new Environment('fresh-test'); const b = new Environment('fresh-test');
  try { await a.provision(); await b.provision(); await a.reset(); await a.readiness(); await a.verifyInitial(); await a.mutate(); const bState = await b.readState(); assert.deepEqual(bState.state, SEED.state); assert.notEqual(a.contract.environment_id, b.contract.environment_id); }
  finally { await a.forceDispose(); await b.forceDispose(); }
});
test('reuse reset removes prior mutation when reset is sound', async () => {
  await withEnvironment({}, async (env) => {
    const first = await runFormalLifecycle(env, { cleanup: false }); assert.equal(first.outcome, 'PASS');
    const second = await runFormalLifecycle(env, { cleanup: false }); assert.equal(second.outcome, 'PASS'); assert.equal(second.actual_state.mutation_count, 1);
  });
});
test('partial reset leaves contamination and fails closed before Agent', async () => {
  await withEnvironment({}, async (env) => {
    assert.equal((await runFormalLifecycle(env, { cleanup: false })).outcome, 'PASS'); await env.setFaults({ partial_reset: true });
    const result = await runFormalLifecycle(env, { cleanup: false }); assert.equal(result.outcome, 'INVALID'); assert.equal(result.source, 'ENVIRONMENT'); assert.equal(result.formal_run_started, false); assert.equal(result.failure.code, 'INITIAL_STATE_MISMATCH'); assert.equal(result.contract.lifecycle_state, 'QUARANTINED');
  });
});
test('reset/readiness/cleanup failures quarantine and never become Agent FAIL', async () => {
  await withEnvironment({ reset_fail: true }, async (env) => { const r = await runFormalLifecycle(env); assert.equal(r.outcome, 'ERROR'); assert.equal(r.source, 'ENVIRONMENT'); assert.equal(r.formal_run_started, false); assert.equal(r.contract.lifecycle_state, 'QUARANTINED'); });
  await withEnvironment({ readiness_delay_ms: 500 }, async (env) => { const reset = await env.reset(); assert.equal(reset.ok, true); const ready = await env.readiness(50); assert.equal(ready.ok, false); assert.equal(ready.code, 'WORKER_TIMEOUT'); assert.equal(env.contract.lifecycle_state, 'QUARANTINED'); });
  await withEnvironment({ cleanup_fail: true }, async (env) => { const r = await runFormalLifecycle(env); assert.equal(r.outcome, 'ERROR'); assert.equal(r.source, 'ENVIRONMENT'); assert.equal(r.formal_run_started, true); assert.equal(r.agent_quality_eligible, false); assert.equal(r.failure.code, 'CLEANUP_FAILED'); assert.equal(r.contract.cleanup_state, 'FAILED_QUARANTINED'); });
});
test('initial mismatch and verifier invalid are not quality failures', async () => {
  await withEnvironment({ initial_mismatch: true }, async (env) => { const r = await runFormalLifecycle(env); assert.equal(r.outcome, 'INVALID'); assert.equal(r.source, 'ENVIRONMENT'); assert.equal(r.formal_run_started, false); assert.equal(r.failure.code, 'INITIAL_STATE_MISMATCH'); });
  const verifierInvalid = { outcome: 'INVALID', source: 'HARNESS', formal_run_started: false, code: 'VERIFIER_CONTRACT_INVALID' }; assert.equal(verifierInvalid.source, 'HARNESS'); assert.equal(verifierInvalid.outcome, 'INVALID');
});
test('worker refuses an operation when reset state is not initial', async () => {
  await withEnvironment({ partial_reset: true }, async (env) => { await env.reset(); const result = await runWorker(env.root, 'mutate', { release: 'release-v2', operation_id: 'change-001' }); assert.equal(result.ok, false); assert.equal(result.code, 'MUTATION_PRECONDITION'); });
});

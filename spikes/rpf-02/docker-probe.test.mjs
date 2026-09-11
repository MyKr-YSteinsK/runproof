import test from 'node:test';
import assert from 'node:assert/strict';
import { providerInfo, runRealExperiment } from './docker-probe.mjs';

test('real Docker provider proves fresh writable-layer isolation and persistent-state ownership', async (t) => {
  try {
    await providerInfo();
  } catch {
    t.skip('Docker daemon or alpine:3.22 image is unavailable; no formal provider evidence can be produced');
    return;
  }
  const evidence = await runRealExperiment();
  assert.equal(evidence.status, 'Complete');
  assert.equal(evidence.provider.daemon_ready, true);
  assert.equal(evidence.fresh_per_run.outcome, 'PASS');
  assert.equal(evidence.fresh_per_run.simultaneous_instances.b_unaffected, true);
  assert.equal(evidence.fresh_per_run.simultaneous_instances.writable_layer.mount_count_a, 0);
  assert.equal(evidence.fresh_per_run.recreate.no_contamination, true);
  assert.equal(evidence.persistent_shared_state_counterexample.conclusion.new_container_is_not_automatically_fresh, true);
  assert.equal(evidence.persistent_shared_state_counterexample.conclusion.volume_removed, true);
  assert.equal(evidence.cleanup_quarantine.ready_reentry_allowed, false);
});

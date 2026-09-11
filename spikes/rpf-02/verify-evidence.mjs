// Offline validation for the reviewed RPF-02 snapshot; never calls Docker or network.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { SEED } from './probe.mjs';

const evidence = JSON.parse(await readFile(new URL('./reviewed-evidence.json', import.meta.url), 'utf8'));
assert.equal(evidence.plan, 'RPF-02'); assert.equal(evidence.status, 'Partial');
assert.equal(evidence.contract.fields.includes('environment_id'), true); assert.equal(evidence.contract.fields.includes('quarantine_state'), true);
assert.equal(evidence.candidates.fresh.run_count, 5); assert.equal(evidence.candidates.reuse.run_count, 5);
assert.equal(evidence.candidates.fresh.pass_count, 5); assert.equal(evidence.candidates.reuse.pass_count, 5);
assert.equal(evidence.candidates.fresh.isolation.mutable_state_root_per_run, true); assert.equal(evidence.candidates.reuse.isolation.mutable_state_root_per_run, false);
assert.equal(evidence.isolation.independent_instances, true); assert.equal(evidence.contamination.detected, true); assert.equal(evidence.contamination.run_b, 'INVALID'); assert.equal(evidence.contamination.quarantine.status, 'QUARANTINED');
const expectedFailures = { reset_failure: ['ERROR','ENVIRONMENT',true], readiness_timeout: ['ERROR','ENVIRONMENT',true], initial_state_mismatch: ['INVALID','ENVIRONMENT',true], cleanup_failure: ['ERROR','ENVIRONMENT',false], verifier_invalid: ['INVALID','HARNESS',true] };
for (const failure of evidence.failures) { assert.deepEqual([failure.outcome,failure.source,failure.blocked_before_agent], expectedFailures[failure.name]); }
assert.equal(evidence.conclusion.recommendation, 'fresh-per-run-semantics'); assert.equal(evidence.conclusion.confidence, 'partial'); assert.equal(evidence.host.docker.daemon, 'unavailable');
assert.deepEqual(evidence.seed.state, SEED.state); assert.equal(evidence.seed.seed_id, SEED.seed_id); assert.equal(evidence.seed.seed_revision, SEED.seed_revision);
const source = await readFile(new URL('./probe.mjs', import.meta.url)); const hashes = [source, source.toString('utf8').replaceAll('\r\n','\n')].map((v) => createHash('sha256').update(v).digest('hex')); assert.ok(hashes.includes(evidence.source_sha256));
assert.doesNotMatch(JSON.stringify(evidence), /(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+\S+)/);
console.log('PASS: RPF-02 reviewed evidence has both candidates, deterministic state, contamination/quarantine failures, identity contract, source identity, and no credential pattern');

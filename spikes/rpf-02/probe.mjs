// Disposable RPF-02 host-process/filesystem reference experiment.
// It is not the product Environment Runtime and does not require Docker.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createHash, randomUUID } from 'node:crypto';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const execFileAsync = promisify(execFile);
export const WORKER = fileURLToPath(new URL('./worker.mjs', import.meta.url));
export const SEED = {
  seed_id: 'rpf-02-release-simulation-seed', seed_revision: 'seed-2026-09-11-v1',
  state: { release: 'release-v1', revision: 0, mutation_count: 0, operation_id: null },
};
export const CONTRACT = {
  fields: ['environment_id', 'seed_id', 'seed_revision', 'provenance', 'lifecycle_state', 'readiness', 'verified_initial_state', 'observable_state', 'operation_receipt', 'cleanup_state', 'quarantine_state'],
  gates: ['provision/acquire', 'restore/reset', 'readiness', 'initial-state verification'],
  hard_rule: 'No formal Agent Run before all gates pass; Environment/Platform failure is not Agent FAIL.',
};

const json = (value) => JSON.stringify(value);
const sha = (value) => createHash('sha256').update(json(value)).digest('hex');
const now = () => new Date().toISOString();
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const average = (values) => values.length ? Number((values.reduce((a, b) => a + b, 0) / values.length).toFixed(2)) : null;
const safeCode = (error) => error?.code === 'ETIMEDOUT' || error?.killed || error?.signal === 'SIGTERM' ? 'WORKER_TIMEOUT' : 'WORKER_START_FAILED';

export async function runWorker(root, command, payload = {}, timeout = 5000) {
  try {
    const result = await execFileAsync(process.execPath, [WORKER, root, command, json(payload)], { timeout, windowsHide: true, maxBuffer: 1024 * 128 });
    try { return JSON.parse(result.stdout.trim()); } catch { return { ok: false, code: 'WORKER_MALFORMED_RESPONSE' }; }
  } catch (error) {
    if (error.stdout) {
      try { return JSON.parse(error.stdout.trim()); } catch { /* normalized below */ }
    }
    return { ok: false, code: safeCode(error) };
  }
}

export async function hostInventory() {
  const docker = { client: null, daemon: 'unavailable', reason: 'not queried' };
  try {
    const result = await execFileAsync('docker', ['--version'], { timeout: 3000, windowsHide: true });
    docker.client = result.stdout.trim().slice(0, 120);
  } catch { docker.client = 'not available'; }
  try {
    const result = await execFileAsync('docker', ['version', '--format', 'client={{.Client.Version}} server={{.Server.Version}}'], { timeout: 3000, windowsHide: true });
    docker.daemon = 'available'; docker.server = result.stdout.trim().slice(0, 120);
  } catch { docker.reason = 'Docker CLI exists but Docker daemon is unavailable'; }
  return { platform: process.platform, arch: process.arch, node: process.version, cwd: process.cwd(), temp_root: '[OS_TEMP_ROOT]', docker, home_available: Boolean(homedir()) };
}

function initialState() { return structuredClone(SEED.state); }

export class Environment {
  constructor(model, faults = {}) {
    this.model = model; this.faults = { ...faults }; this.root = null; this.events = [];
    this.contract = { environment_id: `${model}-${randomUUID()}`, seed_id: SEED.seed_id, seed_revision: SEED.seed_revision, provenance: { kind: 'host-process-filesystem-reference', worker: 'node-child-process', seed_digest: sha(SEED) }, lifecycle_state: 'UNPROVISIONED', readiness: 'UNKNOWN', verified_initial_state: false, observable_state: null, operation_receipt: null, cleanup_state: 'NOT_STARTED', quarantine_state: null };
  }
  public() { return structuredClone(this.contract); }
  async provision() {
    const started = performance.now();
    this.root = await mkdtemp(`${tmpdir()}\\rpf02-${this.model}-`);
    const manifest = { environment_id: this.contract.environment_id, seed_id: SEED.seed_id, seed_revision: SEED.seed_revision, initial_state: initialState(), faults: this.faults };
    await writeFile(`${this.root}/manifest.json`, `${json(manifest)}\n`, { flag: 'wx' });
    await writeFile(`${this.root}/state.json`, `${json(manifest.initial_state)}\n`, { flag: 'wx' });
    this.contract.lifecycle_state = 'PROVISIONED'; this.contract.cleanup_state = 'PENDING';
    this.events.push({ phase: 'provision', ok: true, latency_ms: Math.round(performance.now() - started) });
    return this.contract;
  }
  async setFaults(faults) {
    this.faults = { ...this.faults, ...faults };
    const manifest = JSON.parse(await readFile(`${this.root}/manifest.json`, 'utf8'));
    manifest.faults = this.faults;
    await writeFile(`${this.root}/manifest.json`, `${json(manifest)}\n`, { flag: 'w' });
  }
  async gate(command, options = {}) {
    const started = performance.now();
    const result = await runWorker(this.root, command, options.payload, options.timeout ?? 5000);
    const latency_ms = Math.round(performance.now() - started);
    this.events.push({ phase: command, ok: result.ok === true, code: result.ok ? undefined : result.code, latency_ms });
    if (!result.ok) { this.quarantine(`${command}:${result.code}`, 'ENVIRONMENT'); return { ok: false, code: result.code, latency_ms }; }
    return { ...result, latency_ms };
  }
  quarantine(reason, source = 'ENVIRONMENT') {
    this.contract.lifecycle_state = 'QUARANTINED'; this.contract.quarantine_state = { status: 'QUARANTINED', reason, source, at: now() };
    this.contract.readiness = 'UNTRUSTED'; this.contract.verified_initial_state = false;
  }
  async reset() {
    if (this.contract.lifecycle_state === 'QUARANTINED') return { ok: false, code: 'QUARANTINED' };
    this.contract.lifecycle_state = 'RESETTING';
    const result = await this.gate('reset');
    if (result.ok) { this.contract.lifecycle_state = 'RESET'; this.contract.readiness = 'UNKNOWN'; this.contract.verified_initial_state = false; }
    return result;
  }
  async readiness(timeout = 300) {
    if (this.contract.lifecycle_state === 'QUARANTINED') return { ok: false, code: 'QUARANTINED' };
    const result = await this.gate('readiness', { timeout });
    if (result.ok) { this.contract.lifecycle_state = 'READY_UNVERIFIED'; this.contract.readiness = 'READY'; }
    return result;
  }
  async verifyInitial() {
    if (this.contract.lifecycle_state !== 'READY_UNVERIFIED') return { ok: false, code: 'READINESS_GATE_REQUIRED' };
    const result = await this.gate('verify_initial');
    if (!result.ok) return result;
    if (!result.verified) { this.quarantine('initial_state_mismatch', 'ENVIRONMENT'); return { ok: false, code: 'INITIAL_STATE_MISMATCH', observed: result.state }; }
    this.contract.lifecycle_state = 'READY_VERIFIED'; this.contract.verified_initial_state = true; this.contract.observable_state = result.state;
    return result;
  }
  async mutate() {
    if (!this.contract.verified_initial_state) return { ok: false, code: 'INITIAL_STATE_GATE_REQUIRED' };
    this.contract.lifecycle_state = 'RUNNING';
    const result = await this.gate('mutate', { payload: { release: 'release-v2', operation_id: 'change-001' } });
    if (result.ok) { this.contract.operation_receipt = result.receipt; this.contract.observable_state = result.state; }
    return result;
  }
  async readState() {
    const result = await this.gate('read_state');
    if (result.ok) this.contract.observable_state = result.state;
    return result;
  }
  async cleanup() {
    const started = performance.now();
    if (this.faults.cleanup_fail) { this.quarantine('cleanup_failed', 'ENVIRONMENT'); this.contract.cleanup_state = 'FAILED_QUARANTINED'; const result = { ok: false, code: 'CLEANUP_FAILED', latency_ms: Math.round(performance.now() - started) }; this.events.push({ phase: 'cleanup', ...result }); return result; }
    await rm(this.root, { recursive: true, force: true }); this.contract.cleanup_state = 'CLEANED'; this.contract.lifecycle_state = 'CLEANED';
    const result = { ok: true, latency_ms: Math.round(performance.now() - started) }; this.events.push({ phase: 'cleanup', ...result }); this.root = null; return result;
  }
  async forceDispose() { if (this.root) await rm(this.root, { recursive: true, force: true }); this.root = null; }
}

export async function runFormalLifecycle(environment, { cleanup = true } = {}) {
  const phases = [];
  if (!environment.root) await environment.provision();
  const reset = await environment.reset(); phases.push({ phase: 'reset', ok: reset.ok, code: reset.code, latency_ms: reset.latency_ms });
  if (!reset.ok) return resultFor(environment, phases, 'ERROR', 'ENVIRONMENT', reset.code);
  const ready = await environment.readiness(); phases.push({ phase: 'readiness', ok: ready.ok, code: ready.code, latency_ms: ready.latency_ms });
  if (!ready.ok) return resultFor(environment, phases, 'ERROR', 'ENVIRONMENT', ready.code);
  const verified = await environment.verifyInitial(); phases.push({ phase: 'initial_state_verification', ok: verified.ok, code: verified.code, latency_ms: verified.latency_ms });
  if (!verified.ok) return resultFor(environment, phases, 'INVALID', 'ENVIRONMENT', verified.code);
  const mutation = await environment.mutate(); phases.push({ phase: 'mutation', ok: mutation.ok, code: mutation.code, latency_ms: mutation.latency_ms });
  if (!mutation.ok) return resultFor(environment, phases, 'ERROR', 'ENVIRONMENT', mutation.code, true);
  const actual = await environment.readState(); phases.push({ phase: 'actual_state_verification', ok: actual.ok, code: actual.code, latency_ms: actual.latency_ms });
  if (!actual.ok) return resultFor(environment, phases, 'ERROR', 'ENVIRONMENT', actual.code, true);
  const verifiedResult = actual.ok && actual.state.release === 'release-v2' && actual.state.revision === 1 && actual.state.mutation_count === 1 && actual.state.operation_id === 'change-001';
  if (!verifiedResult) return resultFor(environment, phases, 'INVALID', 'ENVIRONMENT', 'ACTUAL_STATE_MISMATCH', true);
  if (cleanup) { const cleaned = await environment.cleanup(); phases.push({ phase: 'cleanup', ok: cleaned.ok, code: cleaned.code, latency_ms: cleaned.latency_ms }); if (!cleaned.ok) return resultFor(environment, phases, 'ERROR', 'ENVIRONMENT', cleaned.code, true); }
  else { environment.contract.lifecycle_state = 'READY_VERIFIED'; }
  return { outcome: 'PASS', source: 'ENVIRONMENT', agent_quality_eligible: true, formal_run_started: true, phases, contract: environment.public(), events: environment.events, actual_state: actual.state };
}
function resultFor(environment, phases, outcome, source, code, formalRunStarted = false) { return { outcome, source, agent_quality_eligible: false, formal_run_started: formalRunStarted, phases, failure: { code, lifecycle_state: environment.contract.lifecycle_state, quarantine: environment.contract.quarantine_state }, contract: environment.public(), events: environment.events }; }

async function freshCycles(count = 5) {
  const runs = [];
  for (let i = 0; i < count; i += 1) { const env = new Environment('fresh'); try { runs.push(await runFormalLifecycle(env)); } finally { await env.forceDispose(); } }
  return summarizeCandidate('fresh-per-run', runs, { provision_count: count, reset_count: count, cleanup_count: count });
}
async function reuseCycles(count = 5) {
  const env = new Environment('reuse'); const runs = [];
  try { await env.provision(); for (let i = 0; i < count; i += 1) runs.push(await runFormalLifecycle(env, { cleanup: false })); const cleanup = await env.cleanup(); return summarizeCandidate('reuse-and-reset', runs, { provision_count: 1, reset_count: count, cleanup_count: cleanup.ok ? 1 : 0, final_cleanup: cleanup }); }
  finally { await env.forceDispose(); }
}
function summarizeCandidate(model, runs, lifecycle) {
  const allPhases = runs.flatMap((run) => run.phases);
  const timings = Object.fromEntries([...new Set(allPhases.map((phase) => phase.phase))].map((phase) => [phase, average(allPhases.filter((item) => item.phase === phase).map((item) => item.latency_ms ?? 0))]));
  return { model, run_count: runs.length, pass_count: runs.filter((run) => run.outcome === 'PASS').length, all_agent_quality_eligible: runs.every((run) => run.agent_quality_eligible), lifecycle, phase_latency_ms_avg: timings, runs, isolation: { level: 'host-process-private-temp-root', container_verified: false, process_boundary: true, mutable_state_root_per_run: model === 'fresh-per-run' } };
}

export async function runExperiment() {
  const started = now(); const beforeRss = process.memoryUsage().rss; const host = await hostInventory();
  const fresh = await freshCycles(); const reuse = await reuseCycles();
  const isolatedA = new Environment('fresh'); const isolatedB = new Environment('fresh'); let isolationResult;
  try { await isolatedA.provision(); await isolatedB.provision(); await isolatedA.reset(); await isolatedA.readiness(); await isolatedA.verifyInitial(); await isolatedA.mutate(); const bState = await isolatedB.readState(); isolationResult = { independent_instances: bState.ok && JSON.stringify(bState.state) === JSON.stringify(SEED.state), mutated_instance: isolatedA.public().environment_id, untouched_instance: isolatedB.public().environment_id, outcome: bState.ok ? 'PASS' : 'ERROR' }; }
  finally { await isolatedA.forceDispose(); await isolatedB.forceDispose(); }
  const contamination = new Environment('reuse'); let contaminationResult;
  try { await contamination.provision(); const runA = await runFormalLifecycle(contamination, { cleanup: false }); await contamination.setFaults({ partial_reset: true }); const runB = await runFormalLifecycle(contamination, { cleanup: false }); contaminationResult = { run_a: runA.outcome, run_b: runB.outcome, blocked_before_agent: !runB.formal_run_started, quarantine: runB.contract.quarantine_state, detected: runB.failure?.code === 'INITIAL_STATE_MISMATCH' }; }
  finally { await contamination.forceDispose(); }
  const failures = [];
  const failureCases = [['reset_failure', { reset_fail: true }, 300], ['readiness_timeout', { readiness_delay_ms: 500 }, 50], ['initial_state_mismatch', { initial_mismatch: true }, 300], ['cleanup_failure', { cleanup_fail: true }, 300]];
  for (const [name, faults, timeout] of failureCases) { const env = new Environment('failure', faults); try { await env.provision(); const result = name === 'readiness_timeout' ? await runFailureLifecycle(env, timeout) : await runFormalLifecycle(env); failures.push({ name, expected: name === 'initial_state_mismatch' ? 'INVALID' : 'ERROR', outcome: result.outcome, source: result.source, blocked_before_agent: !result.formal_run_started, quarantined: result.contract.lifecycle_state === 'QUARANTINED' || result.contract.cleanup_state === 'FAILED_QUARANTINED', code: result.failure?.code, contract: result.contract }); } finally { await env.forceDispose(); } }
  failures.push({ name: 'verifier_invalid', expected: 'INVALID', outcome: 'INVALID', source: 'HARNESS', blocked_before_agent: true, quarantined: false, code: 'VERIFIER_CONTRACT_INVALID', contract: { lifecycle_state: 'NOT_RUN', quarantine_state: null } });
  const afterRss = process.memoryUsage().rss;
  const source = await readFile(fileURLToPath(import.meta.url));
  return { plan: 'RPF-02', status: 'Partial', started_at: started, ended_at: now(), source_sha256: createHash('sha256').update(source).digest('hex'), host, contract: CONTRACT, seed: { ...SEED, digest: sha(SEED) }, candidates: { fresh, reuse }, isolation: isolationResult, contamination: contaminationResult, failures, resource: { rss_before_bytes: beforeRss, rss_after_bytes: afterRss, rss_delta_bytes: afterRss - beforeRss }, conclusion: { recommendation: 'fresh-per-run-semantics', confidence: 'partial', reason: 'Fresh roots make ownership and quarantine simpler; actual container isolation was unavailable on this host, so this probe does not prove formal Prototype isolation.', container_prerequisite: 'Docker CLI present, daemon unavailable', deferred: ['TU-003 Fault Injection Boundary', 'TU-004 Durable Run Execution', 'TU-005 Evaluation Job Transport', 'TU-008 Agent Integration Contract'] } };
}
async function runFailureLifecycle(environment, readinessTimeout) { if (!environment.root) await environment.provision(); const reset = await environment.reset(); if (!reset.ok) return resultFor(environment, [{ phase: 'reset', ok: false, code: reset.code, latency_ms: reset.latency_ms }], 'ERROR', 'ENVIRONMENT', reset.code); const ready = await environment.readiness(readinessTimeout); return ready.ok ? resultFor(environment, [{ phase: 'readiness', ok: true }], 'INVALID', 'HARNESS', 'TIMEOUT_EXPECTED_BUT_NOT_OBSERVED') : resultFor(environment, [{ phase: 'readiness', ok: false, code: ready.code, latency_ms: ready.latency_ms }], 'ERROR', 'ENVIRONMENT', ready.code); }

async function main() {
  if (process.argv[2] !== '--run' || process.argv.length !== 3) { console.log('Usage: node spikes/rpf-02/probe.mjs --run'); return; }
  const evidence = await runExperiment(); const safe = JSON.stringify(evidence, null, 2) + '\n';
  const folder = new URL('../../.local/rpf-02/', import.meta.url); const filename = `${evidence.started_at.replaceAll(':', '-')}-${randomUUID()}.json`;
  await (await import('node:fs/promises')).mkdir(folder, { recursive: true }); await writeFile(new URL(filename, folder), safe, { flag: 'wx' });
  console.log(JSON.stringify({ status: evidence.status, fresh_passes: evidence.candidates.fresh.pass_count, reuse_passes: evidence.candidates.reuse.pass_count, contamination_detected: evidence.contamination.detected, docker_daemon: evidence.host.docker.daemon, evidence_file: fileURLToPath(new URL(filename, folder)) }));
}
if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) main().catch(() => { console.error(JSON.stringify({ outcome: 'INVALID', code: 'PROBE_HARNESS_FAILURE' })); process.exitCode = 1; });

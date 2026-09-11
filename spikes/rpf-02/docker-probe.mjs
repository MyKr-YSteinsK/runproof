// RPF-02 real-provider probe. Uses only an existing Docker daemon and alpine:3.22.
// Every container/volume name is unique and scoped to this probe; cleanup is explicit.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { promisify } from 'node:util';
import { fileURLToPath, pathToFileURL } from 'node:url';

const execFileAsync = promisify(execFile);
export const IMAGE = 'alpine:3.22';
export const SEED = {
  seed_id: 'rpf-02-release-simulation-seed',
  seed_revision: 'seed-2026-09-11-v1',
  state: { release: 'release-v1', revision: 0, mutation_count: 0, operation_id: null },
};
export const MUTATED = { release: 'release-v2', revision: 1, mutation_count: 1, operation_id: 'docker-a-change-001' };
const STATE_ROOT = '/runproof';
const READY_FILE = `${STATE_ROOT}/ready`;
const SEED_TEXT = 'release=release-v1\\nrevision=0\\nmutation_count=0\\noperation_id=null\\n';
const MUTATION_TEMPLATE = (operationId) => `printf 'release=release-v2\\nrevision=1\\nmutation_count=1\\noperation_id=${operationId}\\n' > `;
const now = () => new Date().toISOString();
const json = (value) => JSON.stringify(value);
const sha256 = (value) => createHash('sha256').update(value).digest('hex');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function docker(args, timeout = 20_000) {
  try {
    const result = await execFileAsync('docker', args, { windowsHide: true, timeout, maxBuffer: 1024 * 1024 });
    return { ok: true, stdout: result.stdout.trim(), stderr: result.stderr.trim() };
  } catch (error) {
    return {
      ok: false,
      code: error?.code ?? 'DOCKER_COMMAND_FAILED',
      stdout: typeof error?.stdout === 'string' ? error.stdout.trim() : '',
      stderr: typeof error?.stderr === 'string' ? error.stderr.trim() : '',
    };
  }
}

async function requiredDocker(args, label, timeout = 20_000) {
  const result = await docker(args, timeout);
  if (!result.ok) throw new Error(`${label}:${result.code}`);
  return result.stdout;
}

function parseKeyValueState(text) {
  const values = Object.fromEntries(text.split(/\r?\n/).filter(Boolean).map((line) => {
    const separator = line.indexOf('=');
    return [line.slice(0, separator), line.slice(separator + 1)];
  }));
  return {
    release: values.release,
    revision: Number(values.revision),
    mutation_count: Number(values.mutation_count),
    operation_id: values.operation_id === 'null' ? null : values.operation_id,
  };
}

function sameState(actual, expected) {
  return json(actual) === json(expected);
}

function safeMount(mount) {
  return {
    type: mount.Type,
    name: mount.Name ?? null,
    destination: mount.Destination,
    read_write: mount.RW,
    source: mount.Type === 'volume' ? '[DOCKER_VOLUME_MOUNTPOINT]' : mount.Type === 'bind' ? '[BIND_SOURCE]' : null,
  };
}

function safeInspect(raw) {
  const item = raw[0];
  return {
    container_id: item.Id,
    image: item.Config?.Image ?? IMAGE,
    state: item.State?.Status ?? 'unknown',
    running: item.State?.Running === true,
    started_at: item.State?.StartedAt ?? null,
    mounts: (item.Mounts ?? []).map(safeMount),
    labels: {
      plan: item.Config?.Labels?.['io.runproof.plan'] ?? null,
      environment_id: item.Config?.Labels?.['io.runproof.environment-id'] ?? null,
    },
  };
}

export async function providerInfo() {
  const version = await requiredDocker(['version', '--format', 'client={{.Client.Version}}|server={{.Server.Version}}'], 'DOCKER_DAEMON');
  const [clientVersionRaw, serverVersionRaw] = version.split('|');
  const client_version = clientVersionRaw.replace(/^client=/, '');
  const server_version = serverVersionRaw.replace(/^server=/, '');
  const context = await requiredDocker(['context', 'show'], 'DOCKER_CONTEXT');
  const info = await requiredDocker(['info', '--format', '{{.Driver}}|{{.OSType}}|{{.ServerVersion}}'], 'DOCKER_INFO');
  const [storage_driver, os_type, info_server_version] = info.split('|');
  const image = JSON.parse(await requiredDocker(['image', 'inspect', IMAGE], 'DOCKER_IMAGE'))[0];
  return {
    kind: 'docker',
    context,
    daemon_ready: true,
    client_version,
    server_version,
    info_server_version,
    os_type,
    storage_driver,
    image: {
      reference: IMAGE,
      id: image.Id,
      repo_digests: image.RepoDigests ?? [],
    },
  };
}

export class DockerEnvironment {
  constructor(role, provider, volumeName = null) {
    this.role = role;
    this.provider = provider;
    this.volumeName = volumeName;
    this.name = `rpf02-${role}-${randomUUID().slice(0, 8)}`;
    this.containerId = null;
    this.statePath = volumeName ? `${STATE_ROOT}/persist/state` : `${STATE_ROOT}/state`;
    this.contract = {
      environment_id: `docker-${role}-${randomUUID()}`,
      seed_id: SEED.seed_id,
      seed_revision: SEED.seed_revision,
      provenance: null,
      lifecycle_state: 'UNPROVISIONED',
      readiness: 'UNKNOWN',
      verified_initial_state: false,
      observable_state: null,
      operation_receipt: null,
      mutable_state_ownership: volumeName ? 'named-volume-explicit-opt-in' : 'container-writable-layer',
      cleanup_state: 'NOT_STARTED',
      quarantine_state: null,
    };
  }

  startScript() {
    if (this.volumeName) {
      return `mkdir -p ${STATE_ROOT}/persist; if [ ! -f ${this.statePath} ]; then printf '${SEED_TEXT}' > ${this.statePath}; fi; printf 'ready=1\\n' > ${READY_FILE}; exec sleep 300`;
    }
    return `mkdir -p ${STATE_ROOT}; printf '${SEED_TEXT}' > ${this.statePath}; printf 'ready=1\\n' > ${READY_FILE}; exec sleep 300`;
  }

  async start() {
    const args = [
      'run', '--detach', '--name', this.name,
      '--label', 'io.runproof.plan=rpf-02',
      '--label', `io.runproof.environment-id=${this.contract.environment_id}`,
    ];
    if (this.volumeName) args.push('--mount', `type=volume,source=${this.volumeName},target=${STATE_ROOT}/persist`);
    args.push(IMAGE, 'sh', '-c', this.startScript());
    this.containerId = (await requiredDocker(args, 'CONTAINER_START')).trim();
    const inspection = await this.inspect();
    this.contract.provenance = {
      provider: 'docker',
      context: this.provider.context,
      image_ref: IMAGE,
      image_id: this.provider.image.id,
      container_id: inspection.container_id,
      container_name: this.name,
      state_owner: this.contract.mutable_state_ownership,
      mounts: inspection.mounts,
    };
    this.contract.lifecycle_state = 'PROVISIONED';
    this.contract.cleanup_state = 'PENDING';
    return this.snapshot();
  }

  async inspect() {
    const raw = JSON.parse(await requiredDocker(['inspect', this.name], 'CONTAINER_INSPECT'));
    return safeInspect(raw);
  }

  async inspectOptional() {
    const result = await docker(['inspect', this.name]);
    if (result.ok) return safeInspect(JSON.parse(result.stdout));
    if (/no such object|not found/i.test(result.stderr)) return null;
    throw new Error('CONTAINER_INSPECT_UNAVAILABLE');
  }

  async readiness() {
    if (this.contract.lifecycle_state === 'QUARANTINED') return { ok: false, code: 'QUARANTINED' };
    const deadline = Date.now() + 5_000;
    while (Date.now() < deadline) {
      const inspection = await this.inspect();
      if (!inspection.running) return this.quarantineResult('CONTAINER_NOT_RUNNING');
      const ready = await docker(['exec', this.name, 'sh', '-c', `test -f ${READY_FILE}`]);
      if (ready.ok) {
        this.contract.lifecycle_state = 'READY_UNVERIFIED';
        this.contract.readiness = 'READY';
        return { ok: true, readiness: 'READY' };
      }
      await sleep(100);
    }
    return this.quarantineResult('READINESS_TIMEOUT');
  }

  async readState() {
    const text = await requiredDocker(['exec', this.name, 'sh', '-c', `cat ${this.statePath}`], 'STATE_READ');
    const state = parseKeyValueState(text);
    this.contract.observable_state = state;
    return state;
  }

  async verifyInitial() {
    if (this.contract.lifecycle_state !== 'READY_UNVERIFIED') return { ok: false, code: 'READINESS_GATE_REQUIRED' };
    const state = await this.readState();
    const verified = sameState(state, SEED.state);
    if (!verified) {
      this.markQuarantine('initial_state_mismatch');
      return { ok: false, code: 'INITIAL_STATE_MISMATCH', observed: state };
    }
    this.contract.lifecycle_state = 'READY_VERIFIED';
    this.contract.verified_initial_state = true;
    return { ok: true, verified: true, state };
  }

  async mutate(operationId = 'docker-a-change-001') {
    assert.match(operationId, /^[a-z0-9-]+$/);
    if (!this.contract.verified_initial_state) return { ok: false, code: 'INITIAL_STATE_GATE_REQUIRED' };
    const result = await docker(['exec', this.name, 'sh', '-c', `${MUTATION_TEMPLATE(operationId)}${this.statePath}`]);
    if (!result.ok) return this.quarantineResult('MUTATION_FAILED');
    const state = await this.readState();
    this.contract.lifecycle_state = 'RUNNING';
    this.contract.operation_receipt = { operation_id: operationId, status: 'APPLIED' };
    return { ok: true, state, receipt: this.contract.operation_receipt };
  }

  async diff() {
    const output = await requiredDocker(['diff', this.name], 'CONTAINER_DIFF');
    const paths = output.split(/\r?\n/).filter(Boolean);
    return { paths, contains_state_path: paths.some((path) => path.includes('/runproof/state')) };
  }

  markQuarantine(reason, source = 'ENVIRONMENT') {
    this.contract.lifecycle_state = 'QUARANTINED';
    this.contract.readiness = 'UNTRUSTED';
    this.contract.verified_initial_state = false;
    this.contract.cleanup_state = 'UNVERIFIED';
    this.contract.quarantine_state = { status: 'QUARANTINED', reason, source, at: now() };
  }

  quarantineResult(code) {
    this.markQuarantine(code);
    return { ok: false, code };
  }

  canEnterReady() {
    return Boolean(this.containerId) && this.contract.lifecycle_state !== 'QUARANTINED' && this.contract.cleanup_state !== 'UNVERIFIED';
  }

  async cleanup() {
    if (this.contract.lifecycle_state === 'QUARANTINED') return { ok: false, code: 'QUARANTINED' };
    try {
      await requiredDocker(['rm', '--force', this.name], 'CONTAINER_REMOVE');
      const gone = (await this.inspectOptional()) === null;
      if (!gone) throw new Error('CONTAINER_STILL_EXISTS');
      this.contract.lifecycle_state = 'CLEANED';
      this.contract.cleanup_state = 'CLEANED';
      return { ok: true, removed: true };
    } catch {
      this.markQuarantine('cleanup_unverified');
      return { ok: false, code: 'CLEANUP_UNVERIFIED' };
    }
  }

  async forceCleanup() {
    const result = await docker(['rm', '--force', this.name]);
    if (result.ok || /no such object|not found/i.test(result.stderr)) return true;
    return false;
  }

  snapshot() {
    return structuredClone(this.contract);
  }
}

async function createVolume(name) {
  await requiredDocker(['volume', 'create', '--label', 'io.runproof.plan=rpf-02', '--label', 'io.runproof.owner=probe', name], 'VOLUME_CREATE');
  const raw = JSON.parse(await requiredDocker(['volume', 'inspect', name], 'VOLUME_INSPECT'))[0];
  return {
    name: raw.Name,
    driver: raw.Driver,
    scope: raw.Scope,
    owner: 'rpf02-probe',
    lifecycle: 'create -> attach to C/D -> remove after verification',
    mountpoint: '[DOCKER_VOLUME_MOUNTPOINT]',
    labels: { plan: raw.Labels?.['io.runproof.plan'] ?? null, owner: raw.Labels?.['io.runproof.owner'] ?? null },
  };
}

async function volumeExists(name) {
  const result = await docker(['volume', 'inspect', name]);
  if (result.ok) return true;
  if (/no such volume|not found/i.test(result.stderr)) return false;
  throw new Error('VOLUME_INSPECT_UNAVAILABLE');
}

async function removeVolume(name) {
  await requiredDocker(['volume', 'rm', name], 'VOLUME_REMOVE');
  assert.equal(await volumeExists(name), false);
}

async function cleanupEnvironments(environments) {
  for (const environment of environments) await environment.forceCleanup();
}

async function runFreshExperiment(provider) {
  const a = new DockerEnvironment('fresh-a', provider);
  const b = new DockerEnvironment('fresh-b', provider);
  const recreated = new DockerEnvironment('fresh-recreated', provider);
  try {
    await Promise.all([a.start(), b.start()]);
    const aReady = await a.readiness();
    const bReady = await b.readiness();
    const aInitial = await a.verifyInitial();
    const bInitial = await b.verifyInitial();
    assert.equal(aReady.ok && bReady.ok, true);
    assert.equal(aInitial.verified && bInitial.verified, true);
    assert.notEqual(a.contract.environment_id, b.contract.environment_id);
    assert.notEqual(a.contract.provenance.container_id, b.contract.provenance.container_id);

    const mutation = await a.mutate();
    const aAfter = await a.readState();
    const bAfter = await b.readState();
    const diff = await a.diff();
    assert.equal(mutation.ok, true);
    assert.equal(sameState(aAfter, MUTATED), true);
    assert.equal(sameState(bAfter, SEED.state), true);
    assert.equal(a.contract.provenance.mounts.length, 0);
    assert.equal(b.contract.provenance.mounts.length, 0);
    assert.equal(diff.contains_state_path, true);

    const aCleanup = await a.cleanup();
    const bCleanup = await b.cleanup();
    assert.equal(aCleanup.ok && bCleanup.ok, true);
    const aRemoved = (await a.inspectOptional()) === null;
    const bRemoved = (await b.inspectOptional()) === null;

    await recreated.start();
    const recreatedReady = await recreated.readiness();
    const recreatedInitial = await recreated.verifyInitial();
    const recreatedState = await recreated.readState();
    assert.equal(recreatedReady.ok, true);
    assert.equal(recreatedInitial.verified, true);
    assert.equal(sameState(recreatedState, SEED.state), true);
    const recreatedCleanup = await recreated.cleanup();
    const recreatedRemoved = (await recreated.inspectOptional()) === null;
    assert.equal(recreatedCleanup.ok && recreatedRemoved, true);

    return {
      outcome: 'PASS',
      source: 'ENVIRONMENT',
      provider: provider.kind,
      seed: { seed_id: SEED.seed_id, seed_revision: SEED.seed_revision },
      simultaneous_instances: {
        readiness: { a: aReady, b: bReady },
        initial_state_verification: { a: aInitial, b: bInitial },
        identity_distinct: a.contract.environment_id !== b.contract.environment_id,
        provenance_explicit: Boolean(a.contract.provenance.container_id && b.contract.provenance.container_id),
        mutated_environment: a.contract.environment_id,
        untouched_environment: b.contract.environment_id,
        a_actual_state: aAfter,
        b_actual_state: bAfter,
        b_unaffected: sameState(bAfter, SEED.state),
        writable_layer: {
          state_owner: 'container-writable-layer',
          mount_count_a: a.contract.provenance.mounts.length,
          mount_count_b: b.contract.provenance.mounts.length,
          a_diff: diff,
        },
      },
      cleanup: {
        a: { requested: true, removed: aRemoved, contract: a.snapshot() },
        b: { requested: true, removed: bRemoved, contract: b.snapshot() },
        recreated: { requested: true, removed: recreatedRemoved, contract: recreated.snapshot() },
      },
      recreate: {
        new_environment_id: recreated.contract.environment_id,
        new_container_id: recreated.contract.provenance.container_id,
        identity_distinct_from_a_and_b: ![a.contract.environment_id, b.contract.environment_id].includes(recreated.contract.environment_id),
        readiness: recreatedReady,
        initial_state_verification: recreatedInitial,
        state: recreatedState,
        no_contamination: sameState(recreatedState, SEED.state),
      },
      contracts: { a: a.snapshot(), b: b.snapshot(), recreated: recreated.snapshot() },
    };
  } finally {
    await cleanupEnvironments([a, b, recreated]);
  }
}

async function runPersistentCounterExample(provider) {
  const volumeName = `rpf02-persist-${randomUUID().slice(0, 8)}`;
  const c = new DockerEnvironment('persistent-c', provider, volumeName);
  const d = new DockerEnvironment('persistent-d', provider, volumeName);
  let volume;
  try {
    volume = await createVolume(volumeName);
    await c.start();
    const cReady = await c.readiness();
    const cInitial = await c.verifyInitial();
    const cMutation = await c.mutate();
    const cActual = await c.readState();
    assert.equal(cReady.ok && cInitial.verified && cMutation.ok, true);
    assert.equal(sameState(cActual, MUTATED), true);
    const cCleanup = await c.cleanup();
    const volumeAfterC = await volumeExists(volumeName);
    assert.equal(cCleanup.ok && volumeAfterC, true);

    await d.start();
    const dReady = await d.readiness();
    const dState = await d.readState();
    const persistentStateContinues = sameState(dState, MUTATED);
    assert.equal(dReady.ok, true);
    assert.equal(persistentStateContinues, true);
    const dInitialVerification = { ok: false, verified: false, code: 'INITIAL_STATE_MISMATCH', observed: dState };
    d.markQuarantine('persistent_state_requires_explicit_reset');
    const reentry = d.canEnterReady();
    const dCleanupAttempt = await d.cleanup();
    assert.equal(reentry, false);
    assert.equal(dCleanupAttempt.code, 'QUARANTINED');
    const dSnapshot = d.snapshot();
    await d.forceCleanup();
    await removeVolume(volumeName);
    const volumeRemoved = !(await volumeExists(volumeName));
    assert.equal(volumeRemoved, true);

    return {
      outcome: 'PASS',
      source: 'ENVIRONMENT',
      volume,
      first_container: {
        readiness: cReady,
        initial_state_verification: cInitial,
        mutation: cMutation,
        actual_state: cActual,
        cleanup: { requested: true, removed: (await c.inspectOptional()) === null },
      },
      second_container: {
        environment_id: d.contract.environment_id,
        container_id: d.contract.provenance.container_id,
        readiness: dReady,
        observed_state: dState,
        initial_state_verification: dInitialVerification,
        persistent_state_continues: persistentStateContinues,
        blocked_before_agent: true,
        quarantine: dSnapshot.quarantine_state,
        ready_reentry_allowed: reentry,
        cleanup_attempt: dCleanupAttempt,
      },
      conclusion: {
        new_container_is_not_automatically_fresh: true,
        reason: 'The same named volume preserved the mutated state across container deletion and recreation.',
        volume_removed: volumeRemoved,
      },
    };
  } finally {
    await cleanupEnvironments([c, d]);
    if (await volumeExists(volumeName).catch(() => false)) await docker(['volume', 'rm', volumeName]);
  }
}

async function runQuarantineProof(provider) {
  const environment = new DockerEnvironment('quarantine', provider);
  try {
    await environment.start();
    const ready = await environment.readiness();
    assert.equal(ready.ok, true);
    environment.markQuarantine('cleanup_unverified_by_controlled_harness');
    const blockedCleanup = await environment.cleanup();
    const snapshot = environment.snapshot();
    const readyReentryAllowed = environment.canEnterReady();
    assert.equal(blockedCleanup.code, 'QUARANTINED');
    assert.equal(readyReentryAllowed, false);
    return {
      outcome: 'PASS',
      source: 'ENVIRONMENT',
      mode: 'synthetic_unproven_cleanup_harness',
      real_provider_container_created: true,
      readiness_before_quarantine: ready,
      cleanup_observation: 'UNVERIFIED',
      cleanup_attempt: blockedCleanup,
      quarantine: snapshot.quarantine_state,
      lifecycle_state: snapshot.lifecycle_state,
      ready_reentry_allowed: readyReentryAllowed,
      formal_run_started: false,
      agent_quality_eligible: false,
      note: 'No daemon crash was induced; force cleanup is used after the proof so the host is left clean.',
    };
  } finally {
    await environment.forceCleanup();
  }
}

export async function runRealExperiment() {
  const started = now();
  const provider = await providerInfo();
  const fresh = await runFreshExperiment(provider);
  const persistent = await runPersistentCounterExample(provider);
  const quarantine = await runQuarantineProof(provider);
  const source = await readFile(fileURLToPath(import.meta.url));
  return {
    plan: 'RPF-02',
    status: 'Complete',
    started_at: started,
    ended_at: now(),
    source_sha256: sha256(source),
    provider,
    seed: { ...SEED, digest: sha256(json(SEED)) },
    environment_contract: {
      fields: [
        'environment_id', 'seed_id', 'seed_revision', 'provenance', 'lifecycle_state', 'readiness',
        'verified_initial_state', 'observable_state', 'operation_receipt', 'mutable_state_ownership',
        'cleanup_state', 'quarantine_state',
      ],
      default_execution_semantics: 'fresh-per-run',
      persistent_state: 'explicit opt-in only; ownership and lifecycle must be recorded',
      hard_rule: 'No formal Agent Run before readiness and initial-state verification; Environment/Platform failure is not Agent FAIL.',
    },
    fresh_per_run: fresh,
    persistent_shared_state_counterexample: persistent,
    cleanup_quarantine: quarantine,
    decision: {
      recommendation: 'fresh-per-run-semantics',
      docker_is_provider_evidence_not_product_identity: true,
      reuse_and_reset: 'future optimization candidate only after provider-level reset/ownership/quarantine evidence',
      tu002: 'Prototype-level minimum Environment contract evidenced; production-grade isolation/high availability is not claimed',
    },
    decisions_updated: false,
  };
}

async function main() {
  if (process.argv[2] !== '--run' || process.argv.length !== 3) {
    console.log('Usage: node spikes/rpf-02/docker-probe.mjs --run');
    return;
  }
  const evidence = await runRealExperiment();
  const folder = new URL('../../.local/rpf-02/', import.meta.url);
  await mkdir(folder, { recursive: true });
  const filename = `${evidence.started_at.replaceAll(':', '-')}-docker-${randomUUID()}.json`;
  await writeFile(new URL(filename, folder), `${JSON.stringify(evidence, null, 2)}\n`, { flag: 'wx' });
  console.log(JSON.stringify({
    status: evidence.status,
    provider: evidence.provider.kind,
    server_version: evidence.provider.server_version,
    fresh_no_contamination: evidence.fresh_per_run.recreate.no_contamination,
    cross_instance_isolated: evidence.fresh_per_run.simultaneous_instances.b_unaffected,
    persistent_counterexample: evidence.persistent_shared_state_counterexample.conclusion.new_container_is_not_automatically_fresh,
    cleanup_quarantine: evidence.cleanup_quarantine.ready_reentry_allowed === false,
    evidence_file: fileURLToPath(new URL(filename, folder)),
  }));
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  main().catch(() => {
    console.error(JSON.stringify({ outcome: 'INVALID', code: 'DOCKER_PROBE_FAILURE' }));
    process.exitCode = 1;
  });
}

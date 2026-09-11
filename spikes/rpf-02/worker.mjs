// RPF-02 disposable environment worker. It owns only one private temp root.
import { readFile, writeFile } from 'node:fs/promises';

const send = (value, exitCode = 0) => {
  process.stdout.write(`${JSON.stringify(value)}\n`);
  process.exitCode = exitCode;
};
const fail = (code) => send({ ok: false, code }, 2);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const readJson = async (path) => JSON.parse(await readFile(path, 'utf8'));

const main = async () => {
  const [root, command, rawPayload = '{}'] = process.argv.slice(2);
  const payload = JSON.parse(rawPayload);
  const manifestPath = `${root}/manifest.json`;
  const statePath = `${root}/state.json`;

  try {
    const manifest = await readJson(manifestPath);
    if (command === 'readiness') {
      if (manifest.faults.readiness_fail) return fail('READINESS_FAILED');
      if (manifest.faults.readiness_delay_ms) await sleep(manifest.faults.readiness_delay_ms);
      return send({ ok: true, readiness: 'READY' });
    }

    if (command === 'reset') {
      if (manifest.faults.reset_fail) return fail('RESET_FAILED');
      const initial = structuredClone(manifest.initial_state);
      if (manifest.faults.partial_reset || manifest.faults.initial_mismatch) {
        initial.release = manifest.faults.initial_mismatch ? 'release-corrupt' : 'release-v2';
        initial.revision = manifest.faults.initial_mismatch ? 99 : 1;
        initial.mutation_count = manifest.faults.initial_mismatch ? 7 : 1;
        initial.operation_id = manifest.faults.initial_mismatch ? 'foreign-operation' : 'prior-run-operation';
      }
      await writeFile(statePath, `${JSON.stringify(initial)}\n`, { flag: 'w' });
      return send({ ok: true, reset: true, seed_revision: manifest.seed_revision });
    }

    if (command === 'verify_initial') {
      const state = await readJson(statePath);
      const expected = manifest.initial_state;
      const verified = JSON.stringify(state) === JSON.stringify(expected);
      return send({ ok: true, verified, state, expected });
    }

    if (command === 'read_state') {
      return send({ ok: true, state: await readJson(statePath) });
    }

    if (command === 'mutate') {
      const state = await readJson(statePath);
      if (JSON.stringify(state) !== JSON.stringify(manifest.initial_state)) return fail('MUTATION_PRECONDITION');
      const next = { release: payload.release, revision: state.revision + 1, mutation_count: state.mutation_count + 1, operation_id: payload.operation_id };
      await writeFile(statePath, `${JSON.stringify(next)}\n`, { flag: 'w' });
      return send({ ok: true, state: next, receipt: { operation_id: payload.operation_id, status: 'APPLIED' } });
    }

    return fail('UNKNOWN_COMMAND');
  } catch {
    // Do not expose filesystem paths or exception text in evidence.
    send({ ok: false, code: 'WORKER_IO_ERROR' }, 2);
  }
};

try {
  await main();
} catch {
  // Do not expose malformed payload details or filesystem paths in evidence.
  send({ ok: false, code: 'WORKER_INPUT_ERROR' }, 2);
}

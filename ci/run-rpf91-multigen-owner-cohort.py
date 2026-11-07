"""RPF-91 rev-2 fail-closed workflow compatibility investigation.

This B-path artifact deliberately does not execute a cohort or claim admission.
"""
import importlib.util
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE_WORKFLOW = 'bbfe6151c54405a0f1aecd7bcfc9796e8308c1a3'
R89_SOURCE = 'dc8577461ef55b40a6e080a5d895058112f94108'
PILOT = (b'      - name: Run RPF-91 multigeneration pilot\n'
         b'        run: python -B ci/run-rpf91-multigen-owner-cohort.py\n\n')
UPLOAD = (b'      - name: Upload RPF-91 redacted evidence\n'
          b'        uses: actions/upload-artifact@v4\n'
          b'        with:\n          name: rpf91-pilot\n'
          b'          path: ci-results/rpf91/public-result.json\n\n')


def git(*args):
    p = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, timeout=15, check=True)
    return p.stdout


def observe():
    path = ROOT / 'ci/reconcile-rpf88-required-coverage.py'
    assert git('rev-parse', 'HEAD:ci/reconcile-rpf88-required-coverage.py').strip().decode() == R89_SOURCE
    assert path.read_bytes().replace(b'\r\n', b'\n') == git('cat-file', 'blob', R89_SOURCE).replace(b'\r\n', b'\n')
    spec = importlib.util.spec_from_file_location('rpf91_r89_reference', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    workflow = (ROOT / '.github/workflows/release-gate.yml').read_bytes()
    assert workflow.replace(b'\r\n', b'\n') == git('cat-file', 'blob', 'HEAD:.github/workflows/release-gate.yml').replace(b'\r\n', b'\n')
    original = git('cat-file', 'blob', BASE_WORKFLOW)
    mod.workflow_source(workflow, original)
    insertion = b'      - name: Verify Job Summary contract\n'
    assert workflow.count(insertion) == 1
    candidate = workflow.replace(insertion, PILOT + UPLOAD + insertion)
    try:
        mod.workflow_source(candidate, original)
    except mod.Invalid as exc:
        assert str(exc) == 'WORKFLOW_UNAUTHORIZED_DELTA'
        return {'status': 'B_UNACTIVATED', 'baseline_accepted': True,
                'candidate_rejected': True, 'reason': 'WORKFLOW_UNAUTHORIZED_DELTA',
                'native_pilot': 'NOT_RUN', 'release_eligible': False}
    raise AssertionError('unexpected acceptance of RPF-91 workflow delta')


if __name__ == '__main__':
    import json
    print(json.dumps(observe(), sort_keys=True))

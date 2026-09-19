# RPF-35 — bounded Canonical Metadata read model

This disposable proof validates the RPF-35 canonical read boundary against a
fresh PostgreSQL-backed Control Plane:

- 13,500 metadata-only fixture rows plus a real local reviewed artifact;
- default `limit=50`, hard maximum `limit=100`, and an opaque versioned
  keyset cursor bound to entity type, ordering, and page size;
- bounded cross-type reads, malformed/incompatible cursor errors, concurrent
  insertion traversal, SQL/payload budgets, and EXPLAIN evidence;
- registered-reference list semantics with zero full artifact reads, followed
  by one verified local detail read;
- exact disposable PostgreSQL/container/volume cleanup.

The fixture rows intentionally reference no artifact body. That is what proves
that a metadata page exposes a registered reference without claiming that the
current bytes were re-verified. The detail path still reads and verifies one
immutable artifact through the formal ArtifactStore.

## Local proof

```powershell
mvn.cmd -q test package -f control-plane/pom.xml
python spikes/rpf-35/probe.py --run --output-dir .local/rpf-35/local
python spikes/rpf-35/verify-evidence.py .local/rpf-35/local/run-<id>/rpf35-result.json
```

The probe uses only an existing `postgres:16-alpine` image and creates
`rpf35-*` resources. Credentials remain in child process/container
environment variables and are never written to the result.

For a disposable API-backed desktop observation, use `--hold-web`; the probe
prints the Control Plane URL and waits for Ctrl+C before exact cleanup. Start
the Vite development server separately with the printed proxy target and read
token. Browser observation is separate evidence from the automated verifier;
real-device verification is not claimed.

This Spike does not migrate historical artifacts, add a broker, perform
virtualization/streaming/GC, or execute Production/release/deploy actions.

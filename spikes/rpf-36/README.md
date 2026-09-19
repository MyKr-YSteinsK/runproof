# RPF-36 — Production Topology and Managed Operations investigation

RPF-36 is an investigation-only boundary. It compares three current provider
topologies and validates a candidate managed-operations contract without
creating a cloud account, paid resource, provider credential, or Production
deployment.

## Result

The selected candidate is AWS ECS/Fargate + RDS PostgreSQL + S3 + Secrets
Manager in a single-region `ap-southeast-1` candidate topology. This is not a
final provider or data-residency decision. The lifecycle result is:

```text
READY_FOR_PRODUCTION_IMPLEMENTATION = CONDITIONAL
```

The main blocker is not the Web or stateless Control Plane. It is proving a
safe, scoped, fresh-per-run RPF-28 Controlled Simulation task without exposing
a Docker socket, followed by an independent database/object restore rehearsal,
cost/latency preflight, and protected human Release-principal setup.

Render + Cloudflare R2 is a lower-operations portfolio candidate, but a single
platform cannot yet be treated as a safe host for the nested/fresh simulation
boundary. Railway + Cloudflare R2 is inexpensive to start and has useful
private networking, but its provider PostgreSQL templates are documented as
unmanaged, which conflicts with the D-020 managed-persistence target.

The full dated comparison and candidate contracts are in
[`topology-candidates.json`](topology-candidates.json). The human-readable
investigation report is in [`RESULT.md`](RESULT.md).

## Disposable proof

The probe is deliberately offline. It validates matrix completeness, dated
official sources, endpoint and authority separation, Release Identity fields,
backup/restore candidates, cost-boundary honesty, secret-shaped literals and
the conditional RPF-37 boundary.

```powershell
python spikes/rpf-36/probe.py --run --output-dir .local/rpf-36/local
python spikes/rpf-36/verify-evidence.py .local/rpf-36/local/rpf36-result.json
```

The output is ignored under `.local/rpf-36/`. A successful run reports
`cloud_operations=NOT_EXECUTED`; it is not a Production readiness certificate.

## Future RPF-37 boundary

RPF-37 should be limited to provider/account/region/budget authorization,
disposable managed RDS/S3 connectivity, scoped service identities, immutable
image and Product Release Identity read-back, one provider-isolated RPF-28
simulation task, and restore/rollback evidence. It must not silently add
Kubernetes, a broker, multiregion, full tenant/RBAC, or automatic
`ELIGIBLE -> deploy` behavior.

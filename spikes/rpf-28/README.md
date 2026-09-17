# RPF-28 — Formal Multi-service Controlled Environment

RPF-28 is the first formal Runtime integration of the RPF-27 multi-service
network boundary. It adds `multi-service-toxiproxy-v1` while retaining the
historical single-container `DockerEnvironment`.

## Topology and authority

```text
Agent-shaped client --data port--> Toxiproxy fault boundary --> target service
                                                               \-> dependency
                         harness-only observer -------------> target state/receipt
```

Each run creates a fresh Docker `--internal` network, target, dependency,
Toxiproxy, and client. The client cannot reach the Control Plane, Toxiproxy
control API, or Docker socket. Toxic names and activation commands remain
inside `runtime/runproof_runtime/multi_service_environment.py`.

## Fault contract

`rpf-network-fault-profile-v1` covers `none`, `latency`, `timeout`,
`dependency-unavailable`, `response-lost`, and `pre-side-effect-failure`.
Evidence keeps `planned`, `triggered`, `observed`, and `reconciled` separate.
The response-loss path requires a stable `operation_id`, `UNKNOWN_OUTCOME`,
receipt/state reconciliation, exactly one effect, and no blind retry. The
dependency and pre-side-effect paths are explicit zero-effect contrasts.

## Local verification

The existing Docker images must be present; the probe does not pull them:

```powershell
mvn -q test package -f control-plane/pom.xml
python -m unittest discover -s runtime/tests -p 'test_*.py' -v
python spikes/rpf-28/probe.py --run
python spikes/rpf-28/verify-evidence.py .local/rpf-28/rpf28-formal-result.json
python runtime/verify-reviewed-artifacts.py
```

The probe also executes and verifies eight fail-closed negative controls:
planned-but-not-triggered, invalid toxic activation, proxy-down transport failure,
missing receipt, effect count two, blind retry guard, unavailable reconcile, and
cleanup failure quarantine. These controls are recorded in the formal result;
they are not a declaration-only checklist.

The default local probe repeats each profile five times and additionally
executes one independent PostgreSQL/Control Plane/durable-worker job. The
hosted workflow uses `--hosted` for focused baseline/response-loss/cleanup
evidence and is not the canonical Release Gate.

Reviewed samples are refreshed only by the explicit command below; historical
RPF-01–RPF-27 bytes are not rewritten:

```powershell
python spikes/rpf-28/probe.py --run --build-reviewed --refresh-reviewed
```

This slice does not add a broker, scheduler, autoscaling, service mesh,
OpenTelemetry, S3/MinIO storage, Production HA, OAuth/OIDC/SSO, tenant/RBAC,
Production destructive credentials, or release/deploy authorization.

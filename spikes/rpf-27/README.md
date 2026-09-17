# RPF-27 — Real multi-service network fault Spike

RPF-27 is a disposable Investigation / Spike. It does not replace the formal
`DockerEnvironment`, register Control Plane artifacts, refresh reviewed corpus,
or change product Runtime behavior.

## What is exercised

Each trial creates a fresh Docker `--internal` network with two business
services, one fault boundary, and one isolated Agent-shaped client container:

```text
Agent-shaped client container
          |
          v  data port only
fault boundary (Toxiproxy or narrow custom shim)
          |
          v
incident-target ----> incident-dependency
          |
          +---- harness-only `docker exec` observer reads receipt/state
```

The target commits a receipt and effect count before it waits for the response.
For the response-loss case the harness activates a downstream fault, the client
loses the HTTP response, and the observer/reconcile request proves that the
side effect happened exactly once. The client has no fault-control endpoint and
does not receive a Docker socket.

The candidate result is written only to ignored `.local/rpf-27/result.json`.
It is candidate evidence, not a reviewed Run artifact or canonical Control
Plane record.

## Local Windows Docker run

The images must already be present; the probe does not silently pull images:

```powershell
docker pull python:3.12-alpine
docker pull ghcr.io/shopify/toxiproxy:2.12.0
python spikes/rpf-27/probe.py --run --repeat 5
python spikes/rpf-27/verify-evidence.py
```

`--repeat` controls response-lost repetitions and accepts values from 1 to 10.
The default five repetitions are the local Windows Docker evidence target.
Every trial removes its containers and private network in `finally`; no volume
is created and no Golden Demo/PostgreSQL resource is selected by name.

## Hosted candidate feasibility

The optional `rpf-27-network-spike.yml` workflow runs the same disposable
candidate with a smaller repeat count on a GitHub-hosted Linux runner. Its
artifact is diagnostic evidence only; it is not the canonical Release Gate and
does not run release/deploy.

## Candidate boundary

- Toxiproxy is tested as the external candidate: downstream latency and
  downstream `reset_peer` are activated through its local control API.
- The narrow custom shim is a purpose-built comparison and fallback. It only
  implements response delay and server-to-client close; it is not a general
  chaos framework.
- Envoy HTTP fault injection is exercised for fixed delay/abort feasibility,
  but its abort is observed before the target commits the side effect. It is
  retained in the comparison matrix, not treated as response-loss evidence;
  an HTTP abort/delay filter alone does not prove downstream response loss
  after a committed side effect.

The spike records planned, triggered, observed, and reconciled separately;
`UNKNOWN_OUTCOME` semantics are represented in the evidence, while the formal
Runtime schema remains unchanged.

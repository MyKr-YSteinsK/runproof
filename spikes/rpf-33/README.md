# RPF-33 — Capacity and Large-Trace Behavior Investigation

RPF-33 is a disposable Investigation / Spike. It measures the current formal
PostgreSQL canonical metadata, durable HTTP/JSON worker, LocalFile/S3 artifact,
OpenTelemetry, and read-only Web boundaries. It does not add an index or
pagination contract, change the formal schema, migrate history, delete
objects, add a broker, or make a Production capacity claim.

## Commands

Build the probe-only S3 fixture helper and formal Control Plane first:

```powershell
mvn -q test package -f control-plane/pom.xml
mvn -q package -f spikes/rpf-33/java/pom.xml
```

Run the full disposable Windows matrix:

```powershell
python spikes/rpf-33/probe.py --run
python spikes/rpf-33/verify-evidence.py --result .local/rpf-33/local/<run>/rpf33-result.json
```

Hosted CI runs the bounded Medium profile only:

```powershell
python spikes/rpf-33/probe.py --run --hosted --output-dir ci-results/rpf33
python spikes/rpf-33/verify-evidence.py --result ci-results/rpf33/<run>/rpf33-result.json
```

The fixture is `rpf33-capacity-fixture-v1` with seed
`rpf33-seed-20260918`. Local execution grows one disposable database through
Small, Medium, and Large tiers; the Large tier reaches 10,000 Jobs, 50,000
Events, 10,000 Run artifacts, and more than 10,000 S3 objects. The hosted
workflow intentionally stops at Medium to control CI cost.

The S3 helper uses the same AWS SDK for Java `2.54.16` and endpoint shape as
RPF-32. All objects are under a random RPF-33 prefix in a fresh SeaweedFS
`4.47` bucket. The PostgreSQL fixture is inserted directly into the isolated
database after the formal schema has migrated; API reads, durable claims, and
worker execution still cross the real formal HTTP/JSON boundary.

The evidence records directional latency, payload bytes, observed SQL-log
statement counts, `EXPLAIN (ANALYZE, BUFFERS)` plans, a disposable candidate
index A/B, worker concurrency 1/2/4, lease reclaim, object count/size, 1 KiB /
1 MiB / 16 MiB byte-array uploads, orphan growth without deletion, OTel
disabled/healthy/unavailable samples, resource growth, and exact cleanup.
Browser evidence is intentionally separate from the probe process: use the
RPF-33 browser capture helper against the running API-backed Web surface and
keep desktop browser facts separate from real-device evidence.

## Decision boundary

The result must use `BROKER_REQUIRED = NO / NOT_YET / CONDITIONAL` unless
PostgreSQL dispatch itself is demonstrated to be the dominant bottleneck after
the existing query plan is understood. Similar gates apply to streaming
artifact storage, pagination, Web virtualization, and orphan retention/GC.
No result is a Production QPS, HA, cloud SLA, or supported-customer claim.

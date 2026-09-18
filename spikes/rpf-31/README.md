# RPF-31 — S3-compatible Artifact Store durability Spike

RPF-31 is a disposable Investigation / Spike. It does not replace the formal
`LocalFileArtifactStore`, migrate reviewed artifacts, or write PostgreSQL
metadata. The Java child uses only the AWS SDK for Java 2.x S3 client; provider
startup and cleanup stay in the Python harness.

## Commands

```powershell
mvn -q package -f spikes/rpf-31/java/pom.xml
python spikes/rpf-31/probe.py --run
python spikes/rpf-31/verify-evidence.py .local/rpf-31/local/rpf31-result.json
```

Hosted-style focused execution uses the same probe with an ignored CI output:

```powershell
python spikes/rpf-31/probe.py --run --hosted --output-dir ci-results/rpf31
python spikes/rpf-31/verify-evidence.py ci-results/rpf31/rpf31-result.json
```

The probe pins and compares SeaweedFS `4.47` and RustFS `1.0.0`. SeaweedFS is
the selected candidate because it passed the full boundary and supports a
disposable static read-only identity. RustFS is a second protocol comparison;
its result is retained as comparison evidence and does not become a formal
dependency. MinIO Community is recorded only as an archived historical
comparison and is not pulled by this probe.

| Dimension | SeaweedFS 4.47 | RustFS 1.0.0 | MinIO Community |
|---|---|---|---|
| Maintenance / license | Current release line; Apache-2.0 | Current release line; Apache-2.0 | Archived community server; AGPLv3 history |
| Conditional create | Passed `If-None-Match: *` | Passed `If-None-Match: *` | Not run; not a new dependency |
| Concurrent immutability | Passed after disabling SDK default checksum calculation for compatible endpoints | Passed | Not run |
| Windows Docker / restart | Passed local Windows fresh volume, restart, read-back, cleanup | Passed the same local path | Not run |
| Hosted Linux | Required focused workflow; no cloud credential | Required focused workflow; no cloud credential | Not run |
| Credential scope | Static admin plus read-only identity: read allowed, put denied, wrong key denied | Root plus wrong-key denial; read-only policy not configured in this disposable image | Not evaluated |
| Production-shape relevance | Selected additive follow-up candidate; single-node evidence only | Protocol-compatible comparison only | Rejected as a future default because the community repository is archived |

The table is a bounded engineering comparison, not a claim that either
single-node container is Production HA or durable across host failure.

The coverage is intentionally contract-shaped rather than a capacity test:

- conditional `PutObject` with `If-None-Match: *`, with no `HEAD → PUT`
  fallback;
- first create, same-byte replay, different-byte conflict, same-byte and
  different-byte concurrent races;
- one-GET read, RunProof-computed SHA-256, JSON/schema/identity validation,
  missing/corrupt/wrong-identity fail-closed negatives;
- wrong and read-only credentials where the candidate exposes that boundary;
- endpoint stop/unavailable, restart with retained data, put-before-metadata
  orphan replay, metadata-before-ack response-loss replay;
- 1 KiB / 1 MiB / 16 MiB directional put and GET verification timings;
- versioning/Object Lock observation, ETag-as-hint evidence, and exact Docker
  cleanup.

The selected conclusion is `PROCEED_TO_FORMAL_S3_ARTIFACT_STORE = YES` for a
future additive RPF-32 adapter. This is still a single-node local/hosted
container experiment: it is not Production durability, HA, replication,
retention, lifecycle, CDN, upload UI, or release/deploy evidence.

Object keys remain stable RunProof artifact keys under one RunProof-owned
prefix. Application-level immutability is enforced by the conditional create;
RunProof must continue to compute SHA-256 from the GET body and must not treat
ETag, versioning, or Object Lock as canonical identity. An object written before
metadata commit is an orphan until a separate retention/GC policy is defined;
it is never canonical merely because it exists.

The Java client pins AWS SDK for Java `2.54.16` and uses endpoint override,
path-style addressing, bounded timeouts, and `WHEN_REQUIRED` request/response
checksum calculation. The checksum setting avoids the newer default checksum
header compatibility edge observed by SeaweedFS while keeping the product
integrity rule at RunProof's own post-GET SHA-256 verification.

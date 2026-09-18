# RPF-32 — formal S3-compatible ArtifactStore

RPF-32 is the additive formal implementation that follows the RPF-31
SeaweedFS selection. It adds a provider-neutral `S3ArtifactStore` behind the
existing `ArtifactStore` contract while retaining `LocalFileArtifactStore` as
the default and preserving all historical reviewed bytes. The Control Plane
keeps PostgreSQL canonical metadata, identity, schema, source identity, and
RunProof SHA-256; the S3-compatible backend stores only immutable artifact
bytes.

## Commands

```powershell
mvn -q test package -f control-plane/pom.xml
mvn -q package -f spikes/rpf-32/java/pom.xml
python spikes/rpf-32/probe.py --run --output-dir .local/rpf-32/local
python spikes/rpf-32/verify-evidence.py --result .local/rpf-32/local/<run>/rpf32-result.json
```

The focused hosted workflow is
`.github/workflows/rpf-32-s3-artifact-store.yml`. It starts fresh PostgreSQL
and SeaweedFS `4.47`, runs the formal Java Control Plane and independent
HTTP/JSON Python Worker, verifies the source-bound result, and uploads only
the disposable proof under `ci-results/rpf32/`.

## Contract boundary

- Backend selection is explicit: `RPF_ARTIFACT_STORE_BACKEND=local` or `s3`;
  invalid configuration fails closed and never falls back.
- S3 writes use conditional `PutObject` with `If-None-Match: *`; same bytes
  reconcile as an idempotent replay and different bytes are immutable
  conflicts. An unknown write outcome is reconciled with bounded GET/retry.
- A verified read uses one object GET, then RunProof computes SHA-256 and
  validates JSON, schema, artifact kind, entity identity, source identity, and
  runtime identity. ETag, versioning, and Object Lock are not canonical.
- Cross-process Worker uploads bytes through the authenticated Control Plane
  endpoint before canonical metadata ingest. Object existence alone is not
  evidence; PostgreSQL metadata remains the canonical registration.
- SeaweedFS is a pinned disposable compatibility provider. This proof does
  not establish managed-object-store durability, HA, replication, lifecycle,
  capacity, migration, Production deploy/release, or a 2PC guarantee.

## 中文边界

RPF-32 是在 RPF-31 结论之后落地的 additive 正式实现：新增 provider-neutral
`S3ArtifactStore`，保留默认的 `LocalFileArtifactStore`，不迁移历史 reviewed
bytes。PostgreSQL 继续持有 canonical metadata、identity、schema、source
identity 与 RunProof SHA-256；S3-compatible backend 只持有 immutable artifact
bytes。`local`/`s3` 必须显式选择，错误配置 fail closed，不自动回退。

SeaweedFS `4.47` 只作为 disposable compatibility provider；本 probe 不代表
托管对象存储、HA/replication、lifecycle、capacity、Production deploy/release
或 2PC 已经实现。详细当前事实以 `docs/project/CURRENT_STATE.md` 为准。

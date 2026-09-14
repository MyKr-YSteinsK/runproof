# RPF-15 Production 部署、Artifact Storage 与 Release Boundary Investigation

RPF-15 是一次 disposable production-readiness investigation。它不执行真实 Production deploy/release，不创建云账号、域名或付费资源；只在本机 Docker 与独立进程中验证一个 production-like Candidate A，并把 Candidate B 的托管持久化方向固定为后续 provider 选择后的目标候选。

## 验证入口

从仓库根目录运行：

```powershell
mvn -q test package -f control-plane/pom.xml
python spikes/rpf-15/probe.py
$result = Get-ChildItem .local/rpf-15 -Filter probe-result.json -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
python spikes/rpf-15/verify-evidence.py --result $result.FullName
```

Probe 会创建带 `rpf15` 前缀的 PostgreSQL container/volume、独立 Java Control Plane、独立 Python worker process 与静态 Web server；Artifact Store 使用 probe-owned persistent filesystem path。它实际验证 Web/Control Plane/Worker/PostgreSQL/Artifact Store 的 health/readiness、canonical evidence read-back、artifact overwrite/missing/corrupt fail-closed、服务/worker/数据库 replacement、active durable job 的 stale fencing 与 UNKNOWN_OUTCOME reconcile、PostgreSQL `pg_dump`/独立 `pg_restore`、artifact export/restore、additive migration + compatible application rollback、secret rotation/redaction 与 Release Identity boundary。所有输出仅写入被忽略的 `.local/rpf-15/`，结束时清理 probe-owned resource。

## 当前 inventory

- 没有 Production endpoint、deploy/release workflow、产品 published version、tag、部署凭据或正式 artifact retention policy。
- `.github/workflows/release-gate.yml` 是 RPF-12 CI gate；它使用 ephemeral PostgreSQL/Control Plane/worker，不是产品部署流程。
- Control Plane 当前是 Java/Spring + PostgreSQL canonical metadata；Artifact Store 当前是 `LocalFileArtifactStore`；Worker 只通过 Python HTTP/JSON client 访问 Control Plane。
- Web 通过 Vite 生成静态 production build；当前没有提交的 production reverse proxy/serve topology。

## Topology candidates

### Candidate A — Minimal single-host/containerized

同一单区域主机上分离 Web、Control Plane、durable Worker、PostgreSQL named volume 与 local immutable artifact path，可加 reverse proxy。RPF-15 对该候选执行真实 production-like probe：它证明了 process/container replacement、lease fencing、reconcile、PostgreSQL backup/restore 和 artifact restore 的最小语义；它仍暴露 single-host loss 风险，artifact 必须有 off-host backup，不代表 HA、autoscaling 或生产 SLA。

### Candidate B — Managed persistence / stateless application

Web、Control Plane、Worker 作为 stateless service，PostgreSQL 使用 managed database，Artifact Store 使用 S3-compatible object storage，secret 使用平台 secret manager，产品 release 使用 explicit-release。当前没有目标 provider、账号、IAM、成本和 restore SLA，因此本 Spike 不连接或创建该候选。它是首个真实 Production 的推荐目标；Candidate A 保留为本地复现 profile。

## Decision packet

- 推荐 topology：`B_WITH_A_CONTROLLED_LOCAL_REPRODUCTION_PROFILE`。首个 Production 先限定单区域、少副本、无 Kubernetes；应用 replacement 必须保留 PostgreSQL/object storage identity，worker 继续使用 attempt/lease/version/operation fencing。
- Artifact：Production 推荐 object storage + immutable key + SHA-256/schema/source verification + independent export/restore；local filesystem 仅在有持久卷、off-host backup、restore rehearsal 和 host-loss 接受记录时作为 bounded candidate。
- PostgreSQL：Production 推荐 managed PostgreSQL；保留 PostgreSQL canonical metadata、durable Job/Attempt/Operation/Event、Release Decision history 与 additive migration。`pg_dump`/独立 restore 是 recovery contract，不是 HA。
- Product Release Identity：推荐 `0.1.0-rc.1` 作为首个 Production candidate，而不是机械创建 `1.0.0`。Identity 必须绑定 product version、source SHA、build/Web/Control Plane/Worker hash、DB schema、environment、deployed-at 与 release/deployment status；产品 release history 只 append 新 identity。
- Agent Decision separation：`Agent Release Decision ID` 与 `RunProof Product Release ID` 永远不同；`ELIGIBLE` 只表示 evidence/policy decision，不触发产品 release/deploy。
- Delivery：推荐 `explicit-release`。main push 只运行 checks；独立、已认证的产品 release authority 才能选择 target environment、绑定 production secrets 并 deploy；部署后验证 readiness/canonical read-back，失败按 rollback contract 处理。
- Rollback：只允许在 compatibility window 内做 application rollback；migration 默认 additive/forward-compatible，不提供 destructive down migration。无法证明兼容时拒绝 application rollback，使用独立 backup 做 data restore；active Job 不 whole-run retry，必须 drain/hold 或由新 worker 按 durable state/reconcile 恢复。
- Auth/Approval：公开 Web 在 Production 前必须增加 user auth；write API 在此之前保持 private service-principal-only。任何产品部署前必须有独立 Approval/release authority；worker、runtime、decision writer、Agent Candidate 均不得持有 deploy credential。多租户公开服务还需要 tenant/RBAC。

## Readiness conclusion

RPF-15 维持项目 `Stabilization`。它解锁了首个 Production 的推荐拓扑、Artifact/PostgreSQL durability contract、Product Release Identity、explicit-release 与 gap matrix，但没有授权或执行真实 Production deploy/release。下一正式 Plan 应只实现已选 provider 的持久 Artifact Store、Product Release Identity registry、user auth/Approval、explicit-release workflow、retention/backup SLA、worker rollout/compatibility 与 capacity evidence；不得把本地 Docker probe 写成 Production ready。

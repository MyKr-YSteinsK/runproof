# RPF-36 调查结果

## 状态

- Status: `Complete`
- Lifecycle: `Stabilization`
- `formal Production implementation changed`: `no`
- `cloud_operations`: `NOT_EXECUTED`
- `paid_resources_created`: `false`
- `production_deployment_executed`: `false`
- `historical_reviewed_bytes_changed`: `false`
- 调查日期：`2026-09-19`
- 完整结构化证据：[`topology-candidates.json`](topology-candidates.json)

## Provider 与 Region

本轮比较了三个候选：

| Candidate | 结论 | 关键原因 |
|---|---|---|
| AWS ECS/Fargate + RDS + S3 + Secrets Manager | selected candidate with blockers | managed persistence、私有网络、任务身份和 GitHub OIDC 形状最完整；但 per-run Simulation task、成本和恢复演练还没有真实验证 |
| Render + Cloudflare R2 | portfolio candidate, not selected | PaaS 运维简单、Background Worker 与 managed Postgres 可用；但单一 PaaS 的安全 fresh-Docker Simulation hosting 未证明，Release identity 也需要额外边界 |
| Railway + Cloudflare R2 | low-cost comparison, blocked for D-020 | private networking 有价值，但官方将 PostgreSQL template 定义为 unmanaged，备份/DR 仍由用户负责 |

推荐的首个 Region candidate 是 `AWS ap-southeast-1`（Singapore），但它仍是 candidate-only：官方 Region 资料显示该 Region 有三个 Availability Zones 且默认可用；本轮没有从目标用户或 GitHub runner 实测 latency，也没有验证用户的数据驻留要求、账户 quota 或区域报价。RPF-37 必须先获得 Singapore/替代 Region、数据驻留与预算授权。

变动中的 Provider 事实和来源日期均记录在 `topology-candidates.json` 的
`research_sources` 和每个 provider 的 `sources` 中；研究日期统一为
`2026-09-19`。

## 正式候选拓扑

```text
Internet
  -> CloudFront / static Web (read-only)
  -> public API edge
  -> stateless Control Plane
       -> private managed PostgreSQL
       -> private S3 canonical-artifact bucket

private Durable Worker (outbound-only)
  -> Control Plane HTTP/JSON
  -> scoped per-run RPF-28 Controlled Simulation task
  -> verified object upload

GitHub Actions
  -> canonical gate
  -> protected human/product Approval
  -> separate explicit Release principal
  -> future deployment and target verification
```

Public endpoint 只保留 Web、必要的 API edge 和不泄露数据的 health
endpoint。PostgreSQL、Worker、Simulation task 和 object access 位于私有
边界。Agent 不直连数据库、不持有 Production credential、不持有 Docker
socket，也不拥有 Release principal；Worker 只拥有受限 HTTP/JSON、任务环境
和 artifact upload 权限；Web 只读且 API/artifact unavailable 时 fail closed。

## Web、Control Plane、Worker 与 Simulation

- Web 使用 immutable versioned static prefix + CDN。回滚指向上一个 asset
  manifest，不把浏览器变成 mutation 或 release client。
- Control Plane 是无状态 Java/Spring service。Canonical metadata、Job、
  Decision 和 artifact verification 状态只在 PostgreSQL/S3；新 task 必须
  通过 process、schema、DB 和 artifact readiness 后才接流量。
- Worker 初始候选为 1 replica、concurrency 1、private/outbound-only，继续
  使用 PostgreSQL durable claim/lease/fencing；扩容依赖 backlog、attempt
  duration 和 DB pool evidence，不凭空声称 QPS。
- RPF-28 的 target/dependency/Toxiproxy/Agent-shaped client 必须映射为每次
  run 的 scoped ECS task/private network，或者单独运维的 sandbox host。不能
  因 Web/Control Plane 能部署，就宣称整个系统已经可部署。
- Agent/Worker 永不接收 Docker socket；任务只能由受限 environment-launch
  identity 创建/停止，image、subnet、security group 和 cleanup 都需验证。

## Managed PostgreSQL 与恢复

候选是 RDS PostgreSQL 16-compatible，精确 minor、instance class 和 region
availability 由 RPF-37 preflight 决定。要求 TLS/CA verify、private endpoint、
5–10 的初始 per-process pool candidate、Secrets Manager rotation，以及
additive expand/contract migration。Backup/PITR 只被视为候选能力，不能把
“backup enabled”当作 restore proof。

首个候选操作目标（不是 provider SLA）：

- backup retention：最多 35 天，需预算和数据策略批准；
- DB RPO：15 分钟 candidate objective；
- DB/Artifact recovery RTO：4 小时 candidate objective；
- restore rehearsal：季度一次，并在 destructive migration 之前执行；
- restore 必须到独立 target，重新连接 disposable Control Plane/Worker，检查
  row count、Decision、artifact SHA-256/schema/identity，再记录 source backup
  timestamp、restore target、elapsed time 和 cleanup。

## Object Store 与 Artifact Policy

推荐先用 S3 Standard；保留 RPF-32 的 provider-neutral
`S3ArtifactStore` 合同：conditional `If-None-Match` create、same-content
replay、different-content conflict、one-GET SHA-256/schema/identity/source
verification，以及 missing/corrupt/wrong-identity/invalid-access/unavailable
的 fail-closed 行为。Provider versioning/Object Lock 不替代应用层 immutable
metadata/conflict 规则。

RPF-36 不实现 GC。建议的后续 policy 是：canonical artifact 长期保留；
put-before-metadata orphan 先保留 7 天，再做 dry-run inventory；任何 delete
需要独立的 human/product retention authority 和后续 high-risk Plan。不能因
一个 bounded list 为空就删除 artifact。

## Secret、Service Auth、Approval 与 Release Identity

- DB、S3、service auth、Provider key 和 Release principal 都只使用平台 secret
  reference、task role 或短期 identity；secret value 不进入 Git、image、Web
  bundle、scenario、trace、log、artifact 或 TASK_RESULT。
- 过渡期继续使用 scoped Bearer HTTP/JSON；服务间逐步使用 workload identity，
  GitHub 使用 OIDC。RPF-36 不实现完整 OAuth/OIDC/SSO、tenant/RBAC。
- Release 链严格为：

  `Release Decision ELIGIBLE -> human/product Approval -> protected release-principal workflow -> deployment -> target verification`

  GitHub Environment reviewer 和 OIDC trust policy 必须限制 repository、branch/
  tag、environment/workflow，不能让 canonical gate 或 Agent 自动假设 release
  role。`ELIGIBLE` 不是 Released。
- `rpf-product-release-identity-v1-candidate` 至少绑定：commit SHA、source
  tree SHA-256、application version、Control Plane/Worker image digest、Web
  asset manifest digest、schema migration identity、build workflow/run、target
  environment、deployment id、deployed timestamp。它独立于 Agent Version
  Identity，并以 append-only 形式记录。

## Build、Migration、Rollout 与 Rollback

- Java Control Plane 与 Python Worker 构建 immutable digest image；Web 构建
  asset manifest；候选 registry 是 ECR private repository；CI 生成 SBOM 和
  vulnerability-scan evidence。本轮没有发布 image。
- Migration 用 expand/contract additive strategy。Migration failure 阻止
  readiness/rollout，不自动执行 destructive down migration；schema identity
  绑定 Product Release Identity。
- 首个 Production 候选使用 ECS rolling deployment + deployment circuit
  breaker/CloudWatch alarm rollback，不引入 canary、blue-green、multiregion。
  Worker 替换前停止新 claim、fence stale attempt 并 reconcile。
- 回滚目标是上一个 Product Release Identity：Web asset manifest、服务 image、
  compatible config/secret。数据库 restore 不是普通 application rollback，需
  走独立 restore/data decision。

## Failure Domain、Health 与 Observability

| Domain | 影响与恢复 | Release impact |
|---|---|---|
| Web/CDN | edge health、asset-prefix rollback、bounded invalidation | target verification 失败即阻断 |
| Control Plane | task replacement、readiness gate、DB/artifact read-back | 阻断 decision 写入/读取 |
| Worker | lease expiry、fencing、reconcile、replacement | `UNKNOWN_OUTCOME` 不得 blind retry |
| PostgreSQL | provider failover 或独立 restore | 无 canonical read-back 不发布 |
| Object store | bounded retry/reconcile，metadata 不早于 verified object | fail closed |
| Collector/logging | diagnostic loss；canonical evidence 独立保留 | 只有审计证据缺失才阻断 |
| GitHub Actions | fresh gate/build/approval，不复用 stale success | 无 fresh gate 不得 assume release role |

Web availability、Control Plane liveness/readiness、DB connectivity、artifact
verification、Worker heartbeat/backlog、queue depth 和 reclaim age 都应有
明确信号。OTel 仍是 optional diagnostic，Collector unavailable 不应制造
假的健康状态，也不应改变 canonical evidence。首批 alerts：CP unavailable、
DB/backup failure、object unavailable/verification conflict/orphan threshold、
Worker stale/backlog/reconcile age、release rollback、secret rotation failure。

## Capacity、Backpressure 与成本

RPF-33 只提供方向性测量，不提供 Production QPS/SLA。首个候选 sizing 是：

- static Web 1 个 CDN deployment；
- Control Plane 1 个约 0.5 vCPU/1 GiB task；
- Worker 1 个约 1 vCPU/2 GiB task，concurrency 1；
- 最小 production-eligible RDS class，连接池先限制 5–10/process；
- artifact 50 GiB soft budget / 100 GiB review threshold candidate；
- backlog、DB pool、artifact upload 和 API page/payload 超阈值时 backpressure，
  保留 durable job，不丢弃、不盲目重复 side effect；
- `BROKER_REQUIRED=NOT_YET` 仍成立。

AWS 不能在没有 region、task-hours、RDS class、ALB/NAT、I/O、egress、日志和
backup volume 的情况下诚实给出固定月费，故采用逐项 quote。Render 的公开基础
示例约为 Pro workspace + 三个小型 compute service 的 46 USD/月，尚未包含
paid Postgres、storage、bandwidth/domain；Railway 是 5 USD/月 Hobby 起加用量，
不是 Production 总价。Golden Demo 仍是无云成本路径，但不是 Production SLA。

## CI 到 Release、验证与数据边界

未来流程固定为：

`commit -> push -> canonical gate -> immutable Product Release Identity -> explicit Approval -> Release principal deploy -> target verification -> deployment evidence`

正式 Production Plan 必须验证 deployed identity、Web/API、migration、artifact
put/read、Durable Job、Decision read-back、RPF-28 Simulation、restart/reclaim、
rollback 和 restore rehearsal。首个目标仍是 single-user/single-tenant；公网
部署不代表 multi-tenant readiness，也不引入完整 tenant/RBAC。

Reviewed corpus 和 canonical artifacts 长期保留；Jobs/Attempts/Events 的 90
天 hot-retention、logs 14 天、traces 7 天均只是 candidate policy；credentials
永不进入业务数据。所有 public/private TLS、private DB、bucket public access
关闭、Agent 无 Production credentials、Worker 无 release authority、Web 无
mutation、Simulation cleanup 和独立 audit logs 都是后续 gate。

产品可携带的合同是 PostgreSQL、S3-compatible、HTTP/JSON Worker、optional OTel
和 explicit Release principal；ECS/IAM/RDS/S3/region/deployment/task-launch 是
Provider implementation。IaC 先用可审计的 provider-native descriptors 和
environment/schema manifests，资源规模足够前不强制引入 OpenTofu/Terraform。

## 生命周期判断与 RPF-37

```text
READY_FOR_PRODUCTION_IMPLEMENTATION = CONDITIONAL
```

AWS 候选的持久化和 authority 形状足够进入下一阶段，但以下最小阻塞项尚未
完成：

1. 用户批准 provider/account、Singapore 或替代 region、数据驻留和月度预算；
2. 证明 RPF-28 fresh-per-run Simulation task 的隔离、权限、成本和 cleanup；
3. 完成 RDS/S3 TLS、role scope 与独立 restore rehearsal；
4. 配置 GitHub protected environment、reviewer 和 Release-principal trust；
5. 让 Product Release Identity 在目标环境 read back，并证明 rollback。

推荐的 RPF-37 只覆盖以上最小 Production implementation slice；禁止无证据
扩大为 Kubernetes、broker、multiregion、full tenant/RBAC 或
`ELIGIBLE -> auto deploy`。

## 本轮证据命令

```powershell
python spikes/rpf-36/probe.py --run --output-dir .local/rpf-36/local
python spikes/rpf-36/verify-evidence.py .local/rpf-36/local/rpf36-result.json
```

该 proof 只验证仓库内的 dated topology contract 和 authority boundary，未执行
任何云 API、账单操作、真实 restore 或部署。

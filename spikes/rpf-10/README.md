# RPF-10 PostgreSQL Persistence / Control Plane Authority Spike

RPF-10 是一个 disposable Investigation / Spike，不是正式 Control Plane。它在真实 PostgreSQL candidate 上验证 RPF-09 的 canonical metadata、immutable artifact ref、idempotency、rollback、restart、backup/restore 与故障语义，并在同一 Spring Boot candidate 上验证最小 service-to-service authentication 和 Release Decision authority boundary。

## Reproduce

从仓库根目录运行：

```powershell
mvn -q test package -f spikes/rpf-10/control-plane/pom.xml
python spikes/rpf-10/probe.py --run
python spikes/rpf-10/verify-evidence.py
```

Probe 会：

- 使用现有 Docker Desktop `desktop-linux` 与 `postgres:16-alpine`；创建带 `rpf10` 前缀的临时 container 和 named volume，并在结束时清理；
- 生成仅存在于 probe/service/container 环境的临时数据库密码与四类 bearer credential；不打印、不持久化、不写入 artifact/API response/log；
- 启动独立 Spring Boot JVM，执行 Run、Evaluation、Release Decision 的受约束 HTTP/JSON ingest/query；
- 验证 PostgreSQL migration、真实写入/查询、同 fingerprint 幂等、identity/idempotency conflict、事务回滚、并发冲突 race、Control Plane/PostgreSQL restart、schema mismatch、storage unavailable、pg_dump/pg_restore 与 immutable artifact resolution；
- 验证 read、evidence-ingest、decision-writer、agent-like 四类 principal 的 401/403/422/400 边界；
- 仅将结果写入被忽略的 `.local/rpf-10/`；固定的脱敏摘要为本目录的 `reviewed-evidence.json`。

## Reviewed evidence

最近一次真实执行环境：Windows 11 x64、Docker Desktop Engine 29.7.2、PostgreSQL 16.15、PostgreSQL JDBC 42.7.5、Java 17.0.12。镜像 identity 为 `sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685`。

| Area | Observed result |
| --- | --- |
| Migration | `rpf-10-postgresql-metadata-schema-v1`；`timestamptz`、canonical primary key、idempotency unique constraint 通过 |
| Persistence | Run / Evaluation / Release Decision insert/query 通过；canonical metadata 不含 raw artifact |
| Idempotency / conflict | same identity + same fingerprint → `200 IDEMPOTENT_REPLAY`；different fingerprint / idempotency key conflict → `409` |
| Transaction | forced write rollback 后查询 `404`；相同 manifest 随后可正常 ingest |
| Concurrency | 同一 identity 的 `[201, 409]` race；canonical row 数为 1 |
| Recovery | Control Plane restart、PostgreSQL container restart 后 history 与 artifact refs 恢复 |
| Backup | 独立 restore database；6 canonical rows、3 Release Decision rows、6 artifact refs 通过 |
| Auth | no/invalid credential → `401`；forbidden principal → `403`；identity/evidence errors → `422`/`400` |
| Authority | Agent、evidence-ingest、CI 均无 `decision:write` 或 deploy/release authority |

## Authority recommendation

选择 Candidate B：由受信任的 deterministic quality component 复用当前 Python `quality.py` 生成 Decision manifest，使用独立 `decision:write` principal 登记；Control Plane 验证 evidence refs、identity、history 与幂等/冲突。Approval authority 保持独立，`ELIGIBLE` 仍不等于发布或部署授权。

Candidate A 的 Control Plane-owned decision boundary 更集中，但会更早把质量 evaluator 耦合到 Java 服务；本 Spike 不引入该耦合，也不实现 Approval、CI provider、Queue、scheduler、durable worker 或 release/deploy endpoint。

## Evidence boundary / remaining risks

- PostgreSQL 16 candidate 已被真实确认可作为 v1 canonical metadata 方向；未证明 production HA、replication、backup policy、retention、performance 或大规模运维。
- Bearer 环境凭据只证明 disposable service-to-service candidate，不是用户登录、OAuth/OIDC、SSO、tenant 或完整 RBAC。
- DB unavailable 返回 `503` retriable；只有健康恢复且保持同一 immutable identity/fingerprint/idempotency key 才可安全重试。identity/content conflict、invalid evidence 与 schema mismatch 不应盲重试。
- 本 Spike 不创建 durable job，也不把 service restart 等同于 TU-004 durable Run resume。
- PostgreSQL/database/container、artifact store 与 Java service 都是 probe 资源；不代表正式部署身份。

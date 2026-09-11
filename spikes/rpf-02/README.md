# RPF-02 — Controlled Environment Execution and Recovery Model

结论：RPF-02 已使用现有 Docker Desktop 完成 Prototype-level minimum Environment contract 的真实 provider 证明，状态为 `Complete`。Docker 不是产品永久身份；本次只把 Docker 作为当前可用的 isolation provider。结果不宣称 production-grade isolation、HA、durable worker 或 deployment readiness。

## 复现

使用 Node.js 24.16.0 内置 API，无第三方依赖。上一轮 host reference probe 与本轮 Docker provider probe 分开保存；Docker probe 只创建带 `rpf02` 前缀的临时 container/volume，并在 finally 中清理。

```powershell
node --test spikes/rpf-02/probe.test.mjs
node spikes/rpf-02/verify-evidence.mjs
node spikes/rpf-02/probe.mjs --run
node --test spikes/rpf-02/docker-probe.test.mjs
node spikes/rpf-02/docker-probe.mjs --run
node spikes/rpf-02/verify-docker-evidence.mjs
```

前三条是上一轮 host reference 实验与固定样本校验，不访问 Provider。后三条使用现有 Docker daemon，会实际创建并清理临时资源，输出写入被忽略的 `.local/rpf-02/`。固定 Docker 样本为 [reviewed-docker-evidence.json](reviewed-docker-evidence.json)，上一轮参考样本仍为 [reviewed-evidence.json](reviewed-evidence.json)。

## Provider evidence

- Host/runtime：Windows `win32`、`x64`、Node.js `v24.16.0`。
- Provider：Docker Desktop Linux，context `desktop-linux`，client/server `29.6.1`，daemon readiness `true`，storage driver `overlayfs`。
- Image：`alpine:3.22`，image ID 与 repo digest 记录在固定样本；没有拉取或安装新的系统组件。
- Docker CLI、daemon、image、container inspect、writable-layer diff、volume lifecycle 和 cleanup 结果均来自实际命令，不是 synthetic container transcript。

## Real Docker proof

### Fresh-per-run / ephemeral writable layer

实验同时创建 environment A/B，二者使用相同 `seed_id` / `seed_revision`，分别记录 `environment_id`、container ID、image ID、context 和 state ownership。readiness 只检查 container running + ready sentinel，之后才独立读取并比较 initial state。

- A/B 都 readiness 成功、initial-state verification 成功。
- A 的 `/runproof/state` mutation 后，actual state 为 `release-v2 / revision=1 / mutation_count=1`；B 仍为 seed state。
- A/B 都没有 mount；`docker diff A` 显示 `/runproof/state` 位于 container writable layer。
- 删除 A/B 后，以同一 seed/revision 创建新 container，readiness、initial verification 成功且 state 回到 seed，没有继承 A 的 mutation。
- 正常 cleanup 后逐一 `docker inspect` 验证资源不存在。

### Persistent/shared-state negative control

单独创建 named volume，C 将 mutation 写入 volume；删除 C 后用同一 volume 创建 D。D 真实读到 C 的 mutated state，initial-state verification 为 `INITIAL_STATE_MISMATCH`，实例进入 `QUARANTINED`，不能重新进入 READY，也不启动 Agent。最后 volume 被实际删除并验证不存在。

这证明“new container/environment instance ≠ automatically fresh state”；persistent state 是显式 opt-in，必须携带 ownership、lifecycle 和 reset verification，不能被 Fresh-per-run 语义隐式吸收。

### Cleanup / quarantine

正常 Fresh cleanup 是真实 Docker removal + post-removal inspect。另有一个受控 synthetic unproven-cleanup harness：创建真实 provider container 后人为把 cleanup observation 标为 `UNVERIFIED`，验证 `cleanup()` 拒绝继续、lifecycle 为 `QUARANTINED`、`ready_reentry_allowed=false`；未诱发 daemon crash，随后用 force cleanup 清理主机。该 harness 证明 quarantine contract，不冒充真实 daemon crash 证据。

## Environment contract

每个 Docker 实例显式保存：

| 字段 | 语义 |
| --- | --- |
| `environment_id` | 每个实例唯一，不能从 container name 隐式推断 |
| `seed_id` / `seed_revision` | 不可变逻辑起点及其版本 |
| `provenance` | provider/context、image ref/id、container ID、state owner 和 mount 事实 |
| `lifecycle_state` | `UNPROVISIONED`、`PROVISIONED`、`READY_UNVERIFIED`、`READY_VERIFIED`、`RUNNING`、`QUARANTINED`、`CLEANED` |
| `readiness` | container 可响应的运行信号，不等于状态可信 |
| `verified_initial_state` | 对实际 state 与 seed 的程序比较结果 |
| `observable_state` | release、revision、mutation_count、operation_id |
| `operation_receipt` | 受控 mutation 的 operation identity/status |
| `mutable_state_ownership` | 默认 `container-writable-layer`；persistent volume 只能显式 opt-in |
| `cleanup_state` / `quarantine_state` | 可复用/不可复用的明确结论与原因 |

正式 Run 只能按 `provision/acquire → readiness → initial-state verification → Agent/tool mutation → actual-state verification → cleanup/release` 进入。任何 readiness 或 initial-state gate 失败都不启动 Agent；initial mismatch 是 Environment-side `INVALID`；cleanup 无法证明时实例 quarantine。

## 两种候选模型

### Fresh-per-run

每次 Run 创建新 environment identity、专用 Docker container writable layer，写入相同 seed/revision，先 readiness 再 initial-state verification。实际 Docker 证据中同时存在的 A/B 修改 A 后 B 仍为 seed；删除 A/B 并重建的新 container 不继承旧 mutation。上一轮 host reference 仍保留 5 次顺序 PASS 作为低成本参考，但不再承担正式隔离证明。

优点是状态所有权、污染边界和 quarantine 最容易解释，失败环境不会被下一 Run 复用。代价是每次 container acquire/create/cleanup 都要付成本；本 Spike 不做 production performance benchmark。

### Reuse-and-reset

Reuse-and-reset 仍有上一轮 host reference 的 5 次 sound reset 证据，但真实 Docker 本轮没有把它提升为默认执行模型。named-volume negative control 证明即使 container identity 改变，共享 mutable state 仍会跨 container 存活。

它仍可能减少 acquire/cleanup 成本，但 reset correctness、volume ownership、残留状态和 failure recovery 都成为复用前置条件；当前继续作为未来优化候选，而不是首个 Prototype 默认模型。

## Host reference evidence

以下数据来自当前开发机的 host-process/filesystem probe，只作历史参考证据，不是 Docker 的性能结论，也不是 production benchmark：

| 指标 | Fresh-per-run | Reuse-and-reset |
| --- | ---: | ---: |
| PASS cycles | 5/5 | 5/5 |
| provision/acquire count | 5 | 1 |
| reset count | 5 | 5 |
| cleanup count | 5 | 1（循环结束） |
| isolation claim | 每 Run 独立 temp root/process | 同一 root，靠 reset + verify |
| contamination detection | 通过独立 root 观察 | 主动 partial reset 被检测并 quarantine |
| formal container proof | 本轮已由独立 Docker 样本提供 | 本轮未验证为默认模型 |

完整阶段 latency、每次 lifecycle、状态快照和失败证据见 [reviewed-evidence.json](reviewed-evidence.json)；数值受 Windows 文件系统、Node child-process 启动和当前机器负载影响，不能推导 QPS 或生产恢复 SLA。`resource` 只记录 probe 进程 RSS 粗粒度变化，不是容器资源测量。

## Failure matrix

| Failure | 观察结果 | Agent Quality |
| --- | --- | --- |
| reset failure | Environment `ERROR`，quarantine | 不进入 |
| readiness timeout | Environment `ERROR`，quarantine | 不进入 |
| initial-state mismatch | Environment `INVALID`，quarantine | 不进入 |
| previous Run contamination | Run B `INVALID`，fail closed，quarantine | 不进入 |
| persistent shared state | 新 container 读到旧 volume state，`INVALID`，quarantine | 不进入 |
| cleanup unverified | Environment quarantine，拒绝 READY re-entry | 不计为 Agent FAIL |
| verifier contract invalid | Harness `INVALID` | 不进入 |

`ready` 只说明 provider instance 可响应；`verified_initial_state` 才说明实际状态与 seed 相等。所有错误均不伪装成 Agent FAIL，且没有自动 whole-run retry。

## Recommendation and boundary

RPF-02 现在可以标记为 `Complete`，但关闭范围是 **Prototype-level minimum Environment contract**。首个 Prototype 采用 **Fresh-per-run 的执行语义**：每个 Run 必须拥有可识别 environment identity、seed/revision、可信 provenance、明确的 mutable-state ownership 和独立可回收的状态所有权；readiness 与 initial-state verification 必须分离。

Reuse-and-reset 暂不作为首个 Prototype 默认语义。未来可在明确 snapshot/restore、volume ownership、reset verification、quarantine 和恢复成本后作为优化 provider；其存在不改变 `UNKNOWN_OUTCOME → reconcile` 约束，也不自动赋予 Run retry 权限。Docker 证据支持的是执行语义与合同，不是永久 Docker 绑定。

本 Spike 没有修改 `DECISIONS.md`：推荐的是执行语义，不是对 Docker、Node、Java/Python 或具体编排工具的永久决定。TU-002 已获得 Prototype 级最小合同证据，但不等于 production-grade isolation/high availability 已解决。TU-003 仍负责 Fault Injection boundary，TU-004 负责 durable worker/lease/checkpoint/recovery，TU-005 负责 Evaluation job transport，TU-008 负责 Agent integration contract。本次没有访问真实 production resource。

## 固定样本与结论边界

文档事实、`reviewed-evidence.json` 的 host reference 观测、`reviewed-docker-evidence.json` 的真实 provider 观测、程序验证结论和推荐推断分开保存。固定样本没有 secret、用户目录、异常原文或生产凭据；Docker mountpoint 已脱敏。修改任一 probe 后必须重新生成并审查对应固定样本的 `source_sha256`，不能让新源码冒认旧数据。

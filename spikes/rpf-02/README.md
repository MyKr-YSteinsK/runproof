# RPF-02 — Controlled Environment Execution and Recovery Model

结论：在当前 Windows 主机上完成了同一逻辑 Initial State 的 Fresh-per-run 与 Reuse-and-reset 参考实验。Docker CLI 29.6.1 存在，但 Docker Desktop Linux daemon 不可用；没有安装系统组件，也没有把临时目录实验升级成容器隔离证明。因此本 Spike 返回 `Partial`。

## 复现

使用 Node.js 24.16.0 内置 API，无第三方依赖。probe 每个环境使用独立临时根目录，并为每个环境操作启动独立 Node worker 进程；这是 host-process/filesystem reference isolation，便于观察所有权、reset 和 quarantine，不能替代正式容器/虚拟机隔离。

```powershell
node --test spikes/rpf-02/probe.test.mjs
node spikes/rpf-02/verify-evidence.mjs
node spikes/rpf-02/probe.mjs --run
```

第一条不访问网络或 Docker。第二条只离线验证固定样本。第三条只创建仓库临时目录中的本地模拟状态，输出写入被忽略的 `.local/rpf-02/`。固定样本为 [reviewed-evidence.json](reviewed-evidence.json)。

## Host evidence

- OS/runtime：Windows `win32`、`x64`、Node.js `v24.16.0`。
- Docker client：`Docker version 29.6.1`。
- Docker daemon：Unavailable；`docker version` 无法连接 `dockerDesktopLinuxEngine` named pipe。Docker Desktop start 尝试未在限定等待内变为 ready，随后停止等待。
- 因此没有真实 container writable layer、volume、container cleanup 或跨容器隔离证据。

## Environment contract

每个实例显式保存：

| 字段 | 语义 |
| --- | --- |
| `environment_id` | 每个实例唯一，不能从目录名推断 |
| `seed_id` / `seed_revision` | 不可变逻辑起点及其版本 |
| `provenance` | `host-process-filesystem-reference`、worker 边界和 seed digest |
| `lifecycle_state` | `UNPROVISIONED`、`PROVISIONED`、`RESET`、`READY_UNVERIFIED`、`READY_VERIFIED`、`RUNNING`、`QUARANTINED`、`CLEANED` |
| `readiness` | 服务可响应的运行信号，不等于状态可信 |
| `verified_initial_state` | 对实际 state 与 seed 的程序比较结果 |
| `observable_state` | release、revision、mutation_count、operation_id |
| `operation_receipt` | 受控 mutation 的 operation identity/status |
| `cleanup_state` / `quarantine_state` | 可复用/不可复用的明确结论与原因 |

正式 Run 只能按 `provision/acquire → restore/reset → readiness → initial-state verification → Agent/tool mutation → actual-state verification → cleanup/release` 进入。任何前三个 gate 失败都不启动 Agent；initial mismatch 是 Environment-side `INVALID`；cleanup 失败将实例 quarantine。

## 两种候选模型

### Fresh-per-run

每次 Run 创建新 environment identity、专用 temp root 和 worker process，写入相同 seed/revision，reset 后做 readiness 和 initial-state verification。Run 结束销毁该 root；失败时 quarantine 后由 harness 最终清理。5 次顺序运行全部 PASS，每次 mutation_count 都为 1；两个同时存在的实例中修改 A 后，B 仍为原始 seed。

优点是状态所有权、污染边界和 quarantine 最容易解释，失败环境不会被下一 Run 复用。代价是每次 provision/worker 创建和 cleanup 都要付成本，实际容器启动成本尚未测量。

### Reuse-and-reset

一个 identity/root/worker 生命周期中执行多次 Run；每次 Run 仍强制 reset、readiness 和 initial-state verification。5 次 sound reset 全部 PASS，且第二次不会继承第一次的 mutation。

主动注入不完全 reset 后，Run B 观察到 release-v2、revision=1、mutation_count=1，而 seed 要求 release-v1/revision=0/0；B 被 `INVALID` 阻止，实例进入 `QUARANTINED`，没有启动 Agent。

优点是可减少 acquire/cleanup 成本，适合将来明确的 snapshot/restore provider。代价是 reset correctness、残留状态和 failure recovery 都成为复用前置条件；如果共享 volume，新的 container 也不代表新的 state。当前没有 container/volume 证据支持它作为首个 Prototype 默认模型。

## Measured reference evidence

本次固定样本使用同一 seed 和同一组 invariant；每个候选 5 次 sequential cycle。以下数据来自当前开发机的 host-process/filesystem probe，只作开发决策证据，不是 production benchmark：

| 指标 | Fresh-per-run | Reuse-and-reset |
| --- | ---: | ---: |
| PASS cycles | 5/5 | 5/5 |
| provision/acquire count | 5 | 1 |
| reset count | 5 | 5 |
| cleanup count | 5 | 1（循环结束） |
| isolation claim | 每 Run 独立 temp root/process | 同一 root，靠 reset + verify |
| contamination detection | 通过独立 root 观察 | 主动 partial reset 被检测并 quarantine |
| formal container proof | 未获得 | 未获得 |

完整阶段 latency、每次 lifecycle、状态快照和失败证据见固定 JSON；数值受 Windows 文件系统、Node child-process 启动和当前机器负载影响，不能推导 QPS 或生产恢复 SLA。`resource` 只记录 probe 进程 RSS 粗粒度变化，不是容器资源测量。

## Failure matrix

| Failure | 观察结果 | Agent Quality |
| --- | --- | --- |
| reset failure | Environment `ERROR`，quarantine | 不进入 |
| readiness timeout | Environment `ERROR`，quarantine | 不进入 |
| initial-state mismatch | Environment `INVALID`，quarantine | 不进入 |
| previous Run contamination | Run B `INVALID`，fail closed，quarantine | 不进入 |
| cleanup failure | Agent/tool 已执行后，Environment `ERROR`，`FAILED_QUARANTINED`；不计入 Agent 质量失败 | 已开始，但环境不可复用 |
| verifier contract invalid | Harness `INVALID` | 不进入 |

`ready` 只说明 worker 响应；`verified_initial_state` 才说明实际状态与 seed 相等。所有错误均不伪装成 Agent FAIL，且没有自动 whole-run retry。

## Recommendation and boundary

建议首个 Prototype 采用 **Fresh-per-run 的执行语义**：每个 Run 必须拥有可识别 environment identity、seed/revision、可信 provenance 和独立可回收的状态所有权；在真实隔离 provider 不可用时应拒绝把 host reference 当作正式 Run 环境。

Reuse-and-reset 暂不作为首个 Prototype 默认语义。未来可在明确 snapshot/restore、volume ownership、reset verification、quarantine 和恢复成本后作为优化 provider；其存在不改变 `UNKNOWN_OUTCOME → reconcile` 约束，也不自动赋予 Run retry 权限。

本 Spike 没有修改 `DECISIONS.md`：推荐的是执行语义，不是对 Docker、Node、Java/Python 或具体编排工具的永久决定。TU-003 仍负责 Fault Injection boundary，TU-004 负责 durable worker/lease/checkpoint/recovery，TU-005 负责 Evaluation job transport，TU-008 负责 Agent integration contract。正式 Prototype 前仍需获得真实隔离 provider 证据；本次没有访问真实 production resource。

## 固定样本与结论边界

文档事实、`reviewed-evidence.json` 的实验观测、程序验证结论和推荐推断分开保存。固定样本没有绝对临时路径、secret、用户目录、异常原文或生产凭据。修改 probe 后必须重新生成并审查固定样本，不能让新源码冒认旧数据。

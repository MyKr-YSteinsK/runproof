# RunProof Golden Demo

[English](DEMO.md) | [简体中文](DEMO.zh-CN.md) | [README](../README.zh-CN.md)

Golden Demo 是当前 RunProof 产品边界的本地 reviewed-evidence 演示路径，适合面试或架构审查：Candidate → Evidence → Failure → Regression → Gate → Release Decision。

它不会调用 DeepSeek，不需要 Provider credential，不创建云资源，不连接真实 Production，也不执行 release/deploy。

## 前置条件

- Windows、Docker Desktop，以及现有可用的 `postgres:16-alpine` image。
- Java 17+、Maven、Python 3.11+ 和 Node.js/npm。
- PostgreSQL、Control Plane 与 Vite 所需的本地端口可用。

Demo 使用仓库内 reviewed corpus，不需要 `DEEPSEEK_API_KEY`。

## 启动、查看、停止和恢复

启动正式 Control Plane、幂等 seed reviewed artifacts 并启动 Web：

```powershell
powershell -ExecutionPolicy Bypass -File demo/start-demo.ps1
```

打开 <http://127.0.0.1:4173/overview>。启动脚本会 fresh package 正式 `control-plane/`，启动或恢复 Demo-owned PostgreSQL resource，通过正式 HTTP/JSON client seed，然后 read back canonical metadata 和 verified artifacts，最后以 API-backed mode 启动 Vite。

停止但保留 named volume、reviewed artifact copies 和本地 Demo state：

```powershell
powershell -ExecutionPolicy Bypass -File demo/stop-demo.ps1
```

再次执行同一个 start 命令即可恢复。重复 seed 应该产生 idempotent replay，而不是重复的 canonical record。

在确认资源可删除后，只删除 exact、Demo-owned resource 和本地副本：

```powershell
powershell -ExecutionPolicy Bypass -File demo/stop-demo.ps1 -RemoveData
```

没有当前 ownership label 的 legacy resource 会对 destructive removal fail closed。普通 stop 保留数据；RemoveData 不是通用 Docker cleanup 命令。

## 生命周期合同

Windows lifecycle probe 检查 child-specific environment、worker `--allowed-root` containment、state-v2 process/session identity、foreign process/port/container negative、启动 rollback、restart、stop 和 ownership-gated `RemoveData`：

```powershell
powershell -ExecutionPolicy Bypass -File demo/verify-lifecycle.ps1 -Mode contracts
powershell -ExecutionPolicy Bypass -File demo/verify-lifecycle.ps1 -Mode lifecycle
```

Web child 只得到自己的 read boundary；Worker 只得到 worker boundary 和显式 IO roots；本地 state/log/bundle 不能保存 credential。这是 Windows 本机生命周期检查，不是 OS sandbox 或 Production isolation 声明。

## 要展示的三个故事

### 1. Incident remediation 与 Failure Intelligence

Incident Remediation Agent 在外部 dependency 不健康时看到一个 symptom。known-bad 版本误判 incident，并执行 harmful local remediation。受控环境暴露 violated invariant；失败被复现为 Failure Case，经确定性 Failure Intelligence 聚类后晋升为 Regression。fixed candidate 会先观察 dependency，再安全停止。

这个故事说明 Agent `FAIL` 为什么不同于 platform `ERROR`，exact identity 与 structural family 为什么要分离，以及分析结果为什么不会自动 promotion 或 release。

### 2. 副作用后的 response loss

副作用已经成功，但 worker 与 operation boundary 之间的 response 丢失：

```text
effect succeeds → response lost → UNKNOWN_OUTCOME
→ RECONCILE_REQUIRED → receipt/state 证明一次 effect
→ recovered PASS，effect count = 1
```

Worker 不会盲目 retry。response-lost Run、operation identity、reconcile evidence 和最终 State Diff 都可以调查。

### 3. Statistical Reliability 与 safety precedence

Statistical surface 包含受控的 Stable、Flaky、Safety 和 Evidence-poor cohort。展开 trial matrix，解释 valid Agent denominator、attempted/evidence denominator、Wilson interval、`OBSERVED_FLAKY` 和 zero-tolerance safety precedence。高 pass rate 不能覆盖 safety event 或 evidence 不足。

### 4. 正式多服务网络故障 slice

RPF-28 正式 Environment 是独立于 Golden Demo UI 的工程探针。它启动 fresh internal Docker network，包含 target、dependency、Toxiproxy boundary 和 Agent-shaped client，然后证明 baseline、dependency-unavailable 以及 response-lost 的 receipt/effect-count 语义。运行本机完整矩阵：

```powershell
python spikes/rpf-28/probe.py --run
python spikes/rpf-28/verify-evidence.py .local/rpf-28/rpf28-formal-result.json
```

本机 probe 每类 profile 重复五次，并运行独立 PostgreSQL/Control Plane/durable-worker 路径。Hosted CI 只聚焦 baseline、response-loss 和 cleanup；它不是 canonical Release Gate，也不执行 release/deploy。

## 推荐路径

1. **Overview**：沿 Candidate → Evidence → Failure → Regression → Gate，确认两个显式 Agent。
2. **Statistical**：查看四个 cohort 和 interval-aware Comparison。
3. **Failure Intelligence**：打开 Incident family、exact Failure Case、first divergence 和 Version Bisect。
4. **Durable execution**：打开 response-lost Run，展示 reconcile-before-retry。
5. **Release Decision**：展示 `ELIGIBLE` 只是只读决策结果，不是 deploy 按钮。

常用路由：

| Surface | Route |
|---|---|
| Overview | `/overview` |
| Agents | `/agents` |
| Statistical evaluations | `/statistical-evaluations` |
| Statistical comparisons | `/statistical-comparisons` |
| Failure Intelligence | `/failure-intelligence` |
| Version Bisects | `/version-bisects/version-bisect-8ad1ee6051c564080255` |
| Release Decisions | `/release-decisions` |
| Executions | `/executions` |

Control Plane 停止时，Overview 必须显示 canonical data unavailable，不能静默展示 fixture data。恢复正式服务后重新执行 start/seed path，即可恢复 API-backed view。

## Integrity 与 evidence

版本化 profile 冻结 Demo identity、两个 Agent identity、reviewed corpus refs、artifact/source hash、预期断言以及 no-Provider/no-cloud/no-release 边界：

- `demo/rpf-19-golden-demo-v1.json`
- `demo/verify-golden-demo.py --root . --json`
- `demo/seed_demo.py --root . --repeat 2 --json`

正式 Control Plane、PostgreSQL durable worker、reviewed RPF-16/RPF-17/RPF-18 corpus 和 hosted Release Gate 提供页面背后的证据。历史 source identity 与 hosted run link 集中见 [VERIFICATION_HISTORY.zh-CN.md](history/VERIFICATION_HISTORY.zh-CN.md)。

## 当前限制

Demo 是本地/面试交付面，不是 Production deployment。它不证明 managed PostgreSQL HA、object-storage durability、多主机 supervisor、human Approval、tenant/RBAC identity、broker/scheduler/autoscaling、live Provider probability 或真实破坏性 remediation。Web build 仍可能报告 shared-bundle size warning；这与 evidence 和 authority contract 是两个不同问题。

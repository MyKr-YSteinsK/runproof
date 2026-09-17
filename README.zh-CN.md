# RunProof

[English](README.md) | [简体中文](README.zh-CN.md)

RunProof 是一个 **Agent Reliability & Release Engineering Platform**。它把 Agent 行为、状态迁移、失败和发布证据变成可调查的工程资产，而不是把一次评测分数当作产品全部。

## 它是什么

RunProof 将 Candidate Agent Version 连接到有状态评测、可观察轨迹与环境状态、确定性证据、失败调查、回归历史、统计可靠性以及只读的 Quality Gate 决策。

它不只是普通的通用评测运行器：

- 它包含两个显式的参考 Agent：`Production Change` 与 `Incident Remediation`。
- 它把 Agent 行为与平台/环境故障分开建模。
- 它将 `UNKNOWN_OUTCOME` 和 `RECONCILE_REQUIRED` 作为一等安全状态。
- 它保留原始证据与 canonical identity，同时让派生调查和统计结论可追溯。
- 它绝不把 `ELIGIBLE` 当成 deploy 或 release 授权。

## 为什么存在

Agent 可能返回看似合理的答案，却把环境留在错误状态、误判外部依赖，或在副作用已经发生后丢失响应。RunProof 让这些情况可以复现、审查和复用：人可以沿着 Candidate → Failure → Regression → Gate → 最终决策边界追踪证据。

## 核心闭环

```text
Candidate Agent Version
        ↓
Stateful Evaluation
        ↓
Run / Trajectory / State Diff
        ↓
Failure Investigation
        ↓
Failure → Regression
        ↓
Failure Intelligence
        ↓
Statistical Reliability
        ↓
Quality Policy
        ↓
Release Decision（只读决策）
```

`ELIGIBLE` 只表示在当前证据范围内，策略评估没有发现阻断条件。它不会发布产品、部署服务，也不会向 Agent、worker 或 runtime 授予权限。

## Golden Demo

本地 Golden Demo 是查看产品面的最短路径。它使用 reviewed evidence、正式 Control Plane、PostgreSQL canonical metadata、不可变本地 artifact store 和 durable worker。不需要 Provider credential 或云账号，也不会连接真实 Production 系统。

```powershell
powershell -ExecutionPolicy Bypass -File demo/start-demo.ps1
```

打开 <http://127.0.0.1:4173/overview>。五到十分钟的完整路径见 [docs/DEMO.zh-CN.md](docs/DEMO.zh-CN.md) 和 [docs/DEMO.md](docs/DEMO.md)。

## 有证据支持的边界

### 当前范围内已证明

- 面向只读调查的 Desktop Web Control Plane。
- Java/Spring Control Plane、PostgreSQL canonical metadata 与 HTTP/JSON 边界。
- 不可变、经验证的 artifact 引用和 append-only decision history。
- Python Agent/Evaluation Runtime 与 PostgreSQL poll/claim durable worker。
- 有状态 Controlled Simulation、失败复现、Regression 晋升、Failure Intelligence 与统计 trial 语义。
- 能记录 canonical evidence 并回读决策的 hosted GitHub Actions Release Gate。
- 带有显式子进程 ownership 和 fail-closed 清理检查的 Windows 本地 Golden Demo 生命周期。

### 未声明或未授权

仓库不声明 Production HA、托管云部署、S3 durability、human Approval service、OAuth/OIDC/SSO、多租户 RBAC、broker/scheduler/autoscaling、真实破坏性 Production remediation 或长期 live Provider probability。当前任何 Agent、worker 或 `ELIGIBLE` Decision 都不能执行 release 或 deploy。

## 公共文档

| 用途 | English | 简体中文 |
|---|---|---|
| 架构与边界 | [ARCHITECTURE.md](docs/ARCHITECTURE.md) | [ARCHITECTURE.zh-CN.md](docs/ARCHITECTURE.zh-CN.md) |
| Reliability 语义 | [RELIABILITY_MODEL.md](docs/RELIABILITY_MODEL.md) | [RELIABILITY_MODEL.zh-CN.md](docs/RELIABILITY_MODEL.zh-CN.md) |
| 本地 Golden Demo | [DEMO.md](docs/DEMO.md) | [DEMO.zh-CN.md](docs/DEMO.zh-CN.md) |
| 技术术语表 | [GLOSSARY.md](docs/GLOSSARY.md) | [GLOSSARY.zh-CN.md](docs/GLOSSARY.zh-CN.md) |
| 验证历史 | [VERIFICATION_HISTORY.md](docs/history/VERIFICATION_HISTORY.md) | [VERIFICATION_HISTORY.zh-CN.md](docs/history/VERIFICATION_HISTORY.zh-CN.md) |
| 能力历史 | [CAPABILITY_HISTORY.md](docs/history/CAPABILITY_HISTORY.md) | [CAPABILITY_HISTORY.zh-CN.md](docs/history/CAPABILITY_HISTORY.zh-CN.md) |

canonical governance 文件不复制为翻译副本：[AGENTS.md](AGENTS.md)、[PROJECT_BRIEF.md](docs/project/PROJECT_BRIEF.md)、[DECISIONS.md](docs/project/DECISIONS.md) 和 [CURRENT_STATE.md](docs/project/CURRENT_STATE.md)。`CURRENT_STATE.md` 只保存当前快照；历史验证放在 `docs/history/`。

## 验证入口

轻量公共文档合同使用下面的命令校验：

```powershell
python ci/verify-public-docs.py
```

仓库主要检查仍然是：

```powershell
npm test
npm run typecheck
npm run build
python -m unittest discover -s runtime/tests -p 'test_*.py' -v
python runtime/verify-reviewed-artifacts.py
mvn -q test package -f control-plane/pom.xml
python demo/verify-golden-demo.py --root . --json
python ci/run_release_gate.py
```

最后一个命令在 Docker/Java/Python 前置条件可用时创建一次 fresh local canonical gate；它不授权也不执行 release。

## 仓库地图

- [control-plane/README.md](control-plane/README.md)：正式 Java/Spring Control Plane 与 API 边界。
- [runtime/README.md](runtime/README.md)：Python runtime、evidence、evaluation 和 worker 入口。
- [web/README.md](web/README.md)：Web read model 与 presentation 实现。
- [demo/](demo/)：Golden Demo profile、seed、生命周期和 verifier。
- [spikes/](spikes/)：disposable 调查与历史合同 probe，不是 Production 声明。
- [docs/project/](docs/project/)：canonical product brief、decisions 和 current state。

当前生命周期为 `Stabilization`。产品版本、部署与 release 状态只由 canonical project state 和已验证的交付证据报告。

# RunProof

RunProof（`RPF`）是一个 **Agent Reliability & Release Engineering Platform**，目标是让 Agent 行为、验证结果与发布判断以证据为先、可追踪并可复核。

## 当前状态

- 生命周期：`Discovery`
- 仓库状态：已完成本地 Git bootstrap，主分支为 `main`
- 当前实现：仅包含仓库规则、项目说明与 Project State；尚未实现产品运行时或产品功能
- 交付状态：尚未配置 remote、upstream、CI、部署或发布 endpoint
- 安全边界：v1 的 destructive/live side effect 只能发生在 Controlled Production Simulation Environment；不接入真实生产 destructive credentials

## Reliability Loop（产品方向）

```text
Candidate
  → Evaluation
  → Controlled Environment
  → Trajectory / Evidence
  → deterministic verification
  → Failure / Regression
  → Baseline / Candidate
  → Quality Policy
  → Release Gate
```

上图表达产品方向，不代表这些能力已经在本仓库实现。

## v1 边界

- Primary human surface 是 Desktop Web Control Plane；CLI、Programmatic API、CI 是 automation surfaces。
- 首个 reference agent 是 Production Change Agent，首个真实 LLM provider 是 DeepSeek；DeepSeek 不是平台身份。
- 真实 Production destructive operation、PWA/mobile、通用 Agent Framework/Marketplace 不属于 v1。
- React + TypeScript Web、Java/Spring Boot Control Plane、Python Agent/Evaluation Runtime、PostgreSQL 等只是待调查的推荐方向，不是本 bootstrap 已锁定的实现。

项目的稳定意图、决策与当前真实状态分别记录在 [`docs/project/PROJECT_BRIEF.md`](docs/project/PROJECT_BRIEF.md)、[`docs/project/DECISIONS.md`](docs/project/DECISIONS.md) 与 [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md)。仓库执行规则见 [`AGENTS.md`](AGENTS.md)。

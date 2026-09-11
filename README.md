# RunProof

RunProof（`RPF`）是一个 **Agent Reliability & Release Engineering Platform**：通过状态化评测、故障注入、失败回归化、证据可视化和发布门禁，把 Agent Failure 变成可重现、可验证、可持续复用的工程资产。

## 仓库入口

仓库包含 bootstrap 文档、[RPF-01 disposable DeepSeek probe](spikes/rpf-01/README.md) 和 [RPF-02 controlled-environment probe](spikes/rpf-02/README.md)，尚无正式产品运行时。当前生命周期、任务与远端交付事实以 [CURRENT_STATE](docs/project/CURRENT_STATE.md) 为准；产品能力描述仍是目标合同，probe 不等于产品实现。

- [PROJECT_BRIEF](docs/project/PROJECT_BRIEF.md)：稳定产品意图、v1 Reliability/UX 合同与边界。
- [DECISIONS](docs/project/DECISIONS.md)：继承 Bootstrap canonical D-001～D-012 的有效决定。
- [AGENTS](AGENTS.md)：仓库执行、安全和 Git/delivery 规则。
- RPF-02 已取得 Docker provider 的 Prototype-level minimum Environment 证据；不代表 production-grade isolation/HA，也不把 Docker 固化为产品身份。

## 核心方向

Candidate → Evaluation Suite → Controlled Stateful Environment → Trajectory / State / Evidence → deterministic verification → Failure Investigation / Regression → Baseline vs Candidate → Quality Policy → Release Gate。

Desktop Web Control Plane 为 Primary human surface；CLI / Programmatic API / CI 为 automation surfaces。Production Change Agent 为首个 reference agent，DeepSeek 为首个 Provider；平台身份保持独立。

v1 Agent 有副作用 Tool 仅操作 Controlled Production Simulation Environment，不连接真实生产 destructive credentials。技术栈是待 Investigation/Spike 验证的推荐方向；正式产品范围与非目标见 PROJECT_BRIEF。

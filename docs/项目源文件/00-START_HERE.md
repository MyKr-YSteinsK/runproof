# RunProof 接管与 GPT Project 启动

2026-11-23，项目孵化器 **Upgrade Existing Project** 模式。目标仓库 `MyKr-YSteinsK/runproof`，默认 `main`。本轮落地现行入口、历史整理和兼容性重构。升级案已写成待评审材料，产品路线和实施范围由用户确认。

## 新建 GPT Project

1. 新建名为 **RunProof** 的 Project，将 [PROJECT_INSTRUCTIONS.md](PROJECT_INSTRUCTIONS.md) 全文粘贴进项目指令。
2. 上传 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) 与 [RUNBOOK.md](RUNBOOK.md)。要在新 Project 里做路线评审，再上传 [UPGRADE_REVIEW.md](UPGRADE_REVIEW.md) 与 [PORTFOLIO.md](PORTFOLIO.md)。如果当前对话无法直读 GitHub，需要精确合同、决定或状态时，从同一提交上传 [PROJECT_BRIEF](../project/PROJECT_BRIEF.md)、[DECISIONS](../project/DECISIONS.md) 或 [CURRENT_STATE](../project/CURRENT_STATE.md)。
3. 全局指令独立应用。[GPT 网页全局自定义指令](全局指令/GPT全局自定义指令.txt) 粘贴到账号的全局自定义指令栏。[Codex 全局 AGENTS](全局指令/Codex全局AGENTS.md) 供检查或手动同步到所用 Codex 实例的全局规则。两份原文均来自 `ai-workflow-assets@750c69673ccaeac9b5999f3b38b8ebc11abebc24`，仓库内副本供交付和版本核对。项目根的 [AGENTS.md](../../AGENTS.md) 已单独落地。
4. 新聊天先确认能读到 `PROJECT_CONTEXT.md`、`RUNBOOK.md` 的具体正文以及生效版本。保留活动附件与当前提交的关联，核对新版本可读后停用旧版。仓库更新后由用户同步 GPT Project。

首条消息可直接复制：

> 这是 RunProof 的接管后项目。先读 PROJECT_CONTEXT.md 和 RUNBOOK.md，能访问 GitHub 时核对 MyKr-YSteinsK/runproof 的 main 与最新 CURRENT_STATE。请区分现有证据与 UPGRADE_REVIEW 中待我确认的方案。先评审配置变更 Agent 作为下一条主线的价值、风险和最小验收；已有批准的维护工作可由 Codex 直接继续。

## 从仓库恢复

| 用途 | 有效入口 |
| --- | --- |
| 执行权限与恢复 | 根 [AGENTS.md](../../AGENTS.md) |
| 产品目标与长期边界 | [PROJECT_BRIEF](../project/PROJECT_BRIEF.md) |
| 决定和批准身份 | [DECISIONS](../project/DECISIONS.md) |
| 实现、证据、风险 | [CURRENT_STATE](../project/CURRENT_STATE.md) |
| 历史合同与可恢复证据 | [维护归档](../history/MAINTENANCE_ARCHIVE.md) |
| 本轮本机清理 | [待清理清单](../delete/README.md) |

在目标工作区打开 Codex 可直接使用短 Prompt 继续。跨对话移交复杂任务时，获授权的公开 Plan 用目标仓库 Issue 正文，受限 Plan 用授权的私有或本地渠道。查看完整正文后执行。混合来源或多任务由同一 Codex 对话对齐来源、修订、依赖和运行资源。

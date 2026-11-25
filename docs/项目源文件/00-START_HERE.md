# RunProof 新对话恢复与 GPT Project 同步

RunProof 已在 `MyKr-YSteinsK/runproof` 落地，常规交付分支为 `main`。新对话先从当前仓库状态恢复，再接续用户交付的任务。此入口按 `MyKr-YSteinsK/ai-workflow-assets@f50e2b1682af21842a730f20c8533cbc3372a72f` 的项目孵化器 03–06 同步。

## 同步 GPT Project

1. 在 RunProof Project 中，从同一完整 Git 提交上传 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)、[CURRENT_STATE.md](../project/CURRENT_STATE.md) 和 [RUNBOOK.md](RUNBOOK.md)。
2. 将同一提交的 [PROJECT_INSTRUCTIONS.md](PROJECT_INSTRUCTIONS.md) 全文粘贴进项目指令。
3. 需要按原文核对产品合同、长期决定或取证时，可从同一提交补充 [PROJECT_BRIEF.md](../project/PROJECT_BRIEF.md)、[DECISIONS.md](../project/DECISIONS.md) 或 [RPF-120 结果](../../spikes/rpf-120/RESULT.md)。路线评审和作品组合按需使用 [UPGRADE_REVIEW.md](UPGRADE_REVIEW.md) 和 [PORTFOLIO.md](PORTFOLIO.md)。
4. 在新对话核对三份源文件的实际正文和来源提交。GitHub 正文可读时，检查远端 `main` 并按实际提交读取当前状态。无法读取时使用用户指定的同提交附件，说明哪些事实尚未核实。确认新版可读后停用同名旧附件。后续仓库版本由用户手动同步到 Project。

首条消息可直接复制：

> 这是 RunProof 的续接对话。先读 PROJECT_CONTEXT.md、CURRENT_STATE.md 和 RUNBOOK.md。能读 GitHub 正文时，核对 MyKr-YSteinsK/runproof 的 main 与该提交的 CURRENT_STATE.md。用一段话说明当前基线、已有证据和未解决事项，再接续我交付的任务。分别说明 RPF-120 本机复验的范围，以及目标提交的产品 CI 和 Canonical Gate。当前优先完善 RunProof 自身，config-center 联动保留为待评审候选。已授权的维护可由 Codex 直接继续。

## 从仓库恢复

| 用途 | 有效入口 |
| --- | --- |
| 执行权限与恢复 | 根 [AGENTS.md](../../AGENTS.md) |
| 产品目标与长期边界 | [PROJECT_BRIEF](../project/PROJECT_BRIEF.md) |
| 决定和批准身份 | [DECISIONS](../project/DECISIONS.md) |
| 实现、证据、风险 | [CURRENT_STATE](../project/CURRENT_STATE.md) |
| 历史合同与可恢复证据 | [维护归档](../history/MAINTENANCE_ARCHIVE.md) |
| 既有本机待清理记录 | [待清理清单](../delete/README.md) |

在目标工作区打开 Codex 可直接使用短 Prompt 继续。跨对话移交复杂任务时，获授权的公开 Plan 用目标仓库 Issue 正文，受限 Plan 用授权的私有或本地渠道。查看完整正文后执行。混合来源或多任务由同一 Codex 对话对齐来源、修订、依赖和运行资源。

账号级指令可独立核对或手动同步。仓库保留来自 `ai-workflow-assets@750c69673ccaeac9b5999f3b38b8ebc11abebc24` 的 [GPT 网页全局自定义指令](全局指令/GPT全局自定义指令.txt) 和 [Codex 全局 AGENTS](全局指令/Codex全局AGENTS.md) 副本。

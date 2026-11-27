# RunProof 新对话恢复与 GPT Project 同步

RunProof 已在 `MyKr-YSteinsK/runproof` 落地，常规交付分支为 `main`。新对话先从当前仓库状态恢复，再接续用户交付的任务。此入口按 `MyKr-YSteinsK/ai-workflow-assets@f50e2b1682af21842a730f20c8533cbc3372a72f` 的项目孵化器 03–06 同步。

## 同步 GPT Project

1. 按导出清单核对完整 Git 提交与摘要，上传 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)、[CURRENT_STATE.md](../project/CURRENT_STATE.md)、[RUNBOOK.md](RUNBOOK.md)、[接手索引](HANDOFF_INDEX.md) 和本入口。从同一提交取文件。
2. 将同一提交的 [PROJECT_INSTRUCTIONS.md](PROJECT_INSTRUCTIONS.md) 全文粘贴进项目指令。此操作由用户在 RunProof Project 内执行。
3. 需要原始合同、决定、候选评审或报告时按清单补充附件。摘要一致的 [PROJECT_BRIEF.md](../project/PROJECT_BRIEF.md)、[DECISIONS.md](../project/DECISIONS.md)、[UPGRADE_REVIEW.md](UPGRADE_REVIEW.md) 和 [PORTFOLIO.md](PORTFOLIO.md) 可沿用。[RPF-126 验收](../../spikes/rpf-126/RESULT.md) 与 [RPF-127 收口](../../spikes/rpf-127/RESULT.md) 提供本次证据边界。
4. 在新对话核对入口、状态和 Runbook 的实际正文、来源提交及阶段验收状态。GitHub 正文可读时检查远端 `main`，并分开报告导出版本与当前远端版本。无法读取时使用用户指定的同提交附件，说明哪些事实尚未核实。确认新版可读后移除同名旧附件。

首条消息可直接复制：

> 这是 RunProof 的阶段验收对话。先读 HANDOFF_INDEX.md、PROJECT_CONTEXT.md、CURRENT_STATE.md 和 RUNBOOK.md，按导出清单核对完整 SHA。能读 GitHub 时另核对远端 main 与目标提交的产品 CI、Canonical Gate 和实际 checkout。用一段话说明 RPF-126 已验收的范围、RPF-127 保全结果、初赛实投尚未核实的内容，以及当前仍阻塞的门禁。停在阶段验收，等我确认下一步。复赛改造和 config-center 联动仍待我决定。

## 从仓库恢复

| 用途 | 有效入口 |
| --- | --- |
| 执行权限与恢复 | 根 [AGENTS.md](../../AGENTS.md) |
| 产品目标与长期边界 | [PROJECT_BRIEF](../project/PROJECT_BRIEF.md) |
| 决定和批准身份 | [DECISIONS](../project/DECISIONS.md) |
| 实现、证据、风险 | [CURRENT_STATE](../project/CURRENT_STATE.md) |
| 当前离线候选、CI 与证据边界 | [接手索引](HANDOFF_INDEX.md) |
| 历史合同与可恢复证据 | [维护归档](../history/MAINTENANCE_ARCHIVE.md) |
| 既有本机待清理记录 | [待清理清单](../delete/README.md) |

在目标工作区打开 Codex 可直接使用短 Prompt 继续。跨对话移交复杂任务时，获授权的公开 Plan 用目标仓库 Issue 正文，受限 Plan 用授权的私有或本地渠道。查看完整正文后执行。混合来源或多任务由同一 Codex 对话对齐来源、修订、依赖和运行资源。

账号级指令可独立核对或手动同步。仓库保留来自 `ai-workflow-assets@750c69673ccaeac9b5999f3b38b8ebc11abebc24` 的 [GPT 网页全局自定义指令](全局指令/GPT全局自定义指令.txt) 和 [Codex 全局 AGENTS](全局指令/Codex全局AGENTS.md) 副本。

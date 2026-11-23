# RunProof 维护归档

2026-11-23 接管归档。现行入口为 [AGENTS.md](../../AGENTS.md)，当前结论在 [CURRENT_STATE](../project/CURRENT_STATE.md)。用下列入口查历史来源、验收范围和可恢复的版本。

| 历史阶段 | 仍有价值的成果 | 证据入口 |
| --- | --- | --- |
| RPF-00～39，原 RunProof | Production Change、Incident Remediation、Failure → Regression、Baseline/Candidate、decision-only Gate，以及 Java/Python/Web 的 canonical 读取路径 | [能力历史](CAPABILITY_HISTORY.zh-CN.md) · [验证历史](VERIFICATION_HISTORY.zh-CN.md) · [任务索引](RPF_EXECUTION_INDEX.md) |
| RPF-40～81，EffectWitness 研究 | 三份合同、双业务域、权威读回、Proof-Guided Exploration 和 Witness 验证。RPF-74 的 UNKNOWN 后再预约是必须保留的反例，后续隔离实验各有适用条件 | [RPF-74](../../spikes/rpf-74/README.md) · [RPF-79 固定快照](https://github.com/MyKr-YSteinsK/runproof/tree/b076d2c4206683ba96eb8ffc6ae2cd290074af0c/docs/effectwitness-migration/2026-10-29-rpf79) |
| RPF-82～99，集成与治理 | 历史契约分层、旧 CI 覆盖缺口、只读工作台、JiuwenSwarm MCP 实际调用。RPF-96 保持本地未交付，RPF-98 的 Router 结果属于当次 CI | [RPF-95/rev-2](../../spikes/rpf-95/rev-2/RESULT.md) · [RPF-97 清理审查](../../spikes/rpf-97/governance-audit.md) · [RPF-98/rev-3](../../spikes/rpf-98/rev-3/RESULT.md) |
| RPF-100～110，受控产品与真实 Explorer 尝试 | 受限 Controller、实验接缝、可携带证据与 Provider 预发送边界。历史 live 尝试有失败回执，后续 parser 修订进行离线验证 | [RPF-108](../../spikes/rpf-108/RESULT.md) · [RPF-110/rev-3](../../spikes/rpf-110/rev-3/RESULT.md) |
| RPF-111～114，竞赛演示 | 同一解包会话的两域收据、有界故障、独立读回和 Witness，另有报告、截图和工程包清单。项目包、材料与门户提交各有独立状态 | [RPF-112](../../spikes/rpf-112/RESULT.md) · [RPF-113](../../spikes/rpf-113/RESULT.md) · [RPF-114](../../spikes/rpf-114/RESULT.md) · [材料清单](../../spikes/rpf-114/DELIVERABLES.md) |

## RPF-79 迁移包

原目录 `docs/effectwitness-migration/2026-10-29-rpf79/` 有 21 个文件。现行维护文件接替旧启动、Plan 和治理入口，全部原件按原路径结构移入本地 `docs/delete/2026-11-23/docs/effectwitness-migration/`。迁移前后逐文件 SHA-256 一致。Git 历史可恢复原路径，历史账本仍按其固定提交解析 source map。以 [完整固定快照](https://github.com/MyKr-YSteinsK/runproof/tree/b076d2c4206683ba96eb8ffc6ae2cd290074af0c/docs/effectwitness-migration/2026-10-29-rpf79) 核验历史哈希、链接与内部引用。

- `01-PROJECT_BRIEF.md`、`02-REQUIREMENTS.md` 和 `03-DECISIONS.md` 保存原批准竞赛目标、R-01～R-10、MUST/SHOULD/NON-GOAL、D-COMP 和 COMP-03 的完整措辞。后续取舍以用户新的决定为准。
- 两份 `05-*` 保存实验协议和 UX baseline。旧 owner、预算、阶段和执行顺序只在对应历史试验范围解释。
- `MIGRATION_MANIFEST.json`、`SOURCE_EVIDENCE_INDEX.json`、`RPF79_RESULT.md` 和 `spikes/rpf-82/integration-ledger.json` 提供来源、路径和验收记录。

Git 本地读取示例：

```powershell
git show 'b076d2c4206683ba96eb8ffc6ae2cd290074af0c:docs/effectwitness-migration/2026-10-29-rpf79/02-REQUIREMENTS.md'
```

## 清理范围

本轮移走 RPF-79 旧快照和已核验可重建的生成物，清单在 [待清理目录](../delete/README.md)。旧 CI 结果、已注册 Git worktree、所有 `spikes/` 历史证明、reviewed artifacts、旧本机业务账本、未提交研究和保护范围继续留在原处。

后续若考虑缩减 `spikes/` 或版本化 Runtime，实现审计至少追踪包入口和动态导入、Web fixture、测试与 workflow、归档验证器和固定 source identity。针对确认退役的路径出具清单，验收引用或构建替代路径，并由用户确认迁移范围。

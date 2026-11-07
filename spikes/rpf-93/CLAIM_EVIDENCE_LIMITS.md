# 主张、证据与限制

基线 `0dee6283f9a1c3a54edd79f78aabee784d562648`；历史材料是记录，不代表本轮新执行。固定链接指向对应源版本；哈希及离线验证不构成第三方签名。

| 主张 / 页面 | 来源和证据等级 | 范围及限制 |
| --- | --- | --- |
| 业务效果区别于工具返回（2） | [RPF-60 历史 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/RESULT.md)；历史实验 | 情景说明，不代表生产系统。 |
| 三合同及权限分离（3） | [项目合同](https://github.com/MyKr-YSteinsK/runproof/blob/0dee6283f9a1c3a54edd79f78aabee784d562648/docs/project/PROJECT_BRIEF.md)；产品合同/目标 | 不是所有目标均已实现或验收。 |
| Explorer、Target、Authority、Oracle、反馈与 Witness（4） | [RPF-60 历史 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/RESULT.md)；历史记录 | 有界会话；不得推广为生产能力。 |
| 虚构订单 2500 分，PAID 到 REFUNDED、一张退款记录（5） | [RPF-60 历史 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/RESULT.md)；fresh SQLite 当时只读验证 | 订单 Target 确定性执行，不是第二个真实 LLM Target。 |
| Java/H2 配置 v2、GET 历史 [2,1]（6） | [RPF-60 历史 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/RESULT.md)；当时服务读回 | SDK scripted fixture；计划故障未触发；同服务 GET 不是外部数据库独立审计。 |
| 截图及探索角色（7） | [RPF-60 历史 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/RESULT.md)；`RECORDED`，session `rpf60-session-ff259b8d1bef494b` | 截图不能证明当前 live；一次会话不能证明因果或统计优势。 |
| 另一配置域真实双角色（7） | [RPF-57 历史 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-57/RESULT.md)；另一独立会话 | 不能拼接为 RPF-60 同一实验或声称已集成 JiuwenSwarm。 |
| UNKNOWN 与故障边界（8） | [RPF-92 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/0dee6283f9a1c3a54edd79f78aabee784d562648/spikes/rpf-92/RESULT.md)；当前状态报告 | RPF-74 零新 Provider 预约强化约束仍未修复验收，不声称全局安全。 |
| Recorded 和两份 Witness（9） | [RPF-92 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/0dee6283f9a1c3a54edd79f78aabee784d562648/spikes/rpf-92/RESULT.md)；本地历史证据离线重验 | ISSUER_AUTHENTICITY=NOT_ESTABLISHED；并非第三方签名或独立新环境复现。 |
| 当前运行和 CI（9） | [RPF-92 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/0dee6283f9a1c3a54edd79f78aabee784d562648/spikes/rpf-92/RESULT.md)、[Run 42375255570](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42375255570) | Golden Demo 因 Docker daemon 不可达为 UNAVAILABLE；新订单/配置 NOT_RUN。Router 676 PASS/12 ERROR/5 SKIP/539 UNAVAILABLE，具体异常未确定；非 green CI 或 release。 |
| 后续研发（10） | [RPF-92 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/0dee6283f9a1c3a54edd79f78aabee784d562648/spikes/rpf-92/RESULT.md)；建议 | 计划不是已验证效果，无统计或因果优势结论。 |

本次未启动 Provider、SDK、Gateway、业务实验、Docker 或 Golden Demo；没有新的 Run ID。R-01～R-10 均仍为目标，不由该材料自动完成。

# 首轮创意提交草案｜RunProof EffectWitness

> 状态：`SUBMISSION_PREPARED / NOT_SUBMITTED`。这里不填报名人姓名、联系方式、学校/单位、团队成员、项目链接账号或任何个人资料。公开公告中的截止日期为 2026-10-30；精确时刻、时区和登录页最终字段仍待用户核实。

## 建议填报内容

### 作品名称

**RunProof EffectWitness｜让智能体行动可验证**

英文备选：**RunProof EffectWitness — Verifiable Outcomes for Agent Actions**

### 项目简介（短版）

RunProof EffectWitness 面向会调用工具、改变业务状态的 AI Agent。在受控模拟中，它记录 Agent 的工具选择，由独立 Authority 与确定性 Oracle 核验实际状态和收据，并把有界 Witness 交给离线 verifier 检查。一次成功或一次故障不会被包装成普遍可靠性结论。

### 项目简介（长版）

Agent 能调用工具，不代表任务结果已经可信。请求可能超时，但退款或配置变更已提交；只看模型回复或日志也无法确认系统最后处于什么状态。RunProof EffectWitness 把“Agent 选择了什么、受控业务实际发生什么、独立验证器能证明到哪里”放在同一条可审查路径中。

在受控的本地模拟中，Agent 通过 Tool Call 选择动作。独立 Authority 从业务存储读回操作前后状态与唯一收据，确定性 Oracle 按预先固定的业务合同核验结果。若调用响应丢失，流程通过收据对账确认已提交状态，而不是盲目重试。已生成的 Witness 可以脱离原数据库和模型 API 做离线结构与内容核验；可信 hash 只能锚定文件字节，当前样本不建立签发者身份认证。

本次公开演示使用一份已提交的 RPF-46 实时研究摘要：两轮真实模型工具选择分别为 `normal` 和 `response-lost`，第一轮反馈在下一次选择之前完成验证并以相同 hash 回注。两笔订单均完成合同要求的全额退款，第二轮故障已触发并通过收据调和；未发现退款合同违规。该单次会话只支持有限机制观察和相关性结论，不证明因果、复现、一般策略优势或生产支付能力。RPF-43 订单样本和 RPF-44 运维样本是另两次独立的确定性受控运行，不属于该 Live 会话。

### 应用场景与目标用户

- **目标用户**：开发/评审会调用工具并产生状态变更的 Agent 的工程师、AI 平台与可靠性工程师。
- **优先场景建议**：Coding / 运维变更 Agent 在沙箱中执行配置更新、发布或回滚前后的结果核验。
- **演示中的第二个领域**：运维配置变更的本地受控样本，用于说明订单与运维复用同一 Witness 核心；它不是 Docker 正式接入，也不是实时运维 LLM PGE。
- **风险控制**：展示系统只操作本地虚构订单/配置，不连接真实支付、生产账号或云资源；决定发布的权限不交给被测 Agent。

### 技术方案

1. Agent 在冻结的预算和实验合同内通过固定工具调用选择受控动作。
2. 业务操作写入本机模拟环境；独立 Authority 通过只读接口获取状态差异和唯一收据。
3. 确定性 Oracle 分别判定业务合同、故障激活、归因强度和复现状态，不把它们合并成单一“AI 判断”。
4. 遇到 `UNKNOWN_OUTCOME` 时读取并调和收据；未能确定前不盲目重试。
5. Witness 记录受限来源与核验材料；独立离线 verifier 检查 schema、业务事实和调用者提供的可信文件摘要。
6. Web 演示以固定来源标记分别展示实时摘要、历史证书和实时新运行。本次 RECORDED 页面只读，不发送网络请求或创建实验。

本竞赛分支没有实现 JiuwenSwarm/WorkSwarm 集成。官方公告把 openJiuwen 的 JiuwenSwarm 列为推荐平台；本稿不会声称已经使用该平台。

### 创新点

- 把模型工具选择与独立业务状态、收据核验连起来，清楚显示反馈验证是否先于下一轮选择。
- 在响应丢失场景中以唯一业务收据调和已提交结果，避免把网络状态未知误判为操作失败并盲目重放。
- 对 Witness 的文件内容、来源锚和签发者真实性分层表达，防止“哈希通过”被误说成“官方签名”或“生产真实”。
- 对单次实验的结论主动设限：合同满足不等于发现漏洞；一次受控故障不等于复现；相关性不等于干预因果。

## 公开代码与演示入口

- 公开仓库：<https://github.com/MyKr-YSteinsK/runproof>
- 本稿对应分支：<https://github.com/MyKr-YSteinsK/runproof/tree/codex/rpf-47-competition-evidence-demo>
- 只读演示运行说明：[README.md](README.md)
- 本地页面：`http://127.0.0.2:4174/effectwitness/recorded`（按 [README.md](README.md) 的回环绑定命令启动）
- 独立样本验证：`python -B spikes/rpf-47/verify_evidence.py --root .`

该分支不是 `main`；公开默认分支和当前正式产品定位未因此改变。活动评审可查看功能分支中的源代码及来源文件。

## 英文备选简介

RunProof EffectWitness helps engineers verify outcomes produced by tool-using agents. In controlled local simulations, an independent authority reads back business state and receipts, a deterministic oracle checks a frozen contract, and an offline verifier inspects a bounded witness. The recorded RPF-46 example shows feedback validated before a second model choice and a response-lost refund reconciled from its receipt. Both recorded refunds satisfied their contract. This is one limited, correlational mechanism observation—not proof of causality, reproducibility, general policy advantage, issuer identity or production readiness.

## 官方字段映射与待填项

| 官方公开公告列出的材料 | 本目录对应内容 | 门户/用户待核实 |
| --- | --- | --- |
| 作品名称 | 本页“作品名称” | 门户字段长度、中文/英文限制 |
| 项目简介 | 短版 / 长版 | 最终字数上限、是否允许 Markdown |
| 应用场景说明 | “应用场景与目标用户” | 是否必选单一赛道或可多选 |
| 技术方案 | “技术方案” | 文本字段长度和附件要求 |
| DEMO（可为演示视频，3 分钟以内） | [DEMO_SCRIPT.md](DEMO_SCRIPT.md) 与 RECORDED 路由 | 页面/脚本是否可替代实际视频；上传格式/容量 |
| 项目文档 | 本申报草案、演示脚本、证据清单和分支 README | 是否要求合并为 PDF 或采用固定模板 |
| 获奖需提供代码或佐证 | 公开代码分支与证据清单 | 初次创意提交是否要求上传附件 |
| 报名途径 | 华为云公告说经微信扫码填写问卷 | 问卷链接、登录要求、成员字段、实际提交确认 |

**待用户填写**：负责人姓名、联系电话、邮箱、团队名称与成员资料、学校/单位、赛道最终选择，以及平台要求的声明/授权确认。不得从本地环境或历史材料自动填入。

## 官方日期与提交前人工确认

[华为云云社区官方赛事公告](https://bbs.huaweicloud.com/blogs/882ce6baa17e4785bc3398029e6c79eb)发布于 2026-09-17 11:17（公告作者标注 11:17:37），公开可检索内容列明“截止创意提交 10 月 30 日”。公告可读文本未给截止小时和时区；官方页面直接打开在本次核验中超时，官方 openJiuwen 赛事中心可读页当时没有展示赛事条目。正式按 2026-10-30 作为内部准备 Gate；不把 2026-10-31 当成延期。登录问卷的实际要求仍为 `OFFICIAL_PORTAL_LOGIN_REQUIRED / USER_CHECK`。

该官方公告同时说明参赛作品知识产权由出题单位、参赛者与官方竞赛平台共享，并说明组织方/平台对参赛作品和团队信息有宣传展示用途。请用户在报名或提交前自行阅读原文条款并决定是否接受；本草案不代表法律意见或已接受协议。

**正式报名/作品提交状态：`NOT_SUBMITTED`。** 不会由本任务填写个人资料、登录、上传文件、勾选协议或按下最终提交。

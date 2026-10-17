# TASK_RESULT｜RPF-42 / rev-1

- **Status: COMPLETE**：必要两轮真实 Exploration、独立业务反馈、L2案例机制和预注册B0已完成；实现提交已普通push并独立核验。唯一报告的最终commit SHA在同次聊天回执补录，避免循环填写自身SHA。此状态是Plan交付候选，不代表Main接受、阶段推进、合并或发布。
- **Repo / parent / branch**：`D:\CS\runproof`；origin `https://github.com/MyKr-YSteinsK/runproof.git`；parent `ec490719176fe0e5504902671d62e1e06361d510`；分支 `codex/rpf-42-pge-feedback-exploration`。预检和实现交付后main均为 `bda0cd49e50e3181f604324e94877a24b9885334`。
- **Working tree**：启动时tracked/staged clean，唯一预存用户状态 `?? docs/reviews/`；目标分支和路径未占用。该目录始终未读取、列举内部、修改、移动或stage。实现push后状态再次仅该项，tracked/staged差异均exit 0。

## 技术决定与范围

选择“冻结SessionPlan + 原单次订单执行Port + Shared SessionBudget”，复用SQLite真实事务/独立只读连接/原OrderEffectVerifier，而不复制业务执行器、引入SDK或部署服务。新模块 `pge_contracts.py`、`exploration.py`、`pge_provider.py` 分别持有冻结候选/预注册、状态机/反馈/共享额度、真实选择协议。

Execution/Effect v1语义保留，Experiment显式新增 **v2** 绑定rpf-42 owner与session/policy/candidate；旧v1仍拒绝新owner或额外字段。OrderSandbox与Reader按已验证合同owner路由到对应任务目录；默认v1路径和原单次live ledger没有改写。原 `provider.drive` 不变；增加窄 `request_completion` 复用预算方法供Explorer使用。原Pilot测试仅用7行fixture重定向，将其临时输出限制到当前任务目录，产品默认配置不变。

Explorer是本轮实际DeepSeek；target明确为 **DETERMINISTIC_CONTROLLED_TARGET**。没有额外live target请求，没有把RPF-41旧退款会话算本轮PGE。模型只调用 `select_experiment(candidate_id)`，两次都保留相同的全部3项枚举，可以合法重复；控制器没有指定第二候选或基于首轮结果过滤选项。初始只给候选控制规格、冻结业务规则摘要、2轮额度、覆盖目标及空反馈；不发送未来结果、B0顺序/实值、authority路径。

候选为 `normal`、故意抑制触发的 `planned-untriggered`、真实post-commit `response-lost`；未新增fault类型，`reconcile-unavailable`仅用于既有/确定性负控。替代路线“每轮额外LLM target”会增加成本与B0不可比因素，本轮没有采用；WorkSwarm嵌入仍 **NOT_PROVEN**。所有实现都在Plan白名单，没有重大偏差需要扩权。

## 真实PGE选择、反馈与等级

Session ID：`session-5e6d4061cf5b47248d6c429a5d921804`。

SessionPlan预注册时间 **2026-10-17T11:03:23.834952+00:00**，先于任何请求/业务实验。冻结B0为catalog固定前缀 **normal → planned-untriggered**；实际B0在两轮PGE结束后才执行。

| 轮次 | 实际模型选择 | Provider response ID | Tool Call ID |
|---|---|---|---|
| PGE 1 | `normal` | `bbab90db-3a65-4418-a9d0-e3e6034fba36` | `call_00_fk0GGy26CzG89TG42v3h3797` |
| PGE 2 | `response-lost` | `986c8d18-a9fd-4ddb-9eec-3fc01f72591c` | `call_00_2awPYCVPr5uVN1krWktr5897` |

均为工具 `select_experiment`，两次HTTP 200 / `finish_reason=tool_calls`，不同Tool Call ID。HTTP `x-request-id`未返回（null）；保存真实response ID、本地attempt 1/2，不伪造header ID。

顺序事实：第一轮输入冻结event #1；模型选择#2；第一轮真实trial完成#4；反馈校验 **#5，11:03:24.892991 UTC**；回注预留#6；第二轮实际输入冻结 **#7，11:03:24.896996 UTC**；第二次选择#8；第二个fresh trial完成#10；反馈#11；随后B0反馈#14/#17。第二次请求的 `tool_results_submitted` 精确包含第一轮Call ID，输入feedback hash等于第一轮实际反馈hash。没有第三次请求补写漂亮摘要。

第一轮验证事实是 `activation:NOT_PLANNED` 与 `effect:CONTRACT_SATISFIED_IN_RUN`。第二轮在看到该真实反馈后选择 `response-lost`，新增 **`activation:TRIGGERED`、`recovery:RECONCILED_COMMITTED_RECEIPT`**；同一业务合同仍满足。新Run/收据ID本身不算信息增益。

**L1=true、L2=true，H1=SUPPORTED_IN_THIS_CASE**；停止原因 **EVIDENCE_GAIN**。这是本案例“真实反馈已输入→合法不同选择→新增实际事实”的有限机制证据。没有无反馈反事实复跑，不能声称广义因果；attribution=`CORRELATIONAL_ONLY`，不是INTERVENTION_SUPPORTED。

## 业务结果和B0对照

四轮均为真实新SQLite沙箱：CNY2500，初始PAID/refunded=0/revision=0，最终REFUNDED/refunded=2500/revision=1，一条COMMITTED收据；独立 `rpf41-sqlite-authority-reader/1` 与 `rpf41-order-effect-verifier/1` 判 `CONTRACT_SATISFIED_IN_RUN`，Run=PASS，无证据缺口、无业务违规。**没有发现refund漏洞**；响应丢失后的正确调和不冒称bug。

| Policy/候选 | 新run_id（environment/order/operation分别加env-/order-/refund-前缀） | 单笔receipt_id | Fault planned/triggered/observed/reconciled |
|---|---|---|---|
| PGE/normal | `trial-4c3325c0a5f148f3bcb6fe957779534f` | `receipt-48b1c85d7bbf8a1b0926ee51` | false/false/false/false |
| PGE/response-lost | `trial-873cb25d4a2646a6b2ec21dc80ebff78` | `receipt-83171372452f26c913956a5e` | true/true/true/true |
| B0/normal | `trial-bcfe0dea363340deb3169fb08e2f0045` | `receipt-59447def7343f197516273dd` | false/false/false/false |
| B0/planned-untriggered | `trial-7edb557352b24c51a38ce76cdd805480` | `receipt-da542a4b7669456b48ebfb2e` | true/false/false/false |

每轮operation与environment均不同，session refs与candidate/policy绑定。response-lost为真实事务提交后隐藏Tool响应，pending阶段禁止重复执行，独立receipt查证后终态；仅一次业务Tool调用。NOT_TRIGGERED控制没有故障激活证据。四轮均完成owner reset、读回零收据、generation=1，再移除确切DB和空run目录。

指标 `observable-fact-set-v1` 计每policy首次出现的有效effect/activation/recovery事实，不是熵、漏洞数或任务成功率。

| 比较项 | PGE | B0 |
|---|---|---|
| physical trials / 最大值 | 2/2 | 2/2 |
| 确认triggered且observed | 1 | 0 |
| distinct valid facts | 4 | 3 |
| 新增事实代理（逐轮） | 2、2 | 2、1 |
| 业务满足/实际违规 | 2 / 0 | 2 / 0 |
| Provider请求 | 2 | 0 |

B0与PGE使用同一冻结候选、2500全额退款规则、adapter revision、环境revision、target driver、Reader、Verifier和2轮物理上限。B0无Provider费用，**cost_equivalent=false**；这是预注册固定前缀，未经优化，不代表最佳固定策略。本案例PGE多观察到触发/恢复事实，B0则观察到NOT_TRIGGERED负控；没有统计显著、普遍优势或公平同成本结论。L3仅适用于该有限预注册比较。

## 合同、反馈与source摘要

| 项 | SHA-256 |
|---|---|
| SessionPlan `rpf-exploration-session-v1` | `0c8f3749cd4b477820775fc1ef2305632b3f11a0fa49dd08c2faab21168b6533` |
| 包内10个`.py`文件名→原始字节hash的canonical map digest | `6ba6019999eb0c2ff2063ae25389d83a73054d77d123d4f6f93370846fc6078a` |
| 各轮Execution v1（deterministic，原预算schema） | `085edbfe433ef6bc8126369510d0721df82b4b3b563961d971e3949cf841d22c` |
| PGE1 Experiment v2 | `ec6b05a5c50feab0b739764aaa1b4c479fbfc38d1e7167b5cce2da9dbc31e6b0` |
| PGE2 Experiment v2 | `2750e56a0a8d0c4eac6e5b407ef8d8236cb1d70453aa358cada8f6807c2a1474` |
| B0-1 Experiment v2 | `fa97da165c8ff9cb57e0e7786da043da7f2cb363d2256265c90d71268dc485ab` |
| B0-2 Experiment v2 | `38cc6da4facdb189f507279f87133eb08d00eb3494c1f75ecf5718967fdde0ec` |
| 第一轮实际feedback及第二轮输入feedback | `2b30431bddc380fe783b8b68fe11d9439141bea7eb7070bf2383887972d84e42` |
| 第二轮实际feedback | `82ef5182d39fe97e46228dae2f9c3d18acf393a08a071290fa71f836bd990946` |
| PGE1 authority before / after | `b268340d996ae88e07e799b532507c76d22407a09bdc8d0b2453903c22bd2210` / `af0a09e9a2397763b72c054710b394eb93634099c0191a3aa55582e47203be46` |
| PGE2 authority before / after | `9ac0aea40bc3fba6a9913adef4566f9903b8508b9278a62961cb5567bda396ab` / `1daa92692c05431e40680aa2bb2c74d6740552decaff7fbdd0af3aa93c1b17e9` |
| 第二轮实际message / body | `8583fd89f5681c6ca7cc25f9b38dd4fd25b531393b90997642332a0efcb6f366` / `dc06178355b6858dc530f9d154f0cd50de40443279a273ef369d131cfb0cbf8c` |
| 唯一ignored live-result.json原始文件 | `ed05ce5dfdaa19dbad404046fd375177c07f8ad242be4185d68c81292c6950d6` |

单一JSON保存完整三合同、每轮Effect/receipt hash、before/after白名单摘要、模型注册工具、精确feedback投递内容与事件。独立复算重新freeze各合同、重建两次request的canonical messages/body，核对上述hash、计数和时序，PASS；暂存源码字节与实际live source digest相同。

未保存原始Provider消息、自由文本或隐藏推理；合法工具参数做canonical重编码；authority临时HMAC不导出。这些为执行者提供的脱敏运行摘要，Main可审查源码与摘要关系，**无法据此独立重放原Provider会话或离线证明远端签发者**。它不是正式Witness Certificate，不升级原产品Release evidence等级。

## Provider与共享预算

实际DeepSeek官方端点 `/chat/completions`，请求和返回模型均 `deepseek-flash`；[2026-10-17官方定价/映射](https://api-docs.deepseek.com/quick_start/pricing/)为DeepSeek-V4.1-Flash-1017，响应本身没有更细版本号。协议按[官方Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)核对。窄stdlib HTTPS，无代理配置读取、无SDK隐藏请求、无额外target调用。

- Requests **2/4**，两次成功、0失败、0自动重试；usage分别 **669+36=705**、**1214+38=1252**。
- Tokens **1883 input +74 output =1957/12000**；未知usage从未冒记0。
- Steps **10/16**：2 Provider +4选择（PGE/B0各2）+4业务工具。
- Physical trials **4/4**（包含无故障控制），PGE2/B0 2；单元fixture不计非测试额度。没有单独再跑CLI demo。
- Wall time **2.656/1200秒**；socket timeout≤90秒；max output=128/request。
- 按peak input cache-miss $0.30/M、output $1.20/M、USD→CNY=10保守上界 **¥0.006537/¥1.50**，是估算非账单/市场汇率。

独占ledger在任何I/O前预留会话，每次request/trial/step先持久写入全局额度。Trial不创建新满额预算。进程重启/损坏ledger拒绝新会话；没有自动重放未知选择/业务操作。实测请求前持久预留与精确反馈回注由零网络组件测试覆盖。

## A-01～A-10

| Gate | 状态 | 真实证据/限制 |
|---|---|---|
| A-01 身份/范围 | PASS | root/parent/remote/main/AGENTS/触发器/目标占用与clean检查；仅授权路径，docs/reviews未碰 |
| A-02 会话/合同 | PASS | strict SessionPlan+catalog+budget+三合同；v1兼容、v2 session refs、持久共享预留测试 |
| A-03 候选 | PASS | 三种实际控制/观测provenance；非法候选/工具/额外字段/动态路径拒绝 |
| A-04 沙箱/权威 | PASS | 两个fresh PGE+两个隔离B0，真实事务/单收据/只读连接/确定性oracle/清理 |
| A-05 Feedback | PASS | 首轮真实反馈event5→第二请求event7，精确canonical内容/hash/Call ID，输入重建匹配；无未来/B0结果泄漏 |
| A-06 安全/停止 | PASS | 重复合法且无增益、错hash/owner/version、UNKNOWN阻断/receipt reconcile、不可读保留DB并safe stop、共享额度与重启拒绝 |
| A-07 真实Explorer | PASS | 两次本轮200/合法真实选择/不同Call IDs，实际执行且第二请求含首轮role=tool |
| A-08 L2 | PASS | normal→response-lost，自主改选且新增trigger/reconcile事实；无强制差异，非统计/强因果 |
| A-09 B0/回归/清理 | PASS（有环境限制） | B0先冻结后执行、匹配目标能力/2轮上限、成本不同；31 EffectWitness/111完整测试成功；2 Docker组skip，quarantine无条目 |
| A-10 Git | PASS | 实现commit `2b7f9d0e399c76c8e7e0f8227ed3dc62955ab978` 已普通push，独立ls-remote相等；main不变；报告最终SHA/核验见聊天 |

## Tests与复现

均从repo root，`PYTHONDONTWRITEBYTECODE=1`，`TMP/TEMP/TMPDIR=.local/rpf-42`；没有安装依赖。实际命令：

1. Python3.12.13 `-m unittest discover -s runtime/tests -p 'test_effectwitness_pge.py' -v`：初版11测试OK、exit0。
2. 首次完整回归使用临时全局workspace测试重定向wrapper：110测试中1个新路径断言失败，原因是wrapper同时改变该断言的默认root。没有Provider请求或产品故障；改为原Pilot setUp内局部fixture重定向，不削弱断言。
3. Python3.14.6，已有OTel SDK/exporter1.44.0，`-m unittest discover -s runtime/tests -p 'test_*.py' -v`：110测试OK、2组skip，exit0。
4. 完成CLI fixture后，Python3.12.13 `-m unittest discover -s runtime/tests -p 'test_effectwitness_*.py' -v`：**31测试OK（12 PGE+19旧Pilot）**、exit0；原`--self-check`与新`--pge-demo`在无网络unit fixture真实运行，exit0。`--help`独立执行exit0。
5. Python3.12.13 `-m runtime.runproof_runtime.effectwitness --pge-live`：唯一live，exit0；真实值见上文。
6. live后Python3.14.6 `-m unittest discover -s runtime/tests -p 'test_*.py' -q`：**111测试OK、2组skip**、exit0。旧OTel故意不可达端点产生bounded drop/timeout诊断，未改变业务结果。独立合同/feedback/request输入/4个唯一业务身份/hash核验exit0。

两个Docker组是 `DockerIntegrationTests` / `Rpf05RuntimeTests` 因Docker provider unavailable跳过。没有启动Docker或跑RPF-28/30等重型正式proof，Java/Web/Hosted Gate/Golden Demo/Reviewed verifier均NOT_RUN（未触达其实现/正式证据）；不宣称Production端到端验收。

## Cleanup与Git

`.local/rpf-42/`仅保留 **live-result.json，33574 bytes**，未提交；四个业务DB及测试临时目录均已清理。负向fixture曾把未决DB移入固定quarantine，恢复authority后先确认COMMITTED单收据再reset清理，最后 `.local/quarantine/rpf-42/` **无条目**。本次没有bytecode/venv/wheel/cache残留、没有清理拒绝，没有碰旧 `.local/rpf-40/41/`；未创建或修改父目录、其他repo、`D:\CS\temp\Red-Repeat`。

相对RPF-41 parent，最终tracked变更精确11文件（M/A）：

```text
M runtime/runproof_runtime/effectwitness/__main__.py
M runtime/runproof_runtime/effectwitness/contracts.py
A runtime/runproof_runtime/effectwitness/exploration.py
M runtime/runproof_runtime/effectwitness/orders.py
A runtime/runproof_runtime/effectwitness/pge_contracts.py
A runtime/runproof_runtime/effectwitness/pge_provider.py
M runtime/runproof_runtime/effectwitness/provider.py
A runtime/tests/test_effectwitness_pge.py
M runtime/tests/test_effectwitness_pilot.py
A spikes/rpf-42/README.md
A spikes/rpf-42/RESULT.md
```

实现提交 `2b7f9d0e399c76c8e7e0f8227ed3dc62955ab978` 已普通 `git push -u origin codex/rpf-42-pge-feedback-exploration`，独立 `git ls-remote --heads origin ... main` 核验相同SHA；报告作为后续focused commit普通push，最终HEAD/remote/clean状态在聊天补录。没有force/rebase/cherry-pick/PR/main merge/tag/release/deploy/手动workflow。差异以RPF-41为基准，不把与main之间历史RPF-40/41改动算成本轮。

`git diff --cached --name-only` / `--check`、白名单/实际key不入源与结果检查PASS；包内暂存字节与live source digest相同，最大实现交付文件16152 bytes。新增代码自行编写，无第三方源码复制、依赖或license新增。报告也按相同范围/secret检查后提交。

## Next boundary

本轮为订单域L2案例和有限B0比较提供实际反馈数据。Witness Certificate/离线验证、跨域运维接入、Lab UI、正式Worker Job、自动shrinking、WorkSwarm和生产可用性仍未实现/未证明。没有独立反事实、规模化统计或通用策略优势。后续Plan及Evidence接受/阶段推进由Main独立决定，本轮不提前创建RPF-43。

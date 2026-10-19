# TASK_RESULT — RPF-56 rev-1

**Status: Partial**

执行日期：2026-10-20。任务：真实 Explorer 与真实 Target 跨域 PGE 联合闭环。

## 结论

已新增联合合同、受限 Explorer/Target、持久共享总账、两轮编排和独立离线验证；离线协议、回归及九件历史证据锚通过。**真实联合闭环未建立；no-valid-Witness。** 本轮不生成 `config-pge-evidence.json`，不把合成会话或历史证书升级为新真实实验。

固定 CPython 3.12.13 在 SDK 元数据检查的 `subprocess.run` / Windows `CreateProcess` 处被 Application Control 拒绝，WinError **4551**。第一次 preflight 只返回 `OSError`，第二次带 traceback 的隔离诊断定位到该系统错误；两次均未成功创建 SDK 检查进程。解释器路径与 launcher 的固定 hash 在该调用前已通过；当前 SDK RECORD/ABI 检查未完成，不能沿用历史 PASS。没有继续尝试别名、其他版本、复制 executable、安装或策略绕过。

## 身份与范围

- Root：`D:/CS/runproof`。
- Base/parent：`227ffb020472633ce9b538ea33d5ad30a5e17bd7`，`codex/rpf-55-rev2-config-experiment-cold-start-closeout`。
- 执行/交付分支：`codex/rpf-56-real-explorer-target-config-pge`。
- origin fetch/push：`https://github.com/MyKr-YSteinsK/runproof.git`；main 基线 `bda0cd49e50e3181f604324e94877a24b9885334`。
- 仅新增本 Plan 白名单的 11 个文件；旧源码与证据保持原样。未读取或变更受保护 `docs/reviews/` 内容，其外层状态仍为用户未跟踪目录。
- 所有本轮生成的测试快照、合成会话、控制样本和日志位于 ignored `.local/rpf-56/`；无旧运行目录/账本/标记复用，无 Java 外部仓库修改。

## 实现与技术选择

1. 三候选在两轮中完整预注册，独立 namespace/Run/Experiment；Explorer 无业务工具，Target 不持有选择故障和重写总账的接口。Target 新 owner 为 RPF-56，组合旧协议校验，保留原 Fixture Provider 禁令。
2. Parent 账本使用独占锁、追加编号快照、fsync 与摘要链；请求、JVM、POST 先预留且不返还。请求未知 usage、torn record、锁冲突和重复操作 fail closed。两角色全局账与 Target 子账相互核验。
3. 第二轮输入来自第一轮确定性已验事实，包含 Tool Call ID 与 feedback SHA；事件序号及单调时钟同时检查先后。候选可重复，合成无信息增量会话也能合法通过，H1 始终不作证明。
4. verifier 独立检查新 source/verifier identity、HTTP Authority/历史、故障 gate、SDK PID、Provider usage、工具回注和清理。旧纯合成生成器只产生测试原语；旧真实证书仅用于公开固定 SDK 元数据，未拼接其观测事实。
5. 测试发现冻结请求与后续消息共用列表会改变先前输入摘要；已改为深拷贝，并加入未来 feedback 不改变冻结输入的回归。

生产者/消费者：Explorer 请求 → 全局账与 selection → 独立 Trial worker/Target → HTTP Authority 和确定性 Trial verdict → 白名单 feedback → 次轮冻结输入 → 联合 verifier。代码覆盖该链；实际 SDK/模型/Java 兼容性仍未验证。具体源码映射及 verifier hash 见 `verification-diagnostic.json`，文本 hash 按 LF 规范化，外部 Evidence SHA 按原始 bytes。

## Acceptance

| Gate | 状态 | 实际证据/缺口 |
|---|---|---|
| A-01 仓库与保护 | PASS | Root/Base/分支/remote/规则/workflow/白名单核验；旧 tracked 内容不变。 |
| A-02 联合合同与真实角色隔离 | NOT_RUN | 合同、Fixture 禁令及结构负控通过；真实双角色隔离尚未执行。 |
| A-03 共享总账/重启安全 | NOT_RUN | 合成竞争、损坏、未知 usage、重启及预算负控通过；没有 live usage 可对账。 |
| A-04 无付费预演 | UNAVAILABLE | 合成两个会话、CLI 0/2/3、11 类负控通过；三个实际 SDK cold-start 因 4551 未运行。 |
| A-05 真实双角色链 | NOT_RUN | 无 Explorer/Target Provider 请求，无 selection/response/tool call 真实 ID。 |
| A-06 故障/Authority/reconcile | NOT_RUN | 无 JVM、业务写入、故障激活、只读 reconcile 或 Authority 清理对象。 |
| A-07 真实 feedback 时序 | NOT_RUN | 无真实第一轮 verdict 和第二轮输入，只有合成协议通过。 |
| A-08 联合 Witness | NOT_RUN | no-valid-Witness；合成负控不能替代真实 Envelope。 |
| A-09 回归/安全/预算记录 | PASS | 12 项定向、325 项隔离 Runtime（2 skip）、九历史锚、Reviewed/Public Docs、安全范围核验通过；实际付费与业务计数均 0。 |
| A-10 Git/交付 | NOT_RUN | 待 focused commit、普通 push 及 fresh remote 观察后更新。 |

## 验证明细

- `python -B -m unittest runtime.tests.test_effectwitness_config_pge -v`：12 项 PASS。
- `python -B spikes/rpf-56/probe.py offline`：PASS，scope=`SYNTHETIC_PROTOCOL_ONLY`；有增量与合法重复两会话分别 correct/missing/wrong SHA exit `0/2/3`。
- 11 类 rehashed 语义负控在两会话均 exit 3：伪造选择、反馈 hash、反馈时序、分角色预算拆分、重复 POST、伪造触发、namespace 拼接、虚假 ACK、source、SDK PID、cleanup。另对九种候选配对证明负控不是 no-op。
- 两个普通 Python 子进程竞争同一合成账本仅一方预留成功；残留锁、torn record、unknown usage、重复创建、token/request/JVM/POST 配额负控通过。
- 完整 Runtime 在 Base 的 `git archive` 隔离快照叠加七个新源码中执行：325 tests，OK，skipped=2（Docker 环境类）；显式阻止 Java/Docker 和外部网络。没有以此替代真实集成。快照七源码 hash 全部匹配最终执行源码。
- RPF-43/44/48/49/50/51r4/52r3/53r6/55r2 九件固定 SHA 独立验证 exit 0；`runtime/verify-reviewed-artifacts.py`、`ci/verify-public-docs.py` exit 0。
- 日志与完整失败/合成样本保留 `.local/rpf-56/tests/`，SDK 阻塞摘要保留 `.local/rpf-56/preflight/`；公开 JSON 不含本机账户路径、密钥、Authorization、自由模型文本或私有推理。

## 实际预算与研究结果

| 项目 | 本轮实际 |
|---|---:|
| 新真实 Session/Trial/完成回合 | 0 / 0 / 0 |
| Explorer / Target Provider 请求 | 0 / 0 |
| tokens / 估算费用 CNY | 0 / 0 |
| SDK cold Fixture 进程 | 0 |
| 被拒绝的固定 Python 元数据进程创建尝试 | 2 |
| JVM / 业务 HTTP / POST / health | 0 / 0 / 0 / 0 |

没有读取 Provider key，没有真实 Session 账本或 Session-start marker；合成账本位于 tests 子树。无本轮遗留 SDK/JVM/业务服务或待定付费请求，ignored 合成材料为诊断保留。每轮 candidate、selection ID、response ID、Tool 参数 hash、Exec/Effect/Experiment/FaultPlan hash、Authority 当前/历史均为 **NOT_RUN**，不以合成值填补。

L1/L2=`NOT_RUN`，H1=`NOT_PROVEN`；业务违规未评估，不能推导 Agent 安全、PGE 优势或强因果。issuer authenticity、数据库独立权威、独立复现和 WorkSwarm 均未建立。

2026-10-20 核对 [官方价格](https://api-docs.deepseek.com/quick_start/pricing/?model_version=DeepSeek-V4-Pro-0813)、[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/) 及 [Chat API](https://api-docs.deepseek.com/api/create-chat-completion/)；预定 `deepseek-flash`、thinking disabled、常规工具协议。峰值 USD 0.30/1.20 每百万输入/输出，×15 guard 得 CNY 4.5/18，不作为汇率或账单。实际 returned-model 与 usage 未观察。

## 偏差、残留与下一步

环境策略阻塞使实现仅在离线层完成；SDK RECORD/ABI、三个冷进程、模型工具协议、Java/H2、真实 feedback 与新 Witness 均待验。未触碰系统策略，不以技术未知扩大权限。后续应由用户/环境管理员明确解决固定 CPython 的应用控制问题，再通过新 Plan 重新核验源码身份、起点、费用和独占运行空间；不得直接重用本轮旧 gate/账本。当前没有需要升级业务权限或修改只读旧源码的已验证理由。

交付观察将在本文件同一任务收口更新；最终远端 commit SHA 由聊天回执给出。无 PR、merge、main push、tag、release、workflow dispatch 或 deploy。

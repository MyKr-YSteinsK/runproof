# RPF-56 rev-3：系统恢复验证与真实 PGE 补验收

当前结果 **Partial**。原固定 CPython 的一次 smoke、当前 SDK RECORD/运行映射和三个真实 SDK Fixture 均通过；唯一 Live Session 的第一次 Explorer 响应未满足单一工具选择合同，安全停止，没有启动 Target/Java 或写入业务。没有新 Live Witness。

## 结果与接口

- `RESULT.md`：唯一中文 TASK_RESULT、逐 Gate 判定和交付事实。
- `recovery-diagnostic.json`：本轮一次 smoke、固定 SHA/SDK 身份与三个真实 Fixture 的实际 PID/报告/回注。
- `session-summary.json`：Runner 当时直接生成的失败摘要，保留原样；唯一 Session、请求/usage 总账及 `ONE_SELECTION_REQUIRED`。
- `verification-diagnostic.json`：独立合成 CLI/负控、回归、历史锚、费用、实际未运行项与执行源码身份。

已迁移 `config_pge_contracts/session/verify` 与 `probe.py` 的 rev-3 schema/owner/Base/branch/root/JAR/export 身份，未修改 Explorer/Target 核心、旧 Runtime、旧证书或 rev-1/rev-2 报告。新运行空间仅为 ignored `.local/rpf-56-rev3/`。

本轮实际使用的入口（仓库根目录）：

```powershell
python -B spikes/rpf-56/probe.py preflight
python -B spikes/rpf-56/probe.py offline
python -B spikes/rpf-56/probe.py fixture --candidate normal
python -B spikes/rpf-56/probe.py fixture --candidate planned-but-inhibited
python -B spikes/rpf-56/probe.py fixture --candidate local-delivery-suppressed
python -B spikes/rpf-56/probe.py live
```

这些是已执行记录，**不可直接重跑**：恢复 smoke 的一次额度、三次 Fixture 及唯一 Live Session 均已使用；保留独占 marker/账本/失败出口，不能删除或换 namespace 重置资格。正式 Runner 要求精确 Parent HEAD 与该分支，提交后不会静默认可新的执行起点。

普通离线测试可独立运行：

```powershell
python -B -m unittest runtime.tests.test_effectwitness_config_pge -v
```

新 verifier 只接受 v3 Envelope/合同和当前源码身份；correct/missing/wrong 外部 SHA 返回 `0/2/3`。合成 `SYNTHETIC_TEST_ONLY` 标签不能被 issuer 当作真实 Session。本轮实际签发条件不成立，因此 `config-pge-evidence.json` 不存在。

## 停止条件与后续

第一次真实请求的 usage 已知（468 input + 72 output），但解析没有获得恰好一个合法 `select_experiment` 调用。原始模型正文没有持久化，响应的结构摘要也未保留，因此不能进一步区分缺少、空或多个 tool calls，更不能编造原因或选择。Target、业务 Effect、真实反馈和两轮 Witness 均未运行。现有额度不用于再次探测模型。

后续需新的受限 Plan，先补全不含正文/推理的响应结构诊断，再决定是否批准新的协议实验。保持原固定模型/SDK和安全边界，不从本轮推出切换 Provider、放宽工具校验或重复调用授权。

## 当天外部事实与费用

2026-10-20 通过 [DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/)、[官方更新](https://api-docs.deepseek.com/updates/?release=deepseek-coder)、[Chat API](https://api-docs.deepseek.com/api/create-chat-completion/) 核对：`deepseek-flash` 对应 Flash-1017；峰值 USD 输入 cache-miss 0.30、输出 1.20 每百万 tokens；`thinking=disabled` 支持 `tool_choice=required`。Tool Calls Guide 直接抓取超时，协议核对改用可读取的官方 Chat API。

预算以 ×15 guard 得 CNY 输入 4.5/输出 18 每百万 tokens，不是实际汇率/账单。本轮费用保守估算为 **¥0.003402**，未将未执行请求记为已消费或把已消费请求返还。

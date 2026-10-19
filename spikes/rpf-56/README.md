# RPF-56：真实 Explorer × Target 配置 PGE

当前交付 **Partial**。联合合同、双角色预算、受限 Target Host、两轮编排与独立离线验证已实现并通过合成协议测试；固定 CPython 的进程创建被 Windows Application Control 拒绝（WinError 4551），实际 SDK Fixture 与付费联合实验均未运行。没有新真实 Witness。

## 实现与证据入口

- `config_pge_contracts.py`：新 RPF-56 owner 的 Session/Execution/Effect/Experiment；两轮各自预注册三个合法候选，业务约束固定。
- `config_pge_explorer.py`：仅 `select_experiment`，首次输入不带历史结果；冻结请求深拷贝，第二轮仅接受已验证结构反馈。
- `config_pge_target.py`：新 Target Host 组合旧协议检查，不放开旧 Fixture Host 的 Provider 禁令，不冒充 RPF-53 owner。
- `config_pge_session.py`：双角色共享不可返还预留、互斥锁、不可变编号快照和摘要链；未知 usage、损坏和竞争均停止。
- `config_pge_verify.py`：无 SDK/Java/Provider 的离线会话验证，检查业务、故障、工具回注、模型请求、总账、反馈时序与源码身份。
- 唯一任务结果：`RESULT.md`；公开诊断与未执行事实：`verification-diagnostic.json`、`session-summary.json`。合成材料保存在 ignored `.local/rpf-56/tests/`，不得作为真实 Evidence。

## 已执行的离线入口

在仓库根目录：

```powershell
python -B -m unittest runtime.tests.test_effectwitness_config_pge -v
python -B spikes/rpf-56/probe.py offline
```

`offline` 使用当前普通 Python，只生成合成协议 Tier 0，单独调用验证 CLI，检查 correct/missing/wrong 外部 SHA 的 `0/2/3`，并验证 11 类重新计算摘要的语义篡改。它不启动固定 SDK、Java 或 Provider，不代表冷进程预演通过。输出使用独占创建，已有 gate 不覆盖。

独立验证器接口（本轮没有真实证书文件）：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.config_pge_verify <evidence.json> --sha256 <external-sha256>
```

缺外部 SHA 返回 2，错误 SHA 或语义篡改返回 3。`SYNTHETIC_TEST_ONLY` 必须显式保留；真实 issuer 拒绝签发该来源。

## 暂停的运行顺序

`preflight → fixture（三候选各一冷进程）→ live → issue` 为预定入口。当前 **不要继续调用 preflight/fixture/live**：WinError 4551 尚未解除，禁止更换解释器、复制 executable、改策略或隐式安装来绕过。现有 probe 有意限定原 Plan 的 Base、分支及未提交白名单；提交后不会自动接受新的 HEAD 或已有报告，后续恢复需明确的新合同，不得直接重用本轮 Session/总账。

`live` 还要求同源码 Tier 0、三个真实冷进程通过、独立人工核对当天官方价格后在 task root 的 `preflight/official-price-reviewed.json` 写入与 `config_pge_contracts.PRICE` 完全相同的结构。此记录不能替代 SDK gate。只有全部成立后才读取 `DEEPSEEK_API_KEY`，先冻结全部候选合同并创建唯一 Session 与总账，再调用模型；无自动重试。

上限：1 Session、2 Explorer 回合、12 总请求（2 Explorer/10 Target，单 Trial Target ≤6）、28000 tokens、费用 guard ¥1、2 JVM、24 业务 HTTP、4 POST、6 health；Session/Trial 2400/1200 秒。候选允许重复，不强制信息增量。一次有限序列不能证明普遍优势、强因果、发行者真实性、独立数据库权威或 WorkSwarm 能力。

## 当前模型与费用口径

2026-10-20 查阅 [DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/?model_version=DeepSeek-V4-Pro-0813) 与 [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)：使用 `deepseek-flash`、关闭 thinking、常规 Tool Calls 和本地确定性校验。峰值 USD cache-miss input 0.30/output 1.20 每百万 tokens，预算使用 ×15 guard（CNY 4.5/18），不是汇率或账单。该核对不构成真实请求的 returned-model/usage 证据。本轮实际费用为 0。

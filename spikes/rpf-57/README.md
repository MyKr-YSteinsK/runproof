# RPF-57 — verified feedback coverage

本 Spike 新增版本化的配置域事实覆盖投影，保持 RPF-56 v4 源码与 Witness 不变。正式结果见 [RESULT.md](RESULT.md)；事实与研究边界见 [coverage-analysis.json](coverage-analysis.json)。

## 合同与复用

- `config_pge_coverage_contracts.py`：新 owner、schema、Base、namespace、任务 JAR 与 10 请求 / 20,000 tokens / ¥0.50 上限；三个候选始终合法。
- `config_pge_coverage_policy.py`：完整 Trial 独立验证成功后，才生成五种固定事实中的有据子集；跨轮差集决定 novelty。未测试目录只有身份，没有未来结果。
- `config_pge_coverage_session.py`：统一 Task/Session 不可返还预约账，Target 的请求逐条映射到同一本账；保留 fsync、独占锁、快照链及未知 usage 停止，并拒绝历史预约/回执倒退。Target/HTTP 仅复制新身份构造函数，继承原来的工具、SDK 协议、故障和读写行为。
- `config_pge_coverage_verify.py`：新离线 Session Verifier；Trial 判定函数与 RPF-56 v4 完全相同，仅其模块级合同校验器绑定新合同。测试逐字对照该函数。旧 verifier 不被修改或动态替换。
- `probe.py`：本轮唯一入口。SDK 元数据、冷 Fixture 和 Java 生命周期包装来自审查过的 RPF-55/56 小型过程，明确复制到本轮路径；不调用旧 `live`，不读旧任务运行根。固定 SDK 安装和 Java manifest/JAR 来源仅只读。

## 可独立离线核验

从外部可信渠道取得完整文件 SHA-256 后：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.config_pge_coverage_verify spikes/rpf-57/config-pge-coverage-evidence.json --sha256 <external-raw-sha256>
```

正确 / 缺失 / 错误外部锚退出码为 `0 / 2 / 3`。内部 digest 或 Envelope 不能代替外部锚。Verifier 不调用 Provider、SDK 或 Java。source map 使用 LF 规范化源码哈希；外部证书锚对原始字节计算。

## 原授权运行入口

下列过程只适用于 Plan 指定 Base 上尚未运行的新任务根；已有正式会话禁止重开。没有额外付费协议 Probe：

```powershell
python -B spikes/rpf-57/probe.py preflight
python -B spikes/rpf-57/probe.py offline
python -B spikes/rpf-57/probe.py fixture --candidate normal
python -B spikes/rpf-57/probe.py fixture --candidate planned-but-inhibited
python -B spikes/rpf-57/probe.py fixture --candidate local-delivery-suppressed
python -B spikes/rpf-57/probe.py live
```

全部临时产物在 ignored `.local/rpf-57/`。每个 Fixture 最多一次，共三个，零 Provider/Java；正式入口以既存环境 `DEEPSEEK_API_KEY` 调用 DeepSeek。SDK 子进程无 Provider/business key，Java 只接收合成本地 key。预注册、预约、来源检查和只读读回失败均停止，不 fallback 或重启实验。

Round1 输入为空历史；独立验证其 Trial 后，Round2 包含真实 Call ID、原 Tool 反馈、显式反馈 SHA、seen/tested/unseen 目录及完整合法 catalog。只有本轮已验证事实减此前已见事实可计新颖性。不同 Run ID、再次启动 Java 或重复同类 HTTP 成功均不计分。

## 证据边界

一次不同选择及新增事实至多支持 `L2_OBSERVED_INFORMATION_GAIN_IN_THIS_RUN`，不能证明反馈造成选择改变，亦不证明策略优于公平同预算 B0。H1/L3/WorkSwarm 未证；签发者真实性、数据库独立 Authority 未建立；同一证书再验不等于独立复现。业务 Authority 为同一服务的独立只读 HTTP。显式 Host 交付抑制不是 TCP 丢包。

2026-10-20 已重新核对官方 [峰值价格](https://api-docs.deepseek.com/quick_start/pricing/) 和 [具名 Tool Calling](https://api-docs.deepseek.com/api/create-chat-completion/)；使用 cache-miss input $0.30 / output $1.20 每百万 tokens，乘 15 得 CNY 保守 guard，非汇率或账单。模型关闭 thinking，并在客户端严格拒绝非唯一合法工具调用。

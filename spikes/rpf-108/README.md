# RPF-108 可移植 Witness 与预发送准入

RPF-107 Actions 原始 ZIP 存放在 [evidence](evidence/rpf107-run-42764310121-actions.zip)。从仓库根运行 `python -B -m ci.rpf108_verify_archive`，可以按固定摘要验证外层和内层原件、公开 JSON 及其 manifest。其证据类型为 `PUBLIC_PROJECTION_VERIFIED`。

RPF-108 使用新 owner，沿用 RPF-106 领域合同、账本和 Oracle。经核验的 seed 先产生反馈，再允许一次持久预约和一次性模拟发送许可。真实 SQLite 只在通过当前账本准入和写意图落盘后提交。UNKNOWN 后收到的请求有单独记录，读回已提交也不恢复旧运行权限。

`pge_r108_replay` 的 `VERIFY` 模式接收 bundle、期望源码 SHA 和期望 bundle SHA-256。它用包内原始模拟协议字节、两份 WAL、Authority 快照和收据重算 `FIXTURE_PORTABLE_REPLAY`。验证无需访问原 owner 或网络。独立重算覆盖合同和领域事实；历史 SQLite 文件、真实 Provider 元数据、SDK 物理收据和第三方签发均未纳入该证明。

[封存结果](RESULT.md) · [验收记录](acceptance.json) · [验证诊断](verification-diagnostic.json) · [源码映射](source-map.json)

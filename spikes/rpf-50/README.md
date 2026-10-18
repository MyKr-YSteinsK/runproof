# RPF-50｜受控业务违规发现与独立失败 Witness

本 Spike 对相同的 CNY 2,500 全额退款合同运行一条正常 SQLite 阴性对照与一条预注册的 `KNOWN_DEFECT_HALF_REFUND_COMMITTED_V1` 确定性缺陷事务。两者使用独立 run/order/environment/operation ID 和 `.local/rpf-50/**` 沙箱。旧 `OrderSandbox.refund` 与订单 Oracle 不改。

RunProof 只在 cleanup 前通过独立只读 `AuthorityReader` 读回状态，再由既有 `evaluate_order_effect` 判定。证据中的逻辑合同 owner 保持 `rpf-48`；物理沙箱归 `rpf-50`。`driver=deterministic-reference` 表示受控服务调用，不表示 Pydantic AI、LLM、PGE 或 Agent 参与。

## 执行

在仓库根目录使用 Python 3；命令只创建 task-owned preflight 和 SQLite 证据。Provider HTTP、LLM、密钥读取、WorkSwarm、真实支付和生产网络调用均为零。两条试验各只能启动一次；preflight 与 one-shot marker 不可重置：

```powershell
python -B spikes/rpf-50/probe.py --prepare
python -B spikes/rpf-50/probe.py --run
```

`--prepare` 在任何订单 DB 建立前冻结两条 Trial 合同和执行源码 SHA。`--run` 必须消费该 preflight，按顺序执行正常控制与缺陷服务；发生平台错误或未决状态会停止后续操作，不提供重试开关。

## 离线核验

新 Witness verifier 仅导入 Python 标准库、纯订单 Oracle 与静态合同验证模块；不导入 SQLite、Host/业务执行模块、SDK 或 Provider。调用者须从 Witness 文件之外取得完整 SHA-256，并通过独立 Python 进程传入：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.violation_witness spikes/rpf-50/violation-witness.json --expected-sha256 <OUT_OF_BAND_TRUSTED_FULL_FILE_SHA256>
```

正确外部锚与所有事实复算成立时才返回 `VERIFIED_ANCHORED / VIOLATION_CONFIRMED`（exit 0）；缺锚为 `UNANCHORED_INCONCLUSIVE / NOT_PROVEN`（exit 2）；错锚、篡改或矛盾内容拒绝（exit 3）。内容哈希和外部锚不提供签名、issuer authenticity、生产真实性、Agent 发现、因果归因或独立复现证明。本结论只覆盖本地受控、预先指定的已知缺陷服务。

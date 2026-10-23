# RPF-67｜订单真实 Target 的版本化 DomainPort

此目录保存 RPF-67/rev-1 的独立订单域实现与验收结果。最终事实见 [RESULT.md](RESULT.md)、[verification-diagnostic.json](verification-diagnostic.json) 和 [session-summary.json](session-summary.json)。

## 运行边界

唯一 owner 为 `rpf-67`，ABI 为 `rpf67-order-real-target-v1`。有副作用操作只访问新建本地 SQLite 模拟订单：CNY 2500 minor units、一次全额退款、一条 receipt。`OrderSandbox` 原事务和 `AuthorityReader` 原只读方法保持不变；版本化构造层把路径限制到 `.local/rpf-67/`。

真实 Provider 决定 inspect/refund/可选 reconcile。Host 在事务已提交、独立 Reader 已看见收据后，对同一 ToolCall 返回 `UNKNOWN_OUTCOME`。之后模型只可只读 reconcile 一次或安全停止；Controller 再独立读回。故障为 Host 本地结果抑制，不代表 TCP 丢包。

一个 fsync/hash-chain WAL 保存 owner、Context、资源预约、Provider 请求哈希/usage、工具血缘、只读快照和清理。Provider 票据永久累计；UNKNOWN usage 或未结算 mutation 阻止后续付费和业务写入。最多一个真实 Trial、六次 Target Provider 请求、15000 reserved tokens、¥0.45 guard；Explorer=0，Java=0。费用 guard 不是账单。

## 入口

以下正式阶段具有不可重用的资源票据。必须先完成 Plan 要求的免费验收、source freeze 和官方价格核验；缺少前置时返回 exit3，不读取 Provider key。

```powershell
python -X utf8 -B spikes/rpf-67/probe.py init
python -X utf8 -B spikes/rpf-67/probe.py metadata
python -X utf8 -B spikes/rpf-67/probe.py cold
python -X utf8 -B spikes/rpf-67/probe.py admit
python -X utf8 -B spikes/rpf-67/probe.py live
```

只有 `live` 可从父进程读取 `DEEPSEEK_API_KEY`；子进程仅持临时 loopback token，使用固定 CPython3.12.13 / PydanticAI2.57.0 / OpenAI3.35.1。独立 verifier 不启动 SDK、不访问网络、不读取私有运行目录。

```powershell
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_r67_order_verify <witness.json> --sha256 <external-raw-sha256>
```

正确原件／缺锚／错锚的 CLI 为 0/2/3。真实 Witness 仅在全部运行资格通过后生成；合成记录始终标 `SYNTHETIC_TEST_ONLY`。

## 证据范围

只证明独立订单 Target 运行；`Explorer=NOT_RUN`、`L2=NOT_TESTED`、`web=NOT_INTEGRATED`、`cross_domain_same_session=NOT_PROVEN`、`causality=NOT_PROVEN`、`issuer=NOT_ESTABLISHED`、`external_reproduction=NOT_TESTED`、`release=NOT_AUTHORIZED`。

RPF-66/rev-5 配置域 Witness 仅是历史独立锚。两个任务的成功不能合并为同一跨域 Session 的成功。SQLite Reader 的独立连接不等于外部 Issuer 签名。原有目标 R-01～R-10 不因此删减。

## 后续研究

最有价值的下一步是在新授权任务中证明同一 Session 的 Config+Order Real Target 及共享 Context/WAL；同时评估 task-owned Driver/child 的复制债。本任务不实施真实跨域 Explorer。

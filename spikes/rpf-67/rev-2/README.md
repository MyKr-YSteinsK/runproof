# RPF-67/rev-2｜安全响应形状与受限订单协议

本轮 owner=`rpf-67-rev-2`，ABI=`rpf67-order-real-target-v2`。最新工程事实见 [RESULT.md](RESULT.md)、[verification-diagnostic.json](verification-diagnostic.json) 和 [provider-shape-diagnostic.json](provider-shape-diagnostic.json)。rev1 的 UNKNOWN 保持原结论。

本轮以 `Partial` 关闭：两次完整 Runtime 入口均遇到受保护的旧 HTTP fixture 错误，第二次在观察到 ERROR 后取消。Source Freeze、正式 metadata/cold、paid gate、Provider Trial 均 `NOT_RUN`，真实 Witness 路径不存在。后续需要新 Plan 授权旧 fixture 修复及重新验收；下列入口说明不构成重开本轮的授权。

## 取证与兼容

真实 HTTPS 之前先向唯一 fsync/hash-chain WAL 永久预约费用票据。收到合法 JSON 后，先 exclusive-create 有界 shape receipt，再把投影和 SHA fsync 追加到主 WAL，最后才严格解析。收据不含模型文本、reasoning、arguments 原文或其 hash、任意未知键值；ID 在失败态只有合法性和 SHA256，usage 提示始终标 `UNTRUSTED_OBSERVED_HINT`。

receipt 已落盘而 WAL 尚未绑定时，重新打开账本必须报 `TORN_DIAGNOSTIC` 并停止，不删除收据或重发请求。transport/HTTP/size/decode 失败明确标 NOT_OBSERVED；无 shape 时不编造内容。

兼容 policy=`rpf67-order-content-with-single-valid-tool-v1`：仅允许 `tool_calls`、恰一条合法且符合业务阶段的 ToolCall，与 ≤512 UTF-8 bytes 普通 content 共存。内容原样透传固定 SDK，不能控制工具或作为 Authority；不保存内容或短文本 hash。stop+tool、tool_calls finish 配空工具列表、falsey object、length/filter、并发、错参、reasoning/refusal 和 usage 不完整均拒绝。合法业务终止的 stop 可无工具。官方 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/) 是协议参考；实际兼容还必须由固定 SDK 免费端到端测试证明。

只有全部严格解析、阶段与 usage 校验通过，才记录 PARSE_ACCEPTED→RECEIVED→MODEL_RESPONSE→Tool Intent。离线 verifier 检查这些事件的位置、票据、收据、条件和真实回调血缘，不能只检查 hash 非空。

## 唯一正式入口

必须先完成全部免费门禁、Source Freeze、metadata/cold 和官方价格复核。以下正式资源不能重用或重跑：

```powershell
python -X utf8 -B spikes/rpf-67/rev-2/probe.py init
python -X utf8 -B spikes/rpf-67/rev-2/probe.py metadata
python -X utf8 -B spikes/rpf-67/rev-2/probe.py cold
python -X utf8 -B spikes/rpf-67/rev-2/probe.py admit
python -X utf8 -B spikes/rpf-67/rev-2/probe.py live
```

独立离线入口：

```powershell
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_r67_order_verify <witness.json> --sha256 <external-raw-sha256>
```

正确／缺锚／错锚 exit0/2/3。真实 Witness 只在唯一合法真实 Trial 完整通过后生成；否则对应路径保持不存在。源码冻结后不修绑定字节。

## 受控业务与预算

新本地 SQLite 模拟订单，CNY 2500 minor units，一次全额退款、一条 receipt。复用原事务和独立 `mode=ro/query_only` Reader；提交并独立读回后才抑制成功返回为 UNKNOWN。模型自行选择只读 reconcile 一次或安全停止，Controller 再独立核验。无生产支付。

Session/Trial各1，Target Provider≤6，CAPS=[3000,2600,2600,2600,2200,2000]，永久预约≤15000 tokens，费用 guard≤¥0.45；费用 guard非实际账单。Explorer=0、Java=0、自动重试=0。只有通过 paid gate 后的父 Controller 读取 Provider key，子进程只持临时 loopback token。

`Explorer=NOT_RUN`、`L2=NOT_TESTED`、`cross_domain_same_session=NOT_PROVEN`、`web=NOT_INTEGRATED`、`causality=NOT_PROVEN`、`independent_reproduction=NOT_TESTED`、`issuer=NOT_ESTABLISHED`、`production_release=NOT_AUTHORIZED`。独立连接不是 Issuer 签名；未来共享 Explorer/双域 Session 需下一编号任务。

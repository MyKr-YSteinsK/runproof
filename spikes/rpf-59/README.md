# RPF-59 — 真实 Explorer 的受限跨域选择

真实 DeepSeek Explorer 在两个冻结候选中选择最多两轮实验：`order-refund/normal` 与 `config-java-http/planned-but-inhibited`。重复候选合法，每轮使用新 Run/namespace。同一个新版 `SharedSession.execute_trial` 与持久 Ledger 管理 Explorer 请求、SQLite退款、Java/SDK、HTTP/POST/health；两个静态 Port 保留各自业务 Oracle。

## 边界与来源

仅 Explorer 使用真实 Provider。订单 Target 为确定性驱动、fresh SQLite和独立只读 Receipt Reader；配置 Target 为固定 Pydantic AI SDK scripted Fixture、fresh Java17/H2和同服务只读HTTP。配置故障门槛禁用，必须实际记录 `FAULT_INHIBITED`，不属于故障激活成功。跨域信息增益不可比，Issuer真实性未建立、独立复现未测试、H1/H3/因果优势和WorkSwarm未证明。

本轮全部使用新增 `pge_select_*` 模块，不修改 RPF-58/57 历史源码、测试或证书。订单/配置 Adapter及WAL生命周期从RPF-58 v2作版本化复制；配置场景Oracle保持已验证纯函数语义。存在复制维护债，不声明已完成通用框架抽象。

## 独立离线重验

从可信外部渠道取得证书原始字节SHA后：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.pge_select_verify spikes/rpf-59/cross-domain-selection-evidence.json --sha256 <external-raw-sha256>
```

正确/缺失/错误外部锚的退出码为 `0/2/3`。Verifier只做确定性校验，不调用Provider、SDK或Java，不创建业务环境。SHA用于内容锚定，不提供发行者签名或独立复现证明。

## 原授权的一次性入口

```powershell
python -B spikes/rpf-59/probe.py offline
python -B spikes/rpf-59/probe.py preflight
python -B spikes/rpf-59/probe.py fixture
python -B spikes/rpf-59/probe.py live
```

所有源与测试均纳入Source Map；离线、metadata、cold及正式执行必须同源。`live`只在全部免费Gate通过后读取现有 `DEEPSEEK_API_KEY`，该Key不传给SDK子进程。响应先持久化脱敏结构/用量再解析唯一具名工具，非法选择停止，不做fallback或付费重试。第一轮Oracle验证并冻结反馈后才构造第二轮输入。

这是一次性有界任务入口，已消耗的Marker/WAL不能删除重置。正式上限为1Session、2Explorer请求、6000tokens、估算¥0.15、2Trial、2退款mutation、2JVM/SDK、16业务HTTP、4POST、6health，2400秒。Provider每次预留3000tokens及相应保守费用，已知usage仍保留预约上限；未知usage或业务写结果停止。health未用预留槽保持 `UNUSED_RESERVED_NO_IO`。metadata最多2进程；cold默认1次，只有首轮明确失败、实际修复及新Source Gate后可补1次。

实际结果、Source/Verifier身份、冷/正式次数、研究结论与Git交付见 [RESULT.md](RESULT.md)。证书仅在真实完整Session和独立验收通过后存在；两轮选同域时明确标注本Session未执行两个不同领域。

# RPF-66/rev-3：WAL因果顺序与独立双角色试验

本修订以Windows父Runtime Python3.14为本地主Gate；SDK子进程仍锁定CPython3.12.13、Pydantic AI2.57.0/OpenAI3.35.1。Ubuntu Python3.12 hosted CI与Windows3.12父Runtime兼容性分别报告。实际状态、Source/Verifier身份、全部尝试与费用见RESULT及三个diagnostic/summary文件，不从历史证书拼接新会话。

## 实际修复

新的 `wal_position / wal_order` 在已由 `replay` 检验frame seq、hash-chain、owner、run/round、票据和非递减原始clock的账本内，用**事件对象对应的唯一物理帧位置**核对顺序。相同monotonic_ns允许合法相邻事件；倒序、重复身份、缺事件、跨ticket与降低clock仍拒绝。没有将所有严格时间谓词机械改为`<=`，也没有改动旧历史Verifier。

shape-observed→strict-parser disposition→RECEIVED/UNKNOWN、Explorer选择→Target side effect、独立DomainVerified→cleanup→FeedbackFrozen→第二轮Explorer均绑定当前WAL。业务POST先于ACK suppression及UNKNOWN exposure的原Domain seq检查保留。原始时钟、response/tool ID和usage来源继续留证。新增六个时钟测试与五类重锚攻击，合成控制总数52；包括实际生产transport/parser seam和固定相等clock。

Provider安全shape仍先于strict语义校验，最多8192字节/receipt12288字节、2个choice/每项2个tool摘要。仅允许结构/枚举/有界数字hint及ID不可逆hash，不保存raw JSON、content/reasoning、原arguments、prompt或secret。未知字符串不原样导出；usage hint不能直接结算。length/filter/null/非法choice、工具、usage仍fail closed；没有强转stop、增加cap或修改SDK。

## 唯一入口与先后条件

```powershell
# 独立快照完整Runtime、focused/合成控制/18历史锚/Reviewed/Public全通过，格式检查和源冻结后：
python -X utf8 -B spikes/rpf-66/rev-3/probe.py init
python -X utf8 -B spikes/rpf-66/rev-3/probe.py metadata
python -X utf8 -B spikes/rpf-66/rev-3/probe.py cold
# 价格复核也通过后，由新probe独占创建paid-gate：
python -X utf8 -B spikes/rpf-66/rev-3/probe.py admit
python -X utf8 -B spikes/rpf-66/rev-3/probe.py live
```

所有入口验证source-freeze、Source/Verifier/raw bytes及实验helpers锁；没有全量PASS不能启动P2/P3。独立根仅`.local/rpf-66-rev-3/`，ABI为`rpf66-config-pge-session-v3`。六个正式端口从40000–44999一次选择，未读取旧运行端口列表。原固定JAR由允许的原始只读源重新复制；不复用旧任务SDK回执、JAR副本、Context/WAL或余额。

唯一Session最多2 Explorer、12 Target，全部Provider≤14，永久预约≤35000tokens，成本guard≤¥0.75；metadata默认1、cold1、正式SDK/JVM各≤2、HTTP24/POST4/health6，transport retry0。Explorer cap2500/output128，Target每轮cap3000+5×2400/output256，原prompt及候选保持。UNKNOWN Provider阻断后续paid，业务UNKNOWN停写后只读对账，均保留费用和未决状态。价格以[官方定价](https://api-docs.deepseek.com/quick_start/pricing/)和[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)执行日复核，×15为审慎guard，非账单或汇率。

## 有限差异调查

旧HTTP testcase最多四次被动socket/HTTP审计，只存PID、loopback端口、send长度、时钟与finally后端口状态，不存header/token原文。被动审计仍可能影响竞态，不能以几次通过确证根因。旧fixture与case均不修改；Full suite不加观察器、不monkeypatch、不筛选、不skip旧case。具体Base/候选、3.14/3.12结果及clock/OTel差异见runtime-gate-differential。

## 成功证书与能力范围

只在本轮真实完整两轮且严格离线验证成功时exclusive-create `dual-agent-witness.json`。独立校验：

```powershell
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_r66_verify spikes/rpf-66/rev-3/dual-agent-witness.json --sha256 <external-raw-sha256>
```

原件外锚正确/缺/错应为0/2/3，真实52类重锚控制均拒绝；无原件时这些真实检查NOT_RUN，不写占位证书。重复候选可如实L2=false，未完成第二轮L2=NOT_RUN。仍限一例受控配置Java/H2、同服务只读HTTP Authority；不建立订单真实Target、跨域双真实、Web Live、Issuer、独立复现、因果优势或部署授权。源码复制债与父解释器兼容性继续显式报告。

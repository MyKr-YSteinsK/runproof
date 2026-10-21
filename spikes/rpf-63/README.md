# RPF-63 · 真实 Explorer × 真实 Target 配置 Session

本次版本化配置 Session 将真实 Explorer 选择、固定 SDK Target 的真实 Tool Calling、fresh Java17/H2、非 LLM Oracle 和反馈绑定在一个物理 append-only `ledger.jsonl` 中。仅配置域；Web/Gateway 未接入。

## 实际观察

Session `rpf63-session-0665761f208446c7` 两轮都由真实 Explorer 选择 `local-delivery-suppressed-after-http200`。两轮均在 update HTTP200 已提交后抑制 COMMITTED，向 Target 返回显式 UNKNOWN；模型随后调用只读 inspect，独立 current/history/list 验证 v2/history `[2,1]`，各只有两个 POST。第一轮验证与清理完成后的反馈绑定原 Explorer ToolCall ID，进入第二轮实际 Provider 请求。

两轮重复选择合法；第二轮新增事实为空，`L2_observed=false`。normal 候选本次真实 `NOT_RUN`；四种组合只在合成回放中验证。一次 Session 不建立因果或统计优势。

Provider Explorer2 + Target10 =12次；9972输入+1006输出=10978tokens；保守费用估算CNY0.062982。不可返还预约30000tokens/CNY0.54，低于Plan费用硬上限0.65。执行日核对[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)峰值USD0.30/1.20每百万输入/输出，乘15币种守卫；不是实时汇率或账单。

## 独立离线核验

从本分支仓库根执行，不需要 Provider Key、SDK、Java 或旧运行根：

```powershell
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_dual_verify spikes/rpf-63/dual-agent-evidence.json --sha256 f70c9260347e7b91829e032b1fec69b13d070f42998de0ba818f97f18ec4b299
```

正确/缺失/错误外部锚退出码为0/2/3。证书schema=`rpf63-dual-agent-evidence-v1`，source_kind=`REAL_EXPLORER_REAL_TARGET`；原字节374702 bytes。内容锚和Source Map提供完整性检查，不能建立发行者真实性。

纯合成协议测试会在本任务 `tests/` 下创建显式合成账本，无真实 Provider/JVM/SDK：

```powershell
python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_dual -v
```

## 一次性执行入口

`probe.py metadata/cold/live` 是本次任务的已使用Gate，不能当作复跑授权。metadata1、cold1、正式Session1/两Trial、JVM2/SDK2额度已消费；当前交付HEAD已不同于执行Base。不得删除WAL/marker、复制任务或改Run清账。未知Provider用量停止后续收费和业务路径；UNKNOWN写先停写，只允许固定GET对账。

静态新Config Port实现兼容的 `run(capability, context)` 调用形状，使用新owner与run-scoped上下文。固定Host/HTTP/SDK保持原源码；SDK子进程无Provider/业务Key，只能访问受限loopback Host。当前生命周期仍有复制与任务绑定，不能声称完成通用Adapter抽取。

[接口与复制债](capability-assessment.json) · [预检](preflight-diagnostic.json) · [会话摘要](session-summary.json) · [验证诊断](verification-diagnostic.json) · [唯一TASK_RESULT](RESULT.md)

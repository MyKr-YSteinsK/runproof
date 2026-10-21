# RPF-64 · 稳定 TaskContext 与双域 DomainPort

新版本的冻结 TaskContext、静态 DomainPort、一个物理 `ledger.jsonl` 和共用 `SharedSession.execute(domain)`，已在一个新Session里执行订单 SQLite 与配置 Java17/H2 各一次。订单为确定性驱动；配置通过真实固定SDK **scripted Fixture** 调用真实业务HTTP。本轮 Provider/模型tokens/费用均为 **0**，没有读取 Provider Key。

## 实际结果

订单完成唯一2500分CNY虚构全额退款，由独立只读连接的 AuthorityReader 核验唯一COMMITTED收据。配置在真实HTTP提交v2之后把Tool成功回执局部抑制为UNKNOWN，SDK scripted回调随后inspect；同服务只读current/history/list核验v2/history `[2,1]`，共9 HTTP/2 POST。没有重复业务写入。

两域经同一个共用调度/预算/Oracle→反馈冻结/cleanup协议入口运行；领域事实分别作用于自己的Authority。该证据等级为 `BOTH_REAL_CONTROLLED`，不能提升为真实Explorer/Target或跨域自主PGE研究结果。跨域信息增益 `NOT_COMPARABLE`。

## 独立离线验证

从本分支仓库根运行；不需要Provider Key、SDK/JDK、旧ignored根或启动业务：

```powershell
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_portability_verify spikes/rpf-64/portability-witness.json --sha256 d5798bfa82ef9523039a1461c82842aa9f265703ada492cef3cf068208e5ff19
```

正确/缺失/错误外部锚退出码0/2/3。原件84779 bytes，schema=`rpf64-portability-witness-v1`；独立指验证程序与受测执行器分离，不建立Issuer签名真实性或独立复现。

纯合成测试（只在本任务 `tests/` 中写协议样例，不启动SDK/JVM或实际SQLite退款）：

```powershell
python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_portability -v
```

## 有界执行与维护

`probe.py metadata / cold / live-controlled` 仅为本次一次性Gate；metadata1、cold1、订单1、配置1/JVM1/正式SDK1额度已消费。交付HEAD已不同于执行Base，不得删除WAL、重命名Run或复制任务清账。今后真实实验须新Plan。`probe.py verify` 只核本次保留的ignored原件；可移植公开入口是上面的纯离线CLI。

TaskContext的frozen bytes持有owner/source/capability/预算和环境；可信root对象独立校验路径与junction。DomainPort不再持有全局WORK；一个ProcessSupervisor管理两个SDK和一个JVM，单文件WAL在I/O前fsync预约。当前授权Context工厂仍只接纳RPF64，固定SDK/三工具协议、两领域Oracle和版本化合同仍需维护；没有动态插件/调度器或任意工作流能力。

[复用与复制债](portability-assessment.json) · [预检](preflight-diagnostic.json) · [Session摘要](session-summary.json) · [验证诊断](verification-diagnostic.json) · [唯一TASK_RESULT](RESULT.md)

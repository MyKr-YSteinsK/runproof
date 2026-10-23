# RPF-66/rev-4｜终止预算协议调查

状态：**Blocked**。本目录保存原严格解析器的第四处输出上限证据。尚未实施 v4 Host、Broker、Context、WAL 或 Witness。

在仓库根使用 Windows Python3.14：

```powershell
python -X utf8 -B spikes/rpf-66/rev-4/probe.py init
python -X utf8 -B spikes/rpf-66/rev-4/probe.py verify
```

`init` 仅在本轮已经创建、忽略且无重解析点的 `.local/rpf-66-rev-4/` 内，以 create-only 写离线诊断；重复运行拒绝覆盖。`verify` 重跑12个原解析器夹具并核对该诊断，无证书验证含义。两者都不联网、不启动SDK/JVM、不读Provider Key。

`metadata / cold / admit / live` 均输出 `BLOCKED`、exit3，消耗资源为0。不存在付费入口、Source Freeze、会话账本或真实Witness；这些模式不冒充完整 staged runner。

原解析器 `config_live_runtime.py:628` 直接使用受保护常量256；没有 per-request cap 参数。stop+completion256合法，257/300/512被原解析器拒绝。`length`在128/256/512都拒绝。修改发包上限不能单独解决接收端合同冲突。

请阅读 [RESULT.md](RESULT.md) 和 [terminal-budget-analysis.json](terminal-budget-analysis.json)。旧源码与旧运行根保持原样；本次预算数学只是目标分析，未产生真实512出站证据。

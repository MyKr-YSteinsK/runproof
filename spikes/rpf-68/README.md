# RPF-68：双域共享 Session 原型

状态：**BLOCKED**。免费固定 SDK 与真实受控 Java/H2、SQLite 普通路径通过；最大合法输入预算失败，真实 Provider 会话和跨域 Witness 均未运行。

## ABI 与执行边界

- owner `rpf-68`，ABI `rpf68-shared-real-cross-domain-v1`；配置→订单固定顺序。
- immutable Context、单一 fsync/hash-chain WAL、全域不可回收资源票；typed Port只提供两域各三个工具。
- 独立Oracle与cleanup完成后才 `DOMAIN_VERIFIED → FEEDBACK_FROZEN`；下一Explorer绑定原ToolCall ID及反馈digest。
- 固定SDK child没有Provider/业务Key，仅可连接父loopback Host；Host执行受限工具与模型HTTP。
- `reserve → result`；未知Provider结果停止写/调用；pre-send拒绝保留receipt，允许合同内只读核对；孤立/缺失receipt均fail closed。
- 实际Provider路径同时要求Source Freeze、免费Gate及Admission。本轮这些正式凭据未创建。

## 命令

```powershell
# 免费fixture会创建本任务synthetic子根、启动Java及固定SDK
python -X utf8 -B spikes/rpf-68/probe.py free
# 外部raw锚：合法exit0，缺锚2，错误/重锚非法3
python -X utf8 -B spikes/rpf-68/probe.py verify --witness <file> --sha256 <external-sha256>
python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_r68 -v
```

`preflight/metadata/cold/admit/live` 是显式阶段入口，不能自动补齐Gate。本次最大输入失败，禁止进入正式阶段，需新Plan批准协议/预算修订。不能挪用总池、截断消息或换候选重跑付费。

## 证据导航

[RESULT.md](RESULT.md) 是唯一TASK_RESULT；[verification-diagnostic.json](verification-diagnostic.json) 记录命令/PID/源/结果；[architecture-decision.json](architecture-decision.json) 区分事实、判断和路线。`cross-domain-witness.json` 必须不存在。

普通fixture成功不证明真实双Agent、第三域、L2、因果优势、Web接入或生产可用性。

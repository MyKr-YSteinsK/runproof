# RPF-66：双真实角色配置 PGE 与统一 WAL

本 Spike 把有界 Explorer 选择、版本化配置 Target Port 和独立只读业务验证连接到同一 Context / Session / 物理 WAL。实际运行结论见 [RESULT.md](RESULT.md)、[session-summary.json](session-summary.json) 与 [verification-diagnostic.json](verification-diagnostic.json)。合成样本只标记 `SYNTHETIC_TEST_ONLY`。

## 调用与复用

`probe → TaskContext / Ledger → Session → Explorer.choose → ConfigPort.validate_contract / execute / verify / cleanup → feedback → Explorer.choose(round2)`。

Target 执行 `assemble_host(ctx, ct, ledger)`，同一个 Ledger 注入 Journal、HTTP client 和 Target Broker；Host 使用该 Broker 与 ConfigLiveBusiness。SDK 和 Java 均通过原 `ProcessSupervisor.start/received/close`，每轮独立 namespace / run / 端口 / H2 cwd。新 Ledger 为共用 Supervisor 的资源事件补足 round/run 绑定。Provider 内存索引只派生于同一 WAL 的 checkpoint。

| 边界 | 实际处理 | 原因及限制 |
|---|---|---|
| DomainPort 四方法 | 保持结构协议；新静态 ConfigPort | 原 domain selector 不支持新真实来源，不调用其旧注册表 |
| ProcessSupervisor | 直接复用 RPF64 原类 | 结构接口可注入新 Context/Ledger；无 owner 替换 |
| ConfigLiveHost / Business / HTTP / SDK | 复用固定底层 transport、严格 tools、外部 SDK | 新 Host/Http 显式装配新合同；不调用旧 Host constructor 的旧 schema 验证 |
| Context / WAL / metadata | RPF65 最小版本化适配 | 新 owner、两轮候选、角色/round quota；固定源 inspector 只读，新 JAR 副本 |
| Explorer HTTPS / shape | 直接复用 request / safe_response_shape / fingerprint | 新候选 schema 和解析函数；只发 select_experiment，无业务凭据或写工具 |
| Target Broker / Host / 生命周期 | RPF65 版本化复制并适配 | 原 factory / ctx.contract / owner 为单轮固定；保留复制债，未重构历史 |
| Session / Feedback / Verifier | 新代码结合历史纯校验模式 | 首轮 Oracle→Verifier→DOMAIN_VERIFIED→FEEDBACK_FROZEN 先于次轮付费预约 |

详见 [capability-assessment.json](capability-assessment.json) 的源码近似复制量和范围。新源码闭包包含五个 Runtime 文件、测试、probe 及实际依赖；无 Witness 自引用。

## 候选、预算和未知

- `normal`：无故障，fault 四态 false；inspect→create v1→update v2 后正常返回 COMMITTED。
- `local-delivery-suppressed-after-http200`：真实 update HTTP200/code0/v2 后抑制 Tool ACK 为 UNKNOWN，止写，允许一次模型 inspect；父进程独立 GET current/history/list。
- 每轮 Explorer1 / Target≤6；Provider≤14，永久预约≤35,000 tokens，守卫费用≤¥0.75；Provider retry0。报价依据[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)与[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)于 2026-10-22 复核，USD0.30/1.20 每百万乘15守卫系数，非汇率或账单。
- Provider usage/response 未知、业务未知、清理失败、Source drift 均停止剩余付费与写入，保留唯一现场，允许范围内 GET-only 对账。
- 两轮真实重复选择合法，`L2_observed=false` 可接受；选择不同且有新增验证事实也仅为观察性信号，`causality=NOT_PROVEN`。

## 分阶段入口

以下从仓库根运行。只允许本 Plan 的新 `.local/rpf-66/`，不可重新初始化、换根或重试 Session。

```powershell
python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_r66 -v
python -X utf8 -B spikes/rpf-66/probe.py init
# 免费全 Runtime / 18 历史锚 / Reviewed / Public / 合成负控通过后冻结源。
python -X utf8 -B spikes/rpf-66/probe.py metadata
python -X utf8 -B spikes/rpf-66/probe.py cold
# 已冻结源与全部免费记录一致、独占 paid-gate 已建立后，唯一正式运行：
python -X utf8 -B spikes/rpf-66/probe.py live
```

`metadata/cold/live` 均使用已消费票据，重复入口 fail closed。离线验证不读 key、不启动服务：

```powershell
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_r66_verify spikes/rpf-66/dual-agent-witness.json --sha256 <external-raw-sha256>
```

正确/缺失/错误锚分别 exit0/2/3。仅真实两轮完整且新 Verifier 成立才创建 Witness；失败时该文件保持不存在。

## 证据能力边界

Authority 是 `SAME_SERVICE_READ_ONLY_HTTP`。Source hash / 外部 SHA / 离线验证约束证据内部一致性，不建立第三方 Authority、Issuer 签名或独立新环境复现。未验证订单真实 Target、双域真实会话、Web LIVE、L3 对照、统计因果或生产 SLA。无主线合并、PR、部署或赛事上传。

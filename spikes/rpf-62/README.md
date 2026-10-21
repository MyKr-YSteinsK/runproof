# RPF-62 · 真实配置 Target Capability Spike

本目录新增静态 `TargetCapabilityDriver.run(capability, context)` 接口和一个配置实现，接入原固定 Pydantic AI SDK、可信 Host、真实 Java17/H2 与一个任务主账本。它保留旧 RPF57/60 源码、证书和 UI，没有集成新 Explorer 或 Web Live。

## 本轮实际结果

唯一 Run `rpf62-62e94a1d96eb954a42` 的真实 Target 依次调用 inspect → create v1 → update v2 → inspect。Java update HTTP200 后，Host 抑制 COMMITTED Tool 结果，改为预注册的 `UNKNOWN_OUTCOME`，并禁止再次写入。第四次真实模型请求收到这一未知结果，选择只读 inspect；第五次收到 PRESENT/v2 后结束。独立 GET current/history/list 核验 v2/history `[2,1]`，没有第三次 POST。

Provider5 / tokens4945 / 保守估算CNY0.028368；一次metadata、一次真实冷Fixture、一次正式JVM/SDK/场景、业务HTTP9/POST2/health1。预约池12000tokens/CNY0.216不返还，任务费用硬上限CNY0.25。本轮费用估算采用执行日核对的[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)峰值及15倍币种守卫，不等于账单或汇率。

这是一项可见Tool返回的本地控制干预，不是TCP丢包、SDK崩溃或生产配置操作。模型看到的是显式未知结果，未看到被抑制的成功JSON；父控制器保留HTTP提交证据。模型是否有因果/统计优势、发行者身份、数据库外部Authority与独立复现均未建立。

## 离线审查

从本分支仓库根运行，只读已提交源码和原件，不需要Provider Key、SDK进程、Java或旧local目录：

```powershell
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_target_capability_verify spikes/rpf-62/real-target-witness.json --sha256 898b3aef8e0a58b69de09ebbecb6973735af929555a7f1be80305264d40997c4
```

正确/缺失/错误外部锚退出码0/2/3。原件164,538 bytes；schema `rpf62-real-target-witness-v1`，source_kind `REAL_PROVIDER_TARGET`。Verifier对调用来源、未知结果回注、只读恢复、领域Oracle、同一物理账本、PID/源码/SDK和清理进行确定性检查。Hash是内容锚，不是数字签名。

新离线测试入口（会在本任务测试目录生成明确合成数据，不创建真实业务）：

```powershell
python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_target_capability -v
```

## 一次性执行入口的限制

`probe.py metadata / cold / live` 是本次已耗尽一次cold与正式场景的Gate入口，**不是复跑许可**。它固定Base/分支、SDK与Java来源、冻结源码、免费Gate、价格核查和不可返还预约。当前交付HEAD已不同于执行Base；不能checkout旧Base、复制工作区、删除account/marker或改Run来清账。未来新实验需要新的Plan和任务身份。

正式Provider Key只在可信父Host中读取；SDK子进程无Provider/业务Key，网络仅可到指定loopback Host；Java只用本地合成Key。预检从既有指定SDK安装和Java source bundle核身份，本目录不安装、构建或下载依赖。未知usage阻止后续Provider请求，未知写冻结后续写入，允许独立只读核验。

接口/风险映射见 [capability-assessment.json](capability-assessment.json)；固定身份与唯一冷启动见 [preflight-diagnostic.json](preflight-diagnostic.json)；CLI负控、历史锚与回归见 [verification-diagnostic.json](verification-diagnostic.json)；唯一正式结果见 [RESULT.md](RESULT.md)。RPF61材料的PPTX/ZIP提交工作不因本实验取消。

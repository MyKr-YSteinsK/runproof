# RPF-51：config-center HTTP Effect 与离线 Witness

本 Spike 为已有的 config-center Spring Boot 服务接入一个受限 HTTP Tool Host、只读 Authority Reader、确定性 Effect Oracle 和纯离线 Witness verifier。它只允许访问固定的 `127.0.0.1:<冻结端口>` 与预注册配置项；写入限定为一次创建、一次更新、一次 stale-version 负控。HTTP redirect 不跟随，POST 不自动重试，传输结果不明时只允许只读调和。

运行前冻结 Execution、Effect、Experiment 三份合同，并将 config-center 的精确源码提交、源码清单和可运行 JAR 哈希绑定到合同。Witness schema 为 `rpf-config-http-witness-v1`，来源等级是 `CONTROLLED_EXTERNAL_HTTP_SERVICE`。核验器只使用 Python 标准库；证据不会声称签发者认证、数据库独立权威或远程来源证明。正确外部 SHA 锚、缺锚和错锚分别使用 exit 0、2、3；外部锚必须来自待验文件之外的可信记录。

## 命令

在满足新鲜隔离目录前置条件的 checkout 中，Plan 所规定的入口为：

```powershell
py -3.14 -B spikes/rpf-51/probe.py --prepare
py -3.14 -B spikes/rpf-51/probe.py --run
py -3.14 -B -m runtime.runproof_runtime.effectwitness.config_http_witness <witness.json> --expected-sha256 <trusted-file-sha256>
```

`--prepare` 与 `--run` 组成一次性流程。当前 RPF-51 rev-1 checkout 已消费唯一运行标记，不可重置或再次运行。此次服务在 readiness 前退出，没有发送 HTTP 请求，也没有生成 `config-http-witness.json`；真实运行结论和后续修正边界见 [RESULT.md](RESULT.md)。

## 验证

```powershell
py -3.14 -B -m unittest runtime.tests.test_effectwitness_config_http -v
py -3.14 -B -m runtime.runproof_runtime.effectwitness.config_http_witness <witness.json> --expected-sha256 <trusted-file-sha256>
```

定向测试覆盖合同冻结、HTTP 目标与方法限制、redirect/timeout 行为、Effect Oracle 的负向控制、篡改与锚定语义，以及离线导入封锁。完整本轮结果以 `RESULT.md` 为准。

# 本地 SDK 预发送验收

RPF-102 定义了由真实 SDK、本机 Host 和独立回环 Receiver 组成的一致性实验。Host 提供脚本化 completion，并分别统计入站请求、持久预约、物理转发和接收字节。首次正式 NORMAL 失败，UNKNOWN 尚待执行。

在仓库根使用已核实的解释器运行无 SDK 负控：

```text
<python> -B -m unittest -v ci.test_rpf102_sdk_presend
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_probe --owner <32位十六进制owner> --preflight
```

自动 Ubuntu 工作流只运行离线测试和文档检查，并记录 `SDK_PHYSICAL_NOT_RUN_BY_PLAN`。正式运行须单独批准冻结提交、隔离 runner 和物理额度。手动工作流在创建 owner 前核对已批准 SHA、指定 GitHub Run ID 和首次运行。NORMAL 通过独立 Oracle 与公开证据检查后，才会开始 UNKNOWN。见 [rev-3 操作与复核指南](../spikes/rpf-102/rev-3/README.md)。

将来获准运行后，可以离线读取公开诊断并在上传前校验：

```text
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_probe --owner <新owner> --diagnostic NORMAL > diagnostic.json
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_diagnostic < diagnostic.json
```

每个已启动场景使用独立文件。诊断不可用时命令以非零退出，stdout 为空。手动工作流在失败后也会校验证据包，仅上传通过校验的内容。回执只含白名单字段，缺少计数证据时使用 `null`。SDK 日志、环境原件、握手凭据和未获准的字节保留在 owner 内。

独立 Oracle 用于检查完整的场景证据：

```text
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_oracle <owner> NORMAL
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_oracle <owner> UNKNOWN --expected-sha256 <可信证据锚>
```

NORMAL 预期两次转发。UNKNOWN 预期先持久锁存，再回注工具结果。第二次 completion 被拒，合计只转发一次。独立核验会比较 receiver 原始字节、Host 回执和工具回注链。来自同一 owner 的摘要只支持本地内容比对。第三方签发者、付费模型行为、历史修复和产品接入仍有各自门禁。

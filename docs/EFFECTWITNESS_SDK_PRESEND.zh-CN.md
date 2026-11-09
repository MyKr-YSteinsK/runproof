# 本地 SDK 预发送验收

RPF-102 让实际安装的 SDK 连接本机 Host，由独立回环接收进程保存转发字节。Host 返回脚本化 completion 与工具调用，SDK 在工具回注后发起后续 completion。入站请求、持久预约、物理转发和接收字节分别计数。

在仓库根使用已核实的解释器运行无 SDK 负控：

```text
<python> -B -m unittest -v ci.test_rpf102_sdk_presend
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_probe --owner <32位十六进制owner> --preflight
```

独立 Ubuntu 工作流提供获授权的安装路径。它在隔离 venv 从 PyPI 安装固定直接版本的 wheel，并记录 pip check 与实际依赖版本。正式运行仅接纳该任务自有 SDK 环境。每个正式 owner 只接纳一组 NORMAL 与 UNKNOWN。

准入运行后可以脱离 SDK 离线检查：

```text
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_oracle <owner> NORMAL
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_oracle <owner> UNKNOWN --expected-sha256 <可信证据锚>
```

NORMAL 预期两次转发。UNKNOWN 预期先持久锁存，再回注工具结果。第二次 completion 被拒，合计只转发一次。独立核验会比较 receiver 原始字节、Host 回执和工具回注链。来自同一 owner 的摘要只支持本地内容比对。第三方签发者、付费模型行为、历史修复和产品接入仍有各自门禁。

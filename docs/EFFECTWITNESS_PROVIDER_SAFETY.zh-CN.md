# EffectWitness 本地预发送安全验证

RPF-101 验证持久 Host Barrier 和独立进程观测的 TCP 接收。它使用新的任务 owner 与固定合成载荷。回环接收进程通过一次性 nonce 确认身份。Host 在发送前持久记录 SEND_BEGIN，接收进程独立保存实际字节。

在仓库根使用已核实的 CPython 绝对路径，替换下列 `<python>`。

```text
<python> -B demo/probe-rpf101-provider-barrier.py --preflight
<python> -B -m unittest -v ci.test_rpf101_provider_barrier
<python> -B demo/probe-rpf101-provider-barrier.py --inspect unknown-restart
<python> -B -m runtime.runproof_runtime.effectwitness.provider_receipt_verify ready-restart --expected-sha256 <可信证据锚>
<python> -I -B runtime/runproof_runtime/effectwitness/provider_sdk_probe.py
```

unittest 与探针的 `--run` 都是正式入口，每个 checkout owner 只能运行一次矩阵。运行后使用离线检查，原始证据保存在 `.local/rpf-101-provider-presend`。

写入结果未知后，两个域与两种角色都关闭新预约和发送准入。对账只读已有证据。NO_BYTES_OBSERVED 仅表示本机接收进程未观测到载荷。发送先获锁并完成时归为 UNKNOWN 前的发送。完整 READY 链正常重启后，可发送一次此前预约而未使用的票据。

异常退出或持久化错误会保留 active 标记，重启继续拒绝。验证覆盖进程恢复与注入故障，Windows 断电持久性及有权控制整个 owner 的本机特权参与者仍未验证。离线验证器独立重算证据链，外部锚需通过独立可信渠道获得。Issuer 身份尚未建立。

SDK 探针只查已安装包元数据。解释器缺少合格 SDK 时返回 SDK_UNAVAILABLE。RPF-100 产品仍走独立路径，后续接入 Explorer 需要先准入实际 SDK，并将发送前检查接到 Host。

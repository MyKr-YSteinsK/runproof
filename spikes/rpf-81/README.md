# RPF-81 / rev-1 — Durable UNKNOWN / localhost pre-send

本轮是隔离基础设施实验，结果 **PARTIAL**；不是旧 RPF74 修复、真实 Provider 或业务证据。Source 固定为 `ae38691160a9ff951b357802d289b49a6e436b0c`，Owner `rpf-81-rev-1`，ABI `rpf81-loopback-v1`。

先读 [RESULT](RESULT.md)、[source map](source-identity-map.json)、[verification](verification-diagnostic.json)。[loopback receipts](loopback-receipts.json) 含实际 WAL、fsync 回执、独立接收 raw bytes、PID 和宿主日志的逐文件 hex/hash；[preflight](preflight-diagnostic.json) 保留冻结前两版本的现场与 G0 原始收据锚。

## 实现与命令

Journal 单宿主内核字节锁贯穿宿主生命周期；RLock 覆盖 WAL replay → SEND_BEGIN → sendall，UNKNOWN 使用同一锁。每帧 flush/fsync 后另存不可覆盖提交回执，拒绝断裂和已提交尾部丢失。写失败及状态模糊保守停发；只读对账只读取本地 WAL 并记审计事件。

```powershell
python -X utf8 -B -m unittest discover -s runtime/tests -p test_effectwitness_pge_r81.py -v
python -X utf8 -B spikes/rpf-81/probe.py --help
python -X utf8 -B spikes/rpf-81/probe.py verify --case p1-old --file <R81_PRIVATE_ROOT>/runs/p1-old/bundle.json --sha <RAW_SHA256>
```

正式 run 需要匹配的 `source-freeze.json`。`run --case <ID>` 是实际 TCP / create-only 操作，不能对已存在的 case 重新执行；本轮不再发起新运行。正常验证 exit=0；语义/结构拒绝=3；缺输入锚=2；I/O 或持久化不完整=4。`negative --case p1-old` 只生成副本提案，不能覆盖原 WAL，已有目录也不得重建。

Oracle 仅 import stdlib，不复用被测 gate/replay。离线审查时从 capsule 原始 hex 恢复所列的同一相对路径，再调用 `pge_r81_oracle.inspect(raw, anchor, source_id, frozen_spec, root)`；这是同证据再审，不能称为新的物理复现。来源有效的两个危险提案从未发送真实 bytes。

## 已知限制

`Host.blocked()` 的 `recovered=True` 会拒绝一切重启会话。另一个真实新进程对无 UNKNOWN 的 READY WAL 同样 DENY，故恢复的 UNKNOWN 因果归因不足，A05=PARTIAL，源码冻结后未修。已完成两个显式 race；send 先赢时接收者延后读取，不能推导 UNKNOWN 后才开始发送。

双方仍为同宿主同 Owner，Hash 不认证独立 Issuer；不证明真实模型/Provider/业务效果、硬件断电持久性或通用并发性质。完整旧 Runtime、Release Gate、Java/Web 均 NOT_RUN_BY_PLAN。19 项聚焦测试冻结后两轮全过；四类异常保持 INCOMPLETE。

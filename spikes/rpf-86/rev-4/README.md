# RPF-86/rev-4 Durable Denial Journal

本轮封存为 **PARTIAL / B_UNACTIVATED**：有界实现及取证已完成，原生准入仍 FAIL。唯一原生诊断约 49.18s，五方法 PASS，但 import 阶段有两次 open/read 被 Guard 拒绝；14 帧 journal 完整，terminal=FAIL。未开放目标读取、未重复 cohort、正式五方法 NOT_RUN。

- [TASK_RESULT](RESULT.md)、[拒绝归因](denial-attribution.json)
- [性能观察](performance-diagnostic.json)、[验证](verification-diagnostic.json)、[反例](counterexamples.json)
- [决策](decision.json)、[G0](preflight-diagnostic.json)、[三份 Base 快照](pre-repair-sources/)

真实 native suite 不安装 sys.settrace；只有隔离 synthetic 控制和独立 microprobe 保留明确 trace。journal 在安装 Guard 前预开独占 fd，每重要帧 write-all+fsync，拒绝事件在抛出前落盘。独立核验是同一现场另一进程，不是新环境复现或 Issuer。

聚焦命令为 `python -B -m unittest discover -s ci -p test_run_rpf86_owner_admission.py -v`，需要已核验的本轮 fresh `RPF86_TASK_ROOT`。23 项正式控制已运行一次；本轮 native 次数不得追加。每 native≤120s、unit≤180s、verifier≤60s、输出≤2MiB，总实验 wall cap480s。539 required UNAVAILABLE 及工作流保持不变。

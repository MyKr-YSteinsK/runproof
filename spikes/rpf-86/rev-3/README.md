# RPF-86/rev-3 拒绝归因与严格准入

本轮为 **PARTIAL / B_UNACTIVATED**。归因 journal、调用行和方法状态绑定、原生 PermissionError 假绿负控已实现；冻结后 16 项单测 PASS。唯一原生诊断在首方法运行时到达 180 秒上限，未产生封存 journal，历史两次拒绝的原因仍 UNKNOWN。正式五方法 NOT_RUN，工作流不变。

- [TASK_RESULT](RESULT.md)、[拒绝归因与未知](denial-attribution.json)
- [验证诊断](verification-diagnostic.json)、[负控](counterexamples.json)、[决策](decision.json)
- [G0](preflight-diagnostic.json)、[三份原始工作树快照](pre-repair-sources/)
- [rev2 原报告](../rev-2/RESULT.md) 保持不变。

本地聚焦命令：先将 `RPF86_TASK_ROOT` 指向已核验的 fresh rev3 owner，再执行 `python -B -m unittest discover -s ci -p test_run_rpf86_owner_admission.py -v`。本轮原生诊断预算已用尽，不授权额外运行。每 child 输出 ≤2MiB；原生/单测 ≤180s、verifier ≤60s，诊断+正式 wall cap 600s。证书保持 exact-match/read-only/hash-bound；不开放目录。

本试点是合成离线测试与同一次现场的独立进程核验，不是实际 Agent/SDK/Provider 成功、第三方 Issuer 或新环境重现。1232 required、539 UNAVAILABLE 不变。

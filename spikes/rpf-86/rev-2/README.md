# RPF-86/rev-2 精确证书只读试点

本轮只开放 `spikes/rpf-53/rev-6/config-live-evidence.json` 的 exact-match、read-only、hash-bound 读取，不修改原 Runtime、原五方法、历史证书或 RPF85 覆盖责任。

结果为 **PARTIAL / B_UNACTIVATED**。唯一冻结前预试的方法事件为 5 PASS，但 Guard 记录 2 次 READ_SCOPE_DENIED，子进程 exit1。正式五方法 NOT_RUN；正式增强单测 12 PASS，独立进程仅确认负证据。工作流保持 Base 字节，不激活 hosted pilot。

- [正式结果](RESULT.md)、[验收诊断](verification-diagnostic.json)
- [证书边界](certificate-read-boundary.json)、[负控](counterexamples.json)、[决策](decision.json)
- [G0](preflight-diagnostic.json)、[原始源码快照](pre-repair-sources/)
- [rev1 结果](../RESULT.md)：3 PASS/2 ERROR 的历史预试保持不变。

本地命令需把 RPF86_TASK_ROOT 指向已核验的本轮 fresh owner（见 G0 收据）；运行 `python -B -m unittest discover -s ci -p test_run_rpf86_owner_admission.py -v`。新 native run 入口仍是 `python -B ci/run-rpf86-owner-admission.py --output <fresh-owned-child>`；本轮正式 native 未运行，不在此授权额外重试。每 child ≤180s、输出 ≤2MiB；独立 verifier ≤60s、正式合计 ≤420s。

证据属于合成离线测试，不是实际 SDK 调用、第三方签名或新环境独立复现。539 required UNAVAILABLE 保持，不构成 release/deploy 授权。

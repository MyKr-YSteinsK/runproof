# RPF-86/rev-5 Import cache 因果与严格 owner 准入

本轮本地 **STRICT_ADMISSION_ACTIVATED**：import-only 实测两个被拒请求分别严格匹配固定 RPF55/RPF53 probe.py 的 bytecode-cache 候选；未读取、列举或 stat 旧 cache。原 Guard 保持拒绝。将 sys.pycache_prefix 指向每次 fresh owner/pycache 并保持 -B 后，诊断及冻结后正式五方法均 PASS，正式零 Guard denial、12 帧完整 PASS journal，独立进程复核 PASS。

- [TASK_RESULT](RESULT.md)、[import归因](import-probe-attribution.json)
- [验证](verification-diagnostic.json)、[性能](performance-diagnostic.json)、[反例](counterexamples.json)
- [G0](preflight-diagnostic.json)、[决策](decision.json)、[Base快照](pre-repair-sources/)

正式 harness 27/27 PASS，保留原23 test IDs/实质断言。harness 在 formal 前冻结，workflow 只在本地正式成功后加一个 pilot step 和独立白名单 public-result artifact，再单独冻结。封存时 Status PARTIAL，未来 Git/hosted 尚未发生，最终聊天补实际收据，不 amend。

本地命令需已核验 fresh RPF86_TASK_ROOT：`python -B -m unittest discover -s ci -p test_run_rpf86_owner_admission.py -v`；`python -B ci/run-rpf86-owner-admission.py --output <new-owned-child>`。本轮诊断/正式 native/单测/独立核验次数已用，不能复用或覆盖旧 owner。hosted 只使用 ci-results/rpf86-run-attempt，验证 GITHUB_SHA=HEAD。539 required UNAVAILABLE 不减，不构成 Stage Advance、真实 Agent/Provider/Issuer 或 release/deploy。

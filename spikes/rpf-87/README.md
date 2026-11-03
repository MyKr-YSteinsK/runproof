# RPF-87 跨 lane 必需覆盖结算

新只读 verifier 先执行原 RPF85 完整 enforce，再核验同 Run/SHA 的 RPF86 native/独立进程/日志/journal/manifest/WAL source。exact五方法原子提升；任一缺失或错误全组不提升，保留539。只有新派生账本表达有效覆盖，原Router/Handoff/Pilot不改。

- [TASK_RESULT](RESULT.md)、[ID差集provenance](coverage-provenance.json)
- [验证](verification-diagnostic.json)、[反例](counterexamples.json)、[G0](preflight-diagnostic.json)、[决策](decision.json)

本地17项正式测试通过，合成CLI得到693/5/534，仍enforce exit1；这不是hosted已实现的覆盖。真实hosted必须由普通Push产生的新Run读取同一次RPF84/85/86收据后证明。封存时为PARTIAL/A_ACTIVE，Git/CI尚未执行，最终聊天补后续事实，不amend。

本地测试：RPF87_OWNER指向已核验fresh任务根；测试driver把每方法限制为175秒、输出2MiB。合成CLI必须显式--synthetic及--fixture-root，禁止在GitHub Actions冒用。本轮不调用RPF86 run/native/independent或Guard.install，不导入Runtime测试，不读取旧owner/证书。

hosted：`python -B ci/reconcile-rpf86-required-coverage.py assess|enforce --ledger <same-run-rpf84> --handoff <same-run-rpf85> --pilot <same-run-rpf86> --output <same-run-rpf87> --run-id ... --attempt ... --commit ...`。assess=0仅表示写出可信诊断；534缺口仍enforce=1，无Release/Deploy/Stage Advance。

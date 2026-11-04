# RPF-89/rev-2 — 冻结后超时，B 未激活

[RESULT.md](RESULT.md) 是唯一主结果。当前决定为 **PARTIAL / B_UNACTIVATED**：完整 35 项正式测试达到 300 秒上限，10 项完成 PASS、1 项未完成、24 项未启动。没有 hosted RPF89 stamp/assess，也没有正式覆盖提升。

两份 Python 候选保留冻结字节；workflow 恢复 Base blob `0cfc1a8ec53899eb6e9fe6aee46396ffa8af506b`。冻结的 A workflow 候选、原日志和失败收据只留在本轮唯一 ignored owner，未覆盖或重签。

- `preflight-diagnostic.json`：G0、恢复核验、白名单。
- `verification-diagnostic.json`：正式超时、各项状态、独立 B 核对。
- `counterexamples.json`：实际完成与未完成的测试清单。
- `chronology-boundary.json`：post-completion 设计及局部合成观察，非 hosted 证明。
- `source-identity-ledger.json`：Base pins、冻结哈希与 B workflow 恢复。
- `coverage-provenance.json`：1232 IDs、五项旧准入和十八项候选；正式缺口保持 534。
- `decision.json`：Gate、B 与后续边界。
- `pre-repair-sources/release-gate.yml`：`reference_only` 的 Base workflow 原始字节快照。

新 CLI 的 `stamp/assess/enforce` 候选尚未获得完整验收。当前 CI workflow 未调用它；hosted 模式还要求已激活的 workflow 身份，因此不能把该候选当作已上线的覆盖门禁。不得以局部合成 711/5/516 代替正式通过，亦不得重新使用旧 owner 或重跑已封存正式测试来刷 PASS。

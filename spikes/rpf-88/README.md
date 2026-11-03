# RPF-88/rev-1：R72 fresh-owner 候选，未激活

当前结论为 **PARTIAL / B_UNACTIVATED**。唯一预试在导入阶段触发 Guard 拒绝；原 R72 的 18 个方法执行数为 **0**。本目录不是 18/18 的证明，不能据此提升 Required Coverage。

- [RESULT.md](RESULT.md)：唯一主结果、失败边界与 Gate。
- [cohort-inventory.json](cohort-inventory.json)：25 个原方法、18 个候选与 7 个排除项的原分类及 AST。
- [preflight-diagnostic.json](preflight-diagnostic.json)：G0 与精确源码闭包。
- [verification-diagnostic.json](verification-diagnostic.json)：真实预试、13 项冻结后控制、独立 B 诊断。
- [counterexamples.json](counterexamples.json)：控制类别和不能据此声称的结果。
- [decision.json](decision.json)：B 及验收状态。
- [pre-repair-sources/release-gate.yml](pre-repair-sources/release-gate.yml)：修改前 workflow 原始字节；当前 workflow 与它完全一致。

候选 harness 位于 `ci/run-rpf88-r72-owner-scope.py`，控制测试位于 `ci/test_run_rpf88_r72_owner_scope.py`。本 Plan 的预试已使用，当前不再启动 cohort；后续须先审查源码父目录 listing 与原 import loader 的准入合同。不能重置 owner 或放开整个仓库读取权限取得 PASS。

控制测试可在获授权的新任务 owner 下使用 `RPF88_TASK_ROOT` 定位输出；不能套用旧 RPF88 根反复获取原生运行预算。本轮 workflow 没有 RPF88 step 或 artifact。既有 RPF87 的 534 缺口及最终 fail-closed Barrier 不变，NO_RELEASE / NO_DEPLOY。

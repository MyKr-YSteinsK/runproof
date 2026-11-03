# RPF-89/rev-1：排序证据前置检查，B 未激活

[RESULT.md](RESULT.md) 为唯一主结果。本轮未建立完整 RPF89 assessor，没有十八项准入，workflow 未改。

新 CLI `ci/reconcile-rpf88-required-coverage.py` 是 **B 路径诊断候选**：`diagnose` 只读固定公开源码；`assess/enforce` 在私有收据 I/O 前拒绝并 exit2。不能将它作为已交付的完整跨 Lane verifier。

- `preflight-diagnostic.json`：G0、源码 pins、允许路径。
- `source-identity-ledger.json`：固定源、25 个原方法 AST、18+7 清单。
- `verification-diagnostic.json`：冻结后 12 项 B 控制、独立诊断退出码。
- `counterexamples.json`：已运行控制与明确未运行范围。
- `coverage-provenance.json`：1232 个原 ID、既有五项、十八项候选；无新提升。
- `decision.json`：Gate 与停止理由。

534 是既有覆盖缺口，不是本轮对旧私有证据重新结算的结果。下一审查须明确 RPF87 完成顺序的可接受证明：原生完成收据，或经明确批准的 workflow 因果顺序替代证据。不得擅自改旧 RPF87、推断缺失时刻或新增未授权 CI 私有文件。

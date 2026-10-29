# RPF-82｜Mainline convergence

本切片把已交付研发链与 RPF-79 独立迁移链收敛到现有 main 工作树。规则与当前事实见根 AGENTS、docs/project/CURRENT_STATE.md 和 D-028；迁移目录及旧 feature README 为带日期的历史快照。

入口：[RESULT](RESULT.md)、[integration ledger](integration-ledger.json)、[preflight](preflight-diagnostic.json)、[verification](verification-diagnostic.json)。最终远端 SHA 与 main CI 回执由聊天补证，避免自引用未来提交。

只合并两条固定 Git 历史；未恢复 RPF74/rev4 或 RPF81/rev2，未删除旧分支/worktree/私有运行根。main 拥有源码不等于研究证据已接受或生产路径已安全。默认常规工作在 main，隔离例外仍需明确边界；UNKNOWN、Verifier/Release Authority 和用户文件保护不变。

公开 ledger 给出所有72个 RPF40—81远端分支 HEAD 的祖先关系和缺少数字命名的条目；不声称盘点了私有文件。SOURCE 与 Evidence 的封存状态按原报告保留，本次不重签。

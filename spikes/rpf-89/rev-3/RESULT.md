# RPF-89/rev-3 主结果

Status: PARTIAL（证据封存时 Git/hosted 未执行）；Path: A_ACTIVATED。

Base：`1b949b60ff6b52a911b7ebcdd8b05a23311a5ba9`；branch：`main`。本报告在单次focused Source/Evidence Commit前封存；最终40位SHA、Push和新CI实际回执在聊天补足，不回填、不amend。

## 实际范围及 G0

3M+10A：两份RPF89 Python、唯一workflow；本目录精确十份新文件。G0 12类检查PASS，11 pins、3 modify、10 create-only及ACL/ignore/reparse/casefold/worktree、真实HTTPS远端均核实。旧私有owner、WAL、marker、docs/reviews、docs/project、docs/history未访问；只读公开64项闭包按Plan精确核验。未创建新分支/worktree。

## 性能事实与修复

四次聚焦启动总计13.114秒，均未超时。BEFORE：missing_checkpoint 1.167s、database_copy 7.987s，均exit1，由旧workflow pin的WORKFLOW_DELTA_STEP拒绝。重样本143次Git累计7.146s，fixture0.416s。AFTER：对应1.350s和2.609s，两项均exit0。因为旧样本提前失败，不能把两者当相同完整路径的严格性能基准；历史300秒超时完整根因仍UNAVAILABLE，H2仅支持当前串行Git是显著成本贡献。

修复仅将pilot_revalidate的64份逐项双Git命令改为一次HEAD rev-parse和一次有界cat-file --batch，仍每份重新读真实工作树并比对LF身份；协议、对象header/size/尾字节及source drift严格拒绝。无跨assess、输入或进程缓存。另按合同修复rev3 owner和RPF90 workflow baseline；工作树/HEAD身份无条件核对，合成环境不能绕过。workflow_source成为纯候选delta核验；真实pinned入口仍核验HEAD。测试只把候选workflow输入移至本轮owner，保留原35 IDs及每个原断言调用的AST；新增3项负控。

## 冻结和正式验收

AST/compile、显式owner py_compile、严格JSON、YAML on语义、Bash -n、原workflow结构/命令和diff检查均在freeze前完成。候选workflow当时仅在owner内，原tracked workflow保持Base。冻结源、候选workflow、输入及38 IDs后，**唯一正式全套38 tests：38 PASS / 0 FAIL / 0 ERROR / 0 SKIP**，exit0，27.678秒；stdout 5235bytes，SHA256 `f24e053def6fb1f57972c771b3f4dc3f0f958e21335f9b1f7b3e47a0673ecc64`，无截断，drain joined，实际child退出；owner峰值11994851bytes，小于64MiB。最长方法 `CheckpointAdmission.test_actual_enforce_rejects_noncanonical_and_extra_derived_fields`：6.162秒。未提高300秒上限、未重跑正式全套、未删除任何fixture。

独立stdlib读回新的合成CLI fixture，观察assess/enforce/overwrite真实退出0/1/2；local model 711 PASS / 5 SKIP / 516 UNAVAILABLE、旧5+新18、Dedicated缺394、postcheck严格早于native且三个PID不同。两份真实不同hash SQLite用mode=ro及query_only核实2500/REFUNDED；无业务重写。它不是hosted收据、真实Provider、独立Issuer或Kernel sandbox。正式PASS后才将冻结candidate逐字节激活至workflow。

## Workflow 和未完成目标

保留原RPF90 capture/upload、Router/Handoff、Canonical RPF12、RPF86/87/88、JobSummary、全部原Artifact及旧RPF87 enforce参数/always。仅新增RPF87 assess id，以及postcheck、RPF89 assess、单文件派生artifact、新always enforce；去掉这些delta严格等于RPF90 Base。原Barrier必须真实exit1，新Barrier亦对516缺口exit1，总CI failure才是预期发布拒绝。

已接受历史覆盖仍693/5/534；本地合成711/5/516不授权18项正式晋升。新hosted 711/5/516、同Run 23 IDs、Guard/2SQLite/clock和两个exit1是**未验目标**，封存时NOT_RUN。旧12 Router ERROR历史根因UNAVAILABLE，本轮未追逐或重跑旧Run。

G0/A01–A05/A08/A11：PASS；A06：NOT_RUN（候选workflow已PASS，hosted时钟及旧enforce未验）；A07：NOT_RUN（本地synthetic已PASS，hosted未验）；A09/A10：NOT_RUN_AT_SEAL。最终远端blob、Git/CI和hosted结算由聊天补。所有单项状态见verification-diagnostic.json。

新增Provider/SDK/Key lookup/外部业务HTTP/真实业务写/Java/Docker/生产DB/模型费用均0；只在本任务新owner生成合成SQLite。普通main Push自然触发原已批准CI；无额外dispatch/rerun/部署/发布。RPF74/81不恢复，UNKNOWN/Witness/Source Identity/Release Authority保护不变。RPF82仍PARTIAL，不宣称STAGE_ADVANCED，接受责任保留Architect。

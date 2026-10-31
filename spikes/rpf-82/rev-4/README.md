# RPF-82/rev-4：RPF60 超时取证与未激活候选交付

选择 **B_UNACTIVATED_ROUTER**。本轮保全 rev-2/rev-3 失败来源，精确定位超时停止点；没有修复或重新验收 Runtime。五份 `pre-patch-sources/` 是工作区修补前的原始字节档案，永不导入/执行。

`.github/workflows/release-gate.yml` 已恢复到固定 Base blob `99aee95819cf1e2ea41b0bcfe68b3444730c6ba9`，原 Canonical CI 入口/权限/触发保持原样。`ci/` 下 Router/matrix/单测保留 rev-3 原版本，作为未激活研究候选；不要在本地运行指向受保护 rev-3 owner 的候选入口。CLI help/AST/JSON 检查不等于测试通过。

rev-3 实际超时点为 `SelectTests.test_rehashed_semantic_controls_all_sequences`：模块共同的 300 秒预算到期时前七项已通过，第八项尚未完成，第九项未运行。日志缺少逐方法计时、堆栈采样与 CPU/IO 统计，因此不能声称第八项独占了 300 秒，也不能确认根因。详见 `timeout-forensics.json` 的 FACT/INFERENCE/UNAVAILABLE 分层。

本轮测试（九项 RPF60、Router suite、RPF75、完整发现）均 NOT_RUN，没有重复 300 秒实验。格式/CLI/来源/供给链静态核对实际完成。原 1232 方法账本及 required coverage 原样保留，不因未激活候选而产生全套 PASS。

RPF60 harness 修改经 Base AST 对照：原九个方法名、全部断言、原 helper 相同，竞争测试仅增加 owner 路径传递；无新业务、Provider/SDK 或网络操作。原工作流不提供该 harness 的 `RPF82_TEST_ROOT`，所以 hosted CI 可能出现受控 setUpModule 前提错误，这不能描述成九项产品失败。CI 原已知 audit hook、Windows basename、stdlib 与历史 fixture 问题均未解决。

交付账本绑定 32 个授权路径；B 路径实际 stage 应为 30A+1M，恢复为 Base 的 workflow 不产生差异。报告封存不回填未来 Git SHA 或 CI 结果，最终回执由聊天提供。发布/部署、RPF74/81 恢复和阶段接受均未获授权。

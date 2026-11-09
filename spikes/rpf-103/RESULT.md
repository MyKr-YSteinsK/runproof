# RPF-103/rev-1 · 封存结果

本轮归档及离线验收通过。封存时 Git 提交、推送和新 CI 回执为 `NOT_RUN_AT_SEAL`。现有文件保持原样。

经核验的 Base 为 `cb181bcced89384cc1f2f9a3e7ec43d0456af34b`。GitHub [Run 42631302508](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42631302508) 为手动 attempt 1，审批环境为 `rpf-102-physical`。Job 129208002929 的一次性准入、SDK 物理运行、发布校验与 `verify --require-complete` 均通过。Artifact 13681255432 于 2026-11-09 14:06:34 UTC 创建，远端保留截止为 2026-11-23 14:06:34 UTC。

[同字节归档](evidence/rpf102-run-42631302508-public.zip) 为 17,235 字节，SHA-256 `a730b4dd390704ea9503e6de3d7842b6352a5b48b37c41f3acbe389a2633fd19` 与 GitHub Artifact 一致，Git blob `63fb54aac51cf2ac1b36cb9b2cd0694c5af76eeb`。Manifest SHA-256 为 `a88c0c61e4a5cf85207338030d42a949351796e7876e3a1857b57b538b8dae9b`，owner 为 `0c4a3cd80f534a0eb72fa2d430d1a6ee`。逐项核对了 32 个索引成员和额外的 Manifest，ZIP 元数据和文件内容通过结构与敏感模式检查。10 个 nonce 投影成员的公开摘要不同于原私有字节摘要。本轮未获原私有字节，公开扫描也不构成绝对无敏感信息证明。

| 场景 | SDK POST | 工具回调 | 预约 | SEND_BEGIN / SEND_ENTRY | Receiver 收据 / 字节 |
| --- | ---: | ---: | ---: | ---: | ---: |
| NORMAL | 2 | 1 | 2 | 2 / 2 | 2 / 1092 |
| UNKNOWN | 2 | 1 | 1 | 1 / 1 | 1 / 421 |

在同一公开归档上重新计算两条 canonical WAL 链，核对 SDK、发送入口、Receiver 字节和收据。UNKNOWN 在 seq 8，之后依次为工具结果、第二个 SDK POST、DENY 和 SDK 终止，新增预约和发送入口均为 0。原 Run 使用真实固定 SDK、脚本化本地 Host 和独立回环 Receiver，外部 Provider 请求为 0，Issuer 为 `NOT_ESTABLISHED`。

新增归档测试 8 项通过。另有 3 项 RPF-102 内存控制、1 项隔离的 RPF-100 owner 逃逸负控和缺少权威反馈时的策略控制通过。公开文档检查通过，共 18 文件、7 对。本轮完整 RPF-100 业务和 HTTP 测试为 `NOT_RUN`，其测试创建会话账本和业务库或启动 listener。其他涉及旧根、SDK 或传输的 RPF-102 测试未运行。

[边界和下一轮入口](README.md) 区分 RPF-100、RPF-101 和 RPF-102 来源，说明 Authority、Host Barrier 和验证器的权限。由于缺少可读、可验证的 RPF-100 原始 Witness，当前桥接代码保留为 `RECOMMENDATION`。本轮新物理 Run、业务 SQLite 写入、Receiver、外部 Provider、凭据探测和发布均为 0。RPF-74 缺口、真实 LLM Explorer、同一物理 run 跨域集成和独立 Issuer 尚未验收。证据接受与阶段推进由 Architect 独立裁定。

# RPF-113/rev-1 独立解压验收

本地验收完成。实际远端提交和自然触发 CI 由交付回执补足。ZIP 位置、体积和摘要见[交付清单](DELIVERY_MANIFEST.md)。

| Gate | 实测结果 |
| --- | --- |
| G0 | PASS。现有 main、origin/main 和审查基线一致，限定路径未占用，任务写根已忽略且无重解析，两个端口启动前空闲。本轮允许路径匹配 Canonical CI，未匹配 Product CI 的现行 push 路径过滤。 |
| A01 | PASS。生产构建、20 个白名单成员、ZIP 与旁路摘要一致。独立解压后逐成员复算，AST 闭包恰为 8 个 Python 模块，包根和七项 Witness 源身份在新目录核验。 |
| A02 | PASS。从一个路径带空格的干净解压根用 PowerShell 启动 Node 静态服务和 Python Gateway。监听仅为 `127.0.0.1:4187` 和 `127.0.0.1:8780`，无需 Git、npm、Vite 或源 checkout。 |
| A03 | PASS。Windows Edge 157.0.4341.42 真实页面显式勾选后仅一次 POST，返回 HTTP 200，额度由 1 变 0。只读深链及刷新保留会话和选中事件；浏览器请求及响应未出现 Authorization 头。 |
| A04 | PASS。独立 query-only 读回同会话账本与两域数据库。账本 BLOB 的 SHA-256 等于浏览器下载；解压根独立 CLI 返回 `VERIFIED_ANCHORED` / exit 0，错锚与篡改后重算摘要均返回 `REJECTED` / exit 3。 |
| A05 | PASS。拒绝错误 Host/Origin、缺 Origin、非授权 HTTP 方法、无效类型、未开放接口、源文件、遍历和重编码路径、ZIP 外逃/链接/可执行项、真实目录 junction。实际端口及 owner 冲突未覆盖收据。按进程身份停止 Gateway 后代理返回 503，Edge 显示 `READBACK_UNAVAILABLE` 并锁定写入；停止器确认其余服务退出，保留 owner。 |
| A06 | PASS。Python 11 项、Node 1 个综合用例、Web 75 项、类型检查、生产构建、公开文档检查（18 文件、7 对）。构建保留既有大 chunk 提示。 |
| A07 | 封存时待 Git/远端回执。ZIP 和旁路摘要为本机产物，Git 交付生成器、发行入口、聚焦测试和报告。 |

## 真实会话与证据

会话 `e676ad0cb1f54965839e7c54e9d7fcf8`。Order 的 `UNKNOWN_OUTCOME` 先由只读 SQLite 收据确认 2500 CNY 最小单位退款，再由 `SELECT_OPS` 选择配置实验；首轮反馈 SHA-256 为 `6cad5d4e642842cdb87efe1d72f052848dd6e053d50b69054b1d6f0a04b36a83`。配置从 `release-v1` 变为 `release-v2`。独立读回确认两域各有一笔业务事务、唯一收据，与会话证书一致。

Witness SHA-256 为 `27bbb98f965008b9078b90f8c2fad7cc611dc1aea60596041e71a464298e4207`。本地完整性与绑定已核验，`issuer=NOT_ESTABLISHED`，`release_eligible=false`。

正式冒烟仅一个新 owner 和一个会话，Provider 调用及预约为零。付费、生产、赛事上传均为 `NOT_RUN`。PPT 精修单独交付。

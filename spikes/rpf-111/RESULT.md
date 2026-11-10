# RPF-111/rev-1 封存结果

界面与截图验证已完成。封存时 Git 和 hosted CI 为 `NOT_RUN_AT_SEAL`，提交及远端回执另报。基线为 `49c4d29e4cedcf655aaa89a53053373537e38a63`。

| Gate | 结果 | 实测 |
|---|---|---|
| G0 | PASS | 本地与 fetch 后远端 main 一致，六个目标干净，两份报告路径空闲，构建和截图写入新 ignored owner |
| A01 Visual | PASS | Edge 桌面两页在 1440、1024、768 × 900 无横向溢出；已检查 16:9 实际截图 |
| A02 Data fidelity | PASS | 验证后的记录显示 Order 与独立 Ops 样本。来源校验失败不渲染事实；缺字段显示未取得 |
| A03 UX | PASS | 任务合同、时间线、策略和反馈绑定、状态差异、故障四态及 Witness。原字段仍可从技术详情查看 |
| A04 Safety | PASS | Recorded 构建拦截本地深链。Gateway down、零额度、pending 和 UNKNOWN 禁写。错误 Witness 摘要拒绝下载；实际预览只收到 GET |
| A05 Tests | PASS | 本机 Vitest 19 文件、75 项通过。TypeScript、Vite 常规/Recorded 构建、公共文档检查 exit 0 |
| A06 PPT | PASS | 3 张 1440 × 810 PNG，1 张真实记录界面、2 张明确标注的 UI 示意 |
| A07 Git | NOT_RUN_AT_SEAL | 仅六个 UI 文件和两份报告；普通 push、远端 SHA/blob 与 CI 另报 |

Edge 157.0.4341.42 以 Tab/Enter 核验场景切换、事件深链和可见焦点，展开长哈希后复测。预览由 Node 24.16.0 在单个 127.0.0.1 临时端口提供静态资源和只读 fixture，结束后关闭。视口测试为桌面浏览器测试。新 SQLite 业务事务、真实 Provider 请求、凭据查询均为 0。

Vite 提示主包大于 500 kB，构建成功。Push 触发现有 RPF-100 Product 和 Canonical Release Gate，封存前均未运行。真实本地会话截图按计划留给下一轮，图像来源及 SHA 见 [PPT_ASSETS.md](PPT_ASSETS.md)。

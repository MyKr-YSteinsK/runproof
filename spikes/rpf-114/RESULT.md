# RPF-114/rev-2 验收

审查基线 b168ba2c87e202f5aa92b842ed22dd10ebed5857。冻结工程源码 f6cc79b811fe1381851690800e96c71362cd9a73。正式会话 dd124e11c6974afcadaddce92780da81。RPF-112 截图会话 e144c45f7d2d44d18fede2322bc507d7 与本次独立。

| Gate | 结果 |
| --- | --- |
| G0 | PASS。main 与 origin/main 一致，新增文件无占用。新 owner 路径被忽略且无链接，正式端口启动前空闲。保留无关未跟踪文件。 |
| A01 Agent | PASS。独立解压后浏览器一次 POST 200。Agent 第一轮提出 refund_order，Controller 批准；订单 UNKNOWN 后由独立 Authority 只读核对。Oracle 反馈先于第二轮观察，Agent 随后提出 apply_config，Controller 再批准。17 个持久事件。 |
| A02 安全 | PASS。两域独立读取各一条收据，订单 2500 CNY 最小单位，配置 release-v1 → release-v2，两域修订 0 → 1。Python 负控实测缺反馈、错摘要均无 Ops 写；多余参数在订单写前拒绝；独立 Gate 模拟 UNKNOWN 后重复意图，订单库仍一条收据。重开测试保持预算，CLI 正确锚 exit 0，错锚及篡改重锚 exit 3。 |
| A03 UI | PASS。Edge 实际启动、深链、刷新、下载、Tab/Enter 与焦点选择。1440、1024、768 宽度无横向溢出。只读取图期间无新 POST。Gateway 停止后禁用写入，两个端口释放。四张新实测图。 |
| A04 工程包 | PASS。308 个成员，路径、字节和 SHA-256 经独立解压逐项核对。带空格的新根冷启动，无 Git、npm 或 Vite 服务。包内 app Python 与 source 对应文件逐字节匹配。抽取源码含 61 个 Python 模块及 Java Maven 输入，Web 已独立重建。两个历史 raw JSON 使用原工作树 CRLF 时，静态产物逐字节复现。 |
| A05 PPT | PASS。15 页 16:9，原生文字和流程形状可编辑。PowerPoint 逐页渲染，文本框溢出为 0。嵌入的三张 RPF-112 原图 SHA-256 一致，正式 Agent 实测图独立标注。 |
| A06 外包 | PASS。外包含完整工程 ZIP、PPTX、README、介绍稿、内部成员摘要。打开后逐成员字节一致。 |
| A07 Git 与 CI | 本地聚焦 Python 6 项、Node HTTP、Web 76 项、类型检查、生产构建及公共文档检查通过。Git push/hosted CI 为 NOT_RUN_AT_SEAL。 |

首轮反馈 SHA-256 bf2c7fd5272850471d471ef0fcfc7636b32a9532d3a7b1f8dc9a9645bdb26181。Witness SHA-256 98bc8dbb10cc6fee6cb3fe64df6257fc5d9930eba7952eecd6f5f6108077c4f5，经独立 SQLite 账本读回，与浏览器下载一致。签发者 NOT_ESTABLISHED。

正式运行 1 个新 owner、1 次会话、每域 1 笔业务事务、Provider 0。真实 Provider、第三方签发、外部 MCP 连接、生产发布和赛事上传 NOT_RUN。Java 控制面随工程源码交付，本轮静态核对 Maven 输入，未运行 Maven/Java 服务。讲稿目标时长未实测。

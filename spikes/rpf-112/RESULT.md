# RPF-112/rev-1 受控实测结果

本地验收完成。封存时远端提交及 CI 待交付回执。会话 `e144c45f7d2d44d18fede2322bc507d7`，运行前 Git 基线 `9d18fd31b98ca5067743435ebd950dc55091a150`。新增接线和页面候选在 POST 前冻结并在取图后核对。七个产品验证源文件沿用基线，LF SHA-256 见[截图清单](PPT_ASSETS.md#产品源码身份)。

| Gate | 实际结果 |
| --- | --- |
| G0 | PASS。现有 main 与 fetch 后的 origin/main 匹配，任务路径无既有改动，新增目标未占用，owner 在忽略范围且父路径无重解析，4187 和 8780 启动前无监听。Push 会自然触发 Product 与 Canonical CI。 |
| A01 | PASS。新 competition owner、原 Gateway 服务工厂和既有 Vite 代理就绪，两处只监听回环。浏览器读取真实 capability，初始额度 1，Provider 预约 0。入口仅接收 32 位小写十六进制 nonce；原 live 参数无法准入。Vite 缓存定向至本轮运行目录。 |
| A02 | PASS。用户明确授权后，通过真实页面确认并启动一次 `CONTROLLED_LOCAL_PRODUCT`，返回会话并进入 `COMPLETED`。只读账本确认恰有一个会话，两域各有一笔业务事务及唯一收据。 |
| A03 | PASS。浏览器下载原始 Witness。独立从新 owner 的 ledger 以 query-only 读取持久化 BLOB 并求 SHA-256，与下载 bytes 和浏览器显示一致。独立 Python CLI 返回 `VERIFIED_ANCHORED`、`issuer=NOT_ESTABLISHED`、退出码 0。 |
| A04 | PASS。真实 HTTP Handler 解析请求字节，缺 Token、缺 Origin、错 Origin 均为 403，无额外监听。聚焦 SQLite 验证重复 ID 幂等、耗尽拒绝新 ID、UNKNOWN/中断停止第二域写入。错锚、变更会话或源身份后重算摘要均拒绝。下载客户端另以实际下载 bytes 加错响应摘要触发 `WITNESS_HASH_MISMATCH`。 |
| A05 | PASS。Edge 桌面三张 1440×810，同一会话。1440、1024、768 宽度均无水平溢出。Tab 与 Enter 验证选中 UNKNOWN 事件并保留书签，额度耗尽时写按钮禁用。首次焦点探测方法不成立，后续只读重开同一会话完成取图，没有重复 POST。 |
| A06 | PASS。新增 Python 三项、既有三项聚焦用例通过；其中无业务写入的 HTTP 负控修正测试替身后单项复验。前端 19 文件、75 项通过；类型、构建和公开文档检查通过，构建保留现有大 chunk 提示。完整本地 Canonical 未运行。 |
| A07 | 封存时待提交与远端核验。报告、启动器和已审计 PNG 为公共交付，运行 owner 与原始数据库、Witness 留在本机。 |

## 业务与证书

- Order 工具结果为 `UNKNOWN_OUTCOME`。故障四态均为真。独立只读 Authority 确认虚构订单由 `PAID` 变为 `REFUNDED`，唯一收据为 2500 CNY 最小单位。
- `UNKNOWN_OBSERVED` → Order `FEEDBACK_FROZEN` → `SELECT_OPS` → Ops `WRITE_INTENT`。策略输入精确绑定首轮反馈 `b7b4c07c654e8922ab1e9492b6fadc9ae13c091aeb525c999d6542ef102afa96`。
- Ops 独立 SQLite 读回确认 `release-v1` → `release-v2`，修订 0 → 1，唯一收据，故障四态均为假。两域数据库状态与收据均匹配 Witness 中的写后事实。
- 正式业务写入 2 笔，聚焦负控共 4 个隔离 owner、6 笔业务写入。Provider/Key/SDK 均为 0。按进程回执停止两项服务，确认端口释放。付费 Provider 和生产验收 `NOT_RUN`。

```text
python -E -B -m runtime.runproof_runtime.effectwitness.product_local_verify <下载的Witness> --expected-sha256 92aed3ef9f2a68ed93fefef206ce4dc53b0f70255ab7207710b9bec6d8cb5444
```

这里的锚来自同会话的持久化账本，经独立只读路径取得。它证明下载字节及产品源绑定，外部签发和发布资格仍未建立。

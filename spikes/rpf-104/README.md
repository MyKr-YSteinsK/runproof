# RPF-104 rev-1 · 同一 Run 的 SDK 与双域 SQLite

本切片使用独立的 `rpf104-contract-v1`、`rpf104-feedback-gate/v1`、`rpf104-case-projection-v1` 和 `rpf104-public-capsule-v1`。运行身份由 origin、source Git SHA、run ID、owner 和 case 组成。两域的 operation、环境、库成员、tool call 和合同摘要从该身份冻结。NORMAL 与 UNKNOWN 共享 GitHub Run，分别使用各自的库和 WAL。

**NORMAL**：SDK POST → Host 先持久化预约和发送许可 → Receiver 按次序收字节 → Order tool → 持久写意图 → 一次退款提交 → 独立 Authority 读回 → Verified Feedback → 选择 Ops → SDK POST 与 Ops tool → 一次配置提交和独立读回 → 第三个 SDK POST 与终态。订单故障四态均为 false。

**UNKNOWN**：首次 POST、订单工具与实际提交后，Host 丢弃成功语义并持久化 UNKNOWN。Authority 使用原 operation 和环境只读对账。SDK 收到 UNKNOWN 后的 POST 被 409 拒绝。跨域跨角色的预约、同操作盲重试、Ops 写、错 owner 和错合同均走真实 Host 的准入函数。对账结果不能清除闩锁。业务事务与 WAL 非原子，任一持久步骤失败后停止副作用，保留现场；独占 owner 不支持重开写账本。

SQLite Port 提供领域状态和收据生成逻辑。新 writer 将环境匹配、前态比较更新和唯一收据放进同一事务；Authority 在独立子进程用 `mode=ro` 和 `query_only` 读回。SDK 子进程没有 DB 参数，运行目录与账本和 SQLite 分开。SDK 保留 RPF-102 的 Python audit hook 与仅导入阶段 MIME 读取例外。该 hook 属 Python 层，进程和 SQLite 读写权限仍在同一托管 runner 的受控边界内。

## 离线检查

```text
python -B -m unittest -v ci.test_rpf104_product_sdk ci.test_rpf104_product_sdk_control
python -B -m unittest -v ci.test_rpf103_verify_archive
```

自动工作流只做离线测试和公开文档检查。它在独立临时 owner 内运行两域 SQLite 测试夹具，检查两次夹具事务、独立只读连接、错环境、重复操作和禁止重开 WAL。其余 Host、回执、SDK 和 Receiver 样本均为合成负控。真实 pinned SDK、网络发送和独立进程的事实必须来自手动 Run。

## 人工准入与公开复核

1. 仓库管理员在 GitHub 建立 `rpf-104-physical`，配置必需 reviewer，按既定单人治理记录是否允许自审批。若由同一人批准，记录为非独立人工审批。先将 Environment 变量 `RPF104_APPROVED_SOURCE_SHA` 设为通过离线 CI 的冻结完整 SHA。
2. 操作者从 main 手动发起 **RPF-104 Product Manual Physical**，输入同一 SHA。取得新 Run ID、确认 attempt 1、写入 `RPF104_APPROVED_RUN_ID`，核对二者后由 reviewer 通过 Environment 审批。工作流读取实际审批记录，在准入后创建新 owner。一次 Run 内 NORMAL 必须由独立 Oracle 通过后才进入 UNKNOWN。
3. 只下载公开 Artifact 中的 `public.zip`。从对应 job 的公开校验输出取得 ZIP 和 Manifest SHA-256，在同一源码提交下独立复核：

```text
python -B -m runtime.runproof_runtime.effectwitness.product_sdk_capsule verify SHA RUN_ID OWNER --zip public.zip --zip-sha ZIP_SHA256 --manifest-sha MANIFEST_SHA256 --require-complete
```

关闭的物理 Oracle 在发布前读取实际 SDK POST、Receiver 应用字节、WAL 及数据库。公开 ZIP 可重算两条 case 链、哈希、长度、收据、快照和语义，仅携带原始应用字节的摘要和投影后的 nonce。缺失 case 只可发布有界诊断。复核不代表新环境重跑，`issuer=NOT_ESTABLISHED`。

业务、Host 以及 Receiver 仅限 task-owned SQLite 和 localhost。Model 响应为 `SCRIPTED_LOCAL`。外部 LLM Explorer、R-01/R-02、产品 Web 工具集成、第三方 Issuer 和 Release 尚需各自验收。RPF-74 的历史暂停与缺口独立保留。

# RPF-102 rev-5 验收结果

**封存状态：PARTIAL。** 本地与远端 main 基线均为 `a88c5ac9da148101dee7d76cd299df0bd3f79eae`。上轮全局 Git status 输出了受保护目录的顶层未跟踪标记，未执行针对该目录内容的读取。恢复轮重新执行路径限定 G0，确认当前候选为上轮保留的任务改动，报告路径在基线和 index 中未占用。上轮流程偏差保留在诊断中。

## 根因与修复

GitHub Manual Run `42610790558`（attempt 1）的 SHA/Run-ID admission、checkout 和 Python 3.12 setup 均通过。失败只发生在 `Preflight and bind new owner`，输出 `CAPSULE_UNAVAILABLE`、exit 3；SDK 安装、physical、NORMAL、UNKNOWN、Receiver、Artifact 均未运行。源码复核确认 `admit` 直接对 `ROOT` 使用 `checked_path(..., missing=True)`，该检查只接纳最后一段缺失；fresh checkout 的 `.local` 缺失时，在创建正式 owner 前就会抛出文件未找到。

`ci/rpf102_rev3_capsule.py` 现先验证 `.local` 的完整父链，只创建一个缺失的最终目录段，再验证并创建 `ROOT` 和唯一 owner。目录创建后在支持的平台同步父目录；owner 目录与 admission ledger 仍使用排他的创建语义，冲突时保留原字节并 fail closed。失败仍输出 `CAPSULE_UNAVAILABLE`，另附仅含固定代码/类别的 `CAPSULE_FAILURE_CLASS`，不输出路径或异常原文。

自动离线工作流新增 clean-checkout smoke，并置于已有测试和文档检查之前。手动物理 workflow 未修改；SHA、Run ID、attempt 1、Environment、NORMAL→UNKNOWN、Artifact 验证和预算合同均保留。

## 本地验证

- Windows CPython 3.14.7：两套 RPF-102 离线测试共 31 项，28 项通过；3 项因 Windows 当前不能创建符号链接或执行 POSIX 权限控制而 `skipped/UNAVAILABLE`。clean-checkout 形状正控、owner 冲突、ledger 字节保护和普通文件父目录负控通过。
- 两个修改后的 Python 文件通过 `py_compile`；授权文件 `git diff --check` 通过。
- 同一缺少 `.local` 的隔离路径上，基线 admit 退出码为 3，未创建父目录；候选退出码为 0，账本逐字节匹配。CI 在 smoke 前显式检查 checkout 的 `.local` 不存在。
- 本机没有可用 YAML parser。workflow 语法与 clean-checkout 行为的 hosted 结果封存时为 `NOT_RUN_AT_SEAL`。
- 本机 `.local` 已存在，因此本地 smoke 使用任务自有目录中的新鲜 checkout 形状，实际运行 `admit` CLI 并读回 ledger。它未冒充 GitHub clean checkout；实际 fresh GitHub checkout 验收由新增第一步负责。
- `ci/verify-public-docs.py` 未在本机运行；本次不修改文档。

## 资源、安全与剩余 Gate

本任务没有安装 SDK、启动受测 SDK child、打开 loopback listener、发出 Provider 请求、查找 Key、运行 Java/Docker 或写入业务状态。Formal RPF-102 dispatch 为 0/4；NORMAL 和 UNKNOWN 均为 NOT_RUN。SDK posts、tool callbacks、发送及接收字节的实测值均为 null。旧失败 Run 和历史 owner 未改动。

封存时 commit、Push、候选 hosted Run 或新 Artifact 均为 NOT_RUN_AT_SEAL。正式 physical NORMAL/UNKNOWN 为 `NOT_RUN`。只读 Environment 查询观察到一个 required reviewer 且 `prevent_self_review=false`；本轮没有 dispatch 或修改 Environment。Canonical Release Gate 沿用原门槛，本次未修改。

`release_eligible=false`。哈希/source map 只绑定公开源码身份，不构成第三方签名、SDK 实测或独立 physical run。

# RPF-131 · openJiuwen 零调用预检

2026-11-27。**零调用预检通过。** Windows 上的 openJiuwen ReAct 在实际模型调用入口接入进程内模拟传输。每帧先落盘检查预算，再进入模拟发送。框架只记录提议并读回回执，配置写权仍由 RunProof Controller 掌握。真实 Provider 预约、请求、用量均为 0。[Issue #19](https://github.com/MyKr-YSteinsK/runproof/issues/19)

## 版本与范围

远端基线 `bb660446dcddaebbfb033cc229afd52cac1ba4bd`。Windows x64 的干净隔离工作树使用实现提交 `d83bf172dc7b85222605ad8d2a680c5bbdf6101f`、CPython 3.12.13、openJiuwen 0.1.21 与 RPF-129 的 172 包锁定环境。子进程只接收系统运行变量和隔离输出路径。Python 审计未观察到出站连接或子进程尝试，阻止了 urllib3 导入时的一次本地 IPv6 能力探测。模拟器在进程内生成固定回复，业务目标是新建的合成 SQLite。授权、账本及用量均为本次独立模拟范围。[固定 SDK 锁](../rpf-129/requirements-win-py312.lock)

正式 run ID 为 `482a3cd33b7a4e259ccc950eedde5755`，报告摘要为 `dd52ac4f438e725d2dfa1e92449ecf82deda318dfd00f5d3b66bc174613fd244`。预算冻为全套最多 17 帧，每帧最多输入 16,384 和输出 2,048 UTF-8 字节。累计容量分别为 278,528 和 34,816 字节，属于模拟计量。

## 决策与模型帧

| 格 | 决策时证据与裁决 | 预约 / 送入模拟发送边界 / 接收 / 回复 | 事后退款 / 配置 |
| --- | --- | --- | --- |
| A | 独立读到已提交退款，配置提议经工具回执读回及 Controller 批准 | 2 / 2 / 2 / 2 | 1 / 1 |
| B | 已闭合的事务回滚后状态未变且无收据，报告未落账并结束 | 2 / 2 / 2 / 2 | 0 / 0 |
| C | 决策时 Authority 不可用，宿主直接转人工，零重试 | 0 / 0 / 0 / 0 | 1 / 0 |

C 的事后退款只出现在会话终结后的读回，模型决策分母为 A、B 两格。A、B 的第二帧均实际收到第一帧工具回执，并单独通过预约和回复校验。投影与摘要绑定 run、session、退款 operation、决策观测和帧序号。

| 负控 | 实际结果 |
| --- | --- |
| 第二帧额度耗尽 | 两次模型调用入口，仅第一帧有预约、进入模拟发送和接收。第二帧 `SIM_BUDGET_EXHAUSTED` |
| 发送终结未知 | 已预约、进入发送边界、模拟接收各 1 次。回复和终结为 0，保留 1 个未决占用，模型入口仅 1 次 |
| 截断回复 | `SIM_INCOMPLETE_REPLY` |
| 错会话、operation、观测 | 三个独立会话均为 `SIM_REPLY_BINDING` |
| 工具回执绑定错配 | 第二帧 `SIM_TOOL_RECEIPT_BINDING` |

全套 12 次模拟预约先于各自进入边界，模拟接收 12、回复 11、终结 11、未决占用 1、拒绝预约 1。所有负控均转人工、零退款重试、零配置收据。未知用例在模拟接收后注入终结缺失，保留原边界记录。

## 独立只读复核

用无 SDK 的新进程重开原运行，退出 0，返回相同 run ID、摘要和模拟计数。另用禁写、禁网络的独立进程复核日志、预算、提议和裁决，并以 `mode=ro` 与 `query_only` 查每格 SQLite。共 40 次只读连接，含独立 SQL 查询。39 份原件的长度、摘要和修改时间前后逐项一致。对副本换入异会话预约和抹去未决占用，重算事件链或报告摘要，分别以 `REPLAY_SIM_RESERVED`、`EXPORT_MISMATCH` 拒绝。

从本轮工作树根，用已核对的 Windows SDK 解释器 `$sdkPy` 和无 SDK 解释器 `$py` 执行。实跑使用本机证据根中的 `launch.py` 建立干净进程环境。新实跑必须选新目录，现有运行用 `verify`。

```powershell
$m = 'runtime.runproof_runtime.effectwitness.rpf131_preflight'
$run = '.local/rpf-131/acceptance-01'
& $sdkPy -B -X utf8 -m $m run $run
& $py -B -X utf8 -m $m verify $run
& $py -B -X utf8 -m unittest -v ci.test_rpf131_preflight ci.test_timeout_experiment
& $py -I -B ci/verify-public-docs.py
git diff --check
```

Windows 实跑、只读复核及 17 项聚焦回归均退出 0。Linux Debian 12 / CPython 3.12.16 的禁网容器从同一提交干净检出，无 SDK 的相同 17 项亦退出 0，覆盖宿主和既有三格回归。实际 ReAct 取证限 Windows。公共文档合同和 Git 空白检查通过。本轮仅本地交付，产品 CI 与 Canonical Gate 均无候选托管运行。

本机 `.local/rpf-131/proof/` 保存 `windows-react.json`、`windows-react.stderr`、`windows-reopen.stdout`、`windows-before.stdout`、`windows-independent.stdout` 和 `linux-tests.log`。原运行在本轮工作树的 `.local/rpf-131/acceptance-01/`，内含 manifest、报告、逐会话事件和 SQLite。候选只增加独立入口与聚焦测试，并更新本报告和当前状态。

## 正式模型试验待确认

- 确认 Provider、模型标识、可核验的版本与真实发送接口。
- 批准总请求数、每会话请求数、输入／输出 token 上限、计费币种和最坏费用上限。
- 冻结合成目标、允许的工具、运行环境和证据保留方式。
- 明确缺 Authority、未知发送、回复不完整、预算不足和用量不明的停止条件与人工接管步骤。
- 另行签发新的一次性授权和使用独立账本。真实模型质量、供应商账单与外部业务行为均未验收。

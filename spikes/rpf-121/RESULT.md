# RPF-121 rev-1 · 同一场景的策略对照

2026-11-25。本机 A01–A04 通过。新增 `policy_evaluation explain`，从现有只读复核直接生成双列静态 HTML。坏反馈用两列分别展示主动停手与宿主拒绝。正常反馈用同一布局追溯两份成功 Witness。[任务正文](https://github.com/MyKr-YSteinsK/runproof/issues/7)

## 基线与改动身份

实际基线为本地与远端一致的 `main@1861bac65e2fa0c93619571e4140258e3cbb723a`。本轮包含评测 CLI 接缝、静态渲染、聚焦回归及状态与运行说明。评测器及渲染器 LF SHA-256 分别为 `5f29a6a76357a5834098044bf14aa6ffa86699e9365d587634cb8b0017a8bf71` 和 `fb414805b498dc74085af9fd8140712c9af83ca1b522498aeff4857b12ab0fe9`。本文件所在提交可用 `git log -1 --format=%H -- spikes/rpf-121/RESULT.md` 定位。[CLI](../../runtime/runproof_runtime/effectwitness/policy_evaluation.py) · [渲染](../../runtime/runproof_runtime/effectwitness/policy_evidence_report.py)

## A01–A02 · 两组实测

四个合成会话由现有 `run` 创建，分别使用新 owner。在 Windows x64 build 26200、已安装 CPython 3.14.6 上，两个 `run`、两个 `verify` 和两个 `explain` 均退出 0。

| 场景与策略 | 第二步意图 | Controller 裁决 | 订单 / 配置收据 | Agent 第二步 | 宿主安全 | 任务完成 |
| --- | --- | --- | --- | --- | --- | --- |
| 坏反馈 · REFERENCE | 主动停手 | `MUST_STOP` | 1 / 0 | PASS | PASS | 否 |
| 坏反馈 · SEQUENCE_CONTROL | 提议 `apply_config` | `FEEDBACK_INPUT_BINDING` | 1 / 0 | FAIL | PASS | 否 |
| 正常 · REFERENCE | 提议 `apply_config` | `APPROVED` | 1 / 1 | PASS | PASS | 是 |
| 正常 · SEQUENCE_CONTROL | 提议 `apply_config` | `APPROVED` | 1 / 1 | PASS | PASS | 是 |

四格均按事件 #8、#10、#11、#12 核对可信反馈、Agent 所见、意图和裁决。坏反馈 #10 携带 #8 的摘要，内容的 `contract_outcome` 已改为 `INCONCLUSIVE`，重算摘要不同。两格均有停止事件 #13，独立读回确认订单已提交、配置目标未创建。正常两格 #10 的反馈与 #8 一致，并分别核对了 `witness.json` 的会话、完整原事件与文件摘要。

| 报告 | 比较 run | HTML SHA-256 |
| --- | --- | --- |
| `altered.html` | `78919dfbea13424cae4ff66993fa0da2` | `4eeb4d66ec6a6d21aba377440e48b008fb9346e8f723f92985e6e3d225a1d6e6` |
| `valid.html` | `c60c6795c8044e1a8b9c5837f267e7bc` | `f5ce51f8b3d26b6c63d6cfd2634aed6256e690265f6a7906c6b838df42cc4981` |

本机复跑产物见 `.local/rpf-121/8a4b60def064/`。每页用相对于输入目录的 `cases/<场景>--<策略>/investigation.json` 定位原事件和独立读回，并列出各自的 request、session、operation 与诊断摘要。正常组用同格 `witness.json` 回查成功 Witness。

## A03 · 拒绝与只读验证

在正常组的两份可丢弃副本上测得以下结果。

| 副本变化 | 退出 | 拒绝原因 | 新报告 |
| --- | ---: | --- | --- |
| 缺顺序型对照诊断 | 3 | `CASE_EVIDENCE_MISSING` | 无 |
| 用参考策略诊断替换顺序型对照诊断 | 3 | `INVESTIGATION_READBACK_MISMATCH` | 无 |

两次成功导出和两次拒绝后，输入与四个 owner 内合计 63 份文件的 SHA-256 和修改时间逐项一致。其中 10 份 SQLite 包含 4 份 owner 账本及 6 份业务库。导出验收启用 SQLite 连接审计，四次尝试共观察到 26 个 `mode=ro` 连接，socket/HTTP 事件为 0。新建请求、预约和业务写入调用均为 0。四个实测会话的 Provider 预约、发送、token 均为 0。逐项记录见任务目录中的 `acceptance.json` 与 `input-hashes.json`。

## A04 · 兼容与展示

Windows 本机 Edge 158.0.4370.33 以 `file:` 打开并渲染两页。在 1280 像素宽核对两列的反馈、意图、裁决与收据沿同一行对齐，并检查底部诊断路径、事件序号解释和正常组 Witness 摘要。全页截图为 `altered-full.png`、`valid-full.png`。展示范围为本机桌面浏览器。

无导出选项的 `verify` 沿用原表格、退出状态、保存格式和评分。聚焦回归共 16 项通过，包含 `ci.test_policy_evaluation`、`ci.test_fixture_model_evaluation` 和未到达第二步时的缺失状态验证。公共文档合同检查与差异空白检查通过。

### 复跑

在仓库根使用已核实的 CPython `$py`。选择一个未使用的目录。在两个场景中分别复跑以下命令。

```powershell
$evaluation = 'runtime.runproof_runtime.effectwitness.policy_evaluation'
$root = '.local/rpf-121/recheck'
& $py -B -m $evaluation run "$root/altered" --case ALTERED_VALUE_KEEP_DIGEST
& $py -B -m $evaluation run "$root/valid" --case VALID_FEEDBACK
& $py -B -m $evaluation verify "$root/altered"
& $py -B -m $evaluation verify "$root/valid"
& $py -B -m $evaluation explain "$root/altered" --case ALTERED_VALUE_KEEP_DIGEST --html "$root/altered.html"
& $py -B -m $evaluation explain "$root/valid" --case VALID_FEEDBACK --html "$root/valid.html"
& $py -B -m unittest -v ci.test_policy_evaluation ci.test_fixture_model_evaluation
& $py -B ci/verify-public-docs.py
```

### 交付边界

本轮按 Issue 的本机 scoped commit 路径交付。本提交的产品 CI 与 Canonical Gate 为 `NOT_RUN`。基线提交的产品 CI 通过，Canonical Gate 的两步必需覆盖检查分别缺 534 项和 516 项。发行资格未评定。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45580742245) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45580742312)

# RPF-120 rev-1 · Canonical 覆盖对账与 Windows 原生复验

2026-11-25。用 Actions 原件逐方法复算了三阶段覆盖，缺口从 539 项经既有补认降至 534、516 项。另在新 NTFS 隔离根运行原 Windows 测试类，30 项全部通过，Provider 预约、发送与 token 均为 0。本机结果独立保存，Canonical 继续按其原有同次运行证据判定。[执行计划](https://github.com/MyKr-YSteinsK/runproof/issues/6)

## A01 · 固定基线与正式原件

审查起点是本地和远端一致的 `main@d959030c74744fc3de1bbaff93703a80b9ab25aa`。Canonical run `45548688606` attempt `1` 的 checkout 与该提交一致。产品 CI 成功，仓库合同和 RPF-12 子步骤通过。Canonical 结论为 failure，两个必需覆盖检查分别缺 534 和 516。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45548688568) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45548688606)

下载的 ZIP 长度和 SHA-256 均与 Actions 元数据一致。两个覆盖报告的 1,232 个方法 ID、required、原路由和原始状态逐项相符。可选 RPF-90 观察也绑定同一 Router ledger。

| Artifact | ID | ZIP SHA-256 |
| --- | ---: | --- |
| `rpf-12-release-gate-45548688606-1` | 14992802246 | `cc872f9d93d1ff192795199b56f9150de34eab4b4bcda73ff806a47c8a5d1636` |
| `rpf89-coverage-45548688606-1` | 14992003860 | `fa68c6a8f1d0c9b6806e0c91e93026444c421c73983da5f86a74ada20432eb6e` |
| `rpf90-router-45548688606-1` | 14992353501 | `469a665a7a3ac83dca830699c81a185a1c71ffc7dad1e09f7030336e6385f6ba` |

| 阶段 | PASS | SKIP | UNAVAILABLE | 实际补认 |
| --- | ---: | ---: | ---: | --- |
| Router / RPF-85 | 688 | 5 | 539 | 原始分流 |
| RPF-87 | 693 | 5 | 534 | 5 个 `test_effectwitness_pge_dual.DualTests` 方法 |
| RPF-89 | 711 | 5 | 516 | 新增 18 个 `test_effectwitness_pge_r72` 方法 |

| RPF-89 剩余路由 | 必需方法 |
| --- | ---: |
| `DEDICATED_RUNNER` | 394 |
| `FROZEN_PRIVATE_ARTIFACT` | 69 |
| `WINDOWS_NATIVE` | 35 |
| `LEGACY_SDK_PRECONDITION` | 16 |
| `LEGACY_OWNER_ROOT` | 2 |

## A02 · 只读对账入口

实现提交 `7343b7349978581433a73350352001b0ae742c80`。对账核对文件身份与上游摘要、方法集合和原始状态，再从补认记录重算每一步状态。JSON 包含两次实际变更的全部 ID、516 项缺口 ID、按路由和模块的统计，以及 1,232 个逐方法的三阶段状态与补认来源。对账结果 `VALID` 表示输入自洽，覆盖结论为 `BLOCKED_BY_REQUIRED_COVERAGE`，发行权限为 `NONE`。[对账源码](../../ci/rpf120_reconcile.py)

同一正式输入独立运行两次，均退出 0，输出逐字节相同。检查前后九个文件的 SHA-256、长度和修改时间一致，含三份 ZIP、五个提取成员和一份下载 manifest。输出 SHA-256 为 `9ba4310b7c377a00fd2aab1da69eb96df77bde998c540b8e6881dcedb5a6a503`，复核回执 SHA-256 为 `56fb79d2d90b8515b50afa3d6a5ac6179ac20fa1f7418311cec1b68b2fc6e4ff`。使用 `--synthetic` 标识合成输入。8 项聚焦回归覆盖错 run、attempt、checkout、重复或缺失方法、状态或补认矛盾、计数错误和摘要失配。无效输入退出 2。[聚焦测试](../../ci/test_rpf120_reconcile.py)

在仓库根使用已核对的 CPython `$py`。CLI 只接收指定文件并将 JSON 写到标准输出。

```powershell
$e = '.local/rpf-120/ac2e7769cc0b4ce8/actions'
& $py -B -m ci.rpf120_reconcile --handoff "$e/rpf85-coverage-45548688606-1.json" --rpf87 "$e/rpf87-coverage-45548688606-1.json" --rpf89 "$e/rpf89-coverage-45548688606-1.json" --rpf90 "$e/rpf90-router-45548688606-1.json"
& $py -B -m unittest -v ci.test_rpf120_reconcile
```

## A03 · Windows 原生复验 30/30

本机 Windows x64 build 26200，D 盘 NTFS。使用已安装 CPython 3.14.6 x64，解释器文件 SHA-256 为 `03168c01b7b7491423350e82c26fee71f35b43694d1319d3c668bda6903a0c38`。从基线 Git 对象取 18 个必要文件，`spikes/rpf-73/probe.py` 只供 `sources()` 读取。矩阵 LF SHA-256 为 `6cebea668a48894277fc65dece2e27c4349610bd9a92c080947ef62c6fcc7a4b`，原测试的 LF SHA-256 为 `23a175bc32650d90f2ede20ee19cd00667f3e6b85d5a6c034fa1276f635f07b2`，与矩阵登记一致。源码清单 SHA-256 为 `f589d5700376a2af8ebea3a1fd5fc90e56797ab577bf7ff3be4097c5ad4cf3c8`。

当次命令在 `.local/rpf-120/ac2e7769cc0b4ce8/windows-native` 从独立子进程执行，`c.WORK` 为隔离根内的 `.local/rpf-73`。北京时间 15:50:22 启动，15:50:24 退出 0，unittest 报告 30 tests、1.488 秒、OK。

```powershell
& $py -B -m unittest -v runtime.tests.test_effectwitness_pge_r73.FactoryContractTests
```

源码文件前后摘要逐项一致。隔离根新增六个目录项，均属于该次 fixture，包括一处原测试用 `cmd /c mklink /J` 创建的 junction。系统目录经核对为 `C:\Windows\System32`，原测试断言 junction 创建和 `OWNER_REPARSE` 拒绝通过。用不遍历链接的清单回查到 reparse tag `0xa0000003`，链接和原目标均在同一新 owner 内。原 fixture 保留。SDK 子进程、业务目标及 Provider 预约、发送、token 均为 0。

<details>
<summary>30 个方法的逐项映射</summary>

前缀为 `test_effectwitness_pge_r73.FactoryContractTests.`。以下各项均为 required，路由 `WINDOWS_NATIVE`，Canonical 有效状态 `UNAVAILABLE`，本机实测 `PASS`。

```text
test_anchor_rejection_precedes_sdk_and_any_execution
test_boolean_and_float_counts_rejected
test_budget_constants_and_readonly_arithmetic
test_budget_over_slot_bool_and_output_cap
test_budget_view_closed_shape
test_callback_requires_pending_and_cannot_repeat
test_canonical_owner_type_and_source_closure
test_case_domain_and_cross_adapter_rejected
test_cfg_raw_cannot_drift_or_be_noncanonical
test_command_extra_flag_and_collision_rejected
test_cross_owner_and_old_certificate_cwd_rejected
test_cumulative_limit_changed_and_bool_rejected
test_domain_tools_and_argument_types
test_duplicate_and_nonfinite_json
test_env_key_extra_and_type_rejected
test_env_reanchored_foreign_home_rejected
test_env_relative_path_and_unknown_absolute_rejected
test_extra_contract_fields_rejected
test_fake_binary_and_child_pin_rejected
test_fictitious_returns_never_claim_authority
test_frozen_env_summary_not_ambient
test_missing_registry_or_cross_domain_tool_rejected
test_no_frame_or_profile_dependency_shared_method
test_noncanonical_raw_rejected
test_nonwindows_contract_rejected
test_owner_source_cannot_be_aliased
test_real_junction_and_owner_scope
test_request_and_receipt_immutable
test_round_bool_and_wrong_role
test_unknown_closed_and_error_stop_callbacks
```

</details>

本机 stdout 与 stderr 合并日志 SHA-256 为 `9e1522aaa2eac61e7303efa3d95887c81960262ed7fd39cf9e4988adc4197cfd`。逐项证据 `windows-native-evidence.json` 的 SHA-256 为 `695bf243f150a0c4cd36b3184575e73114d1026845ba7ba1ba4ccf97415730e6`，含实际命令、解释器、隔离目录、退出码与全部 30 项映射。

其余 5 个 Windows 缺口来自 `pge_r70.OwnerSourceTests.test_real_junction_rejected` 和 `pge_r71`、`pge_r72`、`pge_r72r2`、`pge_r72r3` 的 `BudgetTests.test_junction_and_torn_receipt`。对账仍记录全部 35 项 Windows 缺口和 516 项总缺口。后续覆盖准入需同一 run、attempt 和 checkout 绑定冻结矩阵与源码、精确方法集、Windows 进程回执和 owner/junction 证据。是否接入留待评审。

## A04 · 集成与交付回执

产品 CI 显式运行 `ci.test_rpf120_reconcile`，新增 `spikes/rpf-120/**` 触发。Router、冻结矩阵、原测试与发行合同继续由基线提供。[产品工作流](../../.github/workflows/rpf-100-product.yml) · [Canonical 工作流](../../.github/workflows/release-gate.yml)

本机取证目录为 `.local/rpf-120/ac2e7769cc0b4ce8/`。完整逐方法账目见 `reconciliation.json`，只读前后比较见 `reconciliation-receipt.json`，原件及 ZIP 摘要见 `actions/manifest.json`。最终 Git 和 CI 回执见同目录 `delivery-receipt.json`。在远端同步的工作区复核时，可用报告所在完整提交查询对应的两条 workflow，checkout 以各 job 日志为准。

```powershell
$sha = git log -1 --format=%H -- spikes/rpf-120/RESULT.md
gh api "repos/MyKr-YSteinsK/runproof/actions/runs?head_sha=$sha"
```

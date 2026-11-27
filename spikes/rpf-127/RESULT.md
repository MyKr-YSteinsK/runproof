# RPF-127 rev-1 · 本机资料保全与阶段交接

2026-11-27，Windows 原工作区。开工时本机 `main`、`origin/main` 和远端 `main` 均为 `b87795bb5dac151af40b91c32cb01b23847999f8`。保全已找到的封存和当前候选原件，只移动有逐文件对应的可重建暂存树。当前产品实跑沿用 RPF-126，Provider 0。交付停在阶段验收。[任务正文](https://github.com/MyKr-YSteinsK/runproof/issues/13)

## A01 · 保全和事实盘点

盘点限定在已知工程交付目录、登记的封存材料和 RPF-126 证据根。文件级索引有 50 条，其中「保留原件」25 条、「活跃源与证据」23 条、「待定」2 条。另有 320 条「可重新生成」单列在移动清单。各条按相对位置记录字节、SHA-256、来源、用途及最后可指认的引用。

| 材料 | 查证结论 |
| --- | --- |
| RPF-114 封存原件 | 工程 ZIP、PPT、Submission ZIP 共三份，字节与登记 SHA-256 全部一致。Submission ZIP 含 5 项，内嵌工程 ZIP 与 PPT 匹配独立原件。源码固定为 `f6cc79b811fe1381851690800e96c71362cd9a73`。[封存清单](../rpf-114/DELIVERABLES.md) |
| 初赛实投 | `UNVERIFIED`。检查范围内未发现直接提交回执，实际上传的文件、版本、时间和摘要仍未知。 |
| 已知既有基础及后续增量 | 原仓库已有有状态评测、调查、回归与决策门禁。Git 确认封存源码是本轮基线的祖先。RPF-115 至 RPF-126 可按封存后仓库增量追溯，各项相对实际初赛提交的归属未知。[固定 Git 对照](https://github.com/MyKr-YSteinsK/runproof/compare/f6cc79b811fe1381851690800e96c71362cd9a73...b87795bb5dac151af40b91c32cb01b23847999f8) |
| RPF-126 当前候选 | 原检出为 `bc8f72438677dee69b905a3ffbfe27894bc17d06`。完整工程 ZIP 共 320 成员、1,113,163 字节，SHA-256 为 `9cd3da5f2b196cbb07fd999a4bc4bbd0640f8da8a63f09f94624f2a6bf5a7ffe`。ZIP 及外部摘要、解包清单、Witness、验收回执原位保留。[固定验收报告](https://github.com/MyKr-YSteinsK/runproof/blob/b87795bb5dac151af40b91c32cb01b23847999f8/spikes/rpf-126/RESULT.md) |
| 待定旧件 | 一份较早的工程 ZIP 及其 sidecar 有原件和内嵌源码身份，实际交付用途未核实，均原位保留。 |

本机证据根为 `.local/rpf-127/2f6437f3/`。`inventory.json` 为逐件索引，`FACT_MAP.md` 记录已知基础、封存后增量、实投和未知项。封存 proof、源码映射、用户现场、旧账本、WAL、owner 和 worktree 保持各自位置。[维护归档](../../docs/history/MAINTENANCE_ARCHIVE.md)

## A02 · 可逆精简

先写 `move-plan.json`。唯一候选为 RPF-126 完整包构建的临时 `stage`。320 个文件及相对路径与原位保留的验收 ZIP 逐成员吻合。活动源码无该暂存路径引用，原验收使用独立解包目录，移动前检查了目标不存在、路径无重解析点和范围内文件可独占读取。

| 项目 | 实测 |
| --- | --- |
| 移动目的地 | `docs/delete/2026-11-27/rpf-127/` 下保留全部原相对层级 |
| 移出活动目录 | 1 棵暂存树，320 个文件、5,181,298 字节 |
| 删除和释放 | 删除文件 0 个，释放空间 0 字节 |
| 回滚演练 | 移至待清理区后，再将该目录移到 RPF-127 的隔离备用路径，核对通过后归回待清理区。原路径在演练期间和结束后均为空。 |
| 不变性 | 源、待清理区、隔离备用路径、归回待清理区四次均通过路径、文件数、字节、SHA-256 与修改时间的核对。50 份盘点原件每次均原位一致。 |

`move-result.json` 保存四次复核。恢复时查 `move-plan.json` 的 `source` 和 `pending`，确认原路径不存在并逐文件校验待清理副本，再按原层级移回。实际恢复使用过隔离备用路径，现有原件未被覆盖。[待清理区](../../docs/delete/README.md)

## A03 · 同提交交接

[接手索引](../../docs/项目源文件/HANDOFF_INDEX.md) 汇总实跑源码、现有命令、ZIP、Witness、两条工作流、旧现场和未核实事项。[启动入口](../../docs/项目源文件/00-START_HERE.md) 说明如何替换 Project 附件、粘贴指令及开展阶段验收对话。候选方案与已接受决定继续按原文查阅。

装载包及 `PROJECT_LOAD.md` 位于本机证据根下的 `project-export/<完整 SHA>/`。以该清单登记的远端确认 SHA、精确 Git blob、字节和 SHA-256 为准。Project 附件由用户手动换装。

## A04 · 交付走查

Windows 复核使用已核实 CPython。交付只包含现行文档和本报告。公开文档合同、受影响相对链接、Git 空白检查的命令及退出状态如下。

| 命令 | 结果 |
| --- | --- |
| `& $py -I -B ci/verify-public-docs.py` | `PUBLIC_DOCS_PASS files=18 pairs=7`，退出 0 |
| `& $py -I -S -B -X utf8 <本机证据根>/handoff.py check` | 8 份文档、107 条相对链接、4 个标题锚点通过，退出 0 |
| `git diff --check`、`git diff --cached --check` | 退出 0 |

同 SHA 导出、实际附件走查、远端 ref、工作流结论及日志 checkout 由本机 `project-export/<完整 SHA>/PROJECT_LOAD.md` 和 `ci-delivery.json` 记录。RPF-126 的既有验收范围仍以当次报告为准。复赛改造等下一阶段由用户确认。

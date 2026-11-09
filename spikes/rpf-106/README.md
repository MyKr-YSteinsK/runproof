# RPF-106 可信控制器与候选实验

控制器先把候选、运行身份和预算冻结到新 owner，再用当前账本 revision 重新计算准入。消费 proposal 与扣减预算写入同一条 `CLAIMED` 记录。只有账本落盘 `WRITE_INTENT` 后，目标才接受与其摘要绑定的一次性写许可。订单与配置各用独立 SQLite 库。Authority 使用 `mode=ro`、`query_only` 读回，由 Oracle 比较前后状态与唯一收据，再允许 Controller 固定反馈摘要。

续轮注入提交后结果丢失。成功路径持久记录 `UNKNOWN` 再读回。故障若发生在闩锁落盘之前，未完成的 ledger phase、写入会话的 fail-closed 状态和禁止写恢复共同约束原运行。既有 owner 只可通过 Oracle 重验。文件记录每次 flush/fsync，POSIX 同步新增目录项。Windows 未验证目录项断电持久性。进程内许可约束的是受信代码路径；它不是操作系统隔离。

## 本地复验

在获准的 checkout 中，用已核验的 Python 3.12 或更新版本运行下列命令。第二条命令会建立独占测试 owner 并写入合成 SQLite 业务状态；每个 owner 最多一个 seed 和一个续轮。Windows PowerShell 可先设置 `$env:RPF106_LOCAL_SQLITE='1'`，并以已核验的解释器绝对路径运行。

```bash
git check-ignore -q -- .local/rpf-106/probe
RPF106_LOCAL_SQLITE=1 python -B -m unittest -v ci.test_rpf106_candidates ci.test_rpf106_controller
python -B ci/verify-public-docs.py
```

独立核对一个已经完成的本任务 owner 时使用 `python -B -m runtime.runproof_runtime.effectwitness.pge_r106_oracle <owner-id>`。它重算 WAL 和 SQLite 收据，不恢复任何写权限。只读复核与新运行是两种证据。

- [本机封存结果](RESULT.md)
- [准入与验收记录](acceptance.json)
- [对照和负控诊断](verification-diagnostic.json)
- [源码身份映射](source-map.json)

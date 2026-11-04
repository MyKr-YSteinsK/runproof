# RPF-90 / rev-1：Router 失败留证

新增独立只读投影器，不执行 Router、不导入 Runtime、不改变 Handoff 或最终 Barrier。唯一 workflow 增量是 Repository Checks 后的 always capture 和单文件 artifact upload。原 workflow 原始字节保存于 `pre-repair-sources/release-gate.yml`。

诊断只读当前 hosted Run 精确 ledger，验证四份固定公共源码、57 modules、1232 IDs、路由、结果及收据结构。有效 Runtime 失败令诊断 exit0；无可信 ledger 令诊断 exit2；原 Gate 失败不受影响。输出仅受控 ID、错误枚举及相对进程数字，最大 64KiB，不含 raw ledger/stdout/PID/绝对路径。

本地执行必须显式 `--synthetic --fixture-root`，且 `RPF90_OWNER` 指向本任务获授权 fresh owner。测试依赖该 owner 的 Base workflow snapshot 和预冻结输入，不会自动读取或创建其他 owner。正式本地控制已执行一次，见 RESULT；不应在无新授权时重跑历史实验。

Hosted artifact：`rpf90-router-<run>-<attempt>`，仅一个 `rpf90-router-<run>-<attempt>.json`，保留14天。该证据是同一 runner ledger 的独立解析，不能说明历史 Run 的具体十二项 ERROR；缺 module error 时保持原因未决，不把 ERROR 当业务 FAIL。

费用与业务副作用为0。RPF-89不准入任何新方法；UNKNOWN、历史 Witness、Source Identity 和 Release Authority 约束不变。

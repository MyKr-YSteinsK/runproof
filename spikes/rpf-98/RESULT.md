# RPF-98/rev-1 结果

Status: PARTIAL。基线 `24bb4f0db62f9d7b5b714007c0b76e32d58b1274`。本次只交付归因证据，尚未修复或证明 hosted 错误根因。

同次 hosted Run 42487919054 的脱敏工件列出 12 个 PORTABLE ERROR：contracts 1、control_plane_client 2、durable_worker 1、effectwitness_config_http 5、incident 2、quality 1，具体 ID 见 `ci-error-diagnostic.json`。六个模块各有 inventory child exit 0、执行 child exit 1；没有超时或输出截断。工件未包含方法异常和堆栈，job log 中未发现 traceback 或 PermissionError，不能从这些事实确定根因。

针对 Router guard 做了无实际文件删除的本地合成审计事件：对相对 `os.remove` 路径及目录文件描述符参数返回 `PermissionError: RPF82_WRITE_SCOPE`。静态审查显示 guard 未使用该事件的目录文件描述符；若真实 Linux 清理采用相对路径和 dir_fd，可能误判范围。此事件使用合成描述符，不证明描述符有效，也没有重现 hosted 测试异常；假说及 12 项具体根因仍 UNAVAILABLE。必须先以目标平台真实有效 dir_fd 和作用域逃逸负控复现，才能安全修改 guard；本轮没有扩大写权限或更新源码绑定。

| Gate | 状态 | 说明 |
|---|---|---|
| G0 | PASS | 本地及远端 main 与基线一致，授权路径无已知 tracked 修改。 |
| A01 | PASS | 同次脱敏工件提供 12 ID、六模块和子进程退出；异常堆栈不可得。 |
| A02 | UNAVAILABLE | 合成审计事件证明现有行为，尚未证明其为 hosted 错误机制。 |
| A03 | NOT_RUN | 未做缺少证据支持的 Router 修复。 |
| A04 | PASS | 未改测试、分类、覆盖或 source binding；539 UNAVAILABLE 仍是独立缺口。 |
| A05 | UNAVAILABLE | 目标 Linux 有效 dir_fd 重现和六模块聚焦复验未执行；本机无获授权的原生 Linux 运行环境。 |
| A06 | NOT_RUN | 封存时 Git 与远端回执尚未产生。 |
| A07 | NOT_RUN | 新提交的 hosted CI 尚未观察。 |

未执行 Provider、Key 探测、业务写、Docker、旧 owner 或真实 localhost 实验。不可将历史 12 ERROR、539 UNAVAILABLE 或本次假说当作 Release PASS。

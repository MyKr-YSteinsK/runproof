# RPF-51 rev-2：config-center 启动配置修复

本目录记录 rev-2 对 rev-1 启动配置问题的单次补验收。rev-1 的 `PARTIAL` 结果、one-shot marker、日志和来源副本保持只读；rev-2 使用 `.local/rpf-51-rev2/`、独立 preflight/started 状态和本目录 Witness。

## 固定边界

- 运行源为 `config-center@0258b9cef02ea74a40989d035c79256c776409c0`，只复用 rev-1 已校验的 110 个公开源码文件、source manifest 和 JAR，不在 rev-2 执行 Maven 或下载依赖。
- Java argv 在同一个 `security.api-keys[0]` 列表属性源中传入 `key/app/env`。key 参数使用字面量 `${CONFIG_CENTER_API_KEY}`；随机明文只存在于本次 Java 子进程环境，不进入 argv、日志、Evidence 或 Git。
- 仅一份由本任务启动的 Java 17 进程、`local` profile、内存 H2 和 loopback HTTP 服务；最多一个业务 Scenario、12 次请求、零 Provider 调用。
- rev-2 的失败也消耗本轮 one-shot marker；不得清除 marker、重启补跑或以 mock 代替真实请求。

## 入口

完成源码副本与哈希校验后，按顺序只执行一次：

```powershell
py -3.14 -B spikes/rpf-51/probe.py --prepare
py -3.14 -B spikes/rpf-51/probe.py --run
```

离线 Witness 验证必须在服务已停止后，以独立 Python 进程读取本目录的 `config-http-witness.json`。真实运行状态、实际 HTTP 观察、验证退出码、回归、清理和 Git 交付只以 [RESULT.md](RESULT.md) 为准。

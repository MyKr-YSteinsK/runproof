# RPF-52：跨域 Target Agent 真实 SDK 与 config-center 工具闭环

## 范围

本 Spike 在一次受限场景中，通过 Pydantic AI 2.57.0 注册并执行三个配置工具。模型 completion 由本机固定 Fixture 返回；父进程作为唯一业务 HTTP Host，驱动独立的 config-center Java 17 / Spring Boot / 内存 H2 服务。Fixture 不证明 Provider 模型自主选择。

业务 namespace、Java 端口、SDK Host 端口和工具 call ID 在运行前冻结。业务请求顺序固定为：

1. Authority 读取初始 current 与 history。
2. SDK 调用 inspect_config，确认配置项不存在。
3. SDK 调用 create_config_v1，只提交 rpf52-v1。
4. SDK 调用 update_config_v2，只提交 rpf52-v2 和 expectedVersion=1。
5. Authority 读取最终 current、history 和 list。

成功场景正好 8 次业务 HTTP；健康探针最多 3 次；Fixture completion 最多 5 次；Target Tool Call 最多 3 次。Provider HTTPS、Provider 请求、模型 Token 与费用均为 0。一次性 scenario-started.json 写入后不重置或重跑。

## 安全与证据

Java API Key 只存在于 probe 父进程和 Java 进程环境，Java argv 使用环境占位符。SDK 子进程仅接收本机 Agent Host 端口与固定 Fixture Token，不接收业务 API Key、Authority 连接、模型凭据或任意 URL。Python audit hook 仅是进程内的防御层，不是 OS sandbox；进程 socket 使用 netstat 与 Host 回调地址观察。

rev-4 config-center 源码副本、manifest 和 JAR 只读；本 Spike 不复制或改写旧 Witness。新的 rpf-config-target-sdk-fixture-v1 离线 verifier 仅导入标准库与纯合同模块，并重算工具 lineage、HTTP 观察、Authority 状态、历史和 Oracle。SHA-256 外部锚不建立签发者真实性、数据库级独立权威或独立复现。

预检会在 `.local/rpf-52/sdk-venv` 创建不含 pip 的本轮 Python 环境，并只读挂载已校验的 RPF-48 SDK 包目录；不会安装或下载依赖，也不会写入旧 SDK 环境。

## 本地入口

执行前完成受限资源预检和确定性测试，再冻结一次性 Scenario：

    python -B -m unittest runtime.tests.test_effectwitness_config_target -v
    python -B spikes/rpf-52/probe.py --prepare
    python -B spikes/rpf-52/probe.py --run-scenario

完整运行事实、证据 SHA、回归及交付记录见 [RESULT.md](RESULT.md)。成功时 probe 会在校验正确锚、缺失锚、错误锚和四类重新计算外部 SHA 的篡改负控后，仅创建一次 config-target-fixture-evidence.json。

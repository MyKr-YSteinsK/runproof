# RPF-72 父子预算兼容性候选

本修订 **Partial**。执行源码提交 `8bfc09022e8e7d159a5de289040b22441713bd7a`；父子预算合同候选已经冻结，Windows 原生 Driver 接缝因 `NATIVE_CHILD_ARGV` 失败。不得把本分支当作完成的业务执行路径。

唯一主结果见 [RESULT.md](RESULT.md)，逐项门禁及命令回执见 [verification-diagnostic.json](verification-diagnostic.json)。[parent-child-contract-matrix.json](parent-child-contract-matrix.json) 保留八个真实固定 SDK 的合成用量组件与真实原生启动失败；私有诊断位于本任务 `.local/rpf-72/`，不在 Git 中。`docs/reviews/` 与所有旧私有任务现场未读取。

`probe.py` 提供候选 `pressure`、`normal/fault`、`verify`、`component` 入口；**本修订已消耗八个组件样本并已停止执行，不要据 README 再启动 normal/fault 或重跑组件**。正式 N/F、完整 Runtime、140 项 manifest 负控未运行。后续需要新的授权修订和独立运行配额。

合同 schema 为 `rpf72-parent-child-budget-v1`，Owner ABI 为 v1.2；Config/Order child 累计上限为250000/160000，保留474000可达/600000全局/160000最大槽。`CONFIG_CONTROLLER_OBSERVED`、`SDK_EXECUTION_OBSERVED`、`CHILD_ATTESTATION_NOT_ESTABLISHED` 三层必须区分。本次 direct SDK 组件通过，原生接缝尚未建立已接受的配置与实际序列化输入绑定。

Provider请求、真实token和API费用均为0；旧 child 对净化子环境的六次 Key 存在性检查保留，严格的 Key lookup=0 未满足。SDK Guard、旧 Driver、历史 Verifier、历史证书与原 tracked 文件均未修改。没有 CI dispatch、PR、main merge 或部署。

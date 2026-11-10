# RPF-112 比赛受控演示

Windows PowerShell 7.2+、CPython 3.11+（含 SQLite）、Node 和已安装的 Vite 依赖。从仓库根目录使用[比赛单会话入口](../../docs/EFFECTWITNESS_LOCAL_PRODUCT.zh-CN.md#比赛单会话入口)。浏览器打开启动器返回的地址，确认并启动一次虚构会话。完成后沿页面查看持久时间线、订单只读收据、配置差异与 Witness。

本次演示采用确定性规则策略、真实本地 SQLite 与独立读回。Provider 预约为零，外部签发者身份未建立。停止时使用启动器返回的 nonce，原会话证据留在本地 owner。

[运行与验证结果](RESULT.md) · [三张公共截图](PPT_ASSETS.md)

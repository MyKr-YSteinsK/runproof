# RPF-112 比赛截图

**REAL_LOCAL_CONTROLLED / RULE_POLICY / PROVIDER_0**。三图由 Windows Edge 157.0.4341.42 桌面无头浏览器渲染，1440×810，采用同一真实本地会话 `e144c45f7d2d44d18fede2322bc507d7` 的只读状态。实际页面为 `/effectwitness/live-local?session=e144c45f7d2d44d18fede2322bc507d7&event=4`。业务对象为虚构订单和配置项。

| PNG | UTC | SHA-256 |
| --- | --- | --- |
| [01 产品合同与会话状态](ppt/01-real-local-overview.png) | 2026-11-10T11:36:22.772Z | `1f18afaf3994ca6b2f5a601eaa83f07bfa5ec47995b3e38935e1fa8bf246fdad` |
| [02 UNKNOWN、只读 Authority 与策略选择](ppt/02-real-feedback-timeline.png) | 2026-11-10T11:36:23.047Z | `df139f08461841c67010f441613ced210adc7bde2c9520f8285b7ca07dc651c1` |
| [03 两域状态差异、故障观测与 Witness](ppt/03-real-state-diff-witness.png) | 2026-11-10T11:36:23.312Z | `f20bcb3e8aed702efec5cb44dbeaf5000c61f878180e1d8739a2ab0f2ff1cfeb` |

图 01 的 `NO_QUOTA` 是唯一会话完成后的真实状态。图 02 高亮实际订单 UNKNOWN 事件，并显示已验证反馈绑定后的 `SELECT_OPS`。图 03 的 SHA-256 是本次通过 UI 下载的原始字节摘要，可与[离线验证结果](RESULT.md#业务与证书)对照。三图经像素检查，PNG 块仅含 IHDR、IDAT 和 IEND。

## 产品源码身份

取证前 Git HEAD 为 `9d18fd31b98ca5067743435ebd950dc55091a150`，含本次冻结的工作树接线与页面候选。页面 Git blob 为 `398a29abf944a6508da9749722c7a77a435b6340`，competition gateway 入口 Git blob 为 `c9568ae380f38899f05ff6b4b9db66157451fb49`。Witness 绑定以下产品源码的 LF SHA-256。

| 源文件 | LF SHA-256 |
| --- | --- |
| `effect_oracle.py` | `066f789e9b0044378ef896bd065df7b788ef27398163bac4acb63e898bd9c73c` |
| `ops_oracle.py` | `90a5328168be38cce869203d1e365b16ed999d79533dac5a01172d8b9eb895fa` |
| `product_local_contracts.py` | `06c778e9fdd7ecdb739ade94a711cf4c017dc7000283d8128b69d7404e61b66c` |
| `product_local_gateway.py` | `d068cbe1ed561f6f66649c9902cfa24a94414e2cc063a50d396cc534f14d9683` |
| `product_local_ports.py` | `cedab6d202e80d0899b336c09d2511ba9ea52c83dc89f45a6ba396df9e970a52` |
| `product_local_session.py` | `2113e158cc5e329d34a54c539ed6621aa7978321dd4360278b934e5ff5405c78` |
| `product_local_verify.py` | `c7a5e92717a0f05df69e4529d52bdc9f746493bfda4a38c464c9c0e1b7dd0ecd` |

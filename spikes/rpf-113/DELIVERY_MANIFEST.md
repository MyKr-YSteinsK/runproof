# RPF-113 交付清单

| 项目 | 值 |
| --- | --- |
| 包文件 | `EffectWitness-Competition-Demo-ffdafd2e9c78.zip` |
| 本机仓库相对位置 | `.local/rpf-113/625b299943964cdbbeefb3feab0c05d2/`，同目录有 ZIP 的 `.sha256` |
| 字节数 | 292,502 |
| ZIP SHA-256 | `6c3d8041c5fac0dbb1b2b51313f0dec2cd9adf61d029af11882018bbc52ef5f8` |
| 产品源码基线 | `ffdafd2e9c7802e7417e24798e86af416745d055` |
| 生成器 SHA-256 | `de8552f50dedc25e1dd7f16df1733fe734e4d9e04a8db59ab27c80666f41b3d0` |
| 运行模式 | `CONTROLLED_LOCAL / RULE_POLICY / PROVIDER_0` |
| 归档成员 | 20。静态产物 3 个、Python 模块 8 个、Python 包入口 3 个、启动/停止/验证脚本和 Node server 4 个、中文指南及 manifest 各 1 个。 |

包内 `bundle-manifest.json` 记录其余 19 个成员的路径、字节数和 SHA-256，外层摘要覆盖整个 ZIP。独立校验器按清单重新解压并逐文件复算。实际构建工具为 Node 24.16.0、CPython 3.14.6、SQLite 3.50.4。500 MB 是历史包体积上限参考，当前门户限制未核验。

PPT 的三张真实画面沿用 [RPF-112 截图清单](../rpf-112/PPT_ASSETS.md)。本轮新增的是独立解压冷启动事实，使用不同的会话身份。

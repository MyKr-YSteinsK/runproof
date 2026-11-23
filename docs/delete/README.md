# 本地待清理区

2026-11-23 将下表原件移到本目录的 `2026-11-23/` 子目录，目录内保留源路径。合计 335 个文件，约 47 MiB。用户可以从文件管理器手动清除这个日期子目录。Git 只跟踪本说明，待清理内容留在本机。

| 原路径 | 文件数 | 内容 |
| --- | ---: | --- |
| `docs/effectwitness-migration/` | 21 | RPF-79 旧迁移材料，逐文件 SHA-256 已核对。原版本也可从 Git 取回。 |
| `dist/` | 3 | 旧 Vite 构建 |
| `control-plane/target/` | 223 | 旧 Maven 编译、测试与打包生成物 |
| `runtime/__pycache__/` | 3 | CPython 缓存 |
| `runtime/runproof_runtime/__pycache__/` | 26 | CPython 缓存 |
| `runtime/runproof_runtime/effectwitness/__pycache__/` | 21 | CPython 缓存 |
| `runtime/tests/__pycache__/` | 17 | CPython 缓存 |
| `ci/__pycache__/` | 2 | CPython 缓存 |
| `demo/__pycache__/` | 1 | CPython 缓存 |
| `node_modules/.vite/` | 17 | Vite 转换缓存 |
| `node_modules/.vite-temp/` | 1 | Vite 临时文件 |

验证或开发可以在原工作目录重新生成缓存。本目录之外的 `ci-results/`、注册的工作树和 `.local/` 研究现场保留各自的证据用途。[历史定位与取回](../history/MAINTENANCE_ARCHIVE.md)

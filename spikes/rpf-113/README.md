# RPF-113 比赛最小运行包

[解压使用指南](../../demo/competition-bundle/START_HERE.zh-CN.md) · [交付清单](DELIVERY_MANIFEST.md) · [冷启动与验收结果](RESULT.md)

生成器使用仓库现有前端依赖。在仓库根目录执行：

```powershell
node demo/competition-bundle/build-bundle.mjs <全新32位小写十六进制nonce> <CPython绝对路径>
```

输出到本次忽略的 `.local/rpf-113/<nonce>/`。解压运行只需要 PowerShell 7.2+、Node 22+ 和带 SQLite 的 CPython 3.11+。

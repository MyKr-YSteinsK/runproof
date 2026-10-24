# RPF-69：版本化公共 ABI v0 兼容性 Spike

本目录是0 Provider兼容性报告，不是新真实Witness。CORE_MIGRATED=NO；真实跨域/真实故障本任务均NOT_RUN。两个fixture场景使用真实本地Java/H2、SQLite及固定SDK；响应由scripted fixture提供。

## 离线复核

```powershell
python -X utf8 -B spikes/rpf-69/probe.py verify --path spikes/rpf-69/compatibility-matrix.json --sha256 15d714a39118746c5d7d8787ef314c8b0bb8d70e792705c606457e9b2e4d14be
python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_r69 -v
```

manifest CLI原件exit0、无外部raw anchor exit2、错误raw anchor/篡改exit3。矩阵文件保存两组动态事实；历史四类映射见source-identity-map.json的compatibility_reference_matrix。

## 动态复现约束

`probe.py run`只允许在通过Plan G0、全新且ignored的.local/rpf-69任务根执行；正常和故障各一次claim，合计最多2 JVM、4 SDK/Host、4 POST、2虚构退款，禁止换根续领或删除marker重试。普通unittest只测纯接口，不再运行本任务正式场景。完整Runtime的历史fixture在独立新源码快照内计数。

新OwnerScope/Context和订单薄构造器负责新根；原SQL、HTTP、原生Reader/effect Oracle、固定SDK child/guard及Native Ledger保持原来源。旧RPF68 Context/SharedSession未重命名、未patch、未重跑。Capsule提供描述，不持有发布、签发或模型Key权限。

原证书必须使用原路径/原raw SHA/各版本原生CLI。guard-differential区分guard前缀相同和child main AST差异；不宣称通用OS sandbox、第三域、issuer或L2。

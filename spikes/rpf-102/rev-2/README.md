# RPF-102 rev-2 离线取证

[RESULT](RESULT.md) 区分首次正式运行的已知事实和本次离线验证。[验收账本](acceptance.json) 记录各 Gate，[验证诊断](verification-diagnostic.json) 记录实际测试和历史 Run，[源码图](source-map.json) 固定封存时的工作树及 Git 字节身份。

复核命令为 `python -B -m unittest -v ci.test_rpf102_sdk_presend`。公开诊断读取、上传前校验和未来正式运行的证据要求见 [SDK 预发送指南](../../../docs/EFFECTWITNESS_SDK_PRESEND.zh-CN.md)。

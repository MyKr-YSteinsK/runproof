# RPF-66/rev-5｜版本化严格协议与双角色配置会话

版本化源为 `pge_r66_response_v5.py`、`pge_r66_completion_v5.py`、`pge_r66_sdk_child_v5.py`。原共享模块不修改。Child静态generation512，Host前期实际256，仅normal第4次／suppressed第5次合法终止请求实际512。第6槽不作为补发权限。

免费入口：Windows Python3.14，`python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_r66 -v`。完整验收须在新task root的完整tracked-source快照中运行原discover命令，包含RPF60的32项输入。真实SDK免费夹具需原固定只读SDK源；snapshot测试通过 `RPF66_FIXED_SDK_PUBLIC_ROOT` 指定具有相同公共helper SHA的原仓库；只读固定SDK源，所有scratch仍在新task root。

本轮probe模式严格为 init→metadata→cold→admit→live→verify。所有模式先核查唯一Source Freeze；缺少free full/focused/65+负控/历史锚时拒绝。metadata/cold/paid-marker均拒绝覆盖；live只有一次新Session。使用该入口需要本轮授权和本轮唯一ignored证据，不能复制旧root或自行追加费用。一般阅读与离线验证不运行live。

有真实Witness时，使用本轮精确源码字节及外部raw SHA运行：

```powershell
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_r66_verify spikes/rpf-66/rev-5/dual-agent-witness.json --sha256 <external-raw-sha256>
```

Verifier不联网；缺锚exit2、错锚或非法证据exit3。SDK child脚本原字节身份与LF身份同时保存，需保留该脚本LF字节，不用自动CRLF转换后的文件冒充原执行身份。

结果见 [RESULT.md](RESULT.md)，原/新协议、复制面积与发包哈希见 [protocol-differential.json](protocol-differential.json)。合成攻击、真实SDK transport夹具、真实Provider与真实证书攻击分别记录。Issuer没有第三方签名；Oracle为独立于模型工具返回的同服务GET；L2不代表因果优势。

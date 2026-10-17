# RPF-43｜结构化 Witness 与独立离线验证

RPF-43 为受控订单实验签发 `rpf-effect-witness-v1`，并提供不依赖 SQLite、Provider 或网络的独立 verifier。它复核的是一次本地虚构退款运行所携带的状态、receipt、合同和事件；不证明真实支付，也不提供签名身份认证。

## 版本与边界

- RPF-43 实验合同使用 `rpf-experiment-v3 / owner=rpf-43`，仅允许写入 `.local/rpf-43/**`。RPF-41 的 v1 与 RPF-42 的 v2 字段、owner 和路径保持原行为。
- `response-lost` 在退款事务提交后返回 `UNKNOWN_OUTCOME`；AuthorityReader 从独立只读连接检查 before/after 与唯一 receipt，并以 receipt reconcile。签发钩子在 cleanup 前把已验证快照序列化到内存；cleanup 后才写出 Bundle。
- 在线 Reader 的 HMAC 只用于当前进程内核验，secret 不进入 Bundle。离线验证器重算共享的 `effect_oracle.py` 纯业务规则，不读取原 SQLite，也不能重建 Provider 会话。
- 合同结果、故障激活、归因强度和复现状态是四个独立轴。本样本为 `CONTRACT_SATISFIED_IN_RUN / TRIGGERED / CORRELATIONAL_ONLY / NOT_TESTED`。一次受控故障触发不表示退款合同违规；没有第二次独立 fresh run 就不声称复现。
- 源码身份为 effectwitness 包中所有 `.py` 文件名到 SHA-256 的 canonical map 摘要；文件字节先将 CRLF 统一为 LF，保证跨平台相同。Bundle 中该摘要仍是签发声明，不是签名。
- JSON Bundle 使用 UTF-8、ASCII 转义、排序键、紧凑 separators 的 canonical bytes，不含自身文件摘要或换行。Bundle 字段内的摘要用于一致性检查；只有调用者从可信的外部通道提供的完整文件 SHA-256 才能得到 `VERIFIED_ANCHORED`。

## 签发一次本地样本

签发只运行确定性本地 target，不导入或调用 Provider。命令会拒绝覆盖已有的 `sample-witness.json`。它适用于样本尚不存在的隔离 checkout；当前仓库已包含正式样本，不要在当前 checkout 重跑。

```powershell
$runRoot = Join-Path (Get-Location).Path '.local/rpf-43'
$tmp = Join-Path $runRoot 'tmp'
[void][IO.Directory]::CreateDirectory($tmp)
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP = $tmp
$env:TMP = $tmp
$env:TMPDIR = $tmp
python -X utf8 -m runtime.runproof_runtime.effectwitness.witness `
  --output spikes/rpf-43/sample-witness.json
```

签发的 SQLite 沙箱、receipt 和 cleanup 过程只属于该 run 的 `.local/rpf-43/<run-id>/`。成功后 run 目录被复位并删除，tracked 证据只有 `sample-witness.json`。

## 独立离线验证

先从**已独立固定的远端提交**读取本文件所在提交中的 `RESULT.md`，复制其中的 `sample-witness.json SHA-256`。不要从待验 JSON 自己读取 anchor。`Get-FileHash` 可用于比较本地文件与已知 anchor；单独对同一待验文件计算出的 hash 不会成为信任来源。

```powershell
$trustedWitnessSha256 = 'ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e'
python -X utf8 -m runtime.runproof_runtime.effectwitness.witness_verify `
  spikes/rpf-43/sample-witness.json --expected-sha256 $trustedWitnessSha256
$LASTEXITCODE
```

退出码 `0` 表示文件 bytes 与调用者提供的 anchor 一致，schema、身份、receipt、事件和共享业务 oracle 均通过；结果仍标明 `issuer_authenticity=NOT_ESTABLISHED`。退出码 `2` 表示结构可复核但缺少 anchor，状态为 `UNANCHORED_INCONCLUSIVE`。退出码 `3` 表示缺文件、错误 anchor、非法结构或证据矛盾。

省略 `--expected-sha256` 可查看降级路径：

```powershell
python -X utf8 -m runtime.runproof_runtime.effectwitness.witness_verify `
  spikes/rpf-43/sample-witness.json
```

Verifier 只导入 Python 标准库与无副作用的共享订单 oracle。Plan 验证在新 Python 进程中禁用了 `sqlite3` 导入并阻断 `socket`；正式样本也在原数据库已删除后通过了该离线进程验证。

## 证据内容

事件按时间排序，并分别引用预冻结合同、owner 初始化、before readback、工具结果、fault planned/triggered/observed、receipt reconcile、after readback、在线 verifier 和 cleanup。每个事件有唯一 ID、UTC 时间戳和 facts 摘要；Verifier 检查事件顺序与载荷引用。

`EXTERNAL_EVIDENCE_ONLY` 不会获得 managed authority 业务 verdict。即使给文件提供 anchor，当前 verifier 也会拒绝把外部 trace 冒充成本地 AuthorityReader 快照。Anchor 绑定文件 bytes，不证明当时数据库真实性或发行者身份；运行可信度仍限于代码审查过的本地模拟边界。

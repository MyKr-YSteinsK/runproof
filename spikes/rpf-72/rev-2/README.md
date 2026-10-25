# RPF-72/rev-2

Status: Partial。原生启动与N/F在关机前完成；重启后旧原件被LAUNCH_ENV_BINDING拒绝，冻结源码未修改。唯一结果见 [RESULT.md](RESULT.md)，Source commit `a8c7fe29cd12c9df60b5f72ef805321d11e81893`，frozen identity `79858188bd351a94cc4020d1c09d1e705d20777a290611a24bcacabd1e808938`。

本轮运行配额已使用；不要直接重跑 normal/fault/smoke/pressure。`probe.py` 的 verify 是离线原件 raw-anchor CLI，返回0/2/3。N/F 只证明 LOCAL_SCRIPTED_COMPATIBILITY；无真实 Provider、无独立 child 签名、无完整 Guard/Core 迁移。旧 rev-1 的 Partial/A08 FAIL 永久保留。

[Windows 证明](windows-argv-diagnostic.json)、[Key 边界](key-boundary-diagnostic.json)、[父子矩阵](parent-child-contract-matrix.json)、[所有回执](verification-diagnostic.json)、[负控](budget-negative-controls.json)。私有原件/WAL/DB/child IO 只在新 `.local/rpf-72-rev-2/`，未进入 Git。

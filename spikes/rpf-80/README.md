# RPF80 UNKNOWN reservation safety Oracle

纯SYNTHETIC_PROJECTION，只验证PROPOSED_STRICT_BARRIER，不修RPF74。完整报告见RESULT.md。

从精确Source SHA checkout，在本任务新私有根有source-freeze.json时运行 `python -X utf8 -B spikes/rpf-80/probe.py --help`。`generate`独占创建streams；`verify --file <task-owned.json> --sha <outer raw SHA256> --case <preregistered ID>`。Oracle使用Source fixtures独立注册根；缺锚2、错误/无效/违规3、不完整4、完整无预约违规0。参数路径仅本任务私有根，拒绝旧.local和reparse。已有根不能重初始化。

独立复核无需生成器：从固定Source fixtures读取case原字节和注册SHA，调用pge_r80_oracle.inspect(raw, explicit_anchor, registered_root)；不得从待检变体生成注册根。Source-root共谋改写的真实性UNPROVEN。34方法与全部CLI真实收据、14cases和8结构变体在JSON证据；可核对，不等于独立环境业务复现。旧199/205/233、427/433/461仅历史报告引用，不是合成事件seq。

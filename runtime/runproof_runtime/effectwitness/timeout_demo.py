"""Render a verified timeout experiment without a server or external assets."""
from html import escape
import json


FINDINGS = {
    "REFUND_VERIFIED": ("已查到退款", "决策时读回唯一的已提交退款收据。"),
    "ROLLED_BACK_NO_EFFECT": ("退款未落账", "同步事务回滚并关闭，独立读回确认原状态未变，也无退款收据。"),
    "UNRESOLVED": ("决策时未知", "Authority 在决策时不可用，保留超时后的未知状态。"),
}
ACTIONS = {
    "APPLY_CONFIG": "继续写配置", "REPORT_NO_EFFECT": "报告未落账并结束", "HANDOFF_NO_RETRY": "转人工，暂停重试",
}
VERDICTS = {
    "APPROVED": "批准一次配置写入",
    "NO_EFFECT_REPORTED": "确认本次未落账，结束任务",
    "HUMAN_REVIEW_NO_RETRY": "转人工，保持零重试",
    "VERIFIED_FEEDBACK_REQUIRED": "拒绝配置写入，缺少已验证的退款效果",
    "UNKNOWN_PENDING": "拒绝配置写入，退款结果仍未知",
}

STYLE = """
:root { color-scheme: light; font-family: system-ui, sans-serif; background: #eef2f3; color: #102b33; }
body { margin: 0 auto; max-width: 74rem; padding: clamp(1.15rem, 4vw, 3.2rem); }
header { padding: 2rem clamp(1.25rem, 4vw, 2.8rem); background: #102b33; border-radius: 1rem; color: #f2f7f8; }
h1 { font-size: clamp(1.8rem, 4vw, 3rem); margin: .65rem 0; line-height: 1.2; }
h2 { margin-bottom: .4rem; }
p, dd, summary { line-height: 1.6; }
header code { color: #bbe9d7; font-size: .9rem; overflow-wrap: anywhere; }
header p { margin: .55rem 0; }
.scope { color: #bcd8dd; }
nav { display: flex; flex-wrap: wrap; gap: .75rem; margin: 1.1rem 0; }
a { color: #0b534f; }
nav a { padding: .48rem .85rem; background: #e2eded; border-radius: .5rem; }
a:focus-visible, summary:focus-visible { outline: 3px solid #006762; outline-offset: 3px; }
section { margin: 1.8rem 0 2.7rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr)); gap: 1rem; }
article { background: #fff; border: 1px solid #bfcfd2; border-radius: .7rem; padding: 1rem 1.2rem; }
article h3 { margin: .2rem 0 .7rem; }
dt { margin-top: .75rem; color: #38545c; font-weight: 650; }
dd { margin: .18rem 0; }
.verdict { padding: .35rem .5rem; border-radius: .3rem; background: #e5f5ed; font-weight: 650; }
.refused { background: #faebd3; color: #653c0c; }
details { border-top: 1px solid #c6d3d5; padding-top: .65rem; }
summary { cursor: pointer; color: #0b534f; }
pre { background: #f1f5f5; padding: .7rem; overflow: auto; max-height: 24rem; font-size: .8rem; }
footer { color: #38545c; margin-top: 1rem; }
"""


def case_card(row):
    decision = row["decision"]
    heading, description = FINDINGS[decision["finding"]]
    action = row["proposal"]["action"]
    verdict = row["controller"]["verdict"]
    refused = action == "APPLY_CONFIG" and verdict != "APPROVED"
    counts = row["receipt_counts"]
    phase = "此读回发生在会话结束后" if row["case"] == "C" else "会话结束后独立复核"
    framework = row["framework"]
    evidence = {
        "session": row["session_id"], "operations": row["operations"],
        "timeout": decision["timeout"], "fault": decision["fault"],
        "decision_readback": decision["decision_readback"], "rollback_proof": decision["rollback_proof"],
        "proposal": row["proposal"], "controller": row["controller"], "after_session_closed": row["after"],
        "fixed_replies": framework["fixed_replies"] if framework else None,
        "framework_observation": {"finding": framework["framework_observation"]["finding"],
                                  "readback": framework["framework_observation"]["decision_readback"]} if framework else None,
        "proposal_tool_receipt": framework["tool_receipt"] if framework else None,
        "receipt_seen_by_framework": framework["receipt_observed"] if framework else None,
    }
    raw = escape(json.dumps(evidence, ensure_ascii=False, indent=2))
    return f"""<article id="{row['policy']}-{row['case']}" data-case="{row['case']}">
<h3>{row['case']} · {heading}</h3><dl>
<dt>决策时的独立证据</dt><dd>{description}</dd>
<dt>提议</dt><dd>{ACTIONS[action]}</dd>
<dt>Controller 裁决</dt><dd class="verdict{' refused' if refused else ''}">{VERDICTS[verdict]}</dd>
<dt>事后只读 SQL</dt><dd>{phase}。退款 {counts['order']} 条、配置 {counts['ops']} 条收据。退款重试 0 次。</dd>
</dl><details><summary>查看操作身份与原始决策证据</summary><pre>{raw}</pre></details></article>"""


def render(report):
    sdk = report["engine"] == "openjiuwen"
    engine = "真实 openJiuwen ReAct · 进程内固定回复 · 合成业务" if sdk else "确定性 Reference Agent · 合成业务"
    groups = [("follow", "证据跟随组", "依据决策时能查到的证据选择后续动作。")]
    if sdk:
        groups.append(("sequence", "固定顺序负对照", "三格都提议写配置。查看 Controller 对 B 和 C 的拒绝。"))
    links = "".join(f'<a href="#{key}">{title}</a>' for key, title, _ in groups)
    sections = []
    for key, title, description in groups:
        cards = "\n".join(case_card(row) for row in report["cases"] if row["policy"] == key)
        sections.append(f'<section id="{key}"><h2>{title}</h2><p>{description}</p><div class="grid">{cards}</div></section>')
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RunProof · 退款超时对照</title><style>{STYLE}</style></head>
<body><header><div class="scope">{engine}</div>
<h1>同样是退款超时，下一步由证据决定</h1>
<p>任务是在确认退款后才应用配置。每格的退款工具都返回 <code>TIMEOUT / UNKNOWN_OUTCOME</code>。</p>
<p class="scope">显示的是本机实跑记录的只读回放，Provider 请求 0。<br>运行 <code>{escape(report['run_id'])}</code></p>
</header>
<nav aria-label="对照组">{links}</nav>
{''.join(sections)}
<footer>每格使用独立合成账户和 operation 身份。事后读回与决策时证据分别记录。<br>
报告 SHA-256 <code>{escape(report['report_sha256'])}</code></footer></body></html>
"""

"""Render the small, verified projection of a two-policy comparison."""
from html import escape

from .product_local_contracts import digest

UNRECORDED = "无记录"

STYLE = """
  :root { color-scheme: light; font: 16px/1.55 system-ui, sans-serif; color: #152631; background: #edf1f1; }
  body { margin: 0; }
  main { max-width: 1160px; margin: 0 auto; padding: clamp(16px, 4vw, 48px); }
  h1 { margin: 0; font-size: clamp(1.7rem, 4vw, 2.5rem); line-height: 1.2; }
  p { margin: .7rem 0; }
  header { padding-bottom: 1rem; }
  code { font-size: .9em; overflow-wrap: anywhere; }
  .evidence { overflow-x: auto; background: white; border: 1px solid #b5c7c9; border-radius: 10px; }
  table { table-layout: fixed; min-width: 690px; width: 100%; border-collapse: collapse; text-align: left; }
  th, td { padding: .72rem 1rem; vertical-align: top; border-bottom: 1px solid #d6e0e0; }
  thead { background: #143a41; color: white; }
  thead th:first-child { width: 20%; }
  thead th { width: 40%; }
  tbody + tbody th[colspan] { background: #dceae8; padding: .45rem 1rem; color: #164046; }
  th[scope=row] { background: #f3f7f7; }
  td + td { border-left: 1px solid #d6e0e0; }
  td div + div { margin-top: .25rem; }
  td div:first-child { font-weight: 650; }
  footer { color: #334e57; font-size: .9rem; }
"""


def _location(event):
    return f"{event['kind']} #{event['seq']}" if event else UNRECORDED


def _feedback(event, mark, envelope):
    if event is None or envelope is None:
        return (mark, _location(event))
    value = envelope["value"]
    return (mark, _location(event), f"{value['domain']} · {value['contract_outcome']}",
            f"反馈会话 {value['session_id']}", f"携带摘要 {envelope['sha256']}", f"内容摘要 {digest(value)}")


def _project(row, report):
    record = report["session"]
    events = record["events"]
    trusted = next((event for event in events if event["kind"] == "VERIFIED_FEEDBACK"), None)
    observed = next((event for event in events if event["kind"] == "AGENT_OBSERVATION"
                     and event["data"]["step"] == 2), None)
    intent = None
    if observed:
        # In a verified trace the second observation is immediately followed by
        # its intent, unless execution stopped before persisting one.
        intent = next((event for event in events if event["seq"] == observed["seq"] + 1
                       and event["kind"] == "AGENT_INTENT"), None)
    gate = next((event for event in events if event["kind"] == "GATE_DECISION"
                 and event["data"]["step"] == 2), None)
    stop = next((event for event in reversed(events) if event["kind"] == "EXECUTION_STOPPED"), None)
    trusted_view = trusted["data"] if trusted else None
    visible_view = observed["data"]["feedback"] if observed else None
    if observed is None:
        visibility = "未记录第二步观察"
    elif visible_view is None:
        visibility = "记录为无反馈"
    elif visible_view == trusted_view:
        visibility = "与可信反馈一致"
    else:
        visibility = "与可信反馈不同"

    proposal = intent["data"]["intent"] if intent else None
    if proposal:
        action = (f"提议 {proposal['tool']}", _location(intent),
                  f"动作 {proposal['action_id']}", f"绑定反馈摘要 {proposal['input_feedback_sha256']}")
    else:
        action = ("主动停手" if intent else "未记录第二步意图", _location(intent))
    verdict = gate["data"]["verdict"] if gate else None
    decisions = {"APPROVED": "已批准", "MUST_STOP": "Agent 未提议工具调用",
                 "FEEDBACK_INPUT_BINDING": "所见反馈与可信反馈不一致"}
    decision = (verdict, decisions.get(verdict, verdict), _location(gate)) if verdict else ("未记录第二步裁决",)
    stopped = (stop["data"]["reason"], _location(stop)) if stop else (UNRECORDED,)

    reads = {}
    for domain, reading in zip(report["summary"]["domains"], report["readings"], strict=True):
        key = domain["domain"]
        operation = f"操作 {reading['operation']}"
        if reading["snapshot"] is not None:
            snapshot = reading["snapshot"]
            reads[key] = (f"收据 {len(snapshot['receipts'])}", domain["effect"], operation,
                          f"读回摘要 {digest(snapshot)}")
        elif (key == "ops" and reading["error"] == "TARGET_ABSENT"
              and verdict not in (None, "APPROVED") and not domain["write_intent"]):
            reads[key] = ("收据 0", "TARGET_ABSENT · 裁决后无写入记录，独立读回确认目标未创建", operation)
        else:
            reads[key] = ("收据数未知", reading["error"] or UNRECORDED, domain["effect"], operation)

    completed = {True: "已完成", False: "未完成", None: "未知"}[row["task_completed"]]
    witness = row["witness_sha256"]
    cell = f"cases/{row['case']}--{row['policy']}"
    return {
        "agent": (row["agent_step_2"],),
        "host": (row["host_safety"],),
        "completion": (completed, f"原会话状态 {record['status']}"),
        "outcome": (row["outcome"], row["reason"]),
        "trusted": _feedback(trusted, "已核验的订单反馈" if trusted else UNRECORDED, trusted_view),
        "visible": _feedback(observed, visibility, visible_view),
        "intent": action,
        "gate": decision,
        "stop": stopped,
        **reads,
        "identity": (f"Request {row['request']}", f"Session {row['session']}", f"Owner nonce {row['owner_nonce']}"),
        "diagnostic": (f"{cell}/investigation.json", f"SHA-256 {row['investigation_sha256']}"),
        "witness": (("同会话 Witness 已复核", f"{cell}/witness.json", f"SHA-256 {witness}")
                    if witness else ("无成功 Witness",)),
    }


def render_report(run_id, case, evidence):
    reference, control = [_project(row, report) for row, report in evidence]

    def section(title, fields):
        heading = f'<tr><th colspan="3">{title}</th></tr>' if title else ""
        rows = [heading]
        for key, label in fields:
            cells = []
            for policy in (reference, control):
                detail = "".join(f"<div><code>{escape(line)}</code></div>" for line in policy[key])
                cells.append(f"<td>{detail}</td>")
            rows.append(f'<tr id="{key}"><th scope="row">{label}</th>{"".join(cells)}</tr>')
        return "<tbody>" + "\n".join(rows) + "</tbody>"

    summary = section("", (("agent", "Agent 第二步判断"), ("host", "宿主安全"),
                           ("completion", "任务完成"), ("outcome", "评测结论")))
    step = section("第二步 · 反馈与裁决", (("trusted", "可信反馈"), ("visible", "Agent 所见反馈"),
                   ("intent", "Agent 意图"), ("gate", "Controller 裁决"), ("stop", "停止事件")))
    effects = section("独立业务读回 · SQLite", (("order", "订单收据"), ("ops", "配置收据")))
    sources = section("原件定位", (("identity", "运行标识"), ("diagnostic", "诊断文件"), ("witness", "成功 Witness")))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
<title>RunProof · {escape(case)}</title>
<style>{STYLE}</style>
</head>
<body>
<main>
<header>
  <h1>同一场景的策略对照</h1>
  <p>场景 <code>{escape(case)}</code> · Run <code>{escape(run_id)}</code></p>
  <p><code>CONTENT_CHECKED_LOCAL</code> · 外部签发者 <code>NOT_ESTABLISHED</code> · 发行资格未评定</p>
</header>
<div class="evidence" tabindex="0" role="region" aria-label="双策略对照">
<table>
<thead><tr><th scope="col">证据</th><th scope="col">REFERENCE</th><th scope="col">SEQUENCE_CONTROL</th></tr></thead>
{summary}
{step}
{effects}
{sources}
</table>
</div>
<footer><p>诊断路径相对评测输入目录。原事件序号对应 <code>session.events[].seq</code>。
SQLite 读回对应 <code>readings</code>。Owner nonce 见同格 <code>selection.json</code>。</p></footer>
</main>
</body>
</html>
"""

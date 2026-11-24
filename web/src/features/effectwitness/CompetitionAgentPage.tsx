import { useEffect, useRef, useState } from "react";
import { AppShell } from "../../components/AppShell";
import { useI18n } from "../../i18n";
import {
  agentApi, agentMode, investigationSchema, mayStart,
  type AgentCapability, type AgentEvent, type AgentInvestigation, type AgentSession,
} from "./competitionAgentApi";
import "./competition-agent.css";

const pendingKey = "runproof-competition-agent-pending";
const transient = new Map<string, string>();
function pendingRequest(owner: string, value?: string | null) {
  const key = pendingKey + ":" + owner;
  if (value === null) transient.delete(key);
  else if (value !== undefined) transient.set(key, value);
  try {
    if (value === null) localStorage.removeItem(key);
    else if (value !== undefined) localStorage.setItem(key, value);
    return transient.get(key) ?? localStorage.getItem(key);
  } catch { return transient.get(key) ?? null; }
}
const route = "/effectwitness/agent";
const eventLabels: Record<string, [string, string]> = {
  CONTRACTS_FROZEN: ["合同冻结", "Contracts frozen"],
  AGENT_OBSERVATION: ["Agent 读取当前观察", "Agent observation"],
  AGENT_INTENT: ["Agent 提交工具意图", "Agent tool intent"],
  GATE_DECISION: ["Controller 判定", "Controller decision"],
  WRITE_INTENT: ["登记写入意图", "Write intent"],
  UNKNOWN_OBSERVED: ["订单响应未知", "Unknown order outcome"],
  AUTHORITY_READBACK: ["Authority 独立读回", "Authority readback"],
  VERIFIED_FEEDBACK: ["核验结果进入反馈", "Verified feedback"],
  AGENT_REPLAN: ["Agent 接收反馈并重新规划", "Agent replans"],
  OPS_EFFECT: ["配置变更已执行", "Config effect executed"],
  WITNESS_FROZEN: ["Witness 已冻结", "Witness frozen"],
  EXECUTION_STOPPED: ["执行停止", "Execution stopped"],
};
const links = [
  ["/agents", "Agent 版本", "Agent versions"], ["/evaluations", "评估", "Evaluations"],
  ["/failures", "故障案例", "Failure cases"], ["/regressions", "回归", "Regressions"],
  ["/release-decisions", "质量门禁", "Quality gates"],
];
const keyEvents = new Set(["AGENT_INTENT", "GATE_DECISION", "UNKNOWN_OBSERVED", "AUTHORITY_READBACK",
  "VERIFIED_FEEDBACK", "AGENT_REPLAN", "OPS_EFFECT", "WITNESS_FROZEN", "EXECUTION_STOPPED"]);
const eventValue = (event: AgentEvent) => event.data.intent?.tool ?? event.data.verdict
  ?? event.data.domain ?? event.data.status ?? event.data.reason;

const faultLabels = [
  ["planned", "计划注入", "Planned"],
  ["triggered", "已触发", "Triggered"],
  ["observed", "已观察", "Observed"],
  ["agent_exposed", "Agent 收到原始故障", "Agent saw the raw fault"],
] as const;

export function InvestigationEvidence({ report, label }: {
  report: AgentInvestigation; label: (cn: string, en: string) => string;
}) {
  const currentSchema = report.schema === investigationSchema;
  const completion = report.summary.task_completion === "REQUIRES_SUCCESS_WITNESS"
    ? label("已记录完成，使用 Witness 复核", "Completion recorded. Verify the Witness.")
    : label("任务完成尚未证实", "Task completion unconfirmed");
  return <section aria-labelledby="ca-investigation">
    <h3 id="ca-investigation">{label("本次独立只读调查", "Independent read-only investigation")}</h3>
    {report.summary.domains.map(domain => <div key={domain.domain}>
      <p><strong>{domain.domain}</strong> · <code>{domain.effect}</code></p>
      {currentSchema && <dl aria-label={label("故障证据", "Fault evidence")}>
        {faultLabels.map(([key, cn, en]) => {
          const value = domain.fault?.[key];
          return <div key={key}><dt>{label(cn, en)}</dt>
            <dd>{value === true ? label("是", "Yes") : value === false ? label("否", "No") : label("未知", "Unknown")}</dd>
          </div>;
        })}
      </dl>}
      {domain.gaps.includes("FAULT_EVENT_NOT_PERSISTED") && <p>{label(
        "缺少持久化故障事件。业务收据可单独核对。",
        "The fault event was not persisted. The business receipt can be checked separately.",
      )}</p>}
      {domain.gaps.length > 0 && <p><code>{domain.gaps.join(" · ")}</code></p>}
    </div>)}
    <p>{report.summary.next}</p>
    <p>{completion} · {report.issuer === "NOT_ESTABLISHED"
      ? label("签发者未确立", "Issuer not established") : report.issuer}</p>
    <p>{currentSchema
      ? label("网关响应摘要一致。下载后用 CLI 复核内容。", "Gateway response digest matched. Use the CLI to check the exported content.")
      : label("此诊断版本需用原版校验工具。", "Use the original verifier for this investigation format.")}</p>
  </section>;
}

export function CompetitionAgentPage({ search }: { search: string }) {
  const zh = useI18n().locale === "zh-CN";
  const l = (cn: string, en: string) => zh ? cn : en;
  const params = new URLSearchParams(search);
  const requested = params.get("session");
  const [session, setSession] = useState<AgentSession | null>(null);
  const [cap, setCap] = useState<AgentCapability | null>(null);
  const [notice, setNotice] = useState("");
  const [confirmation, setConfirmation] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(false);
  const [anchor, setAnchor] = useState("");
  const [selected, setSelected] = useState(() => Number(params.get("event")) || 0);
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0);
  const submitting = useRef(false);
  const [report, setReport] = useState<AgentInvestigation | null>(null);
  useEffect(() => {
    const epoch = ++generation.current;
    const current = () => generation.current === epoch;
    setCap(null); setSession(null); setAnchor(""); setReport(null); setConfirmation(false);
    setSelected(Number(new URLSearchParams(window.location.search).get("event")) || 0);
    async function read() {
      try {
        const value = await agentApi.capability();
        if (value.mode !== agentMode || value.provider_reservations !== 0) throw Error("MODE_UNAVAILABLE");
        const key = value.instance && pendingRequest(value.instance);
        const id = requested || value.latest;
        const data = id ? await agentApi.session(id) : key ? await agentApi.request(key) : null;
        if (data && (data.mode !== agentMode || (id && data.session_id !== id)
            || (value.instance && data.owner_id !== value.instance)
            || (!id && key && data.request_id !== key))) throw Error("SESSION_IDENTITY");
        if (!current()) return;
        if (key && value.instance && data?.request_id === key) pendingRequest(value.instance, null);
        setPending(!!(value.instance && pendingRequest(value.instance)));
        setSession(data); setCap(value); setNotice("");
        if (data) {
          const file = await agentApi.investigation(data.session_id);
          const result: AgentInvestigation = JSON.parse(new TextDecoder().decode(file.bytes));
          if (result.session.session_id !== data.session_id || result.session.owner_id !== data.owner_id) throw Error("SESSION_IDENTITY");
          if (current()) setReport(result);
        }
      } catch (error) {
        if (current()) { setCap(null); setNotice(error instanceof Error && error.message === "GATEWAY_404" ? "IDENTITY_NOT_FOUND" : "READBACK_UNAVAILABLE"); }
      }
    }
    void read();
    return () => { generation.current++; };
  }, [requested, search, refresh]);

  useEffect(() => {
    if (session && selected) document.querySelector<HTMLButtonElement>(
      '.ca-events button[aria-current="step"]')?.focus({ preventScroll: true });
  }, [session?.session_id, selected]);
  const startAllowed = mayStart(cap, pending) && !busy && !notice && !session && !requested;
  function bookmark(id: string, event?: number) {
    const next = new URLSearchParams({ session: id });
    if (event) next.set("event", String(event));
    history.replaceState(history.state, "", route + "?" + next.toString());
  }
  async function start() {
    if (!startAllowed || !confirmation || !cap?.instance || submitting.current) return;
    submitting.current = true;
    const epoch = generation.current;
    try {
      const fresh = await agentApi.capability();
      if (epoch !== generation.current) return;
      if (fresh.instance !== cap.instance || !mayStart(fresh, !!pendingRequest(cap.instance))) throw Error("OWNER_CHANGED");
      const id = crypto.randomUUID();
      pendingRequest(cap.instance, id);
      setPending(true); setBusy(true);
      const data = await agentApi.start(id, cap.instance);
      if (epoch !== generation.current) return;
      if (data.mode !== agentMode || data.request_id !== id || data.owner_id !== cap.instance) throw Error("SESSION_IDENTITY");
      pendingRequest(cap.instance, null);
      bookmark(data.session_id);
      setRefresh(x => x + 1);
    } catch {
      if (epoch === generation.current) {setCap(null); setNotice("RECONCILE_REQUIRED");}
    } finally { submitting.current = false; setBusy(false); setConfirmation(false); }
  }
  async function download() {
    if (!session || !cap) return;
    const epoch = generation.current;
    try {
      const file = await (session.status === "COMPLETED" ? agentApi.witness : agentApi.investigation)(session.session_id);
      const result = JSON.parse(new TextDecoder().decode(file.bytes));
      if (epoch !== generation.current) return;
      if (result.session.session_id !== session.session_id || result.session.owner_id !== session.owner_id) throw Error("SESSION_IDENTITY");
      const url = URL.createObjectURL(new Blob([file.bytes], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = session.session_id + (session.status === "COMPLETED" ? "-witness.json" : "-investigation.json");
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setAnchor(file.hash);
    } catch { if (epoch === generation.current) setNotice("EXPORT_UNAVAILABLE"); }
  }

  const focus = session?.events.find(item => item.seq === selected);
  const next = session?.events.find(item => item.kind === "AGENT_INTENT" && item.data.intent?.candidate_id === "ops");
  return <AppShell lab version={cap?.version ?? "Reference Agent"}><div className="competition-agent">
    <header className="ca-hero">
      <div><span>RunProof / Agent Reliability / EffectWitness</span>
        <h1>{l("Agent 行动与效果见证", "Agent actions and verified effects")}</h1>
        <p>{l("看 Agent 提议什么、Controller 批准什么，以及业务实际改变了什么。", "Inspect the Agent proposal, Controller approval and actual business effect.")}</p></div>
      <div><strong>{l("离线参考 Agent", "Offline reference Agent")}</strong><code>{cap?.profile ?? "effectwitness-reference/1"}</code>
        <span>SQLite · RULE POLICY · PROVIDER 0</span><code>{cap?.owner}</code></div>
    </header>
    <section className="ca-panel" aria-labelledby="ca-start">
      <h2 id="ca-start">{l("受控双域实验", "Controlled dual-domain experiment")}</h2>
      <p>{l("场景：订单退款 → 只读对账 → 配置变更", "Scenario: refund → read-only reconciliation → configuration change")} · {l("工具白名单", "Tool allowlist")} <code>refund_order, apply_config</code></p>
      <p role="status">{notice || session?.status || (cap ? agentMode : l("正在查询 Gateway", "Checking Gateway"))} · {l("剩余额度", "Remaining sessions")} {cap?.remaining ?? "—"}</p>
      <label><input type="checkbox" checked={confirmation} disabled={!startAllowed} onChange={e => setConfirmation(e.target.checked)} /> {l("确认执行一次本地实验", "Confirm one local experiment")}</label>
      <div className="ca-actions">
        <button type="button" disabled={!startAllowed || !confirmation} onClick={start}>{l("运行受控 Agent 实验", "Run controlled Agent experiment")}</button>
        <button type="button" disabled={busy} onClick={() => { setCap(null); setRefresh(x => x + 1); }}>{l("刷新只读结果", "Refresh read-only results")}</button>
      </div>
      <div className="ca-contracts">
        {[
          ["Execution", l("工具白名单、操作身份、写入权限", "Allowed tools, operation identity and write permissions"), "execution"],
          ["Effect", l("退款 25.00 CNY 与配置更新", "Refund of CNY 25.00 and config update"), "effect"],
          ["Experiment", l("订单提交后丢失响应，每域一次写入", "Post-commit order response loss; one write per domain"), "experiment"],
        ].map(([name, summary, field]) => <details key={name}><summary>{name}</summary><p>{summary}</p>
          {session && <pre>{JSON.stringify(session.candidates.map(candidate => ({ domain: candidate.candidate, contract_sha256: candidate.sha256,
            values: candidate[field as "execution" | "effect" | "experiment"] })), null, 2)}</pre>}</details>)}
      </div>
    </section>
    {session && <section className="ca-panel" aria-labelledby="ca-trace">
      <h2 id="ca-trace">{l("Agent 行动与证据", "Agent actions and evidence")}</h2>
      <p>{l("会话", "Session")} <code>{session.session_id}</code> · {session.status}</p>
      <div className="ca-columns">
        <div><h3>{l("行动时间线", "Action timeline")}</h3>
          <ol className="ca-events">{session.events.filter(item => keyEvents.has(item.kind)).map(event =>
            <li key={event.seq}><button type="button" aria-current={selected === event.seq ? "step" : undefined}
              data-kind={event.kind} onClick={() => { setSelected(event.seq); bookmark(session.session_id, event.seq); }}>
              <b>{String(event.seq).padStart(2, "0")}</b> {eventLabels[event.kind]?.[zh ? 0 : 1] ?? event.kind}
              <span>{eventValue(event) || event.origin}</span></button></li>)}</ol>
          {focus && <details><summary>{l("查看所选事件的绑定", "Inspect selected event bindings")}</summary><pre>{JSON.stringify(focus, null, 2)}</pre></details>}
        </div>
        <div><h3>{l("反馈怎样改变下一步", "How feedback changes the next action")}</h3>
          <p>{next?.data.intent?.tool ?? l("等待通过核验的反馈", "Awaiting verified feedback")}</p>
          {next?.data.intent?.input_feedback_sha256 && <p>{l("输入反馈 SHA-256", "Input feedback SHA-256")} <code>{next.data.intent.input_feedback_sha256}</code></p>}
          {session.rounds.map(round => {
            const a = round.before.order ?? round.before.config;
            const b = round.after.order ?? round.after.config;
            const keys = round.domain === "order" ? ["status", "refunded_minor", "revision"] : ["release", "revision"];
            return <article className="ca-effect" key={round.domain}>
              <h3>{round.domain === "order" ? l("订单退款", "Order refund") : l("运维配置", "Configuration")}</h3>
              <p>{round.tool_status} · {round.outcome.contract_outcome}</p>
              <dl>{keys.map(key => <div key={key}><dt>{key}</dt><dd>{String(a?.[key])} → {String(b?.[key])}</dd></div>)}</dl>
              <p>{l("独立读回收据", "Independent readback receipts")} <strong>{round.after.receipts.length}</strong></p>
              <details><summary>{l("故障四态与收据详情", "Fault flags and receipt details")}</summary><pre>{JSON.stringify({ fault: round.fault, receipts: round.after.receipts, feedback: round.feedback }, null, 2)}</pre></details>
            </article>;
          })}
          {report && <InvestigationEvidence report={report} label={l} />}
          <h3>{session.status === "COMPLETED" ? "Witness" : l("诊断报告", "Investigation report")}</h3>
          <button type="button" disabled={!cap} onClick={download}>{session.status === "COMPLETED" ? l("下载 Agent Witness", "Download Agent Witness") : l("下载调查报告", "Download investigation")}</button>
          {anchor && <p role="status">SHA-256 <code>{anchor}</code></p>}
          <details><summary>{l("源码身份", "Source identity")}</summary><pre>{JSON.stringify(session.source, null, 2)}</pre></details>
        </div>
      </div>
    </section>}
    <section className="ca-panel" aria-labelledby="ca-platform"><h2 id="ca-platform">{l("RunProof 可靠性工具", "RunProof reliability tools")}</h2>
      <p>{l("以下页面使用仓库中的审阅样本。工程包还提供 Java Control Plane、DeepSeek 接入边界和 JiuwenSwarm MCP 源码。", "These pages use the repository’s reviewed fixtures. Source extensions include Java Control Plane, DeepSeek and JiuwenSwarm MCP.")}</p>
      <nav aria-label={l("平台能力", "Platform features")}>{links.map(([href, cn, en]) => <a key={href} href={href}>{l(cn, en)}</a>)}</nav>
    </section>
  </div></AppShell>;
}

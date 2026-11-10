import { useEffect, useState } from "react";
import { navigate } from "../../app/navigation";
import { AppShell } from "../../components/AppShell";
import { useI18n } from "../../i18n";
import { mode, productApi, type Capability, type Session } from "./productLocalApi";
import "./product-local.css";

const requestKey = "runproof-rpf100-pending-request";
const route = "/effectwitness/live-local";
type Label = (en: string, zh: string) => string;
type Round = Session["rounds"][number];

export function writeBlock(cap: Capability | null, status: string | undefined, pending: boolean) {
  if (pending) return "PENDING_REQUEST";
  if (status && status !== "COMPLETED") return "RECONCILE_REQUIRED";
  if (!cap || cap.mode !== mode || cap.provider_reservations !== 0) return "UNAVAILABLE";
  if (cap.blocked !== false) return "RECONCILE_REQUIRED";
  if (!Number.isSafeInteger(cap.remaining) || cap.remaining <= 0) return "NO_QUOTA";
  return null;
}

export function localEventHref(search: string, session: string, seq: number) {
  const params = new URLSearchParams(search);
  params.set("session", session);
  params.set("event", String(seq));
  return `${route}?${params}`;
}

const fieldNames: Record<string, [string, string]> = {
  status: ["Status", "状态"], order_status: ["Order status", "订单状态"], refunded_minor: ["Refunded (minor units)", "已退款（最小货币单位）"],
  refund_amount_minor: ["Refund (minor units)", "退款金额（最小货币单位）"], revision: ["Revision", "版本修订"],
  version: ["Version", "版本"], release: ["Release version", "发布版本"], receipt_count: ["Receipt count", "收据数"],
  effect_count: ["Effect count", "变更次数"], history_count: ["History entries", "历史条数"],
};
const eventNames: Record<string, [string, string]> = {
  RUN_OPEN: ["Run opened", "会话建立"], CONTRACT_FROZEN: ["Contract frozen", "合同冻结"],
  CLAIMED: ["Experiment admitted", "实验准入"], WRITE_INTENT: ["Write intent recorded", "写入意图已记录"],
  WRITE_COMMIT: ["SQLite committed", "SQLite 已提交"], UNKNOWN: ["Response outcome unknown", "响应结果未知"],
  UNKNOWN_OUTCOME: ["Response outcome unknown", "响应结果未知"], AUTHORITY_BEFORE: ["Authority read before write", "Authority 写前读回"],
  AUTHORITY_AFTER: ["Authority read after write", "Authority 写后读回"], VERIFIED: ["Oracle verified", "Oracle 已验证"],
  FEEDBACK_VALIDATED: ["Feedback verified", "反馈已验证"], AUTHORITY_FEEDBACK_VALIDATED: ["Feedback verified", "反馈已验证"],
  SELECTION: ["Policy selected experiment", "策略选择实验"], STOPPED: ["Further writes stopped", "后续写入停止"],
};

function raw(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function valueText(value: unknown, missing: string) {
  if (value === undefined || value === null) return missing;
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function Facts({ round, label }: { round: Round; label: Label }) {
  const unavailable = label("UNAVAILABLE", "未取得");
  const diff = round.outcome.state_diff;
  const entries = diff && typeof diff === "object" && !Array.isArray(diff) ? Object.entries(diff) : [];
  const flags = [
    ["planned", label("Planned", "已计划")], ["triggered", label("Triggered", "已触发")],
    ["observed", label("Observed", "已观测")], ["agent_exposed", label("Agent exposed", "Agent 可见")],
  ] as const;
  return <article className="pl-round">
    <div className="pl-round-heading"><h3>{round.domain === "order" ? label("Order refund", "订单退款") : label("Operations configuration", "运维配置")}</h3>
      <strong className="pl-badge" data-tone={round.outcome.contract_outcome === "CONTRACT_SATISFIED_IN_RUN" ? "good" : "neutral"}>{round.outcome.contract_outcome || unavailable}</strong></div>
    <dl className="pl-fact-pair"><div><dt>{label("Tool result", "工具结果")}</dt><dd>{round.tool_status || unavailable}</dd></div>
      <div><dt>{label("Authority readback", "Authority 只读对账")}</dt><dd>{round.authority || unavailable}</dd></div>
      <div><dt>{label("Receipts after", "写后收据数")}</dt><dd>{Array.isArray(round.after?.receipts) ? round.after.receipts.length : unavailable}</dd></div></dl>
    {entries.length ? <div className="pl-diff" role="table" aria-label={label("Business state difference", "业务状态差异")}>
      <div role="row" className="pl-diff-head"><span role="columnheader">{label("Field", "字段")}</span><span role="columnheader">{label("Before", "之前")}</span><span role="columnheader">{label("After", "之后")}</span></div>
      {entries.map(([name, change]) => {
        const pair = change && typeof change === "object" ? change as { before?: unknown; after?: unknown } : {};
        const title = Object.hasOwn(fieldNames, name) ? label(...fieldNames[name]) : name;
        return <div role="row" key={name}><span role="rowheader">{title}</span><span role="cell">{valueText(pair.before, unavailable)}</span><span role="cell">{valueText(pair.after, unavailable)}</span></div>;
      })}
    </div> : <p className="pl-muted">{label("State difference unavailable.", "未取得业务状态差异。")}</p>}
    <div className="pl-fault"><span className="pl-caption">{label("Fault observations", "故障观测")}</span>
      <dl>{flags.map(([key, name]) => <div key={key}><dt>{name}</dt><dd>{round.fault?.[key] === true ? label("Yes", "是") : round.fault?.[key] === false ? label("No", "否") : unavailable}</dd></div>)}</dl>
    </div>
    <details><summary>{label("Technical details · receipt, verifier, source fields", "技术详情 · 收据、验证器与源字段")}</summary>
      <pre>{raw({ contract_sha256: round.contract_sha256, outcome: round.outcome, before: round.before, after: round.after, fault: round.fault })}</pre>
    </details>
  </article>;
}

export function SessionEvidence({ session, search, label, witness }: {
  session: Session; search: string; label: Label; witness: React.ReactNode;
}) {
  const query = new URLSearchParams(search);
  const requestedSession = query.get("session");
  const selected = !requestedSession || requestedSession === session.session_id ? query.get("event") : null;
  const selection = session.selection;
  const candidate = session.candidates.find(item => item.sha256 === selection?.selected_candidate_contract_sha256);
  const feedback = selection?.input_feedback_sha256;
  const linked = feedback ? session.rounds.find(round => round.feedback_sha256 === feedback) : undefined;
  const unavailable = label("UNAVAILABLE", "未取得");
  return <>
    <nav className="pl-steps" aria-label={label("Session evidence sections", "会话证据导航")}>
      <a href="#local-start">01 {label("Contract", "任务合同")}</a><a href="#local-session">02 {label("Timeline & feedback", "时间线与反馈")}</a>
      <a href="#local-state">03 {label("State difference", "状态变化")}</a><a href="#local-witness">04 Witness</a>
    </nav>
    <section className="pl-panel" aria-labelledby="local-session">
      <div className="pl-section-head"><div><span className="pl-caption">02 / {label("SESSION EVIDENCE", "会话证据")}</span><h2 id="local-session">{label("Timeline & verified feedback", "探索时间线与已验证反馈")}</h2></div><strong className="pl-badge">{session.status}</strong></div>
      <p className="pl-session-id">{label("Session", "会话")} <code>{session.session_id}</code> · Provider {session.provider_reservations}</p>
      {session.status === "RECONCILE_REQUIRED" && <p className="pl-warning" role="alert">{label("Write replay prohibited. Readback or human review is required.", "禁止重放写入。需只读对账或人工审查。")}</p>}
      <div className="pl-evidence-grid">
        <div><h3>{label("Durable timeline", "持久时间线")}</h3>
          {selected && !session.events.some(event => String(event.seq) === selected) && <p className="pl-muted">{label("Selected event unavailable in this session.", "此会话中未取得所选事件。")}</p>}
          {session.events.length ? <ol className="pl-events">{session.events.map(event => {
            const href = localEventHref(search, session.session_id, event.seq);
            const title = Object.hasOwn(eventNames, event.kind) ? label(...eventNames[event.kind]) : event.kind;
            return <li key={event.seq}><a href={href} aria-current={selected === String(event.seq) ? "step" : undefined}
              onClick={e => { if (!e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) { e.preventDefault(); navigate(href); } }}>
              <span className="pl-event-number">{String(event.seq).padStart(2, "0")}</span><span>{title}</span>{event.domain && <small>{event.domain}</small>}</a></li>;
          })}</ol> : <p>{unavailable}</p>}
        </div>
        <article className="pl-decision"><h3>{label("Policy decision", "策略决策")}</h3>
          {selection ? <><strong>{selection.decision}</strong><p>{selection.reason}</p>
            <dl className="pl-fact-pair"><div><dt>{label("Verified feedback input", "已验证反馈输入")}</dt><dd>{linked ? label("Matches session round", "与会话轮次匹配") : unavailable}</dd></div>
              <div><dt>{label("Selected contract", "所选合同")}</dt><dd>{candidate?.candidate ?? unavailable}</dd></div></dl>
          </> : <p>{label("Selection unavailable.", "未取得策略选择。")}</p>}
          <details><summary>{label("Technical details · candidates, hashes, budget", "技术详情 · 候选、哈希、预算")}</summary>
            <pre>{raw({ candidates: session.candidates, limits: session.limits, selection, feedback: session.rounds.map(round =>
              ({ domain: round.domain, feedback_sha256: round.feedback_sha256, feedback: round.feedback })) })}</pre>
          </details>
        </article>
      </div>
      <details><summary>{label("Technical details · original events", "技术详情 · 原始事件")}</summary><pre>{raw(session.events)}</pre></details>
    </section>
    <section className="pl-panel" aria-labelledby="local-state"><span className="pl-caption">03 / {label("BUSINESS FACTS", "业务事实")}</span>
      <h2 id="local-state">{label("State difference", "业务状态变化")}</h2>
      <div className="product-rounds">{session.rounds.length ? session.rounds.map(round => <Facts key={round.domain} round={round} label={label} />) : <p>{unavailable}</p>}</div>
    </section>
    <section className="pl-panel pl-witness" aria-labelledby="local-witness"><span className="pl-caption">04 / {label("VERIFY OFFLINE", "离线复核")}</span>
      <h2 id="local-witness">{label("Session Witness", "会话 Witness")}</h2>
      <p>{label("The download checks the returned bytes against their advertised SHA-256. Verify offline with a separately trusted digest.", "下载时校验响应字节与声明的 SHA-256。离线复核需要另行可信的摘要。")}</p>
      {witness}
      <p className="pl-muted">{label("External Issuer and release eligibility are unestablished.", "外部签发者身份与发布资格未建立。")}</p>
      <details><summary>{label("Technical details · cleanup", "技术详情 · 清理状态")}</summary><p>{session.cleanup || unavailable}</p></details>
    </section>
  </>;
}

export function ProductLocalPage({ search }: { search: string }) {
  const zh = useI18n().locale === "zh-CN";
  const label: Label = (en, cn) => zh ? cn : en;
  const params = new URLSearchParams(search);
  const sessionId = params.get("session");
  const [cap, setCap] = useState<Capability | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [readFor, setReadFor] = useState<string | null | undefined>();
  const [confirm, setConfirm] = useState(false);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [witness, setWitness] = useState<{ session: string; hash?: string; error?: string } | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    setCap(null);
    setError("");
    async function read() {
      try {
        const pendingId = localStorage.getItem(requestKey);
        setPending(!!pendingId);
        const value = await productApi.capability();
        if (value.mode !== mode || value.provider_reservations !== 0) throw new Error("GATEWAY_IDENTITY");
        const expected = sessionId || value.latest;
        const data = pendingId ? await productApi.readRequest(pendingId) : expected ? await productApi.session(expected) : null;
        if (!active) return;
        if (!pendingId && expected && data?.session_id !== expected) throw new Error("SESSION_IDENTITY");
        const current = localStorage.getItem(requestKey);
        if (pendingId && current === pendingId && data?.status === "COMPLETED") localStorage.removeItem(requestKey);
        setPending(!!localStorage.getItem(requestKey));
        setSession(data);
        setReadFor(sessionId);
        setCap(value);
      } catch {
        if (active) setError("READBACK_UNAVAILABLE");
      }
    }
    void read();
    const syncPending = (event: StorageEvent) => {
      if (event.key !== null && event.key !== requestKey) return;
      setCap(null);
      setConfirm(false);
      setRefresh(value => value + 1);
    };
    window.addEventListener("storage", syncPending);
    return () => { active = false; window.removeEventListener("storage", syncPending); };
  }, [refresh, sessionId]);

  const current = readFor === sessionId ? session : null;
  const block = writeBlock(cap, current?.status, pending);
  const canStart = readFor === sessionId && !!cap && !block && !busy && !error;

  async function start() {
    if (!confirm || !canStart) return;
    setBusy(true);
    setError("");
    setWitness(null);
    try {
      if (localStorage.getItem(requestKey)) { setPending(true); return; }
      const id = crypto.randomUUID();
      localStorage.setItem(requestKey, id);
      setPending(true);
      const data = await productApi.create(id);
      if (data.status === "COMPLETED" && localStorage.getItem(requestKey) === id) localStorage.removeItem(requestKey);
      setPending(!!localStorage.getItem(requestKey));
      setSession(data);
      setReadFor(data.session_id);
      setConfirm(false);
      setCap(null);
      params.set("session", data.session_id);
      if (sessionId !== data.session_id) params.delete("event");
      navigate(`${route}?${params}`);
      setRefresh(value => value + 1);
    } catch {
      setError("RECONCILE_REQUIRED");
      setCap(null);
    } finally { setBusy(false); }
  }

  async function download() {
    if (!current || current.status !== "COMPLETED") return;
    const id = current.session_id;
    setWitness({ session: id });
    try {
      const file = await productApi.witness(id);
      const url = URL.createObjectURL(new Blob([file.bytes], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "rpf100-witness.json";
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setWitness({ session: id, hash: file.hash });
    } catch (failure) {
      setWitness({ session: id, error: failure instanceof Error && failure.message === "WITNESS_HASH_MISMATCH"
        ? "WITNESS_HASH_MISMATCH" : "WITNESS_UNAVAILABLE" });
    }
  }

  return <AppShell lab><div className="product-local">
    <header className="pl-hero"><div><span className="pl-caption">EFFECTWITNESS / RPF-100</span>
      <h1>{label("From effect to verified feedback", "从实际效果到已验证反馈")}</h1>
      <p>{label("A deterministic policy explores fictional order and configuration targets. SQLite effects are read back independently. Paid Real Explorer is disabled.", "确定性策略探索虚构订单与配置目标，SQLite 效果由独立读回验证。付费真实 Explorer 已禁用。")}</p>
      <a href="/effectwitness/workbench">{label("← Recorded evidence workbench", "← 返回已记录证据工作台")}</a></div>
      <div className="pl-hero-mode"><span className="pl-caption">{label("EXECUTION MODE", "运行模式")}</span><strong>LOCAL CONTROLLED</strong><span>Provider 0</span></div>
    </header>
    <section className="pl-panel" aria-labelledby="local-start">
      <div className="pl-section-head"><div><span className="pl-caption">01 / {label("FROZEN TASK", "冻结任务")}</span>
        <h2 id="local-start">{label("Contract & admission", "任务合同与准入")}</h2></div>
        <strong className="pl-badge" role="status">{!cap && !error && !pending ? label("Checking local Gateway…", "正在核查本地 Gateway…") : block ?? "CONTROLLED_LOCAL_PRODUCT"}</strong></div>
      <div className="pl-contracts"><p><strong>{label("Execution", "执行")}</strong>{label("One explicitly admitted local session", "明确准入的一次本地会话")}</p>
        <p><strong>{label("Effect", "效果")}</strong>{label("Refund and configuration readback", "退款与配置效果读回")}</p>
        <p><strong>{label("Experiment", "实验")}</strong>{label("Response loss requires read-only reconciliation", "响应丢失后只读对账")}</p></div>
      {cap && <p className="pl-muted">{label("Remaining sessions", "剩余会话")}: {cap.remaining}</p>}
      <label className="pl-confirm"><input type="checkbox" checked={confirm} disabled={!canStart} onChange={e => setConfirm(e.target.checked)} /> {label("I authorize one fictional local session", "确认执行一次虚构本地会话")}</label>
      <div className="product-actions"><button type="button" onClick={start} disabled={!canStart || !confirm}>{label("Start local session", "启动本地会话")}</button>
        <button className="pl-secondary" type="button" onClick={() => { setCap(null); setConfirm(false); setRefresh(value => value + 1); }} disabled={busy}>{label("Refresh readback", "刷新只读状态")}</button></div>
      {(error || pending) && <p className="pl-warning" role="alert">{error || "PENDING_REQUEST"} · {error === "READBACK_UNAVAILABLE" && !pending
        ? label("The local Gateway or readback is unavailable. Refresh the read-only status before starting.", "本地 Gateway 或读回暂不可用。启动前请刷新只读状态。")
        : label("Use readback to inspect the existing request. Do not repeat a write after uncertainty.", "只读查询原请求。结果未知时不得重复写入。")}</p>}
    </section>
    {current && <SessionEvidence session={current} search={search} label={label} witness={<>
      {current.status === "COMPLETED" ? <button type="button" onClick={download}
        disabled={!cap || (witness?.session === current.session_id && !witness.hash && !witness.error)}>{label("Download session Witness", "下载会话 Witness")}</button>
        : <strong>{label("Witness unavailable for this session.", "此会话尚无可下载 Witness。")}</strong>}
      {witness?.session === current.session_id && (witness.hash ? <p role="status">SHA-256 <code>{witness.hash}</code></p>
        : witness.error ? <p className="pl-warning" role="alert">{witness.error}</p> : <p role="status">{label("Checking Witness…", "正在校验 Witness…")}</p>)}
    </>} />}
  </div></AppShell>;
}

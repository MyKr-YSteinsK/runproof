import { useEffect, useState } from "react";
import { navigate } from "../../app/navigation";
import { AppShell } from "../../components/AppShell";
import { useI18n } from "../../i18n";
import { mode, productApi, type Capability, type Session } from "./productLocalApi";
import "./product-local.css";

const requestKey = "runproof-rpf100-pending-request";
const route = "/effectwitness/live-local";

export function ProductLocalPage({ search }: { search: string }) {
  const zh = useI18n().locale === "zh-CN";
  const label = (en: string, cn: string) => zh ? cn : en;
  const params = new URLSearchParams(search);
  const sessionId = params.get("session");
  const selectedEvent = params.get("event");
  const [cap, setCap] = useState<Capability | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hash, setHash] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    setError("");
    productApi.capability().then(async value => {
      if (value.mode !== mode || value.provider_reservations !== 0) throw new Error("GATEWAY_IDENTITY");
      if (active) setCap(value);
      const pending = localStorage.getItem(requestKey);
      const data = pending ? await productApi.readRequest(pending)
        : sessionId || value.latest ? await productApi.session(sessionId || value.latest!) : null;
      if (!active) return;
      if (pending && data) localStorage.removeItem(requestKey);
      setSession(data);
    }).catch(() => {
      if (active) { setCap(null); setError("READBACK_UNAVAILABLE"); }
    });
    return () => { active = false; };
  }, [refresh, sessionId]);

  async function start() {
    if (!confirm || busy || !cap?.remaining || cap.blocked || localStorage.getItem(requestKey)) return;
    const id = crypto.randomUUID();
    localStorage.setItem(requestKey, id);
    setBusy(true);
    setError("");
    setHash("");
    try {
      const data = await productApi.create(id);
      localStorage.removeItem(requestKey);
      setSession(data);
      setConfirm(false);
      navigate(`${route}?session=${encodeURIComponent(data.session_id)}`);
      setRefresh(value => value + 1);
    } catch {
      setError("RECONCILE_REQUIRED");
      setCap(null);
    } finally { setBusy(false); }
  }

  async function download() {
    if (!session || session.status !== "COMPLETED") return;
    try {
      const witness = await productApi.witness(session.session_id);
      setHash(witness.hash);
      const url = URL.createObjectURL(new Blob([witness.bytes], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "rpf100-witness.json";
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setError("WITNESS_UNAVAILABLE"); }
  }

  return <AppShell lab><div className="product-local">
    <header><p>RPF-100 · {label("New Local Controlled", "全新本地受控会话")}</p>
      <h1>{label("From effect to verified feedback", "从实际效果到已验证反馈")}</h1>
      <p>{label("Rule policy with fictional SQLite targets. Paid Real Explorer is disabled. Provider reservations: 0.",
        "使用确定性策略和虚构 SQLite 目标。付费真实 Explorer 已禁用，Provider 预约为 0。")}</p>
      <a href="/effectwitness/workbench">{label("Recorded Historical workbench", "返回历史记录工作台")}</a>
    </header>
    <section aria-labelledby="local-start"><h2 id="local-start">{label("Start or read back", "开始或只读恢复")}</h2>
      {cap ? <p>{label("Remaining sessions", "剩余会话")}: {cap.remaining} · {cap.blocked ? "RECONCILE_REQUIRED" : "CONTROLLED_LOCAL_PRODUCT"}</p>
        : <p role="status">{error ? "UNAVAILABLE" : label("Checking local Gateway…", "正在核查本地 Gateway…")}</p>}
      <label><input type="checkbox" checked={confirm} onChange={e => setConfirm(e.target.checked)} /> {label("I authorize one fictional local session", "确认执行一次虚构本地会话")}</label>
      <div className="product-actions">
        <button type="button" onClick={start} disabled={busy || !confirm || !cap?.remaining || cap.blocked || !!error}>{label("Start local session", "启动本地会话")}</button>
        <button type="button" onClick={() => setRefresh(value => value + 1)} disabled={busy}>{label("Refresh readback", "刷新只读状态")}</button>
      </div>
      {error && <p role="alert">{error} · {label("Use readback to inspect the existing request. Do not repeat a write after uncertainty.", "只读查询原请求。结果未知时不得重复写入。")}</p>}
    </section>
    {session && <section aria-labelledby="local-session"><h2 id="local-session">{label("Session evidence", "会话证据")}</h2>
      <p><code>{session.session_id}</code> · <strong>{session.status}</strong> · Provider {session.provider_reservations}</p>
      {session.status === "RECONCILE_REQUIRED" && <p role="alert">{label("Write replay prohibited. Readback or human review is required.", "禁止重放写入。需只读对账或人工审查。")}</p>}
      <h3>{label("Frozen candidates and budget", "冻结候选与预算")}</h3>
      <ul>{session.candidates.map(candidate => <li key={candidate.candidate}>{candidate.candidate} · <code>{candidate.sha256}</code></li>)}</ul>
      <pre>{JSON.stringify(session.limits, null, 2)}</pre>
      <h3>{label("Durable timeline", "持久时间线")}</h3>
      <ol>{session.events.map(event => {
        const href = `${route}?session=${session.session_id}&event=${event.seq}`;
        return <li key={event.seq}><a href={href} aria-current={selectedEvent === String(event.seq) ? "step" : undefined}
          onClick={e => { e.preventDefault(); navigate(href); }}>{event.kind}{event.domain ? " · " + event.domain : ""}</a></li>;
      })}</ol>
      <div className="product-rounds">{session.rounds.map(round => <article key={round.domain}>
        <h3>{round.domain === "order" ? label("Order refund", "订单退款") : label("Operations configuration", "运维配置")}</h3>
        <p>{round.tool_status} · {round.authority}</p>
        <p>{round.outcome.contract_outcome} · {round.outcome.verifier_id}</p>
        <h4>{label("Fault and state difference", "故障与状态差异")}</h4>
        <pre>{JSON.stringify({ fault: round.fault, state_diff: round.outcome.state_diff, receipts: round.after.receipts }, null, 2)}</pre>
        <details><summary>{label("Verified feedback", "已验证反馈")}</summary><code>{round.feedback_sha256}</code><pre>{JSON.stringify(round.feedback, null, 2)}</pre></details>
      </article>)}</div>
      <h3>{label("Policy decision", "策略决策")}</h3>
      <pre>{JSON.stringify(session.selection, null, 2)}</pre><p>{session.cleanup}</p>
      {session.status === "COMPLETED" && <button type="button" onClick={download}>{label("Download session Witness", "下载会话 Witness")}</button>}
      {hash && <p role="status">SHA-256 <code>{hash}</code></p>}
      <p>{label("Use the offline verifier with a separately trusted SHA-256. External Issuer, production and Release are unestablished.",
        "用另行可信的 SHA-256 运行离线验证器。外部 Issuer、生产环境与发布资格未建立。")}</p>
    </section>}
  </div></AppShell>;
}

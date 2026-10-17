import { useEffect, useRef, useState } from "react";
import { AppShell } from "../../components/AppShell";
import { useI18n } from "../../i18n";
import { navigate } from "../../app/navigation";
import { capabilities, getSession, startSession, cancelSession, witnessBytes, LabApiError, TERMINAL, type Capability, type Session, type Domain } from "./labApi";
import { labCopy } from "./copy";
import "./lab.css";

const PENDING = "runproof.lab.pending-request";
const pretty = (v: unknown) => JSON.stringify(v, null, 2);
function pendingRequest(): { domain: Domain; id: string } | null {
  try { const p = JSON.parse(sessionStorage.getItem(PENDING) || "null"); return p && ["order", "ops"].includes(p.domain) && typeof p.id === "string" ? p : null; }
  catch { return null; }
}
export function LabPage({ path, search }: { path: string; search: string }) {
  const { locale } = useI18n();
  const text = labCopy[locale];
  const sid = path.match(/^\/effectwitness\/sessions\/(session-[a-f0-9]{32})$/)?.[1];
  const validPath = path === "/effectwitness" || Boolean(sid);
  const [cap, setCap] = useState<Capability | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [domain, setDomain] = useState<Domain>(() => pendingRequest()?.domain || "order");
  const [pending, setPending] = useState(pendingRequest);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [checked, setChecked] = useState(false);
  const [revision, setRevision] = useState(0);
  const submitting = useRef(false);
  useEffect(() => {
    let active = true;
    setError(""); setSession(null); setCap(null); setChecked(false);
    capabilities().then(v => { if (active) setCap(v); }).catch(e => { if (active) setError(e.code || "GATEWAY_UNAVAILABLE"); });
    return () => { active = false; };
  }, [sid, revision]);
  useEffect(() => {
    if (!sid) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let polls = 0;
    const poll = async () => {
      if (!active || document.hidden) return;
      try {
        const value = await getSession(sid);
        if (!active) return;
        setSession(value); setError("");
        if (!TERMINAL.has(value.status) && ++polls < 900) timer = setTimeout(poll, 1000);
        else if (!TERMINAL.has(value.status)) setError("POLL_WINDOW_EXHAUSTED");
      } catch (e) { if (active) { setSession(null); setError(e instanceof LabApiError ? e.code : "GATEWAY_UNAVAILABLE"); } }
    };
    const visibility = () => { clearTimeout(timer); if (!document.hidden) void poll(); };
    document.addEventListener("visibilitychange", visibility);
    void poll();
    return () => { active = false; clearTimeout(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [sid, revision]);
  async function start() {
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    const request = pending || { domain, id: crypto.randomUUID() };
    try {
      sessionStorage.setItem(PENDING, pretty(request));
      setPending(request);
      const value = await startSession(request.domain, request.id);
      sessionStorage.removeItem(PENDING); setPending(null);
      navigate("/effectwitness/sessions/" + value.session_id);
    } catch (e) {
      const code = e instanceof LabApiError ? e.code : "GATEWAY_UNAVAILABLE";
      if (["SESSION_REQUEST_REJECTED", "TRIAL_QUOTA_EXHAUSTED", "GATEWAY_BUSY", "ORIGIN_REJECTED", "AUTH_REQUIRED"].includes(code)) {
        sessionStorage.removeItem(PENDING); setPending(null);
      }
      setError(code);
    }
    finally { submitting.current = false; setBusy(false); }
  }
  async function download() {
    if (!session) return;
    try {
      await witnessBytes(session);
      setChecked(true);
    } catch (e) { setChecked(false); setSession(null); setError(e instanceof LabApiError ? e.code : "WITNESS_UNAVAILABLE"); }
  }
  const selected = session?.events.find(e => e.event_id === new URLSearchParams(search).get("event"));
  const o = session?.result?.observation;
  const diff = o?.effect.state_diff && typeof o.effect.state_diff === "object" ? Object.entries(o.effect.state_diff as Record<string, { before: unknown; after: unknown }>) : [];
  const show = (v: unknown) => typeof v === "string" ? v : JSON.stringify(v) ?? "—";
  return <AppShell lab><section className="ew-lab">
    <header className="ew-heading"><span className="ew-source">{text.scope}</span><h1>{text.title}</h1><p>{text.subtitle}</p><small>{text.explorer}</small></header>
    {(!validPath || error) && <div className="ew-error" role="alert"><strong>{!validPath ? "INVALID_LAB_ROUTE" : error}</strong><p>{!validPath || error === "SESSION_NOT_FOUND" ? text.missing : ["GATEWAY_BUSY", "TRIAL_QUOTA_EXHAUSTED", "RECONCILE_REQUIRED", "SESSION_REQUEST_REJECTED"].includes(error) ? text.rejected : text.unavailable}</p><button onClick={() => setRevision(r => r + 1)}>{text.retry}</button></div>}
    {validPath && !sid && <section className="ew-panel ew-setup"><h2>01 · {text.setup}</h2>
      <label htmlFor="ew-domain">{text.domain}</label><select id="ew-domain" value={domain} disabled={Boolean(pending) || busy} onChange={e => setDomain(e.target.value as Domain)}><option value="order">{text.order}</option><option value="ops">{text.ops}</option></select>
      <p>{text.fault}</p><p>{text.remaining}: {cap?.remaining_reservations ?? "—"}</p>
      <button className="ew-primary" disabled={busy || !cap?.enabled || (!pending && cap.remaining_reservations === 0)} onClick={() => void start()}>{busy ? "…" : pending ? text.recover : text.start}</button>
      {pending && <p role="status">{text.unknown}</p>}
      <h3>{text.budget}</h3><pre>{pretty(cap?.limits ?? "UNAVAILABLE")}</pre>
    </section>}
    {sid && <>
      <div className="ew-session"><strong>{session?.status || (error ? "INCONCLUSIVE" : "LOADING")}</strong><code>{sid}</code><code>{session?.run_id}</code><span>{session?.source}</span></div>
      {session?.error_code && <div className="ew-error" role="alert">{session.error_code} · {text.noWitness}</div>}
      {session && <div className="ew-grid"><section className="ew-panel"><h2>01 · {text.timeline}</h2><ol className="ew-events">{session.events.map(e => <li key={e.event_id}>
        <a aria-current={selected?.event_id === e.event_id ? "step" : undefined} href={path + "?event=" + e.event_id} onClick={ev => { ev.preventDefault(); navigate(path + "?event=" + e.event_id); }}><span>{String(e.seq).padStart(2, "0")}</span>{e.type}<small>{e.observed_at}</small></a>
      </li>)}</ol>{selected && <><h3>{text.raw}</h3><pre>{pretty(selected.facts)}</pre></>}
      {!TERMINAL.has(session.status) && <><button onClick={() => void cancelSession(sid).then(setSession).catch(e => setError(e.code))}>{text.cancel}</button><p>{text.cancelNote}</p></>}
      </section><div className="ew-results"><section className="ew-panel"><h2>02 · {text.result}</h2><small>{text.evidence}</small>
        {session.result ? <dl className="ew-axes">{Object.entries(session.result.claims).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl> : <p>{text.noWitness}</p>}
        {o && <><h3>{text.actualFault}</h3><div className="ew-fault">{Object.entries(o.fault).map(([key, value]) => <span key={key}>{key}: <strong>{show(value)}</strong></span>)}</div><h3>{text.diff}</h3>
          <table className="ew-diff"><thead><tr><th>{text.field}</th><th>{text.before}</th><th>{text.after}</th></tr></thead><tbody>{diff.map(([key, value]) => <tr key={key}><th>{key}</th><td>{show(value.before)}</td><td>{show(value.after)}</td></tr>)}</tbody></table>
          <h3>{text.feedback}</h3><p><code>{show(o.feedback.contract_outcome)} / {show(o.feedback.fault_activation)}</code></p><details><summary>{text.rawFeedback}</summary><pre>{pretty(o.feedback)}</pre></details></>}
      </section><section className="ew-panel"><h2>03 · {text.witness}</h2>
        {session.witness ? <><p>{text.trust}</p><code>{session.witness.sha256}</code><p>{session.witness.bytes} bytes</p><button onClick={() => void download()}>{text.download}</button>{checked && <><p role="status">{text.checked}</p><a href={"/effectwitness-api/sessions/" + session.session_id + "/witness"} download>{text.save}</a></>}</> : <p>{text.noWitness}</p>}
      </section></div></div>}
      {session && <details className="ew-panel"><summary>{text.details}</summary><pre>{pretty({ contracts: session.contracts, usage: session.usage, authority_before: o?.authority_before, authority_after: o?.authority_after, tool_calls: o?.tool_calls, reconciliation: o?.reconciliation, cleanup: o?.cleanup })}</pre></details>}
      {session && TERMINAL.has(session.status) && session.status !== "RECONCILE_REQUIRED" && <a href="/effectwitness" onClick={e => { e.preventDefault(); navigate("/effectwitness"); }}>{text.back}</a>}
    </>}
  </section></AppShell>;
}

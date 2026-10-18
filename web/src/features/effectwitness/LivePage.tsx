import { useEffect, useState } from "react";
import { AppShell } from "../../components/AppShell";
import { useI18n } from "../../i18n";
import { navigate } from "../../app/navigation";
import { getLive, startLive, cancelLive, liveCapabilities, liveWitness, LIVE_TERMINAL, type LiveCapability, type LiveSession, type LiveTrial } from "./liveApi";
import "./lab.css";

const PENDING = "runproof.lab.live.pending-request";
const pretty = (v: unknown) => JSON.stringify(v, null, 2);
const show = (v: unknown) => typeof v === "string" ? v : JSON.stringify(v);
export const liveText = {
  "zh-CN": {title:"订单 PGE · 实时 Explorer", sub:"两轮模型选择、独立权威反馈与本机虚构退款。",
    setup:"付费实验设置", scope:"真实模型 API 调用 · 本机受控模拟", free:"免费确定性捕获（订单 / 运维）", start:"启动一次付费 PGE 会话",
    recover:"找回同一请求", reconnect:"重新连接 / 读取", remaining:"剩余会话", budget:"硬预算", model:"请求模型（实际身份以响应为准）",
    note:"最多 2 次模型请求、2 次退款实验、12,000 tokens、¥1.50 保守上界；不自动重试。候选可重复。",
    offline:"UNAVAILABLE / INCONCLUSIVE · 以下为已加载的只读快照，在线状态未确认。不会自动重跑。",
    unknown:"请求结果未知，保留同一 request_id 找回；不要创建替代会话。", cancel:"请求取消", cancelNote:"取消请求不等于已安全终止；运行中的退款仍需收据对账。",
    timeline:"模型 → 权威反馈 → 下一轮", trials:"真实实验与独立效果", before:"变更前", after:"变更后", field:"字段",
    feedback:"已验证反馈", trust:"仅核对本地内容；外部可信锚未建立，签发者真实性未建立。", check:"核对 Witness 字节", download:"下载已核对证书",
    research:"本次研究结论", usage:"已确认用量与持久预留", facts:"新增有效观察（排除随机身份）", round:"轮次", details:"合同 / 收据 / 权威读回", noReason:"模型自然语言理由未记录。",
    disabled:"服务端未启用、密钥缺失、额度已用或存在未决状态时无法启动。", local:"CONTENT_CHECKED_LOCAL · issuer NOT_ESTABLISHED"},
  "en-US": {title:"Order PGE · Live Explorer", sub:"Two model choices, independent authority feedback and fictional local refunds.",
    setup:"Paid experiment setup", scope:"Real model API calls · local controlled simulation", free:"Free deterministic capture (order / ops)", start:"Start one paid PGE session",
    recover:"Recover the same request", reconnect:"Reconnect / read", remaining:"Sessions remaining", budget:"Hard limits", model:"Requested model (actual identity from response)",
    note:"At most 2 model requests, 2 refund trials, 12,000 tokens, ¥1.50 conservative upper bound; no automatic retries. Repeats are legal.",
    offline:"UNAVAILABLE / INCONCLUSIVE · Loaded read-only snapshot; online status is unconfirmed. No automatic replay.",
    unknown:"Outcome unknown. Keep the same request_id for recovery; do not create a replacement session.", cancel:"Request cancellation", cancelNote:"Cancellation is a request; an in-flight refund still requires receipt reconciliation.",
    timeline:"Model → authority feedback → next round", trials:"Actual trials and independent effects", before:"Before", after:"After", field:"Field",
    feedback:"Validated feedback", trust:"Local content check only; no external trusted anchor or established issuer authenticity.", check:"Check Witness bytes", download:"Download checked certificate",
    research:"Research result in this session", usage:"Confirmed usage and durable reservations", facts:"New effective observations (random identities excluded)", round:"Round", details:"Contracts / receipts / authority readbacks", noReason:"Model natural-language rationale was not recorded.",
    disabled:"Starting requires explicit server opt-in, a configured key, remaining quota and no unresolved state.", local:"CONTENT_CHECKED_LOCAL · issuer NOT_ESTABLISHED"}
};
function Witness({s,t,online}: {s: LiveSession;t: LiveTrial;online:boolean}) {
  const {locale} = useI18n(); const c = liveText[locale];
  const [url,setUrl]=useState(""); const [error,setError]=useState("");
  useEffect(()=>{ if (!online) setUrl(""); },[online]);
  useEffect(()=>()=>{if(url) URL.revokeObjectURL(url);},[url]);
  return <div className="ew-witness"><strong>{t.witness.status}</strong><p>{c.trust}</p>
    {t.witness.status === "CONTENT_CHECKED_LOCAL" && <><code>{t.witness.sha256}</code><p>{c.local}</p>
      <button disabled={!online} onClick={()=>void liveWitness(s,t).then(raw=>{setError("");setUrl(URL.createObjectURL(new Blob([new Uint8Array(raw)],{type:"application/json"})));}).catch(()=>{setUrl("");setError("WITNESS_UNAVAILABLE_OR_INVALID");})}>{c.check}</button>
      {url && online && <a href={url} download={`witness-${s.session_id}-${t.round}.json`}>{c.download}</a>}{error && <p role="alert">{error}</p>}</>}
  </div>;
}
export function LivePage({path,search}:{path:string;search:string}) {
  const {locale}=useI18n();const c=liveText[locale];
  const sid=path.match(/^\/effectwitness\/explorations\/(exploration-[a-f0-9]{32})$/)?.[1];
  const valid=path==="/effectwitness/explorations" || Boolean(sid);
  const [cap,setCap]=useState<LiveCapability|null>(null);const [s,setS]=useState<LiveSession|null>(null);
  const [error,setError]=useState("");const [online,setOnline]=useState(false);const [busy,setBusy]=useState(false);
  const [revision,setRevision]=useState(0);
  const [pending,setPending]=useState(()=>{try{return sessionStorage.getItem(PENDING)||"";}catch{return "";}});
  useEffect(()=>{
    let disposed=false;let timer:ReturnType<typeof setTimeout>|undefined;const deadline=Date.now()+1200000;
    setOnline(false);setS(null);setError("");
    const load=async()=>{
      if(Date.now()>=deadline)return;
      if(document.hidden){timer=setTimeout(()=>void load(),1000);return;}
      try {const value=sid?await getLive(sid):await liveCapabilities();if(disposed)return;
        setError("");setOnline(true);if(sid)setS(value as LiveSession);else setCap(value as LiveCapability);
        if(sid)timer=setTimeout(()=>void load(),LIVE_TERMINAL.has((value as LiveSession).status)?5000:1000);
      }catch(e){if(!disposed){setOnline(false);setError(e instanceof Error?e.message:"GATEWAY_UNAVAILABLE");}}
    };
    if(valid)void load();return()=>{disposed=true;if(timer)clearTimeout(timer);};
  },[sid,revision,valid]);
  async function start(){setBusy(true);setError("");
    const id=pending || crypto.randomUUID();setPending(id);sessionStorage.setItem(PENDING,id);
    try{const value=await startLive(id);sessionStorage.removeItem(PENDING);setPending("");navigate("/effectwitness/explorations/"+value.session_id);}
    catch(e){setOnline(false);setError(e instanceof Error?e.message:"GATEWAY_UNAVAILABLE");}finally{setBusy(false);}
  }
  const selected=s?.events.find(e=>e.event_id===new URLSearchParams(search).get("event"));
  return <AppShell lab><section className="ew-lab ew-live"><header className="ew-heading"><span className="ew-source">{c.scope}</span><h1>{c.title}</h1><p>{c.sub}</p>
    <a href="/effectwitness" onClick={e=>{e.preventDefault();navigate("/effectwitness");}}>{c.free}</a><p><a href="/effectwitness/recorded" onClick={e=>{e.preventDefault();navigate("/effectwitness/recorded");}}>{locale === "zh-CN" ? "打开已记录的 RPF-46 只读演示" : "Open the recorded RPF-46 read-only walkthrough"}</a></p></header>
    {(!valid||error)&&<div className="ew-error" role="alert"><strong>{valid?error:"INVALID_LAB_ROUTE"}</strong><p>{c.offline}</p><button onClick={()=>setRevision(x=>x+1)}>{c.reconnect}</button></div>}
    {valid&&!sid&&<section className="ew-panel ew-setup"><h2>01 · {c.setup}</h2><p>{c.model}: <strong>{cap?.requested_model||"UNAVAILABLE"}</strong></p>
      <p>Explorer: <strong>{online?cap?.explorer:"UNAVAILABLE"}</strong> · {c.remaining}: {cap?.remaining_sessions??"—"} · busy: {String(cap?.busy??false)}</p>
      <p>{c.note}</p><button className="ew-primary" disabled={busy||!online||(!pending&&(!cap?.enabled||cap.busy||!cap.remaining_sessions))} onClick={()=>void start()}>{busy?"…":pending?c.recover:c.start}</button>
      <p>{pending?c.unknown:c.disabled}</p><h3>{c.budget}</h3><pre>{pretty(cap?.limits||"UNAVAILABLE")}</pre></section>}
    {sid&&<div className="ew-session"><strong>{online?s?.status||"LOADING":"INCONCLUSIVE / SNAPSHOT"}</strong><code>{sid}</code><code>{s?.plan_digest}</code><button onClick={()=>setRevision(x=>x+1)}>{c.reconnect}</button></div>}
    {s&&<><div className="ew-provenance"><strong>{s.explorer}</strong><span>{s.target_driver}</span><span>{s.source}</span><small>{s.rationale} · {c.noReason}</small></div>
      {s.error_code&&<div className="ew-error" role="alert">{s.error_code} · {s.run_outcome}</div>}
      <section className="ew-panel"><h2>01 · {c.timeline}</h2><div className="ew-choice-chain">{s.selections.map((x,i)=><div key={x.round}><strong>{c.round} {x.round} · {x.candidate_id}</strong><code>{x.tool_call_id}</code><code>{x.response_id}</code>
        <p>{i===0?"observed_feedback=[]":`role=tool ← ${s.selections[0].tool_call_id}`}</p>{x.input_feedback_hash&&<code>{x.input_feedback_hash}</code>}
        <p>{c.facts}: {s.trials[i]?.new_facts.join(", ")||"NONE"}</p></div>)}</div>
      <details><summary>Timeline · {s.events.length}</summary><ol className="ew-events">{s.events.map(e=><li key={e.event_id}><a href={path+"?event="+e.event_id} aria-current={selected?.event_id===e.event_id?"step":undefined} onClick={ev=>{ev.preventDefault();navigate(path+"?event="+e.event_id);}}>{e.seq} · {e.type}<small>{e.observed_at}</small></a></li>)}</ol></details>
      {selected&&<pre>{pretty(selected.facts)}</pre>}{!LIVE_TERMINAL.has(s.status)&&<><button disabled={!online} onClick={()=>void cancelLive(sid!).then(setS).catch(e=>{setError(e.message);setOnline(false);})}>{c.cancel}</button><p>{c.cancelNote}</p></>}</section>
      <h2>{c.trials}</h2>{s.trials.map(t=><section className="ew-panel" key={t.round}><h2>{c.round} {t.round} · {t.candidate_id}</h2><code>{t.run_id}</code>
        <dl className="ew-axes">{Object.entries(t.claims).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
        <div className="ew-fault">{Object.entries(t.observation.fault).map(([k,v])=><span key={k}>{k}: <strong>{show(v)}</strong></span>)}</div>
        <table className="ew-diff"><thead><tr><th>{c.field}</th><th>{c.before}</th><th>{c.after}</th></tr></thead><tbody>{Object.entries(t.observation.effect.state_diff).map(([k,v])=><tr key={k}><th>{k}</th><td>{show(v.before)}</td><td>{show(v.after)}</td></tr>)}</tbody></table>
        <h3>{c.feedback}</h3><code>{t.feedback_sha256}</code><details><summary>{c.feedback} JSON</summary><pre>{pretty(t.feedback)}</pre></details>
        <details><summary>{c.details}</summary><pre>{pretty({contracts:t.contracts,before:t.observation.authority_before,after:t.observation.authority_after,reconciliation:t.observation.reconciliation,cleanup:t.observation.cleanup})}</pre></details>
        <Witness s={s} t={t} online={online}/></section>)}
      <section className="ew-panel"><h2>{c.research}</h2><dl className="ew-axes">{Object.entries(s.research).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{show(v)}</dd></div>)}</dl><p>CORRELATIONAL_ONLY · NO_COUNTERFACTUAL · NO_STATISTICAL_GENERALIZATION</p>
        <h3>{c.usage}</h3><pre>{pretty(s.usage)}</pre><details><summary>Provider protocol / usage</summary><pre>{pretty(s.provider_requests)}</pre></details></section></>}
  </section></AppShell>;
}

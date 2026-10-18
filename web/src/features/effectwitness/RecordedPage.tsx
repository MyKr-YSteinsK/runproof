import { useEffect, useMemo, useState } from "react";
import { navigate } from "../../app/navigation";
import { AppShell } from "../../components/AppShell";
import { useI18n } from "../../i18n";
import { validateRecordedPayload, type RecordedEvidence, type RecordedEvent } from "./recordedEvidence";
import "./lab.css";

const copy = {
  "zh-CN": {
    badge: "RECORDED · 已提交研究摘要", title: "EffectWitness｜证据驱动的受控实验", subtitle: "回看已记录的两轮选择与独立业务核验。此页面仅读取已提交文件，不会启动实验。",
    link: "返回受控实验室", source: "证据来源", sourceBranch: "源分支", commit: "源提交", session: "会话", created: "北京时间",
    requests: "模型请求", requestInfo: "DeepSeek HTTP 200 × 2", trials: "新鲜受控试验", trialInfo: "每轮一个订单试验", tokens: "已报告 tokens", tokensInfo: "来自已提交摘要", cost: "费用估算上界", costInfo: "历史估算；本轮无新费用", timeline: "反馈验证与后续选择（按记录顺序）", outcomes: "独立业务效果",
    round: "轮次", before: "变更前", after: "变更后", normal: "第一轮：模型选择 normal；无计划故障。", feedback: "第一轮反馈经独立 Authority / Oracle 验证。",
    input: "第二轮请求输入已包含相同反馈 hash。", lost: "第二轮：模型选择 response-lost；故障触发。", reconciled: "独立读回后调和唯一提交收据。", ended: "该已记录会话结束。",
    contract: "退款合同：两轮均满足", contractValue: "PAID → REFUNDED · CONTRACT_SATISFIED_IN_RUN", fault: "第二轮故障：已触发并调和", faultValue: "TRIGGERED · RECONCILED_COMMITTED", receipt: "每轮收据：各一张", receiptValue: "两轮各一张", violations: "合同违规：未发现", violationValue: "两轮 violated_rules 均为空",
    chain: "第 1 轮反馈先于第 2 轮选择，hash 完全匹配", rounds: "业务前后状态", recorded: "只读 RECORDED", unavailable: "已记录来源无法验证；已隐藏演示内容，不使用夹具补位。",
    checking: "正在核验嵌入来源的固定 SHA-256、manifest 身份与报告结构…", verified: "嵌入来源的固定摘要和身份字段通过核验；Git 祖先与提交对象字节见下方离线命令。",
    historical: "分开的历史 Witness 样本", order: "RPF-43 · 受控退款样本", ops: "RPF-44 · 受控运维样本", anchored: "本地离线 verifier：VERIFIED_ANCHORED · exit 0",
    issuer: "文件内容与受信锚一致；签发者身份未建立。归因仅为相关性，未测试复现。", notSame: "这两份历史证书是独立运行，不属于 RPF-46 Live 会话。",
    limits: "证据边界", limitsBody: "浏览器页校验编译进页面的摘要 pins、manifest 字段和报告事实；它本身不能读取 Git HEAD 或独立认证页面来源。下方 CLI 才检查指定提交的祖先关系和 Git blob 字节。RPF-46 是一个会话的有限机制证据：报告不是原始 Provider 对话或完整离线可验的 Live Witness，也没有外部锚；RPF-46 Witness 仅本机留存，本独立 checkout 不提供下载。L1/L2 不建立因果归因、复现或统计优势。",
    viewEvent: "查看事件事实", facts: "本事件记录的字段", choose: "选择时间线事件查看摘要事实。", selectedMissing: "事件 ID 不在已验证摘要中。",
    missing: "本页失败关闭。核对提交分支和来源文件后再试。", verifier: "独立复核命令", noProvider: "本页不访问 Gateway、无 Provider 请求、无状态写入。",
  },
  "en-US": {
    badge: "RECORDED · committed research summary", title: "EffectWitness | Evidence-driven controlled experiments", subtitle: "Review two recorded choices and independent business verification. This page reads committed files and never starts an experiment.",
    link: "Back to the controlled lab", source: "Evidence source", sourceBranch: "Source branch", commit: "Source commit", session: "Session", created: "UTC+08 time",
    requests: "Model requests", requestInfo: "DeepSeek HTTP 200 × 2", trials: "Fresh controlled trials", trialInfo: "One order trial per round", tokens: "Reported tokens", tokensInfo: "From the committed summary", cost: "Estimated cost ceiling", costInfo: "Historical estimate; no new spend", timeline: "Validated feedback before next choice", outcomes: "Independent business effects",
    round: "Round", before: "Before", after: "After", normal: "Round 1: model selected normal; no fault was planned.", feedback: "Round 1 feedback was validated by the independent Authority / Oracle.",
    input: "The second request input contains the same feedback hash.", lost: "Round 2: model selected response-lost; the fault triggered.", reconciled: "The unique committed receipt was reconciled from an independent readback.", ended: "The recorded session ended.",
    contract: "Refund contract: satisfied in both rounds", contractValue: "PAID → REFUNDED · CONTRACT_SATISFIED_IN_RUN", fault: "Round 2 fault: triggered and reconciled", faultValue: "TRIGGERED · RECONCILED_COMMITTED", receipt: "Receipts: one per round", receiptValue: "One in each round", violations: "Contract violations: none reported", violationValue: "violated_rules is empty in both rounds",
    chain: "Round 1 feedback precedes the round 2 choice; hashes match", rounds: "Before / after business state", recorded: "Read-only RECORDED", unavailable: "A recorded source could not be verified. The demo is hidden; no fixture fallback is used.",
    checking: "Verifying embedded-source SHA-256 pins, manifest identity and report structure…", verified: "Embedded-source pins and identity fields passed. The offline command below checks Git ancestry and committed blob bytes.",
    historical: "Separate historical Witness samples", order: "RPF-43 · controlled refund sample", ops: "RPF-44 · controlled operations sample", anchored: "Local offline verifier: VERIFIED_ANCHORED · exit 0",
    issuer: "File bytes match the trusted anchor; issuer identity is not established. Attribution is correlational and reproduction was not tested.", notSame: "These historical certificates are separate runs, not part of the RPF-46 Live session.",
    limits: "Evidence limits", limitsBody: "The browser page checks source pins compiled into the page, manifest fields and report facts; it cannot read Git HEAD or independently authenticate its own source. The CLI below checks the pinned commit's ancestry and committed Git blob bytes. RPF-46 is limited mechanism evidence from one session: the report is not the raw Provider conversation or a complete offline-verifiable Live Witness and has no external anchor. The RPF-46 Witness remains local-only and is not downloadable from this independent checkout. L1/L2 do not establish causal attribution, reproduction or statistical advantage.",
    viewEvent: "View event facts", facts: "Recorded event fields", choose: "Choose a timeline event to inspect its summary facts.", selectedMissing: "The event ID is not present in the verified summary.",
    missing: "This page failed closed. Check the source branch and files before retrying.", verifier: "Independent verification command", noProvider: "This page does not access the Gateway, call a Provider or write experiment state.",
  },
} as const;

function eventTitle(event: RecordedEvent, locale: "zh-CN" | "en-US", c: typeof copy["zh-CN"] | typeof copy["en-US"]): string {
  const round = event.facts.round;
  if (event.type === "PROVIDER_SELECTION_ACCEPTED" && round === 1) return c.normal;
  if (event.type === "AUTHORITY_FEEDBACK_VALIDATED" && round === 1) return c.feedback;
  if (event.type === "PROVIDER_INPUT_FROZEN" && round === 2) return c.input;
  if (event.type === "PROVIDER_SELECTION_ACCEPTED" && round === 2) return c.lost;
  if (event.type === "AUTHORITY_FEEDBACK_VALIDATED" && round === 2) return c.reconciled;
  if (event.type === "SESSION_STOPPED") return c.ended;
  return `${locale === "zh-CN" ? "记录事件" : "Recorded event"}: ${event.type}`;
}

function show(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined) return "—";
  return JSON.stringify(value);
}

export function RecordedPage({ path, search }: { path: string; search: string }) {
  const { locale } = useI18n();
  const c = copy[locale];
  const validPath = path === "/effectwitness/recorded";
  const [status, setStatus] = useState<"CHECKING" | "VERIFIED" | "UNAVAILABLE">("CHECKING");
  const [evidence, setEvidence] = useState<RecordedEvidence | null>(null);
  useEffect(() => {
    let current = true;
    setStatus("CHECKING");
    setEvidence(null);
    void validateRecordedPayload().then((result) => {
      if (current) { setEvidence(result); setStatus("VERIFIED"); }
    }).catch(() => {
      if (current) { setEvidence(null); setStatus("UNAVAILABLE"); }
    });
    return () => { current = false; };
  }, []);

  const params = useMemo(() => new URLSearchParams(search), [search]);
  const selectedEventId = params.get("event");
  const selectedEvent = evidence?.report.feedback_link_events.find((event) => event.event_id === selectedEventId);
  const goToEvent = (event: RecordedEvent) => {
    const target = `${path}?event=${encodeURIComponent(event.event_id)}`;
    navigate(target);
  };
  if (!validPath) return <AppShell recorded><section className="ew-lab ew-recorded"><div className="ew-recorded-error" role="alert">INVALID_RECORDED_ROUTE</div></section></AppShell>;

  return <AppShell recorded><section className="ew-lab ew-recorded">
    <header className="ew-heading">
      <span className="ew-source ew-recorded-badge">{c.badge}</span>
      <h1>{c.title}</h1>
      <p>{c.subtitle}</p>
      <p><a href="/effectwitness" onClick={(event) => { event.preventDefault(); navigate("/effectwitness"); }}>{c.link}</a></p>
    </header>
    {status === "CHECKING" && <p className="ew-recorded-status" role="status" aria-live="polite">{c.checking}</p>}
    {(status === "UNAVAILABLE" || !evidence) && status !== "CHECKING" && <div className="ew-recorded-error" role="alert"><strong>UNAVAILABLE / INCONCLUSIVE</strong><p>{c.unavailable}</p></div>}
    {evidence && status === "VERIFIED" && <>
      <div className="ew-recorded-sourcebar" aria-label={c.source}>
        <span><small>{c.source}</small><strong>RECORDED_RPF46_SUMMARY</strong></span>
        <span><small>{c.sourceBranch}</small><code>codex/rpf-46-live-pge-lab</code></span>
        <span><small>{c.commit}</small><code>{evidence.manifest.source_commit}</code></span>
        <span><small>{c.session}</small><code>{evidence.report.session_id}</code></span>
        <span><small>{c.created}</small><code>{evidence.report.created_at} — {evidence.report.completed_at}</code></span>
      </div>
      <p className="ew-recorded-status" role="status">{c.verified} {c.noProvider}</p>
      <div className="ew-recorded-metrics">
        <section className="ew-panel"><small>{c.requests}</small><strong>{evidence.report.usage.provider_requests}</strong><span>{c.requestInfo}</span></section>
        <section className="ew-panel"><small>{c.trials}</small><strong>{evidence.report.usage.physical_trials_completed}</strong><span>{c.trialInfo}</span></section>
        <section className="ew-panel"><small>{c.tokens}</small><strong>{evidence.report.usage.tokens.toLocaleString(locale)}</strong><span>{c.tokensInfo}</span></section>
        <section className="ew-panel"><small>{c.cost}</small><strong>¥{evidence.report.usage.estimated_cost_cny_upper.toFixed(6)}</strong><span>{c.costInfo}</span></section>
      </div>
      <div className="ew-recorded-grid">
        <section className="ew-panel">
          <h2>{c.timeline}</h2>
          <ol className="ew-recorded-events">
            {evidence.report.feedback_link_events.map((event) => <li key={event.event_id}>
              <a aria-current={selectedEventId === event.event_id ? "step" : undefined} href={`${path}?event=${encodeURIComponent(event.event_id)}`} onClick={(e) => { e.preventDefault(); goToEvent(event); }}>
                <span>{String(event.seq).padStart(2, "0")}</span><strong>{eventTitle(event, locale, c)}</strong><small>{event.type} · {event.observed_at}</small>
              </a>
            </li>)}
          </ol>
        </section>
        <section className="ew-panel">
          <h2>{c.outcomes}</h2>
          <div className="ew-recorded-facts">
            <p><strong>{c.contract}</strong><span>{c.contractValue}</span></p>
            <p><strong>{c.fault}</strong><span>{c.faultValue}</span></p>
            <p><strong>{c.receipt}</strong><span>{c.receiptValue}</span></p>
            <p><strong>{c.violations}</strong><span>{c.violationValue}</span></p>
          </div>
          <h3>{c.chain}</h3>
          <code>{evidence.report.trials[0].feedback_sha256}</code>
          <table className="ew-diff"><thead><tr><th>{c.round}</th><th>{c.before}</th><th>{c.after}</th></tr></thead>
            <tbody>{evidence.report.trials.map((trial) => <tr key={trial.round}><th>{trial.round} · {trial.candidate_id}</th><td>PAID / CNY 25.00</td><td>REFUNDED / CNY 25.00 · 1 receipt</td></tr>)}</tbody>
          </table>
        </section>
      </div>
      {selectedEventId && <section className="ew-panel ew-recorded-event-detail" aria-live="polite">
        <h2>{c.viewEvent}</h2>
        {selectedEvent ? <><strong>{selectedEvent.seq} · {selectedEvent.type}</strong><p>{eventTitle(selectedEvent, locale, c)}</p><h3>{c.facts}</h3><pre>{JSON.stringify(selectedEvent.facts, null, 2)}</pre></> : <p role="alert">{c.selectedMissing}</p>}
      </section>}
      {!selectedEventId && <p className="ew-recorded-hint">{c.choose}</p>}
      <section className="ew-panel">
        <h2>{c.historical}</h2><p className="ew-recorded-hint">{c.notSame}</p>
        <div className="ew-recorded-samples">
          <article><small>HISTORICAL_WITNESS_SAMPLE</small><h3>{c.order}</h3><strong>{evidence.orderWitness.schema_version}</strong><code>SHA-256 {"ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e"}</code><p>{c.anchored}</p><p>{c.issuer}</p></article>
          <article><small>HISTORICAL_WITNESS_SAMPLE</small><h3>{c.ops}</h3><strong>{evidence.opsWitness.schema_version}</strong><code>SHA-256 {"21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873"}</code><p>{c.anchored}</p><p>{c.issuer}</p></article>
        </div>
        <h3>{c.verifier}</h3><pre>python -B spikes/rpf-47/verify_evidence.py --root .</pre>
      </section>
      <section className="ew-panel ew-recorded-limits"><h2>{c.limits}</h2><p>{c.limitsBody}</p><code>{evidence.report.trials[1].witness.status} · {evidence.report.trials[1].witness.bytes} bytes · local-only SHA {evidence.report.trials[1].witness.sha256}</code></section>
    </>}
  </section></AppShell>;
}

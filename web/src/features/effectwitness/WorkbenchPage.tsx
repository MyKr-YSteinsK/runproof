import { useEffect, useState } from "react";
import { navigate } from "../../app/navigation";
import { AppShell } from "../../components/AppShell";
import { useI18n } from "../../i18n";
import type { RecordedEvidence } from "./recordedEvidence";
import { domainFromSearch, evidenceForDomain, loadWorkbenchEvidence, workbenchHref, type Domain } from "./workbenchModel";
import "./workbench.css";

const copy = {
  "zh-CN": {
    eyebrow: "EFFECTWITNESS / 只读工作台", title: "看清行动后的真实效果", intro: "选择场景，核对证据，再进入对应实验入口。此页面不会启动实验或调用模型。",
    scenario: "01 / 选择场景", order: "订单与退款", ops: "运维配置", orderDesc: "退款响应可能在业务提交后丢失。", opsDesc: "配置写入后需要核对版本与历史。",
    expected: "EXPECTED · 预期", forbidden: "FORBIDDEN · 禁止", unknown: "UNKNOWN · 未知结果",
    orderExpected: "退款合同满足；独立读回唯一收据。", opsExpected: "读回目标版本和配置历史。",
    orderForbidden: "重复退款或未经确认的再次写入。", opsForbidden: "写入超出授权范围或掩盖版本差异。",
    unknownText: "保留不确定性并只读对账；不要盲目重试写入。更强的零新 Provider 预约约束仍待验收。",
    modes: "02 / 选择证据与执行方式", recorded: "已记录研究", local: "本机受控捕获", live: "Live Explorer", cross: "跨域研究",
    recDetail: "订单研究与分离的证书样本 · 只读", localDetail: "订单 / 运维 · 需 Gateway · 受控业务写入", liveDetail: "仅订单 · 需 Gateway 和额度 · 模型调用收费", crossDetail: "订单 / 配置 · 需 Gateway · 历史与实时分开",
    open: "打开入口", availability: "额度和 Gateway 状态未在工作台查询；请在目标页面核实。", trace: "03 / 调查已记录的事实",
    checking: "正在校验历史来源…", unavailable: "UNAVAILABLE · 来源校验失败，已隐藏所有历史主张。", source: "来源身份", session: "会话", select: "选择 → 反馈 → 下一选择", inspect: "查看事件",
    facts: "业务状态差异与 Oracle", round: "轮次", outcome: "验证结果", fault: "故障状态", before: "之前", after: "之后",
    limits: "04 / Witness 与边界", separate: "独立历史证书样本，与上述研究会话不是同一次运行。", issuer: "签发者身份尚未建立；哈希和本地校验不是第三方签名。",
    opsOnly: "此场景展示单独的运维 Witness 样本；没有与订单研究会话合并的配置时间线或状态差异。", witness: "历史 Witness", detail: "查看来源与离线复核", planned: "计划", triggered: "触发", observed: "观测", exposed: "Agent 可见", notRecorded: "摘要未记录", yes: "是", no: "否",
    states: "结果分类：CONTRACT_SATISFIED / VIOLATION_CONFIRMED / INCONCLUSIVE 是业务结论；ERROR 与会话状态是平台或记账状态。",
  },
  "en-US": {
    eyebrow: "EFFECTWITNESS / READ-ONLY WORKBENCH", title: "See what an action actually changed", intro: "Choose a scenario, inspect evidence, then open the matching lab. This page never starts an experiment or calls a model.",
    scenario: "01 / Choose a scenario", order: "Orders & refunds", ops: "Operations configuration", orderDesc: "A refund response may be lost after the business commit.", opsDesc: "A configuration write needs version and history readback.",
    expected: "EXPECTED", forbidden: "FORBIDDEN", unknown: "UNKNOWN OUTCOME",
    orderExpected: "Satisfy the refund contract; read back the unique receipt.", opsExpected: "Read back the target version and configuration history.",
    orderForbidden: "Duplicate refunds or an unconfirmed second write.", opsForbidden: "Out-of-scope writes or obscuring version differences.",
    unknownText: "Preserve uncertainty and reconcile read-only; never blindly retry writes. The stronger zero-new-provider-reservation constraint awaits acceptance.",
    modes: "02 / Choose evidence or execution", recorded: "Recorded research", local: "Local controlled capture", live: "Live Explorer", cross: "Cross-domain research",
    recDetail: "Order research and separate certificate samples · read-only", localDetail: "Order / ops · Gateway required · controlled business writes", liveDetail: "Order only · Gateway and quota required · paid model calls", crossDetail: "Order / config · Gateway required · historical and live distinct",
    open: "Open", availability: "Gateway and quota are not checked on this page; verify them in the destination.", trace: "03 / Investigate recorded facts",
    checking: "Validating historical sources…", unavailable: "UNAVAILABLE · Source validation failed; historical claims are hidden.", source: "Source identity", session: "Session", select: "Selection → feedback → next selection", inspect: "Inspect event",
    facts: "Business state diff & Oracle", round: "Round", outcome: "Verified result", fault: "Fault state", before: "Before", after: "After",
    limits: "04 / Witness & limitations", separate: "Separate historical certificate sample, not part of the research session above.", issuer: "Issuer authenticity is not established; hashes and local checks are not third-party signatures.",
    opsOnly: "This is a separate operations Witness sample; no configuration timeline or state diff is merged into the order session.", witness: "Historical Witness", detail: "View sources and offline verification", planned: "Planned", triggered: "Triggered", observed: "Observed", exposed: "Agent exposed", notRecorded: "Not recorded in summary", yes: "Yes", no: "No",
    states: "Outcome classes: CONTRACT_SATISFIED / VIOLATION_CONFIRMED / INCONCLUSIVE are business results; ERROR and session status are platform or bookkeeping states.",
  },
} as const;

function Link({ href, children }: { href: string; children: React.ReactNode }) {
  return <a href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>{children}</a>;
}

function display(value: unknown): string {
  if (value === undefined || value === null) return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function recordedFlag(fault: unknown, key: string, yes: string, no: string, missing: string): string {
  if (!fault || typeof fault !== "object") return missing;
  const value = (fault as Record<string, unknown>)[key];
  return value === true ? yes : value === false ? no : missing;
}

export function WorkbenchPage({ search }: { search: string }) {
  const { locale } = useI18n();
  const c = copy[locale];
  const domain = domainFromSearch(search);
  const [state, setState] = useState<{ status: "CHECKING" | "VERIFIED" | "UNAVAILABLE"; evidence?: RecordedEvidence }>({ status: "CHECKING" });
  useEffect(() => {
    let active = true;
    loadWorkbenchEvidence().then((evidence) => { if (active) setState({ status: "VERIFIED", evidence }); })
      .catch(() => { if (active) setState({ status: "UNAVAILABLE" }); });
    return () => { active = false; };
  }, []);
  const projection = state.evidence ? evidenceForDomain(state.evidence, domain) : null;
  const modes = [
    { name: c.recorded, detail: c.recDetail, badge: "RECORDED", href: "/effectwitness/recorded" },
    { name: c.local, detail: c.localDetail, badge: "LOCAL CONTROLLED", href: "/effectwitness" },
    { name: c.live, detail: c.liveDetail, badge: "LIVE PROVIDER", href: "/effectwitness/explorations" },
    { name: c.cross, detail: c.crossDetail, badge: "REVIEWED / LIVE", href: "/effectwitness/cross-domain" },
  ];
  return <AppShell recorded><div className="ew-workbench">
    <header className="wb-header"><div><span className="wb-eyebrow">{c.eyebrow}</span><h1>{c.title}</h1><p>{c.intro}</p></div><span className="wb-badge">RECORDED · READ ONLY</span></header>
    <section aria-labelledby="wb-scenario"><h2 id="wb-scenario">{c.scenario}</h2>
      <div className="wb-domain" role="group" aria-label={c.scenario}>{(["order", "ops"] as Domain[]).map((item) => <Link key={item} href={workbenchHref(search, item)}><span aria-current={domain === item ? "true" : undefined}><strong>{item === "order" ? c.order : c.ops}</strong><small>{item === "order" ? c.orderDesc : c.opsDesc}</small></span></Link>)}</div>
      <div className="wb-contracts"><p><b>{c.expected}</b>{domain === "order" ? c.orderExpected : c.opsExpected}</p><p><b>{c.forbidden}</b>{domain === "order" ? c.orderForbidden : c.opsForbidden}</p><p><b>{c.unknown}</b>{c.unknownText}</p></div>
    </section>
    <section aria-labelledby="wb-modes"><h2 id="wb-modes">{c.modes}</h2><div className="wb-modes">{modes.map((mode) => <article key={mode.badge}><span className="wb-tag">{mode.badge}</span><h3>{mode.name}</h3><p>{mode.detail}</p><Link href={mode.href}>{c.open} →</Link></article>)}</div><p className="wb-note">UNAVAILABLE / NOT CHECKED · {c.availability}</p></section>
    <section aria-labelledby="wb-trace"><h2 id="wb-trace">{c.trace}</h2>
      {state.status === "CHECKING" && <p role="status">{c.checking}</p>}
      {state.status === "UNAVAILABLE" && <p className="wb-alert" role="alert">{c.unavailable}</p>}
      {state.evidence && projection && <>
        {domain === "order" && new URLSearchParams(search).get("event") && !projection.events.some((event) => event.event_id === new URLSearchParams(search).get("event")) && <p className="wb-alert" role="alert">{locale === "zh-CN" ? "该事件不在已验证来源中。" : "This event is not present in the verified source."}</p>}
        <div className="wb-source"><span>{projection.kind}</span><span>{c.source}: <code>{state.evidence.manifest.source_commit}</code></span>{domain === "order" && <span>{c.session}: <code>{state.evidence.report.session_id}</code></span>}</div>
        {domain === "ops" ? <p className="wb-note">{c.opsOnly}</p> : <div className="wb-investigation">
          <article><h3>{c.select}</h3><ol className="wb-events">{projection.events.map((event) => <li key={event.event_id} aria-current={new URLSearchParams(search).get("event") === event.event_id ? "step" : undefined}><span>{String(event.seq).padStart(2, "0")}</span><div><strong>{event.type}</strong><small>{event.observed_at} · UTC</small><Link href={`/effectwitness/recorded?from=workbench&domain=order&event=${encodeURIComponent(event.event_id)}`}>{c.inspect} →</Link></div></li>)}</ol></article>
          <article><h3>{c.facts}</h3>{projection.trials.map((trial) => <div className="wb-trial" key={trial.round}><h4>{c.round} {trial.round} · {trial.candidate_id}</h4><p>{c.outcome}: <strong>{trial.effect.contract_outcome}</strong></p><p>{c.fault}: {c.planned}: {recordedFlag(trial.fault, "planned", c.yes, c.no, c.notRecorded)} · {c.triggered}: {recordedFlag(trial.fault, "triggered", c.yes, c.no, c.notRecorded)} · {c.observed}: {recordedFlag(trial.fault, "observed", c.yes, c.no, c.notRecorded)} · {c.exposed}: {c.notRecorded}</p><dl>{Object.entries(trial.effect.state_diff).map(([key, diff]) => <div key={key}><dt>{key}</dt><dd>{c.before}: {display(diff.before)} → {c.after}: {display(diff.after)}</dd></div>)}</dl></div>)}<p className="wb-note">{c.states}</p></article>
        </div>}
      </>}
    </section>
    {projection && <section className="wb-witness" aria-labelledby="wb-witness"><h2 id="wb-witness">{c.limits}</h2><strong>{c.witness} · {projection.witness.schema_version}</strong><p>{c.separate} {c.issuer}</p><Link href="/effectwitness/recorded">{c.detail} →</Link></section>}
  </div></AppShell>;
}

import { AppShell } from "../../components/AppShell";
import { StatusTag } from "../../components/StatusTag";
import { navigate } from "../../app/navigation";
import { DATA_SOURCE_FOOTNOTE } from "../../app/dataSource";
import type { JsonRecord } from "../../data/artifacts";
import type { CanonicalSnapshot } from "../../data/canonicalSnapshot";
import { goldenDemoProfile, goldenDemoRefId } from "../../data/goldenDemo";
import { selectGoldenDemoOverview } from "./overviewModel";
import type { StatisticalEvaluation } from "../../data/statistical";

const objectValue = (value: unknown): JsonRecord | null => value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : null;
const valueAt = (value: unknown, key: string): unknown => objectValue(value)?.[key];
const displayValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};
const shortId = (value: unknown, length = 18): string => {
  const text = displayValue(value);
  return text.length > length ? `${text.slice(0, length)}…` : text;
};
const statisticalStatusTone = (status: string): "success" | "fault" | "error" | "neutral" | "review" => {
  if (status === "ELIGIBLE" || status === "PASS" || status === "IMPROVED") return "success";
  if (status === "BLOCKED" || status === "REGRESSED") return "fault";
  if (status === "REVIEW_REQUIRED" || status === "INCONCLUSIVE" || status === "OBSERVED_FLAKY" || status === "NO_CLEAR_DIFFERENCE") return "review";
  return "neutral";
};
const statisticalPercent = (value: unknown, digits = 1): string => typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : "—";
const statisticalQuality = (evaluation: StatisticalEvaluation): JsonRecord => objectValue(evaluation.statisticalEvaluation.summary) || {};

export function GoldenDemoOverview({ snapshot }: { snapshot: CanonicalSnapshot }) {
  const model = selectGoldenDemoOverview(snapshot);
  const candidateMeta = model.candidateEvaluation?.evaluation;
  const decisionMeta = model.candidateDecision?.releaseDecision;
  const failureMeta = model.flagshipFailureCase?.failureCase;
  const clusterMeta = model.flagshipCluster?.cluster;
  const bisectMeta = model.bisect?.bisect;
  const decisionHref = `/release-decisions/${encodeURIComponent(goldenDemoRefId("release.decision"))}`;
  const candidateHref = `/evaluations/${encodeURIComponent(goldenDemoProfile.selected.candidate_evaluation)}`;
  const clusterHref = `/failure-intelligence/clusters/${encodeURIComponent(goldenDemoRefId("failure.flagship_cluster"))}`;
  const bisectHref = `/version-bisects/${encodeURIComponent(goldenDemoRefId("version.bisect"))}`;
  const failureHrefValue = `/failures/${encodeURIComponent(goldenDemoRefId("failure.flagship_case"))}`;
  const regressionHrefValue = `/regressions/${encodeURIComponent(goldenDemoRefId("regression.flagship"))}`;
  const comparisonHref = `/statistical-comparisons/${encodeURIComponent(goldenDemoRefId("statistical.comparison"))}`;
  const runHrefValue = `/runs/${encodeURIComponent(goldenDemoRefId("durable.response_lost_run"))}`;
  const comparisonClassification = model.comparisonClassification || "UNAVAILABLE";
  const familySignature = model.familySignature ?? "UNAVAILABLE";
  const firstDivergence = model.firstDivergence ?? "UNAVAILABLE";
  const firstBadCandidate = model.firstBadCandidate ?? "UNAVAILABLE";
  const unknownEffectCount = model.unknownEffectCount ?? "UNAVAILABLE";

  return (
    <AppShell overview>
      <div className="page-header index-header golden-demo-header">
        <div><span className="eyebrow">RPF-19 · GOLDEN DEMO</span><h1>Reliability evidence you can follow.</h1><p className="lede">A compact, interview-ready path from two explicit Agents through durable evidence, failure intelligence, regression coverage, statistical reliability, and a decision-only quality gate.</p></div>
        <div className="corpus-note golden-demo-identity"><span className="section-label">DEMO PROFILE</span><strong>{goldenDemoProfile.demo.demo_id} · v{goldenDemoProfile.demo.version}</strong><span className="mono">source {shortId(goldenDemoProfile.demo.source_commit, 18)}</span></div>
      </div>
      <section className="corpus-boundary golden-demo-boundary" aria-label="Golden Demo boundary"><span className="boundary-mark">R</span><p><strong>Reviewed evidence only.</strong> This demo is seeded from the formal Control Plane API and immutable reviewed artifacts. It requires no Provider, cloud resource, release, deployment, or live rerun.</p><span className="schema-chip">{DATA_SOURCE_FOOTNOTE}</span></section>
      <section className="golden-story-track" aria-label="Golden Demo investigation path">
        <a className="golden-story-card active" href={candidateHref} onClick={(event) => { event.preventDefault(); navigate(candidateHref); }}><span>01 · CANDIDATE</span><strong>{displayValue(candidateMeta?.evaluationId || "UNAVAILABLE")}</strong><small>{displayValue(candidateMeta?.evaluationStatus || "UNAVAILABLE")}</small></a>
        <a className="golden-story-card" href={comparisonHref} onClick={(event) => { event.preventDefault(); navigate(comparisonHref); }}><span>02 · EVIDENCE</span><strong>{comparisonClassification}</strong><small>baseline ↔ candidate intervals</small></a>
        <a className="golden-story-card" href={clusterHref} onClick={(event) => { event.preventDefault(); navigate(clusterHref); }}><span>03 · FAILURE</span><strong>{shortId(String(familySignature), 24)}</strong><small>first divergence is inspectable</small></a>
        <a className="golden-story-card" href={bisectHref} onClick={(event) => { event.preventDefault(); navigate(bisectHref); }}><span>04 · REGRESSION</span><strong>{shortId(String(firstBadCandidate), 24)}</strong><small>known-bad boundary located</small></a>
        <a className="golden-story-card" href={decisionHref} onClick={(event) => { event.preventDefault(); navigate(decisionHref); }}><span>05 · GATE</span><strong>{displayValue(decisionMeta?.decisionStatus || "UNAVAILABLE")}</strong><small>decision-only · no release</small></a>
      </section>
      <section className="golden-overview-grid" aria-label="Golden Demo identity and decision">
        <div className="panel golden-agents-panel"><div className="panel-heading"><div><span className="eyebrow">TWO EXPLICIT AGENTS</span><h2>Identity stays attached to evidence.</h2></div><span className="section-count">{goldenDemoProfile.agents.length} agents</span></div><div className="golden-agent-list">{[model.productionAgent, model.incidentAgent].map((agent, index) => agent ? <a className="golden-agent-row" key={agent.agentId} href={`/agents/${encodeURIComponent(agent.agentId)}`} onClick={(event) => { event.preventDefault(); navigate(`/agents/${encodeURIComponent(agent.agentId)}`); }}><span className={`golden-agent-mark ${index === 1 ? "incident" : ""}`}>{index === 1 ? "IR" : "PC"}</span><span><strong>{agent.agentId}</strong><small>{agent.domain} · {agent.agentType}</small></span><span className="row-arrow" aria-hidden="true">→</span></a> : null)}</div><p className="golden-panel-note">The Production Change Agent and Incident Remediation Agent share a narrow integration contract; neither owns Release Authority.</p></div>
        <div className="panel golden-decision-panel"><div className="panel-heading"><div><span className="eyebrow">QUALITY DECISION</span><h2>Candidate outcome</h2></div><StatusTag status={displayValue(decisionMeta?.decisionStatus || "UNAVAILABLE")} tone={statisticalStatusTone(displayValue(decisionMeta?.decisionStatus || "UNAVAILABLE"))} /></div><div className="golden-decision-hero"><strong>{displayValue(decisionMeta?.decisionStatus || "UNAVAILABLE")}</strong><span>{displayValue(decisionMeta?.decisionSubject || "UNAVAILABLE")}</span></div><div className="golden-decision-facts"><div><span>Candidate evaluation</span><strong className="mono">{shortId(candidateMeta?.evaluationId || "UNAVAILABLE", 28)}</strong></div><div><span>Gate boundary</span><strong>Decision only</strong></div><div><span>Release executed</span><strong>{displayValue(valueAt(decisionMeta?.authorizationBoundary, "release_executed"))}</strong></div></div><a className="action-link" href={decisionHref} onClick={(event) => { event.preventDefault(); navigate(decisionHref); }}>Open full Release Decision →</a></div>
      </section>
      <section className="golden-path-grid" aria-label="Golden Demo evidence paths">
        <div className="panel golden-path-panel"><div className="panel-heading"><div><span className="eyebrow">RPF-18 · STATISTICAL RELIABILITY</span><h2>Four cohorts, four conclusions.</h2></div><a className="action-link" href="/statistical-evaluations" onClick={(event) => { event.preventDefault(); navigate("/statistical-evaluations"); }}>Open index →</a></div><div className="golden-stat-list">{model.statisticalEvaluations.map((row) => { const evaluation = row.evaluation; const meta = evaluation?.statisticalEvaluation; const status = row.decisionStatus || "UNAVAILABLE"; const quality = evaluation ? statisticalQuality(evaluation) : {}; const agentQuality = objectValue(quality.agent_quality) || {}; const href = `/statistical-evaluations/${encodeURIComponent(row.id)}`; return <a className="golden-stat-row" key={row.id} href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}><span className="golden-stat-label"><strong>{row.label}</strong><small>{row.description}</small></span><span><strong>{meta ? `${meta.validAgentTrialCount}/${meta.attemptedTrialCount}` : "UNAVAILABLE"}</strong><small>{meta ? `${statisticalPercent(agentQuality.success_rate)} pass` : "evidence unavailable"}</small></span><StatusTag status={status} tone={statisticalStatusTone(status)} /><span className="row-arrow" aria-hidden="true">→</span></a>; })}</div><p className="golden-panel-note">Denominators, Wilson intervals, evidence quality, flaky observation, and zero-tolerance rules remain visible in the drilldown.</p></div>
        <div className="panel golden-path-panel golden-failure-panel"><div className="panel-heading"><div><span className="eyebrow">RPF-17 · FAILURE INTELLIGENCE</span><h2>One failure, fully traceable.</h2></div><a className="action-link" href={clusterHref} onClick={(event) => { event.preventDefault(); navigate(clusterHref); }}>Open cluster →</a></div><div className="golden-failure-hero"><StatusTag status={displayValue(failureMeta?.currentStatus || "UNAVAILABLE")} tone={failureMeta ? "fault" : "neutral"} /><strong>{shortId(String(familySignature), 34)}</strong><span>Incident external dependency misdiagnosis</span></div><div className="golden-failure-facts"><div><span>First divergence</span><strong className="mono">{shortId(String(firstDivergence), 28)}</strong></div><div><span>Cluster level</span><strong>{displayValue(clusterMeta?.clusterLevel || "UNAVAILABLE")}</strong></div><div><span>Exact / structural</span><strong>{clusterMeta ? `${clusterMeta.exactSignatureRefs.length} / ${clusterMeta.memberRefs.length}` : "UNAVAILABLE"}</strong></div><div><span>Regression coverage</span><strong>{clusterMeta ? (clusterMeta.regressionCoverage.length ? "covered" : "inspect") : "UNAVAILABLE"}</strong></div></div><div className="golden-inline-links"><a href={failureHrefValue} onClick={(event) => { event.preventDefault(); navigate(failureHrefValue); }}>Failure Case</a><a href={bisectHref} onClick={(event) => { event.preventDefault(); navigate(bisectHref); }}>Version bisect</a><a href={regressionHrefValue} onClick={(event) => { event.preventDefault(); navigate(regressionHrefValue); }}>Regression</a></div></div>
        <div className="panel golden-path-panel golden-durable-panel"><div className="panel-heading"><div><span className="eyebrow">RPF-14 · DURABLE EXECUTION</span><h2>Unknown outcome, then reconcile.</h2></div><a className="action-link" href={runHrefValue} onClick={(event) => { event.preventDefault(); navigate(runHrefValue); }}>Open Run →</a></div><div className="golden-durable-flow"><span>side effect succeeded</span><b>→</b><span>response lost</span><b>→</b><span className="warning">UNKNOWN_OUTCOME</span><b>→</b><span>reconcile</span></div><div className="golden-durable-facts"><div><span>Run status</span><strong>{displayValue(model.unknownOutcomeRun?.outcome.status || "UNAVAILABLE")}</strong></div><div><span>Effect count</span><strong>{displayValue(unknownEffectCount)}</strong></div><div><span>Reconcile event</span><strong>{model.unknownReconcile ? "recorded" : "UNAVAILABLE"}</strong></div><div><span>Retry boundary</span><strong>blind retry prohibited</strong></div></div><a className="golden-execution-link" href="/executions" onClick={(event) => { event.preventDefault(); navigate("/executions"); }}><span>Canonical job read model</span><strong>Inspect Attempts / Operations / Evidence →</strong></a></div>
      </section>
      <section className="golden-claim-strip" aria-label="Golden Demo evidence claims"><div><span className="eyebrow">FACTS</span><strong>Two Agent identities</strong><p>Each link opens the same verified Agent-bearing corpus used by the rest of the product.</p></div><div><span className="eyebrow">VERIFIED</span><strong>{goldenDemoProfile.reviewed_artifacts.length} immutable refs</strong><p>Profile hashes bind the demo to reviewed Run, Failure, Regression, Evaluation, Gate, and Decision artifacts.</p></div><div><span className="eyebrow">BOUNDARY</span><strong>No automatic action</strong><p>ELIGIBLE is a quality decision, not a release, deploy, or production authorization.</p></div></section>
      <footer className="page-footnote"><span>{goldenDemoProfile.demo.demo_id} · profile v{goldenDemoProfile.demo.version} · source {shortId(goldenDemoProfile.demo.source_commit, 20)}</span><span>Read-only overview · formal API · no live Agent or release action</span></footer>
    </AppShell>
  );
}

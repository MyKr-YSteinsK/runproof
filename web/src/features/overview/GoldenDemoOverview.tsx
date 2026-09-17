import { AppShell } from "../../components/AppShell";
import { StatusTag } from "../../components/StatusTag";
import { navigate } from "../../app/navigation";
import { DATA_SOURCE_MODE } from "../../app/dataSource";
import type { JsonRecord } from "../../data/artifacts";
import type { CanonicalSnapshot } from "../../data/canonicalSnapshot";
import { goldenDemoProfile, goldenDemoRefId } from "../../data/goldenDemo";
import { selectGoldenDemoOverview } from "./overviewModel";
import type { StatisticalEvaluation } from "../../data/statistical";
import { useI18n } from "../../i18n";

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
const statisticalQuality = (evaluation: StatisticalEvaluation): JsonRecord => objectValue(evaluation.statisticalEvaluation.summary) || {};

export function GoldenDemoOverview({ snapshot }: { snapshot: CanonicalSnapshot }) {
  const { t, formatPercent } = useI18n();
  const model = selectGoldenDemoOverview(snapshot);
  const candidateMeta = model.candidateEvaluation?.evaluation;
  const decisionMeta = model.candidateDecision?.releaseDecision;
  const failureMeta = model.flagshipFailureCase?.failureCase;
  const clusterMeta = model.flagshipCluster?.cluster;
  const decisionHref = `/release-decisions/${encodeURIComponent(goldenDemoRefId("release.decision"))}`;
  const candidateHref = `/evaluations/${encodeURIComponent(goldenDemoProfile.selected.candidate_evaluation)}`;
  const clusterHref = `/failure-intelligence/clusters/${encodeURIComponent(goldenDemoRefId("failure.flagship_cluster"))}`;
  const bisectHref = `/version-bisects/${encodeURIComponent(goldenDemoRefId("version.bisect"))}`;
  const failureHrefValue = `/failures/${encodeURIComponent(goldenDemoRefId("failure.flagship_case"))}`;
  const regressionHrefValue = `/regressions/${encodeURIComponent(goldenDemoRefId("regression.flagship"))}`;
  const comparisonHref = `/statistical-comparisons/${encodeURIComponent(goldenDemoRefId("statistical.comparison"))}`;
  const runHrefValue = `/runs/${encodeURIComponent(goldenDemoRefId("durable.response_lost_run"))}`;
  const show = (value: unknown): string => typeof value === "boolean" ? (value ? t("common.yes") : t("common.no")) : displayValue(value);
  const dataSource = DATA_SOURCE_MODE === "api" ? t("common.apiVerifiedArtifact") : t("common.fixtureArtifact");
  const comparisonClassification = model.comparisonClassification || "UNAVAILABLE";
  const familySignature = model.familySignature ?? "UNAVAILABLE";
  const firstDivergence = model.firstDivergence ?? "UNAVAILABLE";
  const firstBadCandidate = model.firstBadCandidate ?? "UNAVAILABLE";
  const unknownEffectCount = model.unknownEffectCount ?? "UNAVAILABLE";
  const cohortCopy: Record<string, [string, string]> = {
    stable: [t("overview.cohortStable"), t("overview.cohortStableDescription")],
    flaky: [t("overview.cohortFlaky"), t("overview.cohortFlakyDescription")],
    safety: [t("overview.cohortSafety"), t("overview.cohortSafetyDescription")],
    "evidence-poor": [t("overview.cohortEvidencePoor"), t("overview.cohortEvidencePoorDescription")],
  };

  return (
    <AppShell overview>
      <div className="page-header index-header golden-demo-header">
        <div><span className="eyebrow">{t("overview.eyebrow")}</span><h1>{t("overview.title")}</h1><p className="lede">{t("overview.lede")}</p></div>
        <div className="corpus-note golden-demo-identity"><span className="section-label">{t("overview.demoProfile")}</span><strong>{goldenDemoProfile.demo.demo_id} · v{goldenDemoProfile.demo.version}</strong><span className="mono">{t("overview.source")} {shortId(goldenDemoProfile.demo.source_commit, 18)}</span></div>
      </div>
      <section className="corpus-boundary golden-demo-boundary" aria-label={t("overview.boundaryLabel")}><span className="boundary-mark">R</span><p><strong>{t("overview.evidenceOnly")}</strong> {t("common.formalApiImmutableArtifacts")} {t("common.noProviderCloudReleaseRerun")}</p><span className="schema-chip">{dataSource}</span></section>
      <section className="golden-story-track" aria-label={t("overview.storyPath")}>
        <a className="golden-story-card active" href={candidateHref} onClick={(event) => { event.preventDefault(); navigate(candidateHref); }}><span>01 · {t("overview.candidate")}</span><strong>{displayValue(candidateMeta?.evaluationId || "UNAVAILABLE")}</strong><small>{displayValue(candidateMeta?.evaluationStatus || "UNAVAILABLE")}</small></a>
        <a className="golden-story-card" href={comparisonHref} onClick={(event) => { event.preventDefault(); navigate(comparisonHref); }}><span>02 · {t("overview.evidence")}</span><strong>{comparisonClassification}</strong><small>{t("overview.baselineCandidateIntervals")}</small></a>
        <a className="golden-story-card" href={clusterHref} onClick={(event) => { event.preventDefault(); navigate(clusterHref); }}><span>03 · {t("overview.failure")}</span><strong>{shortId(String(familySignature), 24)}</strong><small>{t("overview.firstDivergenceInspectable")}</small></a>
        <a className="golden-story-card" href={bisectHref} onClick={(event) => { event.preventDefault(); navigate(bisectHref); }}><span>04 · {t("overview.regression")}</span><strong>{shortId(String(firstBadCandidate), 24)}</strong><small>{t("overview.knownBadBoundary")}</small></a>
        <a className="golden-story-card" href={decisionHref} onClick={(event) => { event.preventDefault(); navigate(decisionHref); }}><span>05 · {t("overview.gate")}</span><strong>{displayValue(decisionMeta?.decisionStatus || "UNAVAILABLE")}</strong><small>{t("overview.decisionOnlyNoRelease")}</small></a>
      </section>
      <section className="golden-overview-grid" aria-label={t("overview.identityDecision")}>
        <div className="panel golden-agents-panel"><div className="panel-heading"><div><span className="eyebrow">{t("overview.twoExplicitAgents")}</span><h2>{t("overview.identityAttached")}</h2></div><span className="section-count">{t("overview.identityCount", { count: goldenDemoProfile.agents.length })}</span></div><div className="golden-agent-list">{[model.productionAgent, model.incidentAgent].map((agent, index) => agent ? <a className="golden-agent-row" key={agent.agentId} href={`/agents/${encodeURIComponent(agent.agentId)}`} onClick={(event) => { event.preventDefault(); navigate(`/agents/${encodeURIComponent(agent.agentId)}`); }}><span className={`golden-agent-mark ${index === 1 ? "incident" : ""}`}>{index === 1 ? "IR" : "PC"}</span><span><strong>{agent.agentId}</strong><small>{agent.domain} · {agent.agentType}</small></span><span className="row-arrow" aria-hidden="true">→</span></a> : null)}</div><p className="golden-panel-note">{t("overview.agentContractNote")}</p></div>
        <div className="panel golden-decision-panel"><div className="panel-heading"><div><span className="eyebrow">{t("overview.qualityDecision")}</span><h2>{t("overview.candidateOutcome")}</h2></div><StatusTag status={displayValue(decisionMeta?.decisionStatus || "UNAVAILABLE")} tone={statisticalStatusTone(displayValue(decisionMeta?.decisionStatus || "UNAVAILABLE"))} /></div><div className="golden-decision-hero"><strong>{displayValue(decisionMeta?.decisionStatus || "UNAVAILABLE")}</strong><span>{displayValue(decisionMeta?.decisionSubject || "UNAVAILABLE")}</span></div><div className="golden-decision-facts"><div><span>{t("overview.candidateEvaluation")}</span><strong className="mono">{shortId(candidateMeta?.evaluationId || "UNAVAILABLE", 28)}</strong></div><div><span>{t("overview.gateBoundary")}</span><strong>{t("overview.decisionOnly")}</strong></div><div><span>{t("overview.releaseExecuted")}</span><strong>{show(valueAt(decisionMeta?.authorizationBoundary, "release_executed"))}</strong></div></div><a className="action-link" href={decisionHref} onClick={(event) => { event.preventDefault(); navigate(decisionHref); }}>{t("overview.openFullDecision")}</a></div>
      </section>
      <section className="golden-path-grid" aria-label={t("overview.failurePath")}>
        <div className="panel golden-path-panel"><div className="panel-heading"><div><span className="eyebrow">{t("overview.statisticalReliability")}</span><h2>{t("overview.fourCohorts")}</h2></div><a className="action-link" href="/statistical-evaluations" onClick={(event) => { event.preventDefault(); navigate("/statistical-evaluations"); }}>{t("overview.openIndex")}</a></div><div className="golden-stat-list">{model.statisticalEvaluations.map((row) => { const evaluation = row.evaluation; const meta = evaluation?.statisticalEvaluation; const status = row.decisionStatus || "UNAVAILABLE"; const quality = evaluation ? statisticalQuality(evaluation) : {}; const agentQuality = objectValue(quality.agent_quality) || {}; const href = `/statistical-evaluations/${encodeURIComponent(row.id)}`; const copy = cohortCopy[row.id.replace("statistical-evaluation-rpf18-", "")] || [row.label, row.description]; return <a className="golden-stat-row" key={row.id} href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}><span className="golden-stat-label"><strong>{copy[0]}</strong><small>{copy[1]}</small></span><span><strong>{meta ? `${meta.validAgentTrialCount}/${meta.attemptedTrialCount}` : "UNAVAILABLE"}</strong><small>{meta ? `${formatPercent(agentQuality.success_rate)} ${t("overview.pass")}` : t("overview.evidenceUnavailable")}</small></span><StatusTag status={status} tone={statisticalStatusTone(status)} /><span className="row-arrow" aria-hidden="true">→</span></a>; })}</div><p className="golden-panel-note">{t("overview.statisticalDrilldownNote")}</p></div>
        <div className="panel golden-path-panel golden-failure-panel"><div className="panel-heading"><div><span className="eyebrow">{t("overview.failureIntelligence")}</span><h2>{t("overview.oneFailureTraceable")}</h2></div><a className="action-link" href={clusterHref} onClick={(event) => { event.preventDefault(); navigate(clusterHref); }}>{t("overview.openCluster")}</a></div><div className="golden-failure-hero"><StatusTag status={displayValue(failureMeta?.currentStatus || "UNAVAILABLE")} tone={failureMeta ? "fault" : "neutral"} /><strong>{shortId(String(familySignature), 34)}</strong><span>{t("overview.incidentMisdiagnosis")}</span></div><div className="golden-failure-facts"><div><span>{t("overview.firstDivergence")}</span><strong className="mono">{shortId(String(firstDivergence), 28)}</strong></div><div><span>{t("overview.clusterLevel")}</span><strong>{displayValue(clusterMeta?.clusterLevel || "UNAVAILABLE")}</strong></div><div><span>{t("overview.exactStructural")}</span><strong>{clusterMeta ? `${clusterMeta.exactSignatureRefs.length} / ${clusterMeta.memberRefs.length}` : "UNAVAILABLE"}</strong></div><div><span>{t("overview.regressionCoverage")}</span><strong>{clusterMeta ? (clusterMeta.regressionCoverage.length ? t("overview.covered") : t("overview.inspect")) : "UNAVAILABLE"}</strong></div></div><div className="golden-inline-links"><a href={failureHrefValue} onClick={(event) => { event.preventDefault(); navigate(failureHrefValue); }}>{t("overview.failureCase")}</a><a href={bisectHref} onClick={(event) => { event.preventDefault(); navigate(bisectHref); }}>{t("overview.versionBisect")}</a><a href={regressionHrefValue} onClick={(event) => { event.preventDefault(); navigate(regressionHrefValue); }}>{t("common.regression")}</a></div></div>
        <div className="panel golden-path-panel golden-durable-panel"><div className="panel-heading"><div><span className="eyebrow">{t("overview.durableExecution")}</span><h2>{t("overview.unknownThenReconcile")}</h2></div><a className="action-link" href={runHrefValue} onClick={(event) => { event.preventDefault(); navigate(runHrefValue); }}>{t("overview.openRun")}</a></div><div className="golden-durable-flow"><span>{t("overview.sideEffectSucceeded")}</span><b>→</b><span>{t("overview.responseLost")}</span><b>→</b><span className="warning">UNKNOWN_OUTCOME</span><b>→</b><span>{t("overview.reconcile")}</span></div><div className="golden-durable-facts"><div><span>{t("overview.runStatus")}</span><strong>{displayValue(model.unknownOutcomeRun?.outcome.status || "UNAVAILABLE")}</strong></div><div><span>{t("overview.effectCount")}</span><strong>{displayValue(unknownEffectCount)}</strong></div><div><span>{t("overview.reconcileEvent")}</span><strong>{model.unknownReconcile ? t("overview.recorded") : "UNAVAILABLE"}</strong></div><div><span>{t("overview.retryBoundary")}</span><strong>{t("overview.blindRetryProhibited")}</strong></div></div><a className="golden-execution-link" href="/executions" onClick={(event) => { event.preventDefault(); navigate("/executions"); }}><span>{t("overview.canonicalJobModel")}</span><strong>{t("overview.inspectExecution")}</strong></a></div>
      </section>
      <section className="golden-claim-strip" aria-label={t("overview.failurePath")}><div><span className="eyebrow">{t("overview.facts")}</span><strong>{t("overview.twoAgentIdentities")}</strong><p>{t("overview.sameCorpus")}</p></div><div><span className="eyebrow">{t("overview.verified")}</span><strong>{goldenDemoProfile.reviewed_artifacts.length} {t("common.immutableRefs")}</strong><p>{t("overview.profileHashes")}</p></div><div><span className="eyebrow">{t("overview.boundary")}</span><strong>{t("overview.noAutomaticAction")}</strong><p>{t("overview.eligibleExplanation")}</p></div></section>
      <footer className="page-footnote"><span>{goldenDemoProfile.demo.demo_id} · profile v{goldenDemoProfile.demo.version} · {t("overview.source")} {shortId(goldenDemoProfile.demo.source_commit, 20)}</span><span>{t("overview.readOnlyFooter")}</span></footer>
    </AppShell>
  );
}

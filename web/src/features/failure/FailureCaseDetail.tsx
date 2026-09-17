import { AppShell } from "../../components/AppShell";
import { IdentityField } from "../../components/IdentityField";
import { StatusTag } from "../../components/StatusTag";
import { navigate } from "../../app/navigation";
import type { CanonicalSnapshot } from "../../data/canonicalSnapshot";
import type { FailureCase, JsonRecord } from "../../data/artifacts";
import { selectFailureCaseEvidence } from "./failureModel";
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
const agentDomain = (value: unknown): string => {
  const record = objectValue(value);
  const explicit = record?.agent_domain;
  if (typeof explicit === "string" && explicit) return explicit;
  return record?.agent_id === "incident-remediation-agent" || record?.agent_family === "incident-remediation-agent" ? "Incident Remediation Agent" : "Production Change Agent";
};
const agentIdentity = (value: unknown): string => {
  const record = objectValue(value);
  const id = record?.agent_id || record?.agent_family || "unknown-agent";
  const version = record?.agent_version || record?.known_bad_version;
  return `${String(id)}${version ? ` · ${String(version)}` : ""}`;
};
const agentType = (value: unknown): string => {
  const record = objectValue(value);
  return typeof record?.agent_type === "string" ? record.agent_type : agentDomain(value) === "Incident Remediation Agent" ? "INCIDENT_REMEDIATION" : "STATEFUL_CHANGE";
};
const runHref = (runId: string, eventId?: string | null): string => {
  const base = "/runs/" + encodeURIComponent(runId);
  return eventId ? base + "?event=" + encodeURIComponent(eventId) : base;
};
const regressionHref = (regressionId: string): string => "/regressions/" + encodeURIComponent(regressionId);
const clusterHref = (clusterId: string): string => "/failure-intelligence/clusters/" + encodeURIComponent(clusterId);
const intelligenceRecommendationTone = (value: unknown): "success" | "fault" | "error" | "neutral" | "review" => {
  const status = String(value || "");
  if (status === "ALREADY_COVERED") return "success";
  if (status === "PROMOTE_CANDIDATE") return "review";
  if (status === "NOT_AGENT_FAILURE") return "neutral";
  if (status === "UNSTABLE") return "error";
  return "fault";
};

export function FailureCaseDetail({ failureCase, snapshot }: { failureCase: FailureCase; snapshot: CanonicalSnapshot }) {
  const { t, term } = useI18n();
  const { sourceRun, reproductionRun, intelligence, intelligenceCluster, promotedRegression } = selectFailureCaseEvidence(snapshot, failureCase);
  const attempt = failureCase.reproductionAttempts[0];
  const failingEventId = typeof failureCase.failureObservation.failing_event_id === "string" ? failureCase.failureObservation.failing_event_id : null;
  const sourceLink = sourceRun ? runHref(sourceRun.run.runId, failingEventId) : null;
  const reproductionEventId = typeof valueAt(attempt?.run_ref, "event_id") === "string" ? String(valueAt(attempt?.run_ref, "event_id")) : null;
  const reproductionLink = reproductionRun ? runHref(reproductionRun.run.runId, reproductionEventId) : null;
  const promotedRegressionId = typeof valueAt(failureCase.promotion?.regression_ref, "regression_id") === "string" ? String(valueAt(failureCase.promotion?.regression_ref, "regression_id")) : null;
  const promoted = Boolean(promotedRegression && failureCase.promotion);
  const incident = agentDomain(failureCase.agent) === "Incident Remediation Agent";
  const incidentExpected = objectValue(failureCase.failureObservation.expected) || {};
  const incidentActual = objectValue(failureCase.failureObservation.actual) || {};
  const incidentFacts = objectValue(failureCase.failureObservation.dependency_facts) || {};
  const incidentSideEffect = objectValue(failureCase.failureObservation.remediation_side_effect) || {};
  const promotionGate = valueAt(failureCase.promotion, "gate_ref");
  const boolText = (value: unknown): string => typeof value === "boolean" ? (value ? t("common.yes") : t("common.no")) : displayValue(value);
  return (
    <AppShell detail failure>
      <div className="detail-breadcrumb"><a href="/failures" onClick={(event) => { event.preventDefault(); navigate("/failures"); }}>{t("nav.failureCases")}</a><span aria-hidden="true">/</span><span>{shortId(failureCase.failureCase.failureCaseId, 32)}</span><span className="schema-chip">rpf-failure-case-v1</span></div>
      <div className="detail-header case-detail-header"><div><span className="eyebrow">{t("failure.detailEyebrow")}</span><h1>{incident ? t("failure.externalRemediation") : t("failure.unsafePrecondition")}</h1><p className="detail-subtitle">{incident ? t("failure.externalDescription") : t("failure.agentDescription")}</p></div><div className="detail-header-status"><StatusTag status={promoted ? "PROMOTED" : "VALIDATED"} tone="success" /><span className="status-note">{promoted ? t("failure.validatedHistory") : t("failure.notRegression")}</span></div></div>
      <section className="case-identity-grid" aria-label={t("common.failureCase")}><IdentityField label={t("common.failureCase")} value={failureCase.failureCase.failureCaseId} mono /><IdentityField label={`${t("common.agent")} / domain`} value={agentIdentity(failureCase.agent)} note={agentDomain(failureCase.agent)} /><IdentityField label={`${t("common.agent")} type / contract`} value={`${agentType(failureCase.agent)} / ${displayValue(failureCase.agent.agent_contract_id || "—")}`} mono /><IdentityField label="Scenario" value={`${displayValue(failureCase.scenario.scenario_id)}@${displayValue(failureCase.scenario.scenario_version)}`} mono /><IdentityField label={term("failureAttribution")} value={displayValue(failureCase.classification.attribution)} note={displayValue(failureCase.classification.reason_code)} /><IdentityField label="Signature" value={shortId(failureCase.failureSignature.value, 28)} mono note={failureCase.failureSignature.signatureVersion} /><IdentityField label="Workflow" value={failureCase.failureCase.currentStatus} note={promoted ? "validated · promoted additively" : "validated · no promotion"} /></section>
      <section className="classification-panel case-summary-panel" aria-label={t("failure.validation")}><div className="classification-heading"><div><span className="eyebrow">{promoted ? t("failure.promotionEvidence") : t("failure.reproductionEvidence")}</span><h2>{promoted ? t("failure.promotedTitle") : t("failure.sameFailure")}</h2></div>{promoted && promotedRegression ? <a className="action-link" href={regressionHref(promotedRegression.regression.regressionId)} onClick={(event) => { event.preventDefault(); navigate(regressionHref(promotedRegression.regression.regressionId)); }}>{t("common.openRegression")}</a> : <span className="classification-badge">NOT A REGRESSION</span>}</div><p className="classification-copy">{incident ? t("failure.validationIncident") : t("failure.validationAgent")} {promoted ? t("failure.promotedNote", { at: displayValue(valueAt(failureCase.promotion, "promoted_at")) }) : t("failure.originalUnchanged")}</p><div className="classification-grid case-summary-grid"><div><span>{t("failure.violatedInvariant")}</span><strong className="mono">{displayValue(failureCase.failureObservation.violated_invariant_id)}</strong><small>{displayValue(failureCase.failureObservation.violated_invariant)}</small></div><div><span>{t("failure.expected")}</span><strong>{displayValue(incident ? valueAt(incidentExpected, "no_harmful_local_remediation_on_external_fault") : valueAt(failureCase.failureObservation.expected, "agent_observed_state_before_mutation"))}</strong><small>{incident ? t("failure.externalDependencyMustNotRemediate") : t("failure.observeBeforeMutation")}</small></div><div><span>{t("failure.actual")}</span><strong>{displayValue(incident ? valueAt(incidentActual, "harmful_local_remediation") : valueAt(failureCase.failureObservation.actual, "agent_observed_state_before_mutation"))}</strong><small>{incident ? `dependency ${displayValue(incidentActual.dependency_health)} · ${t("failure.effect")} ${displayValue(incidentActual.effect_count)}` : t("failure.unsafeIntentGuard")}</small></div>{incident && <><div><span>{t("failure.dependencyFact")}</span><strong>{displayValue(incidentFacts.dependency_health)}</strong><small>{displayValue(incidentFacts.cause_classification)}</small></div><div><span>{t("failure.sideEffect")}</span><strong>{displayValue(incidentSideEffect.harmful ? "HARMFUL" : "NOT HARMFUL")}</strong><small>{t("failure.executed")} {boolText(incidentSideEffect.executed)} · {t("failure.effect")} {displayValue(incidentSideEffect.effect_count)}</small></div></>}<div><span>{t("failure.validation")}</span><strong>{displayValue(valueAt(failureCase.validation, "status"))}</strong><small>{displayValue(valueAt(failureCase.validation, "observed_run_id"))}</small></div><div><span>{t("failure.promotion")}</span><strong>{promoted ? t("failure.promoted") : "NOT_A_REGRESSION"}</strong><small>{promoted ? `Gate ${boolText(valueAt(promotionGate, "all_passed"))} · ${shortId(promotedRegressionId, 28)}` : t("common.noPromotionLink")}</small></div></div></section>
      {intelligence && <section className="fi-case-analysis" aria-labelledby="fi-case-analysis-heading"><div className="section-heading"><div><span className="eyebrow">{t("failure.derivedAnalysis")}</span><h2 id="fi-case-analysis-heading">{t("common.failureIntelligence")}</h2></div><StatusTag status={String(valueAt(intelligence.intelligence.recommendation, "value"))} tone={intelligenceRecommendationTone(valueAt(intelligence.intelligence.recommendation, "value"))} /></div><div className="fi-case-analysis-grid"><div><span className="field-label">{term("failureAttribution")}</span><strong>{displayValue(valueAt(intelligence.intelligence.deterministicAttribution, "responsibility_layer"))}</strong><small>{displayValue(valueAt(intelligence.intelligence.deterministicAttribution, "basis"))}</small></div><div><span className="field-label">{t("failure.failureClassPhase")}</span><strong>{displayValue(valueAt(intelligence.intelligence.agentFailureTaxonomy, "agent_failure_class"))}</strong><small>{displayValue(valueAt(intelligence.intelligence.firstMeaningfulDivergence, "phase"))} · {shortId(valueAt(intelligence.intelligence.firstMeaningfulDivergence, "event_id"), 30)}</small></div><div><span className="field-label">{t("failure.recurrence")}</span><strong>{displayValue(valueAt(intelligence.intelligence.recurrence, "occurrence_count"))} {t("common.events")}</strong><small>{displayValue(valueAt(valueAt(intelligence.intelligence.recurrence, "exact_dedup"), "compatible_reproduction_facts") === true ? t("failure.exactRecurrence") : t("failure.identityNotProven"))}</small></div><div><span className="field-label">{term("structuralFailureFamily")}</span><strong>{intelligenceCluster ? <a className="action-link" href={clusterHref(intelligenceCluster.cluster.clusterId)} onClick={(event) => { event.preventDefault(); navigate(clusterHref(intelligenceCluster.cluster.clusterId)); }}>{shortId(intelligenceCluster.cluster.clusterId, 30)} →</a> : t("failure.notAgentCluster")}</strong><small>{displayValue(valueAt(valueAt(intelligence.intelligence.familySignatures.crossAgent, "features"), "reliability_pattern"))}</small></div></div><div className="evidence-separation"><div><span className="eyebrow">{t("failure.evidenceFacts")}</span><p>{t("failure.facts")}</p></div><div><span className="eyebrow">{t("failure.derivedFacts")}</span><p>{displayValue(valueAt(intelligence.intelligence.recommendation, "next_action"))}</p></div><div><span className="eyebrow">{t("failure.aiAnalysis")}</span><p>{t("failure.evidenceAiNotPresent")}</p></div></div></section>}
      <section className="case-compare-section" aria-labelledby="case-compare-heading"><div className="section-heading"><div><span className="eyebrow">{t("failure.caseCompared")}</span><h2 id="case-compare-heading">{t("failure.evidencePath")}</h2></div><span className="section-count">{t("failure.freshRunEnvironment")}</span></div><div className="case-compare-grid"><div className="case-run-card"><span className="field-label">{t("failure.sourceFail")}</span><strong className="mono">{shortId(failureCase.sourceRun.runId, 30)}</strong><span>{t("common.agent")} · {displayValue(failureCase.sourceRun.environment_id)}</span>{sourceLink && <a className="action-link" href={sourceLink} onClick={(event) => { event.preventDefault(); navigate(sourceLink); }}>{t("failure.openSourceEvent")}</a>}</div><div className="case-compare-arrow" aria-hidden="true">→</div><div className="case-run-card accent"><span className="field-label">{t("failure.validatedReproduction")}</span><strong className="mono">{shortId(attempt?.runId, 30)}</strong><span>{t("common.agent")} · {displayValue(attempt?.environment_id)}</span>{reproductionLink && <a className="action-link" href={reproductionLink} onClick={(event) => { event.preventDefault(); navigate(reproductionLink); }}>{t("failure.openReproductionEvent")}</a>}</div></div></section>
      <section className="case-evidence-section" aria-labelledby="case-evidence-heading"><div className="section-heading"><div><span className="eyebrow">{t("failure.stableReferences")}</span><h2 id="case-evidence-heading">{t("failure.keyEvidenceRefs")}</h2></div><span className="section-count">{t("failure.sourceArtifactRemainsImmutable")}</span></div><div className="case-ref-list">{failureCase.evidenceRefs.map((ref, index) => { const refRunId = typeof ref.run_id === "string" ? ref.run_id : failureCase.sourceRun.runId; const refEventId = typeof ref.event_id === "string" ? ref.event_id : null; const href = snapshot.artifacts.allRuns.some((item) => item.run.runId === refRunId) ? runHref(refRunId, refEventId) : null; return <div className="case-ref-row" key={`${displayValue(ref.role)}-${index}`}><span>{displayValue(ref.role)}</span><strong className="mono">{shortId(refEventId, 35)}</strong>{href ? <a href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>{t("common.openEvidence")}</a> : <span className="failure-evidence-unavailable">{t("common.evidenceUnavailable")}</span>}</div>; })}</div></section>
      <footer className="detail-footer"><span>Case {failureCase.failureCase.failureCaseId} · {failureCase.failureCase.workflowState}</span><span>{promoted ? t("failure.caseHistory") : t("failure.validatedNotRegression")}</span></footer>
    </AppShell>
  );
}

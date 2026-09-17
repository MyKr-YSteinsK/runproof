import { AppShell } from "../../components/AppShell";
import { IdentityField } from "../../components/IdentityField";
import { StatusTag } from "../../components/StatusTag";
import { navigate } from "../../app/navigation";
import type { CanonicalSnapshot } from "../../data/canonicalSnapshot";
import type { FailureCase, JsonRecord } from "../../data/artifacts";
import { selectFailureCaseEvidence } from "./failureModel";

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
const failureHref = (failureCaseId: string): string => "/failures/" + encodeURIComponent(failureCaseId);
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
  return (
    <AppShell detail failure>
      <div className="detail-breadcrumb">
        <a href="/failures" onClick={(event) => { event.preventDefault(); navigate("/failures"); }}>Failure Cases</a>
        <span aria-hidden="true">/</span>
        <span>{shortId(failureCase.failureCase.failureCaseId, 32)}</span>
        <span className="schema-chip">rpf-failure-case-v1</span>
      </div>
      <div className="detail-header case-detail-header">
        <div>
          <span className="eyebrow">FAILURE CASE INVESTIGATION</span>
          <h1>{incident ? "External dependency remediation failure" : "Unsafe precondition failure"}</h1>
          <p className="detail-subtitle">{incident ? "The source Incident Remediation Agent acted before dependency disambiguation; the failure was reproduced in a fresh controlled simulation with the same signature and harmful side-effect evidence." : "The source Agent FAIL was reproduced in a fresh Environment with the same failure signature and evidence pattern."}</p>
        </div>
        <div className="detail-header-status"><StatusTag status={promoted ? "PROMOTED" : "VALIDATED"} tone="success" /><span className="status-note">{promoted ? "validated history retained · Regression linked" : "Not a Regression"}</span></div>
      </div>
      <section className="case-identity-grid" aria-label="Failure Case identity">
        <IdentityField label="Failure Case" value={failureCase.failureCase.failureCaseId} mono />
        <IdentityField label="Agent / domain" value={agentIdentity(failureCase.agent)} note={agentDomain(failureCase.agent)} />
        <IdentityField label="Agent type / contract" value={`${agentType(failureCase.agent)} / ${displayValue(failureCase.agent.agent_contract_id || "—")}`} mono />
        <IdentityField label="Scenario" value={`${displayValue(failureCase.scenario.scenario_id)}@${displayValue(failureCase.scenario.scenario_version)}`} mono />
        <IdentityField label="Attribution" value={displayValue(failureCase.classification.attribution)} note={displayValue(failureCase.classification.reason_code)} />
        <IdentityField label="Signature" value={shortId(failureCase.failureSignature.value, 28)} mono note={failureCase.failureSignature.signatureVersion} />
        <IdentityField label="Workflow" value={failureCase.failureCase.currentStatus} note={promoted ? "validated · promoted additively" : "validated · no promotion"} />
      </section>
      <section className="classification-panel case-summary-panel" aria-label="Failure Case validation summary">
        <div className="classification-heading"><div><span className="eyebrow">{promoted ? "PROMOTION EVIDENCE · VALIDATED → REGRESSION" : "REPRODUCTION EVIDENCE · VALIDATED"}</span><h2>{promoted ? "Failure Case promoted to Regression" : "Same failure, independently reproduced"}</h2></div>{promoted && promotedRegression ? <a className="action-link" href={regressionHref(promotedRegression.regression.regressionId)} onClick={(event) => { event.preventDefault(); navigate(regressionHref(promotedRegression.regression.regressionId)); }}>Open Regression →</a> : <span className="classification-badge">NOT A REGRESSION</span>}</div>
        <p className="classification-copy">{incident ? "Validation matched the stable signature, violated invariant, Incident Agent attribution, dependency facts, side-effect evidence, and healthy Provider/Environment boundary." : "Validation matched the stable signature, violated invariant, Agent attribution, key guard evidence, and healthy Provider/Environment boundary."} {promoted ? `The explicit promotion gate passed and recorded ${displayValue(valueAt(failureCase.promotion, "promoted_at"))}; the original Run Evidence and validated history remain unchanged.` : "The original Run Evidence remains unchanged."}</p>
        <div className="classification-grid case-summary-grid">
          <div><span>Violated invariant</span><strong className="mono">{displayValue(failureCase.failureObservation.violated_invariant_id)}</strong><small>{displayValue(failureCase.failureObservation.violated_invariant)}</small></div>
          <div><span>Expected</span><strong>{displayValue(incident ? valueAt(incidentExpected, "no_harmful_local_remediation_on_external_fault") : valueAt(failureCase.failureObservation.expected, "agent_observed_state_before_mutation"))}</strong><small>{incident ? "external dependency must not trigger local remediation" : "Agent observes before mutation"}</small></div>
          <div><span>Actual</span><strong>{displayValue(incident ? valueAt(incidentActual, "harmful_local_remediation") : valueAt(failureCase.failureObservation.actual, "agent_observed_state_before_mutation"))}</strong><small>{incident ? `dependency ${displayValue(incidentActual.dependency_health)} · effect ${displayValue(incidentActual.effect_count)}` : "unsafe intent reached guard"}</small></div>
          {incident && <><div><span>Dependency fact</span><strong>{displayValue(incidentFacts.dependency_health)}</strong><small>{displayValue(incidentFacts.cause_classification)}</small></div><div><span>Remediation side effect</span><strong>{displayValue(incidentSideEffect.harmful ? "HARMFUL" : "NOT HARMFUL")}</strong><small>executed {displayValue(incidentSideEffect.executed)} · effect {displayValue(incidentSideEffect.effect_count)}</small></div></>}
          <div><span>Validation</span><strong>{displayValue(valueAt(failureCase.validation, "status"))}</strong><small>{displayValue(valueAt(failureCase.validation, "observed_run_id"))}</small></div>
          <div><span>Promotion</span><strong>{promoted ? "PROMOTED" : "NOT_A_REGRESSION"}</strong><small>{promoted ? `Gate ${displayValue(valueAt(promotionGate, "all_passed"))} · ${shortId(promotedRegressionId, 28)}` : "no Regression link"}</small></div>
        </div>
      </section>
      {intelligence && <section className="fi-case-analysis" aria-labelledby="fi-case-analysis-heading">
        <div className="section-heading"><div><span className="eyebrow">DERIVED DETERMINISTIC ANALYSIS · RPF-17</span><h2 id="fi-case-analysis-heading">Failure Intelligence</h2></div><StatusTag status={String(valueAt(intelligence.intelligence.recommendation, "value"))} tone={intelligenceRecommendationTone(valueAt(intelligence.intelligence.recommendation, "value"))} /></div>
        <div className="fi-case-analysis-grid"><div><span className="field-label">RESPONSIBILITY</span><strong>{displayValue(valueAt(intelligence.intelligence.deterministicAttribution, "responsibility_layer"))}</strong><small>{displayValue(valueAt(intelligence.intelligence.deterministicAttribution, "basis"))}</small></div><div><span className="field-label">FAILURE CLASS / PHASE</span><strong>{displayValue(valueAt(intelligence.intelligence.agentFailureTaxonomy, "agent_failure_class"))}</strong><small>{displayValue(valueAt(intelligence.intelligence.firstMeaningfulDivergence, "phase"))} · {shortId(valueAt(intelligence.intelligence.firstMeaningfulDivergence, "event_id"), 30)}</small></div><div><span className="field-label">RECURRENCE</span><strong>{displayValue(valueAt(intelligence.intelligence.recurrence, "occurrence_count"))} occurrences</strong><small>{displayValue(valueAt(valueAt(intelligence.intelligence.recurrence, "exact_dedup"), "compatible_reproduction_facts") === true ? "exact recurrence dedup" : "identity not proven" )}</small></div><div><span className="field-label">STRUCTURAL FAMILY</span><strong>{intelligenceCluster ? <a className="action-link" href={clusterHref(intelligenceCluster.cluster.clusterId)} onClick={(event) => { event.preventDefault(); navigate(clusterHref(intelligenceCluster.cluster.clusterId)); }}>{shortId(intelligenceCluster.cluster.clusterId, 30)} →</a> : "No Agent cluster"}</strong><small>{displayValue(valueAt(valueAt(intelligence.intelligence.familySignatures.crossAgent, "features"), "reliability_pattern"))}</small></div></div>
        <div className="evidence-separation"><div><span className="eyebrow">FACTS</span><p>Exact signature, source Run, event refs, health boundary, and Regression linkage remain canonical references.</p></div><div><span className="eyebrow">DERIVED DETERMINISTIC ANALYSIS</span><p>{displayValue(valueAt(intelligence.intelligence.recommendation, "next_action"))}</p></div><div><span className="eyebrow">AI ANALYSIS</span><p>Not present in RPF-17.</p></div></div>
      </section>}
      <section className="case-compare-section" aria-labelledby="case-compare-heading">
        <div className="section-heading"><div><span className="eyebrow">SOURCE ↔ REPRODUCTION</span><h2 id="case-compare-heading">Evidence path</h2></div><span className="section-count">fresh Run / fresh Environment</span></div>
        <div className="case-compare-grid">
          <div className="case-run-card"><span className="field-label">SOURCE FAIL</span><strong className="mono">{shortId(failureCase.sourceRun.runId, 30)}</strong><span>Agent · {displayValue(failureCase.sourceRun.environment_id)}</span>{sourceLink && <a className="action-link" href={sourceLink} onClick={(event) => { event.preventDefault(); navigate(sourceLink); }}>Open source event →</a>}</div>
          <div className="case-compare-arrow" aria-hidden="true">→</div>
          <div className="case-run-card accent"><span className="field-label">VALIDATED REPRODUCTION</span><strong className="mono">{shortId(attempt?.runId, 30)}</strong><span>Agent · {displayValue(attempt?.environment_id)}</span>{reproductionLink && <a className="action-link" href={reproductionLink} onClick={(event) => { event.preventDefault(); navigate(reproductionLink); }}>Open reproduction event →</a>}</div>
        </div>
      </section>
      <section className="case-evidence-section" aria-labelledby="case-evidence-heading">
        <div className="section-heading"><div><span className="eyebrow">STABLE REFERENCES</span><h2 id="case-evidence-heading">Key evidence refs</h2></div><span className="section-count">source artifact remains immutable</span></div>
        <div className="case-ref-list">
          {failureCase.evidenceRefs.map((ref, index) => {
            const refRunId = typeof ref.run_id === "string" ? ref.run_id : failureCase.sourceRun.runId;
            const refEventId = typeof ref.event_id === "string" ? ref.event_id : null;
            const href = snapshot.artifacts.allRuns.some((item) => item.run.runId === refRunId) ? runHref(refRunId, refEventId) : null;
            return <div className="case-ref-row" key={`${displayValue(ref.role)}-${index}`}><span>{displayValue(ref.role)}</span><strong className="mono">{shortId(refEventId, 35)}</strong>{href ? <a href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>Open evidence →</a> : <span className="failure-evidence-unavailable">Evidence unavailable</span>}</div>;
          })}
        </div>
      </section>
      <footer className="detail-footer"><span>Case {failureCase.failureCase.failureCaseId} · {failureCase.failureCase.workflowState}</span><span>{promoted ? "Failure Case history retained · Regression is a separate artifact." : "Failure Case validated ≠ Regression."}</span></footer>
    </AppShell>
  );
}

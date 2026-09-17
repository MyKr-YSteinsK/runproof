import { useEffect, useMemo, useState } from "react";
import {
  activateControlPlaneCorpus,
  EvidenceLayer,
  EvaluationComparison,
  EvaluationComparisonMember,
  EvaluationMemberResult,
  EvaluationResult,
  FailureCase,
  getDerivedCost,
  getAgent,
  getEvaluation,
  getEvaluationComparison,
  getFailureCase,
  getFailureCaseForRun,
  getFailureCluster,
  getVersionBisect,
  getQualityGate,
  getRegression,
  getRegressionResultForRun,
  getRegressionForRun,
  getRegressionResults,
  getReleaseDecision,
  getRun,
  getUsage,
  isAgentFailureRun,
  isEnvironmentErrorRun,
  isFaultedRun,
  JsonRecord,
  AgentSummary,
  reviewedAgents,
  reviewedRuns,
  reviewedFailureCases,
  reviewedFailureClusters,
  reviewedFailureIntelligence,
  reviewedVersionBisects,
  reviewedEvaluationComparison,
  reviewedEvaluationComparisons,
  reviewedEvaluations,
  reviewedEvaluationSuite,
  reviewedEvaluationSuites,
  reviewedQualityGates,
  reviewedQualityPolicy,
  reviewedQualityPolicies,
  reviewedReleaseDecisions,
  reviewedRegressions,
  reviewedRegressionCollection,
  reviewedRegressionCollections,
  Regression,
  RegressionExecutionResult,
  ReleaseDecision,
  RunEvidence,
  TrajectoryEvent,
  FailureCluster,
  FailureIntelligence,
  VersionBisect,
} from "./data/artifacts";
import { ControlPlaneApiError, loadControlPlaneCorpus } from "./data/controlPlaneApi";
import { ExecutionJobDto, loadExecutionJob, loadExecutionJobs, loadExecutionMetrics } from "./data/executions";
import { AppShell } from "./components/AppShell";
import { DataSourceState as SharedDataSourceState, NotFoundState } from "./components/DataSourceState";
import { IdentityField } from "./components/IdentityField";
import { StatusTag } from "./components/StatusTag";
import { DATA_SOURCE_FOOTNOTE, DATA_SOURCE_MODE } from "./app/dataSource";
import { navigate, readLocation, type LocationState } from "./app/navigation";
import { createCanonicalSnapshot, type CanonicalSnapshot } from "./data/canonicalSnapshot";
import {
  StatisticalComparisonDetail as StatisticalComparisonDetailFeature,
  StatisticalComparisonIndex as StatisticalComparisonIndexFeature,
  StatisticalEvaluationDetail as StatisticalEvaluationDetailFeature,
  StatisticalEvaluationIndex as StatisticalEvaluationIndexFeature,
} from "./features/statistical/StatisticalPages";
import { GoldenDemoOverview as GoldenDemoOverviewFeature } from "./features/overview/GoldenDemoOverview";
import { FailureCaseDetail as FailureCaseDetailFeature } from "./features/failure/FailureCaseDetail";
import { resolveCanonicalRouteState } from "./app/canonicalRouteState";

const EVENT_META: Record<string, { label: string; marker: string; description: string }> = {
  environment_provisioned: { label: "Environment provisioned", marker: "ENV", description: "A fresh controlled environment was created." },
  readiness: { label: "Readiness gate", marker: "RDY", description: "The environment reported ready before the run began." },
  initial_state_verification: { label: "Initial state verified", marker: "S0", description: "The known starting state passed its verification gate." },
  agent_tool_intent: { label: "Agent tool intent", marker: "TOOL", description: "The Agent selected a typed tool call." },
  tool_result: { label: "Tool result", marker: "RES", description: "The tool boundary returned an observable result." },
  environment_transition: { label: "Environment transition", marker: "Δ", description: "The controlled environment recorded a state transition." },
  fault: { label: "Fault observed", marker: "FLT", description: "The planned fault crossed the Agent boundary." },
  reconcile: { label: "Reconcile", marker: "REC", description: "The uncertain operation was reconciled against receipt and state." },
  agent_completion: { label: "Agent completion", marker: "END", description: "The Agent stopped after the required observations." },
  actual_state_verification: { label: "Actual state read-back", marker: "S1", description: "The final state was independently read back for verification." },
  cleanup: { label: "Environment cleanup", marker: "CLR", description: "The run environment was removed and cleanup was checked." },
  tool_execution_failure: { label: "Tool execution failure", marker: "ERR", description: "The harness classified a tool execution failure." },
  actual_state_observed_after_failure: { label: "State observed after failure", marker: "OBS", description: "The harness observed state after a terminal failure." },
  guard_blocked: { label: "Safety guard blocked", marker: "GRD", description: "The runtime guard rejected an unsafe Agent action before side effect." },
};

const EVIDENCE_LAYERS: Array<{ label: EvidenceLayer; note: string }> = [
  { label: "Observed Fact", note: "Provider, environment, tool and timeline observations" },
  { label: "Verified Result", note: "Deterministic verifier and reconcile results" },
  { label: "Derived Value", note: "Usage-based cost estimate" },
  { label: "Inference", note: "Not present in this run" },
  { label: "AI Analysis", note: "Not present in this run" },
];

const CHECK_LABELS: Record<string, string> = {
  initial_state_verified: "Initial state gate",
  required_target_state: "Required target state",
  exactly_one_mutation: "Exactly one mutation",
  actual_state_read_back: "Independent read-back",
  no_unresolved_unknown_outcome: "No unresolved UNKNOWN_OUTCOME",
  no_blind_retry_attempt: "No blind retry",
  planned_fault_triggered_and_observed: "Planned fault observed",
  planned_fault_reconciled: "Fault reconciled",
};

function objectValue(value: unknown): JsonRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : null;
}

function valueAt(value: unknown, key: string): unknown {
  return objectValue(value)?.[key];
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function agentDomain(value: unknown): string {
  const record = objectValue(value);
  const explicit = record?.agent_domain;
  if (typeof explicit === "string" && explicit) return explicit;
  return record?.agent_id === "incident-remediation-agent" || record?.agent_family === "incident-remediation-agent"
    ? "Incident Remediation Agent"
    : "Production Change Agent";
}

function agentIdentity(value: unknown): string {
  const record = objectValue(value);
  const id = record?.agent_id || record?.agent_family || "unknown-agent";
  const version = record?.agent_version || record?.known_bad_version;
  return `${String(id)}${version ? ` · ${String(version)}` : ""}`;
}

function agentType(value: unknown): string {
  const record = objectValue(value);
  return typeof record?.agent_type === "string" ? record.agent_type : agentDomain(value) === "Incident Remediation Agent" ? "INCIDENT_REMEDIATION" : "STATEFUL_CHANGE";
}

function isKnownBadProfile(value: unknown): boolean {
  const profile = typeof value === "string" ? value : displayValue(value);
  return profile.includes("known-bad");
}

function isFixedCandidateProfile(value: unknown): boolean {
  const profile = typeof value === "string" ? value : displayValue(value);
  return profile.includes("fixed") || profile.includes("candidate");
}

function shortId(value: unknown, length = 18): string {
  const text = displayValue(value);
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

function formatDuration(value: unknown): string {
  const milliseconds = typeof value === "number" ? value : 0;
  if (milliseconds < 1000) return `${milliseconds} ms`;
  return `${(milliseconds / 1000).toFixed(1)} s`;
}

function formatDate(value: unknown): string {
  if (typeof value !== "string") return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date);
}

function humanize(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function eventMeta(eventType: string) {
  return EVENT_META[eventType] || { label: humanize(eventType), marker: "EVT", description: "A recorded run event." };
}

function eventSummary(event: TrajectoryEvent): string {
  const payload = event.payload;
  const result = objectValue(payload.result);
  switch (event.eventType) {
    case "environment_provisioned":
      return `Fresh ${displayValue(valueAt(payload.provenance, "provider"))} environment · ${displayValue(payload.seed_revision)}`;
    case "readiness":
      return `Readiness: ${displayValue(valueAt(result, "readiness") || valueAt(result, "code"))}`;
    case "initial_state_verification":
      return `Starting state verified · revision ${displayValue(valueAt(result?.state, "revision"))}`;
    case "agent_tool_intent":
      return `${displayValue(payload.tool_name)} · validated arguments`;
    case "tool_result":
      return `${displayValue(payload.tool_name)} returned ${displayValue(result?.status)}`;
    case "environment_transition":
      return `State changed once · operation ${displayValue(payload.operation_id)}`;
    case "fault":
      return `Side effect ${displayValue(payload.side_effect_status)} · Agent received ${displayValue(payload.response_to_agent)}`;
    case "reconcile":
      return `Receipt ${displayValue(valueAt(result, "status"))} · no write performed`;
    case "agent_completion":
      return `Stopped with ${displayValue(payload.tool_calls)} additional tool calls`;
    case "actual_state_verification":
      return `Actual state read-back · ${displayValue(valueAt(payload.state, "release"))}`;
    case "actual_state_observed_after_failure":
      return `State observed after terminal ${displayValue(payload.reason || payload.code || "failure")}`;
    case "guard_blocked":
      return `Guard rejected ${displayValue(payload.tool_name)} · ${displayValue(payload.reason)}`;
    case "tool_execution_failure":
      return `${displayValue(payload.domain)} · ${displayValue(payload.code)}`;
    case "cleanup":
      return `Environment ${displayValue(valueAt(result, "removed") ? "removed" : valueAt(result, "code"))}`;
    default:
      return eventMeta(event.eventType).description;
  }
}

function statusTone(run: RunEvidence): "success" | "fault" | "error" | "neutral" {
  if (run.outcome.status === "PASS") return "success";
  if (run.outcome.status === "FAIL") return "fault";
  if (run.outcome.status === "ERROR") return "error";
  return "neutral";
}

function runSignal(run: RunEvidence): string {
  if (isAgentFailureRun(run)) return "Agent behavior defect · Failure Case";
  if (isEnvironmentErrorRun(run)) return "Platform/Environment · Agent not started";
  if (isFaultedRun(run)) return "Fault observed · reconciled PASS";
  if (run.outcome.status === "PASS") return "Normal transition · verified PASS";
  return `${run.outcome.source} · ${run.outcome.reason || "review required"}`;
}

function RunIndex() {
  return (
    <AppShell>
      <div className="page-header index-header">
        <div>
          <span className="eyebrow">RUN EVIDENCE · REVIEWED CORPUS</span>
          <h1>Investigate a run from the evidence trail.</h1>
          <p className="lede">A compact control plane for reconstructing Agent behavior, environment transitions, and verified outcomes.</p>
        </div>
        <div className="corpus-note">
          <span className="section-label">ACTIVE CORPUS</span>
          <strong>{reviewedRuns.length} reviewed runs</strong>
          <span>v2 schema · source-bound</span>
        </div>
      </div>
      <section className="corpus-boundary" aria-label="Evidence boundary">
        <span className="boundary-mark">i</span>
        <p><strong>Evidence boundary.</strong> The corpus contains normal <strong>PASS</strong>, recovered faulted <strong>PASS</strong>, deterministic Agent <strong>FAIL</strong>, and Platform/Environment <strong>ERROR</strong>. Failure Cases are separate artifacts; historical v1 evidence remains preserved.</p>
      </section>
      <a className="failure-entry" href="/failures" onClick={(event) => { event.preventDefault(); navigate("/failures"); }}>
        <span className="failure-entry-mark">!</span>
        <span><strong>Failure Case investigation</strong><small>Promoted Agent failure · source and reproduction evidence remain linked</small></span>
        <span aria-hidden="true">→</span>
      </a>
      <a className="failure-entry regression-entry" href="/regressions" onClick={(event) => { event.preventDefault(); navigate("/regressions"); }}>
        <span className="failure-entry-mark">↗</span>
        <span><strong>Historical Regression</strong><small>Known-bad FAIL reproduced · fixed Candidate PASS · not a Release decision</small></span>
        <span aria-hidden="true">→</span>
      </a>
      <section className="run-section" aria-labelledby="run-list-heading">
        <div className="section-heading">
          <div>
            <span className="eyebrow">SELECT A RUN</span>
            <h2 id="run-list-heading">Reviewed run evidence</h2>
          </div>
          <span className="section-count">{reviewedRuns.length.toString().padStart(2, "0")} records</span>
        </div>
        <div className="run-list">
          <div className="run-list-head" aria-hidden="true">
            <span>OUTCOME / SIGNAL</span><span>AGENT / SCENARIO</span><span>PROVIDER / ENVIRONMENT</span><span>RUN / COST</span><span />
          </div>
          {reviewedRuns.map((run) => <RunRow key={run.run.runId} run={run} />)}
        </div>
      </section>
      <footer className="page-footnote">
        <span>Source: {DATA_SOURCE_FOOTNOTE}</span>
        <span>Read-only API adapter · no live run action</span>
      </footer>
    </AppShell>
  );
}

function RunRow({ run }: { run: RunEvidence }) {
  const faulted = isFaultedRun(run);
  const href = `/runs/${encodeURIComponent(run.run.runId)}`;
  const usage = getUsage(run);
  const cost = getDerivedCost(run);
  return (
    <a className="run-row" href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>
      <div className="run-row-signal">
        <StatusTag status={run.outcome.status} tone={statusTone(run)} />
        <span className={`signal-label ${faulted || run.outcome.status !== "PASS" ? "fault" : ""}`}>{runSignal(run)}</span>
      </div>
      <div className="run-row-agent">
        <strong>{agentIdentity(run.run.agent)}</strong>
        <span>{agentDomain(run.run.agent)} <em>·</em> {displayValue(run.scenario.scenario_id)}@{displayValue(run.scenario.scenario_version)}</span>
      </div>
      <div className="run-row-provider">
        <strong>{displayValue(run.llmProvider.requested_model)}</strong>
        <span>{displayValue(run.environmentProvider.provider_implementation)} · {displayValue(run.environment.environment_id)}</span>
      </div>
      <div className="run-row-run">
        <strong className="mono">{shortId(run.run.runId, 23)}</strong>
        <span>{formatDuration(run.run.durationMs)} <em>·</em> {displayValue(usage.total_tokens)} tok <em>·</em> ¥{displayValue(cost.estimate)}</span>
      </div>
      <span className="row-arrow" aria-hidden="true">→</span>
    </a>
  );
}

function RunDetail({ run, eventId }: { run: RunEvidence; eventId: string | null }) {
  const agentFailure = isAgentFailureRun(run);
  const environmentError = isEnvironmentErrorRun(run);
  const failureCase = getFailureCaseForRun(run.run.runId);
  const regression = getRegressionForRun(run.run.runId);
  const regressionResult = getRegressionResultForRun(run.run.runId);
  const preferredEventId = eventId || (typeof run.failureAttribution?.failing_event_id === "string" ? run.failureAttribution.failing_event_id : null);
  const selected = run.trajectory.find((event) => event.eventId === preferredEventId) || run.trajectory[0];
  const [activeEventId, setActiveEventId] = useState(selected.eventId);
  useEffect(() => setActiveEventId(selected.eventId), [selected.eventId]);
  const selectEvent = (nextEventId: string) => {
    setActiveEventId(nextEventId);
    navigate(`/runs/${encodeURIComponent(run.run.runId)}?event=${encodeURIComponent(nextEventId)}`);
  };
  const selectedIndex = run.trajectory.findIndex((event) => event.eventId === activeEventId);
  const activeEvent = run.trajectory[selectedIndex] || selected;
  const faulted = isFaultedRun(run);
  const usage = getUsage(run);
  const cost = getDerivedCost(run);
  return (
    <AppShell detail regression={Boolean(regression)}>
      <div className="detail-breadcrumb">
        <a href="/runs" onClick={(event) => { event.preventDefault(); navigate("/runs"); }}>Run Evidence</a>
        <span aria-hidden="true">/</span>
        <span>{shortId(run.run.runId, 32)}</span>
        <span className="schema-chip">rpf-run-evidence-v2</span>
      </div>
      <div className="detail-header">
        <div>
          <span className="eyebrow">RUN INVESTIGATION</span>
          <h1>{regressionResult ? `${regressionResult.result.regressionResult === "FAIL" ? "Historical Regression" : "Regression fixed Candidate"} · ${regressionResult.result.regressionResult}` : agentFailure ? "Agent safety failure" : environmentError ? "Environment readiness error" : faulted ? "Response-lost recovery run" : "Normal release transition"}</h1>
          <p className="detail-subtitle">{regressionResult ? `Focused rerun of ${regressionResult.result.regressionId}@${regressionResult.result.regressionVersion}. Run outcome ${regressionResult.result.runOutcome}; Regression result ${regressionResult.result.regressionResult}. This result is scoped to one Regression, not a Suite or Release decision.` : agentFailure ? "The known-bad Agent attempted a state-changing action before observation; the guard protected the environment, but the behavior is still a deterministic FAIL." : environmentError ? "A controlled Environment-side readiness failure stopped the run before Agent start. It is excluded from Agent Quality." : faulted ? "A side effect completed, its response was lost, and reconciliation established the verified result." : "A controlled release change completed with an independent state read-back."}</p>
        </div>
        <div className="detail-header-status">
          <StatusTag status={run.outcome.status} tone={statusTone(run)} />
          <span className="status-note">{regressionResult ? `${regressionResult.result.agentVersion} · Regression ${regressionResult.result.regressionResult}` : agentFailure ? "deterministic Agent attribution" : environmentError ? "Platform/Environment attribution" : "deterministic verifier"}</span>
        </div>
      </div>
      <section className="identity-strip" aria-label="Run context identity">
        <IdentityField label="Agent" value={agentIdentity(run.run.agent)} note={agentDomain(run.run.agent)} />
        <IdentityField label="Agent type / contract" value={`${agentType(run.run.agent)} / ${displayValue(run.run.agent.agent_contract_id || "—")}`} mono />
        <IdentityField label="Evaluation / Run" value={`${shortId(run.run.evaluationId, 16)} / ${shortId(run.run.runId, 16)}`} mono />
        <IdentityField label="Scenario" value={`${displayValue(run.scenario.scenario_id)}@${displayValue(run.scenario.scenario_version)}`} mono />
        <IdentityField label="LLM provider" value={`${displayValue(run.llmProvider.provider_id)} · ${displayValue(run.llmProvider.requested_model)}`} note={displayValue(run.llmProvider.mode)} />
        <IdentityField label="Environment" value={shortId(run.environment.environment_id, 23)} mono note={`${displayValue(run.environment.seed_id)} / ${displayValue(run.environment.seed_revision)}`} />
        <IdentityField label="Verifier" value={`${displayValue(run.run.verifier.verifier_id)}@${displayValue(run.run.verifier.verifier_version)}`} mono />
      </section>
      <section className="run-facts-bar" aria-label="Run facts">
        <div><span>Outcome</span><strong>{run.outcome.status}</strong><small>{run.outcome.agentQualityEligible ? "quality eligible" : "Agent Quality excluded"}</small></div>
        <div><span>{regressionResult ? "Regression result" : agentFailure || environmentError ? "Attribution" : "Fault"}</span><strong>{regressionResult ? regressionResult.result.regressionResult : agentFailure ? "Agent" : environmentError ? "Platform/Environment" : faulted ? "Observed" : "None"}</strong><small>{regressionResult ? `Run outcome ${regressionResult.result.runOutcome}` : agentFailure ? displayValue(run.outcome.reason) : environmentError ? "controlled readiness failure" : faulted ? "planned · triggered · reconciled" : "normal profile"}</small></div>
        <div><span>Environment provider</span><strong>{displayValue(run.environmentProvider.provider_implementation)}</strong><small>{displayValue(run.environmentProvider.context)} · writable layer</small></div>
        <div><span>Run duration</span><strong>{formatDuration(run.run.durationMs)}</strong><small>{formatDate(run.run.startedAt)} UTC</small></div>
      </section>
      {agentFailure && <AgentFailureSummary run={run} failureCase={failureCase} regression={regression} />}
      {regressionResult && regression && <RegressionRunSummary run={run} regression={regression} result={regressionResult} />}
      {environmentError && <EnvironmentErrorSummary run={run} />}
      {faulted && <RecoveryPath />}
      <div className="investigation-layout">
        <section className="panel timeline-panel" aria-labelledby="timeline-heading">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">SEQUENCE · {run.trajectory.length.toString().padStart(2, "0")} EVENTS</span>
              <h2 id="timeline-heading">Run timeline</h2>
            </div>
            <span className="ordering-note"><span className="mono">sequence</span> ascending · IDs stable</span>
          </div>
          <div className="timeline-scroll" role="list" aria-label="Run event timeline">
            {run.trajectory.map((event, index) => (
              <TimelineEventButton
                key={event.eventId}
                event={event}
                selected={event.eventId === activeEvent.eventId}
                isLast={index === run.trajectory.length - 1}
                onSelect={selectEvent}
                onMove={(direction) => {
                  const nextIndex = Math.min(Math.max(selectedIndex + direction, 0), run.trajectory.length - 1);
                  selectEvent(run.trajectory[nextIndex].eventId);
                }}
              />
            ))}
          </div>
        </section>
        <EventInspector event={activeEvent} run={run} />
      </div>
      <div className="lower-layout">
        <StateDiffPanel run={run} />
        <EvidencePanel run={run} usage={usage} cost={cost} />
      </div>
      <footer className="detail-footer">
        <span>Runtime {displayValue(run.run.runtime.runtime_version)} · source <span className="mono">{shortId(run.run.runtime.source_sha256, 20)}</span></span>
        <span>Historical v1 evidence is preserved outside the active v2 corpus.</span>
      </footer>
    </AppShell>
  );
}

function runHref(runId: string, eventId?: string | null): string {
  const base = `/runs/${encodeURIComponent(runId)}`;
  return eventId ? `${base}?event=${encodeURIComponent(eventId)}` : base;
}

function failureHref(failureCaseId: string): string {
  return `/failures/${encodeURIComponent(failureCaseId)}`;
}

function regressionHref(regressionId: string): string {
  return `/regressions/${encodeURIComponent(regressionId)}`;
}

function evaluationHref(evaluationId: string): string {
  return `/evaluations/${encodeURIComponent(evaluationId)}`;
}

function comparisonHref(comparisonId: string): string {
  return `/comparisons/${encodeURIComponent(comparisonId)}`;
}

function releaseDecisionHref(decisionId: string): string {
  return `/release-decisions/${encodeURIComponent(decisionId)}`;
}

function intelligenceHref(): string {
  return "/failure-intelligence";
}

function clusterHref(clusterId: string): string {
  return `/failure-intelligence/clusters/${encodeURIComponent(clusterId)}`;
}

function bisectHref(bisectId: string): string {
  return `/version-bisects/${encodeURIComponent(bisectId)}`;
}

function intelligenceRecommendationTone(value: unknown): "success" | "fault" | "error" | "neutral" | "review" {
  const status = String(value || "");
  if (status === "ALREADY_COVERED") return "success";
  if (status === "PROMOTE_CANDIDATE") return "review";
  if (status === "NOT_AGENT_FAILURE") return "neutral";
  if (status === "UNSTABLE") return "error";
  return "fault";
}

function formatRate(value: unknown): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "UNKNOWN";
}

function formatMetric(value: unknown, suffix = ""): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "UNKNOWN";
  return `${value.toLocaleString("en-US")}${suffix}`;
}

function evaluationTone(status: string): "success" | "fault" | "error" | "neutral" {
  if (status === "PASS" || status === "COMPLETE" || status === "IMPROVED") return "success";
  if (status === "FAIL" || status === "REGRESSED") return "fault";
  if (status === "ERROR") return "error";
  return "neutral";
}

function releaseTone(status: string): "success" | "fault" | "error" | "neutral" | "review" {
  if (status === "ELIGIBLE") return "success";
  if (status === "BLOCKED") return "fault";
  if (status === "REVIEW_REQUIRED") return "review";
  if (status === "INCONCLUSIVE") return "error";
  return "neutral";
}

function resultTone(result: string): "success" | "fault" | "error" | "neutral" {
  if (result === "PASS") return "success";
  if (result === "FAIL") return "fault";
  if (result === "ERROR") return "error";
  return "neutral";
}

function AgentFailureSummary({ run, failureCase, regression }: { run: RunEvidence; failureCase?: FailureCase; regression?: Regression }) {
  const failure = run.failureAttribution || {};
  const failingEventId = typeof failure.failing_event_id === "string" ? failure.failing_event_id : null;
  const incident = agentDomain(run.run.agent) === "Incident Remediation Agent";
  const sideEffect = objectValue(failure.remediation_side_effect) || {};
  return (
    <section className="classification-panel agent-failure-panel" aria-label="Agent failure attribution">
      <div className="classification-heading">
        <div><span className="eyebrow">FAILURE ATTRIBUTION · DETERMINISTIC</span><h2>{incident ? "Agent FAIL, harmful remediation observed" : "Agent FAIL, guard protected state"}</h2></div>
        {failureCase && <a className="action-link" href={failureHref(failureCase.failureCase.failureCaseId)} onClick={(event) => { event.preventDefault(); navigate(failureHref(failureCase.failureCase.failureCaseId)); }}>Open Failure Case →</a>}
      </div>
      <p className="classification-copy">{incident ? "The Incident Remediation Agent acted on a service symptom without disambiguating dependency health. The controlled simulation recorded the remediation side effect, so the unsafe behavior remains an Agent FAIL." : "The Candidate Agent issued a state-changing intent before observing the expected state. The runtime guard rejected it, so no business mutation occurred; the unsafe behavior itself remains a FAIL."}</p>
      <div className="classification-grid">
        <div><span>Attribution</span><strong>Agent</strong><small>{displayValue(failure.reason_code)}</small></div>
        <div><span>Violated invariant</span><strong className="mono">{displayValue(failure.violated_invariant_id)}</strong><small>{displayValue(failure.violated_invariant)}</small></div>
        <div><span>Failing event</span><strong className="mono">{shortId(failingEventId, 27)}</strong>{failingEventId && <a href={runHref(run.run.runId, failingEventId)} onClick={(event) => { event.preventDefault(); navigate(runHref(run.run.runId, failingEventId)); }}>Open event deep-link</a>}</div>
        <div><span>Expected / actual</span><strong>{displayValue(failure.expected)}</strong><small>{displayValue(failure.actual)}</small></div>
        <div><span>Side effect</span><strong>{incident ? displayValue(sideEffect.executed ? "Executed" : "Not executed") : "Not executed"}</strong><small>{incident ? `${displayValue(sideEffect.harmful ? "harmful local mutation" : "no harmful local mutation")} · effect ${displayValue(sideEffect.effect_count)}` : "guard rejected unsafe intent"}</small></div>
        <div><span>Quality / workflow</span><strong>Excluded from quality</strong><small>{regression ? `Regression ${shortId(regression.regression.regressionId, 27)} · focused` : failureCase ? "Failure Case linked · promoted separately" : "Failure Case not linked"}</small></div>
      </div>
    </section>
  );
}

function RegressionRunSummary({ run, regression, result }: { run: RunEvidence; regression: Regression; result: RegressionExecutionResult }) {
  const resultId = result.result.resultId;
  const href = regressionHref(regression.regression.regressionId);
  return (
    <section className="classification-panel regression-run-panel" aria-label="Regression focused rerun result">
      <div className="classification-heading">
        <div><span className="eyebrow">FOCUSED RERUN · REGRESSION RESULT</span><h2>{isKnownBadProfile(result.result.agentProfile) ? "Known-bad failure reproduced" : "Fixed Candidate passed this Regression"}</h2></div>
        <a className="action-link" href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>Open Regression →</a>
      </div>
      <p className="classification-copy">Run outcome and Regression result are separate contracts. This execution is evidence for <span className="mono">{shortId(regression.regression.regressionId, 31)}</span> version {regression.regression.regressionVersion}; it is not an overall Agent, Suite, Quality, or Release decision.</p>
      <div className="classification-grid regression-result-grid">
        <div><span>Regression result</span><strong><StatusTag status={result.result.regressionResult} tone={resultTone(result.result.regressionResult)} /></strong><small>{result.result.agentVersion}</small></div>
        <div><span>Underlying Run</span><strong>{run.outcome.status}</strong><small className="mono">{shortId(run.run.runId, 27)}</small></div>
        <div><span>Execution result</span><strong className="mono">{shortId(resultId, 27)}</strong><small>{displayValue(valueAt(result.result.oracle, "reason"))}</small></div>
        <div><span>Release eligibility</span><strong>{result.result.releaseEligibility}</strong><small>not evaluated by RPF-06</small></div>
      </div>
    </section>
  );
}

function EnvironmentErrorSummary({ run }: { run: RunEvidence }) {
  const failure = run.failureAttribution || {};
  return (
    <section className="classification-panel environment-error-panel" aria-label="Platform environment error attribution">
      <div className="classification-heading">
        <div><span className="eyebrow">ERROR ATTRIBUTION · PRE-AGENT</span><h2>Platform / Environment ERROR</h2></div>
        <span className="classification-badge">Agent Quality excluded</span>
      </div>
      <p className="classification-copy">The controlled readiness boundary failed before the Agent started. No Scenario mutation was attempted, and this evidence must not be counted as an Agent FAIL.</p>
      <div className="classification-grid">
        <div><span>Failure source</span><strong>Platform/Environment</strong><small>{displayValue(failure.reason_code)}</small></div>
        <div><span>Agent started</span><strong>No</strong><small>formal run not started</small></div>
        <div><span>State change</span><strong>None</strong><small>controlled pre-agent hook</small></div>
        <div><span>Provider</span><strong>Not in failure path</strong><small>no Provider outage asserted</small></div>
      </div>
    </section>
  );
}

function TimelineEventButton({ event, selected, isLast, onSelect, onMove }: { event: TrajectoryEvent; selected: boolean; isLast: boolean; onSelect: (eventId: string) => void; onMove: (direction: number) => void }) {
  const meta = eventMeta(event.eventType);
  return (
    <div role="listitem">
      <button
        className={`timeline-event ${selected ? "selected" : ""} ${event.eventType === "fault" ? "fault-event" : ""} ${event.eventType === "guard_blocked" || event.eventType === "tool_execution_failure" ? "failure-event" : ""}`}
        type="button"
        aria-current={selected ? "step" : undefined}
        onClick={() => onSelect(event.eventId)}
        onKeyDown={(keyboardEvent) => {
          if (keyboardEvent.key === "ArrowDown") { keyboardEvent.preventDefault(); onMove(1); }
          if (keyboardEvent.key === "ArrowUp") { keyboardEvent.preventDefault(); onMove(-1); }
        }}
      >
        <span className="timeline-spine" aria-hidden="true"><span className="timeline-dot" />{!isLast && <span className="timeline-line" />}</span>
        <span className="event-sequence mono">{String(event.sequence).padStart(2, "0")}</span>
        <span className="event-marker" aria-hidden="true">{meta.marker}</span>
        <span className="event-copy">
          <strong>{meta.label}</strong>
          <span>{event.evidenceLayer} <em>·</em> {eventSummary(event)}</span>
        </span>
        <span className="event-chevron" aria-hidden="true">›</span>
      </button>
    </div>
  );
}

function EventInspector({ event, run }: { event: TrajectoryEvent; run: RunEvidence }) {
  const meta = eventMeta(event.eventType);
  const refs = event.entityRefs;
  return (
    <aside className="panel inspector-panel" aria-labelledby="inspector-heading">
      <div className="panel-heading inspector-heading">
        <div>
          <span className="eyebrow">SELECTED EVIDENCE</span>
          <h2 id="inspector-heading">{meta.label}</h2>
        </div>
        <span className={`layer-tag ${event.evidenceLayer.toLowerCase().replace(/ /g, "-")}`}>{event.evidenceLayer}</span>
      </div>
      <div className="event-summary"><span className="summary-mark">↳</span><p>{eventSummary(event)}</p></div>
      <div className="inspector-facts">
        <IdentityField label="Event ID" value={event.eventId} mono />
        <IdentityField label="Run sequence" value={String(event.sequence).padStart(2, "0")} mono note="explicit ordering" />
        <IdentityField label="Related entity" value={shortId(refs.tool_call_id || refs.operation_id || refs.fault_id || refs.environment_id || run.run.runId, 27)} mono />
      </div>
      <div className="inspector-divider" />
      <div className="inspector-section-title"><span>Evidence detail</span><span className="section-label">{event.evidenceLayer}</span></div>
      <EventFacts event={event} />
      <details className="raw-details">
        <summary>Show raw event payload</summary>
        <pre>{JSON.stringify(event.payload, null, 2)}</pre>
      </details>
    </aside>
  );
}

function EventFacts({ event }: { event: TrajectoryEvent }) {
  const rows: Array<[string, unknown]> = [];
  const payload = event.payload;
  if (event.eventType === "agent_tool_intent") {
    rows.push(["Tool", payload.tool_name], ["Validated arguments", payload.validated_arguments]);
  } else if (event.eventType === "fault") {
    rows.push(["Fault profile", payload.fault_id], ["Side effect", payload.side_effect_status], ["Agent boundary", payload.response_to_agent]);
  } else if (event.eventType === "environment_transition") {
    rows.push(["Operation", payload.operation_id], ["Before", payload.before], ["After", payload.after]);
  } else if (event.eventType === "tool_result" || event.eventType === "reconcile") {
    rows.push(["Tool", payload.tool_name], ["Result", payload.result]);
  } else if (event.eventType === "guard_blocked") {
    rows.push(["Tool", payload.tool_name], ["Reason", payload.reason], ["Invariant", payload.invariant_id], ["Side effect", payload.side_effect_executed]);
  } else if (event.eventType === "tool_execution_failure") {
    rows.push(["Domain", payload.domain], ["Code", payload.code], ["Outcome", payload.outcome], ["Invariant", payload.invariant_id]);
  } else if (event.eventType === "initial_state_verification" || event.eventType === "actual_state_verification") {
    rows.push(["State", payload.state || valueAt(payload.result, "state")]);
  } else if (event.eventType === "actual_state_observed_after_failure") {
    rows.push(["State", payload.state]);
  } else if (event.eventType === "environment_provisioned") {
    rows.push(["Environment", payload.environment_id], ["Seed revision", payload.seed_revision], ["Provenance", payload.provenance]);
  } else if (event.eventType === "cleanup") {
    rows.push(["Cleanup result", payload.result]);
  } else {
    Object.entries(payload).filter(([key]) => !["event_id", "sequence", "event_type", "evidence_layer", "entity_refs"].includes(key)).slice(0, 4).forEach(([key, value]) => rows.push([humanize(key), value]));
  }
  return <div className="fact-list">{rows.map(([label, value]) => <div className="fact-row" key={label}><span>{label}</span><strong className={typeof value === "object" ? "fact-object" : ""}>{displayValue(value)}</strong></div>)}</div>;
}

function RecoveryPath() {
  const steps = [
    ["01", "Side effect", "APPLIED"],
    ["02", "Response boundary", "LOST"],
    ["03", "Agent observation", "UNKNOWN_OUTCOME"],
    ["04", "Reconcile", "APPLIED"],
    ["05", "Verified result", "PASS"],
  ];
  return (
    <section className="recovery-panel" aria-label="Response-lost recovery path">
      <div className="recovery-heading"><div><span className="eyebrow">FAULT SEMANTICS</span><h2>Recovery path</h2></div><span className="fault-separation">Fault ≠ Failure</span></div>
      <div className="recovery-track">
        {steps.map(([number, label, state], index) => <div className="recovery-step" key={number}><span className="recovery-number mono">{number}</span><span className="recovery-label">{label}</span><strong>{state}</strong>{index < steps.length - 1 && <span className="recovery-arrow" aria-hidden="true">→</span>}</div>)}
      </div>
      <p className="recovery-explanation">The mutation happened once. The Agent saw an unknown result, reconciled the receipt, read the actual state back, and finished with a deterministic <strong>PASS</strong>.</p>
    </section>
  );
}

function StateSnapshot({ label, state, accent = false }: { label: string; state: JsonRecord; accent?: boolean }) {
  return (
    <div className={`state-snapshot ${accent ? "accent" : ""}`}>
      <span className="field-label">{label}</span>
      <strong>{displayValue(state.release)}</strong>
      <div className="state-mini-grid">
        <span>revision <b>{displayValue(state.revision)}</b></span>
        <span>mutations <b>{displayValue(state.mutation_count)}</b></span>
        <span>operation <b className="mono">{displayValue(state.operation_id)}</b></span>
      </div>
    </div>
  );
}

function StateDiffPanel({ run }: { run: RunEvidence }) {
  const verification = run.verification;
  const changed = verification?.stateDiff.filter((row) => row.changed) || [];
  return (
    <section className="panel state-panel" aria-labelledby="state-diff-heading">
      <div className="panel-heading">
        <div><span className="eyebrow">VERIFIED RESULT · STATE</span><h2 id="state-diff-heading">State diff</h2></div>
        <span className="diff-count">{changed.length} changed fields</span>
      </div>
      {verification ? <>
        <div className="state-compare">
          <StateSnapshot label="S0 · initial" state={verification.initialState} />
          <span className="state-arrow" aria-hidden="true">→</span>
          <StateSnapshot label="Required target" state={verification.expectedState} />
          <span className="state-arrow" aria-hidden="true">≈</span>
          <StateSnapshot label="S1 · actual read-back" state={verification.actualState} accent={verification.passed} />
        </div>
        <div className="diff-table" role="table" aria-label="State field changes">
          <div className="diff-row diff-head" role="row"><span>FIELD</span><span>BEFORE</span><span>AFTER</span><span>STATUS</span></div>
          {verification.stateDiff.map((row) => <div className="diff-row" role="row" key={row.path}><strong className="mono">{row.path}</strong><span>{displayValue(row.before)}</span><span>{displayValue(row.after)}</span><span className={row.changed ? "changed-label" : "unchanged-label"}>{row.changed ? "Changed" : "Unchanged"}</span></div>)}
        </div>
      </> : <div className="empty-evidence"><strong>No Agent state diff</strong><p>The run stopped before initial-state verification. No business mutation was attempted.</p></div>}
    </section>
  );
}

function EvidencePanel({ run, usage, cost }: { run: RunEvidence; usage: JsonRecord; cost: JsonRecord }) {
  const checkEntries = run.verification ? Object.entries(run.verification.checks) : [];
  const passedChecks = checkEntries.filter(([, passed]) => passed).length;
  return (
    <section className="panel evidence-panel" aria-labelledby="evidence-heading">
      <div className="panel-heading"><div><span className="eyebrow">EVIDENCE INSPECTOR</span><h2 id="evidence-heading">Invariants & evidence</h2></div><span className="check-summary">{passedChecks}/{checkEntries.length} verified</span></div>
      <div className="layer-list">
        {EVIDENCE_LAYERS.map(({ label, note }) => <div className={`layer-row ${label === "Inference" || label === "AI Analysis" ? "missing" : ""}`} key={label}><span className="layer-name">{label}</span><span>{note}</span>{(label === "Inference" || label === "AI Analysis") && <em>Not present</em>}</div>)}
      </div>
      {run.verification ? <div className="invariant-list">
        {checkEntries.map(([key, passed]) => <div className="invariant-row" key={key}><span className={`invariant-icon ${passed ? "pass" : "fail"}`} aria-hidden="true">{passed ? "✓" : "!"}</span><span>{CHECK_LABELS[key] || humanize(key)}</span><strong>{passed ? "VERIFIED" : "VIOLATED"}</strong></div>)}
      </div> : <div className="empty-evidence"><strong>Agent Quality excluded</strong><p>No deterministic Agent invariant checks ran because the Environment failed before Agent start.</p></div>}
      <div className="usage-block">
        <div className="usage-heading"><span>Usage fact</span><span>Derived value</span></div>
        <div className="usage-values"><strong>{displayValue(usage.total_tokens)} <small>tokens</small></strong><strong>¥{displayValue(cost.estimate)} <small>{displayValue(cost.tariff)} estimate</small></strong></div>
        <p>Usage is observed from the Provider response. Cost is a derived estimate, not a billing record.</p>
      </div>
    </section>
  );
}

function runRef(value: unknown): { runId: string; eventId: string | null } | null {
  const ref = objectValue(value);
  if (!ref || typeof ref.run_id !== "string") return null;
  return { runId: ref.run_id, eventId: typeof ref.event_id === "string" ? ref.event_id : null };
}

function refLabel(value: unknown): string {
  const ref = objectValue(value);
  return typeof ref?.kind === "string" ? ref.kind : "Evidence ref";
}

function agentHref(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}`;
}

function AgentIndex() {
  return <AppShell agent>
    <div className="page-header index-header"><div><span className="eyebrow">AGENTS · CROSS-AGENT REGISTRY</span><h1>Follow reliability by Agent identity.</h1><p className="lede">Each Agent keeps its own domain, scenario, tool, environment, verifier, and versioned evidence. Shared semantics stop at the narrow integration contract.</p></div><div className="corpus-note"><span className="section-label">REGISTERED AGENTS</span><strong>{reviewedAgents.length}</strong><span>explicit reviewed adapters</span></div></div>
    <section className="corpus-boundary agent-boundary" aria-label="Agent contract boundary"><span className="boundary-mark">◇</span><p><strong>Integration boundary.</strong> The registry is explicit and read-only. It does not dynamically load plugins, grant production access, or give an Agent release authority.</p></section>
    <section className="agent-card-grid" aria-label="Registered Agents">
      {reviewedAgents.map((item) => <a className="agent-card" key={item.agentId} href={agentHref(item.agentId)} onClick={(event) => { event.preventDefault(); navigate(agentHref(item.agentId)); }}><div className="agent-card-mark">{item.domain === "Incident Remediation Agent" ? "IR" : "PC"}</div><div className="agent-card-body"><span className="eyebrow">{item.domain}</span><h2>{item.agentId}</h2><p>{item.agentType} · {item.versions.length} reviewed version(s)</p><div className="agent-card-facts"><span><strong>{item.runIds.length}</strong> Runs</span><span><strong>{item.failureCaseIds.length}</strong> Failures</span><span><strong>{item.regressionIds.length}</strong> Regressions</span><span><strong>{item.evaluationIds.length}</strong> Evaluations</span></div></div><span className="row-arrow" aria-hidden="true">→</span></a>)}
    </section>
    <footer className="page-footnote"><span>Source: {DATA_SOURCE_FOOTNOTE} · derived from verified Agent-bearing artifacts</span><span>Read-only registry · no mutation or release action</span></footer>
  </AppShell>;
}

function AgentDetail({ agent }: { agent: AgentSummary }) {
  const runs = reviewedRuns.filter((run) => agentTextFor(run.run.agent, agent.agentId));
  const failures = reviewedFailureCases.filter((item) => agentTextFor(item.agent, agent.agentId));
  const regressions = reviewedRegressions.filter((item) => agentTextFor(item.agent, agent.agentId));
  const evaluations = reviewedEvaluations.filter((item) => agentTextFor(item.evaluation.agent, agent.agentId));
  const decisions = reviewedReleaseDecisions.filter((item) => agentTextFor(item.releaseDecision.evaluatedAgent, agent.agentId) || agentTextFor(item.releaseDecision.candidateAgent, agent.agentId));
  const incidentFailure = failures.find((item) => item.scenario.scenario_id === "incident-remediation");
  const observation = incidentFailure?.failureObservation || {};
  const dependencyFacts = objectValue(observation.dependency_facts) || objectValue(valueAt(observation, "actual")) || {};
  const sideEffect = objectValue(observation.remediation_side_effect) || {};
  return <AppShell agent detail>
    <div className="detail-breadcrumb"><a href="/agents" onClick={(event) => { event.preventDefault(); navigate("/agents"); }}>Agents</a><span aria-hidden="true">/</span><span>{shortId(agent.agentId, 34)}</span><span className="schema-chip">rpf-agent-integration-contract-v1</span></div>
    <div className="detail-header agent-detail-header"><div><span className="eyebrow">{agent.domain} · AGENT DETAIL</span><h1>{agent.agentId}</h1><p className="detail-subtitle">This view binds versions and execution evidence to one explicit Agent contract. Production Change history remains independent from Incident Remediation history.</p></div><div className="detail-header-status"><span className="status-chip success">REGISTERED</span><span className="status-note">read-only contract view</span></div></div>
    <section className="identity-strip agent-identity-strip" aria-label="Agent contract identity"><IdentityField label="Agent domain" value={agent.domain} /><IdentityField label="Agent type" value={agent.agentType} mono /><IdentityField label="Contract" value={`${agent.contractId}@1.0.0`} mono /><IdentityField label="Versions" value={agent.versions.join(" · ")} /><IdentityField label="Profiles" value={agent.profiles.join(" · ")} mono /></section>
    <section className="agent-contract-panel panel" aria-labelledby="agent-contract-heading"><div className="panel-heading"><div><span className="eyebrow">COMPATIBILITY CONTRACT · EXPLICIT</span><h2 id="agent-contract-heading">Scenario, tools, environment, verifier</h2></div><span className="schema-chip">evidence: rpf-run-evidence-v2</span></div><div className="agent-contract-grid"><div><span>Scenario refs</span><strong>{agent.scenarioRefs.map((ref) => `${displayValue(ref.scenario_id)}@${displayValue(ref.scenario_version)}`).join(" · ") || "—"}</strong><small>versioned case identity stays visible</small></div><div><span>Supported execution</span><strong>fresh-per-member</strong><small>sequential · controlled simulation</small></div><div><span>Evidence boundary</span><strong>Observed Fact / Verified Result</strong><small>private protocol fields are not displayed</small></div><div><span>Authority</span><strong>Agent has no release authority</strong><small>decision-only quality boundary</small></div></div></section>
    <section className="agent-evidence-grid" aria-label="Agent evidence counts"><div className="panel"><span className="eyebrow">RUN EVIDENCE</span><strong className="agent-big-number">{runs.length}</strong><span>linked immutable Runs</span></div><div className="panel"><span className="eyebrow">FAILURE CASES</span><strong className="agent-big-number">{failures.length}</strong><span>investigated Agent failures</span></div><div className="panel"><span className="eyebrow">EVALUATIONS</span><strong className="agent-big-number">{evaluations.length}</strong><span>Baseline / Candidate aggregates</span></div><div className="panel"><span className="eyebrow">DECISIONS</span><strong className="agent-big-number">{decisions.length}</strong><span>decision-only quality records</span></div></section>
    {incidentFailure && <section className="incident-investigation-panel panel" aria-labelledby="incident-investigation-heading"><div className="panel-heading"><div><span className="eyebrow">INCIDENT INVESTIGATION · FACTS FIRST</span><h2 id="incident-investigation-heading">First divergence and dependency attribution</h2></div><StatusTag status="FAILURE CASE" tone="fault" /></div><div className="incident-facts-grid"><div><span>FIRST DIVERGENCE</span><strong className="mono">{displayValue(observation.failing_event_id)}</strong><small>{displayValue(observation.violated_invariant_id)}</small></div><div><span>DEPENDENCY FACT</span><strong>{displayValue(dependencyFacts.dependency_health || dependencyFacts.dependency_health_at_mutation)}</strong><small>{displayValue(dependencyFacts.cause_classification || "external dependency observation")}</small></div><div><span>REMEDIATION SIDE EFFECT</span><strong>{displayValue(sideEffect.executed ? "EXECUTED" : "NOT EXECUTED")}</strong><small>{displayValue(sideEffect.harmful ? "harmful local mutation" : "no harmful local mutation")} · effect {displayValue(sideEffect.effect_count)}</small></div><div><span>VERIFIED LINKS</span><strong>{runs.length} Runs · {regressions.length} Regression(s)</strong><small>{failures[0] ? <a className="action-link" href={failureHref(failures[0].failureCase.failureCaseId)} onClick={(event) => { event.preventDefault(); navigate(failureHref(failures[0].failureCase.failureCaseId)); }}>Open Failure Case →</a> : "—"}</small></div></div><div className="evidence-separation"><div><span className="eyebrow">FACTS</span><p>Service symptom, dependency health, recent change evidence, remediation receipt, and effect count come from the controlled simulation.</p></div><div><span className="eyebrow">VERIFIED</span><p>{displayValue(observation.violated_invariant)} The deterministic verifier and Regression oracle bind the first divergence to the known-bad Agent version.</p></div><div><span className="eyebrow">INFERENCE</span><p>No free-form AI inference is persisted in this view. Any operator conclusion must remain separate from the verified evidence.</p></div></div></section>}
    <section className="agent-linked-lists" aria-label="Agent linked evidence"><div className="panel"><div className="panel-heading"><div><span className="eyebrow">VERSIONS</span><h2>Reviewed configurations</h2></div><span className="section-count">{agent.versions.length}</span></div>{agent.versions.map((version) => <div className="agent-version-row" key={version}><strong>{version}</strong><span>{agent.profiles.join(" · ")}</span></div>)}</div><div className="panel"><div className="panel-heading"><div><span className="eyebrow">LATEST DECISION</span><h2>Quality outcome</h2></div><span className="section-count">{decisions.length}</span></div>{decisions.length ? decisions.slice(-2).map((item) => { const decision = item.releaseDecision; const href = releaseDecisionHref(decision.releaseDecisionId); return <a className="agent-linked-row" key={decision.releaseDecisionId} href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}><strong>{decision.decisionStatus}</strong><span>{decision.evaluatedAgentVersion} · {decision.decisionSubject}</span><span className="row-arrow">→</span></a>; }) : <p className="release-empty-note">No decision record linked.</p>}</div></section>
    <section className="agent-run-links panel" aria-labelledby="agent-run-links-heading"><div className="panel-heading"><div><span className="eyebrow">EXECUTION EVIDENCE</span><h2 id="agent-run-links-heading">Open linked Runs and Regressions</h2></div><span className="section-count">{runs.length + regressions.length} refs</span></div><div className="agent-ref-list">{runs.slice(0, 12).map((run) => <a key={run.run.runId} href={runHref(run.run.runId)} onClick={(event) => { event.preventDefault(); navigate(runHref(run.run.runId)); }}><span className="field-label">RUN · {run.outcome.status}</span><strong className="mono">{shortId(run.run.runId, 34)}</strong><small>{displayValue(run.scenario.case_id || run.scenario.scenario_id)} · {agentIdentity(run.run.agent)}</small></a>)}{regressions.map((item) => <a key={item.regression.regressionId} href={regressionHref(item.regression.regressionId)} onClick={(event) => { event.preventDefault(); navigate(regressionHref(item.regression.regressionId)); }}><span className="field-label">REGRESSION · {item.regression.status}</span><strong className="mono">{shortId(item.regression.regressionId, 34)}</strong><small>{displayValue(item.scenario.scenario_id)} · {displayValue(item.agent.agent_version || item.agent.known_bad_version)}</small></a>)}</div></section>
    <footer className="detail-footer"><span>{agent.agentId} · {agent.domain} · contract-bound</span><span>Read-only · no Agent mutation or release action</span></footer>
  </AppShell>;
}

function agentTextFor(value: unknown, expectedAgentId: string): boolean {
  const record = objectValue(value) || {};
  return record.agent_id === expectedAgentId || record.agent_family === expectedAgentId;
}

function RegressionIndex() {
  return (
    <AppShell regression>
      <div className="page-header index-header">
        <div>
          <span className="eyebrow">REGRESSIONS · HISTORICAL CORPUS</span>
          <h1>Make a validated failure reusable.</h1>
          <p className="lede">Historical Regressions preserve the failure contract, promotion evidence, and focused rerun results as a small read-only test corpus.</p>
        </div>
        <div className="corpus-note">
          <span className="section-label">ACTIVE COLLECTION</span>
          <strong>{reviewedRegressions.length} Regression</strong>
          <span>{reviewedRegressionCollections.length} versioned collections · not Release</span>
        </div>
      </div>
      <section className="corpus-boundary" aria-label="Regression boundary">
        <span className="boundary-mark regression-boundary-mark">↗</span>
        <p><strong>Regression boundary.</strong> A Regression is a versioned, deterministic test asset. A PASS means only that this Candidate passed this Regression; it does not establish overall Agent quality, Suite status, or Release eligibility.</p>
      </section>
      <section className="regression-list-section" aria-labelledby="regression-list-heading">
        <div className="section-heading">
          <div><span className="eyebrow">SELECT A REGRESSION</span><h2 id="regression-list-heading">Historical Regression collection</h2></div>
          <span className="section-count">{reviewedRegressions.length.toString().padStart(2, "0")} records</span>
        </div>
        <div className="regression-list">
          <div className="regression-list-head" aria-hidden="true"><span>STATUS / IDENTITY</span><span>SCENARIO / INVARIANT</span><span>KNOWN-BAD</span><span>FIXED CANDIDATE</span><span /></div>
          {reviewedRegressions.map((item) => {
            const results = getRegressionResults(item.regression.regressionId);
            const knownBad = results.find((result) => isKnownBadProfile(result.result.agentProfile));
            const fixedCandidate = results.find((result) => isFixedCandidateProfile(result.result.agentProfile));
            const href = regressionHref(item.regression.regressionId);
            return <a className="regression-row" key={item.regression.regressionId} href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>
              <div className="regression-row-identity"><StatusTag status="ACTIVE" tone="success" /><strong className="mono">{shortId(item.regression.regressionId, 31)}</strong><span>{item.regression.regressionVersion} · {item.regression.category}</span></div>
              <div><strong>{displayValue(valueAt(item.scenario, "scenario_id"))}@{displayValue(valueAt(item.scenario, "scenario_version"))}</strong><span>{displayValue(valueAt(valueAt(item.contract, "failure_condition"), "violated_invariant_id"))}</span></div>
              <div className="regression-result-cell">{knownBad ? <><StatusTag status={knownBad.result.regressionResult} tone={resultTone(knownBad.result.regressionResult)} /><span>{shortId(knownBad.result.agentVersion, 23)}</span></> : <span>—</span>}</div>
              <div className="regression-result-cell">{fixedCandidate ? <><StatusTag status={fixedCandidate.result.regressionResult} tone={resultTone(fixedCandidate.result.regressionResult)} /><span>{shortId(fixedCandidate.result.agentVersion, 23)}</span></> : <span>—</span>}</div>
              <span className="row-arrow" aria-hidden="true">→</span>
            </a>;
          })}
        </div>
      </section>
      <footer className="page-footnote"><span>Source: {DATA_SOURCE_FOOTNOTE}</span><span>Read-only API adapter · no rerun or release action</span></footer>
    </AppShell>
  );
}

function GateStatus({ name, gate }: { name: string; gate: JsonRecord | null }) {
  const status = typeof gate?.status === "string" ? gate.status : "BLOCKED";
  const checks = objectValue(gate?.checks);
  const passed = checks ? Object.values(checks).filter((value) => value === true).length : 0;
  const total = checks ? Object.keys(checks).length : 0;
  return <div className={`regression-gate ${status === "PASS" ? "pass" : "blocked"}`}><div><span>{humanize(name)}</span><StatusTag status={status} tone={status === "PASS" ? "success" : "fault"} /></div><strong>{passed}/{total} checks</strong><small>{typeof gate?.status === "string" && status === "PASS" ? "evidence satisfied" : "promotion blocked"}</small></div>;
}

function RegressionDetail({ regression }: { regression: Regression }) {
  const results = getRegressionResults(regression.regression.regressionId);
  const failureCase = getFailureCase(regression.sourceFailureCase.failureCaseId);
  const gate = objectValue(regression.promotion.gate);
  const gates = objectValue(gate?.gates);
  const contract = regression.contract;
  const failureCondition = objectValue(valueAt(contract, "failure_condition"));
  const signature = objectValue(valueAt(valueAt(failureCondition, "stable_failure_signature"), "components"));
  const requiredOutcome = objectValue(valueAt(contract, "required_outcome"));
  const initialState = objectValue(valueAt(contract, "initial_state")) || {};
  const seedRequirement = objectValue(valueAt(contract, "seed_requirement")) || {};
  const scenario = objectValue(valueAt(contract, "scenario")) || regression.scenario;
  const forbiddenOutcomes = Array.isArray(valueAt(contract, "forbidden_outcomes")) ? valueAt(contract, "forbidden_outcomes") as unknown[] : [];
  const invariants = Array.isArray(valueAt(contract, "invariants")) ? valueAt(contract, "invariants") as unknown[] : [];
  const safeBehavior = Array.isArray(valueAt(contract, "expected_safe_behavior")) ? valueAt(contract, "expected_safe_behavior") as unknown[] : [];
  const sourceRunRef = runRef(valueAt(regression.sourceFailureCase, "source_run_ref"));
  const reproductionRef = runRef(regression.keyEvidenceRefs.find((item) => item.role === "reproduction")?.ref);
  const sourceCaseHref = failureCase ? failureHref(failureCase.failureCase.failureCaseId) : null;
  const sourceHref = sourceRunRef ? runHref(sourceRunRef.runId, sourceRunRef.eventId) : null;
  const reproductionHref = reproductionRef ? runHref(reproductionRef.runId, reproductionRef.eventId) : null;
  const knownBad = results.find((result) => isKnownBadProfile(result.result.agentProfile));
  const fixedCandidate = results.find((result) => isFixedCandidateProfile(result.result.agentProfile));
  const incident = agentDomain(regression.agent) === "Incident Remediation Agent";
  const gateOrder = ["reproducibility", "relevance", "stability", "non_duplicate", "expected_behavior_explicit"];
  return (
    <AppShell detail regression>
      <div className="detail-breadcrumb">
        <a href="/regressions" onClick={(event) => { event.preventDefault(); navigate("/regressions"); }}>Regressions</a>
        <span aria-hidden="true">/</span>
        <span>{shortId(regression.regression.regressionId, 34)}</span>
        <span className="schema-chip">rpf-regression-v1</span>
      </div>
      <div className="detail-header regression-detail-header">
        <div>
          <span className="eyebrow">HISTORICAL REGRESSION · ACTIVE</span>
          <h1>{incident ? "External dependency remediation Regression." : "Unsafe precondition Regression."}</h1>
          <p className="detail-subtitle">A validated Agent failure was explicitly promoted after independent stability evidence and is now reusable as Regression version {regression.regression.regressionVersion}. The contract is separate from the source Failure Case and every Run.</p>
        </div>
        <div className="detail-header-status"><StatusTag status="ACTIVE" tone="success" /><span className="status-note">Historical Regression · not Release ELIGIBLE</span></div>
      </div>
      <section className="regression-identity-grid" aria-label="Regression identity">
        <IdentityField label="Regression" value={regression.regression.regressionId} mono />
        <IdentityField label="Version" value={regression.regression.regressionVersion} mono note={regression.schemaVersion} />
        <IdentityField label="Scenario" value={`${displayValue(valueAt(regression.scenario, "scenario_id"))}@${displayValue(valueAt(regression.scenario, "scenario_version"))}`} mono />
        <IdentityField label="Agent / domain" value={agentIdentity(regression.agent)} note={agentDomain(regression.agent)} />
        <IdentityField label="Agent type / contract" value={`${agentType(regression.agent)} / ${displayValue(valueAt(regression.agent, "agent_contract_id"))}`} mono />
        <IdentityField label="Invariant" value={shortId(valueAt(failureCondition, "violated_invariant_id"), 34)} mono />
        <IdentityField label="Collection" value={displayValue(valueAt(regression.collectionMembership, "collection_id"))} note={displayValue(valueAt(regression.collectionMembership, "category"))} />
      </section>
      <section className="classification-panel regression-why-panel" aria-labelledby="regression-why-heading">
        <div className="classification-heading"><div><span className="eyebrow">WHY THIS EXISTS · PROMOTION GATE</span><h2 id="regression-why-heading">Stable Agent defect, explicitly promoted</h2></div><span className="classification-badge">{displayValue(valueAt(gate, "status"))}</span></div>
        <p className="classification-copy">The Regression identity is derived from the stable failure signature, scenario, invariant, and action category—not a random source Run ID. The gate recorded all required checks before promotion.</p>
        <div className="regression-why-grid">
          <div><span>Source Failure Case</span><strong className="mono">{shortId(regression.sourceFailureCase.failureCaseId, 32)}</strong>{sourceCaseHref && <a className="action-link" href={sourceCaseHref} onClick={(event) => { event.preventDefault(); navigate(sourceCaseHref); }}>Open Failure Case →</a>}</div>
          <div><span>Stable failure signature</span><strong className="mono">{shortId(valueAt(valueAt(regression.sourceFailureCase, "failure_signature"), "value"), 38)}</strong><small>{displayValue(valueAt(failureCondition, "reason_code"))} · {displayValue(valueAt(failureCondition, "attribution"))}</small></div>
          <div><span>Promotion decision</span><strong className="mono">{shortId(valueAt(regression.promotion, "decision_id"), 38)}</strong><small>{displayValue(valueAt(regression.promotion, "decided_by"))} · {formatDate(String(valueAt(regression.promotion, "decided_at")))}</small></div>
          <div><span>Expected behavior</span><strong>Explicit contract</strong><small>{displayValue(valueAt(requiredOutcome, "run_status"))} + deterministic verifier + independent read-back</small></div>
        </div>
        <div className="regression-gate-grid">{gateOrder.map((name) => <GateStatus key={name} name={name} gate={gates ? objectValue(gates[name]) : null} />)}</div>
      </section>
      <section className="regression-contract-section" aria-labelledby="regression-contract-heading">
        <div className="section-heading"><div><span className="eyebrow">EXPECTED BEHAVIOR · VERSION {regression.regression.regressionVersion}</span><h2 id="regression-contract-heading">What the Agent must prove</h2></div><span className="section-count">no text-only PASS</span></div>
        <div className="regression-contract-grid">
          <div className="regression-contract-card"><span className="field-label">INITIAL STATE / SEED</span><strong className="mono">{incident ? displayValue(valueAt(valueAt(initialState, "service"), "service_id")) : displayValue(initialState.release)}</strong><div><span>{incident ? "dependency" : "revision"}</span><b>{incident ? displayValue(valueAt(valueAt(initialState, "dependency"), "health")) : displayValue(initialState.revision)}</b></div><div><span>seed</span><b className="mono">{displayValue(seedRequirement.seed_revision)}</b></div><div><span>fresh per Run</span><b>{displayValue(seedRequirement.fresh_per_run)}</b></div></div>
          <div className="regression-contract-card"><span className="field-label">SCENARIO / TASK</span><strong>{displayValue(valueAt(scenario, "scenario_id"))}@{displayValue(valueAt(scenario, "scenario_version"))}</strong><p>{displayValue(valueAt(scenario, "task"))}</p></div>
          <div className="regression-contract-card"><span className="field-label">REQUIRED OUTCOME</span><strong className="success-text">{displayValue(valueAt(requiredOutcome, "run_status"))}</strong><p>{incident ? `terminal mode ${displayValue(valueAt(requiredOutcome, "terminal_mode"))} · effect count ${displayValue(valueAt(requiredOutcome, "effect_count"))} · no harmful local remediation` : `release ${displayValue(valueAt(valueAt(requiredOutcome, "actual_state"), "release"))} · revision ${displayValue(valueAt(valueAt(requiredOutcome, "actual_state"), "revision"))} · ${displayValue(valueAt(requiredOutcome, "exactly_one_authorized_mutation")) ? "one mutation" : "contract mismatch"}`}</p></div>
          <div className="regression-contract-card"><span className="field-label">FAILURE CONDITION</span><strong className="failure-text">{displayValue(valueAt(failureCondition, "violated_invariant_id"))}</strong><p>{displayValue(valueAt(failureCondition, "reason_code"))} · {displayValue(valueAt(failureCondition, "attribution"))}</p></div>
        </div>
        <div className="regression-rule-columns">
          <div><h3>Invariants</h3><ul>{invariants.map((item, index) => { const row = objectValue(item); return <li key={`${displayValue(valueAt(row, "id"))}-${index}`}><span className="invariant-icon">✓</span><span><strong>{displayValue(valueAt(row, "id"))}</strong>{displayValue(valueAt(row, "description"))}</span></li>; })}</ul></div>
          <div><h3>Forbidden outcomes</h3><ul>{forbiddenOutcomes.map((item, index) => <li key={`${String(item)}-${index}`}><span className="forbidden-mark">!</span><span>{displayValue(item)}</span></li>)}</ul></div>
          <div><h3>Expected safe behavior</h3><ul>{safeBehavior.map((item, index) => <li key={`${String(item)}-${index}`}><span className="safe-mark">→</span><span>{displayValue(item)}</span></li>)}</ul></div>
        </div>
      </section>
      <section className="regression-history-section" aria-labelledby="regression-history-heading">
        <div className="section-heading"><div><span className="eyebrow">HISTORICAL FAILURE · STABLE REFERENCES</span><h2 id="regression-history-heading">Failure evidence path</h2></div><span className="section-count">source history immutable</span></div>
        <div className="regression-evidence-grid">
          <div className="regression-evidence-card"><span className="field-label">SOURCE FAIL</span><strong className="mono">{shortId(sourceRunRef?.runId, 32)}</strong><span>{refLabel(valueAt(regression.sourceFailureCase, "source_run_ref"))} · original validated evidence</span>{sourceHref && <a className="action-link" href={sourceHref} onClick={(event) => { event.preventDefault(); navigate(sourceHref); }}>Open source event →</a>}</div>
          <div className="regression-evidence-arrow" aria-hidden="true">→</div>
          <div className="regression-evidence-card accent"><span className="field-label">INDEPENDENT REPRODUCTION</span><strong className="mono">{shortId(reproductionRef?.runId, 32)}</strong><span>Fresh Environment · same signature and invariant</span>{reproductionHref && <a className="action-link" href={reproductionHref} onClick={(event) => { event.preventDefault(); navigate(reproductionHref); }}>Open reproduction event →</a>}</div>
        </div>
        <div className="regression-ref-list">{regression.keyEvidenceRefs.map((item, index) => { const ref = runRef(item.ref); const href = ref ? runHref(ref.runId, ref.eventId) : null; return <div className="regression-ref-row" key={`${displayValue(item.role)}-${index}`}><span>{displayValue(item.role)}</span><strong className="mono">{shortId(ref?.runId, 34)}</strong>{href ? <a href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>Open evidence →</a> : <span>stable ref only</span>}</div>; })}</div>
      </section>
      <section className="regression-rerun-section" aria-labelledby="regression-rerun-heading">
        <div className="section-heading"><div><span className="eyebrow">FOCUSED RERUNS · REGRESSION ONLY</span><h2 id="regression-rerun-heading">Known-bad vs fixed Candidate</h2></div><span className="section-count">{results.length} results · no Suite aggregate</span></div>
        <div className="regression-rerun-list">
          {results.map((item) => { const ref = runRef(item.result.runRef); const href = ref ? runHref(ref.runId) : null; const known = isKnownBadProfile(item.result.agentProfile); return <div className={`regression-rerun-row ${known ? "known-bad" : "fixed-candidate"}`} key={item.result.resultId}>
            <div><span className="field-label">{known ? "KNOWN-BAD AGENT" : "FIXED CANDIDATE"}</span><strong>{item.result.agentVersion}</strong><span>{agentDomain(regression.agent)} · {agentIdentity(regression.agent)}</span><span className="mono">{item.result.agentProfile}</span></div>
            <div><span>Run outcome</span><strong>{item.result.runOutcome}</strong><small className="mono">{shortId(ref?.runId, 27)}</small></div>
            <div><span>Regression result</span><StatusTag status={item.result.regressionResult} tone={resultTone(item.result.regressionResult)} /><small>{displayValue(valueAt(item.result.oracle, "reason"))}</small></div>
            <div><span>Release eligibility</span><strong>{item.result.releaseEligibility}</strong><small>not evaluated</small></div>
            {href && <a className="action-link" href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>Open Run →</a>}
          </div>; })}
        </div>
      </section>
      <section className="regression-status-note" aria-label="Regression scope note"><span className="boundary-mark">i</span><p><strong>Scope boundary.</strong> Regression PASS means the fixed Candidate satisfied this Regression's deterministic expected behavior and did not reproduce the historical signature. It does not mean Candidate overall quality, Evaluation Suite PASS, or Release ELIGIBLE.</p></section>
      <footer className="detail-footer"><span>{regression.regression.regressionId}@{regression.regression.regressionVersion} · {regression.regression.category}</span><span>Regression artifact is independent; source Failure Case and Runs remain linked.</span></footer>
    </AppShell>
  );
}

function EvaluationLabel({ evaluation }: { evaluation: EvaluationResult }): string {
  const version = displayValue(evaluation.evaluation.agent.agent_version);
  if (isKnownBadProfile(evaluation.evaluation.agent.configuration_id) || version.includes("known-bad")) return "BASELINE";
  if (isFixedCandidateProfile(evaluation.evaluation.agent.configuration_id) || version.includes("fixed") || version.includes("candidate")) return "CANDIDATE";
  return "EVALUATION";
}

function comparisonForEvaluation(evaluationId: string): EvaluationComparison {
  return reviewedEvaluationComparisons.find((item) => valueAt(item.comparison.baseline, "evaluation_id") === evaluationId || valueAt(item.comparison.candidate, "evaluation_id") === evaluationId) || reviewedEvaluationComparison;
}

function ProgressMeter({ value, label, note }: { value: unknown; label: string; note: string }) {
  const numeric = typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
  return (
    <div className="progress-meter">
      <div className="metric-heading"><span>{label}</span><strong>{formatRate(value)}</strong></div>
      <div className="progress-track" aria-hidden="true"><span style={{ width: `${numeric * 100}%` }} /></div>
      <small>{note}</small>
    </div>
  );
}

function OutcomeDistribution({ counts, label = "OUTCOME DISTRIBUTION" }: { counts: Record<string, number>; label?: string }) {
  const statuses = ["PASS", "FAIL", "ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED"];
  return (
    <div className="distribution-block" aria-label={label}>
      <span className="field-label">{label}</span>
      <div className="distribution-list">
        {statuses.map((status) => <div className={`distribution-item ${status.toLowerCase()}`} key={status}><strong>{counts[status] || 0}</strong><span>{status}</span></div>)}
      </div>
    </div>
  );
}

function EvaluationIndex() {
  const comparison = reviewedEvaluationComparison.comparison;
  return (
    <AppShell evaluation>
      <div className="page-header index-header">
        <div>
          <span className="eyebrow">EVALUATIONS · REVIEWED CORPUS</span>
          <h1>Run the same Suite. Compare the evidence.</h1>
          <p className="lede">A versioned, three-member reliability evaluation keeps quality, evidence coverage, recovery, and performance visible in one read-only control plane.</p>
        </div>
        <div className="corpus-note">
          <span className="section-label">ACTIVE SUITE</span>
          <strong>{reviewedEvaluationSuite.suite.suiteVersion}</strong>
          <span>{reviewedEvaluationSuite.suite.members.length} required members · {reviewedEvaluationSuites.length} Agent suites reviewed</span>
        </div>
      </div>
      <section className="corpus-boundary evaluation-boundary-note" aria-label="Evaluation boundary">
        <span className="boundary-mark">◎</span>
        <p><strong>Evidence boundary.</strong> Evaluation aggregates Run and Regression refs without rewriting them. Agent Quality counts only valid Agent <strong>PASS / FAIL</strong> evidence; coverage remains a separate required-member measure. This surface produces no Release Decision.</p>
      </section>
      <a className="comparison-entry" href={comparisonHref(comparison.comparisonId)} onClick={(event) => { event.preventDefault(); navigate(comparisonHref(comparison.comparisonId)); }}>
        <span className="comparison-entry-mark">⇄</span>
        <span><strong>Baseline vs Candidate comparison</strong><small>Same Suite v{displayValue(valueAt(comparison.suiteRef, "suite_version"))} · {displayValue(comparison.aggregate?.summary)} · evidence-backed, not Release</small></span>
        <span aria-hidden="true">→</span>
      </a>
      <section className="evaluation-list-section" aria-labelledby="evaluation-list-heading">
        <div className="section-heading">
          <div><span className="eyebrow">SELECT AN EVALUATION</span><h2 id="evaluation-list-heading">Independent Suite results</h2></div>
          <span className="section-count">{reviewedEvaluations.length.toString().padStart(2, "0")} records</span>
        </div>
        <div className="evaluation-list">
          <div className="evaluation-list-head" aria-hidden="true"><span>VERSION / STATUS</span><span>SUITE / MEMBERS</span><span>QUALITY / COVERAGE</span><span>REGRESSION / RUNTIME</span><span /></div>
          {reviewedEvaluations.map((evaluation) => <EvaluationRow key={evaluation.evaluation.evaluationId} evaluation={evaluation} />)}
        </div>
      </section>
      <footer className="page-footnote"><span>Source: {DATA_SOURCE_FOOTNOTE}</span><span>Read-only API adapter · no execute or release action</span></footer>
    </AppShell>
  );
}

function EvaluationRow({ evaluation }: { evaluation: EvaluationResult }) {
  const metadata = evaluation.evaluation;
  const coverage = objectValue(valueAt(metadata.summary, "valid_evidence_coverage")) || {};
  const quality = objectValue(valueAt(metadata.summary, "agent_quality")) || {};
  const regression = objectValue(valueAt(metadata.summary, "regression")) || {};
  const regressionCounts = objectValue(valueAt(regression, "result_counts")) || {};
  const href = evaluationHref(metadata.evaluationId);
  return (
    <a className="evaluation-row" href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>
      <div className="evaluation-row-identity">
        <span className="evaluation-kind">{EvaluationLabel({ evaluation })}</span>
        <strong>{agentIdentity(metadata.agent)}</strong>
        <span>{agentDomain(metadata.agent)}</span>
        <span className="mono">{shortId(metadata.evaluationId, 28)}</span>
        <StatusTag status={metadata.evaluationStatus} tone="success" />
      </div>
      <div className="evaluation-row-suite">
        <strong>{displayValue(valueAt(metadata.suiteRef, "suite_id"))}@{displayValue(valueAt(metadata.suiteRef, "suite_version"))}</strong>
        <span>{metadata.memberResults.length} required members <em>·</em> {Object.entries(metadata.outcomeCounts).filter(([, count]) => count > 0).map(([status, count]) => `${count} ${status}`).join(" · ")}</span>
        <span className="row-member-hint">{metadata.memberResults.map((item) => item.itemResult).join("  /  ")}</span>
      </div>
      <div className="evaluation-row-quality">
        <div><span>Agent Quality</span><strong>{formatRate(quality.success_rate)}</strong><small>{displayValue(quality.pass_count)} pass · {displayValue(quality.fail_count)} fail / {displayValue(quality.denominator)}</small></div>
        <div><span>Valid Evidence</span><strong>{formatRate(coverage.coverage_ratio)}</strong><small>{displayValue(coverage.valid_evidence_item_count)}/{displayValue(coverage.required_item_count)} required</small></div>
      </div>
      <div className="evaluation-row-runtime">
        <div><span>Historical Regression</span><strong>{displayValue(regressionCounts.PASS || 0)} PASS <em>·</em> {displayValue(regressionCounts.FAIL || 0)} FAIL</strong></div>
        <div><span>Observed runtime</span><strong>{formatDuration(metadata.durationMs)}</strong><small>{formatDate(metadata.startedAt)} UTC</small></div>
      </div>
      <span className="row-arrow" aria-hidden="true">→</span>
    </a>
  );
}

function EvaluationContext({ evaluation }: { evaluation: EvaluationResult }) {
  const metadata = evaluation.evaluation;
  const coverage = objectValue(valueAt(metadata.summary, "valid_evidence_coverage")) || {};
  const quality = objectValue(valueAt(metadata.summary, "agent_quality")) || {};
  const agentVersion = displayValue(metadata.agent.agent_version);
  return (
    <section className="evaluation-context-panel" aria-label="Evaluation quality and evidence context">
      <div className="evaluation-context-heading"><div><span className="eyebrow">AGGREGATE SEMANTICS · SEPARATE MEASURES</span><h2>Quality is not coverage</h2></div><span className="boundary-chip">NO RELEASE DECISION</span></div>
      <p className="classification-copy">{EvaluationLabel({ evaluation })} <span className="mono">{agentVersion}</span> has a quality rate over valid Agent evidence. Required-member coverage shows whether the Suite produced enough evidence to support that rate; excluded outcomes remain visible below.</p>
      <div className="evaluation-progress-grid">
        <ProgressMeter value={quality.success_rate} label="Agent Quality" note={`${displayValue(quality.pass_count)} PASS · ${displayValue(quality.fail_count)} FAIL · denominator ${displayValue(quality.denominator)}`} />
        <ProgressMeter value={coverage.coverage_ratio} label="Valid Evidence Coverage" note={`${displayValue(coverage.valid_evidence_item_count)} valid / ${displayValue(coverage.required_item_count)} required · ${displayValue(coverage.missing_or_invalid_item_count)} gap`} />
      </div>
      <div className="evaluation-rule-row"><span>Quality denominator</span><strong>PASS / FAIL only</strong><span>Coverage rule</span><strong>Required member with valid Agent judgment</strong></div>
    </section>
  );
}

function EvaluationMatrix({ evaluation }: { evaluation: EvaluationResult }) {
  return (
    <section className="evaluation-matrix-section" aria-labelledby="evaluation-matrix-heading">
      <div className="section-heading"><div><span className="eyebrow">SUITE MEMBERS · STABLE REFS</span><h2 id="evaluation-matrix-heading">Evidence matrix</h2></div><span className="section-count">{evaluation.evaluation.memberResults.length} members · fresh environments</span></div>
      <div className="evaluation-matrix" role="table" aria-label="Evaluation member evidence matrix">
        <div className="evaluation-matrix-head" role="row" aria-hidden="true"><span>MEMBER / CATEGORY</span><span>OUTCOME / ATTRIBUTION</span><span>EVIDENCE</span><span>LATENCY / USAGE</span><span>LINKS</span></div>
        {evaluation.evaluation.memberResults.map((item) => {
          const run = runRef(item.runRef);
          const runLink = run ? runHref(run.runId, run.eventId) : null;
          const regressionId = typeof valueAt(item.regressionRef, "regression_id") === "string" ? String(valueAt(item.regressionRef, "regression_id")) : null;
          const regressionLink = regressionId ? regressionHref(regressionId) : null;
          const usage = item.usage;
          const cost = usage.derived_cost;
          return <div className="evaluation-matrix-row" role="row" key={item.memberId}>
            <div className="matrix-member"><strong>{item.memberId}</strong><span>{item.category} <em>·</em> {item.required ? "required" : "optional"}</span><small>{displayValue(valueAt(item.scenarioRef, "scenario_id"))}@{displayValue(valueAt(item.scenarioRef, "scenario_version"))}</small></div>
            <div className="matrix-outcome"><StatusTag status={item.itemResult} tone={evaluationTone(item.itemResult)} /><strong>{item.attribution}</strong><span>Run {item.runOutcome}{item.recoveryStatus ? ` · ${humanize(item.recoveryStatus)}` : ""}</span></div>
            <div className={`matrix-evidence ${item.validQualityEvidence ? "valid" : "gap"}`}><strong>{item.validEvidenceStatus === "VALID" ? "VALID EVIDENCE" : "EVIDENCE GAP"}</strong><span>{item.validQualityEvidence ? "Counts in Agent Quality" : item.evidenceGapReasons.map(humanize).join(" · ")}</span>{item.regressionResultRef && <small>Regression result linked</small>}</div>
            <div className="matrix-usage"><strong>{formatDuration(item.durationMs)}</strong><span>{formatMetric(usage.reported_tokens, " tok")}</span><small>{cost === null || cost === undefined ? "cost UNKNOWN" : `¥${formatMetric(cost)}`}</small></div>
            <div className="matrix-links">{runLink && <a href={runLink} onClick={(event) => { event.preventDefault(); navigate(runLink); }}>Open Run →</a>}{regressionLink && <a href={regressionLink} onClick={(event) => { event.preventDefault(); navigate(regressionLink); }}>Open Regression →</a>}{!runLink && <span>Run ref only</span>}</div>
          </div>;
        })}
      </div>
      <p className="matrix-note"><strong>Run outcome and item result stay separate.</strong> Historical Regression uses its versioned Regression oracle; Recovery exposes whether the planned Fault was actually triggered and reconciled. Raw Run Evidence remains the drill-down source.</p>
    </section>
  );
}

function EvaluationDetail({ evaluation }: { evaluation: EvaluationResult }) {
  const metadata = evaluation.evaluation;
  const coverage = objectValue(valueAt(metadata.summary, "valid_evidence_coverage")) || {};
  const quality = objectValue(valueAt(metadata.summary, "agent_quality")) || {};
  const metrics = objectValue(valueAt(metadata.summary, "cost_token_latency")) || {};
  const latency = objectValue(valueAt(metrics, "latency")) || {};
  const regressionSummary = objectValue(valueAt(metadata.summary, "regression")) || {};
  const faultSummary = objectValue(valueAt(metadata.summary, "fault_recovery")) || {};
  const comparison = comparisonForEvaluation(metadata.evaluationId).comparison;
  const comparisonLink = comparisonHref(comparison.comparisonId);
  return (
    <AppShell detail evaluation>
      <div className="detail-breadcrumb"><a href="/evaluations" onClick={(event) => { event.preventDefault(); navigate("/evaluations"); }}>Evaluations</a><span aria-hidden="true">/</span><span>{shortId(metadata.evaluationId, 34)}</span><span className="schema-chip">rpf-evaluation-result-v1</span></div>
      <div className="detail-header evaluation-detail-header">
        <div><span className="eyebrow">{EvaluationLabel({ evaluation })} · EVALUATION DETAIL</span><h1>{displayValue(metadata.agent.agent_version)} across {displayValue(valueAt(metadata.suiteRef, "suite_version"))}.</h1><p className="detail-subtitle">{displayValue(valueAt(metadata.summary, "agent_quality") ? "Agent Quality, Recovery, Regression, and evidence coverage remain separate views of the same independent member Runs." : "Evidence aggregate")}</p></div>
        <div className="detail-header-status"><StatusTag status={metadata.evaluationStatus} tone="success" /><span className="status-note">{metadata.memberResults.length} members · read-only reviewed result</span></div>
      </div>
      <section className="identity-strip evaluation-identity-strip" aria-label="Evaluation context identity">
        <IdentityField label="Agent / domain" value={agentIdentity(metadata.agent)} note={agentDomain(metadata.agent)} />
        <IdentityField label="Agent type / contract" value={`${agentType(metadata.agent)} / ${displayValue(metadata.agent.agent_contract_id || "—")}`} mono />
        <IdentityField label="Evaluation" value={metadata.evaluationId} mono note={metadata.evaluationStatus} />
        <IdentityField label="Suite" value={`${displayValue(valueAt(metadata.suiteRef, "suite_id"))}@${displayValue(valueAt(metadata.suiteRef, "suite_version"))}`} mono note={shortId(valueAt(metadata.suiteRef, "member_contract_digest"), 18)} />
        <IdentityField label="Quality" value={formatRate(quality.success_rate)} note={`${displayValue(quality.pass_count)} pass · ${displayValue(quality.fail_count)} fail`} />
        <IdentityField label="Coverage" value={formatRate(coverage.coverage_ratio)} note={`${displayValue(coverage.valid_evidence_item_count)}/${displayValue(coverage.required_item_count)} required`} />
        <IdentityField label="Observed runtime" value={formatDuration(metadata.durationMs)} mono note={`${formatDate(metadata.startedAt)} UTC`} />
      </section>
      <EvaluationContext evaluation={evaluation} />
      <section className="evaluation-facts-grid" aria-label="Evaluation distributions and summary">
        <div className="panel evaluation-fact-panel"><div className="panel-heading"><div><span className="eyebrow">DISTRIBUTION</span><h2>Item outcomes</h2></div><span className="ordering-note">Run / item counts</span></div><OutcomeDistribution counts={metadata.outcomeCounts} /><div className="fact-list compact-fact-list"><div className="fact-row"><span>Run outcomes</span><strong>{Object.entries(metadata.runOutcomeCounts).filter(([, count]) => count > 0).map(([status, count]) => `${count} ${status}`).join(" · ")}</strong></div><div className="fact-row"><span>Evidence gaps</span><strong>{displayValue(coverage.missing_or_invalid_item_count)}</strong></div></div></div>
        <div className="panel evaluation-fact-panel"><div className="panel-heading"><div><span className="eyebrow">FAULT / REGRESSION</span><h2>Reliability signals</h2></div><span className="ordering-note">Contract-specific</span></div><div className="fact-list evaluation-fact-list"><div className="fact-row"><span>Historical Regression</span><strong>{displayValue(valueAt(regressionSummary, "result_counts"))}</strong></div><div className="fact-row"><span>Fault triggered</span><strong>{displayValue(faultSummary.triggered_fault_count)} / {displayValue(faultSummary.planned_fault_count)}</strong></div><div className="fact-row"><span>Fault reconciled</span><strong>{displayValue(faultSummary.reconciled_fault_count)} · recovered PASS {displayValue(faultSummary.recovered_pass_count)}</strong></div><div className="fact-row"><span>Incompleteness</span><strong>{metadata.incompleteOrUnknown.length ? `${metadata.incompleteOrUnknown.length} member gap(s)` : "None"}</strong></div></div></div>
      </section>
      <EvaluationMatrix evaluation={evaluation} />
      <section className="evaluation-performance-panel panel" aria-label="Cost token and latency aggregate"><div className="panel-heading"><div><span className="eyebrow">PERFORMANCE · RAW VS DERIVED</span><h2>Usage and observed latency</h2></div><span className="ordering-note">No Provider invoice inferred</span></div><div className="performance-grid"><div><span>Reported tokens</span><strong>{formatMetric(metrics.reported_token_usage_sum)}</strong><small>{displayValue(metrics.reported_token_usage_item_count)} item(s) reported · {displayValue(metrics.missing_usage_count)} missing</small></div><div><span>Derived cost</span><strong>{metrics.derived_cost_sum === null || metrics.derived_cost_sum === undefined ? "UNKNOWN" : `¥${formatMetric(metrics.derived_cost_sum)}`}</strong><small>{displayValue(metrics.unknown_cost_count)} unknown · missing is not zero</small></div><div><span>Total observed runtime</span><strong>{formatMetric(latency.total_observed_runtime_ms, " ms")}</strong><small>sum of member Run duration</small></div><div><span>Average item latency</span><strong>{formatMetric(latency.average_item_latency_ms, " ms")}</strong><small>{displayValue(latency.known_item_count)} known · derived from Run duration</small></div></div></section>
      {metadata.incompleteOrUnknown.length > 0 && <section className="evaluation-gap-panel" aria-label="Evaluation evidence gaps"><div className="boundary-mark">!</div><div><span className="eyebrow">EVIDENCE GAPS · VISIBLE</span><h2>Some members cannot support Agent Quality</h2>{metadata.incompleteOrUnknown.map((gap) => <div className="evaluation-gap-row" key={String(gap.member_id)}><strong>{displayValue(gap.member_id)}</strong><span>{displayValue(gap.category)}</span><small>{displayValue(gap.reasons)}</small></div>)}</div></section>}
      <section className="evaluation-actions" aria-label="Evaluation navigation"><div><span className="eyebrow">COMPARE CONTEXT</span><h2>Keep the version context continuous.</h2><p>Open the side-by-side Comparison to inspect this Evaluation against the other Agent Version under the same Suite contract.</p></div><a className="primary-action" href={comparisonLink} onClick={(event) => { event.preventDefault(); navigate(comparisonLink); }}>Open Baseline / Candidate comparison →</a></section>
      <details className="raw-details evaluation-raw"><summary>Expert escape hatch · normalized Evaluation JSON</summary><pre>{JSON.stringify(evaluation, null, 2)}</pre></details>
      <footer className="detail-footer"><span>{metadata.evaluationId} · {displayValue(valueAt(metadata.suiteRef, "suite_id"))}@{displayValue(valueAt(metadata.suiteRef, "suite_version"))}</span><span>Runtime {displayValue(metadata.runtime.runtime_version)} · source <span className="mono">{shortId(metadata.runtime.source_sha256, 20)}</span></span></footer>
    </AppShell>
  );
}

function ComparisonMetric({ label, baseline, candidate, delta, note, tone = "neutral" }: { label: string; baseline: string; candidate: string; delta: string; note: string; tone?: "success" | "fault" | "neutral" }) {
  return <div className={`comparison-metric ${tone}`}><span>{label}</span><div><strong>{baseline}</strong><i aria-hidden="true">→</i><strong>{candidate}</strong></div><em>{delta}</em><small>{note}</small></div>;
}

function ComparisonMemberRow({ item }: { item: EvaluationComparisonMember }) {
  const baselineRun = runRef(item.baseline.runRef);
  const candidateRun = runRef(item.candidate.runRef);
  const baselineLink = baselineRun ? runHref(baselineRun.runId, baselineRun.eventId) : null;
  const candidateLink = candidateRun ? runHref(candidateRun.runId, candidateRun.eventId) : null;
  const regressionId = typeof valueAt(item.regressionRef, "regression_id") === "string" ? String(valueAt(item.regressionRef, "regression_id")) : null;
  const regressionLink = regressionId ? regressionHref(regressionId) : null;
  return <div className={`comparison-member-row ${item.classification.toLowerCase()}`}>
    <div className="comparison-member-name"><strong>{item.memberId}</strong><span>{item.category}</span><small>{item.required ? "required" : "optional"}</small></div>
    <div className="comparison-side baseline-side"><span className="side-label">BASELINE</span><StatusTag status={item.baseline.itemResult} tone={evaluationTone(item.baseline.itemResult)} /><strong>{item.baseline.attribution}</strong><small>{item.baseline.validEvidenceStatus === "VALID" ? "valid evidence" : "evidence gap"}</small>{baselineLink && <a href={baselineLink} onClick={(event) => { event.preventDefault(); navigate(baselineLink); }}>Open Run →</a>}</div>
    <div className="comparison-delta"><StatusTag status={item.classification} tone={evaluationTone(item.classification)} /><small>{item.reasons.map(humanize).join(" · ")}</small></div>
    <div className="comparison-side candidate-side"><span className="side-label">CANDIDATE</span><StatusTag status={item.candidate.itemResult} tone={evaluationTone(item.candidate.itemResult)} /><strong>{item.candidate.attribution}</strong><small>{item.candidate.validEvidenceStatus === "VALID" ? "valid evidence" : "evidence gap"}</small>{candidateLink && <a href={candidateLink} onClick={(event) => { event.preventDefault(); navigate(candidateLink); }}>Open Run →</a>}</div>
    <div className="comparison-member-links">{regressionLink && <a href={regressionLink} onClick={(event) => { event.preventDefault(); navigate(regressionLink); }}>Regression contract →</a>}<span>{displayValue(valueAt(item.scenarioRef, "scenario_id"))}@{displayValue(valueAt(item.scenarioRef, "scenario_version"))}</span></div>
  </div>;
}

function ComparisonIndex() {
  return <AppShell comparison>
    <div className="page-header index-header"><div><span className="eyebrow">COMPARISONS · REVIEWED CORPUS</span><h1>See what changed between versions.</h1><p className="lede">A single side-by-side surface keeps member outcomes, evidence sufficiency, regression behavior, and observed cost/latency in the same context.</p></div><div className="corpus-note"><span className="section-label">REVIEWED COMPARISONS</span><strong>{reviewedEvaluationComparisons.length}</strong><span>same Agent contract per comparison · no Release Decision</span></div></div>
    <section className="corpus-boundary comparison-boundary-note" aria-label="Comparison boundary"><span className="boundary-mark">⇄</span><p><strong>Comparison boundary.</strong> Each result is descriptive evidence about two compatible Agent Versions. It never emits <strong>ELIGIBLE</strong>, <strong>BLOCKED</strong>, or deploy authorization.</p></section>
    <section className="comparison-card-list" aria-label="Reviewed comparisons">{reviewedEvaluationComparisons.map((item) => { const comparison = item.comparison; const href = comparisonHref(comparison.comparisonId); const baseline = objectValue(valueAt(comparison.baseline, "agent")); const candidate = objectValue(valueAt(comparison.candidate, "agent")); return <a className="comparison-card" key={comparison.comparisonId} href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}><span className="comparison-entry-mark">⇄</span><span><strong>{shortId(comparison.comparisonId, 33)}</strong><small>{agentDomain(candidate || baseline)} · {agentIdentity(candidate || baseline)} · {displayValue(valueAt(comparison.suiteRef, "suite_id"))}@{displayValue(valueAt(comparison.suiteRef, "suite_version"))}</small></span><StatusTag status={displayValue(comparison.aggregate?.summary)} tone={evaluationTone(String(comparison.aggregate?.summary || ""))} /><span className="row-arrow" aria-hidden="true">→</span></a>; })}</section>
    <footer className="page-footnote"><span>Source: {DATA_SOURCE_FOOTNOTE}</span><span>Read-only · no comparison mutation or release action</span></footer>
  </AppShell>;
}

function ComparisonDetail({ comparison }: { comparison: EvaluationComparison }) {
  const metadata = comparison.comparison;
  const aggregate = metadata.aggregate || {};
  const quality = objectValue(valueAt(aggregate, "agent_quality")) || {};
  const coverage = objectValue(valueAt(aggregate, "valid_evidence_coverage")) || {};
  const performance = objectValue(valueAt(aggregate, "cost_token_latency")) || {};
  const regression = objectValue(valueAt(aggregate, "regression")) || {};
  const recovery = objectValue(valueAt(aggregate, "fault_recovery")) || {};
  const regressionDeltas = Array.isArray(valueAt(regression, "historical_regression_member_deltas")) ? valueAt(regression, "historical_regression_member_deltas") as unknown[] : [];
  const regressionDelta = objectValue(regressionDeltas[0]) || {};
  const regressionRef = objectValue(valueAt(regressionDelta, "regression_ref")) || {};
  const regressionId = String(valueAt(regressionRef, "regression_id") || "");
  const baselineAgent = objectValue(valueAt(metadata.baseline, "agent")) || {};
  const candidateAgent = objectValue(valueAt(metadata.candidate, "agent")) || {};
  const baselineQuality = objectValue(valueAt(quality, "baseline")) || {};
  const candidateQuality = objectValue(valueAt(quality, "candidate")) || {};
  const baselineCoverage = objectValue(valueAt(coverage, "baseline")) || {};
  const candidateCoverage = objectValue(valueAt(coverage, "candidate")) || {};
  const qualityDelta = objectValue(valueAt(quality, "success_rate_delta")) || {};
  const coverageDelta = objectValue(valueAt(coverage, "coverage_ratio_delta")) || {};
  const runtimeDelta = objectValue(valueAt(performance, "total_observed_runtime_ms")) || {};
  const costDelta = objectValue(valueAt(performance, "derived_cost")) || {};
  const tokenDelta = objectValue(valueAt(performance, "reported_tokens")) || {};
  const runtimeDeltaValue = typeof runtimeDelta.delta === "number" ? runtimeDelta.delta : null;
  const baselineEvaluationId = String(valueAt(metadata.baseline, "evaluation_id") || "");
  const candidateEvaluationId = String(valueAt(metadata.candidate, "evaluation_id") || "");
  return <AppShell detail comparison>
    <div className="detail-breadcrumb"><a href="/evaluations" onClick={(event) => { event.preventDefault(); navigate("/evaluations"); }}>Evaluations</a><span aria-hidden="true">/</span><span>{shortId(metadata.comparisonId, 34)}</span><span className="schema-chip">rpf-evaluation-comparison-v1</span></div>
    <div className="detail-header comparison-detail-header"><div><span className="eyebrow">BASELINE ↔ CANDIDATE · COMPARISON</span><h1>{displayValue(aggregate.summary)} across the same Suite.</h1><p className="detail-subtitle">The comparison describes member-level evidence changes between two independent Evaluations. It is not a Quality Policy result or Release Decision.</p></div><div className="detail-header-status"><StatusTag status={metadata.status} tone="success" /><span className="status-note">{displayValue(aggregate.summary)} · no release action</span></div></div>
    <section className="comparison-identity-strip" aria-label="Comparison identity"><div><span>BASELINE AGENT</span><strong>{agentIdentity(baselineAgent)}</strong><small>{agentDomain(baselineAgent)} · {shortId(baselineEvaluationId, 31)}</small></div><div className="comparison-identity-arrow" aria-hidden="true">→</div><div className="candidate-identity"><span>CANDIDATE AGENT</span><strong>{agentIdentity(candidateAgent)}</strong><small>{agentDomain(candidateAgent)} · {shortId(candidateEvaluationId, 31)}</small></div><div><span>SAME SUITE</span><strong>{displayValue(valueAt(metadata.suiteRef, "suite_id"))}</strong><small>version {displayValue(valueAt(metadata.suiteRef, "suite_version"))}</small></div></section>
    <section className="comparison-boundary-panel" aria-label="Comparison result boundary"><span className="boundary-mark">i</span><p><strong>Descriptive comparison only.</strong> Candidate improves the three observed members with full valid evidence coverage in this reviewed corpus. That statement does not grant <strong>ELIGIBLE</strong>, <strong>BLOCKED</strong>, or deployment authority.</p></section>
    <section className="comparison-metrics-section" aria-labelledby="comparison-metrics-heading"><div className="section-heading"><div><span className="eyebrow">AGGREGATE DELTAS · THREE LENSES</span><h2 id="comparison-metrics-heading">Quality, evidence, and observed cost</h2></div><span className="section-count">same members · independent Runs</span></div><div className="comparison-metrics-grid"><ComparisonMetric label="Agent Quality" baseline={formatRate(baselineQuality.success_rate)} candidate={formatRate(candidateQuality.success_rate)} delta={`+${formatRate(qualityDelta.delta)}`} note={`${displayValue(baselineQuality.denominator)} → ${displayValue(candidateQuality.denominator)} valid quality items`} tone="success" /><ComparisonMetric label="Valid Evidence Coverage" baseline={formatRate(baselineCoverage.coverage_ratio)} candidate={formatRate(candidateCoverage.coverage_ratio)} delta={`${coverageDelta.delta === 0 ? "unchanged" : formatRate(coverageDelta.delta)}`} note={`${displayValue(candidateCoverage.valid_evidence_item_count)}/${displayValue(candidateCoverage.required_item_count)} Candidate required`} tone="neutral" /><ComparisonMetric label="Observed Runtime" baseline={formatMetric(valueAt(runtimeDelta, "baseline"), " ms")} candidate={formatMetric(valueAt(runtimeDelta, "candidate"), " ms")} delta={runtimeDeltaValue === null ? "UNKNOWN" : `${runtimeDeltaValue >= 0 ? "+" : ""}${formatMetric(runtimeDeltaValue, " ms")}`} note="derived from independent member Run durations" tone="neutral" /><ComparisonMetric label="Reported Tokens" baseline={formatMetric(valueAt(tokenDelta, "baseline"))} candidate={formatMetric(valueAt(tokenDelta, "candidate"))} delta={tokenDelta.status === "UNKNOWN" ? "UNKNOWN" : formatMetric(tokenDelta.delta)} note="missing Provider usage is not zero" tone="neutral" /><ComparisonMetric label="Derived Cost" baseline={costDelta.status === "UNKNOWN" ? "UNKNOWN" : `¥${formatMetric(valueAt(costDelta, "baseline"))}`} candidate={costDelta.status === "UNKNOWN" ? "UNKNOWN" : `¥${formatMetric(valueAt(costDelta, "candidate"))}`} delta={costDelta.status === "UNKNOWN" ? "UNKNOWN" : `¥${formatMetric(costDelta.delta)}`} note="not a Provider invoice" tone="neutral" /></div></section>
     <section className="comparison-reliability-grid" aria-label="Regression and Recovery comparisons">
       <div className="panel comparison-signal-panel">
         <div className="panel-heading"><div><span className="eyebrow">HISTORICAL REGRESSION</span><h2>Regression behavior</h2></div><span className="ordering-note">contract-linked</span></div>
         <div className="comparison-signal-content"><div><span>Baseline</span><StatusTag status={displayValue(valueAt(regressionDelta, "baseline_result"))} tone="fault" /></div><span className="comparison-signal-arrow">→</span><div><span>Candidate</span><StatusTag status={displayValue(valueAt(regressionDelta, "candidate_result"))} tone="success" /></div></div>
         <p>Existing Regression <a href={regressionHref(regressionId)} onClick={(event) => { event.preventDefault(); navigate(regressionHref(regressionId)); }}>{shortId(regressionId, 32)}</a> stayed version-linked; Baseline FAIL → Candidate PASS is one member improvement.</p>
       </div>
       <div className="panel comparison-signal-panel">
         <div className="panel-heading"><div><span className="eyebrow">RECOVERY / FAULT</span><h2>Response-lost recovery</h2></div><span className="ordering-note">fault evidence visible</span></div>
         <div className="comparison-recovery-grid"><div><span>Baseline recovered PASS</span><strong>{displayValue(valueAt(valueAt(recovery, "recovered_pass_delta"), "baseline"))}</strong><small>{displayValue(valueAt(valueAt(recovery, "baseline"), "not_reached_count"))} not reached</small></div><div><span>Candidate recovered PASS</span><strong>{displayValue(valueAt(valueAt(recovery, "recovered_pass_delta"), "candidate"))}</strong><small>{displayValue(valueAt(valueAt(recovery, "candidate"), "reconciled_fault_count"))} reconciled</small></div></div>
         <p>Recovery is counted from observed planned/triggered/observed/reconciled facts. Fault presence itself is never a FAIL.</p>
       </div>
     </section>
    <section className="comparison-matrix-section" aria-labelledby="comparison-matrix-heading"><div className="section-heading"><div><span className="eyebrow">MEMBER DIFF · FIRST-CLASS</span><h2 id="comparison-matrix-heading">Baseline / Candidate evidence matrix</h2></div><span className="section-count">{metadata.perMemberComparison.length} member comparisons</span></div><div className="comparison-member-list">{metadata.perMemberComparison.map((item) => <ComparisonMemberRow key={item.memberId} item={item} />)}</div><p className="matrix-note"><strong>INCOMPARABLE is explicit.</strong> An ERROR, INVALID, INCONCLUSIVE, CANCELLED, or missing required item can never be rendered as Candidate improvement. Open the linked Run for the underlying timeline.</p></section>
    <section className="comparison-navigation-panel" aria-label="Evaluation navigation"><div><span className="eyebrow">SOURCE EVALUATIONS</span><h2>Open either full Evaluation.</h2><p>Both artifacts use the same Suite/member contract and retain their own independent Run IDs and Environment IDs.</p></div><div className="comparison-navigation-links"><a href={evaluationHref(baselineEvaluationId)} onClick={(event) => { event.preventDefault(); navigate(evaluationHref(baselineEvaluationId)); }}>Open Baseline Evaluation →</a><a href={evaluationHref(candidateEvaluationId)} onClick={(event) => { event.preventDefault(); navigate(evaluationHref(candidateEvaluationId)); }}>Open Candidate Evaluation →</a></div></section>
    <details className="raw-details evaluation-raw"><summary>Expert escape hatch · normalized Comparison JSON</summary><pre>{JSON.stringify(comparison, null, 2)}</pre></details>
    <footer className="detail-footer"><span>{metadata.comparisonId} · {displayValue(valueAt(metadata.suiteRef, "suite_id"))}@{displayValue(valueAt(metadata.suiteRef, "suite_version"))}</span><span>Runtime {displayValue(metadata.runtime.runtime_version)} · source <span className="mono">{shortId(metadata.runtime.source_sha256, 20)}</span></span></footer>
  </AppShell>;
}

function decisionRef(value: unknown): { label: string; href: string } | null {
  const outer = objectValue(value);
  const ref = objectValue(outer?.ref) || outer;
  if (!ref || typeof ref.kind !== "string") return null;
  if (ref.kind === "Run Evidence" && typeof ref.run_id === "string") {
    return { label: `Run ${shortId(ref.run_id, 24)}`, href: runHref(ref.run_id, typeof ref.event_id === "string" ? ref.event_id : null) };
  }
  if (ref.kind === "Evaluation Result" && typeof ref.evaluation_id === "string") {
    return { label: `Evaluation ${shortId(ref.evaluation_id, 24)}`, href: evaluationHref(ref.evaluation_id) };
  }
  if (ref.kind === "Evaluation Comparison" && typeof ref.comparison_id === "string") {
    return { label: `Comparison ${shortId(ref.comparison_id, 24)}`, href: comparisonHref(ref.comparison_id) };
  }
  if (ref.kind === "Regression" && typeof ref.regression_id === "string") {
    return { label: `Regression ${shortId(ref.regression_id, 24)}`, href: regressionHref(ref.regression_id) };
  }
  return null;
}

function DecisionEvidenceRefs({ refs }: { refs: JsonRecord[] }) {
  if (!refs.length) return <span className="release-empty-note">No linked evidence refs</span>;
  return <div className="release-evidence-links">{refs.slice(0, 5).map((ref, index) => {
    const target = decisionRef(ref);
    const role = typeof ref.role === "string" ? ref.role : typeof valueAt(ref.ref, "role") === "string" ? String(valueAt(ref.ref, "role")) : null;
    return target ? <a key={`${target.href}-${index}`} href={target.href} onClick={(event) => { event.preventDefault(); navigate(target.href); }}><span>{role ? humanize(role) : target.label}</span><strong>{target.label}</strong></a> : <span className="release-ref-plain" key={`${String(ref.kind)}-${index}`}><span>{role ? humanize(role) : ref.kind ? String(ref.kind) : "Evidence ref"}</span><strong>{shortId(valueAt(ref, "id") || valueAt(ref, "result_id") || valueAt(ref, "event_id"), 30)}</strong></span>;
  })}</div>;
}

function ReleaseStatusMessage({ status }: { status: string }) {
  if (status === "ELIGIBLE") return <><strong>Eligible for release consideration.</strong> The current Candidate satisfies this Policy and evidence snapshot. This is not a release action.</>;
  if (status === "BLOCKED") return <><strong>Release consideration blocked.</strong> One or more deterministic Hard Gates have a proven violation.</>;
  if (status === "REVIEW_REQUIRED") return <><strong>Human review required.</strong> Required evidence is sufficient, but a deterministic Review Gate requested a decision.</>;
  return <><strong>Decision inconclusive.</strong> Critical evidence is missing or invalid, so the Gate fails closed.</>;
}

function ReleaseDecisionRow({ decision }: { decision: ReleaseDecision }) {
  const metadata = decision.releaseDecision;
  const coverage = metadata.validEvidenceCoverage;
  const regression = objectValue(valueAt(metadata.historicalRegression, "result_counts")) || {};
  const href = releaseDecisionHref(metadata.releaseDecisionId);
  return <a className={`release-decision-row ${metadata.decisionStatus.toLowerCase()}`} href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>
    <div className="release-row-identity"><StatusTag status={metadata.decisionStatus} tone={releaseTone(metadata.decisionStatus)} /><strong>{agentIdentity(metadata.evaluatedAgent)}</strong><span>{agentDomain(metadata.evaluatedAgent)}</span><span className="mono">{shortId(metadata.releaseDecisionId, 28)}</span></div>
    <div><strong>{shortId(valueAt(metadata.policyRef, "policy_identity"), 30)}</strong><span>Suite {displayValue(valueAt(metadata.suiteRef, "suite_version"))} · {metadata.decisionSubject} subject</span></div>
    <div><strong>{formatRate(valueAt(coverage, "coverage_ratio"))}</strong><span>{displayValue(valueAt(coverage, "valid_evidence_item_count"))}/{displayValue(valueAt(coverage, "required_item_count"))} valid evidence</span></div>
    <div><strong>{metadata.blockingReasons.length} blockers · {metadata.reviewReasons.length} review</strong><span>{metadata.softWarnings.length} soft warning(s) · Regression {displayValue(regression.PASS || 0)} PASS / {displayValue(regression.FAIL || 0)} FAIL</span></div>
    <div><strong>{formatDate(metadata.decisionTimestamp)} UTC</strong><span>decision-only · no deployment</span></div>
    <span className="row-arrow" aria-hidden="true">→</span>
  </a>;
}

function ReleaseDecisionIndex() {
  return <AppShell release>
    <div className="page-header index-header"><div><span className="eyebrow">RELEASE DECISIONS · REVIEWED CORPUS</span><h1>Turn evidence into a bounded decision.</h1><p className="lede">A versioned Quality Policy evaluates the same Suite snapshot and keeps blockers, review requirements, warnings, and authorization boundaries explicit.</p></div><div className="corpus-note"><span className="section-label">ACTIVE POLICY</span><strong>{reviewedQualityPolicy.policy.policyVersion}</strong><span>{reviewedReleaseDecisions.length} reviewed decisions · decision-only</span></div></div>
    <section className="corpus-boundary release-boundary-note" aria-label="Release Decision boundary"><span className="boundary-mark">✓</span><p><strong>Release boundary.</strong> <span>ELIGIBLE</span> means only that the Candidate meets the selected Policy and evidence snapshot for release consideration. No release was executed and no deployment was authorized.</p></section>
    <section className="release-decision-list-section" aria-labelledby="release-decision-list-heading"><div className="section-heading"><div><span className="eyebrow">SELECT A DECISION</span><h2 id="release-decision-list-heading">Baseline / Candidate decisions</h2></div><span className="section-count">{reviewedReleaseDecisions.length.toString().padStart(2, "0")} records · same Policy</span></div><div className="release-decision-list"><div className="release-decision-list-head" aria-hidden="true"><span>SUBJECT / STATUS</span><span>POLICY / SUITE</span><span>EVIDENCE COVERAGE</span><span>GATES / REGRESSION</span><span>DECIDED AT</span><span /></div>{reviewedReleaseDecisions.map((decision) => <ReleaseDecisionRow key={decision.releaseDecision.releaseDecisionId} decision={decision} />)}</div></section>
    <footer className="page-footnote"><span>Source: {DATA_SOURCE_FOOTNOTE}</span><span>Read-only API adapter · no release/deploy action</span></footer>
  </AppShell>;
}

function GateRuleRow({ result }: { result: JsonRecord }) {
  const status = typeof result.status === "string" ? result.status : "NOT_EVALUATED";
  const effect = typeof result.effect === "string" ? result.effect : "NONE";
  const gate = typeof result.rule_gate === "string" ? result.rule_gate : "HARD";
  const tone = effect === "BLOCK" ? "fault" : effect === "REVIEW" ? "review" : effect === "WARNING" ? "error" : status === "PASS" ? "success" : "neutral";
  const reasons = Array.isArray(result.reasons) ? result.reasons.map(String) : [];
  const refs = Array.isArray(result.evidence_refs) ? result.evidence_refs.filter((item): item is JsonRecord => Boolean(item && typeof item === "object" && !Array.isArray(item))) : [];
  return <div className={`release-rule-row ${gate.toLowerCase()} ${effect.toLowerCase()}`}>
    <div className="release-rule-label"><span className="rule-gate-label">{gate} GATE</span><strong>{humanize(String(result.rule_id || "rule"))}</strong><small>{humanize(String(result.rule_type || ""))}</small></div>
    <StatusTag status={status} tone={tone} />
    <div className="release-rule-reason"><strong>{reasons.length ? reasons.map(humanize).join(" · ") : effect === "NONE" ? "Policy condition satisfied" : effect}</strong><small>{displayValue(result.evaluation_semantics)}</small></div>
    <DecisionEvidenceRefs refs={refs} />
  </div>;
}

function ReleaseReasonsPanel({ title, eyebrow, reasons, tone, empty }: { title: string; eyebrow: string; reasons: JsonRecord[]; tone: "fault" | "review" | "error"; empty: string }) {
  return <section className={`release-reasons-panel ${tone}`} aria-label={title}><div className="panel-heading"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div><span className="section-count">{reasons.length} item(s)</span></div>{reasons.length ? <div className="release-reasons-list">{reasons.map((reason, index) => <div className="release-reason-card" key={`${String(reason.rule_id)}-${index}`}><div><strong>{humanize(String(reason.code || reason.rule_id || "Rule"))}</strong><span>{displayValue(reason.reason)}</span></div><DecisionEvidenceRefs refs={Array.isArray(reason.evidence_refs) ? reason.evidence_refs.filter((item): item is JsonRecord => Boolean(item && typeof item === "object" && !Array.isArray(item))) : []} /></div>)}</div> : <p className="release-empty-note">{empty}</p>}</section>;
}

function ReleaseDecisionDetail({ decision }: { decision: ReleaseDecision }) {
  const metadata = decision.releaseDecision;
  const gateId = String(valueAt(metadata.gateEvaluationRef, "gate_evaluation_id") || "");
  const gate = getQualityGate(gateId);
  const gateMetadata = gate?.gateEvaluation;
  const candidateEvaluationId = String(valueAt(metadata.candidateEvaluationRef, "evaluation_id") || "");
  const baselineEvaluationId = String(valueAt(metadata.baselineEvaluationRef, "evaluation_id") || "");
  const comparisonId = String(valueAt(metadata.comparisonRef, "comparison_id") || "");
  const regressionId = String(valueAt(metadata.regressionRef, "regression_id") || "");
  const otherDecision = reviewedReleaseDecisions.find((item) => item.releaseDecision.releaseDecisionId !== metadata.releaseDecisionId);
  const coverage = metadata.validEvidenceCoverage;
  const regressionCounts = objectValue(valueAt(metadata.historicalRegression, "result_counts")) || {};
  const recovery = metadata.recoveryFault;
  const policyRefId = String(valueAt(metadata.policyRef, "policy_id") || "");
  const policyRefIdentity = String(valueAt(metadata.policyRef, "policy_identity") || "");
  const policy = reviewedQualityPolicies.find((item) => item.policy.policyId === policyRefId || item.policy.policyIdentity === policyRefIdentity)?.policy || reviewedQualityPolicy.policy;
  return <AppShell detail release>
    <div className="detail-breadcrumb"><a href="/release-decisions" onClick={(event) => { event.preventDefault(); navigate("/release-decisions"); }}>Release Decisions</a><span aria-hidden="true">/</span><span>{shortId(metadata.releaseDecisionId, 34)}</span><span className="schema-chip">rpf-release-decision-v1</span></div>
    <div className="detail-header release-detail-header"><div><span className="eyebrow">{metadata.decisionSubject} · RELEASE DECISION</span><h1>{metadata.evaluatedAgentVersion} is {metadata.decisionStatus}.</h1><p className="detail-subtitle"><ReleaseStatusMessage status={metadata.decisionStatus} /> The decision is tied to one Policy, Suite, Evaluation, Comparison, and Regression evidence snapshot.</p></div><div className="detail-header-status"><StatusTag status={metadata.decisionStatus} tone={releaseTone(metadata.decisionStatus)} /><span className="status-note">{metadata.decisionSubject} · no release action</span></div></div>
    <section className="release-identity-grid" aria-label="Release Decision identity"><IdentityField label="Evaluated Agent" value={agentIdentity(metadata.evaluatedAgent)} note={`${agentDomain(metadata.evaluatedAgent)} · ${metadata.decisionSubject}`} /><IdentityField label="Agent type / contract" value={`${agentType(metadata.evaluatedAgent)} / ${displayValue(metadata.evaluatedAgent.agent_contract_id || "—")}`} mono /><IdentityField label="Policy" value={String(valueAt(metadata.policyRef, "policy_identity"))} mono /><IdentityField label="Suite" value={`${displayValue(valueAt(metadata.suiteRef, "suite_id"))}@${displayValue(valueAt(metadata.suiteRef, "suite_version"))}`} mono /><IdentityField label="Evidence coverage" value={formatRate(valueAt(coverage, "coverage_ratio"))} note={`${displayValue(valueAt(coverage, "valid_evidence_item_count"))}/${displayValue(valueAt(coverage, "required_item_count"))} required`} /><IdentityField label="Gate Evaluation" value={gateId} mono note={gateMetadata?.status || "—"} /><IdentityField label="Decision time" value={formatDate(metadata.decisionTimestamp)} mono /></section>
    <section className={`release-authorization-panel ${metadata.decisionStatus.toLowerCase()}`} aria-label="Release authorization boundary"><span className="boundary-mark">i</span><div><span className="eyebrow">AUTHORIZATION BOUNDARY · EXPLICIT</span><h2><ReleaseStatusMessage status={metadata.decisionStatus} /></h2><p><strong>No release executed / No deployment authorization.</strong> `ELIGIBLE` is a quality decision only. Agent/runtime does not hold Release Authority, and this surface has no deploy action.</p></div></section>
    <section className="release-policy-panel" aria-labelledby="release-policy-heading"><div className="panel-heading"><div><span className="eyebrow">QUALITY POLICY · VERSIONED SEMANTICS</span><h2 id="release-policy-heading">{policy.name}</h2></div><span className="schema-chip">{policy.policyIdentity}</span></div><p className="classification-copy">{policy.purpose}</p><div className="release-policy-facts"><div><span>Compatible Suite</span><strong>{displayValue(valueAt(policy.compatibleSuite, "suite_id"))}@{displayValue(valueAt(policy.compatibleSuite, "suite_version"))}</strong><small>identity-bound evidence snapshot</small></div><div><span>Required evidence</span><strong>{displayValue(valueAt(policy.requiredEvidence, "required_member_count"))} members · {formatRate(valueAt(policy.requiredEvidence, "minimum_coverage_ratio"))}</strong><small>valid Agent PASS / FAIL only</small></div><div><span>Decision precedence</span><strong>Hard → Evidence → Review → Eligible</strong><small>unknown is never zero</small></div><div><span>Configured rules</span><strong>{policy.rules.length} rules · {policy.rules.filter((rule) => rule.gate === "HARD").length} Hard</strong><small>Soft warnings stay visible</small></div></div></section>
    <section className="release-gates-section" aria-labelledby="release-gates-heading"><div className="section-heading"><div><span className="eyebrow">DETERMINISTIC GATE EVALUATION</span><h2 id="release-gates-heading">Policy Gates</h2></div><span className="section-count">{gateMetadata?.ruleResults.length || 0} rule results · {gateMetadata?.status || "unavailable"}</span></div>{gateMetadata ? <div className="release-gates-layout"><div className="release-rule-matrix"><div className="release-rule-head"><span>RULE / TYPE</span><span>RESULT</span><span>SEMANTICS / REASON</span><span>EVIDENCE REFS</span></div>{gateMetadata.ruleResults.map((result, index) => <GateRuleRow key={`${String(result.rule_id)}-${index}`} result={result} />)}</div><aside className="release-gate-summary panel"><div className="panel-heading"><div><span className="eyebrow">FINAL PRECEDENCE</span><h2>{metadata.decisionStatus}</h2></div><StatusTag status={metadata.decisionStatus} tone={releaseTone(metadata.decisionStatus)} /></div><div className="fact-list"><div className="fact-row"><span>Hard blockers</span><strong>{metadata.blockingReasons.length}</strong></div><div className="fact-row"><span>Evidence gaps</span><strong>{metadata.evidenceGapReasons.length}</strong></div><div className="fact-row"><span>Review reasons</span><strong>{metadata.reviewReasons.length}</strong></div><div className="fact-row"><span>Soft warnings</span><strong>{metadata.softWarnings.length}</strong></div></div><p className="release-gate-summary-note">A proven Hard blocker wins over evidence gaps. Evidence gaps fail closed as INCONCLUSIVE. Review is evaluated only after evidence sufficiency.</p></aside></div> : <div className="empty-evidence"><strong>Gate Evaluation unavailable</strong><p>The Release Decision ref does not resolve to the reviewed Gate artifact.</p></div>}</section>
    <section className="release-reason-grid" aria-label="Release Decision diagnostics"><ReleaseReasonsPanel title="Blocking Evidence" eyebrow="HARD GATE · BLOCKING" reasons={metadata.blockingReasons} tone="fault" empty="No deterministic Hard blocker was proven for this decision." /><ReleaseReasonsPanel title="Review Gates" eyebrow="REVIEW GATE · HUMAN JUDGMENT" reasons={metadata.reviewReasons} tone="review" empty="No Review Gate was triggered in this evidence snapshot." /><ReleaseReasonsPanel title="Soft Warnings" eyebrow="SOFT GATE · NON-BLOCKING" reasons={metadata.softWarnings} tone="error" empty="No non-blocking usage or latency warning was recorded." /></section>
    <section className="release-signal-grid" aria-label="Release evidence signals"><div className="panel release-signal-panel"><div className="panel-heading"><div><span className="eyebrow">VALID EVIDENCE COVERAGE</span><h2>Can this decision be supported?</h2></div><span className="status-note">Policy required</span></div><div className="release-big-fact"><strong>{formatRate(valueAt(coverage, "coverage_ratio"))}</strong><span>{displayValue(valueAt(coverage, "valid_evidence_item_count"))} valid / {displayValue(valueAt(coverage, "required_item_count"))} required</span></div><p>Coverage is separate from Agent Quality. ERROR, INVALID, INCONCLUSIVE, or CANCELLED cannot silently become PASS.</p></div><div className="panel release-signal-panel"><div className="panel-heading"><div><span className="eyebrow">HISTORICAL REGRESSION</span><h2>Regression must stay green.</h2></div><StatusTag status={displayValue(regressionCounts.FAIL ? "FAIL" : "PASS")} tone={regressionCounts.FAIL ? "fault" : "success"} /></div><div className="release-big-fact"><strong>{displayValue(regressionCounts.PASS || 0)} PASS</strong><span>{displayValue(regressionCounts.FAIL || 0)} FAIL · {displayValue(valueAt(metadata.historicalRegression, "member_count"))} member</span></div><p>{regressionId ? <>The active Regression remains version-linked. <a className="action-link" href={regressionHref(regressionId)} onClick={(event) => { event.preventDefault(); navigate(regressionHref(regressionId)); }}>Open Regression →</a></> : "No active Regression ref resolved."}</p></div><div className="panel release-signal-panel"><div className="panel-heading"><div><span className="eyebrow">RECOVERY / FAULT</span><h2>Recovery evidence</h2></div><StatusTag status={displayValue(valueAt(recovery, "recovered_pass_count") === 1 ? "PASS" : "INCONCLUSIVE")} tone={valueAt(recovery, "recovered_pass_count") === 1 ? "success" : "error"} /></div><div className="release-big-fact"><strong>{displayValue(valueAt(recovery, "recovered_pass_count"))} recovered</strong><span>{displayValue(valueAt(recovery, "triggered_fault_count"))}/{displayValue(valueAt(recovery, "planned_fault_count"))} triggered · {displayValue(valueAt(recovery, "reconciled_fault_count"))} reconciled</span></div><p>Fault presence is not failure; a required Recovery PASS needs planned, triggered, observed, and reconciled evidence.</p></div></section>
    <section className="release-trace-section" aria-labelledby="release-trace-heading"><div className="section-heading"><div><span className="eyebrow">BOUND EVIDENCE SNAPSHOT · DEEP LINKS</span><h2 id="release-trace-heading">Open the source contracts</h2></div><span className="section-count">stable refs · source artifacts immutable</span></div><div className="release-trace-links">{comparisonId && <a href={comparisonHref(comparisonId)} onClick={(event) => { event.preventDefault(); navigate(comparisonHref(comparisonId)); }}><span>Comparison</span><strong>{shortId(comparisonId, 35)}</strong><small>Baseline / Candidate member diff</small></a>}{candidateEvaluationId && <a href={evaluationHref(candidateEvaluationId)} onClick={(event) => { event.preventDefault(); navigate(evaluationHref(candidateEvaluationId)); }}><span>Candidate Evaluation</span><strong>{shortId(candidateEvaluationId, 35)}</strong><small>three-member evidence matrix</small></a>}{baselineEvaluationId && <a href={evaluationHref(baselineEvaluationId)} onClick={(event) => { event.preventDefault(); navigate(evaluationHref(baselineEvaluationId)); }}><span>Baseline Evaluation</span><strong>{shortId(baselineEvaluationId, 35)}</strong><small>known-bad evidence matrix</small></a>}{regressionId && <a href={regressionHref(regressionId)} onClick={(event) => { event.preventDefault(); navigate(regressionHref(regressionId)); }}><span>Historical Regression</span><strong>{shortId(regressionId, 35)}</strong><small>active Regression contract</small></a>}</div></section>
    <section className="release-history-panel" aria-label="Release Decision history"><div className="panel-heading"><div><span className="eyebrow">HISTORICAL FACT · IMMUTABLE</span><h2>Decision history stays additive.</h2></div><span className="schema-chip">immutable: {displayValue(valueAt(metadata.history, "immutable"))}</span></div><p>Later evidence or a new Policy Version must create a new Release Decision. This artifact is never silently overwritten.{metadata.history.supersedes_decision_id ? ` It supersedes ${metadata.history.supersedes_decision_id}.` : ""}</p>{otherDecision && <p className="release-other-decision">Related reviewed decision: <a className="action-link" href={releaseDecisionHref(otherDecision.releaseDecision.releaseDecisionId)} onClick={(event) => { event.preventDefault(); navigate(releaseDecisionHref(otherDecision.releaseDecision.releaseDecisionId)); }}>{otherDecision.releaseDecision.decisionStatus} · {otherDecision.releaseDecision.evaluatedAgentVersion} →</a></p>}</section>
    <details className="raw-details evaluation-raw"><summary>Expert escape hatch · normalized Release Decision JSON</summary><pre>{JSON.stringify(decision, null, 2)}</pre></details>
    <footer className="detail-footer"><span>{metadata.releaseDecisionId} · {metadata.decisionStatus} · {policy.policyIdentity}</span><span>Policy/runtime source <span className="mono">{shortId(valueAt(metadata.sourceIdentity, "source_sha256"), 20)}</span> · no release executed</span></footer>
  </AppShell>;
}

function failureCaseIdFromRef(value: unknown): string | null {
  const ref = objectValue(value);
  return typeof ref?.failure_case_id === "string" ? ref.failure_case_id : null;
}

function intelligenceClusterFor(analysis: FailureIntelligence): FailureCluster | undefined {
  const familyValue = valueAt(analysis.intelligence.familySignatures.crossAgent, "value");
  return reviewedFailureClusters.find((cluster) => valueAt(cluster.cluster.familySignature, "value") === familyValue);
}

function FailureIntelligenceIndex() {
  const exactGroups = new Set(
    reviewedFailureIntelligence
      .map((item) => valueAt(valueAt(item.intelligence.recurrence, "exact_dedup"), "group_key"))
      .filter((value): value is string => typeof value === "string"),
  );
  const agentAnalyses = reviewedFailureIntelligence.filter((item) => valueAt(item.intelligence.deterministicAttribution, "responsibility_layer") === "AGENT");
  const domains = new Set(agentAnalyses.map((item) => agentDomain(item.intelligence.agent)));
  const covered = agentAnalyses.filter((item) => valueAt(item.intelligence.regressionLinkage, "status") === "COVERED").length;
  const recurring = agentAnalyses.filter((item) => Number(valueAt(item.intelligence.recurrence, "occurrence_count") || 0) > 1).length;
  const unresolved = reviewedFailureIntelligence.filter((item) => valueAt(item.intelligence.deterministicAttribution, "status") === "UNRESOLVED").length;
  return (
    <AppShell intelligence>
      <div className="page-header index-header">
        <div>
          <span className="eyebrow">FAILURE INTELLIGENCE · DETERMINISTIC DERIVATION</span>
          <h1>Find the reliability pattern behind a failure.</h1>
          <p className="lede">An evidence-first investigation index: deterministic attribution, exact recurrence identity, structural families, version localization, and a human-review recommendation.</p>
        </div>
        <div className="corpus-note"><span className="section-label">DERIVATION</span><strong>v1 deterministic</strong><span>no LLM attribution · no auto-promotion</span></div>
      </div>
      <section className="corpus-boundary intelligence-boundary" aria-label="Failure Intelligence boundary">
        <span className="boundary-mark">⌁</span>
        <p><strong>Derived index boundary.</strong> Facts remain in immutable Run, Failure Case, and Regression artifacts. This surface stores explainable derived values only; a recommendation is not a promotion or release decision.</p>
      </section>
      <section className="fi-metric-grid" aria-label="Failure Intelligence summary">
        <div className="panel"><span className="eyebrow">TOTAL FAILURES</span><strong>{reviewedFailureIntelligence.length}</strong><span>including three negative controls</span></div>
        <div className="panel"><span className="eyebrow">EXACT DEDUP</span><strong>{exactGroups.size}</strong><span>Agent recurrence identities</span></div>
        <div className="panel"><span className="eyebrow">STRUCTURAL FAMILIES</span><strong>{reviewedFailureClusters.length}</strong><span>{domains.size} Agent domains · {recurring} recurring</span></div>
        <div className="panel"><span className="eyebrow">REGRESSION COVERAGE</span><strong>{covered}/{agentAnalyses.length}</strong><span>{unresolved} unresolved attribution</span></div>
      </section>
      <section className="fi-investigation-section" aria-labelledby="fi-investigation-heading">
        <div className="section-heading"><div><span className="eyebrow">INVESTIGATION QUEUE</span><h2 id="fi-investigation-heading">Failure records and derived recommendation</h2></div><span className="section-count">facts → derived analysis</span></div>
        <div className="fi-table" role="table" aria-label="Failure Intelligence records">
          <div className="fi-table-head" role="row"><span>FAILURE / DOMAIN</span><span>ATTRIBUTION / DIVERGENCE</span><span>FAMILY</span><span>RECURRENCE / REGRESSION</span><span>RECOMMENDATION</span></div>
          {reviewedFailureIntelligence.map((item) => {
            const metadata = item.intelligence;
            const caseId = failureCaseIdFromRef(metadata.sourceFailureCaseRef);
            const caseLink = caseId ? failureHref(caseId) : null;
            const cluster = intelligenceClusterFor(item);
            const clusterLink = cluster ? clusterHref(cluster.cluster.clusterId) : null;
            const sourceRun = typeof metadata.sourceRunRef.run_id === "string" ? metadata.sourceRunRef.run_id : "";
            const responsibility = displayValue(valueAt(metadata.deterministicAttribution, "responsibility_layer"));
            const recommendation = displayValue(valueAt(metadata.recommendation, "value"));
            return <div className="fi-table-row" key={metadata.intelligenceId} role="row">
              <div><strong className="mono">{shortId(metadata.intelligenceId, 25)}</strong><span>{agentDomain(metadata.agent)} · {caseLink ? <a href={caseLink} onClick={(event) => { event.preventDefault(); navigate(caseLink); }}>Failure Case →</a> : "negative control"}</span></div>
              <div><StatusTag status={responsibility} tone={responsibility === "AGENT" ? "fault" : "neutral"} /><strong>{displayValue(valueAt(metadata.agentFailureTaxonomy, "agent_failure_class"))}</strong><span>{displayValue(valueAt(metadata.firstMeaningfulDivergence, "phase"))} · {shortId(valueAt(metadata.firstMeaningfulDivergence, "event_id"), 24)}</span></div>
              <div>{clusterLink ? <a className="action-link" href={clusterLink} onClick={(event) => { event.preventDefault(); navigate(clusterLink); }}>{displayValue(valueAt(valueAt(metadata.familySignatures.crossAgent, "features"), "reliability_pattern"))} →</a> : <span className="muted">No Agent family</span>}<small>{displayValue(valueAt(valueAt(metadata.familySignatures.domain, "features"), "invariant_family"))}</small></div>
              <div><strong>{displayValue(valueAt(metadata.recurrence, "occurrence_count"))} occurrences</strong><span>{displayValue(valueAt(metadata.regressionLinkage, "status"))}</span><small className="mono">{shortId(sourceRun, 24)}</small></div>
              <div><StatusTag status={recommendation} tone={intelligenceRecommendationTone(recommendation)} /><small>{displayValue(valueAt(metadata.recommendation, "next_action"))}</small></div>
            </div>;
          })}
        </div>
      </section>
      <section className="fi-lower-grid" aria-label="Failure family and version localization index">
        <div className="panel"><div className="panel-heading"><div><span className="eyebrow">STRUCTURAL FAMILY EXPLORER</span><h2>Clusters</h2></div><span className="section-count">{reviewedFailureClusters.length}</span></div><div className="fi-link-list">{reviewedFailureClusters.map((cluster) => { const href = clusterHref(cluster.cluster.clusterId); return <a key={cluster.cluster.clusterId} href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}><span><strong>{displayValue(valueAt(cluster.cluster.familySignature, "features") && valueAt(valueAt(cluster.cluster.familySignature, "features"), "reliability_pattern"))}</strong><small>{cluster.cluster.clusterLevel} · {cluster.cluster.agentDomains.join(" · ")}</small></span><b>{cluster.cluster.occurrenceCount}</b><span className="row-arrow">→</span></a>; })}</div></div>
        <div className="panel"><div className="panel-heading"><div><span className="eyebrow">VERSION LOCALIZATION</span><h2>Bisect evidence</h2></div><span className="section-count">{reviewedVersionBisects.length}</span></div><div className="fi-link-list">{reviewedVersionBisects.map((bisect) => { const href = bisectHref(bisect.bisect.bisectId); return <a key={bisect.bisect.bisectId} href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}><span><strong>{bisect.bisect.agentDomain}</strong><small>{displayValue(valueAt(bisect.bisect.monotonicity, "status"))} · {bisect.bisect.probeHistory.length} probes</small></span><b>{bisect.bisect.firstBadCandidate ? "FIRST BAD" : "INCONCLUSIVE"}</b><span className="row-arrow">→</span></a>; })}</div></div>
      </section>
      <section className="evidence-separation fi-evidence-separation" aria-label="Failure Intelligence evidence layers"><div><span className="eyebrow">FACTS</span><p>Outcome, health boundary, event refs, exact signature, and Regression results are read from source artifacts.</p></div><div><span className="eyebrow">DERIVED DETERMINISTIC ANALYSIS</span><p>Taxonomy, first divergence phase, structural family, recurrence, bisect status, and recommendation are rule-backed and versioned.</p></div><div><span className="eyebrow">AI ANALYSIS</span><p>Not implemented in RPF-17. No probability or free-form root-cause claim is persisted.</p></div></section>
      <footer className="page-footnote"><span>Source: {DATA_SOURCE_FOOTNOTE} · {reviewedFailureIntelligence[0]?.intelligence.sourceIdentity.source_sha256 ? "source-bound" : "derived"}</span><span>Read-only investigation · no promote, rerun, or release action</span></footer>
    </AppShell>
  );
}

function FailureClusterDetail({ cluster }: { cluster: FailureCluster }) {
  const features = objectValue(valueAt(cluster.cluster.familySignature, "features")) || {};
  return <AppShell intelligence detail>
    <div className="detail-breadcrumb"><a href={intelligenceHref()} onClick={(event) => { event.preventDefault(); navigate(intelligenceHref()); }}>Failure Intelligence</a><span aria-hidden="true">/</span><span>{shortId(cluster.cluster.clusterId, 36)}</span><span className="schema-chip">rpf-failure-cluster-v1</span></div>
    <div className="detail-header"><div><span className="eyebrow">CLUSTER INVESTIGATION · {cluster.cluster.clusterLevel}</span><h1>{displayValue(features.reliability_pattern)}</h1><p className="detail-subtitle">Stable family identity is derived from normalized evidence features. Members retain separate exact Failure Case and Run identities.</p></div><div className="detail-header-status"><StatusTag status={cluster.cluster.status} tone="success" /><span className="status-note">{cluster.cluster.occurrenceCount} occurrences · {cluster.cluster.agentDomains.join(" · ")}</span></div></div>
    <section className="identity-strip" aria-label="Cluster identity"><IdentityField label="Cluster ID" value={cluster.cluster.clusterId} mono /><IdentityField label="Family signature" value={String(valueAt(cluster.cluster.familySignature, "value") || "—")} mono note={String(valueAt(cluster.cluster.familySignature, "signature_version") || "—")} /><IdentityField label="Level" value={cluster.cluster.clusterLevel} /><IdentityField label="Occurrences" value={String(cluster.cluster.occurrenceCount)} note={`${cluster.cluster.firstSeen} → ${cluster.cluster.lastSeen}`} /><IdentityField label="Regression coverage" value={String(cluster.cluster.regressionCoverage.length)} note="linked canonical Regression refs" /></section>
    <section className="fi-detail-grid"><div className="panel"><div className="panel-heading"><div><span className="eyebrow">NORMALIZED FEATURES</span><h2>Why these members relate</h2></div><span className="schema-chip">deterministic</span></div><div className="fact-list">{Object.entries(features).map(([key, value]) => <div className="fact-row" key={key}><span>{humanize(key)}</span><strong className="mono">{displayValue(value)}</strong></div>)}</div></div><div className="panel"><div className="panel-heading"><div><span className="eyebrow">ATTRIBUTION RULE</span><h2>Evidence boundary</h2></div><StatusTag status="RULE-BACKED" tone="success" /></div><p className="classification-copy">This cluster is only built for resolved Agent responsibility. Environment, Provider, Platform, and INVALID controls are excluded from Agent clusters and keep their own NOT_AGENT_FAILURE recommendation.</p><div className="fact-list"><div className="fact-row"><span>Taxonomy</span><strong>{cluster.cluster.taxonomyVersion}</strong></div><div className="fact-row"><span>Unresolved members</span><strong>{cluster.cluster.unresolvedMemberCount}</strong></div><div className="fact-row"><span>Invariant families</span><strong>{cluster.cluster.invariantFamilies.join(" · ")}</strong></div></div></div></section>
    <section className="fi-members-section" aria-labelledby="fi-members-heading"><div className="section-heading"><div><span className="eyebrow">MEMBER FAILURE CASES</span><h2 id="fi-members-heading">Exact identities remain separate</h2></div><span className="section-count">{cluster.cluster.memberRefs.length} Intelligence members</span></div><div className="fi-member-list">{cluster.cluster.memberRefs.map((member, index) => { const caseId = failureCaseIdFromRef(member.failure_case_ref); const analysisId = typeof valueAt(member.intelligence_ref, "intelligence_id") === "string" ? String(valueAt(member.intelligence_ref, "intelligence_id")) : null; const analysis = analysisId ? reviewedFailureIntelligence.find((item) => item.intelligence.intelligenceId === analysisId) : undefined; const caseLink = caseId ? failureHref(caseId) : null; const runId = typeof valueAt(analysis?.intelligence.sourceRunRef, "run_id") === "string" ? String(valueAt(analysis?.intelligence.sourceRunRef, "run_id")) : null; const runLink = runId ? runHref(runId) : null; return <div className="fi-member-row" key={`${analysisId || "member"}-${index}`}><div><span className="field-label">MEMBER {index + 1}</span><strong>{caseId ? shortId(caseId, 34) : "negative / unresolved"}</strong><small>{analysis ? agentDomain(analysis.intelligence.agent) : "—"}</small></div><div><span>Exact signature</span><strong className="mono">{shortId(valueAt(member.exact_signature, "value"), 28)}</strong><small>not the family signature</small></div><div><span>First divergence</span><strong>{displayValue(valueAt(analysis?.intelligence.firstMeaningfulDivergence, "phase"))}</strong><small className="mono">{shortId(valueAt(analysis?.intelligence.firstMeaningfulDivergence, "event_id"), 30)}</small></div><div>{caseLink && <a className="action-link" href={caseLink} onClick={(event) => { event.preventDefault(); navigate(caseLink); }}>Open Failure Case →</a>}{runLink && <a className="action-link" href={runLink} onClick={(event) => { event.preventDefault(); navigate(runLink); }}>Open source Run →</a>}</div></div>; })}</div></section>
    <section className="fi-detail-links panel"><div className="panel-heading"><div><span className="eyebrow">REGRESSION COVERAGE</span><h2>Canonical links</h2></div><span className="section-count">{cluster.cluster.regressionCoverage.length}</span></div>{cluster.cluster.regressionCoverage.length ? <div className="fi-link-list">{cluster.cluster.regressionCoverage.map((ref, index) => { const id = typeof ref.regression_id === "string" ? ref.regression_id : null; const href = id ? regressionHref(id) : null; return <div key={`${id || "regression"}-${index}`}>{id && href ? <a href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}><span><strong>{shortId(id, 40)}</strong><small>existing immutable Regression coverage</small></span><span className="row-arrow">→</span></a> : <span>{displayValue(ref)}</span>}</div>; })}</div> : <p className="release-empty-note">No Regression coverage is linked; recommendation remains a derived suggestion.</p>}</section>
    <footer className="detail-footer"><span>{cluster.cluster.clusterId} · {cluster.cluster.clusterLevel} · immutable members</span><span>Facts and derived deterministic analysis are shown separately · no AI Analysis</span></footer>
  </AppShell>;
}

function VersionBisectDetail({ bisect }: { bisect: VersionBisect }) {
  const monotonicStatus = String(valueAt(bisect.bisect.monotonicity, "status") || "INCONCLUSIVE");
  const firstBad = bisect.bisect.firstBadCandidate;
  const regressionId = typeof valueAt(bisect.bisect.regressionRef, "regression_id") === "string" ? String(valueAt(bisect.bisect.regressionRef, "regression_id")) : null;
  const regressionLink = regressionId ? regressionHref(regressionId) : null;
  return <AppShell intelligence detail>
    <div className="detail-breadcrumb"><a href={intelligenceHref()} onClick={(event) => { event.preventDefault(); navigate(intelligenceHref()); }}>Failure Intelligence</a><span aria-hidden="true">/</span><span>{shortId(bisect.bisect.bisectId, 36)}</span><span className="schema-chip">rpf-version-bisect-v1</span></div>
    <div className="detail-header"><div><span className="eyebrow">VERSION LOCALIZATION · CONTROLLED CANDIDATE LINE</span><h1>{bisect.bisect.agentDomain}</h1><p className="detail-subtitle">The candidate order and Regression oracle are explicit. Only a monotonic PASS/FAIL boundary can produce a first-bad candidate.</p></div><div className="detail-header-status"><StatusTag status={bisect.bisect.status} tone={monotonicStatus === "MONOTONIC_ASSUMPTION_HOLDS" ? "success" : "review"} /><span className="status-note">{bisect.bisect.probeHistory.length} probes · {monotonicStatus}</span></div></div>
    <section className="identity-strip" aria-label="Bisect identity"><IdentityField label="Bisect ID" value={bisect.bisect.bisectId} mono /><IdentityField label="Regression" value={regressionId || "—"} mono note={bisect.bisect.regressionVersion || "—"} /><IdentityField label="Known good" value={String(valueAt(bisect.bisect.knownGoodBoundary, "agent_version") || "—")} /><IdentityField label="Known bad" value={String(valueAt(bisect.bisect.knownBadBoundary, "agent_version") || "—")} /><IdentityField label="First bad" value={String(valueAt(firstBad, "agent_version") || "INCONCLUSIVE")} note={firstBad ? "boundary proven under common oracle" : "fail closed"} /></section>
    <section className="corpus-boundary bisect-boundary" aria-label="Bisect monotonicity boundary"><span className="boundary-mark">↕</span><p><strong>{monotonicStatus}.</strong> {displayValue(valueAt(bisect.bisect.monotonicity, "assumption"))}. {bisect.bisect.stopReason || "The first bad candidate is shown only because the observed line contains one PASS → FAIL transition."} {regressionLink && <><a className="action-link" href={regressionLink} onClick={(event) => { event.preventDefault(); navigate(regressionLink); }}>Open target Regression →</a></>}</p></section>
    <section className="fi-bisect-section" aria-labelledby="fi-bisect-heading"><div className="section-heading"><div><span className="eyebrow">PROBE HISTORY</span><h2 id="fi-bisect-heading">Ordered Candidate Version / Profile line</h2></div><span className="section-count">same oracle · same contract</span></div><div className="fi-bisect-table"><div className="fi-table-head"><span>ORDER / CANDIDATE</span><span>VERSION / PROFILE</span><span>REGRESSION ORACLE</span><span>RUN EVIDENCE</span><span>RESULT</span></div>{bisect.bisect.probeHistory.map((probe, index) => { const candidate = objectValue(probe.candidate) || {}; const ref = runRef(probe.run_ref); const href = ref ? runHref(ref.runId) : null; const status = displayValue(probe.regression_result); return <div className="fi-table-row" key={`${String(valueAt(candidate, "candidate_id"))}-${index}`}><div><strong>{displayValue(probe.candidate_order)}</strong><span>{displayValue(valueAt(candidate, "candidate_id"))}</span></div><div><strong>{displayValue(valueAt(candidate, "agent_version"))}</strong><span className="mono">{displayValue(valueAt(candidate, "agent_profile"))}</span></div><div><strong>{displayValue(probe.oracle_id)}</strong><span>{displayValue(probe.probe_status)}</span></div><div>{href ? <a className="action-link" href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>Open Run →</a> : <span className="muted">stable ref only</span>}<small className="mono">{shortId(ref?.runId, 25)}</small></div><div><StatusTag status={status} tone={status === "PASS" ? "success" : status === "FAIL" ? "fault" : "review"} /></div></div>; })}</div></section>
    <section className="fi-detail-grid"><div className="panel"><div className="panel-heading"><div><span className="eyebrow">COMPATIBILITY</span><h2>Common oracle boundary</h2></div><StatusTag status={String(valueAt(bisect.bisect.compatibleContract, "same_regression_oracle") === true ? "COMPATIBLE" : "INCONCLUSIVE")} tone={valueAt(bisect.bisect.compatibleContract, "same_regression_oracle") === true ? "success" : "review"} /></div><div className="fact-list"><div className="fact-row"><span>Scenario</span><strong>{displayValue(valueAt(bisect.bisect.compatibleContract.scenario_ref, "scenario_id"))}@{displayValue(valueAt(bisect.bisect.compatibleContract.scenario_ref, "scenario_version"))}</strong></div><div className="fact-row"><span>Contract</span><strong className="mono">{displayValue(bisect.bisect.compatibleContract.contract_identity)}</strong></div><div className="fact-row"><span>Oracle</span><strong className="mono">{displayValue(bisect.bisect.compatibleContract.oracle_id)}</strong></div></div></div><div className="panel"><div className="panel-heading"><div><span className="eyebrow">STOP RULE</span><h2>Fail closed on uncertainty</h2></div><span className="schema-chip">no false first bad</span></div><p className="classification-copy">Platform ERROR, INVALID, INCONCLUSIVE, incompatible contract, or a non-monotonic line cannot be interpreted as PASS/FAIL. RPF-17 records the stop reason and recommends a full scan.</p><strong>{bisect.bisect.fullScanRecommended ? "Full scan recommended" : "Boundary localized under stated assumption"}</strong></div></section>
    <footer className="detail-footer"><span>{bisect.bisect.bisectId} · {bisect.bisect.agentDomain}</span><span>Bisect is evidence localization only · no Agent code or Regression mutation</span></footer>
  </AppShell>;
}

function FailureIndex() {
  return (
    <AppShell failure>
      <div className="page-header index-header">
        <div>
          <span className="eyebrow">FAILURE CASES · REVIEWED CORPUS</span>
          <h1>Follow a real failure through reproduction.</h1>
          <p className="lede">Failure Cases keep source evidence, independent reproduction, validation, and any additive promotion link together.</p>
        </div>
        <div className="corpus-note">
          <span className="section-label">ACTIVE CASES</span>
          <strong>{reviewedFailureCases.length} promoted</strong>
          <span>validated history retained</span>
        </div>
      </div>
      <section className="corpus-boundary" aria-label="Failure Case boundary">
        <span className="boundary-mark">!</span>
        <p><strong>Workflow boundary.</strong> A validated Failure Case remains its own immutable investigation asset. Promotion is explicit and additive: the case keeps its validated history while pointing to a separate Regression artifact.</p>
      </section>
      <section className="case-list-section" aria-labelledby="failure-list-heading">
        <div className="section-heading">
          <div><span className="eyebrow">SELECT A CASE</span><h2 id="failure-list-heading">Reviewed Failure Cases</h2></div>
          <span className="section-count">{reviewedFailureCases.length.toString().padStart(2, "0")} records</span>
        </div>
        <div className="case-list">
          {reviewedFailureCases.map((item) => {
            const href = failureHref(item.failureCase.failureCaseId);
            return <a className="case-row" key={item.failureCase.failureCaseId} href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>
              <div><StatusTag status={item.failureCase.currentStatus.toUpperCase()} tone="success" /><span className="signal-label">source FAIL · reproduction matched</span></div>
              <div><strong>{agentIdentity(item.agent)}</strong><span>{agentDomain(item.agent)} · {displayValue(item.scenario.scenario_id)}@{displayValue(item.scenario.scenario_version)}</span></div>
              <div><strong className="mono">{shortId(item.failureSignature.value, 24)}</strong><span>{displayValue(item.failureSignature.components.violated_invariant_id)}</span></div>
              <div><strong>Promoted to Regression</strong><span>{item.reproductionAttempts.length} reproduction attempt · validated history retained</span></div>
              <span className="row-arrow" aria-hidden="true">→</span>
            </a>;
          })}
        </div>
      </section>
      <footer className="page-footnote"><span>Source: {DATA_SOURCE_FOOTNOTE}</span><span>Read-only API adapter · no promote action</span></footer>
    </AppShell>
  );
}

function executionStatusTone(state: string): "success" | "fault" | "error" | "neutral" | "review" {
  if (state === "COMPLETED") return "success";
  if (state === "FAILED_PLATFORM") return "error";
  if (state === "CANCELLED") return "fault";
  if (state === "RECONCILE_REQUIRED") return "review";
  return "neutral";
}

function executionStateNote(state: string): string {
  switch (state) {
    case "QUEUED": return "Awaiting a worker claim";
    case "CLAIMED": return "Claimed; Agent start not yet proven";
    case "RUNNING": return "Worker execution in progress";
    case "CANCEL_REQUESTED": return "Cancellation requested; awaiting safe ack";
    case "RECONCILE_REQUIRED": return "Side-effect outcome is uncertain · blind retry prohibited";
    case "COMPLETED": return "Terminal evidence committed";
    case "FAILED_PLATFORM": return "Platform boundary · not Agent FAIL";
    case "CANCELLED": return "Terminal cancellation evidence committed";
    default: return "Unknown execution state";
  }
}

function executionTargetHref(target: ExecutionJobDto["target"] | null | undefined): string | null {
  if (!target || typeof target.id !== "string" || !target.id) return null;
  const routeByType: Record<string, string> = {
    RUN: "runs",
    EVALUATION: "evaluations",
    REGRESSION: "regressions",
    RELEASE_DECISION: "release-decisions",
  };
  const route = routeByType[target.type];
  return route ? `/${route}/${encodeURIComponent(target.id)}` : null;
}

function executionEvidenceHref(evidence: { entity_type: string; entity_id: string }): string | null {
  return executionTargetHref({ type: evidence.entity_type, id: evidence.entity_id });
}

function executionLeaseState(job: ExecutionJobDto): string {
  if (job.state === "RECONCILE_REQUIRED") return "RECONCILE REQUIRED";
  if (!job.active_attempt_id) return job.state === "QUEUED" ? "NOT CLAIMED" : "NO ACTIVE LEASE";
  const expiry = job.lease.lease_expires_at ? Date.parse(job.lease.lease_expires_at) : Number.NaN;
  if (!Number.isNaN(expiry) && expiry <= Date.now()) return "EXPIRED / RECLAIMABLE";
  return "LEASE ACTIVE";
}

function ExecutionIndex() {
  const [state, setState] = useState<"loading" | "ready" | "error">(DATA_SOURCE_MODE === "fixture" ? "ready" : "loading");
  const [jobs, setJobs] = useState<ExecutionJobDto[]>([]);
  const [metrics, setMetrics] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState<ControlPlaneApiError | undefined>();
  useEffect(() => {
    if (DATA_SOURCE_MODE === "fixture") return;
    let active = true;
    Promise.all([loadExecutionJobs(), loadExecutionMetrics()])
      .then(([nextJobs, nextMetrics]) => {
        if (!active) return;
        setJobs(nextJobs);
        setMetrics(nextMetrics as unknown as Record<string, number>);
        setState("ready");
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(cause instanceof ControlPlaneApiError ? cause : new ControlPlaneApiError("Execution API is unavailable.", "API_UNAVAILABLE", null, true));
        setState("error");
      });
    return () => { active = false; };
  }, []);
  if (state === "error") return <ExecutionSurfaceState error={error} />;
  return (
    <AppShell execution>
      <div className="page-header index-header">
        <div>
          <span className="eyebrow">DURABLE EXECUTIONS · POSTGRESQL READ MODEL</span>
          <h1>Follow a job across attempts, leases, and evidence.</h1>
          <p className="lede">Execution coordination is mutable; Run and Evaluation evidence remains immutable. This surface is read-only and never claims, retries, cancels, or releases a job.</p>
        </div>
        <div className="corpus-note">
          <span className="section-label">CURRENT VIEW</span>
          <strong>{DATA_SOURCE_MODE === "fixture" ? "API only" : `${jobs.length} jobs`}</strong>
          <span>{DATA_SOURCE_MODE === "fixture" ? "fixture mode has no jobs" : "canonical job snapshots"}</span>
        </div>
      </div>
      <section className="corpus-boundary execution-boundary" aria-label="Execution boundary">
        <span className="boundary-mark">◇</span>
        <p><strong>Execution boundary.</strong> A <strong>RECONCILE_REQUIRED</strong> job means lease expiry or transport uncertainty did not prove non-execution. Inspect the operation and receipt evidence before any next attempt; blind retry is prohibited.</p>
      </section>
      {DATA_SOURCE_MODE === "fixture" ? (
        <section className="execution-empty" aria-live="polite">
          <span className="eyebrow">EXPLICIT FIXTURE MODE</span>
          <h2>Durable jobs are available from the Control Plane API.</h2>
          <p>Fixture mode intentionally does not invent execution records. Run the Web against <span className="mono">/api/v1</span> to inspect canonical PostgreSQL job state.</p>
        </section>
      ) : (
        <>
          <section className="execution-metrics" aria-label="Execution metrics">
            <div><span>Queued</span><strong>{metrics?.queued_jobs ?? "—"}</strong><small>awaiting claim</small></div>
            <div><span>Active</span><strong>{metrics?.claimed_or_running_jobs ?? "—"}</strong><small>claim / run / cancel request</small></div>
            <div><span>Reconcile</span><strong>{metrics?.reconcile_required_jobs ?? "—"}</strong><small>blind retry blocked</small></div>
            <div><span>Completed</span><strong>{metrics?.completed_jobs ?? "—"}</strong><small>terminal evidence bound</small></div>
            <div><span>Platform failed</span><strong>{metrics?.platform_failed_jobs ?? "—"}</strong><small>not Agent FAIL</small></div>
          </section>
          <section className="execution-list-section" aria-labelledby="execution-list-heading">
            <div className="section-heading"><div><span className="eyebrow">SELECT A JOB</span><h2 id="execution-list-heading">Canonical execution jobs</h2></div><span className="section-count">{jobs.length.toString().padStart(2, "0")} records</span></div>
            {jobs.length === 0 ? <div className="execution-empty compact"><h2>No durable jobs in the current Control Plane.</h2><p>Submission and worker mutation are intentionally unavailable from this read-only surface.</p></div> : (
              <div className="execution-list">
                <div className="execution-list-head" aria-hidden="true"><span>STATE / SIGNAL</span><span>JOB / TARGET</span><span>ATTEMPT / WORKER</span><span>LEASE / UPDATED</span><span /></div>
                {jobs.map((job) => {
                  const href = `/executions/${encodeURIComponent(job.job_id)}`;
                  return <a className="execution-row" key={job.job_id} href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>
                    <div><StatusTag status={job.state} tone={executionStatusTone(job.state)} /><span className="signal-label">{executionStateNote(job.state)}</span></div>
                    <div><strong className="mono">{shortId(job.job_id, 25)}</strong><span>{displayValue(job.job_type)} · {displayValue(job.target?.type)} / {shortId(job.target?.id, 26)}</span></div>
                    <div><strong>{job.attempt_number ? `Attempt ${job.attempt_number}` : "No attempt"}</strong><span>{displayValue(job.active_worker_id || "—")} · v{displayValue(job.version)}</span></div>
                    <div><strong>{executionLeaseState(job)}</strong><span>{formatDate(job.updated_at)} UTC</span></div>
                    <span className="row-arrow" aria-hidden="true">→</span>
                  </a>;
                })}
              </div>
            )}
          </section>
        </>
      )}
      <footer className="page-footnote"><span>Source: Control Plane API · PostgreSQL canonical execution state</span><span>Read-only · no worker or release action</span></footer>
    </AppShell>
  );
}

function ExecutionDetail({ jobId }: { jobId: string }) {
  const [state, setState] = useState<"loading" | "ready" | "error">(DATA_SOURCE_MODE === "fixture" ? "ready" : "loading");
  const [job, setJob] = useState<ExecutionJobDto | null>(null);
  const [error, setError] = useState<ControlPlaneApiError | undefined>();
  useEffect(() => {
    if (DATA_SOURCE_MODE === "fixture") return;
    let active = true;
    loadExecutionJob(jobId)
      .then((nextJob) => { if (active) { setJob(nextJob); setState("ready"); } })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(cause instanceof ControlPlaneApiError ? cause : new ControlPlaneApiError("Execution API is unavailable.", "API_UNAVAILABLE", null, true));
        setState("error");
      });
    return () => { active = false; };
  }, [jobId]);
  if (DATA_SOURCE_MODE === "fixture") return <ExecutionSurfaceState />;
  if (state === "error") return <ExecutionSurfaceState error={error} />;
  if (state === "loading" || !job) return <ExecutionSurfaceState loading />;
  const activeAttempt = job.active_attempt_id ? job.attempts.find((attempt) => attempt.attempt_id === job.active_attempt_id) : undefined;
  const targetHref = executionTargetHref(job.target);
  const reconcileRequired = job.state === "RECONCILE_REQUIRED" || job.operations.some((operation) => ["PREPARED", "IN_FLIGHT", "UNKNOWN_OUTCOME"].includes(operation.status));
  return (
    <AppShell detail execution>
      <div className="detail-breadcrumb"><a href="/executions" onClick={(event) => { event.preventDefault(); navigate("/executions"); }}>Executions</a><span aria-hidden="true">/</span><span>{shortId(job.job_id, 34)}</span><span className="schema-chip">rpf-14 durable job</span></div>
      <div className="detail-header execution-detail-header">
        <div><span className="eyebrow">DURABLE EXECUTION INVESTIGATION</span><h1>{humanize(job.state)} · {displayValue(job.job_type)}</h1><p className="detail-subtitle">{executionStateNote(job.state)}. The execution state and Agent/Evaluation outcome are intentionally reported as separate facts.</p></div>
        <div className="detail-header-status"><StatusTag status={job.state} tone={executionStatusTone(job.state)} /><span className="status-note">read-only canonical job snapshot</span></div>
      </div>
      {reconcileRequired && <section className="execution-alert" aria-label="Reconcile required"><span className="boundary-mark">!</span><div><strong>RECONCILE_REQUIRED · 禁止 blind retry</strong><p>At least one operation is not durably resolved. Lease expiry is not proof that the side effect did not happen; inspect receipt/environment evidence before submitting another mutation.</p></div></section>}
      <section className="identity-strip execution-identity" aria-label="Execution identity">
        <IdentityField label="Job" value={job.job_id} mono />
        <IdentityField label="Target" value={`${displayValue(job.target?.type)} / ${shortId(job.target?.id, 22)}`} mono note={targetHref ? "linked canonical evidence" : "stable target ref"} />
        <IdentityField label="Correlation" value={job.correlation_id} mono />
        <IdentityField label="Current attempt" value={job.active_attempt_id || "—"} mono note={job.active_worker_id || "no active worker"} />
        <IdentityField label="Lease" value={executionLeaseState(job)} note={job.lease.lease_token_present ? "token withheld; hash never shown" : "no raw token"} />
        <IdentityField label="Version" value={`v${job.version}`} mono note={`attempt ${job.attempt_number}`} />
      </section>
      <section className="execution-facts-bar" aria-label="Execution facts">
        <div><span>Execution state</span><strong>{job.state}</strong><small>{executionStateNote(job.state)}</small></div>
        <div><span>Agent / Evaluation outcome</span><strong>{job.outcome_status || "NOT YET RECORDED"}</strong><small>{job.state === "FAILED_PLATFORM" ? "Platform failure; not Agent FAIL" : "terminal evidence only"}</small></div>
        <div><span>Worker ownership</span><strong>{job.active_worker_id || "NONE"}</strong><small>{activeAttempt ? `${activeAttempt.status} · ${activeAttempt.worker_id}` : "no active attempt"}</small></div>
        <div><span>Terminal evidence</span><strong>{job.terminal_evidence_id ? "BOUND" : "PENDING"}</strong><small>{shortId(job.terminal_evidence_id, 25)}</small></div>
      </section>
      <section className="execution-panel" aria-labelledby="attempt-history-heading"><div className="panel-heading"><div><span className="eyebrow">APPEND-ONLY HISTORY</span><h2 id="attempt-history-heading">Attempts and lease changes</h2></div><span className="section-count">{job.attempts.length} attempts</span></div><div className="execution-attempts">{job.attempts.map((attempt) => <div className="execution-attempt" key={attempt.attempt_id}><div><span className="execution-index">{attempt.attempt_number.toString().padStart(2, "0")}</span><strong>{attempt.status}</strong><small className="mono">{attempt.attempt_id}</small></div><div><span>Worker</span><strong>{attempt.worker_id}</strong><small>lease version v{attempt.lease_version}</small></div><div><span>Window</span><strong>{formatDate(attempt.started_at || attempt.created_at)}</strong><small>{attempt.ended_at ? `ended ${formatDate(attempt.ended_at)}` : `expires ${formatDate(attempt.lease_expires_at)}`}</small></div><div><span>Reason</span><strong>{displayValue(attempt.reason)}</strong><small>{attempt.heartbeat_at ? `heartbeat ${formatDate(attempt.heartbeat_at)}` : "no heartbeat recorded"}</small></div></div>)}</div></section>
      <section className="execution-panel" aria-labelledby="operation-heading"><div className="panel-heading"><div><span className="eyebrow">SIDE-EFFECT IDENTITY</span><h2 id="operation-heading">Operations and reconcile status</h2></div><span className="section-count">stable operation_id · at-least-once delivery</span></div>{job.operations.length === 0 ? <p className="execution-muted">No state-changing operation has been prepared for this job.</p> : <div className="execution-operation-list">{job.operations.map((operation) => <div className={`execution-operation ${operation.status === "UNKNOWN_OUTCOME" ? "warning" : ""}`} key={operation.operation_id}><div><span className="field-label">OPERATION</span><strong className="mono">{operation.operation_id}</strong><small>{operation.environment_id}</small></div><div><span className="field-label">STATUS</span><StatusTag status={operation.status} tone={operation.status === "CONFIRMED" ? "success" : operation.status === "UNKNOWN_OUTCOME" ? "review" : "neutral"} /><small>{operation.status === "UNKNOWN_OUTCOME" ? "reconcile before retry" : executionStateNote(operation.status)}</small></div><div><span className="field-label">EFFECT COUNT</span><strong>{operation.effect_count}</strong><small>{operation.receipt_ref || "receipt withheld / pending"}</small></div><div><span className="field-label">FINGERPRINT</span><strong className="mono">{shortId(operation.operation_fingerprint, 22)}</strong><small>{formatDate(operation.updated_at)}</small></div></div>)}</div>}</section>
      <section className="execution-panel" aria-labelledby="evidence-heading"><div className="panel-heading"><div><span className="eyebrow">IMMUTABLE REFERENCES</span><h2 id="evidence-heading">Terminal and execution evidence</h2></div><span className="section-count">{job.evidence.length} refs · bytes not editable here</span></div>{job.evidence.length === 0 ? <p className="execution-muted">No execution evidence has been registered yet.</p> : <div className="execution-evidence-list">{job.evidence.map((evidence) => { const href = executionEvidenceHref(evidence); return <div className="execution-evidence-row" key={evidence.evidence_id}><div><span className="field-label">{evidence.entity_type}</span><strong>{evidence.outcome}</strong><small className="mono">{evidence.evidence_id}</small></div><div><span>Entity</span><strong className="mono">{shortId(evidence.entity_id, 30)}</strong><small>{shortId(evidence.content_sha256, 26)}</small></div>{href ? <a className="action-link" href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>Open canonical evidence →</a> : <span className="execution-muted">stable ref only</span>}</div>; })}</div>}</section>
      <section className="execution-panel" aria-labelledby="event-history-heading"><div className="panel-heading"><div><span className="eyebrow">TRANSITION AUDIT</span><h2 id="event-history-heading">Append-only event history</h2></div><span className="section-count">{job.events.length} events</span></div><ol className="execution-event-list">{job.events.map((event) => <li key={event.event_id}><span className="execution-event-number">{event.event_id}</span><div><strong>{event.event_type}</strong><span>{displayValue(event.from_state)} → <b>{event.to_state}</b> · version {event.version}</span><small>{displayValue(event.reason)} · {formatDate(event.occurred_at)} UTC · {displayValue(event.attempt_id || event.operation_id || "job")}</small></div></li>)}</ol></section>
      <details className="raw-details execution-raw"><summary>Expert escape hatch · normalized durable job JSON</summary><pre>{JSON.stringify(job, null, 2)}</pre></details>
      <footer className="detail-footer"><span>{job.job_id} · {job.state} · correlation {job.correlation_id}</span><span>{job.outcome_status || "outcome pending"} · no mutation available from Web</span></footer>
    </AppShell>
  );
}

function ExecutionSurfaceState({ loading = false, error }: { loading?: boolean; error?: ControlPlaneApiError }) {
  const unavailable = Boolean(error);
  return <main className="data-source-state" aria-live="polite"><div className={"data-source-state-card" + (unavailable ? " error" : "")}><span className="eyebrow">DURABLE EXECUTION API · RPF-14</span><h1>{unavailable ? "Execution data is unavailable." : loading ? "Loading durable job…" : "Execution data is API-only."}</h1><p>{unavailable ? "The Web surface did not receive a canonical execution response. It does not invent a fixture or retry a mutation." : "Use the Control Plane read API to inspect PostgreSQL-backed jobs, attempts, operations, evidence refs, and events."}</p>{unavailable && <code>{error?.code || "API_UNAVAILABLE"}{error?.status ? " · HTTP " + error.status : ""}</code>}</div></main>;
}

export default function App() {
  const [location, setLocation] = useState<LocationState>(() => readLocation());
  const [snapshot, setSnapshot] = useState<CanonicalSnapshot>(() => createCanonicalSnapshot(DATA_SOURCE_MODE));
  const [dataSource, setDataSource] = useState<{ status: "loading" | "ready" | "error"; error?: ControlPlaneApiError }>(() => ({
    status: DATA_SOURCE_MODE === "fixture" ? "ready" : "loading",
  }));
  useEffect(() => {
    const update = () => setLocation(readLocation());
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  const executionRoute = location.pathname === "/executions" || Boolean(location.executionJobId);
  useEffect(() => {
    if (DATA_SOURCE_MODE === "fixture" || executionRoute) {
      setDataSource({ status: "ready" });
      return;
    }
    let active = true;
    loadControlPlaneCorpus()
      .then((payload) => {
        if (!active) return;
        try {
          activateControlPlaneCorpus(payload);
          setSnapshot((current) => createCanonicalSnapshot("api", current.revision + 1));
          setDataSource({ status: "ready" });
        } catch {
          setDataSource({
            status: "error",
            error: new ControlPlaneApiError(
              "Control Plane artifact normalization failed.",
              "INVALID_API_CORPUS",
              null,
              false,
            ),
          });
        }
      })
      .catch((error: unknown) => {
        if (!active) return;
        setDataSource({
          status: "error",
          error: error instanceof ControlPlaneApiError
            ? error
            : new ControlPlaneApiError("Control Plane API is unavailable.", "API_UNAVAILABLE", null, true),
        });
      });
    return () => {
      active = false;
    };
  }, [executionRoute]);
  const canonicalRouteState = useMemo(() => resolveCanonicalRouteState(dataSource.status, snapshot, location), [dataSource.status, snapshot, location]);
  const selected = canonicalRouteState.kind === "ready" || canonicalRouteState.kind === "not-found"
    ? canonicalRouteState.selection
    : {};
  const { run, failureCase, regression, evaluation, comparison, statisticalEvaluation, statisticalComparison, releaseDecision, agent, cluster, bisect } = selected;
  if (executionRoute) return location.executionJobId ? <ExecutionDetail jobId={location.executionJobId} /> : <ExecutionIndex />;
  if (canonicalRouteState.kind === "loading") return <SharedDataSourceState status="loading" />;
  if (canonicalRouteState.kind === "unavailable") return <SharedDataSourceState status="error" error={dataSource.error} />;
  if (location.pathname === "/" || location.pathname === "/overview") return <GoldenDemoOverviewFeature snapshot={snapshot} />;
  if (agent) return <AgentDetail agent={agent} />;
  if (location.pathname === "/agents") return <AgentIndex />;
  if (bisect) return <VersionBisectDetail bisect={bisect} />;
  if (cluster) return <FailureClusterDetail cluster={cluster} />;
  if (location.pathname === "/failure-intelligence") return <FailureIntelligenceIndex />;
  if (releaseDecision) return <ReleaseDecisionDetail decision={releaseDecision} />;
  if (failureCase) return <FailureCaseDetailFeature failureCase={failureCase} snapshot={snapshot} />;
  if (regression) return <RegressionDetail regression={regression} />;
  if (statisticalEvaluation) return <StatisticalEvaluationDetailFeature evaluation={statisticalEvaluation} snapshot={snapshot} />;
  if (statisticalComparison) return <StatisticalComparisonDetailFeature comparison={statisticalComparison} />;
  if (comparison) return <ComparisonDetail comparison={comparison} />;
  if (evaluation) return <EvaluationDetail evaluation={evaluation} />;
  if (location.pathname === "/failures") return <FailureIndex />;
  if (location.pathname === "/regressions") return <RegressionIndex />;
  if (location.pathname === "/evaluations") return <EvaluationIndex />;
  if (location.pathname === "/statistical-evaluations") return <StatisticalEvaluationIndexFeature snapshot={snapshot} />;
  if (location.pathname === "/statistical-comparisons") return <StatisticalComparisonIndexFeature snapshot={snapshot} />;
  if (location.pathname === "/comparisons") return <ComparisonIndex />;
  if (location.pathname === "/release-decisions") return <ReleaseDecisionIndex />;
  if (run) return <RunDetail run={run} eventId={location.eventId} />;
  if (canonicalRouteState.kind === "not-found") {
    return <NotFoundState path={location.pathname} />;
  }
  return <RunIndex />;
}

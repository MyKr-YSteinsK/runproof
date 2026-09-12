import { useEffect, useMemo, useState } from "react";
import {
  EvidenceLayer,
  FailureCase,
  getDerivedCost,
  getFailureCase,
  getFailureCaseForRun,
  getRegression,
  getRegressionResultForRun,
  getRegressionForRun,
  getRegressionResults,
  getRun,
  getUsage,
  isAgentFailureRun,
  isEnvironmentErrorRun,
  isFaultedRun,
  JsonRecord,
  reviewedRuns,
  reviewedFailureCases,
  reviewedRegressions,
  reviewedRegressionCollection,
  Regression,
  RegressionExecutionResult,
  RunEvidence,
  TrajectoryEvent,
} from "./data/artifacts";

type LocationState = { pathname: string; runId: string | null; eventId: string | null; failureCaseId: string | null; regressionId: string | null };

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

function readLocation(): LocationState {
  const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
  const runMatch = pathname.match(/^\/runs\/([^/]+)$/);
  const failureMatch = pathname.match(/^\/failures\/([^/]+)$/);
  const regressionMatch = pathname.match(/^\/regressions\/([^/]+)$/);
  return {
    pathname,
    runId: runMatch ? decodeURIComponent(runMatch[1]) : null,
    eventId: new URLSearchParams(window.location.search).get("event"),
    failureCaseId: failureMatch ? decodeURIComponent(failureMatch[1]) : null,
    regressionId: regressionMatch ? decodeURIComponent(regressionMatch[1]) : null,
  };
}

function navigate(to: string): void {
  window.history.pushState({}, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

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

function AppShell({ children, detail = false, failure = false, regression = false }: { children: React.ReactNode; detail?: boolean; failure?: boolean; regression?: boolean }) {
  return (
    <div className="app-frame">
      <aside className="rail" aria-label="RunProof navigation">
        <a className="brand" href="/runs" onClick={(event) => { event.preventDefault(); navigate("/runs"); }}>
          <span className="brand-mark">R</span>
          <span>
            <strong>RunProof</strong>
            <small>reliability control plane</small>
          </span>
        </a>
        <div className="workspace-switcher">
          <span className="section-label">WORKSPACE</span>
          <span className="workspace-name">RPF / Prototype</span>
          <span className="workspace-status"><i aria-hidden="true" /> local reviewed corpus</span>
        </div>
        <nav className="primary-nav" aria-label="Primary">
          <a className={!detail && !failure && !regression ? "active" : ""} href="/runs" onClick={(event) => { event.preventDefault(); navigate("/runs"); }}>
            <span className="nav-glyph">▤</span>
            <span>Run Evidence</span>
            <span className="nav-count">{reviewedRuns.length}</span>
          </a>
          <a className={failure ? "active" : ""} href="/failures" onClick={(event) => { event.preventDefault(); navigate("/failures"); }}>
            <span className="nav-glyph">!</span>
            <span>Failure Cases</span>
            <span className="nav-count">{1}</span>
          </a>
          <a className={regression ? "active" : ""} href="/regressions" onClick={(event) => { event.preventDefault(); navigate("/regressions"); }}>
            <span className="nav-glyph">↗</span>
            <span>Regressions</span>
            <span className="nav-count">{reviewedRegressions.length}</span>
          </a>
        </nav>
        <div className="rail-note">
          <span className="section-label">CURRENT SURFACE</span>
          <p>Evidence-first investigation for the first Reliability vertical slice.</p>
          <span className="schema-chip">v2 evidence · v1 cases · v1 regressions</span>
        </div>
        <div className="rail-footer">
          <span>Prototype</span>
          <span className="footer-dot" aria-hidden="true" />
          <span>offline corpus</span>
        </div>
      </aside>
      <main className="app-main">
        <header className="topbar">
          <div className="topbar-context">
            <span className="topbar-kicker">CONTROL PLANE</span>
            <span className="topbar-divider" aria-hidden="true">/</span>
            <span>{regression ? "Regression investigation" : failure ? "Failure Case investigation" : detail ? "Run investigation" : "Run evidence"}</span>
          </div>
          <div className="topbar-meta">
            <span className="live-indicator"><i aria-hidden="true" /> reviewed data</span>
            <span className="topbar-revision">RPF-06</span>
          </div>
        </header>
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}

function StatusTag({ status, tone = "neutral" }: { status: string; tone?: "success" | "fault" | "error" | "neutral" }) {
  return <span className={`status-tag ${tone}`}><i aria-hidden="true" />{status}</span>;
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

function IdentityField({ label, value, mono = false, note }: { label: string; value: string; mono?: boolean; note?: string }) {
  return (
    <div className="identity-field">
      <span className="field-label">{label}</span>
      <strong className={mono ? "mono" : ""} title={value}>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
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
        <span>Source: reviewed Run Evidence artifact</span>
        <span>Read-only local adapter · no live run action</span>
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
        <strong>{displayValue(run.run.agent.agent_id)}</strong>
        <span>{displayValue(run.run.agent.agent_version)} <em>·</em> {displayValue(run.scenario.scenario_id)}@{displayValue(run.scenario.scenario_version)}</span>
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
        <IdentityField label="Agent" value={`${displayValue(run.run.agent.agent_id)} / ${displayValue(run.run.agent.agent_version)}`} />
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

function resultTone(result: string): "success" | "fault" | "error" | "neutral" {
  if (result === "PASS") return "success";
  if (result === "FAIL") return "fault";
  if (result === "ERROR") return "error";
  return "neutral";
}

function AgentFailureSummary({ run, failureCase, regression }: { run: RunEvidence; failureCase?: FailureCase; regression?: Regression }) {
  const failure = run.failureAttribution || {};
  const failingEventId = typeof failure.failing_event_id === "string" ? failure.failing_event_id : null;
  return (
    <section className="classification-panel agent-failure-panel" aria-label="Agent failure attribution">
      <div className="classification-heading">
        <div><span className="eyebrow">FAILURE ATTRIBUTION · DETERMINISTIC</span><h2>Agent FAIL, guard protected state</h2></div>
        {failureCase && <a className="action-link" href={failureHref(failureCase.failureCase.failureCaseId)} onClick={(event) => { event.preventDefault(); navigate(failureHref(failureCase.failureCase.failureCaseId)); }}>Open Failure Case →</a>}
      </div>
      <p className="classification-copy">The Candidate Agent issued a state-changing intent before observing the expected state. The runtime guard rejected it, so no business mutation occurred; the unsafe behavior itself remains a FAIL.</p>
      <div className="classification-grid">
        <div><span>Attribution</span><strong>Agent</strong><small>{displayValue(failure.reason_code)}</small></div>
        <div><span>Violated invariant</span><strong className="mono">{displayValue(failure.violated_invariant_id)}</strong><small>{displayValue(failure.violated_invariant)}</small></div>
        <div><span>Failing event</span><strong className="mono">{shortId(failingEventId, 27)}</strong>{failingEventId && <a href={runHref(run.run.runId, failingEventId)} onClick={(event) => { event.preventDefault(); navigate(runHref(run.run.runId, failingEventId)); }}>Open event deep-link</a>}</div>
        <div><span>Expected / actual</span><strong>{displayValue(failure.expected)}</strong><small>{displayValue(failure.actual)}</small></div>
        <div><span>Side effect</span><strong>Not executed</strong><small>guard rejected unsafe intent</small></div>
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
        <div><span className="eyebrow">FOCUSED RERUN · REGRESSION RESULT</span><h2>{result.result.agentProfile === "known-bad-unsafe-precondition-v1" ? "Known-bad failure reproduced" : "Fixed Candidate passed this Regression"}</h2></div>
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
          <strong>{reviewedRegressionCollection.members.length} Regression</strong>
          <span>{reviewedRegressionCollection.collection.category} · not Release</span>
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
            const knownBad = results.find((result) => result.result.agentProfile === "known-bad-unsafe-precondition-v1");
            const fixedCandidate = results.find((result) => result.result.agentProfile === "production-change-agent-v1-fixed");
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
      <footer className="page-footnote"><span>Source: reviewed Regression + result + collection artifacts</span><span>Read-only local adapter · no rerun or release action</span></footer>
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
  const knownBad = results.find((result) => result.result.agentProfile === "known-bad-unsafe-precondition-v1");
  const fixedCandidate = results.find((result) => result.result.agentProfile === "production-change-agent-v1-fixed");
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
          <h1>Unsafe precondition Regression.</h1>
          <p className="detail-subtitle">A validated Agent failure was explicitly promoted after independent stability evidence and is now reusable as Regression version {regression.regression.regressionVersion}. The contract is separate from the source Failure Case and every Run.</p>
        </div>
        <div className="detail-header-status"><StatusTag status="ACTIVE" tone="success" /><span className="status-note">Historical Regression · not Release ELIGIBLE</span></div>
      </div>
      <section className="regression-identity-grid" aria-label="Regression identity">
        <IdentityField label="Regression" value={regression.regression.regressionId} mono />
        <IdentityField label="Version" value={regression.regression.regressionVersion} mono note={regression.schemaVersion} />
        <IdentityField label="Scenario" value={`${displayValue(valueAt(regression.scenario, "scenario_id"))}@${displayValue(valueAt(regression.scenario, "scenario_version"))}`} mono />
        <IdentityField label="Agent family" value={displayValue(valueAt(regression.agent, "agent_family"))} note={displayValue(valueAt(regression.agent, "domain"))} />
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
          <div className="regression-contract-card"><span className="field-label">INITIAL STATE / SEED</span><strong className="mono">{displayValue(initialState.release)}</strong><div><span>revision</span><b>{displayValue(initialState.revision)}</b></div><div><span>seed</span><b className="mono">{displayValue(seedRequirement.seed_revision)}</b></div><div><span>fresh per Run</span><b>{displayValue(seedRequirement.fresh_per_run)}</b></div></div>
          <div className="regression-contract-card"><span className="field-label">SCENARIO / TASK</span><strong>{displayValue(valueAt(scenario, "scenario_id"))}@{displayValue(valueAt(scenario, "scenario_version"))}</strong><p>{displayValue(valueAt(scenario, "task"))}</p></div>
          <div className="regression-contract-card"><span className="field-label">REQUIRED OUTCOME</span><strong className="success-text">{displayValue(valueAt(requiredOutcome, "run_status"))}</strong><p>release {displayValue(valueAt(valueAt(requiredOutcome, "actual_state"), "release"))} · revision {displayValue(valueAt(valueAt(requiredOutcome, "actual_state"), "revision"))} · {displayValue(valueAt(requiredOutcome, "exactly_one_authorized_mutation")) ? "one mutation" : "contract mismatch"}</p></div>
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
          {results.map((item) => { const ref = runRef(item.result.runRef); const href = ref ? runHref(ref.runId) : null; const known = item.result.agentProfile === "known-bad-unsafe-precondition-v1"; return <div className={`regression-rerun-row ${known ? "known-bad" : "fixed-candidate"}`} key={item.result.resultId}>
            <div><span className="field-label">{known ? "KNOWN-BAD AGENT" : "FIXED CANDIDATE"}</span><strong>{item.result.agentVersion}</strong><span className="mono">{item.result.agentProfile}</span></div>
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
              <div><strong>{displayValue(item.agent.agent_version)}</strong><span>{displayValue(item.scenario.scenario_id)}@{displayValue(item.scenario.scenario_version)}</span></div>
              <div><strong className="mono">{shortId(item.failureSignature.value, 24)}</strong><span>{displayValue(item.failureSignature.components.violated_invariant_id)}</span></div>
              <div><strong>Promoted to Regression</strong><span>{item.reproductionAttempts.length} reproduction attempt · validated history retained</span></div>
              <span className="row-arrow" aria-hidden="true">→</span>
            </a>;
          })}
        </div>
      </section>
      <footer className="page-footnote"><span>Source: reviewed Failure Case artifact</span><span>Read-only local adapter · no promote action</span></footer>
    </AppShell>
  );
}

function FailureCaseDetail({ failureCase }: { failureCase: FailureCase }) {
  const sourceRun = getRun(failureCase.sourceRun.runId);
  const attempt = failureCase.reproductionAttempts[0];
  const reproductionRun = attempt ? getRun(attempt.runId) : undefined;
  const failingEventId = typeof failureCase.failureObservation.failing_event_id === "string" ? failureCase.failureObservation.failing_event_id : null;
  const sourceLink = sourceRun ? runHref(sourceRun.run.runId, failingEventId) : runHref(failureCase.sourceRun.runId);
  const reproductionEventId = typeof valueAt(attempt?.run_ref, "event_id") === "string" ? String(valueAt(attempt?.run_ref, "event_id")) : null;
  const reproductionLink = reproductionRun ? runHref(reproductionRun.run.runId, reproductionEventId) : attempt ? runHref(attempt.runId) : null;
  const promotedRegressionId = typeof valueAt(failureCase.promotion?.regression_ref, "regression_id") === "string" ? String(valueAt(failureCase.promotion?.regression_ref, "regression_id")) : null;
  const promotedRegression = promotedRegressionId ? getRegression(promotedRegressionId) : undefined;
  const promoted = Boolean(promotedRegression && failureCase.promotion);
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
          <h1>Unsafe precondition failure</h1>
          <p className="detail-subtitle">The source Agent FAIL was reproduced in a fresh Environment with the same failure signature and evidence pattern.</p>
        </div>
        <div className="detail-header-status"><StatusTag status={promoted ? "PROMOTED" : "VALIDATED"} tone="success" /><span className="status-note">{promoted ? "validated history retained · Regression linked" : "Not a Regression"}</span></div>
      </div>
      <section className="case-identity-grid" aria-label="Failure Case identity">
        <IdentityField label="Failure Case" value={failureCase.failureCase.failureCaseId} mono />
        <IdentityField label="Agent Version" value={`${displayValue(failureCase.agent.agent_id)} / ${displayValue(failureCase.agent.agent_version)}`} />
        <IdentityField label="Scenario" value={`${displayValue(failureCase.scenario.scenario_id)}@${displayValue(failureCase.scenario.scenario_version)}`} mono />
        <IdentityField label="Attribution" value={displayValue(failureCase.classification.attribution)} note={displayValue(failureCase.classification.reason_code)} />
        <IdentityField label="Signature" value={shortId(failureCase.failureSignature.value, 28)} mono note={failureCase.failureSignature.signatureVersion} />
        <IdentityField label="Workflow" value={failureCase.failureCase.currentStatus} note={promoted ? "validated · promoted additively" : "validated · no promotion"} />
      </section>
      <section className="classification-panel case-summary-panel" aria-label="Failure Case validation summary">
        <div className="classification-heading"><div><span className="eyebrow">{promoted ? "PROMOTION EVIDENCE · VALIDATED → REGRESSION" : "REPRODUCTION EVIDENCE · VALIDATED"}</span><h2>{promoted ? "Failure Case promoted to Regression" : "Same failure, independently reproduced"}</h2></div>{promoted && promotedRegression ? <a className="action-link" href={regressionHref(promotedRegression.regression.regressionId)} onClick={(event) => { event.preventDefault(); navigate(regressionHref(promotedRegression.regression.regressionId)); }}>Open Regression →</a> : <span className="classification-badge">NOT A REGRESSION</span>}</div>
        <p className="classification-copy">Validation matched the stable signature, violated invariant, Agent attribution, key guard evidence, and healthy Provider/Environment boundary. {promoted ? `The explicit promotion gate passed and recorded ${displayValue(valueAt(failureCase.promotion, "promoted_at"))}; the original Run Evidence and validated history remain unchanged.` : "The original Run Evidence remains unchanged."}</p>
        <div className="classification-grid case-summary-grid">
          <div><span>Violated invariant</span><strong className="mono">{displayValue(failureCase.failureObservation.violated_invariant_id)}</strong><small>{displayValue(failureCase.failureObservation.violated_invariant)}</small></div>
          <div><span>Expected</span><strong>{displayValue(valueAt(failureCase.failureObservation.expected, "agent_observed_state_before_mutation"))}</strong><small>Agent observes before mutation</small></div>
          <div><span>Actual</span><strong>{displayValue(valueAt(failureCase.failureObservation.actual, "agent_observed_state_before_mutation"))}</strong><small>unsafe intent reached guard</small></div>
          <div><span>Validation</span><strong>{displayValue(valueAt(failureCase.validation, "status"))}</strong><small>{displayValue(valueAt(failureCase.validation, "observed_run_id"))}</small></div>
          <div><span>Promotion</span><strong>{promoted ? "PROMOTED" : "NOT_A_REGRESSION"}</strong><small>{promoted ? `Gate ${displayValue(valueAt(promotionGate, "all_passed"))} · ${shortId(promotedRegressionId, 28)}` : "no Regression link"}</small></div>
        </div>
      </section>
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
            const href = runHref(refRunId, refEventId);
            return <div className="case-ref-row" key={`${displayValue(ref.role)}-${index}`}><span>{displayValue(ref.role)}</span><strong className="mono">{shortId(refEventId, 35)}</strong><a href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>Open evidence →</a></div>;
          })}
        </div>
      </section>
      <footer className="detail-footer"><span>Case {failureCase.failureCase.failureCaseId} · {failureCase.failureCase.workflowState}</span><span>{promoted ? "Failure Case history retained · Regression is a separate artifact." : "Failure Case validated ≠ Regression."}</span></footer>
    </AppShell>
  );
}

export default function App() {
  const [location, setLocation] = useState<LocationState>(() => readLocation());
  useEffect(() => {
    const update = () => setLocation(readLocation());
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  const run = useMemo(() => location.runId ? getRun(location.runId) : undefined, [location.runId]);
  const failureCase = useMemo(() => location.failureCaseId ? getFailureCase(location.failureCaseId) : undefined, [location.failureCaseId]);
  const regression = useMemo(() => location.regressionId ? getRegression(location.regressionId) : undefined, [location.regressionId]);
  if (failureCase) return <FailureCaseDetail failureCase={failureCase} />;
  if (regression) return <RegressionDetail regression={regression} />;
  if (location.pathname === "/failures") return <FailureIndex />;
  if (location.pathname === "/regressions") return <RegressionIndex />;
  if (run) return <RunDetail run={run} eventId={location.eventId} />;
  return <RunIndex />;
}

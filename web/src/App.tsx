import { useEffect, useMemo, useState } from "react";
import {
  EvidenceLayer,
  getDerivedCost,
  getRun,
  getUsage,
  isFaultedRun,
  JsonRecord,
  reviewedRuns,
  RunEvidence,
  TrajectoryEvent,
} from "./data/artifacts";

type LocationState = { pathname: string; runId: string | null; eventId: string | null };

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
  const match = pathname.match(/^\/runs\/([^/]+)$/);
  return {
    pathname,
    runId: match ? decodeURIComponent(match[1]) : null,
    eventId: new URLSearchParams(window.location.search).get("event"),
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
      return `Readiness: ${displayValue(valueAt(result, "readiness"))}`;
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
      return `Actual state matches required target`;
    case "cleanup":
      return `Environment ${displayValue(valueAt(result, "removed") ? "removed" : valueAt(result, "code"))}`;
    default:
      return eventMeta(event.eventType).description;
  }
}

function AppShell({ children, detail = false }: { children: React.ReactNode; detail?: boolean }) {
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
          <a className={!detail ? "active" : ""} href="/runs" onClick={(event) => { event.preventDefault(); navigate("/runs"); }}>
            <span className="nav-glyph">▤</span>
            <span>Run Evidence</span>
            <span className="nav-count">2</span>
          </a>
        </nav>
        <div className="rail-note">
          <span className="section-label">CURRENT SURFACE</span>
          <p>Evidence-first investigation for the first Reliability vertical slice.</p>
          <span className="schema-chip">rpf-run-evidence-v2</span>
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
            <span>{detail ? "Run investigation" : "Run evidence"}</span>
          </div>
          <div className="topbar-meta">
            <span className="live-indicator"><i aria-hidden="true" /> reviewed data</span>
            <span className="topbar-revision">RPF-04</span>
          </div>
        </header>
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}

function StatusTag({ status, tone = "neutral" }: { status: string; tone?: "success" | "fault" | "neutral" }) {
  return <span className={`status-tag ${tone}`}><i aria-hidden="true" />{status}</span>;
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
          <strong>2 reviewed runs</strong>
          <span>v2 schema · source-bound</span>
        </div>
      </div>
      <section className="corpus-boundary" aria-label="Evidence boundary">
        <span className="boundary-mark">i</span>
        <p><strong>Evidence boundary.</strong> These are the two real RPF-03 runs. The response-lost run is a recovered <strong>PASS</strong>, not a Failure Case. Historical v1 artifacts remain preserved separately.</p>
      </section>
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
        <StatusTag status={run.outcome.status} tone="success" />
        <span className={`signal-label ${faulted ? "fault" : ""}`}>{faulted ? "Response lost · reconciled" : "Normal transition"}</span>
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
  const selected = run.trajectory.find((event) => event.eventId === eventId) || run.trajectory[0];
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
    <AppShell detail>
      <div className="detail-breadcrumb">
        <a href="/runs" onClick={(event) => { event.preventDefault(); navigate("/runs"); }}>Run Evidence</a>
        <span aria-hidden="true">/</span>
        <span>{shortId(run.run.runId, 32)}</span>
        <span className="schema-chip">rpf-run-evidence-v2</span>
      </div>
      <div className="detail-header">
        <div>
          <span className="eyebrow">RUN INVESTIGATION</span>
          <h1>{faulted ? "Response-lost recovery run" : "Normal release transition"}</h1>
          <p className="detail-subtitle">{faulted ? "A side effect completed, its response was lost, and reconciliation established the verified result." : "A controlled release change completed with an independent state read-back."}</p>
        </div>
        <div className="detail-header-status">
          <StatusTag status="PASS" tone="success" />
          <span className="status-note">deterministic verifier</span>
        </div>
      </div>
      <section className="identity-strip" aria-label="Run context identity">
        <IdentityField label="Agent" value={`${displayValue(run.run.agent.agent_id)} / ${displayValue(run.run.agent.agent_version)}`} />
        <IdentityField label="Evaluation / Run" value={`${shortId(run.run.evaluationId, 16)} / ${shortId(run.run.runId, 16)}`} mono />
        <IdentityField label="Scenario" value={`${displayValue(run.scenario.scenario_id)}@${displayValue(run.scenario.scenario_version)}`} mono />
        <IdentityField label="LLM provider" value={`${displayValue(run.llmProvider.provider_id)} · ${displayValue(run.llmProvider.requested_model)}`} note={displayValue(run.llmProvider.mode)} />
        <IdentityField label="Environment" value={shortId(run.environment.environment_id, 23)} mono note={`${displayValue(run.environment.seed_id)} / ${displayValue(run.environment.seed_revision)}`} />
        <IdentityField label="Verifier" value={`${displayValue(run.verification.verifierId)}@${displayValue(run.verification.verifierVersion)}`} mono />
      </section>
      <section className="run-facts-bar" aria-label="Run facts">
        <div><span>Outcome</span><strong>PASS</strong><small>quality eligible</small></div>
        <div><span>Fault</span><strong>{faulted ? "Observed" : "None"}</strong><small>{faulted ? "planned · triggered · reconciled" : "normal profile"}</small></div>
        <div><span>Environment provider</span><strong>{displayValue(run.environmentProvider.provider_implementation)}</strong><small>{displayValue(run.environmentProvider.context)} · writable layer</small></div>
        <div><span>Run duration</span><strong>{formatDuration(run.run.durationMs)}</strong><small>{formatDate(run.run.startedAt)} UTC</small></div>
      </section>
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

function TimelineEventButton({ event, selected, isLast, onSelect, onMove }: { event: TrajectoryEvent; selected: boolean; isLast: boolean; onSelect: (eventId: string) => void; onMove: (direction: number) => void }) {
  const meta = eventMeta(event.eventType);
  return (
    <div role="listitem">
      <button
        className={`timeline-event ${selected ? "selected" : ""} ${event.eventType === "fault" ? "fault-event" : ""}`}
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
  } else if (event.eventType === "initial_state_verification" || event.eventType === "actual_state_verification") {
    rows.push(["State", payload.state || valueAt(payload.result, "state")]);
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
  const changed = run.verification.stateDiff.filter((row) => row.changed);
  return (
    <section className="panel state-panel" aria-labelledby="state-diff-heading">
      <div className="panel-heading">
        <div><span className="eyebrow">VERIFIED RESULT · STATE</span><h2 id="state-diff-heading">State diff</h2></div>
        <span className="diff-count">{changed.length} changed fields</span>
      </div>
      <div className="state-compare">
        <StateSnapshot label="S0 · initial" state={run.verification.initialState} />
        <span className="state-arrow" aria-hidden="true">→</span>
        <StateSnapshot label="Required target" state={run.verification.expectedState} />
        <span className="state-arrow" aria-hidden="true">≈</span>
        <StateSnapshot label="S1 · actual read-back" state={run.verification.actualState} accent />
      </div>
      <div className="diff-table" role="table" aria-label="State field changes">
        <div className="diff-row diff-head" role="row"><span>FIELD</span><span>BEFORE</span><span>AFTER</span><span>STATUS</span></div>
        {run.verification.stateDiff.map((row) => <div className="diff-row" role="row" key={row.path}><strong className="mono">{row.path}</strong><span>{displayValue(row.before)}</span><span>{displayValue(row.after)}</span><span className={row.changed ? "changed-label" : "unchanged-label"}>{row.changed ? "Changed" : "Unchanged"}</span></div>)}
      </div>
    </section>
  );
}

function EvidencePanel({ run, usage, cost }: { run: RunEvidence; usage: JsonRecord; cost: JsonRecord }) {
  const checkEntries = Object.entries(run.verification.checks);
  const passedChecks = checkEntries.filter(([, passed]) => passed).length;
  return (
    <section className="panel evidence-panel" aria-labelledby="evidence-heading">
      <div className="panel-heading"><div><span className="eyebrow">EVIDENCE INSPECTOR</span><h2 id="evidence-heading">Invariants & evidence</h2></div><span className="check-summary">{passedChecks}/{checkEntries.length} verified</span></div>
      <div className="layer-list">
        {EVIDENCE_LAYERS.map(({ label, note }) => <div className={`layer-row ${label === "Inference" || label === "AI Analysis" ? "missing" : ""}`} key={label}><span className="layer-name">{label}</span><span>{note}</span>{(label === "Inference" || label === "AI Analysis") && <em>Not present</em>}</div>)}
      </div>
      <div className="invariant-list">
        {checkEntries.map(([key, passed]) => <div className="invariant-row" key={key}><span className={`invariant-icon ${passed ? "pass" : "fail"}`} aria-hidden="true">{passed ? "✓" : "!"}</span><span>{CHECK_LABELS[key] || humanize(key)}</span><strong>{passed ? "VERIFIED" : "VIOLATED"}</strong></div>)}
      </div>
      <div className="usage-block">
        <div className="usage-heading"><span>Usage fact</span><span>Derived value</span></div>
        <div className="usage-values"><strong>{displayValue(usage.total_tokens)} <small>tokens</small></strong><strong>¥{displayValue(cost.estimate)} <small>{displayValue(cost.tariff)} estimate</small></strong></div>
        <p>Usage is observed from the Provider response. Cost is a derived estimate, not a billing record.</p>
      </div>
    </section>
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
  if (run) return <RunDetail run={run} eventId={location.eventId} />;
  return <RunIndex />;
}

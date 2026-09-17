import type { ReactNode } from "react";
import {
  reviewedAgents,
  reviewedEvaluationComparison,
  reviewedEvaluations,
  reviewedFailureCases,
  reviewedFailureClusters,
  reviewedRegressions,
  reviewedReleaseDecisions,
  reviewedRuns,
} from "../data/artifacts";
import { reviewedStatisticalEvaluations } from "../data/statistical";
import { DATA_SOURCE_LABEL, DATA_SOURCE_MODE } from "../app/dataSource";
import { navigate } from "../app/navigation";

export interface AppShellProps {
  children: ReactNode;
  detail?: boolean;
  overview?: boolean;
  agent?: boolean;
  failure?: boolean;
  regression?: boolean;
  evaluation?: boolean;
  comparison?: boolean;
  statistical?: boolean;
  release?: boolean;
  execution?: boolean;
  intelligence?: boolean;
}

export const AppShell = ({ children, detail = false, overview = false, agent = false, failure = false, regression = false, evaluation = false, comparison = false, statistical = false, release = false, execution = false, intelligence = false }: AppShellProps) => (
  <div className="app-frame">
    <aside className="rail" aria-label="RunProof navigation">
      <a className="brand" href="/overview" onClick={(event) => { event.preventDefault(); navigate("/overview"); }}>
        <span className="brand-mark">R</span>
        <span><strong>RunProof</strong><small>reliability control plane</small></span>
      </a>
      <div className="workspace-switcher">
        <span className="section-label">WORKSPACE</span>
        <span className="workspace-name">RPF / Stabilization</span>
        <span className="workspace-status"><i aria-hidden="true" /> {DATA_SOURCE_LABEL}</span>
      </div>
      <nav className="primary-nav" aria-label="Primary">
        <a className={overview ? "active" : ""} href="/overview" onClick={(event) => { event.preventDefault(); navigate("/overview"); }}><span className="nav-glyph">⌂</span><span>Overview</span><span className="nav-count">RPF-19</span></a>
        <a className={agent ? "active" : ""} href="/agents" onClick={(event) => { event.preventDefault(); navigate("/agents"); }}><span className="nav-glyph">◇</span><span>Agents</span><span className="nav-count">{reviewedAgents.length}</span></a>
        <a className={!overview && !detail && !agent && !failure && !regression && !evaluation && !comparison && !statistical && !release && !execution && !intelligence ? "active" : ""} href="/runs" onClick={(event) => { event.preventDefault(); navigate("/runs"); }}><span className="nav-glyph">▤</span><span>Run Evidence</span><span className="nav-count">{reviewedRuns.length}</span></a>
        <a className={failure ? "active" : ""} href="/failures" onClick={(event) => { event.preventDefault(); navigate("/failures"); }}><span className="nav-glyph">!</span><span>Failure Cases</span><span className="nav-count">{reviewedFailureCases.length}</span></a>
        <a className={intelligence ? "active" : ""} href="/failure-intelligence" onClick={(event) => { event.preventDefault(); navigate("/failure-intelligence"); }}><span className="nav-glyph">⌁</span><span>Failure Intelligence</span><span className="nav-count">{reviewedFailureClusters.length}</span></a>
        <a className={regression ? "active" : ""} href="/regressions" onClick={(event) => { event.preventDefault(); navigate("/regressions"); }}><span className="nav-glyph">↗</span><span>Regressions</span><span className="nav-count">{reviewedRegressions.length}</span></a>
        <a className={evaluation ? "active" : ""} href="/evaluations" onClick={(event) => { event.preventDefault(); navigate("/evaluations"); }}><span className="nav-glyph">◎</span><span>Evaluations</span><span className="nav-count">{reviewedEvaluations.length}</span></a>
        <a className={statistical ? "active" : ""} href="/statistical-evaluations" onClick={(event) => { event.preventDefault(); navigate("/statistical-evaluations"); }}><span className="nav-glyph">∿</span><span>Statistical</span><span className="nav-count">{reviewedStatisticalEvaluations.length}</span></a>
        <a className={comparison ? "active" : ""} href={`/comparisons/${encodeURIComponent(reviewedEvaluationComparison.comparison.comparisonId)}`} onClick={(event) => { event.preventDefault(); navigate(`/comparisons/${encodeURIComponent(reviewedEvaluationComparison.comparison.comparisonId)}`); }}><span className="nav-glyph">⇄</span><span>Comparisons</span><span className="nav-count">{2}</span></a>
        <a className={release ? "active" : ""} href="/release-decisions" onClick={(event) => { event.preventDefault(); navigate("/release-decisions"); }}><span className="nav-glyph">✓</span><span>Release Decisions</span><span className="nav-count">{reviewedReleaseDecisions.length}</span></a>
        <a className={execution ? "active" : ""} href="/executions" onClick={(event) => { event.preventDefault(); navigate("/executions"); }}><span className="nav-glyph">◇</span><span>Executions</span><span className="nav-count">API</span></a>
      </nav>
      <div className="rail-note"><span className="section-label">CURRENT SURFACE</span><p>Evidence-first investigation for the first Reliability vertical slice.</p><span className="schema-chip">v2 evidence · v1 evals · v1 gates</span></div>
      <div className="rail-footer"><span>Stabilization</span><span className="footer-dot" aria-hidden="true" /><span>{DATA_SOURCE_MODE === "api" ? "canonical read model" : "fixture mode"}</span></div>
    </aside>
    <main className="app-main">
      <header className="topbar">
        <div className="topbar-context"><span className="topbar-kicker">CONTROL PLANE</span><span className="topbar-divider" aria-hidden="true">/</span><span>{overview ? "Golden Demo overview" : execution ? (detail ? "Durable execution detail" : "Durable executions") : intelligence ? (detail ? "Failure Intelligence detail" : "Failure Intelligence") : agent ? (detail ? "Agent detail" : "Agent registry") : release ? (detail ? "Release Decision detail" : "Release Decisions") : statistical ? (detail ? "Statistical evaluation detail" : "Statistical reliability") : comparison ? "Baseline / Candidate comparison" : evaluation ? (detail ? "Evaluation detail" : "Evaluation suite") : regression ? "Regression investigation" : failure ? "Failure Case investigation" : detail ? "Run investigation" : "Run evidence"}</span></div>
        <div className="topbar-meta"><span className="live-indicator"><i aria-hidden="true" /> {DATA_SOURCE_LABEL}</span><span className="topbar-revision">RPF-19</span></div>
      </header>
      <div className="page-content">{children}</div>
    </main>
  </div>
);

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
import { DATA_SOURCE_MODE } from "../app/dataSource";
import { navigate } from "../app/navigation";
import { useI18n } from "../i18n";
import { LocaleSwitcher } from "./LocaleSwitcher";

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

export const AppShell = ({ children, detail = false, overview = false, agent = false, failure = false, regression = false, evaluation = false, comparison = false, statistical = false, release = false, execution = false, intelligence = false }: AppShellProps) => {
  const { t } = useI18n();
  const dataSourceLabel = DATA_SOURCE_MODE === "api" ? t("common.controlPlaneApi") : t("common.reviewedFixtureCorpus");
  const topContext = overview ? t("nav.top.goldenDemo")
    : execution ? (detail ? t("nav.top.durableDetail") : t("nav.top.durableList"))
      : intelligence ? (detail ? t("nav.top.failureIntelligenceDetail") : t("nav.top.failureIntelligence"))
        : agent ? (detail ? t("nav.top.agentDetail") : t("nav.top.agentRegistry"))
          : release ? (detail ? t("nav.top.releaseDecisionDetail") : t("nav.top.releaseDecisions"))
            : statistical ? (detail ? t("nav.top.statisticalDetail") : t("nav.top.statistical"))
              : comparison ? t("nav.top.comparison")
                : evaluation ? (detail ? t("nav.top.evaluationDetail") : t("nav.top.evaluationSuite"))
                  : regression ? t("nav.top.regression")
                    : failure ? t("nav.top.failure")
                      : detail ? t("nav.top.runDetail") : t("nav.top.run");
  return (
    <div className="app-frame">
      <aside className="rail" aria-label={t("nav.primary")}>
        <a className="brand" href="/overview" onClick={(event) => { event.preventDefault(); navigate("/overview"); }}>
          <span className="brand-mark">R</span>
          <span><strong>RunProof</strong><small>{t("nav.brandDescriptor")}</small></span>
        </a>
        <div className="workspace-switcher">
          <span className="section-label">{t("nav.workspace")}</span>
          <span className="workspace-name">{t("nav.workspaceName")}</span>
          <span className="workspace-status"><i aria-hidden="true" /> {dataSourceLabel}</span>
        </div>
        <nav className="primary-nav" aria-label={t("nav.primary")}>
          <a className={overview ? "active" : ""} href="/overview" onClick={(event) => { event.preventDefault(); navigate("/overview"); }}><span className="nav-glyph">⌂</span><span>{t("nav.overview")}</span><span className="nav-count">RPF-19</span></a>
          <a className={agent ? "active" : ""} href="/agents" onClick={(event) => { event.preventDefault(); navigate("/agents"); }}><span className="nav-glyph">◇</span><span>{t("nav.agents")}</span><span className="nav-count">{reviewedAgents.length}</span></a>
          <a className={!overview && !detail && !agent && !failure && !regression && !evaluation && !comparison && !statistical && !release && !execution && !intelligence ? "active" : ""} href="/runs" onClick={(event) => { event.preventDefault(); navigate("/runs"); }}><span className="nav-glyph">▤</span><span>{t("nav.runEvidence")}</span><span className="nav-count">{reviewedRuns.length}</span></a>
          <a className={failure ? "active" : ""} href="/failures" onClick={(event) => { event.preventDefault(); navigate("/failures"); }}><span className="nav-glyph">!</span><span>{t("nav.failureCases")}</span><span className="nav-count">{reviewedFailureCases.length}</span></a>
          <a className={intelligence ? "active" : ""} href="/failure-intelligence" onClick={(event) => { event.preventDefault(); navigate("/failure-intelligence"); }}><span className="nav-glyph">⌁</span><span>{t("nav.failureIntelligence")}</span><span className="nav-count">{reviewedFailureClusters.length}</span></a>
          <a className={regression ? "active" : ""} href="/regressions" onClick={(event) => { event.preventDefault(); navigate("/regressions"); }}><span className="nav-glyph">↗</span><span>{t("nav.regressions")}</span><span className="nav-count">{reviewedRegressions.length}</span></a>
          <a className={evaluation ? "active" : ""} href="/evaluations" onClick={(event) => { event.preventDefault(); navigate("/evaluations"); }}><span className="nav-glyph">◎</span><span>{t("nav.evaluations")}</span><span className="nav-count">{reviewedEvaluations.length}</span></a>
          <a className={statistical ? "active" : ""} href="/statistical-evaluations" onClick={(event) => { event.preventDefault(); navigate("/statistical-evaluations"); }}><span className="nav-glyph">∿</span><span>{t("nav.statistical")}</span><span className="nav-count">{reviewedStatisticalEvaluations.length}</span></a>
          <a className={comparison ? "active" : ""} href={`/comparisons/${encodeURIComponent(reviewedEvaluationComparison.comparison.comparisonId)}`} onClick={(event) => { event.preventDefault(); navigate(`/comparisons/${encodeURIComponent(reviewedEvaluationComparison.comparison.comparisonId)}`); }}><span className="nav-glyph">⇄</span><span>{t("nav.comparisons")}</span><span className="nav-count">{2}</span></a>
          <a className={release ? "active" : ""} href="/release-decisions" onClick={(event) => { event.preventDefault(); navigate("/release-decisions"); }}><span className="nav-glyph">✓</span><span>{t("nav.releaseDecisions")}</span><span className="nav-count">{reviewedReleaseDecisions.length}</span></a>
          <a className={execution ? "active" : ""} href="/executions" onClick={(event) => { event.preventDefault(); navigate("/executions"); }}><span className="nav-glyph">◇</span><span>{t("nav.executions")}</span><span className="nav-count">API</span></a>
        </nav>
        <div className="rail-note"><span className="section-label">{t("nav.currentSurface")}</span><p>{t("nav.currentSurfaceNote")}</p><span className="schema-chip">v2 evidence · v1 evals · v1 gates</span></div>
        <div className="rail-footer"><span>{t("nav.stabilization")}</span><span className="footer-dot" aria-hidden="true" /><span>{DATA_SOURCE_MODE === "api" ? t("common.canonicalReadModel") : t("common.fixtureMode")}</span></div>
      </aside>
      <main className="app-main">
        <header className="topbar">
          <div className="topbar-context"><span className="topbar-kicker">{t("nav.top.controlPlane")}</span><span className="topbar-divider" aria-hidden="true">/</span><span>{topContext}</span></div>
          <div className="topbar-meta"><span className="live-indicator"><i aria-hidden="true" /> {dataSourceLabel}</span><span className="topbar-revision">RPF-19</span><LocaleSwitcher /></div>
        </header>
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
};

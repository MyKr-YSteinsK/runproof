import type {
  AgentSummary,
  EvaluationResult,
  FailureCase,
  FailureCluster,
  ReleaseDecision,
  RunEvidence,
  VersionBisect,
} from "../../data/artifacts";
import type { StatisticalComparison, StatisticalEvaluation } from "../../data/statistical";
import type { CanonicalSnapshot } from "../../data/canonicalSnapshot";
import { goldenDemoProfile } from "../../data/goldenDemo";

export interface GoldenDemoOverviewModel {
  productionAgent: AgentSummary | undefined;
  incidentAgent: AgentSummary | undefined;
  candidateEvaluation: EvaluationResult | undefined;
  candidateDecision: ReleaseDecision | undefined;
  flagshipFailureCase: FailureCase | undefined;
  flagshipCluster: FailureCluster | undefined;
  bisect: VersionBisect | undefined;
  unknownOutcomeRun: RunEvidence | undefined;
  statisticalComparison: StatisticalComparison | undefined;
  statisticalEvaluations: Array<{
    id: string;
    label: string;
    description: string;
    evaluation: StatisticalEvaluation | undefined;
    decisionStatus: string | undefined;
  }>;
  unknownReconcile: unknown;
  unknownEffectCount: unknown;
  firstDivergence: unknown;
  familySignature: unknown;
  firstBadCandidate: unknown;
  comparisonClassification: string | undefined;
}

const objectValue = (value: unknown): Record<string, unknown> | null => (
  value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null
);

const valueAt = (value: unknown, key: string): unknown => objectValue(value)?.[key];
const firstPresent = (...values: unknown[]): unknown => values.find((value) => value !== null && value !== undefined && value !== "");

const statisticalRows = [
  { id: "statistical-evaluation-rpf18-stable", label: "Stable", description: "quality cohort" },
  { id: "statistical-evaluation-rpf18-flaky", label: "Flaky", description: "observed instability" },
  { id: "statistical-evaluation-rpf18-safety", label: "Safety", description: "zero-tolerance event" },
  { id: "statistical-evaluation-rpf18-evidence-poor", label: "Evidence-poor", description: "insufficient evidence" },
];

export const selectGoldenDemoOverview = (snapshot: CanonicalSnapshot): GoldenDemoOverviewModel => {
  const productionAgent = snapshot.artifacts.agents.find((item) => item.agentId === goldenDemoProfile.agents[0].agent_id);
  const incidentAgent = snapshot.artifacts.agents.find((item) => item.agentId === goldenDemoProfile.agents[1].agent_id);
  const candidateEvaluation = snapshot.artifacts.evaluations.find((item) => item.evaluation.evaluationId === goldenDemoProfile.selected.candidate_evaluation);
  const candidateDecision = snapshot.artifacts.releaseDecisions.find((item) => item.releaseDecision.releaseDecisionId === goldenDemoProfile.selected.release_decision);
  const flagshipFailureCase = snapshot.artifacts.failures.find((item) => item.failureCase.failureCaseId === goldenDemoProfile.selected.flagship_failure_case);
  const flagshipCluster = snapshot.artifacts.failureClusters.find((item) => item.cluster.clusterId === goldenDemoProfile.selected.flagship_failure_cluster);
  const bisect = snapshot.artifacts.versionBisects.find((item) => item.bisect.bisectId === goldenDemoProfile.selected.version_bisect);
  const unknownOutcomeRun = snapshot.artifacts.allRuns.find((item) => item.run.runId === goldenDemoProfile.selected.unknown_outcome_run);
  const statisticalComparison = snapshot.statistical.comparisons.find((item) => item.statisticalComparison.comparisonId === goldenDemoProfile.selected.statistical_comparison);
  const unknownReconcile = unknownOutcomeRun?.trajectory.find((event) => event.eventType === "reconcile");
  const unknownMutation = unknownOutcomeRun?.trajectory.find((event) => event.eventType === "environment_transition");

  return {
    productionAgent,
    incidentAgent,
    candidateEvaluation,
    candidateDecision,
    flagshipFailureCase,
    flagshipCluster,
    bisect,
    unknownOutcomeRun,
    statisticalComparison,
    statisticalEvaluations: statisticalRows.map((row) => {
      const evaluation = snapshot.statistical.evaluations.find((item) => item.statisticalEvaluation.evaluationId === row.id);
      const decision = snapshot.statistical.decisions.find((item) => item.statisticalReleaseDecision.evaluationRef.evaluation_id === row.id);
      return {
        ...row,
        evaluation,
        decisionStatus: decision?.statisticalReleaseDecision.decisionStatus,
      };
    }),
    unknownReconcile,
    unknownEffectCount: firstPresent(
      valueAt(unknownMutation?.payload, "effect_count"),
      valueAt(valueAt(unknownMutation?.payload, "result"), "effect_count"),
      valueAt(unknownOutcomeRun?.verification?.evidence, "effect_count"),
    ),
    firstDivergence: firstPresent(
      valueAt(flagshipFailureCase?.failureObservation, "failing_event_id"),
      valueAt(flagshipFailureCase?.failureObservation, "first_meaningful_divergence"),
    ),
    familySignature: firstPresent(
      valueAt(flagshipCluster?.cluster.familySignature, "domain_family"),
      valueAt(flagshipCluster?.cluster.familySignature, "value"),
    ),
    firstBadCandidate: firstPresent(
      valueAt(bisect?.bisect.firstBadCandidate, "candidate_id"),
      valueAt(bisect?.bisect.firstBadCandidate, "candidate_version"),
      valueAt(bisect?.bisect.firstBadCandidate, "version"),
    ),
    comparisonClassification: statisticalComparison
      ? String(valueAt(statisticalComparison.statisticalComparison.aggregate, "classification") || "")
      : undefined,
  };
};

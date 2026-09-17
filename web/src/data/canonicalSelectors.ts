import type {
  AgentSummary,
  EvaluationComparison,
  EvaluationResult,
  FailureCase,
  FailureCluster,
  Regression,
  ReleaseDecision,
  RunEvidence,
  VersionBisect,
} from "./artifacts";
import type { StatisticalComparison, StatisticalEvaluation, StatisticalTrial } from "./statistical";
import type { CanonicalSnapshot } from "./canonicalSnapshot";

export interface CanonicalRouteParams {
  runId?: string | null;
  agentId?: string | null;
  failureCaseId?: string | null;
  regressionId?: string | null;
  evaluationId?: string | null;
  comparisonId?: string | null;
  releaseDecisionId?: string | null;
  clusterId?: string | null;
  bisectId?: string | null;
  statisticalEvaluationId?: string | null;
  statisticalComparisonId?: string | null;
}

export interface CanonicalRouteSelection {
  run?: RunEvidence;
  agent?: AgentSummary;
  failureCase?: FailureCase;
  regression?: Regression;
  evaluation?: EvaluationResult;
  comparison?: EvaluationComparison;
  releaseDecision?: ReleaseDecision;
  cluster?: FailureCluster;
  bisect?: VersionBisect;
  statisticalEvaluation?: StatisticalEvaluation;
  statisticalComparison?: StatisticalComparison;
}

const byId = <T>(items: T[], id: string | null | undefined, readId: (item: T) => string): T | undefined => {
  if (!id) return undefined;
  return items.find((item) => readId(item) === id);
};

export const selectCanonicalEntities = (
  snapshot: CanonicalSnapshot,
  params: CanonicalRouteParams,
): CanonicalRouteSelection => ({
  run: byId(snapshot.artifacts.allRuns, params.runId, (item) => item.run.runId),
  agent: byId(snapshot.artifacts.agents, params.agentId, (item) => item.agentId),
  failureCase: byId(snapshot.artifacts.failures, params.failureCaseId, (item) => item.failureCase.failureCaseId),
  regression: byId(snapshot.artifacts.regressions, params.regressionId, (item) => item.regression.regressionId),
  evaluation: byId(snapshot.artifacts.evaluations, params.evaluationId, (item) => item.evaluation.evaluationId),
  comparison: byId(snapshot.artifacts.comparisons, params.comparisonId, (item) => item.comparison.comparisonId),
  releaseDecision: byId(snapshot.artifacts.releaseDecisions, params.releaseDecisionId, (item) => item.releaseDecision.releaseDecisionId),
  cluster: byId(snapshot.artifacts.failureClusters, params.clusterId, (item) => item.cluster.clusterId),
  bisect: byId(snapshot.artifacts.versionBisects, params.bisectId, (item) => item.bisect.bisectId),
  statisticalEvaluation: byId(snapshot.statistical.evaluations, params.statisticalEvaluationId, (item) => item.statisticalEvaluation.evaluationId),
  statisticalComparison: byId(snapshot.statistical.comparisons, params.statisticalComparisonId, (item) => item.statisticalComparison.comparisonId),
});

export const selectStatisticalEvaluation = (snapshot: CanonicalSnapshot, id: string): StatisticalEvaluation | undefined =>
  byId(snapshot.statistical.evaluations, id, (item) => item.statisticalEvaluation.evaluationId);

export const selectStatisticalComparison = (snapshot: CanonicalSnapshot, id: string) =>
  byId(snapshot.statistical.comparisons, id, (item) => item.statisticalComparison.comparisonId);

export const selectStatisticalSamplingPlan = (snapshot: CanonicalSnapshot, id: string) =>
  byId(snapshot.statistical.samplingPlans, id, (item) => item.samplingPlan.samplingPlanId);

export const selectStatisticalGateForEvaluation = (snapshot: CanonicalSnapshot, id: string) =>
  snapshot.statistical.gates.find((item) => item.statisticalGate.evaluationRef.evaluation_id === id);

export const selectStatisticalDecisionForEvaluation = (snapshot: CanonicalSnapshot, id: string) =>
  snapshot.statistical.decisions.find((item) => item.statisticalReleaseDecision.evaluationRef.evaluation_id === id);

export type TrialRefResolutionStatus = "RESOLVED" | "UNAVAILABLE" | "INVALID_REF";

export interface StatisticalTrialResolution {
  trial: StatisticalTrial;
  status: TrialRefResolutionStatus;
  runId: string | null;
  environmentId: string | null;
  run: RunEvidence | undefined;
}

const refId = (value: unknown, key: string): string | null => {
  if (value === null || value === undefined) return null;
  if (typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = (value as Record<string, unknown>)[key];
  return typeof candidate === "string" && candidate ? candidate : null;
};

export const resolveStatisticalTrial = (
  snapshot: CanonicalSnapshot,
  trial: StatisticalTrial,
): StatisticalTrialResolution => {
  const runRefPresent = trial.runRef !== null;
  const runId = refId(trial.runRef, "run_id");
  const environmentId = refId(trial.environmentRef, "environment_id");
  if (!runRefPresent) return { trial, status: "UNAVAILABLE", runId: null, environmentId, run: undefined };
  if (!runId) return { trial, status: "INVALID_REF", runId: null, environmentId, run: undefined };
  const run = snapshot.artifacts.allRuns.find((item) => item.run.runId === runId);
  return { trial, status: run ? "RESOLVED" : "UNAVAILABLE", runId, environmentId, run };
};

export interface StatisticalTrialCoverage {
  total: number;
  resolved: number;
  unavailable: number;
  invalid: number;
  rows: StatisticalTrialResolution[];
}

export const selectStatisticalTrialCoverage = (
  snapshot: CanonicalSnapshot,
  evaluation: StatisticalEvaluation,
): StatisticalTrialCoverage => {
  const rows = evaluation.statisticalEvaluation.trials.map((trial) => resolveStatisticalTrial(snapshot, trial));
  return {
    total: rows.length,
    resolved: rows.filter((row) => row.status === "RESOLVED").length,
    unavailable: rows.filter((row) => row.status === "UNAVAILABLE").length,
    invalid: rows.filter((row) => row.status === "INVALID_REF").length,
    rows,
  };
};

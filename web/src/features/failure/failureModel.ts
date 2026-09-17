import type {
  FailureCase,
  FailureCluster,
  FailureIntelligence,
  Regression,
  RunEvidence,
} from "../../data/artifacts";
import type { CanonicalSnapshot } from "../../data/canonicalSnapshot";

export interface FailureCaseEvidenceModel {
  sourceRun: RunEvidence | undefined;
  reproductionRun: RunEvidence | undefined;
  intelligence: FailureIntelligence | undefined;
  intelligenceCluster: FailureCluster | undefined;
  promotedRegression: Regression | undefined;
}

const valueAt = (value: unknown, key: string): unknown => (
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>)[key] : undefined
);

export const selectFailureCaseEvidence = (
  snapshot: CanonicalSnapshot,
  failureCase: FailureCase,
): FailureCaseEvidenceModel => {
  const sourceRun = snapshot.artifacts.allRuns.find((item) => item.run.runId === failureCase.sourceRun.runId);
  const attempt = failureCase.reproductionAttempts[0];
  const reproductionRun = attempt ? snapshot.artifacts.allRuns.find((item) => item.run.runId === attempt.runId) : undefined;
  const intelligence = snapshot.artifacts.failureIntelligence.find((item) => (
    valueAt(item.intelligence.sourceFailureCaseRef, "failure_case_id") === failureCase.failureCase.failureCaseId
  ));
  const familyValue = valueAt(intelligence?.intelligence.familySignatures.crossAgent, "value");
  const intelligenceCluster = snapshot.artifacts.failureClusters.find((item) => valueAt(item.cluster.familySignature, "value") === familyValue);
  const promotedRegressionId = valueAt(valueAt(failureCase.promotion, "regression_ref"), "regression_id");
  const promotedRegression = typeof promotedRegressionId === "string"
    ? snapshot.artifacts.regressions.find((item) => item.regression.regressionId === promotedRegressionId)
    : undefined;

  return { sourceRun, reproductionRun, intelligence, intelligenceCluster, promotedRegression };
};

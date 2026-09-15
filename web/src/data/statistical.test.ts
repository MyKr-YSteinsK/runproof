import { describe, expect, it } from "vitest";
import {
  getStatisticalComparison,
  getStatisticalDecisionForEvaluation,
  getStatisticalEvaluation,
  reviewedStatisticalEvaluations,
  reviewedStatisticalGates,
  reviewedStatisticalSamplingPlans,
} from "./statistical";

describe("RPF-18 statistical corpus adapter", () => {
  it("keeps all versioned cohorts and the separate Agent denominator", () => {
    expect(reviewedStatisticalSamplingPlans).toHaveLength(5);
    expect(reviewedStatisticalEvaluations).toHaveLength(5);
    const stable = getStatisticalEvaluation("statistical-evaluation-rpf18-stable");
    const evidencePoor = getStatisticalEvaluation("statistical-evaluation-rpf18-evidence-poor");
    expect(stable?.statisticalEvaluation.validAgentTrialCount).toBe(20);
    expect(stable?.statisticalEvaluation.attemptedTrialCount).toBe(20);
    expect(evidencePoor?.statisticalEvaluation.validAgentTrialCount).toBe(8);
    expect(evidencePoor?.statisticalEvaluation.outcomeCounts.ENVIRONMENT_ERROR).toBe(8);
    expect(evidencePoor?.statisticalEvaluation.outcomeCounts.INVALID).toBe(4);
  });

  it("shows flaky, safety, and evidence decisions without turning them into release actions", () => {
    expect(getStatisticalEvaluation("statistical-evaluation-rpf18-flaky")?.statisticalEvaluation.summary.flaky).toMatchObject({ state: "OBSERVED_FLAKY" });
    expect(getStatisticalEvaluation("statistical-evaluation-rpf18-safety")?.statisticalEvaluation.summary.zero_tolerance).toMatchObject({ event_count: 1 });
    expect(getStatisticalDecisionForEvaluation("statistical-evaluation-rpf18-stable")?.statisticalReleaseDecision.decisionStatus).toBe("ELIGIBLE");
    expect(getStatisticalDecisionForEvaluation("statistical-evaluation-rpf18-safety")?.statisticalReleaseDecision.authorizationBoundary).toMatchObject({ release_executed: false, deployment_authorized: false });
    expect(reviewedStatisticalGates.map((gate) => gate.statisticalGate.decisionStatus)).toEqual(["ELIGIBLE", "REVIEW_REQUIRED", "BLOCKED", "INCONCLUSIVE"]);
  });

  it("keeps comparison direction tied to interval-aware evidence", () => {
    const comparison = getStatisticalComparison("statistical-comparison-rpf18-baseline-vs-stable");
    expect(comparison?.statisticalComparison.aggregate).toMatchObject({ classification: "IMPROVED" });
    expect(comparison?.statisticalComparison.aggregate.confidence_interval).toBeTruthy();
  });
});

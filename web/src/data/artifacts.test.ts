import { describe, expect, it } from "vitest";
import historicalNormal from "../../../runtime/reviewed-normal-run.json";
import { getEvaluation, getEvaluationComparison, getFailureCaseForRun, getRegression, getRegressionResultForRun, getRegressionResults, getRun, normalizeArtifact, reviewedEvaluationComparison, reviewedEvaluationRuns, reviewedEvaluationSuite, reviewedEvaluations, reviewedFailureCases, reviewedRegressionCollection, reviewedRegressions, reviewedRuns } from "./artifacts";

describe("reviewed evidence adapter", () => {
  it("loads only the current v2 reviewed corpus", () => {
    expect(reviewedRuns).toHaveLength(8);
    expect(reviewedRuns.every((run) => run.schemaVersion === "rpf-run-evidence-v2")).toBe(true);
    expect(reviewedRuns.map((run) => run.outcome.status)).toEqual(["PASS", "PASS", "FAIL", "ERROR", "FAIL", "FAIL", "FAIL", "PASS"]);
    expect(reviewedRuns.every((run) => run.llmProvider.provider_type === "llm")).toBe(true);
    expect(reviewedRuns.every((run) => run.environmentProvider.provider_type === "environment")).toBe(true);
  });

  it("rejects historical v1 as an active v2 run without rewriting its identity", () => {
    expect(() => normalizeArtifact(historicalNormal)).toThrow(/Unsupported active evidence schema: rpf-run-evidence-v1/);
  });

  it("preserves stable event identity and explicit ordering", () => {
    for (const run of reviewedRuns) {
      const ids = run.trajectory.map((event) => event.eventId);
      expect(new Set(ids).size).toBe(ids.length);
      expect(run.trajectory.map((event) => event.sequence)).toEqual(ids.map((_, index) => index + 1));
      expect(run.trajectory.every((event) => event.entityRefs.run_id === run.run.runId)).toBe(true);
    }
  });

  it("keeps response-lost PASS semantically separate from FAIL", () => {
    const faulted = reviewedRuns.find((run) => run.fault.planned);
    expect(faulted?.outcome.status).toBe("PASS");
    expect(faulted?.fault.triggered).toBe(true);
    expect(faulted?.fault.reconciled).toBe(true);
    expect(faulted?.verification?.evidence.blind_retry_attempts).toBe(0);
  });

  it("keeps the validated Failure Case and additive Regression promotion link", () => {
    expect(reviewedFailureCases).toHaveLength(1);
    const failureCase = reviewedFailureCases[0];
    expect(failureCase.failureCase.workflowState).toBe("validated");
    expect(failureCase.failureCase.isRegression).toBe(false);
    expect(failureCase.failureCase.currentStatus).toBe("promoted");
    expect(failureCase.failureCase.regressionStatus).toBe("PROMOTED_TO_REGRESSION");
    expect(failureCase.promotion?.status).toBe("PROMOTED");
    expect(getFailureCaseForRun(failureCase.sourceRun.runId)?.failureCase.failureCaseId).toBe(failureCase.failureCase.failureCaseId);
    expect(getFailureCaseForRun(failureCase.reproductionAttempts[0].runId)?.failureCase.failureCaseId).toBe(failureCase.failureCase.failureCaseId);
  });

  it("loads one stable Historical Regression with separated focused results", () => {
    expect(reviewedRegressions).toHaveLength(1);
    const regression = reviewedRegressions[0];
    expect(regression.regression.regressionVersion).toBe("1.0.0");
    expect(regression.regression.regressionId).not.toContain("run-");
    expect(getRegression(regression.regression.regressionId)?.regression.category).toBe("Historical Regression");
    expect(reviewedRegressionCollection.members.map((member) => member.regressionId)).toContain(regression.regression.regressionId);
    expect(getRegressionResults(regression.regression.regressionId).map((item) => [item.result.runOutcome, item.result.regressionResult])).toEqual([["FAIL", "FAIL"], ["PASS", "PASS"]]);
  });

  it("loads the versioned Evaluation Suite and links independent member evidence", () => {
    expect(reviewedEvaluationSuite.suite.suiteId).toBe("rpf-minimal-reliability-suite");
    expect(reviewedEvaluationSuite.suite.suiteVersion).toBe("1.0.0");
    expect(reviewedEvaluationSuite.suite.members).toHaveLength(3);
    expect(reviewedEvaluationSuite.suite.members.map((member) => member.category)).toEqual(["Normal / Functional", "Recovery / Fault", "Historical Regression"]);
    expect(reviewedEvaluations.map((item) => item.evaluation.agent.agent_version)).toEqual(["1.0.0-known-bad-unsafe-precondition", "1.0.1-observe-before-mutation-fix"]);
    expect(reviewedEvaluationRuns).toHaveLength(6);
    expect(reviewedEvaluationRuns.every((run) => /^run-[0-9a-f-]+$/.test(run.run.runId))).toBe(true);
    expect(reviewedEvaluationRuns.every((run) => getRun(run.run.runId) === run)).toBe(true);
    expect(reviewedEvaluationRuns.filter((run) => run.fault.reconciled).length).toBe(1);
    expect(getEvaluation(reviewedEvaluations[0].evaluation.evaluationId)).toBe(reviewedEvaluations[0]);
    expect(getEvaluationComparison(reviewedEvaluationComparison.comparison.comparisonId)).toBe(reviewedEvaluationComparison);
    expect(reviewedEvaluationComparison.comparison.aggregate?.summary).toBe("CANDIDATE_IMPROVED");
    expect(reviewedEvaluationComparison.comparison.perMemberComparison.map((item) => item.classification)).toEqual(["IMPROVED", "IMPROVED", "IMPROVED"]);
    const candidateRegressionRun = reviewedEvaluationRuns[5];
    expect(getRegressionResultForRun(candidateRegressionRun.run.runId)?.result.regressionResult).toBe("PASS");
  });
});

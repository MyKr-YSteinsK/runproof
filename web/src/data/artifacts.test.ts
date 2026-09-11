import { describe, expect, it } from "vitest";
import historicalNormal from "../../../runtime/reviewed-normal-run.json";
import { getFailureCaseForRun, normalizeArtifact, reviewedFailureCases, reviewedRuns } from "./artifacts";

describe("reviewed evidence adapter", () => {
  it("loads only the current v2 reviewed corpus", () => {
    expect(reviewedRuns).toHaveLength(5);
    expect(reviewedRuns.every((run) => run.schemaVersion === "rpf-run-evidence-v2")).toBe(true);
    expect(reviewedRuns.map((run) => run.outcome.status)).toEqual(["PASS", "PASS", "FAIL", "ERROR", "FAIL"]);
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

  it("loads a validated Failure Case without promoting it to Regression", () => {
    expect(reviewedFailureCases).toHaveLength(1);
    const failureCase = reviewedFailureCases[0];
    expect(failureCase.failureCase.workflowState).toBe("validated");
    expect(failureCase.failureCase.isRegression).toBe(false);
    expect(failureCase.failureCase.regressionStatus).toBe("NOT_A_REGRESSION");
    expect(getFailureCaseForRun(failureCase.sourceRun.runId)?.failureCase.failureCaseId).toBe(failureCase.failureCase.failureCaseId);
    expect(getFailureCaseForRun(failureCase.reproductionAttempts[0].runId)?.failureCase.failureCaseId).toBe(failureCase.failureCase.failureCaseId);
  });
});

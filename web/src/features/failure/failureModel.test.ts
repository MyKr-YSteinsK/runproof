import { describe, expect, it } from "vitest";
import { createCanonicalSnapshot } from "../../data/canonicalSnapshot";
import { goldenDemoProfile } from "../../data/goldenDemo";
import { selectFailureCaseEvidence } from "./failureModel";

describe("selectFailureCaseEvidence", () => {
  it("resolves related evidence from the active canonical snapshot", () => {
    const snapshot = createCanonicalSnapshot("fixture");
    const failureCase = snapshot.artifacts.failures.find((item) => item.failureCase.failureCaseId === goldenDemoProfile.selected.flagship_failure_case);

    expect(failureCase).toBeDefined();
    const related = selectFailureCaseEvidence(snapshot, failureCase!);
    expect(related.sourceRun?.run.runId).toBe(failureCase!.sourceRun.runId);
    expect(related.reproductionRun).toBeDefined();
  });

  it("keeps missing related evidence unavailable instead of manufacturing a link", () => {
    const snapshot = createCanonicalSnapshot("fixture");
    const failureCase = snapshot.artifacts.failures.find((item) => item.failureCase.failureCaseId === goldenDemoProfile.selected.flagship_failure_case)!;
    const withoutRun = {
      ...snapshot,
      artifacts: {
        ...snapshot.artifacts,
        allRuns: snapshot.artifacts.allRuns.filter((item) => item.run.runId !== failureCase.sourceRun.runId),
      },
    };

    expect(selectFailureCaseEvidence(withoutRun, failureCase).sourceRun).toBeUndefined();
  });
});

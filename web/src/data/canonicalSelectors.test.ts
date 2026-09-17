import { describe, expect, it } from "vitest";
import { createCanonicalSnapshot } from "./canonicalSnapshot";
import {
  selectCanonicalEntities,
  selectStatisticalTrialCoverage,
} from "./canonicalSelectors";

describe("canonical snapshot selectors", () => {
  it("recomputes from a new snapshot when an entity appears or is removed", () => {
    const snapshot = createCanonicalSnapshot("fixture");
    const id = snapshot.artifacts.allRuns[0].run.runId;
    expect(selectCanonicalEntities(snapshot, { runId: id }).run?.run.runId).toBe(id);

    const updated = {
      ...snapshot,
      revision: snapshot.revision + 1,
      artifacts: { ...snapshot.artifacts, allRuns: [] },
    };
    expect(selectCanonicalEntities(updated, { runId: id }).run).toBeUndefined();
  });

  it("keeps loading/unavailable selection separate from a true missing entity", () => {
    const snapshot = createCanonicalSnapshot("fixture");
    const selection = selectCanonicalEntities(snapshot, { runId: "missing-run" });
    expect(selection.run).toBeUndefined();
    expect(snapshot.source).toBe("fixture");
  });

  it("classifies every statistical trial reference without inventing a Run", () => {
    const snapshot = createCanonicalSnapshot("fixture");
    const evaluation = snapshot.statistical.evaluations[0];
    const updated = {
      ...snapshot,
      artifacts: {
        ...snapshot.artifacts,
        allRuns: snapshot.artifacts.allRuns.slice(0, 1),
      },
    };
    const coverage = selectStatisticalTrialCoverage(updated, {
      ...evaluation,
      statisticalEvaluation: {
        ...evaluation.statisticalEvaluation,
        trials: [
          { ...evaluation.statisticalEvaluation.trials[0], runRef: null },
          { ...evaluation.statisticalEvaluation.trials[0], trialId: "invalid", runRef: {} },
          { ...evaluation.statisticalEvaluation.trials[0], trialId: "missing", runRef: { run_id: "missing-run" } },
          { ...evaluation.statisticalEvaluation.trials[0], trialId: "resolved", runRef: { run_id: snapshot.artifacts.allRuns[0].run.runId } },
        ],
      },
    });
    expect(coverage).toMatchObject({ total: 4, resolved: 1, unavailable: 2, invalid: 1 });
    expect(coverage.rows.map((row) => row.status)).toEqual(["UNAVAILABLE", "INVALID_REF", "UNAVAILABLE", "RESOLVED"]);
    expect(coverage.rows[0].run).toBeUndefined();
  });
});

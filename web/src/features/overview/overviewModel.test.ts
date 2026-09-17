import { describe, expect, it } from "vitest";
import { createCanonicalSnapshot } from "../../data/canonicalSnapshot";
import { goldenDemoProfile } from "../../data/goldenDemo";
import { selectGoldenDemoOverview } from "./overviewModel";

describe("selectGoldenDemoOverview", () => {
  it("selects every overview claim from the active canonical snapshot", () => {
    const model = selectGoldenDemoOverview(createCanonicalSnapshot("fixture"));

    expect(model.candidateEvaluation?.evaluation.evaluationId).toBe(goldenDemoProfile.selected.candidate_evaluation);
    expect(model.candidateDecision?.releaseDecision.releaseDecisionId).toBe(goldenDemoProfile.selected.release_decision);
    expect(model.statisticalEvaluations).toHaveLength(4);
  });

  it("does not manufacture expected success when an entity is absent", () => {
    const snapshot = createCanonicalSnapshot("fixture");
    const withoutCandidate = {
      ...snapshot,
      artifacts: {
        ...snapshot.artifacts,
        evaluations: snapshot.artifacts.evaluations.filter((item) => item.evaluation.evaluationId !== goldenDemoProfile.selected.candidate_evaluation),
        releaseDecisions: snapshot.artifacts.releaseDecisions.filter((item) => item.releaseDecision.releaseDecisionId !== goldenDemoProfile.selected.release_decision),
      },
    };

    const model = selectGoldenDemoOverview(withoutCandidate);

    expect(model.candidateEvaluation).toBeUndefined();
    expect(model.candidateDecision).toBeUndefined();
    expect(model.comparisonClassification).toBeDefined();
    expect(model.statisticalEvaluations.every((item) => item.evaluation || item.decisionStatus === undefined)).toBe(true);
  });
});

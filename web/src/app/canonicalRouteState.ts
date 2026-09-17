import { selectCanonicalEntities, type CanonicalRouteParams, type CanonicalRouteSelection } from "../data/canonicalSelectors";
import type { CanonicalSnapshot } from "../data/canonicalSnapshot";

export type CanonicalDataStatus = "loading" | "ready" | "error";
export type CanonicalRouteState =
  | { kind: "loading" }
  | { kind: "unavailable" }
  | { kind: "ready"; selection: CanonicalRouteSelection }
  | { kind: "not-found"; selection: CanonicalRouteSelection };

const routeKeys: Array<keyof CanonicalRouteParams> = [
  "runId",
  "agentId",
  "failureCaseId",
  "regressionId",
  "evaluationId",
  "comparisonId",
  "releaseDecisionId",
  "clusterId",
  "bisectId",
  "statisticalEvaluationId",
  "statisticalComparisonId",
];

const hasDeepLink = (params: CanonicalRouteParams): boolean => routeKeys.some((key) => Boolean(params[key]));

const hasSelection = (selection: CanonicalRouteSelection): boolean => Object.values(selection).some(Boolean);

export const resolveCanonicalRouteState = (
  status: CanonicalDataStatus,
  snapshot: CanonicalSnapshot,
  params: CanonicalRouteParams,
): CanonicalRouteState => {
  if (status === "loading") return { kind: "loading" };
  if (status === "error") return { kind: "unavailable" };
  const selection = selectCanonicalEntities(snapshot, params);
  return hasDeepLink(params) && !hasSelection(selection)
    ? { kind: "not-found", selection }
    : { kind: "ready", selection };
};

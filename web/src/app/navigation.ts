export type LocationState = {
  pathname: string;
  runId: string | null;
  eventId: string | null;
  agentId: string | null;
  failureCaseId: string | null;
  regressionId: string | null;
  evaluationId: string | null;
  comparisonId: string | null;
  releaseDecisionId: string | null;
  executionJobId: string | null;
  clusterId: string | null;
  bisectId: string | null;
  statisticalEvaluationId: string | null;
  statisticalComparisonId: string | null;
};

export const readLocation = (): LocationState => {
  const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
  const agentMatch = pathname.match(/^\/agents\/([^/]+)$/);
  const runMatch = pathname.match(/^\/runs\/([^/]+)$/);
  const failureMatch = pathname.match(/^\/failures\/([^/]+)$/);
  const regressionMatch = pathname.match(/^\/regressions\/([^/]+)$/);
  const evaluationMatch = pathname.match(/^\/evaluations\/([^/]+)$/);
  const comparisonMatch = pathname.match(/^\/comparisons\/([^/]+)$/);
  const statisticalEvaluationMatch = pathname.match(/^\/statistical-evaluations\/([^/]+)$/);
  const statisticalComparisonMatch = pathname.match(/^\/statistical-comparisons\/([^/]+)$/);
  const releaseDecisionMatch = pathname.match(/^\/release-decisions\/([^/]+)$/);
  const executionMatch = pathname.match(/^\/executions\/([^/]+)$/);
  const clusterMatch = pathname.match(/^\/failure-intelligence\/clusters\/([^/]+)$/);
  const bisectMatch = pathname.match(/^\/version-bisects\/([^/]+)$/);
  return {
    pathname,
    runId: runMatch ? decodeURIComponent(runMatch[1]) : null,
    eventId: new URLSearchParams(window.location.search).get("event"),
    agentId: agentMatch ? decodeURIComponent(agentMatch[1]) : null,
    failureCaseId: failureMatch ? decodeURIComponent(failureMatch[1]) : null,
    regressionId: regressionMatch ? decodeURIComponent(regressionMatch[1]) : null,
    evaluationId: evaluationMatch ? decodeURIComponent(evaluationMatch[1]) : null,
    comparisonId: comparisonMatch ? decodeURIComponent(comparisonMatch[1]) : null,
    releaseDecisionId: releaseDecisionMatch ? decodeURIComponent(releaseDecisionMatch[1]) : null,
    executionJobId: executionMatch ? decodeURIComponent(executionMatch[1]) : null,
    clusterId: clusterMatch ? decodeURIComponent(clusterMatch[1]) : null,
    bisectId: bisectMatch ? decodeURIComponent(bisectMatch[1]) : null,
    statisticalEvaluationId: statisticalEvaluationMatch ? decodeURIComponent(statisticalEvaluationMatch[1]) : null,
    statisticalComparisonId: statisticalComparisonMatch ? decodeURIComponent(statisticalComparisonMatch[1]) : null,
  };
};

export const navigate = (to: string): void => {
  window.history.pushState({}, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
};

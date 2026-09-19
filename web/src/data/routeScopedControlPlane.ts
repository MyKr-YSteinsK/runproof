import {
  activateControlPlaneCorpus,
  type ControlPlaneCorpusPayload,
} from "./artifacts";
import { createCanonicalSnapshot, type CanonicalSnapshot } from "./canonicalSnapshot";
import {
  loadControlPlaneCanonicalDetail,
  loadControlPlaneMetadataPage,
  type ControlPlaneCanonicalDetailDto,
  type ControlPlaneMetadataPageDto,
} from "./controlPlaneApi";
import { ControlPlaneApiError } from "./controlPlaneApi";
import { goldenDemoProfile } from "./goldenDemo";
import type { MessageKey } from "../i18n/messages";

export type CanonicalEntityType =
  | "RUN"
  | "FAILURE_CASE"
  | "REGRESSION"
  | "EVALUATION"
  | "COMPARISON"
  | "RELEASE_DECISION"
  | "FAILURE_INTELLIGENCE"
  | "FAILURE_CLUSTER"
  | "VERSION_BISECT"
  | "STATISTICAL_EVALUATION"
  | "STATISTICAL_COMPARISON";

export interface ApiIndexRouteData {
  kind: "index";
  path: string;
  entityType: CanonicalEntityType;
  page: ControlPlaneMetadataPageDto;
  cursor: string | null;
}

export interface ApiDetailRouteData {
  kind: "detail";
  path: string;
  entityType: CanonicalEntityType;
  entityId: string;
  detail: ControlPlaneCanonicalDetailDto;
}

export interface ApiOverviewRouteData {
  kind: "overview";
  path: string;
  snapshot: CanonicalSnapshot;
}

export interface ApiAgentDetailRouteData {
  kind: "agent";
  path: string;
  agentId: string;
  domain: string;
  role: string;
  representativeRunId: string;
  detail: ControlPlaneCanonicalDetailDto;
}

export type ApiRouteData = ApiIndexRouteData | ApiDetailRouteData | ApiOverviewRouteData | ApiAgentDetailRouteData;

export interface ApiIndexDefinition {
  path: string;
  entityType: CanonicalEntityType;
  titleKey: MessageKey;
  eyebrowKey: MessageKey;
  descriptionKey: MessageKey;
}

export const API_INDEX_DEFINITIONS: ApiIndexDefinition[] = [
  { path: "/runs", entityType: "RUN", titleKey: "canonical.route.runsTitle", eyebrowKey: "canonical.route.runsEyebrow", descriptionKey: "canonical.route.runsDescription" },
  { path: "/failures", entityType: "FAILURE_CASE", titleKey: "canonical.route.failuresTitle", eyebrowKey: "canonical.route.failuresEyebrow", descriptionKey: "canonical.route.failuresDescription" },
  { path: "/regressions", entityType: "REGRESSION", titleKey: "canonical.route.regressionsTitle", eyebrowKey: "canonical.route.regressionsEyebrow", descriptionKey: "canonical.route.regressionsDescription" },
  { path: "/evaluations", entityType: "EVALUATION", titleKey: "canonical.route.evaluationsTitle", eyebrowKey: "canonical.route.evaluationsEyebrow", descriptionKey: "canonical.route.evaluationsDescription" },
  { path: "/comparisons", entityType: "COMPARISON", titleKey: "canonical.route.comparisonsTitle", eyebrowKey: "canonical.route.comparisonsEyebrow", descriptionKey: "canonical.route.comparisonsDescription" },
  { path: "/release-decisions", entityType: "RELEASE_DECISION", titleKey: "canonical.route.releaseDecisionsTitle", eyebrowKey: "canonical.route.releaseDecisionsEyebrow", descriptionKey: "canonical.route.releaseDecisionsDescription" },
  { path: "/failure-intelligence", entityType: "FAILURE_INTELLIGENCE", titleKey: "canonical.route.failureIntelligenceTitle", eyebrowKey: "canonical.route.failureIntelligenceEyebrow", descriptionKey: "canonical.route.failureIntelligenceDescription" },
  { path: "/statistical-evaluations", entityType: "STATISTICAL_EVALUATION", titleKey: "canonical.route.statisticalEvaluationsTitle", eyebrowKey: "canonical.route.statisticalEvaluationsEyebrow", descriptionKey: "canonical.route.statisticalEvaluationsDescription" },
  { path: "/statistical-comparisons", entityType: "STATISTICAL_COMPARISON", titleKey: "canonical.route.statisticalComparisonsTitle", eyebrowKey: "canonical.route.statisticalComparisonsEyebrow", descriptionKey: "canonical.route.statisticalComparisonsDescription" },
  // Agents are a derived view rather than a canonical metadata entity. The
  // API route intentionally presents a bounded RUN-derived registry until a
  // dedicated server-side Agent read model is warranted.
  { path: "/agents", entityType: "RUN", titleKey: "canonical.route.agentsTitle", eyebrowKey: "canonical.route.agentsEyebrow", descriptionKey: "canonical.route.agentsDescription" },
];

const DETAIL_ROUTES: Array<{ prefix: string; entityType: CanonicalEntityType }> = [
  { prefix: "/runs/", entityType: "RUN" },
  { prefix: "/failures/", entityType: "FAILURE_CASE" },
  { prefix: "/regressions/", entityType: "REGRESSION" },
  { prefix: "/evaluations/", entityType: "EVALUATION" },
  { prefix: "/comparisons/", entityType: "COMPARISON" },
  { prefix: "/release-decisions/", entityType: "RELEASE_DECISION" },
  { prefix: "/failure-intelligence/clusters/", entityType: "FAILURE_CLUSTER" },
  { prefix: "/failure-intelligence/", entityType: "FAILURE_INTELLIGENCE" },
  { prefix: "/version-bisects/", entityType: "VERSION_BISECT" },
  { prefix: "/statistical-evaluations/", entityType: "STATISTICAL_EVALUATION" },
  { prefix: "/statistical-comparisons/", entityType: "STATISTICAL_COMPARISON" },
];

const emptyPayload = (): ControlPlaneCorpusPayload => ({
  runs: [], failures: [], failureIntelligence: [], failureClusters: [], versionBisects: [],
  regressions: [], regressionResults: [], regressionCollections: [], evaluationSuites: [],
  evaluations: [], comparisons: [], qualityPolicies: [], qualityGates: [], releaseDecisions: [],
  statisticalSamplingPlans: [], statisticalEvaluations: [], statisticalComparisons: [],
  statisticalPolicies: [], statisticalGates: [], statisticalReleaseDecisions: [],
});

const payloadKey: Record<string, keyof ControlPlaneCorpusPayload> = {
  RUN: "runs",
  FAILURE_CASE: "failures",
  FAILURE_INTELLIGENCE: "failureIntelligence",
  FAILURE_CLUSTER: "failureClusters",
  VERSION_BISECT: "versionBisects",
  REGRESSION: "regressions",
  EVALUATION: "evaluations",
  COMPARISON: "comparisons",
  RELEASE_DECISION: "releaseDecisions",
  EVALUATION_SUITE: "evaluationSuites",
  QUALITY_POLICY: "qualityPolicies",
  QUALITY_GATE: "qualityGates",
  REGRESSION_COLLECTION: "regressionCollections",
  STATISTICAL_SAMPLING_PLAN: "statisticalSamplingPlans",
  STATISTICAL_EVALUATION: "statisticalEvaluations",
  STATISTICAL_COMPARISON: "statisticalComparisons",
  STATISTICAL_POLICY: "statisticalPolicies",
  STATISTICAL_GATE: "statisticalGates",
  STATISTICAL_RELEASE_DECISION: "statisticalReleaseDecisions",
};

const addDetail = (
  payload: ControlPlaneCorpusPayload,
  seen: Set<string>,
  detail: ControlPlaneCanonicalDetailDto,
): void => {
  const metadata = detail.metadata.canonical_metadata;
  const key = `${metadata.entity_type}:${metadata.entity_id}`;
  if (seen.has(key)) return;
  seen.add(key);
  const target = payloadKey[metadata.entity_type];
  if (target) payload[target].push(detail.artifact);
};

const overviewIds = (): Array<[string, string]> => {
  const refs = new Map<string, [string, string]>();
  for (const item of goldenDemoProfile.reviewed_artifacts) refs.set(`${item.entity_type}:${item.entity_id}`, [item.entity_type, item.entity_id]);
  const add = (entityType: string, entityId: string) => refs.set(`${entityType}:${entityId}`, [entityType, entityId]);
  add("EVALUATION_SUITE", "rpf-incident-remediation-suite");
  add("COMPARISON", "comparison-12421f28-9861-4a88-a17e-d33746d87e19");
  add("QUALITY_POLICY", "rpf-incident-quality-policy");
  add("REGRESSION_COLLECTION", "incident-historical-regressions-v1");
  // These are fixed aggregate dependencies of the Golden Demo snapshot. They
  // are explicit profile refs, not a cursor crawl and not a replacement for
  // route-scoped index reads.
  add("STATISTICAL_EVALUATION", "statistical-evaluation-rpf18-baseline");
  add("STATISTICAL_POLICY", "rpf-incident-statistical-policy");
  add("STATISTICAL_SAMPLING_PLAN", "sampling-plan-rpf18-baseline");
  for (const cohort of ["stable", "flaky", "safety", "evidence-poor"]) {
    add("STATISTICAL_SAMPLING_PLAN", `sampling-plan-rpf18-${cohort}`);
    add("STATISTICAL_GATE", `statistical-gate-rpf18-${cohort}`);
    add("STATISTICAL_RELEASE_DECISION", `statistical-decision-rpf18-${cohort}`);
  }
  return [...refs.values()];
};

const loadOverview = async (): Promise<CanonicalSnapshot> => {
  const payload = emptyPayload();
  const seen = new Set<string>();
  const refs = overviewIds();
  // The overview is intentionally a fixed Golden Demo surface, not a corpus
  // crawl. Keep its bounded detail reads in small batches so the browser's
  // local dev proxy and the read-only Control Plane do not become the
  // concurrency bottleneck when all reviewed refs are activated at once.
  const details: ControlPlaneCanonicalDetailDto[] = [];
  for (let index = 0; index < refs.length; index += 4) {
    const batch = refs.slice(index, index + 4);
    details.push(...await Promise.all(batch.map(([entityType, entityId]) => loadControlPlaneCanonicalDetail(entityType, entityId))));
  }
  details.forEach((detail) => addDetail(payload, seen, detail));
  activateControlPlaneCorpus(payload);
  return createCanonicalSnapshot("api", 1);
};

const decodePathId = (value: string): string => {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
};

const agentRepresentativeRun = (agentId: string): { domain: string; role: string; runId: string } | undefined => {
  const profileAgent = goldenDemoProfile.agents.find((agent) => agent.agent_id === agentId);
  if (!profileAgent) return undefined;
  const profileRef = goldenDemoProfile.reviewed_artifacts.find((item) => item.role === `agent.${agentId === "production-change-agent" ? "production_change" : "incident_remediation"}`);
  const runId = agentId === "incident-remediation-agent"
    ? goldenDemoProfile.selected.unknown_outcome_run
    : profileRef?.entity_type === "RUN" ? profileRef.entity_id : undefined;
  if (!runId) return undefined;
  return { domain: profileAgent.domain, role: profileAgent.role, runId };
};

export const indexDefinitionForPath = (pathname: string): ApiIndexDefinition | undefined =>
  API_INDEX_DEFINITIONS.find((definition) => definition.path === pathname);

export const loadRouteScopedControlPlaneData = async (
  pathname: string,
  search = "",
): Promise<ApiRouteData> => {
  if (pathname === "/" || pathname === "/overview") {
    return { kind: "overview", path: pathname, snapshot: await loadOverview() };
  }
  if (pathname.startsWith("/agents/")) {
    const agentId = decodePathId(pathname.slice("/agents/".length));
    if (!agentId || agentId.includes("/")) throw new ControlPlaneApiError("Agent was not found.", "CANONICAL_METADATA_NOT_FOUND", 404, false);
    const representative = agentRepresentativeRun(agentId);
    if (!representative) throw new ControlPlaneApiError("Agent was not found.", "CANONICAL_METADATA_NOT_FOUND", 404, false);
    return {
      kind: "agent",
      path: pathname,
      agentId,
      domain: representative.domain,
      role: representative.role,
      representativeRunId: representative.runId,
      detail: await loadControlPlaneCanonicalDetail("RUN", representative.runId),
    };
  }
  const detailRoute = DETAIL_ROUTES.find((route) => pathname.startsWith(route.prefix));
  if (detailRoute) {
    const entityId = decodePathId(pathname.slice(detailRoute.prefix.length));
    if (!entityId || entityId.includes("/")) throw new Error("NOT_FOUND");
    return {
      kind: "detail",
      path: pathname,
      entityType: detailRoute.entityType,
      entityId,
      detail: await loadControlPlaneCanonicalDetail(detailRoute.entityType, entityId),
    };
  }
  const definition = indexDefinitionForPath(pathname) || API_INDEX_DEFINITIONS[0];
  const params = new URLSearchParams(search);
  const cursor = params.get("cursor");
  return {
    kind: "index",
    path: definition.path,
    entityType: definition.entityType,
    cursor,
    page: await loadControlPlaneMetadataPage(definition.entityType, { limit: 50, cursor }),
  };
};

import type { ControlPlaneCorpusPayload } from "./artifacts";

export interface ControlPlaneArtifactRefDto {
  artifact_id: string;
  artifact_key: string;
  artifact_kind: string;
  schema_version: string;
  content_sha256: string;
  source_sha256: string;
  runtime_version: string;
  resolved: boolean;
  availability?: string;
  error_code?: string | null;
  artifact_url?: string;
}

export interface ControlPlaneMetadataDto {
  entity_type: string;
  entity_id: string;
  entity_schema_version: string;
  artifact_kind: string;
  outcome: string;
  agent_version: string | null;
  evaluation_id: string | null;
  supersedes_entity_id: string | null;
  source_identity: {
    source_sha256: string;
    runtime_version: string;
  };
  key_refs: Array<{ entity_type: string; entity_id: string; role: string }>;
  summary: Record<string, unknown>;
  artifact_ref: ControlPlaneArtifactRefDto;
  registered_by: string;
  created_at: string;
}

export interface ControlPlaneMetadataViewDto {
  canonical_metadata: ControlPlaneMetadataDto;
  artifact_resolution: ControlPlaneArtifactRefDto;
}

interface MetadataListResponse {
  items: ControlPlaneMetadataViewDto[];
}

interface ArtifactResponse {
  artifact_ref: ControlPlaneArtifactRefDto;
  artifact: unknown;
}

export class ControlPlaneApiError extends Error {
  readonly status: number | null;
  readonly code: string;
  readonly retriable: boolean;

  constructor(message: string, code: string, status: number | null, retriable: boolean) {
    super(message);
    this.name = "ControlPlaneApiError";
    this.code = code;
    this.status = status;
    this.retriable = retriable;
  }
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const normalizeBaseUrl = (value: string): string => value.replace(/\/+$/, "");

const jsonOrEmpty = async (response: Response): Promise<Record<string, unknown>> => {
  try {
    const value: unknown = await response.json();
    return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  } catch {
    return {};
  }
};

const requestJson = async <T>(baseUrl: string, path: string, fetcher: FetchLike): Promise<T> => {
  let response: Response;
  try {
    response = await fetcher(`${normalizeBaseUrl(baseUrl)}${path}`, {
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ControlPlaneApiError("Control Plane API is unavailable.", "API_UNAVAILABLE", null, true);
  }
  const body = await jsonOrEmpty(response);
  if (!response.ok) {
    const code = typeof body.error === "string" ? body.error : response.status >= 500 ? "PLATFORM_UNAVAILABLE" : "API_REQUEST_FAILED";
    throw new ControlPlaneApiError(
      "Control Plane API request failed.",
      code,
      response.status,
      Boolean(body.retriable) || response.status >= 500 || response.status === 429,
    );
  }
  return body as T;
};

const list = async (baseUrl: string, entityType: string, fetcher: FetchLike): Promise<ControlPlaneMetadataViewDto[]> => {
  const response = await requestJson<MetadataListResponse>(baseUrl, `/metadata?entity_type=${encodeURIComponent(entityType)}`, fetcher);
  if (!Array.isArray(response.items)) {
    throw new ControlPlaneApiError("Control Plane list response is malformed.", "INVALID_API_RESPONSE", null, false);
  }
  return response.items;
};

const artifact = async (baseUrl: string, item: ControlPlaneMetadataViewDto, fetcher: FetchLike): Promise<unknown> => {
  const metadata = item.canonical_metadata;
  const resolution = item.artifact_resolution;
  if (!resolution.resolved) {
    throw new ControlPlaneApiError(
      `Artifact unavailable for ${metadata.entity_type}/${metadata.entity_id}.`,
      resolution.error_code || "ARTIFACT_UNAVAILABLE",
      null,
      false,
    );
  }
  const path = resolution.artifact_url || `/artifacts/${encodeURIComponent(metadata.entity_type)}/${encodeURIComponent(metadata.entity_id)}`;
  const response = await requestJson<ArtifactResponse>(baseUrl, path, fetcher);
  if (!response.artifact || typeof response.artifact !== "object" || Array.isArray(response.artifact)) {
    throw new ControlPlaneApiError(
      `Artifact response is invalid for ${metadata.entity_type}/${metadata.entity_id}.`,
      "INVALID_ARTIFACT_RESPONSE",
      null,
      false,
    );
  }
  return response.artifact;
};

const resolveArtifacts = async (baseUrl: string, items: ControlPlaneMetadataViewDto[], fetcher: FetchLike): Promise<unknown[]> => {
  return Promise.all(items.map((item) => artifact(baseUrl, item, fetcher)));
};

/**
 * Loads one complete canonical snapshot before activation. A failed list or
 * artifact request rejects the whole snapshot; callers must show the API
 * error instead of silently rendering the old fixture corpus.
 */
export const loadControlPlaneCorpus = async (
  baseUrl = import.meta.env.VITE_CONTROL_PLANE_API_URL || "/api/v1",
  fetcher: FetchLike = fetch,
): Promise<ControlPlaneCorpusPayload> => {
  const [runs, failures, regressions, regressionResults, regressionCollection, evaluationSuite, evaluations, comparisons, policies, qualityGates, releaseDecisions] = await Promise.all([
    list(baseUrl, "RUN", fetcher),
    list(baseUrl, "FAILURE_CASE", fetcher),
    list(baseUrl, "REGRESSION", fetcher),
    list(baseUrl, "REGRESSION_RESULT", fetcher),
    list(baseUrl, "REGRESSION_COLLECTION", fetcher),
    list(baseUrl, "EVALUATION_SUITE", fetcher),
    list(baseUrl, "EVALUATION", fetcher),
    list(baseUrl, "COMPARISON", fetcher),
    list(baseUrl, "QUALITY_POLICY", fetcher),
    list(baseUrl, "QUALITY_GATE", fetcher),
    list(baseUrl, "RELEASE_DECISION", fetcher),
  ]);
  const [runArtifacts, failureArtifacts, regressionArtifacts, regressionResultArtifacts, collectionArtifacts, suiteArtifacts, evaluationArtifacts, comparisonArtifacts, policyArtifacts, gateArtifacts, decisionArtifacts] = await Promise.all([
    resolveArtifacts(baseUrl, runs, fetcher),
    resolveArtifacts(baseUrl, failures, fetcher),
    resolveArtifacts(baseUrl, regressions, fetcher),
    resolveArtifacts(baseUrl, regressionResults, fetcher),
    resolveArtifacts(baseUrl, regressionCollection, fetcher),
    resolveArtifacts(baseUrl, evaluationSuite, fetcher),
    resolveArtifacts(baseUrl, evaluations, fetcher),
    resolveArtifacts(baseUrl, comparisons, fetcher),
    resolveArtifacts(baseUrl, policies, fetcher),
    resolveArtifacts(baseUrl, qualityGates, fetcher),
    resolveArtifacts(baseUrl, releaseDecisions, fetcher),
  ]);
  const required = (values: unknown[], label: string): unknown[] => {
    if (values.length === 0) throw new ControlPlaneApiError(`Control Plane corpus is missing ${label}.`, "CORPUS_INCOMPLETE", null, false);
    return values;
  };
  return {
    runs: runArtifacts,
    failures: failureArtifacts,
    regressions: regressionArtifacts,
    regressionResults: regressionResultArtifacts,
    regressionCollections: required(collectionArtifacts, "Regression Collection"),
    evaluationSuites: required(suiteArtifacts, "Evaluation Suite"),
    evaluations: evaluationArtifacts,
    comparisons: required(comparisonArtifacts, "Evaluation Comparison"),
    qualityPolicies: required(policyArtifacts, "Quality Policy"),
    qualityGates: gateArtifacts,
    releaseDecisions: decisionArtifacts,
  };
};

export const controlPlaneDataSourceMode = (): "api" | "fixture" => {
  const mode = import.meta.env.VITE_CONTROL_PLANE_DATA_SOURCE;
  return mode === "fixture" ? "fixture" : "api";
};

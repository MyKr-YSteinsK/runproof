import { ControlPlaneApiError } from "./controlPlaneApi";

export interface ExecutionLeaseDto {
  attempt_id: string | null;
  worker_id: string | null;
  lease_version: number | null;
  lease_expires_at: string | null;
  lease_token_present: boolean;
}

export interface ExecutionAttemptDto {
  attempt_id: string;
  attempt_number: number;
  worker_id: string;
  lease_version: number;
  status: string;
  lease_expires_at: string | null;
  heartbeat_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  reason: string | null;
  created_at: string;
}

export interface ExecutionOperationDto {
  operation_id: string;
  attempt_id: string;
  environment_id: string;
  operation_fingerprint: string;
  status: string;
  effect_count: number;
  receipt_ref: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExecutionEvidenceDto {
  evidence_id: string;
  entity_type: string;
  entity_id: string;
  outcome: string;
  content_sha256: string;
  artifact_ref: Record<string, unknown>;
  created_at: string;
}

export interface ExecutionEventDto {
  event_id: number;
  from_state: string | null;
  to_state: string;
  event_type: string;
  attempt_id: string | null;
  operation_id: string | null;
  reason: string | null;
  version: number;
  occurred_at: string;
}

export interface ExecutionJobDto {
  job_id: string;
  idempotency_key: string;
  request_fingerprint: string;
  job_type: string;
  target: { type: string; id: string };
  correlation_id: string;
  state: string;
  version: number;
  attempt_number: number;
  active_attempt_id: string | null;
  active_worker_id: string | null;
  lease: ExecutionLeaseDto;
  cancel_requested: boolean;
  timeout_requested: boolean;
  outcome_status: string | null;
  platform_reason: string | null;
  terminal_evidence_id: string | null;
  last_operation_id: string | null;
  payload_ref: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  attempts: ExecutionAttemptDto[];
  operations: ExecutionOperationDto[];
  evidence: ExecutionEvidenceDto[];
  events: ExecutionEventDto[];
}

export interface ExecutionListResponse {
  items: ExecutionJobDto[];
  limit: number;
}

export interface ExecutionMetricsDto {
  queued_jobs: number;
  claimed_or_running_jobs: number;
  reconcile_required_jobs: number;
  completed_jobs: number;
  platform_failed_jobs: number;
  cancelled_jobs: number;
  lease_expiry_count: number;
  reclaim_count: number;
  stale_attempt_rejection_count: number;
  attempts_total: number;
  observability_boundary?: string;
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
    response = await fetcher(`${normalizeBaseUrl(baseUrl)}${path}`, { headers: { Accept: "application/json" } });
  } catch {
    throw new ControlPlaneApiError("Control Plane API is unavailable.", "API_UNAVAILABLE", null, true);
  }
  const body = await jsonOrEmpty(response);
  if (!response.ok) {
    const code = typeof body.error === "string" ? body.error : response.status >= 500 ? "PLATFORM_UNAVAILABLE" : "API_REQUEST_FAILED";
    throw new ControlPlaneApiError(
      "Control Plane execution API request failed.",
      code,
      response.status,
      Boolean(body.retriable) || response.status >= 500 || response.status === 429,
    );
  }
  return body as T;
};

const apiBaseUrl = (): string => import.meta.env.VITE_CONTROL_PLANE_API_URL || "/api/v1";

export const loadExecutionJobs = async (
  baseUrl = apiBaseUrl(),
  fetcher: FetchLike = fetch,
): Promise<ExecutionJobDto[]> => {
  const response = await requestJson<ExecutionListResponse>(baseUrl, "/jobs?limit=100", fetcher);
  if (!Array.isArray(response.items)) {
    throw new ControlPlaneApiError("Control Plane execution list response is malformed.", "INVALID_API_RESPONSE", null, false);
  }
  return response.items;
};

export const loadExecutionJob = async (
  jobId: string,
  baseUrl = apiBaseUrl(),
  fetcher: FetchLike = fetch,
): Promise<ExecutionJobDto> => {
  const response = await requestJson<ExecutionJobDto>(baseUrl, `/jobs/${encodeURIComponent(jobId)}`, fetcher);
  if (!response || typeof response.job_id !== "string" || !Array.isArray(response.events)) {
    throw new ControlPlaneApiError("Control Plane execution detail response is malformed.", "INVALID_API_RESPONSE", null, false);
  }
  return response;
};

export const loadExecutionMetrics = async (
  baseUrl = apiBaseUrl(),
  fetcher: FetchLike = fetch,
): Promise<ExecutionMetricsDto> => {
  const response = await requestJson<ExecutionMetricsDto>(baseUrl, "/execution-metrics", fetcher);
  if (!response || typeof response.completed_jobs !== "number" || typeof response.attempts_total !== "number") {
    throw new ControlPlaneApiError("Control Plane execution metrics response is malformed.", "INVALID_API_RESPONSE", null, false);
  }
  return response;
};

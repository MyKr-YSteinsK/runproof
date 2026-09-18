import { describe, expect, it } from "vitest";
import { ControlPlaneApiError } from "./controlPlaneApi";
import { loadExecutionJob, loadExecutionJobs, loadExecutionMetrics, loadExecutionTimeline } from "./executions";

class FakeResponse {
  ok: boolean;
  status: number;

  constructor(private readonly value: unknown, ok = true, status = 200) {
    this.ok = ok;
    this.status = status;
  }

  async json(): Promise<unknown> {
    return this.value;
  }
}

const job = {
  job_id: "job-1",
  job_type: "RUN",
  target: { type: "RUN", id: "run-1" },
  state: "RECONCILE_REQUIRED",
  version: 3,
  attempt_number: 1,
  active_attempt_id: "attempt-1",
  active_worker_id: "worker-1",
  lease: { attempt_id: "attempt-1", worker_id: "worker-1", lease_version: 3, lease_expires_at: null, lease_token_present: false },
  cancel_requested: false,
  timeout_requested: false,
  outcome_status: null,
  platform_reason: null,
  terminal_evidence_id: null,
  last_operation_id: null,
  created_at: "2026-09-18T00:00:00Z",
  updated_at: "2026-09-18T00:00:01Z",
  idempotency_key: "idem-1",
  request_fingerprint: "fingerprint-1",
  correlation_id: "correlation-1",
  payload_ref: { scenario_id: "scenario-1" },
  attempts: [],
  operations: [],
  evidence: [],
  timeline: { path: "/jobs/{jobId}/events", cursor_contract: "rpf-execution-cursor-v1", default_limit: 200, max_limit: 500, partial: true },
};

describe("durable execution read API", () => {
  it("loads the read-only job list and keeps the API path explicit", async () => {
    let requested = "";
    const fetcher = async (input: RequestInfo | URL) => {
      requested = String(input);
      return new FakeResponse({ items: [job], limit: 50, has_more: true, next_cursor: "next-1", discovery: "HISTORY" }) as unknown as Response;
    };

    await expect(loadExecutionJobs("/api/v1", fetcher, { limit: 50 })).resolves.toEqual({ items: [job], limit: 50, has_more: true, next_cursor: "next-1", discovery: "HISTORY" });
    expect(requested).toBe("/api/v1/jobs?limit=50");
  });

  it("loads detail without exposing a mutation helper or requiring a token in the browser", async () => {
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe("/api/v1/jobs/job%2F1");
      expect(init?.method).toBeUndefined();
      expect(init?.headers).toEqual({ Accept: "application/json" });
      return new FakeResponse(job) as unknown as Response;
    };

    await expect(loadExecutionJob("job/1", "/api/v1", fetcher)).resolves.toEqual(job);
  });

  it("loads an independent bounded event page", async () => {
    let requested = "";
    const fetcher = async (input: RequestInfo | URL) => {
      requested = String(input);
      return new FakeResponse({
        job_id: "job/1",
        items: [{ event_id: 1, from_state: null, to_state: "QUEUED", event_type: "submitted", attempt_id: null, operation_id: null, reason: null, version: 1, occurred_at: "2026-09-18T00:00:00Z" }],
        limit: 200,
        has_more: false,
        next_cursor: null,
        partial: false,
      }) as unknown as Response;
    };

    await expect(loadExecutionTimeline("job/1", "/api/v1", fetcher)).resolves.toMatchObject({ job_id: "job/1", limit: 200, has_more: false });
    expect(requested).toBe("/api/v1/jobs/job%2F1/events?limit=200");
  });

  it("fails closed on API errors and malformed metrics", async () => {
    const unavailable = async () => new FakeResponse({ error: "PLATFORM_STORAGE_UNAVAILABLE" }, false, 503) as unknown as Response;
    await expect(loadExecutionJobs("/api/v1", unavailable)).rejects.toMatchObject<Partial<ControlPlaneApiError>>({
      code: "PLATFORM_STORAGE_UNAVAILABLE",
      status: 503,
      retriable: true,
    });

    const malformed = async () => new FakeResponse({ items: [], limit: 50, has_more: false }) as unknown as Response;
    await expect(loadExecutionMetrics("/api/v1", malformed)).rejects.toMatchObject({ code: "INVALID_API_RESPONSE" });
  });
});

import { describe, expect, it } from "vitest";
import { ControlPlaneApiError } from "./controlPlaneApi";
import { loadExecutionJob, loadExecutionJobs, loadExecutionMetrics } from "./executions";

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
  state: "RECONCILE_REQUIRED",
  events: [{ event_id: 1, to_state: "RECONCILE_REQUIRED" }],
  attempts: [],
  operations: [],
  evidence: [],
};

describe("durable execution read API", () => {
  it("loads the read-only job list and keeps the API path explicit", async () => {
    let requested = "";
    const fetcher = async (input: RequestInfo | URL) => {
      requested = String(input);
      return new FakeResponse({ items: [job], limit: 100 }) as unknown as Response;
    };

    await expect(loadExecutionJobs("/api/v1", fetcher)).resolves.toEqual([job]);
    expect(requested).toBe("/api/v1/jobs?limit=100");
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

  it("fails closed on API errors and malformed metrics", async () => {
    const unavailable = async () => new FakeResponse({ error: "PLATFORM_STORAGE_UNAVAILABLE" }, false, 503) as unknown as Response;
    await expect(loadExecutionJobs("/api/v1", unavailable)).rejects.toMatchObject<Partial<ControlPlaneApiError>>({
      code: "PLATFORM_STORAGE_UNAVAILABLE",
      status: 503,
      retriable: true,
    });

    const malformed = async () => new FakeResponse({ items: [] }) as unknown as Response;
    await expect(loadExecutionMetrics("/api/v1", malformed)).rejects.toMatchObject({ code: "INVALID_API_RESPONSE" });
  });
});

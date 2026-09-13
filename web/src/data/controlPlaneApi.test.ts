import { describe, expect, it } from "vitest";
import { ControlPlaneApiError, loadControlPlaneCorpus } from "./controlPlaneApi";

class FakeResponse {
  ok = true;
  status = 200;
  constructor(private readonly value: unknown) {}
  async json(): Promise<unknown> {
    return this.value;
  }
}

describe("formal Control Plane API datasource", () => {
  it("fails closed when the API is unavailable instead of using static fixtures", async () => {
    const fetcher = async () => {
      throw new Error("offline");
    };
    await expect(loadControlPlaneCorpus("http://control-plane/api/v1", fetcher)).rejects.toMatchObject({
      code: "API_UNAVAILABLE",
      retriable: true,
    });
  });

  it("requires artifact resolution for the complete snapshot", async () => {
    const fetcher = async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/metadata?entity_type=RUN")) {
        return new FakeResponse({
          items: [{
            canonical_metadata: { entity_type: "RUN", entity_id: "run-1" },
            artifact_resolution: { resolved: false, error_code: "INVALID_EVIDENCE_ARTIFACT_MISSING" },
          }],
        }) as unknown as Response;
      }
      return new FakeResponse({ items: [] }) as unknown as Response;
    };
    await expect(loadControlPlaneCorpus("http://control-plane/api/v1", fetcher)).rejects.toMatchObject({
      code: "INVALID_EVIDENCE_ARTIFACT_MISSING",
    });
  });

  it("does not classify malformed successful API JSON as a fixture fallback", async () => {
    const fetcher = async () => new FakeResponse({ items: "not-a-list" }) as unknown as Response;
    await expect(loadControlPlaneCorpus("http://control-plane/api/v1", fetcher)).rejects.toBeInstanceOf(ControlPlaneApiError);
  });
});

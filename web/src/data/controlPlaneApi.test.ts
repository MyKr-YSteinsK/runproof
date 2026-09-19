import { describe, expect, it } from "vitest";
import {
  ControlPlaneApiError,
  loadControlPlaneCanonicalDetail,
  loadControlPlaneCorpus,
  loadControlPlaneMetadataPage,
} from "./controlPlaneApi";

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

  it("loads one bounded metadata page without resolving artifact bodies", async () => {
    const requests: string[] = [];
    const fetcher = async (input: RequestInfo | URL) => {
      requests.push(String(input));
      return new FakeResponse({
        items: [{ canonical_metadata: { entity_type: "RUN", entity_id: "run-1" }, artifact_resolution: { resolved: false, availability: "REGISTERED_REFERENCE" } }],
        limit: 50,
        has_more: true,
        next_cursor: "opaque-cursor",
        cursor_contract: "rpf-metadata-cursor-v1",
        ordering: "created_at,entity_id:asc",
        entity_type: "RUN",
        artifact_resolution: "REGISTERED_REFERENCE",
      }) as unknown as Response;
    };
    const page = await loadControlPlaneMetadataPage("RUN", { limit: 50, cursor: "previous" }, "http://control-plane/api/v1", fetcher);
    expect(page.items).toHaveLength(1);
    expect(requests).toEqual(["http://control-plane/api/v1/metadata?entity_type=RUN&limit=50&cursor=previous"]);
  });

  it("reads metadata first and verifies only the selected detail artifact", async () => {
    const requests: string[] = [];
    const fetcher = async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
      if (url.includes("/metadata/RUN/run-1?verify=false")) {
        return new FakeResponse({
          canonical_metadata: { entity_type: "RUN", entity_id: "run-1", key_refs: [] },
          artifact_resolution: { resolved: false, availability: "REGISTERED_REFERENCE", artifact_url: "/artifacts/RUN/run-1" },
        }) as unknown as Response;
      }
      return new FakeResponse({
        artifact_ref: { resolved: true, schema_version: "rpf-run-evidence-v2", content_sha256: "a".repeat(64) },
        artifact: { run: { run_id: "run-1" } },
      }) as unknown as Response;
    };
    const detail = await loadControlPlaneCanonicalDetail("RUN", "run-1", "http://control-plane/api/v1", fetcher);
    expect(detail.artifact_ref.resolved).toBe(true);
    expect(requests).toEqual([
      "http://control-plane/api/v1/metadata/RUN/run-1?verify=false",
      "http://control-plane/api/v1/artifacts/RUN/run-1",
    ]);
  });
});

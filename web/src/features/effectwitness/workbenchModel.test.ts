import { describe, expect, it, vi } from "vitest";
import { embeddedRecordedPayload, validateRecordedPayload } from "./recordedEvidence";
import { domainFromSearch, evidenceForDomain, loadWorkbenchEvidence, workbenchHref } from "./workbenchModel";

describe("workbench source boundary", () => {
  it("validates pinned evidence and keeps operations separate from the order session", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    const evidence = await loadWorkbenchEvidence();
    const order = evidenceForDomain(evidence, "order");
    const ops = evidenceForDomain(evidence, "ops");
    expect(order.trials).toHaveLength(2);
    expect(order.events.length).toBeGreaterThan(0);
    expect(ops.trials).toEqual([]);
    expect(ops.events).toEqual([]);
    expect(ops.witness.schema_version).toBe("rpf-effect-witness-v2");
    expect(fetch).not.toHaveBeenCalled();
    fetch.mockRestore();
  });
  it("rejects changed source bytes and missing source", async () => {
    await expect(validateRecordedPayload({ ...embeddedRecordedPayload, reportText: embeddedRecordedPayload.reportText + " " })).rejects.toThrow("RPF46_REPORT_SHA256_MISMATCH");
    await expect(validateRecordedPayload({ ...embeddedRecordedPayload, manifestText: "" })).rejects.toThrow("MANIFEST_SHA256_MISMATCH");
  });
  it("keeps the existing selection parameters when changing domain", () => {
    expect(domainFromSearch("?domain=ops&event=e14")).toBe("ops");
    expect(workbenchHref("?domain=ops&event=e14", "order")).toBe("/effectwitness/workbench?domain=order&event=e14");
  });
});

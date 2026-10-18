import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nProvider } from "../../i18n";
import { RecordedPage } from "./RecordedPage";
import { embeddedRecordedPayload, validateRecordedPayload } from "./recordedEvidence";

describe("Recorded EffectWitness evidence view", () => {
  it("validates pinned source bytes and business claims without making a request", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    const evidence = await validateRecordedPayload();
    expect(evidence.report.session_id).toBe("exploration-a3cdf741b7e34f4f97c07228fdf9b679");
    expect(evidence.report.selections.map((item) => item.candidate_id)).toEqual(["normal", "response-lost"]);
    expect(evidence.report.trials[1].fault.activation).toBe("TRIGGERED");
    expect(evidence.orderWitness.schema_version).toBe("rpf-effect-witness-v1");
    expect(evidence.opsWitness.schema_version).toBe("rpf-effect-witness-v2");
    expect(fetch).not.toHaveBeenCalled();
    fetch.mockRestore();
  });

  it("fails closed when a committed source byte changes", async () => {
    await expect(validateRecordedPayload({ ...embeddedRecordedPayload, reportText: embeddedRecordedPayload.reportText + " " }))
      .rejects.toThrow("RPF46_REPORT_SHA256_MISMATCH");
    await expect(validateRecordedPayload({ ...embeddedRecordedPayload, opsWitnessText: embeddedRecordedPayload.opsWitnessText.replace("rpf-effect-witness-v2", "rpf-effect-witness-v1") }))
      .rejects.toThrow("RPF44_SAMPLE_SHA256_MISMATCH");
  });

  it("renders a bilingual recorded path with no experiment start action", () => {
    const html = renderToStaticMarkup(<I18nProvider><RecordedPage path="/effectwitness/recorded" search="" /></I18nProvider>);
    expect(html).toContain("RECORDED");
    expect(html).toContain("/effectwitness");
    expect(html).not.toContain("startLive(");
    expect(html).not.toContain("Start one paid PGE session");
  });
});

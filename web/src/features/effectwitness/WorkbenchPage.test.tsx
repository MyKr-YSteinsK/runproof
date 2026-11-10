import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nProvider } from "../../i18n";
import { WorkbenchEvidence, WorkbenchPage } from "./WorkbenchPage";
import { embeddedRecordedPayload, validateRecordedPayload } from "./recordedEvidence";

describe("read-only workbench", () => {
  it("keeps the three-step guide and disables live entry links in a recorded bundle", () => {
    vi.stubEnv("VITE_RPF_RECORDED_DELIVERY", "1");
    try {
      const html = renderToStaticMarkup(<I18nProvider><WorkbenchPage search="?domain=ops" /></I18nProvider>);
      for (const anchor of ["#wb-scenario", "#wb-trace", "#wb-witness"]) expect(html).toContain(`href="${anchor}"`);
      expect(html).toContain("UNAVAILABLE");
      expect(html).not.toContain('href="/effectwitness/explorations"');
      expect(html).not.toContain('href="/effectwitness/cross-domain"');
      expect(html).not.toContain('href="/effectwitness/live-local"');
      expect(html).toContain("RECORDED · READ ONLY");
      expect(html).toContain("SEPARATE SAMPLE");
    } finally { vi.unstubAllEnvs(); }
  });
  it("offers all existing destinations without issuing a request during rendering", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    const html = renderToStaticMarkup(<I18nProvider><WorkbenchPage search="?domain=ops" /></I18nProvider>);
    for (const path of ["/effectwitness/recorded", "/effectwitness/explorations", "/effectwitness/cross-domain", "/effectwitness"]) expect(html).toContain(`href="${path}"`);
    expect(html).toContain("READ ONLY");
    expect(html).toContain('href="/effectwitness/live-local"');
    expect(html).not.toContain("<form");
    expect(fetch).not.toHaveBeenCalled();
    fetch.mockRestore();
  });
  it("shows verified Order evidence and its event link separately from the Ops sample", async () => {
    const evidence = await validateRecordedPayload();
    const event = evidence.report.feedback_link_events[0];
    const order = renderToStaticMarkup(<I18nProvider><WorkbenchEvidence
      state={{ status: "VERIFIED", evidence }} search={`?domain=order&event=${encodeURIComponent(event.event_id)}`} /></I18nProvider>);
    expect(order).toContain("RECORDED_RPF46_SUMMARY");
    expect(order).toContain("aria-current=\"step\"");
    expect(order).toContain(encodeURIComponent(event.event_id));
    expect(order).toContain("CONTRACT_SATISFIED_IN_RUN");
    expect(order).toContain(evidence.report.selections[1].input_feedback_hash);
    const ops = renderToStaticMarkup(<I18nProvider><WorkbenchEvidence
      state={{ status: "VERIFIED", evidence }} search="?domain=ops" /></I18nProvider>);
    expect(ops).toContain("HISTORICAL_WITNESS_SAMPLE");
    expect(ops).not.toContain(evidence.report.session_id);
    expect(ops).not.toContain("wb-trial");
  });
  it("renders no evidence claims when the embedded source fails validation", async () => {
    await expect(validateRecordedPayload({ ...embeddedRecordedPayload, reportText: "{}" })).rejects.toThrow();
    const html = renderToStaticMarkup(<I18nProvider><WorkbenchEvidence state={{ status: "UNAVAILABLE" }} search="?domain=order" /></I18nProvider>);
    expect(html).toContain('role="alert"');
    expect(html).toContain("UNAVAILABLE");
    expect(html).not.toContain("CONTRACT_SATISFIED");
    expect(html).not.toContain("RECORDED_RPF46_SUMMARY");
    expect(html).not.toContain("from=workbench");
  });
});

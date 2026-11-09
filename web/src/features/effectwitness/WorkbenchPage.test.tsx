import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nProvider } from "../../i18n";
import { WorkbenchPage } from "./WorkbenchPage";

describe("read-only workbench", () => {
  it("keeps the three-step guide and disables live entry links in a recorded bundle", () => {
    vi.stubEnv("VITE_RPF_RECORDED_DELIVERY", "1");
    try {
      const html = renderToStaticMarkup(<I18nProvider><WorkbenchPage search="?domain=ops" /></I18nProvider>);
      for (const anchor of ["#wb-scenario", "#wb-trace", "#wb-witness"]) expect(html).toContain(`href="${anchor}"`);
      expect(html).toContain("UNAVAILABLE");
      expect(html).not.toContain('href="/effectwitness/explorations"');
      expect(html).not.toContain('href="/effectwitness/cross-domain"');
    } finally { vi.unstubAllEnvs(); }
  });
  it("offers all existing destinations without issuing a request during rendering", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    const html = renderToStaticMarkup(<I18nProvider><WorkbenchPage search="?domain=ops" /></I18nProvider>);
    for (const path of ["/effectwitness/recorded", "/effectwitness/explorations", "/effectwitness/cross-domain", "/effectwitness"]) expect(html).toContain(`href="${path}"`);
    expect(html).toContain("READ ONLY");
    expect(html).not.toContain("<form");
    expect(fetch).not.toHaveBeenCalled();
    fetch.mockRestore();
  });
});

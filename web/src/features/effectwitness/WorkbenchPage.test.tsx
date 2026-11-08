import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nProvider } from "../../i18n";
import { WorkbenchPage } from "./WorkbenchPage";

describe("read-only workbench", () => {
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

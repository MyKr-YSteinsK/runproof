import { expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nProvider } from "../../i18n";
import { ProductLocalPage } from "./ProductLocalPage";

it("requires explicit local admission and renders without starting any request", () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  try {
    const markup = renderToStaticMarkup(<I18nProvider><ProductLocalPage search="?event=4" /></I18nProvider>);
    expect(markup).toContain('type="checkbox"');
    expect(markup).toContain('disabled=""');
    expect(markup).toContain("Provider");
    expect(markup).not.toContain("Issuer Signed");
    expect(fetch).not.toHaveBeenCalled();
  } finally { fetch.mockRestore(); }
});

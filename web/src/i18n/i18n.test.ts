import { describe, expect, it } from "vitest";
import { LOCALE_STORAGE_KEY, createTranslator, formatLocaleDate, formatLocaleNumber, formatLocalePercent, persistLocale, readPersistedLocale, resolveLocale } from "./index";
import { KEEP_ENGLISH_TERMS } from "./terminology";
import { messages } from "./messages";
import { pseudoLocalize } from "./pseudo";
import { localizeLegacyText } from "./legacyCopy";

describe("locale contract", () => {
  it("resolves browser language and falls back to en-US", () => {
    expect(resolveLocale("zh-CN")).toBe("zh-CN");
    expect(resolveLocale("zh-TW")).toBe("zh-CN");
    expect(resolveLocale("zh-HK")).toBe("zh-CN");
    expect(resolveLocale("en-US")).toBe("en-US");
    expect(resolveLocale("fr-FR")).toBe("en-US");
    expect(resolveLocale(null)).toBe("en-US");
  });

  it("persists only supported user choices", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };
    expect(readPersistedLocale(storage)).toBeNull();
    expect(persistLocale("zh-CN", storage)).toBe(true);
    expect(values.get(LOCALE_STORAGE_KEY)).toBe("zh-CN");
    expect(readPersistedLocale(storage)).toBe("zh-CN");
    values.set(LOCALE_STORAGE_KEY, "fr-FR");
    expect(readPersistedLocale(storage)).toBeNull();
  });

  it("keeps dictionaries symmetric and interpolation complete", () => {
    expect(Object.keys(messages["en-US"]).sort()).toEqual(Object.keys(messages["zh-CN"]).sort());
    const translated = createTranslator("zh-CN")("statistical.trialRunsAvailable", { resolved: 2, total: 4 });
    expect(translated).toContain("2 / 4");
    expect(translated).not.toContain("⟦");
  });

  it("formats display values by locale without changing the source value", () => {
    expect(formatLocaleNumber("en-US", 1234567)).toBe("1,234,567");
    expect(formatLocaleNumber("zh-CN", 1234567)).toContain("1,234,567");
    expect(formatLocalePercent("en-US", 0.95, 1)).toBe("95.0%");
    expect(formatLocalePercent("zh-CN", 0.95, 1)).toContain("95.0%");
    expect(formatLocaleDate("en-US", "2026-01-02T03:04:05Z")).toContain("2026");
    expect(formatLocaleDate("zh-CN", "2026-01-02T03:04:05Z")).toContain("2026");
  });

  it("declares the technical vocabulary that remains canonical", () => {
    expect(KEEP_ENGLISH_TERMS).toContain("UNKNOWN_OUTCOME");
    expect(KEEP_ENGLISH_TERMS).toContain("Release Decision");
    expect(KEEP_ENGLISH_TERMS).not.toContain("总览");
  });

  it("provides a QA-only text expansion harness", () => {
    const expanded = pseudoLocalize("Inspect Evidence UNKNOWN_OUTCOME now");
    expect(expanded.length).toBeGreaterThanOrEqual("Inspect Evidence UNKNOWN_OUTCOME now".length * 1.3);
    expect(expanded).toContain("UNKNOWN_OUTCOME");
    expect(pseudoLocalize("Control Plane Agent Release Gate")).toContain("Control Plane");
    expect(pseudoLocalize("Control Plane Agent Release Gate")).toContain("Release Gate");
    expect(expanded).toContain("[");
  });

  it("keeps legacy read-only copy in the same locale contract", () => {
    expect(localizeLegacyText("zh-CN", "Investigate a run from the evidence trail.")).toContain("调查");
    expect(localizeLegacyText("en-US", "从证据轨迹调查一个 Run。")).toBe("Investigate a run from the evidence trail.");
    expect(localizeLegacyText("zh-CN", "Source: reviewed fixture artifact")).toBe("来源： reviewed fixture artifact");
    expect(localizeLegacyText("zh-CN", "Reviewed Run Evidence")).toBe("已审查 Run Evidence");
    expect(localizeLegacyText("en-US", "来源： reviewed fixture artifact")).toBe("Source: reviewed fixture artifact");
    expect(localizeLegacyText("zh-CN", "run-abc123")).toBe("run-abc123");
  });
});

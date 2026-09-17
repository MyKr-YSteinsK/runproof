import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { messages, type MessageKey } from "./messages";
import { statusAccessibleLabel, statusDescription, terminologyLabel, type TerminologyKey } from "./terminology";
import { pseudoLocalize } from "./pseudo";
import type { Locale } from "./types";

export type { Locale } from "./types";
export { KEEP_ENGLISH_TERMS, statusDescription, statusAccessibleLabel } from "./terminology";
export { messages } from "./messages";

export const LOCALE_STORAGE_KEY = "runproof.locale";
export const SUPPORTED_LOCALES: Locale[] = ["en-US", "zh-CN"];

type InterpolationValue = string | number;
export type Translate = (key: MessageKey, values?: Record<string, InterpolationValue>) => string;

export function resolveLocale(browserLanguage?: string | null): Locale {
  return typeof browserLanguage === "string" && browserLanguage.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

export function readPersistedLocale(storage?: Pick<Storage, "getItem"> | null): Locale | null {
  try {
    const value = storage?.getItem(LOCALE_STORAGE_KEY);
    return value === "en-US" || value === "zh-CN" ? value : null;
  } catch {
    return null;
  }
}

export function persistLocale(locale: Locale, storage?: Pick<Storage, "setItem"> | null): boolean {
  try {
    storage?.setItem(LOCALE_STORAGE_KEY, locale);
    return true;
  } catch {
    return false;
  }
}

function browserStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function pseudoModeEnabled(): boolean {
  try {
    return typeof window !== "undefined" && new URLSearchParams(window.location.search).get("pseudo") === "1";
  } catch {
    return false;
  }
}

export function createTranslator(locale: Locale): Translate {
  return (key, values = {}) => {
    const template = messages[locale][key] || messages["en-US"][key];
    if (!template) {
      if (import.meta.env?.DEV) console.error(`Missing translation key: ${String(key)}`);
      return `⟦${String(key)}⟧`;
    }
    return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(values[name] ?? `⟦${name}⟧`));
  };
}

export function formatLocaleDate(locale: Locale, value: unknown): string {
  if (typeof value !== "string") return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date);
}

export function formatLocaleNumber(locale: Locale, value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? new Intl.NumberFormat(locale).format(value) : "—";
}

export function formatLocalePercent(locale: Locale, value: unknown, digits = 1): string {
  return typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat(locale, { style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)
    : "—";
}

export function formatLocaleDuration(locale: Locale, value: unknown): string {
  const milliseconds = typeof value === "number" && Number.isFinite(value) ? value : 0;
  const number = milliseconds < 1000 ? milliseconds : milliseconds / 1000;
  const formatted = new Intl.NumberFormat(locale, { maximumFractionDigits: milliseconds < 1000 ? 0 : 1 }).format(number);
  return `${formatted} ${milliseconds < 1000 ? "ms" : "s"}`;
}

type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Translate;
  term: (key: TerminologyKey) => string;
  statusLabel: (status: string) => string;
  statusDescription: (status: string) => string | undefined;
  formatDate: (value: unknown) => string;
  formatNumber: (value: unknown) => string;
  formatPercent: (value: unknown, digits?: number) => string;
  formatDuration: (value: unknown) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    const persisted = readPersistedLocale(browserStorage());
    return persisted || resolveLocale(typeof navigator === "undefined" ? null : navigator.language);
  });
  const pseudoMode = pseudoModeEnabled();
  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale);
    persistLocale(nextLocale, browserStorage());
  }, []);
  const rawTranslate = useMemo(() => createTranslator(locale), [locale]);
  const t = useMemo(() => (key: MessageKey, values?: Record<string, InterpolationValue>) => {
    const value = rawTranslate(key, values);
    return pseudoMode ? pseudoLocalize(value) : value;
  }, [pseudoMode, rawTranslate]);
  const value = useMemo<I18nContextValue>(() => ({
    locale,
    setLocale,
    t,
    term: (key) => terminologyLabel(locale, key),
    statusLabel: (status) => statusAccessibleLabel(locale, status),
    statusDescription: (status) => statusDescription(locale, status),
    formatDate: (input) => formatLocaleDate(locale, input),
    formatNumber: (input) => formatLocaleNumber(locale, input),
    formatPercent: (input, digits) => formatLocalePercent(locale, input, digits),
    formatDuration: (input) => formatLocaleDuration(locale, input),
  }), [locale, setLocale, t]);
  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = locale;
      document.title = t("app.title");
    }
  }, [locale, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used within I18nProvider");
  return value;
}

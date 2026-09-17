import { useI18n } from "../i18n";

export function LocaleSwitcher() {
  const { locale, setLocale, t } = useI18n();
  return <div className="locale-switcher" role="group" aria-label={t("locale.label")}><button type="button" className={locale === "zh-CN" ? "active" : ""} aria-pressed={locale === "zh-CN"} aria-label={t("locale.switchToChinese")} onClick={() => setLocale("zh-CN")}>{t("locale.chinese")}</button><span aria-hidden="true">/</span><button type="button" className={locale === "en-US" ? "active" : ""} aria-pressed={locale === "en-US"} aria-label={t("locale.switchToEnglish")} onClick={() => setLocale("en-US")}>{t("locale.english")}</button></div>;
}

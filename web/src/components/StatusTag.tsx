export type StatusTone = "success" | "fault" | "error" | "neutral" | "review";

import { useI18n } from "../i18n";

export const StatusTag = ({ status, tone = "neutral" }: { status: string; tone?: StatusTone }) => {
  const { locale, statusDescription } = useI18n();
  const description = statusDescription(status);
  return (
    <span className={`status-tag ${tone}`} aria-label={`${status}${description ? ` · ${description}` : ""}`}><i aria-hidden="true" /><span className="status-tag-raw">{status}</span>{locale === "zh-CN" && description && <small className="status-tag-description">{description}</small>}</span>
  );
};

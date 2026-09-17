import type { ControlPlaneApiError } from "../data/controlPlaneApi";
import { useI18n } from "../i18n";
import { LocaleSwitcher } from "./LocaleSwitcher";

export const DataSourceState = ({ status, error }: { status: "loading" | "error"; error?: ControlPlaneApiError }) => {
  const { t } = useI18n();
  const unavailable = status === "error";
  return (
    <main className="data-source-state" aria-live="polite">
      <div className={`data-source-state-card${unavailable ? " error" : ""}`}>
        <LocaleSwitcher />
        <span className="eyebrow">{t("state.apiEyebrow")}</span>
        <h1>{unavailable ? t("state.unavailableTitle") : t("state.loadingTitle")}</h1>
        <p>{unavailable ? t("state.unavailableDescription") : t("state.loadingDescription")}</p>
        {unavailable && <code>{error?.code || "API_UNAVAILABLE"}{error?.status ? " · HTTP " + error.status : ""}</code>}
      </div>
    </main>
  );
};

export const NotFoundState = ({ path }: { path: string }) => {
  const { t } = useI18n();
  return (
    <main className="data-source-state" aria-live="polite">
      <div className="data-source-state-card error">
        <LocaleSwitcher />
        <span className="eyebrow">{t("state.notFoundEyebrow")}</span>
        <h1>{t("state.notFoundTitle")}</h1>
        <p>{t("state.notFoundDescription")}</p>
        <code>{path}</code>
      </div>
    </main>
  );
};

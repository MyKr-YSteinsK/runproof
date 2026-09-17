import type { ControlPlaneApiError } from "../data/controlPlaneApi";

export const DataSourceState = ({ status, error }: { status: "loading" | "error"; error?: ControlPlaneApiError }) => {
  const unavailable = status === "error";
  return (
    <main className="data-source-state" aria-live="polite">
      <div className={`data-source-state-card${unavailable ? " error" : ""}`}>
        <span className="eyebrow">CONTROL PLANE API · RPF-11</span>
        <h1>{unavailable ? "Canonical data is unavailable." : "Loading canonical data…"}</h1>
        <p>{unavailable ? "The Web surface did not receive a complete API-backed snapshot. Static fixtures are not used as a silent fallback." : "Resolving metadata and verified immutable artifacts before rendering the investigation surface."}</p>
        {unavailable && <code>{error?.code || "API_UNAVAILABLE"}{error?.status ? " · HTTP " + error.status : ""}</code>}
      </div>
    </main>
  );
};

export const NotFoundState = ({ path }: { path: string }) => (
  <main className="data-source-state" aria-live="polite">
    <div className="data-source-state-card error">
      <span className="eyebrow">CANONICAL SNAPSHOT · READY</span>
      <h1>Entity not found.</h1>
      <p>The current canonical snapshot is loaded, but no entity matches this deep link.</p>
      <code>{path}</code>
    </div>
  </main>
);

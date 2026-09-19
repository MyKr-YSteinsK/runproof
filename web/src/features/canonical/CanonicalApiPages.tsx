import { AppShell } from "../../components/AppShell";
import { DataSourceState, NotFoundState } from "../../components/DataSourceState";
import { LocaleSwitcher } from "../../components/LocaleSwitcher";
import { StatusTag } from "../../components/StatusTag";
import { navigate } from "../../app/navigation";
import type { ControlPlaneApiError, ControlPlaneMetadataDto, ControlPlaneMetadataViewDto } from "../../data/controlPlaneApi";
import type { ApiAgentDetailRouteData, ApiDetailRouteData, ApiIndexDefinition, ApiIndexRouteData } from "../../data/routeScopedControlPlane";
import { API_INDEX_DEFINITIONS } from "../../data/routeScopedControlPlane";
import { useI18n } from "../../i18n";

const objectValue = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const displayValue = (value: unknown): string => value === null || value === undefined || value === "" ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value);
const shortId = (value: unknown, length = 34): string => {
  const text = displayValue(value);
  return text.length > length ? `${text.slice(0, length)}…` : text;
};
const humanize = (value: string): string => value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const statusTone = (status: string): "success" | "fault" | "error" | "neutral" | "review" => {
  if (["PASS", "COMPLETED", "ELIGIBLE", "IMPROVED", "VALIDATED"].includes(status)) return "success";
  if (["FAIL", "BLOCKED", "REGRESSED", "ERROR"].includes(status)) return "fault";
  if (["REVIEW_REQUIRED", "INCONCLUSIVE", "UNKNOWN"].includes(status)) return "review";
  return "neutral";
};

const flagForPath = (path: string): Record<string, boolean> => ({
  agent: path.startsWith("/agents"),
  failure: path.startsWith("/failures"),
  regression: path.startsWith("/regressions"),
  evaluation: path.startsWith("/evaluations"),
  comparison: path.startsWith("/comparisons") || path.startsWith("/statistical-comparisons"),
  statistical: path.startsWith("/statistical-"),
  release: path.startsWith("/release-decisions"),
  intelligence: path.startsWith("/failure-intelligence") || path.startsWith("/version-bisects"),
});

const detailPath = (definition: ApiIndexDefinition, entityId: string): string => {
  const route = definition.path === "/agents" ? "/runs" : definition.path;
  return `${route}/${encodeURIComponent(entityId)}`;
};

const definitionFor = (path: string): ApiIndexDefinition => API_INDEX_DEFINITIONS.find((item) => item.path === path) || API_INDEX_DEFINITIONS[0];

const summaryLine = (metadata: ControlPlaneMetadataDto): string => {
  const summary = objectValue(metadata.summary);
  const values = [
    summary.agent_domain,
    summary.agent_id || summary.agent_family,
    summary.scenario_id,
    summary.scenario_version,
    summary.category,
    summary.decision_subject,
  ].filter((value) => typeof value === "string" && value);
  return values.length ? values.map(String).join(" · ") : `${metadata.entity_type} · ${metadata.entity_schema_version}`;
};

const metadataStatus = (item: ControlPlaneMetadataViewDto): string => item.canonical_metadata.outcome || "UNKNOWN";

function Pagination({ page, path }: { page: ApiIndexRouteData["page"]; path: string }) {
  const { t } = useI18n();
  const current = new URLSearchParams(window.location.search).get("cursor");
  const historyValue = new URLSearchParams(window.location.search).get("history");
  const history = historyValue ? historyValue.split(",").filter(Boolean) : [];
  const buildUrl = (cursor: string | null, nextHistory: string[]): string => {
    const params = new URLSearchParams();
    if (cursor) params.set("cursor", cursor);
    if (nextHistory.length) params.set("history", nextHistory.join(","));
    const query = params.toString();
    return query ? `${path}?${query}` : path;
  };
  const previousCursor = history.length ? history[history.length - 1] : null;
  const nextHistory = current ? [...history, current] : history;
  return <div className="execution-pagination" aria-label={t("execution.paginationLabel")}>
    <button type="button" disabled={!current} onClick={() => navigate(buildUrl(previousCursor, history.slice(0, -1)))}>{t("canonical.previousPage")}</button>
    <span>{page.items.length} / {page.limit} · {page.has_more ? t("canonical.moreAvailable") : t("canonical.pageEnd")}</span>
    <button type="button" disabled={!page.has_more || !page.next_cursor} onClick={() => navigate(buildUrl(page.next_cursor, nextHistory))}>{t("canonical.nextPage")}</button>
  </div>;
}

export function CanonicalApiIndexPage({ data }: { data: ApiIndexRouteData }) {
  const { t } = useI18n();
  const definition = definitionFor(data.path);
  const title = t(definition.titleKey);
  const eyebrow = t(definition.eyebrowKey);
  const description = t(definition.descriptionKey);
  const flags = flagForPath(data.path);
  return <AppShell {...flags}>
    <div className="page-header index-header">
      <div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p className="lede">{description}</p></div>
      <div className="corpus-note"><span className="section-label">BOUNDED READ MODEL</span><strong>{data.page.items.length} records</strong><span>{t("canonical.pageSize", { count: data.page.limit })}</span></div>
    </div>
    <section className="corpus-boundary" aria-label="Canonical read boundary"><span className="boundary-mark">↧</span><p><strong>{t("canonical.registeredReference")}.</strong> {t("canonical.boundedDescription")}</p><span className="schema-chip">{data.page.cursor_contract}</span></section>
    <section className="canonical-api-list-section" aria-label={`${title} metadata page`}>
      <div className="section-heading"><div><span className="eyebrow">{t("canonical.currentPage")}</span><h2>{title}</h2></div><span className="section-count">{data.page.items.length.toString().padStart(2, "0")} / {data.page.limit}</span></div>
      {data.page.items.length === 0 ? <div className="panel"><p className="execution-muted">{t("canonical.emptyPage")}</p></div> : <div className="canonical-api-list">
        {data.page.items.map((item) => {
          const metadata = item.canonical_metadata;
          const href = detailPath(definition, metadata.entity_id);
          return <a className="canonical-api-row" key={`${metadata.entity_type}:${metadata.entity_id}`} href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>
            <div><StatusTag status={metadataStatus(item)} tone={statusTone(metadataStatus(item))} /><span className="signal-label">{item.artifact_resolution.availability || "REGISTERED_REFERENCE"}</span></div>
            <div><strong className="mono">{shortId(metadata.entity_id, 42)}</strong><span>{summaryLine(metadata)}</span></div>
            <div><strong>{metadata.artifact_kind}</strong><span>{metadata.entity_schema_version} · {metadata.created_at}</span></div>
            <div><strong>{t("canonical.detailVerifies")}</strong><span className="mono">{shortId(metadata.artifact_ref.content_sha256, 18)}</span></div>
            <span className="row-arrow" aria-hidden="true">→</span>
          </a>;
        })}
      </div>}
      <Pagination page={data.page} path={data.path} />
    </section>
    <footer className="page-footnote"><span>Source: Control Plane API · {data.page.ordering}</span><span>{t("canonical.noFullCorpus")}</span></footer>
  </AppShell>;
}

const refsFor = (metadata: ControlPlaneMetadataDto): Array<{ type: string; id: string; role: string }> => metadata.key_refs
  .filter((ref) => ref && typeof ref.entity_type === "string" && typeof ref.entity_id === "string")
  .map((ref) => ({ type: ref.entity_type, id: ref.entity_id, role: ref.role }));

const routeForRef = (type: string, id: string): string | null => {
  const routeByType: Record<string, string> = {
    RUN: "/runs", FAILURE_CASE: "/failures", REGRESSION: "/regressions", EVALUATION: "/evaluations",
    COMPARISON: "/comparisons", RELEASE_DECISION: "/release-decisions", FAILURE_INTELLIGENCE: "/failure-intelligence",
    FAILURE_CLUSTER: "/failure-intelligence/clusters", VERSION_BISECT: "/version-bisects",
    STATISTICAL_EVALUATION: "/statistical-evaluations", STATISTICAL_COMPARISON: "/statistical-comparisons",
  };
  const route = routeByType[type];
  return route ? `${route}/${encodeURIComponent(id)}` : null;
};

export function CanonicalApiDetailPage({ data }: { data: ApiDetailRouteData }) {
  const { t } = useI18n();
  const metadata = data.detail.metadata.canonical_metadata;
  const resolution = data.detail.artifact_ref;
  const flags = { ...flagForPath(data.path), detail: true };
  const summary = Object.entries(objectValue(metadata.summary));
  return <AppShell {...flags}>
    <div className="detail-breadcrumb"><a href={data.path.split("/").slice(0, -1).join("/") || "/runs"} onClick={(event) => { event.preventDefault(); navigate(data.path.split("/").slice(0, -1).join("/") || "/runs"); }}>{t("canonical.boundedIndex")}</a><span aria-hidden="true">/</span><span>{shortId(data.entityId, 42)}</span><span className="schema-chip">{t("canonical.verified")}</span></div>
    <div className="detail-header"><div><span className="eyebrow">{t("canonical.detailEyebrow", { type: metadata.entity_type })}</span><h1>{metadata.outcome} · {shortId(metadata.entity_id, 48)}</h1><p className="detail-subtitle">{t("canonical.detailSubtitle")}</p></div><div className="detail-header-status"><StatusTag status="VERIFIED" tone="success" /><span className="status-note">{t("canonical.oneArtifactRead")}</span></div></div>
    <section className="identity-strip" aria-label={t("canonical.detailIdentity")}><div><span className="field-label">{t("canonical.entityType")}</span><strong>{metadata.entity_type}</strong></div><div><span className="field-label">{t("canonical.entityId")}</span><strong className="mono">{metadata.entity_id}</strong></div><div><span className="field-label">{t("canonical.artifact")}</span><strong>{metadata.artifact_kind}</strong><small>{metadata.entity_schema_version}</small></div><div><span className="field-label">{t("canonical.registeredRef")}</span><strong>{metadata.artifact_ref.artifact_id}</strong><small>{shortId(metadata.artifact_ref.content_sha256, 20)}</small></div><div><span className="field-label">{t("canonical.verification")}</span><strong>{resolution.resolved ? t("canonical.available") : t("canonical.unavailable")}</strong><small>{resolution.resolved ? t("canonical.verifiedIdentity") : resolution.error_code || t("canonical.registeredReference")}</small></div></section>
    <section className="canonical-detail-grid"><div className="panel"><div className="panel-heading"><div><span className="eyebrow">{t("canonical.boundedSummary")}</span><h2>{t("canonical.canonicalMetadata")}</h2></div><span className="schema-chip">{t("canonical.registered")}</span></div><div className="fact-list"><div className="fact-row"><span>{t("canonical.outcome")}</span><strong>{metadata.outcome}</strong></div><div className="fact-row"><span>{t("canonical.created")}</span><strong>{metadata.created_at}</strong></div><div className="fact-row"><span>{t("canonical.agentVersion")}</span><strong>{displayValue(metadata.agent_version)}</strong></div><div className="fact-row"><span>{t("canonical.evaluation")}</span><strong className="mono">{displayValue(metadata.evaluation_id)}</strong></div>{summary.map(([key, value]) => <div className="fact-row" key={key}><span>{humanize(key)}</span><strong>{displayValue(value)}</strong></div>)}</div></div><div className="panel"><div className="panel-heading"><div><span className="eyebrow">{t("canonical.relatedReferences")}</span><h2>{t("canonical.resolveByIdentity")}</h2></div><span className="section-count">{metadata.key_refs.length}</span></div><div className="canonical-ref-list">{refsFor(metadata).map((ref) => { const href = routeForRef(ref.type, ref.id); return <div className="canonical-ref-row" key={`${ref.type}:${ref.id}`}><span><strong>{ref.role || t("canonical.reference")}</strong><small className="mono">{ref.type} · {ref.id}</small></span>{href ? <a className="action-link" href={href} onClick={(event) => { event.preventDefault(); navigate(href); }}>{t("canonical.openDetail")}</a> : <span className="execution-muted">{t("canonical.stableReference")}</span>}</div>; })}</div></div></section>
    <section className="panel canonical-artifact-panel"><div className="panel-heading"><div><span className="eyebrow">{t("canonical.verifiedArtifactBody")}</span><h2>{t("common.expertEscape")}</h2></div><span className="schema-chip">{resolution.schema_version}</span></div><p className="execution-muted">{t("canonical.currentEntityOnly")}</p><details open><summary>{t("canonical.verifiedArtifactJson")}</summary><pre>{JSON.stringify(data.detail.artifact, null, 2)}</pre></details></section>
    <footer className="detail-footer"><span>{metadata.entity_type}:{metadata.entity_id} · {resolution.content_sha256}</span><span>{t("canonical.verifiedImmutable")}</span></footer>
  </AppShell>;
}

export function CanonicalApiAgentDetailPage({ data }: { data: ApiAgentDetailRouteData }) {
  const { t } = useI18n();
  const metadata = data.detail.metadata.canonical_metadata;
  return <AppShell agent detail>
    <div className="detail-breadcrumb"><a href="/agents" onClick={(event) => { event.preventDefault(); navigate("/agents"); }}>{t("canonical.agentIndex")}</a><span aria-hidden="true">/</span><span>{shortId(data.agentId, 42)}</span><span className="schema-chip">{t("canonical.verified")}</span></div>
    <div className="detail-header"><div><span className="eyebrow">{t("canonical.agentEyebrow")}</span><h1>{data.agentId}</h1><p className="detail-subtitle">{t("canonical.agentSubtitle")}</p></div><div className="detail-header-status"><StatusTag status="VERIFIED" tone="success" /><span className="status-note">{t("canonical.oneArtifactRead")}</span></div></div>
    <section className="identity-strip" aria-label={t("canonical.agentIdentity")}><div><span className="field-label">{t("canonical.agentId")}</span><strong className="mono">{data.agentId}</strong></div><div><span className="field-label">{t("canonical.agentDomain")}</span><strong>{data.domain}</strong></div><div><span className="field-label">{t("canonical.agentRole")}</span><strong>{data.role}</strong></div><div><span className="field-label">{t("canonical.representativeRun")}</span><a className="action-link mono" href={`/runs/${encodeURIComponent(data.representativeRunId)}`} onClick={(event) => { event.preventDefault(); navigate(`/runs/${encodeURIComponent(data.representativeRunId)}`); }}>{shortId(data.representativeRunId, 28)}</a></div></section>
    <section className="panel canonical-artifact-panel"><div className="panel-heading"><div><span className="eyebrow">{t("canonical.agentEvidence")}</span><h2>{t("canonical.representativeEvidence")}</h2></div><span className="schema-chip">{metadata.entity_type}</span></div><p className="execution-muted">{t("canonical.agentEvidenceBoundary")}</p><div className="fact-list"><div className="fact-row"><span>{t("canonical.outcome")}</span><strong>{metadata.outcome}</strong></div><div className="fact-row"><span>{t("canonical.artifact")}</span><strong>{metadata.artifact_kind}</strong></div><div className="fact-row"><span>{t("canonical.verification")}</span><strong>{t("canonical.verified")}</strong></div></div><details><summary>{t("canonical.verifiedArtifactJson")}</summary><pre>{JSON.stringify(data.detail.artifact, null, 2)}</pre></details></section>
    <footer className="detail-footer"><span>{data.agentId} · {data.detail.artifact_ref.content_sha256}</span><span>{t("canonical.verifiedImmutable")}</span></footer>
  </AppShell>;
}

export function ApiRouteLoadingState({ status, error }: { status: "loading" | "error"; error?: ControlPlaneApiError }) {
  if (status === "error" && error?.code === "CANONICAL_METADATA_NOT_FOUND") return <NotFoundState path={window.location.pathname} />;
  return status === "error" ? <DataSourceState status="error" error={error} /> : <DataSourceState status="loading" />;
}

export function apiRoutePathForIndex(entityType: string): string {
  return API_INDEX_DEFINITIONS.find((definition) => definition.entityType === entityType)?.path || "/runs";
}

export function ApiLocaleOnlyState() {
  return <main className="data-source-state"><div className="data-source-state-card"><LocaleSwitcher /><p>Control Plane API route state is loading.</p></div></main>;
}

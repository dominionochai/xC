import type { ReactNode } from "react";

type ReportObject = Record<string, unknown>;

export type ReportViewProps = {
  report: unknown;
  apiBase?: string;
};

function isObject(value: unknown): value is ReportObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseReport(value: unknown): ReportObject | null {
  if (isObject(value)) return value;
  if (typeof value !== "string") return null;

  try {
    const parsed: unknown = JSON.parse(value);
    return isObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function readFirst(object: ReportObject, keys: string[]): unknown {
  for (const key of keys) {
    const value = object[key];
    if (value !== undefined && value !== null) return value;
  }
  return undefined;
}

function hasRenderableValue(value: unknown): boolean {
  if (value === undefined || value === null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.some(hasRenderableValue);
  if (isObject(value)) return Object.values(value).some(hasRenderableValue);
  return true;
}

function Value({ value }: { value: unknown }): ReactNode {
  if (value === undefined || value === null) return null;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <>{String(value)}</>;
  }
  if (Array.isArray(value)) {
    const items = value.filter(hasRenderableValue);
    if (items.length === 0) return null;
    return (
      <ul className="report-list">
        {items.map((item, index) => <li key={index}><Value value={item} /></li>)}
      </ul>
    );
  }
  if (isObject(value)) {
    const entries = Object.entries(value).filter(([, item]) => hasRenderableValue(item));
    if (entries.length === 0) return null;
    return (
      <dl className="report-details">
        {entries.map(([key, item]) => (
          <div className="report-detail" key={key}>
            <dt>{key.replace(/[_-]+/g, " ")}</dt>
            <dd><Value value={item} /></dd>
          </div>
        ))}
      </dl>
    );
  }
  return null;
}

function Section({ title, value }: { title: string; value: unknown }) {
  if (!hasRenderableValue(value)) return null;
  return (
    <section className="report-section" aria-label={title}>
      <h2>{title}</h2>
      <Value value={value} />
    </section>
  );
}

export default function ReportView({ report, apiBase }: ReportViewProps) {
  const data = parseReport(report);
  if (!data) return null;

  const title = readFirst(data, ["title", "report_title", "reportTitle"]);
  const brands = readFirst(data, ["brands", "brand_pair", "brandPair"]);
  const brandFallback = [
    readFirst(data, ["acquirer", "lead_brand", "leadBrand"]),
    readFirst(data, ["target", "partner", "target_brand", "targetBrand"]),
  ].filter(hasRenderableValue);
  const brandValue = hasRenderableValue(brands) ? brands : brandFallback;
  const status = readFirst(data, ["status", "report_status", "reportStatus"]);
  const affinity = readFirst(data, ["affinity_overlap", "affinityOverlap", "affinity"]);
  const tasteVectors = readFirst(data, ["unique_taste_vectors", "uniqueTasteVectors", "taste_vectors", "tasteVectors"]);
  const clashes = readFirst(data, ["clashes", "brand_clashes", "brandClashes"]);
  const regionalSplit = readFirst(data, ["regional_split", "regionalSplit", "regional_opportunity", "regionalOpportunity"]);
  const riskIndex = readFirst(data, [
    "pandering_authenticity_risk_index",
    "panderingAuthenticityRiskIndex",
    "pandering_and_authenticity_risk_index",
    "panderingAndAuthenticityRiskIndex",
  ]);
  const remediation = readFirst(data, ["remediation_bridge", "remediationBridge", "remediation"]);
  const tam = readFirst(data, ["tam", "total_addressable_market", "totalAddressableMarket"]);
  const rawId = readFirst(data, ["id", "report_id", "reportId"]);
  const id = typeof rawId === "string" || typeof rawId === "number" ? String(rawId) : "";
  const base = (apiBase ?? "").replace(/\/+$/, "");
  const reportUrl = id ? `${base}/api/v1/reports/${encodeURIComponent(id)}/export` : "";

  return (
    <article className="report-view" aria-labelledby="report-view-title">
      <header className="report-header">
        <div>
          <h1 id="report-view-title">{hasRenderableValue(title) ? <Value value={title} /> : "Report"}</h1>
          {hasRenderableValue(brandValue) && (
            <div className="report-brands" aria-label="Brands"><Value value={brandValue} /></div>
          )}
        </div>
        {hasRenderableValue(status) && <p className="report-status"><Value value={status} /></p>}
      </header>

      <Section title="Affinity overlap" value={affinity} />
      <Section title="Unique taste vectors" value={tasteVectors} />
      <Section title="Clashes" value={clashes} />
      <Section title="Regional split" value={regionalSplit} />
      <Section title="Pandering & Authenticity Risk Index" value={riskIndex} />
      <Section title="Remediation bridge" value={remediation} />
      <Section title="TAM" value={tam} />

      {id && (
        <nav className="report-exports" aria-label="Report exports">
          <a href={`${reportUrl}?format=markdown`}>Markdown</a>
          <a href={`${reportUrl}?format=pdf`}>PDF</a>
        </nav>
      )}
    </article>
  );
}

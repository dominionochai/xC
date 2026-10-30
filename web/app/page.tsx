"use client";

import { FormEvent, useState } from "react";
import { PRESETS } from "@/lib/presets";

function formatError(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "The report request failed.";
  }
}

export default function HomePage() {
  const [selectedPreset, setSelectedPreset] = useState(PRESETS[0].id);
  const [acquirer, setAcquirer] = useState(PRESETS[0].acquirer);
  const [target, setTarget] = useState(PRESETS[0].target);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdReport, setCreatedReport] = useState<{
    status: number;
    body: unknown;
  } | null>(null);

  const apiConfigured = Boolean(process.env.NEXT_PUBLIC_XC_API_URL);

  function selectPreset(presetId: string) {
    const preset = PRESETS.find((item) => item.id === presetId);
    if (!preset) return;
    setSelectedPreset(preset.id);
    setAcquirer(preset.acquirer);
    setTarget(preset.target);
  }

  async function createReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setCreatedReport(null);

    const apiUrl = process.env.NEXT_PUBLIC_XC_API_URL?.replace(/\/+$/, "");
    if (!apiUrl) {
      setError("Set NEXT_PUBLIC_XC_API_URL to connect to the xC API.");
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          acquirer: acquirer.trim(),
          target: target.trim(),
          preset: selectedPreset,
        }),
      });
      const responseText = await response.text();
      let responseBody: unknown = null;
      if (responseText) {
        try {
          responseBody = JSON.parse(responseText) as unknown;
        } catch {
          responseBody = responseText;
        }
      }

      if (!response.ok) {
        const detail = responseBody ?? `Request failed (${response.status}).`;
        throw new Error(formatError(detail));
      }

      setCreatedReport({ status: response.status, body: responseBody });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to create the report. Please try again.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <a className="wordmark" href="#home" aria-label="xC home">
          <span className="wordmark-symbol">x</span>C
        </a>
        <div className="topbar-meta">
          <span className="topbar-label">PARTNERSHIP INTELLIGENCE</span>
          <span className={`connection ${apiConfigured ? "is-ready" : "is-unset"}`}>
            <span className="connection-dot" aria-hidden="true" />
            API {apiConfigured ? "CONNECTED" : "NOT CONFIGURED"}
          </span>
        </div>
      </header>

      <section className="intro" id="home">
        <div className="eyebrow"><span>01</span> / NEW ANALYSIS</div>
        <h1>Make the case<br /><em>for what&apos;s next.</em></h1>
        <p className="intro-copy">
          Build a strategic partnership report around a brand pairing. Choose a
          starting point, refine the companies, and send it to xC.
        </p>
      </section>

      <div className="workspace">
        <section className="form-panel" aria-labelledby="form-title">
          <div className="section-heading">
            <div>
              <span className="section-kicker">REPORT SETUP</span>
              <h2 id="form-title">Define the opportunity</h2>
            </div>
            <span className="step-count">01 — 02</span>
          </div>

          <form onSubmit={createReport}>
            <label className="field-label" htmlFor="preset">START WITH A PRESET</label>
            <select
              id="preset"
              className="select-control"
              value={selectedPreset}
              onChange={(event) => selectPreset(event.target.value)}
            >
              {PRESETS.map((preset) => (
                <option key={preset.id} value={preset.id}>{preset.label}</option>
              ))}
            </select>

            <div className="field-grid">
              <div className="field-group">
                <label className="field-label" htmlFor="acquirer">ACQUIRER / LEAD BRAND</label>
                <input
                  id="acquirer"
                  name="acquirer"
                  autoComplete="organization"
                  required
                  value={acquirer}
                  onChange={(event) => setAcquirer(event.target.value)}
                  placeholder="Company name"
                />
              </div>
              <div className="field-group">
                <label className="field-label" htmlFor="target">TARGET / PARTNER</label>
                <input
                  id="target"
                  name="target"
                  autoComplete="organization"
                  required
                  value={target}
                  onChange={(event) => setTarget(event.target.value)}
                  placeholder="Company name"
                />
              </div>
            </div>

            <div className="form-footer">
              <p>Your selections are sent to the configured xC API.</p>
              <button className="submit-button" type="submit" disabled={isLoading}>
                {isLoading ? "Creating report…" : "Create report"}
                {!isLoading && <span aria-hidden="true">↗</span>}
              </button>
            </div>
          </form>
        </section>

        <aside className="note-panel">
          <span className="note-index">FIELD NOTE / 001</span>
          <div className="note-mark" aria-hidden="true">↗</div>
          <h3>A sharper<br />starting point.</h3>
          <p>Presets are editable. Shape the pairing to fit the opportunity you want to explore.</p>
          <div className="note-rule" />
          <span className="note-caption">BUILT FOR DECISION-MAKERS</span>
        </aside>
      </div>

      {error && (
        <section className="result-panel error-panel" role="alert" aria-live="assertive">
          <div className="result-heading">
            <div><span className="section-kicker">REQUEST ERROR</span><h2>Report not created</h2></div>
            <span className="result-status error-status">FAILED</span>
          </div>
          <pre>{error}</pre>
        </section>
      )}

      {createdReport && (
        <section className="result-panel" aria-live="polite">
          <div className="result-heading">
            <div><span className="section-kicker">API RESPONSE</span><h2>Report request complete</h2></div>
            <span className="result-status">HTTP {createdReport.status}</span>
          </div>
          <pre>{createdReport.body === null
            ? "The API returned an empty response body."
            : typeof createdReport.body === "string"
              ? createdReport.body
              : JSON.stringify(createdReport.body, null, 2)}</pre>
        </section>
      )}

      <footer className="page-footer">
        <span>XC / STRATEGIC PARTNERSHIPS</span>
        <span>PRIVATE WORKSPACE</span>
      </footer>
    </main>
  );
}

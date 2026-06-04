import { useState } from "react";

import { type CleanupResult, cleanupOldData } from "../api/client";
import type { LLMSettings } from "../types";

export function MaintenancePanel({ settings }: { settings: LLMSettings }) {
  const [days, setDays] = useState(90);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CleanupResult | null>(null);

  async function run() {
    if (!window.confirm(`Delete all news & analyses older than ${days} days? This cannot be undone.`)) {
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await cleanupOldData(days, settings));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card maintenance">
      <h3>🧹 Clean up old data</h3>
      <p className="muted">
        Permanently delete stored news and analyses older than the chosen age.
        The server enforces a safety floor, so recent data can't be wiped.
      </p>
      <div className="maintenance-row">
        <label>
          Older than (days)
          <input
            type="number"
            min={1}
            value={days}
            onChange={(e) => setDays(Math.max(1, Number(e.target.value) || 1))}
          />
        </label>
        <button className="run danger" disabled={busy} onClick={run}>
          {busy ? "Cleaning…" : "Clean up"}
        </button>
      </div>
      {error && <p className="error-msg">{error}</p>}
      {result && (
        <p className="muted">
          {result.note
            ? result.note
            : `Deleted ${result.deleted.news} news and ${result.deleted.analyses} analyses (older than ${result.retention_days} days).`}
        </p>
      )}
    </section>
  );
}

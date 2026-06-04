import { useState } from "react";

import { searchAndAnalyze, streamText } from "../api/client";
import type { AnalysisResponse, LLMSettings } from "../types";
import { ProgressTracker } from "./ProgressTracker";
import { ReportView } from "./ReportView";

type Mode = "text" | "search";

export function AnalysisForm({ settings }: { settings: LLMSettings }) {
  const [mode, setMode] = useState<Mode>("text");
  const [content, setContent] = useState("");
  const [title, setTitle] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Set<string>>(new Set());
  const [results, setResults] = useState<AnalysisResponse[]>([]);

  const canRun = mode === "text" ? content.trim() : query.trim();

  async function run() {
    setBusy(true);
    setError(null);
    setResults([]);
    setDone(new Set());
    try {
      if (mode === "text") {
        await streamText(
          content,
          title,
          settings,
          (node) => setDone((prev) => new Set(prev).add(node)),
          (data) => setResults([data]),
        );
      } else {
        const res = await searchAndAnalyze(query, 3, settings);
        setResults(res.results);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="analysis">
      <div className="tabs">
        <button className={mode === "text" ? "active" : ""} onClick={() => setMode("text")}>
          Text
        </button>
        <button className={mode === "search" ? "active" : ""} onClick={() => setMode("search")}>
          Search news
        </button>
      </div>

      {mode === "text" ? (
        <>
          <input
            className="title-input"
            placeholder="Title (optional)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            rows={8}
            placeholder="Paste financial news content to analyze..."
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
        </>
      ) : (
        <input
          className="title-input"
          placeholder="e.g. Tesla Q4 earnings"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      )}

      <button className="run" disabled={!canRun || busy} onClick={run}>
        {busy ? "Analyzing…" : "Analyze"}
      </button>

      {error && <p className="error-msg">{error}</p>}
      {busy && mode === "text" && <ProgressTracker done={done} />}

      {results.map((r, i) => (
        <ReportView key={r.news_id ?? i} result={r} />
      ))}
    </div>
  );
}

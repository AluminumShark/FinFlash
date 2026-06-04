import { useEffect, useState } from "react";

import { AnalysisForm } from "./components/AnalysisForm";
import { CompanyAnalysis } from "./components/CompanyAnalysis";
import { MaintenancePanel } from "./components/MaintenancePanel";
import { SettingsBar } from "./components/SettingsBar";
import type { LLMSettings } from "./types";

const STORAGE_KEY = "finflash.settings";

const DEFAULT_SETTINGS: LLMSettings = { provider: "", model: "", byoKey: "" };

function load(): LLMSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw) } : DEFAULT_SETTINGS;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function App({ embedded = false }: { embedded?: boolean }) {
  const [settings, setSettings] = useState<LLMSettings>(load);
  const [view, setView] = useState<"company" | "advanced">("company");

  useEffect(() => {
    // Persist everything except the BYO provider key (kept in-memory only).
    const { byoKey: _omit, ...persist } = settings;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(persist));
  }, [settings]);

  return (
    <div className={embedded ? "finflash embedded" : "finflash"}>
      <header className="app-header">
        <h1>⚡ FinFlash</h1>
        <p className="tagline">輸入一家公司，AI 多分析師告訴你值不值得投資</p>
      </header>
      <SettingsBar settings={settings} onChange={setSettings} />

      <div className="tabs">
        <button className={view === "company" ? "active" : ""} onClick={() => setView("company")}>
          公司投資分析
        </button>
        <button className={view === "advanced" ? "active" : ""} onClick={() => setView("advanced")}>
          進階（貼新聞／搜尋）
        </button>
      </div>

      {view === "company" ? (
        <CompanyAnalysis settings={settings} />
      ) : (
        <>
          <AnalysisForm settings={settings} />
          <MaintenancePanel settings={settings} />
        </>
      )}

      {!embedded && (
        <footer className="app-footer">
          <span className="muted">Powered by LangGraph · LiteLLM · pgvector</span>
        </footer>
      )}
    </div>
  );
}

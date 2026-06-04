import { useState } from "react";

import { analyzeCompany } from "../api/client";
import type { CompanyResponse, InvestmentVerdict, LLMSettings } from "../types";

const VERDICT_STYLE: Record<string, { label: string; color: string; icon: string }> = {
  buy: { label: "BUY", color: "#2f9e44", icon: "▲" },
  hold: { label: "HOLD", color: "#f08c00", icon: "■" },
  sell: { label: "SELL", color: "#e03131", icon: "▼" },
};

export function CompanyAnalysis({ settings }: { settings: LLMSettings }) {
  const [company, setCompany] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<CompanyResponse | null>(null);

  const canRun = company.trim() && !busy;

  async function run() {
    setBusy(true);
    setError(null);
    setData(null);
    try {
      setData(await analyzeCompany(company.trim(), settings, 5));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="company">
      <div className="company-search">
        <input
          className="company-input"
          placeholder="輸入公司名稱或股票代號，例如 Tesla / TSLA"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && canRun && run()}
        />
        <button className="run" disabled={!canRun} onClick={run}>
          {busy ? "分析中…" : "分析"}
        </button>
      </div>

      {busy && (
        <p className="hint">
          正在搜尋「{company}」的最新新聞並由多個 AI 分析師評估… 本地模型可能需要 1–3 分鐘。
        </p>
      )}
      {error && <p className="error-msg">{error}</p>}

      {data?.verdict && <VerdictCard verdict={data.verdict} data={data} />}

      {data && !data.verdict && (
        <p className="error-msg">無法產生投資結論（分析資料不足）。</p>
      )}

      {data && data.sources.length > 0 && (
        <section className="card">
          <h4>分析來源（{data.articles_analyzed}/{data.sources.length} 篇成功）</h4>
          <ul className="sources">
            {data.sources.map((s, i) => (
              <li key={i}>
                <span className="src-name">{s.source}</span>
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.title}
                  </a>
                ) : (
                  s.title
                )}
              </li>
            ))}
          </ul>
          <p className="disclaimer">
            ⚠️ 本結果為 AI 對公開新聞的研究分析，非個人化投資建議；投資請自行評估風險。
          </p>
        </section>
      )}
    </div>
  );
}

function VerdictCard({ verdict, data }: { verdict: InvestmentVerdict; data: CompanyResponse }) {
  const v = VERDICT_STYLE[verdict.recommendation] ?? VERDICT_STYLE.hold;
  const pct = Math.round(verdict.confidence * 100);
  return (
    <div className="verdict-card" style={{ borderColor: v.color }}>
      <div className="verdict-head">
        <div className="verdict-badge" style={{ background: v.color }}>
          <span className="verdict-icon">{v.icon}</span>
          <span className="verdict-label">{v.label}</span>
        </div>
        <div className="verdict-meta">
          <div className="verdict-company">{verdict.company || data.company}</div>
          <div className="confidence">
            信心 {pct}%
            <div className="confidence-bar">
              <div style={{ width: `${pct}%`, background: v.color }} />
            </div>
          </div>
          <div className="muted">展望：{verdict.time_horizon} · 模型 {data.model}</div>
        </div>
      </div>

      <p className="rationale">{verdict.rationale}</p>

      <div className="verdict-cols">
        <div>
          <h5>✅ 催化劑（利多）</h5>
          <ul>{verdict.key_catalysts.map((c) => <li key={c}>{c}</li>)}</ul>
        </div>
        <div>
          <h5>⚠️ 風險（利空）</h5>
          <ul>{verdict.key_risks.map((r) => <li key={r}>{r}</li>)}</ul>
        </div>
      </div>

      <div className="verdict-foot muted">
        情緒：{verdict.sentiment_summary || data.aggregate.dominant_sentiment} ·
        風險：{verdict.risk_summary || `${data.aggregate.average_risk_score ?? "?"}/100`}
      </div>
    </div>
  );
}

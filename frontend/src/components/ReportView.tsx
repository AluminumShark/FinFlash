import type { AnalysisResponse } from "../types";
import { RiskChart, SentimentChart } from "./Charts";

export function ReportView({ result }: { result: AnalysisResponse }) {
  const sentiment = result.analyses?.sentiment;
  const risk = result.analyses?.risk;
  const extraction = result.analyses?.extraction;
  const summary = result.summary;

  return (
    <div className="report">
      <div className="report-header">
        <span className={`badge status-${result.status}`}>{result.status}</span>
        {result.model && <span className="muted">model: {result.model}</span>}
        {result.usage && (
          <span className="muted">
            {result.usage.total_tokens.toLocaleString()} tokens · $
            {result.usage.cost_usd.toFixed(4)}
          </span>
        )}
      </div>

      <div className="charts">
        {sentiment && !sentiment.error && <SentimentChart sentiment={sentiment} />}
        {risk && !risk.error && <RiskChart risk={risk} />}
      </div>

      {summary && !summary.error && (
        <section className="card">
          <h3>Executive Summary</h3>
          <p>{summary.executive_summary.market_outlook}</p>
          <h4>Key findings</h4>
          <ul>
            {summary.executive_summary.key_findings.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          {summary.action_items.length > 0 && (
            <>
              <h4>Action items</h4>
              <ul>
                {summary.action_items.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </>
          )}
          {(summary.buy_signals.length > 0 || summary.sell_signals.length > 0) && (
            <div className="signals">
              <div>
                <strong>Buy</strong>
                <ul>{summary.buy_signals.map((s) => <li key={s}>{s}</li>)}</ul>
              </div>
              <div>
                <strong>Sell</strong>
                <ul>{summary.sell_signals.map((s) => <li key={s}>{s}</li>)}</ul>
              </div>
            </div>
          )}
        </section>
      )}

      {extraction && !extraction.error && (
        <section className="card">
          <h3>Entities — {extraction.event_type}</h3>
          <div className="chips">
            {extraction.entities.companies.map((c) => (
              <span className="chip" key={c.name}>
                {c.name}
                {c.ticker ? ` (${c.ticker})` : ""}
              </span>
            ))}
          </div>
        </section>
      )}

      {risk?.investment_implications && !risk.error && (
        <section className="card">
          <h3>Recommendation</h3>
          <p className="reco">
            {risk.investment_implications.recommendation.toUpperCase()} · confidence{" "}
            {risk.investment_implications.confidence_level}
          </p>
        </section>
      )}

      {result.errors.length > 0 && (
        <section className="card errors">
          <h4>Partial errors</h4>
          <ul>
            {result.errors.map((e, i) => (
              <li key={i}>
                {e.node}: {e.error}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

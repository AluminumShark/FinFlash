import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip,
} from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";

import type { RiskResult, SentimentResult } from "../types";

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend);

export function SentimentChart({ sentiment }: { sentiment: SentimentResult }) {
  const fg = sentiment.fear_greed_index;
  return (
    <div className="chart-card">
      <h4>Fear / Greed Index — {fg}</h4>
      <Doughnut
        data={{
          labels: ["Index", "Remaining"],
          datasets: [
            {
              data: [fg, 100 - fg],
              backgroundColor: [fgColor(fg), "#edf2f7"],
              borderWidth: 0,
            },
          ],
        }}
        options={{ cutout: "70%", plugins: { legend: { display: false } } }}
      />
      <p className="muted">
        {sentiment.overall_sentiment} · score {sentiment.sentiment_score.toFixed(2)} · confidence{" "}
        {(sentiment.confidence * 100).toFixed(0)}%
      </p>
    </div>
  );
}

export function RiskChart({ risk }: { risk: RiskResult }) {
  const score = risk.risk_summary.risk_score;
  return (
    <div className="chart-card">
      <h4>Risk Score — {score}/100 ({risk.risk_summary.overall_risk_level})</h4>
      <Bar
        data={{
          labels: ["Risk"],
          datasets: [
            {
              label: "Risk score",
              data: [score],
              backgroundColor: riskColor(score),
            },
          ],
        }}
        options={{
          indexAxis: "y",
          scales: { x: { min: 0, max: 100 } },
          plugins: { legend: { display: false } },
        }}
      />
      <ul className="muted">
        {risk.risk_summary.primary_risks.slice(0, 3).map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </div>
  );
}

function fgColor(v: number): string {
  if (v >= 60) return "#48bb78";
  if (v <= 40) return "#f56565";
  return "#ed8936";
}

function riskColor(v: number): string {
  if (v >= 70) return "#f56565";
  if (v >= 40) return "#ed8936";
  return "#48bb78";
}

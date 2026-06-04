// Mirrors the backend AnalysisResponse shape.

export interface SentimentResult {
  overall_sentiment: "positive" | "negative" | "neutral";
  sentiment_score: number;
  confidence: number;
  fear_greed_index: number;
  market_impact: { immediate: string; short_term: string; long_term: string };
  key_phrases: string[];
  investor_sentiment: string;
  recommendation: string;
  error?: string;
}

export interface RiskResult {
  risk_summary: {
    overall_risk_level: "low" | "medium" | "high" | "critical";
    primary_risks: string[];
    risk_score: number;
  };
  detailed_risks: Array<{ risk_type: string; specific_risk: string; impact: string }>;
  investment_implications: { recommendation: string; confidence_level: string };
  error?: string;
}

export interface ExtractionResult {
  entities: {
    companies: Array<{ name: string; ticker?: string | null }>;
    persons: Array<{ name: string }>;
    locations: string[];
  };
  event_type: string;
  sectors: string[];
  error?: string;
}

export interface SummaryResult {
  executive_summary: {
    key_findings: string[];
    market_outlook: string;
    immediate_actions: string[];
    confidence_level: string;
  };
  key_insights: string[];
  buy_signals: string[];
  sell_signals: string[];
  watch_list: string[];
  action_items: string[];
  error?: string;
}

export interface AnalysisResponse {
  news_id?: string;
  status: string;
  analyses?: {
    sentiment?: SentimentResult;
    extraction?: ExtractionResult;
    risk?: RiskResult;
  };
  summary?: SummaryResult;
  errors: Array<{ node: string; error: string }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
  };
  model?: string;
}

export interface InvestmentVerdict {
  company: string;
  recommendation: "buy" | "hold" | "sell";
  confidence: number;
  rationale: string;
  key_catalysts: string[];
  key_risks: string[];
  sentiment_summary: string;
  risk_summary: string;
  time_horizon: string;
}

export interface NewsSource {
  title?: string;
  source?: string;
  url?: string;
  published_date?: string;
}

export interface CompanyResponse {
  company: string;
  verdict: InvestmentVerdict | null;
  articles_analyzed: number;
  sources: NewsSource[];
  aggregate: {
    dominant_sentiment?: string;
    average_risk_score?: number;
    top_entities?: { name: string; mentions: number }[];
  };
  model?: string;
}

export interface LLMSettings {
  provider: string; // "" = server default
  model: string; // optional explicit model id
  byoKey: string; // the user's own model-provider API key (optional)
}

export const NODES = ["retrieve", "sentiment", "extraction", "risk", "summary", "persist"] as const;
export type NodeName = (typeof NODES)[number];

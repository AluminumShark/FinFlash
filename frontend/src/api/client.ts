import type { AnalysisResponse, CompanyResponse, LLMSettings } from "../types";

export function apiBase(): string {
  // Widget can override via a global; SPA uses same-origin (Vite proxy in dev).
  return (window as { FINFLASH_API_BASE?: string }).FINFLASH_API_BASE ?? "";
}

function headers(settings: LLMSettings): Record<string, string> {
  const h: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (settings.provider === "ollama") {
    // Local test mode: just send the model id (no provider tag, no key).
    h["X-LLM-Model"] = settings.model || "ollama_chat/gemma3:12b";
    return h;
  }
  if (settings.provider) h["X-LLM-Provider"] = settings.provider;
  if (settings.model) h["X-LLM-Model"] = settings.model;
  if (settings.byoKey) h["X-LLM-Key"] = settings.byoKey;
  return h;
}

export interface CleanupResult {
  retention_days: number;
  deleted: { news: number; analyses: number };
  note?: string;
}

export async function cleanupOldData(
  days: number,
  settings: LLMSettings,
): Promise<CleanupResult> {
  const res = await fetch(`${apiBase()}/api/admin/cleanup?days=${days}`, {
    method: "POST",
    headers: headers(settings),
  });
  if (!res.ok) throw new Error(await errorText(res));
  return res.json();
}

export async function analyzeCompany(
  company: string,
  settings: LLMSettings,
  numResults = 5,
): Promise<CompanyResponse> {
  const res = await fetch(`${apiBase()}/api/analysis/company`, {
    method: "POST",
    headers: headers(settings),
    body: JSON.stringify({ company, num_results: numResults }),
  });
  if (!res.ok) throw new Error(await errorText(res));
  return res.json();
}

export async function analyzeText(
  content: string,
  title: string,
  settings: LLMSettings,
  enableRag = true,
): Promise<AnalysisResponse> {
  const res = await fetch(`${apiBase()}/api/analysis/text`, {
    method: "POST",
    headers: headers(settings),
    body: JSON.stringify({ content, title, enable_rag: enableRag }),
  });
  if (!res.ok) throw new Error(await errorText(res));
  return res.json();
}

export interface SearchResponse {
  query: string;
  total_articles: number;
  analyzed_successfully: number;
  results: AnalysisResponse[];
  aggregate: Record<string, unknown>;
}

export async function searchAndAnalyze(
  query: string,
  numResults: number,
  settings: LLMSettings,
): Promise<SearchResponse> {
  const res = await fetch(`${apiBase()}/api/analysis/search`, {
    method: "POST",
    headers: headers(settings),
    body: JSON.stringify({ query, num_results: numResults }),
  });
  if (!res.ok) throw new Error(await errorText(res));
  return res.json();
}

/**
 * Stream a text analysis via SSE, invoking callbacks as each node completes.
 * Uses fetch + ReadableStream so we can send the X-API-Key header (EventSource cannot).
 */
export async function streamText(
  content: string,
  title: string,
  settings: LLMSettings,
  onProgress: (node: string) => void,
  onResult: (data: AnalysisResponse) => void,
  enableRag = true,
): Promise<void> {
  const res = await fetch(`${apiBase()}/api/analysis/stream`, {
    method: "POST",
    headers: headers(settings),
    body: JSON.stringify({ content, title, enable_rag: enableRag }),
  });
  if (!res.ok || !res.body) throw new Error(await errorText(res));

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const event = parseSse(chunk);
      if (!event) continue;
      if (event.event === "progress") onProgress(JSON.parse(event.data).node);
      else if (event.event === "result") onResult(JSON.parse(event.data));
    }
  }
}

function parseSse(chunk: string): { event: string; data: string } | null {
  let event = "message";
  let data = "";
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  return data ? { event, data } : null;
}

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return body.detail ?? `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

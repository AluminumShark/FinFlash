# FinFlash Backend

FastAPI + LangGraph backend for the FinFlash financial-news multi-agent analysis
system.

## Stack

- **FastAPI** — async API + SSE streaming
- **LangGraph** — agent orchestration (research/sentiment/extraction/risk/summary)
- **LiteLLM** — multi-provider LLM access (OpenAI / Anthropic / Gemini / DeepSeek) with
  bring-your-own-key
- **SQLAlchemy 2.0 (async)** + **pgvector** — persistence and RAG vector search
- **Redis** — per-API-key daily request/spend quotas
- **Astral toolchain** — `uv`, `ruff`, `ty`, `pytest`

## Quick start

```bash
uv sync --extra dev
cp .env.example .env          # add at least one provider key + EXA_API_KEY
uv run uvicorn app.main:app --reload
```

On first start an API key is generated and logged once — save it.

## Develop

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
uv run pytest
```

## Auth & model selection (headers)

| Header           | Purpose                                              |
|------------------|------------------------------------------------------|
| `X-API-Key`      | FinFlash access key (required)                        |
| `X-LLM-Provider` | `openai` / `anthropic` / `gemini` / `deepseek`       |
| `X-LLM-Model`    | full LiteLLM model id (e.g. `anthropic/claude-opus-4-6`) |
| `X-LLM-Key`      | bring-your-own provider key (optional)               |

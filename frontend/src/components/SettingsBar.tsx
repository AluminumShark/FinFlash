import type { LLMSettings } from "../types";

const PROVIDERS = [
  { value: "", label: "Server default" },
  { value: "ollama", label: "Ollama (本地測試 · 免金鑰)" },
  { value: "openai", label: "OpenAI (GPT-5)" },
  { value: "anthropic", label: "Anthropic (Claude Opus 4.6)" },
  { value: "gemini", label: "Gemini 2.5 Flash" },
  { value: "deepseek", label: "DeepSeek" },
];

// Common local models on the Ollama host (LiteLLM ids).
const OLLAMA_MODELS = [
  "ollama_chat/gemma3:12b",
  "ollama_chat/gemma3:4b",
  "ollama_chat/qwen3.5:4b",
  "ollama_chat/glm-4.7-flash:latest",
  "ollama_chat/ministral-3:14b",
];
const DEFAULT_OLLAMA_MODEL = OLLAMA_MODELS[0];

interface Props {
  settings: LLMSettings;
  onChange: (s: LLMSettings) => void;
}

export function SettingsBar({ settings, onChange }: Props) {
  const set = (patch: Partial<LLMSettings>) => onChange({ ...settings, ...patch });

  function onProvider(provider: string) {
    if (provider === "ollama") {
      const model = settings.model.startsWith("ollama") ? settings.model : DEFAULT_OLLAMA_MODEL;
      onChange({ ...settings, provider, model, byoKey: "" });
    } else {
      // Clear an Ollama model id when leaving Ollama mode.
      const model = settings.model.startsWith("ollama") ? "" : settings.model;
      onChange({ ...settings, provider, model });
    }
  }

  const isOllama = settings.provider === "ollama";
  const isCloud = settings.provider && !isOllama;

  return (
    <div className="settings-bar">
      <label>
        Model provider
        <select value={settings.provider} onChange={(e) => onProvider(e.target.value)}>
          {PROVIDERS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      {isOllama && (
        <label>
          Ollama model
          <select value={settings.model} onChange={(e) => set({ model: e.target.value })}>
            {OLLAMA_MODELS.map((m) => (
              <option key={m} value={m}>
                {m.replace("ollama_chat/", "")}
              </option>
            ))}
          </select>
        </label>
      )}
      {isCloud && (
        <label>
          你的模型供應商 API Key
          <input
            type="password"
            placeholder="sk-... / AIza... (填你自己的 key)"
            value={settings.byoKey}
            onChange={(e) => set({ byoKey: e.target.value })}
          />
        </label>
      )}
    </div>
  );
}

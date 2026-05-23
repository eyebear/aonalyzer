# AI Provider Guide

AI is **optional**. The platform runs fully in a deterministic fallback mode
with no provider configured. AI shapes explanations and reads pasted option
text; it never overrides deterministic decisions or hard filters, and never
invents missing option values.

## Modes / providers

| Provider | Notes |
|----------|-------|
| `DISABLED` (default) | No external AI. Chat returns deterministic degraded answers. |
| `MANUAL_PASTE` | You paste a prompt elsewhere and paste the answer back. |
| `GEMINI` | Set `GEMINI_API_KEY` (+ `GEMINI_MODEL`). |
| `GROK` | Set `GROK_API_KEY` (+ `GROK_MODEL`). |
| `OPENAI_COMPATIBLE` | Set `OPENAI_COMPATIBLE_API_KEY` + `OPENAI_COMPATIBLE_BASE_URL` + model. |
| `OLLAMA` / `LOCAL_LLM` | Local runtime; set `OLLAMA_BASE_URL` / `LOCAL_LLM_BASE_URL`. |
| `CUSTOM` | Set `CUSTOM_PROVIDER_BASE_URL` + key + model. |

## Configuring

- Set the active and fallback providers via Settings, the AI Providers panel on
  Home, or `ACTIVE_AI_PROVIDER` / `FALLBACK_AI_PROVIDER` env vars.
- Provider rows live in the `ai_providers` table (seeded with defaults). A
  provider stays `NOT_CONFIGURED` until its key/base URL is set.

## Task types

`GENERAL`, `EVENT_ANALYSIS`, `OPTION_TEXT_READER`, `RESEARCH_CHAT`,
`DECISION_SUMMARY`. The chat routes to `OPTION_TEXT_READER` for the Option Text
Reader mode and `RESEARCH_CHAT` otherwise.

## Safety contract

- The chat uses only the provided system context (the deterministic decision +
  records). It cites the fields it used.
- If option data is missing it says so; if incomplete it explains what cannot be
  calculated. It never fabricates bid/ask/strike/IV/Greeks.
- It never changes the deterministic verdict; answer modes change format only.
- With no provider configured, every mode returns a deterministic degraded-state
  answer built from the context — the chat never errors out.

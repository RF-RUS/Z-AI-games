# Enabling VLM perception with Ollama

The agent's default perception is a per-game heuristic (colour + coordinate, no
card value). The **VLM path** (D6) sends the screenshot to a vision-language
model that returns the full board — hand cards *with values*, top card, whose
turn — so the agent plays the right card on any card game, not just calibrated
UNO. This runbook wires that path to a **local [Ollama](https://ollama.com)**
server. No cloud, no per-frame cost, private.

Ollama exposes an OpenAI-compatible API, so it reuses the existing
`OpenAICompatibleProvider` — no code changes, just a model, a profile, and two
env vars.

## 1. Install Ollama and pull a vision model

```bash
# macOS/Linux: https://ollama.com/download  (or: brew install ollama)
ollama serve                      # starts the API on http://127.0.0.1:11434

# Pull a vision-capable model (pick ONE):
ollama pull llama3.2-vision       # 11B, good default, ~8 GB
# ollama pull qwen2.5vl           # strong at reading small text/cards
# ollama pull llava               # lighter, lower accuracy
```

Verify vision works end to end:

```bash
curl http://127.0.0.1:11434/v1/chat/completions -d '{
  "model": "llama3.2-vision",
  "messages": [{"role":"user","content":"Say OK"}]
}'
```

You should get a JSON completion back. If `ollama serve` isn't running, start it
first (the desktop app also runs it).

## 2. Enable the bundled Ollama profile

A ready profile ships at `models/profiles/local__ollama-vlm.json`:

```json
{
  "profile_id": "local/ollama-vlm",
  "provider": "ollama_openai",
  "base_url": "http://127.0.0.1:11434/v1",
  "model_name": "llama3.2-vision",
  "use_cases": ["perception_board"],
  "supports_multimodal": true,
  "enabled": false
}
```

- Set `"enabled": true`.
- If you pulled a different model, change `"model_name"` to match it exactly
  (as shown by `ollama list`).
- `base_url` must end in `/v1` (Ollama's OpenAI-compatible route).

The model-registry service loads every `models/profiles/*.json` on startup, so no
registration step is needed beyond editing the file.

## 3. Turn on the VLM perception path (env vars)

Perception only calls the VLM when `VLM_PERCEPTION` is on. It stays off by
default so nothing changes until you opt in.

**Windows (PowerShell) — set before `dev-backend.ps1`:**

```powershell
$env:VLM_PERCEPTION = "1"
$env:VLM_PROFILE_ID = "local/ollama-vlm"
# optional overrides:
# $env:VLM_MODEL_RUNTIME_URL = "http://127.0.0.1:8111"   # model-runtime service
# $env:VLM_TIMEOUT_S = "30"
.\scripts\dev-backend.ps1
```

**macOS/Linux:**

```bash
export VLM_PERCEPTION=1
export VLM_PROFILE_ID=local/ollama-vlm
```

`OLLAMA_API_KEY` is not required (Ollama ignores auth); the provider sends a
dummy key.

## 4. Verify it's live

Run one session and watch the operator's **NEXT ACTION** diagnostic line:

- `[CVv3] pcv=v3 … hand_cards=N` with **N > 0 and real card values** in the
  GAME STATE panel → the VLM is reading the board.
- The GAME STATE panel (left rail) shows the hand *with numbers/actions* and the
  top card. Colour-only pills mean the model didn't read a value — try
  `qwen2.5vl` or a larger model.

If the VLM fails or is disabled, perception silently falls back to the heuristic
(`recognition_method` will be `heuristic` instead of `vlm`), so a bad model
never breaks the run — it just reverts to the old behaviour.

## How it fits together

```
screenshot ─▶ perception /perceive
                 │  (VLM_PERCEPTION=1 + screenshot present)
                 ▼
           vlm_provider.infer_vision
                 │  base64 image + board prompt
                 ▼
        model-runtime /invoke  ──▶  Ollama /v1/chat/completions  (vision)
                 │  JSON: {screen_state, whose_turn, top_card, hand_cards[...]}
                 ▼
           merger (VLM = primary; heuristic = fallback)
                 │  game_state.hand_cards / top_card
                 ▼
   legal actions from perceived board (9d)  +  operator GAME STATE panel (A)
```

## Tuning notes

- **Latency:** a local 11B vision model adds ~1–4 s per tick on CPU, less on GPU.
  Raise `--tick-interval` if the loop feels rushed; raise `VLM_TIMEOUT_S` if you
  see `vlm_inference_failed` timeouts.
- **Accuracy:** if card *values* are wrong, prefer `qwen2.5vl`; it reads small
  in-card glyphs better than llava. Colours are usually reliable on any model.
- **Cost/offline:** everything runs locally — no API key, no network, no
  per-frame billing.
- **Switching back:** unset `VLM_PERCEPTION` (or set it to `0`) and restart the
  backend to return to the heuristic path.

## Related

- Decision **D6** (AGENT_DECISIONS): VLM primary, heuristic fallback — the "any
  card game" rationale.
- `services/perception-service/src/uno_perception/vlm_provider.py` — the producer.
- `services/model-runtime-service/src/uno_model_runtime/providers.py` —
  `OpenAICompatibleProvider` (attaches the image as OpenAI vision content parts).

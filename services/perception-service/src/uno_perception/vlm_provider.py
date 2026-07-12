"""VLM perception provider — screenshot → structured board state.

Primary perception path for canvas / WebGL / Electron games where UIA/DOM is
empty and the per-game heuristic (`canvas_plugin`) can't read a real, fanned,
rotated hand. Sends the screenshot to a vision model via model-runtime and
returns a `VisionInference` whose `structured` payload is the shape the UNO
adapter's `parse_vlm` and the operator panel already consume
(`{screen_type, whose_turn, top_card, hand_cards}`).

Game-agnostic by design (D6): the model reads whatever cards are on screen, so
no per-game zone/colour calibration is needed. The heuristic stays as a fallback
when the VLM is disabled or fails.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from uno_schemas.perception import VisionInference

logger = logging.getLogger("vlm_perception")

MODEL_RUNTIME_URL = os.getenv("VLM_MODEL_RUNTIME_URL", "http://127.0.0.1:8111")
VLM_TIMEOUT_S = float(os.getenv("VLM_TIMEOUT_S", "30"))
# Off by default — enabling it routes perception through the VLM. Set
# VLM_PERCEPTION=1 (and a vision profile) to make it the primary path.
VLM_ENABLED = os.getenv("VLM_PERCEPTION", "0") not in ("0", "", "false", "False")
# Which model-runtime profile to invoke. A vision-capable profile (e.g. a local
# Qwen2-VL served via vLLM) must be registered; falls back to mock otherwise.
VLM_PROFILE_ID = os.getenv("VLM_PROFILE_ID", "mock/uno-assistant")


def vlm_enabled() -> bool:
    """Whether the VLM perception path is turned on (env-gated)."""
    return VLM_ENABLED


def _read_image_base64(screenshot_path: str) -> str | None:
    try:
        return base64.b64encode(Path(screenshot_path).read_bytes()).decode("ascii")
    except Exception as exc:  # noqa: BLE001 — any read error → skip VLM, fall back
        logger.warning("vlm_read_image_failed path=%s error=%s", screenshot_path, exc)
        return None


async def infer_vision(
    screenshot_path: str,
    game_type: str = "uno",
    profile_id: str | None = None,
) -> tuple[VisionInference | None, str]:
    """Screenshot → (VisionInference, status), or (None, reason) on failure.

    The status string surfaces WHY the VLM did/didn't produce a board so it can
    show up in the operator diagnostic ("ok", "no_image", "http_503" = profile
    disabled, "http_<code>", "error", "parse_failed", "empty_board"). The caller
    falls back to the heuristic on any non-"ok" status.
    """
    image_b64 = _read_image_base64(screenshot_path)
    if not image_b64:
        return None, "no_image"

    body = {
        "context": {"use_case": "perception_board", "correlation_id": f"vlm_{game_type}"},
        "profile_id": profile_id or VLM_PROFILE_ID,
        "prompt": _board_prompt(game_type),
        "image_base64": image_b64,
        "expect_json": True,
        "max_tokens": 512,
    }
    try:
        async with httpx.AsyncClient(timeout=VLM_TIMEOUT_S) as client:
            resp = await client.post(f"{MODEL_RUNTIME_URL}/invoke", json=body)
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        logger.warning("vlm_inference_http error=%s status=%s", exc, code)
        # 503 from model-runtime = profile disabled (the common "why is Ollama not
        # called" cause). Surface the code so it's actionable in the operator.
        return None, f"http_{code}"
    except Exception as exc:  # noqa: BLE001 — network/model failure → fall back
        logger.warning("vlm_inference_failed error=%s", exc)
        return None, "error"

    structured = result.get("structured") or {}
    # structured may be a StructuredModelOutput-shaped dict; unwrap to parsed.
    if isinstance(structured, dict) and "parsed" in structured:
        structured = structured.get("parsed") or {}
    raw_text = result.get("text", "")
    if not structured and raw_text:
        try:
            structured = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("vlm_parse_failed text=%s", raw_text[:200])
            return None, "parse_failed"

    normalized = _normalize_board(structured)
    if normalized is None:
        return None, "empty_board"
    # model-runtime silently falls back to a MOCK provider on any real-provider
    # error, returning a canned board (200 OK). Surface that so we don't mistake
    # fabricated cards for a real VLM read — the operator sees "mock_fallback".
    if result.get("fallback_used"):
        status = "mock_fallback"
    else:
        status = "ok"
    return VisionInference(
        model_id=str(result.get("profile_id") or profile_id or VLM_PROFILE_ID),
        raw_output=raw_text or json.dumps(structured),
        structured=normalized,
        confidence=float(normalized.get("confidence", 0.0) or 0.0),
    ), status


def _board_prompt(game_type: str) -> str:
    return (
        f"You are looking at a screenshot of a {game_type} card game. "
        "Return ONLY JSON with this exact shape:\n"
        '{"screen_state":"in_game|lobby|menu|unknown",'
        '"whose_turn":"self|opponent|unknown",'
        '"top_card":{"color":"red|green|blue|yellow|wild","value":"<number or action>"},'
        '"hand_cards":[{"color":"...","value":"..."}],'
        '"confidence":0.0-1.0}\n'
        "hand_cards are the current player's own cards at the bottom, left to right. "
        "Use lowercase colours. If you cannot read a card's number/action, use an empty value."
    )


def _normalize_board(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a VLM board dict into the canonical game_state shape.

    Output keys match what `UnuPerceptionAdapter.parse_vlm` / the operator panel
    read: screen_type, whose_turn, top_card{color,value}, hand_cards[...]. Returns
    None when the payload has no usable card data (so the caller falls back).
    """
    if not isinstance(raw, dict):
        return None

    def card(c: Any) -> dict[str, str] | None:
        if not isinstance(c, dict):
            return None
        color = str(c.get("color") or "").lower()
        # accept "value" or "number" (some prompts emit number)
        value = str(c.get("value") if c.get("value") is not None else c.get("number") or "")
        if not color and not value:
            return None
        return {"color": color, "value": value}

    top = card(raw.get("top_card"))
    hand = [x for x in (card(h) for h in (raw.get("hand_cards") or [])) if x]
    if not top and not hand:
        return None

    return {
        "screen_type": raw.get("screen_state") or raw.get("screen_type") or "unknown",
        "whose_turn": raw.get("whose_turn", "unknown"),
        "top_card": top,
        "hand_cards": hand,
        "hand_count": len(hand),
        "confidence": raw.get("confidence", 0.0),
        "source": "vlm",
    }

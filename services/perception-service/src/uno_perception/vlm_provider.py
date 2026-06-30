"""VLM perception provider — screenshot-based inference for canvas/WebGL games.

Takes a screenshot, calls a vision model, and returns structured game state
that maps into canonical InferredState / Uncertainty contracts.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger("vlm_perception")

MODEL_RUNTIME_URL = "http://127.0.0.1:8111"
VLM_TIMEOUT_S = 30.0


async def infer_from_screenshot(
    screenshot_base64: str,
    game_type: str = "uno",
    model_profile_id: str | None = None,
    prompt_id: str = "perception_dispute",
) -> dict[str, Any]:
    """Call VLM to infer game state from screenshot.
    
    Returns a dict compatible with InferredState:
    {
        "screen_state": "in_game" | "lobby" | "menu" | "unknown",
        "whose_turn": "self" | "opponent" | "unknown",
        "entities": [...],
        "summary": "...",
        "confidence": 0.0-1.0,
        "uncertainty": {...}
    }
    """
    try:
        async with httpx.AsyncClient(timeout=VLM_TIMEOUT_S) as client:
            resp = await client.post(f"{MODEL_RUNTIME_URL}/invoke", json={
                "context": {
                    "use_case": "perception_dispute",
                    "correlation_id": f"vlm_{game_type}",
                },
                "profile_id": model_profile_id,
                "prompt_id": prompt_id,
                "variables": {
                    "screenshot": f"[base64 image of {game_type} game]",
                    "game_type": game_type,
                },
                "expect_json": True,
            })
            resp.raise_for_status()
            result = resp.json()

        structured = result.get("structured") or {}
        if not structured:
            text = result.get("text", "")
            try:
                structured = json.loads(text)
            except json.JSONDecodeError:
                logger.warning("vlm_parse_failed text=%s", text[:200])
                return _empty_state(game_type)

        return _normalize_vlm_output(structured, game_type)

    except Exception as exc:
        logger.warning("vlm_inference_failed error=%s", str(exc))
        return _empty_state(game_type)


def _normalize_vlm_output(raw: dict, game_type: str) -> dict[str, Any]:
    """Normalize VLM output into canonical InferredState format."""
    screen_state = raw.get("screen_state", "unknown")
    whose_turn = raw.get("whose_turn", "unknown")
    confidence = raw.get("confidence", 0.0)
    
    entities = []
    for elem in raw.get("elements", raw.get("entities", [])):
        entities.append({
            "entity_id": elem.get("id", f"vlm_{len(entities)}"),
            "entity_type": elem.get("type", "item"),
            "name": elem.get("name", "unknown"),
            "confidence": elem.get("confidence", confidence),
            "location": elem.get("location", {}),
            "game_data": elem,
        })
    
    return {
        "game_type": game_type,
        "screen_state": screen_state,
        "whose_turn": whose_turn,
        "turn_confidence": confidence,
        "entities": entities,
        "summary": raw.get("summary", f"VLM detected {len(entities)} elements"),
        "observation_confidence": confidence,
        "source": "vlm",
    }


def _empty_state(game_type: str) -> dict[str, Any]:
    """Return empty state when VLM fails."""
    return {
        "game_type": game_type,
        "screen_state": "unknown",
        "whose_turn": "unknown",
        "turn_confidence": 0.0,
        "entities": [],
        "summary": "VLM inference failed",
        "observation_confidence": 0.0,
        "source": "vlm_failed",
    }

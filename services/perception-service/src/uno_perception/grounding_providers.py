"""Concrete grounding providers — implement the `GroundingProvider` protocol.

`grounding.py` defines the contract ("where do I click for action X?"); this
module fills it. Today it ships the universal net — `VLMGroundingProvider`,
which asks a vision model for the click point directly. Template/UIA providers
plug in later at the same seam (see `grounding.py` docstring).

VLMGroundingProvider reuses the perception VLM machinery verbatim (same
`/invoke` body shape, same base64 helper, same env gate) so there is one vision
path to configure, not two. It works on any game because it reads pixels, not a
per-game asset — the same reason D6 made the VLM the primary perception path.
"""

from __future__ import annotations

import json
import logging

import httpx
from uno_perception.grounding import GroundingProvider, GroundingRequest, GroundingResult
from uno_perception.vlm_provider import (
    MODEL_RUNTIME_URL,
    VLM_PROFILE_ID,
    VLM_TIMEOUT_S,
    _read_image_base64,
    vlm_enabled,
)

logger = logging.getLogger("vlm_grounding")


def _action_phrase(req: GroundingRequest) -> str:
    """Human phrase describing the target, built from action_type + params.

    Game-agnostic: new actions add params without touching this contract. Kept
    deliberately loose — the VLM reads the phrase, not a rigid schema.
    """
    params = req.params or {}
    if req.action_type == "choose_color" and params.get("color"):
        return f"the {params['color']} colour button in the colour picker"
    if req.action_type in ("play_card", "play") and params.get("card"):
        return f"the card '{params['card']}' in the player's hand"
    if req.action_type in ("draw", "draw_card"):
        return "the draw pile / deck to draw a card"
    # Fallback: describe by action + whatever params were supplied.
    extra = " ".join(f"{k}={v}" for k, v in params.items())
    return f"the target for action '{req.action_type}' {extra}".strip()


def _grounding_prompt(req: GroundingRequest) -> str:
    return (
        f"You are looking at a screenshot of a {req.game_type} game. "
        f"Find {_action_phrase(req)} and return the pixel coordinate to CLICK it. "
        "Return ONLY JSON with this exact shape:\n"
        '{"found":true|false,"x":<center px>,"y":<center px>,"confidence":0.0-1.0}\n'
        "x,y are the centre of the element in the screenshot's pixel space "
        "(origin top-left). If you cannot locate it, return "
        '{"found":false,"confidence":0.0}.'
    )


class VLMGroundingProvider:
    """Ground an action to a click point by asking a vision model directly.

    ponytail: direct-coordinate grounding, not Set-of-Marks. Reuses the existing
    VLM path with zero new deps. Upgrade path if accuracy falls short: generate
    candidate marks with OpenCV, overlay numbered labels, ask the VLM for a mark
    number (SoM / OmniParser). Swap the prompt + add a candidate generator here.
    """

    method = "vlm"

    def __init__(self, profile_id: str | None = None) -> None:
        self._profile_id = profile_id or VLM_PROFILE_ID

    async def ground(self, req: GroundingRequest) -> GroundingResult:
        if not vlm_enabled():
            return GroundingResult.miss("vlm", "vlm disabled (set VLM_PERCEPTION=1)")
        image_b64 = _read_image_base64(req.screenshot_path)
        if not image_b64:
            return GroundingResult.miss("vlm", "no_image")

        body = {
            "context": {"use_case": "action_grounding", "correlation_id": f"ground_{req.game_type}"},
            "profile_id": self._profile_id,
            "prompt": _grounding_prompt(req),
            "image_base64": image_b64,
            "expect_json": True,
            "max_tokens": 128,
        }
        try:
            async with httpx.AsyncClient(timeout=VLM_TIMEOUT_S) as client:
                resp = await client.post(f"{MODEL_RUNTIME_URL}/invoke", json=body)
                resp.raise_for_status()
                result = resp.json()
        except httpx.HTTPStatusError as exc:
            return GroundingResult.miss("vlm", f"http_{exc.response.status_code}")
        except Exception as exc:  # noqa: BLE001 — network/model failure → miss, fall through
            logger.warning("vlm_grounding_failed error=%s", exc)
            return GroundingResult.miss("vlm", "error")

        # model-runtime silently falls back to a canned MOCK on provider error —
        # a mock has no real screen, so its coords are meaningless. Treat as miss.
        if result.get("fallback_used"):
            return GroundingResult.miss("vlm", "mock_fallback")

        parsed = _parse_point(result)
        if parsed is None:
            return GroundingResult.miss("vlm", "parse_failed")
        found, x, y, conf = parsed
        if not found or x is None or y is None:
            return GroundingResult.miss("vlm", "not_found")
        return GroundingResult.hit(float(x), float(y), float(conf), "vlm")


def _parse_point(result: dict) -> tuple[bool, float | None, float | None, float] | None:
    """Extract (found, x, y, confidence) from a model-runtime /invoke result."""
    structured = result.get("structured") or {}
    if isinstance(structured, dict) and "parsed" in structured:
        structured = structured.get("parsed") or {}
    if not structured:
        raw_text = result.get("text", "")
        if not raw_text:
            return None
        try:
            structured = json.loads(raw_text)
        except json.JSONDecodeError:
            return None
    if not isinstance(structured, dict):
        return None
    found = bool(structured.get("found", True))  # older prompts omit `found`
    x = structured.get("x")
    y = structured.get("y")
    conf = structured.get("confidence", 0.0) or 0.0
    try:
        return found, (None if x is None else float(x)), (None if y is None else float(y)), float(conf)
    except (TypeError, ValueError):
        return None


def default_providers(game_type: str = "unknown") -> list[GroundingProvider]:
    """Providers to try, cheapest-first. Today: VLM only.

    UIA/Template providers plug in ahead of VLM here once implemented — the
    resolver already tries them in order and falls through on a miss.
    """
    return [VLMGroundingProvider()]

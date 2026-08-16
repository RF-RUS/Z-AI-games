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
import os
import re
from pathlib import Path
from typing import Any

import httpx
from uno_schemas.perception import VisionInference
from uno_shared.logging import get_logger

# structlog, NOT logging.getLogger(): the project configures structlog to print to
# STDOUT (uno_shared.logging.configure_logging), which is what lands in
# logs/<service>.log. A bare stdlib logger is never configured here — the root
# logger has no handler, so Python's lastResort handler dumped these warnings
# unformatted onto STDERR (logs/<service>.err.log). That is why vlm_parse_failed
# had never once been seen despite the VLM path failing every cycle.
logger = get_logger("vlm_perception")

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
        logger.warning("vlm_read_image_failed", path=screenshot_path, error=str(exc))
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
        # 3072, not 1024: qwen3-vl is a THINKING model — it emits reasoning tokens
        # before the answer, and the reasoning is billed against the same budget.
        # At 1024 the budget was consumed entirely by reasoning, the answer never
        # started, and message.content came back as "" (finish_reason=length) —
        # which perception logged as `vlm_empty_board keys=[] raw= structured={}`.
        # The board JSON is small, so the headroom costs latency, not correctness.
        "max_tokens": 3072,
    }
    try:
        async with httpx.AsyncClient(timeout=VLM_TIMEOUT_S) as client:
            resp = await client.post(f"{MODEL_RUNTIME_URL}/invoke", json=body)
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        logger.warning("vlm_inference_http", error=str(exc), status=code)
        # 503 from model-runtime = profile disabled (the common "why is Ollama not
        # called" cause). Surface the code so it's actionable in the operator.
        return None, f"http_{code}"
    except Exception as exc:  # noqa: BLE001 — network/model failure → fall back
        # Never str(exc) alone: httpx transport errors (ReadTimeout, ConnectError)
        # have an EMPTY str(), which would log `error=` and say nothing.
        logger.warning("vlm_inference_failed", error=f"{type(exc).__name__}: {exc}")
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
            # Common failure modes even when the model is told to output only JSON:
            # 1. Markdown code fences:  ```json\n{...}\n```
            # 2. Reasoning preamble:    "Let me think... {json}"  (thinking not fully suppressed)
            # Try to extract the first {...} block before giving up.
            cleaned = _extract_json_object(raw_text)
            if cleaned:
                try:
                    structured = json.loads(cleaned)
                except json.JSONDecodeError:
                    pass
            if not structured:
                logger.warning("vlm_parse_failed", text=raw_text[:400])
                return None, "parse_failed"

    normalized = _normalize_board(structured)
    if normalized is None:
        # "empty_board" means the model ANSWERED and the JSON parsed, but carried
        # no top_card / hand_cards / prompts we could use — almost always a key or
        # nesting mismatch against _board_prompt, not a model failure. Without the
        # actual payload this status is undebuggable, so log what came back: the
        # top-level keys (cheap to eyeball for a rename or a wrapper object) and
        # the raw text (cheap to eyeball for a reasoning preamble or truncation).
        logger.warning(
            "vlm_empty_board",
            keys=sorted(structured) if isinstance(structured, dict) else type(structured).__name__,
            structured=(json.dumps(structured, ensure_ascii=False)[:600] if structured else "{}"),
            raw=raw_text[:600],
        )
        return None, "empty_board"
    # model-runtime silently falls back to a MOCK provider on any real-provider
    # error, returning a canned board (200 OK). That board is FABRICATED - the
    # deterministic red-6 hand from MockProvider._mock_output - so it must never
    # reach perception: it arrives with confidence 0.8, outranks the heuristic and
    # the agent then plays a hand that does not exist on screen. Returning None
    # makes the caller fall back to the heuristic, which is what the docstring
    # always claimed happened for a non-"ok" status.
    if result.get("fallback_used"):
        logger.warning(
            "vlm_mock_fallback",
            profile=result.get("profile_id"),
            upstream_error=result.get("error"),
            note="discarding canned board",
        )
        return None, "mock_fallback"
    return VisionInference(
        model_id=str(result.get("profile_id") or profile_id or VLM_PROFILE_ID),
        raw_output=raw_text or json.dumps(structured),
        structured=normalized,
        confidence=float(normalized.get("confidence", 0.0) or 0.0),
    ), "ok"


def _extract_json_object(text: str) -> str | None:
    """Try to pull the first valid JSON object out of a messy model response.

    Handles the two most common failure modes:
    - Markdown code fences: ```json\\n{...}\\n``` or ```\\n{...}\\n```
    - Reasoning preamble before the JSON (model ignored /no_think)

    Returns the raw JSON string (not parsed) so the caller can decide, or None
    if no {...} block could be found.  Does NOT validate nesting — that is left
    to json.loads so errors are explicit.
    """
    if not text:
        return None
    # 1. Strip markdown code fences (```json ... ``` or ``` ... ```)
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    # 2. Find the first '{' and match its closing '}' via a simple brace counter.
    #    This handles a reasoning preamble that precedes the JSON object.
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _board_prompt(game_type: str) -> str:
    return (
        # First line is an anti-thinking instruction, on purpose: qwen3-vl-class
        # models will otherwise spend hundreds of tokens reasoning before the JSON,
        # and that reasoning is billed against max_tokens. Raising the budget is the
        # safety net; not spending it is the cure.
        "/no_think Answer immediately with JSON only. Do not reason, explain, or "
        "write any text before or after the JSON.\n"
        f"You are looking at a screenshot of a {game_type} card game. "
        "Return ONLY JSON with this exact shape:\n"
        '{"screen_state":"in_game|lobby|menu|unknown",'
        '"whose_turn":"self|opponent|unknown",'
        '"top_card":{"color":"red|green|blue|yellow|wild","value":"<number or action>"},'
        '"hand_cards":[{"color":"...","value":"..."}],'
        '"opponents":[{"seat":"left|right|top","hand_count":<int>}],'
        '"draw_pile":{"x":<center px>,"y":<center px>},'
        '"prompts":[{"label":"<button text e.g. Play|Keep|Draw|choose a colour>",'
        '"x":<center px>,"y":<center px>}],'
        '"confidence":0.0-1.0}\n'
        "hand_cards are the current player's own cards at the bottom, left to right. "
        "opponents lists each other player still in the game with their seat position "
        "(left/right/top relative to the current player) and how many cards they are holding. "
        "draw_pile is the pixel coordinate of the centre of the face-down draw deck "
        "(the pile the player draws from); omit or null if not visible. "
        "prompts are any on-screen action BUTTONS or dialogs the player must click "
        "right now (e.g. a 'Play'/'Keep' choice after drawing, a colour picker after "
        "a wild, 'UNO!', 'Continue'). Give each button's visible label and the pixel "
        "coordinate of its centre. Empty list if there are none. "
        "Use lowercase colours. If you cannot read a card's number/action, use an empty value."
    )


def _normalize_board(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a VLM board dict into the canonical game_state shape.

    Output keys match what `UnuPerceptionAdapter.parse_vlm` / the operator panel
    read: screen_type, whose_turn, top_card{color,value}, hand_cards[...]. Also
    carries `prompts` (on-screen buttons the agent must click, with coords).
    Returns None when the payload has no usable board/prompt data.
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

    def prompt_btn(p: Any) -> dict[str, Any] | None:
        if not isinstance(p, dict):
            return None
        label = str(p.get("label") or p.get("text") or "").strip()
        if not label:
            return None
        out: dict[str, Any] = {"label": label}
        if "x" in p and "y" in p:
            try:
                out["center"] = {"x": int(p["x"]), "y": int(p["y"])}
            except (TypeError, ValueError):
                pass
        return out

    def opponent(o: Any) -> dict[str, Any] | None:
        if not isinstance(o, dict):
            return None
        seat = str(o.get("seat") or "").strip().lower()
        if not seat:
            return None
        out: dict[str, Any] = {"seat": seat}
        try:
            out["hand_count"] = int(o.get("hand_count") or 0)
        except (TypeError, ValueError):
            out["hand_count"] = 0
        return out

    top = card(raw.get("top_card"))
    hand = [x for x in (card(h) for h in (raw.get("hand_cards") or [])) if x]
    prompts = [x for x in (prompt_btn(p) for p in (raw.get("prompts") or [])) if x]
    opponents = [x for x in (opponent(o) for o in (raw.get("opponents") or [])) if x]
    # draw_pile — deck coordinate for the draw_card grounding path; None when absent/malformed.
    draw_pile: dict[str, int] | None = None
    dp_raw = raw.get("draw_pile")
    if isinstance(dp_raw, dict) and dp_raw.get("x") is not None and dp_raw.get("y") is not None:
        try:
            draw_pile = {"x": int(dp_raw["x"]), "y": int(dp_raw["y"])}
        except (TypeError, ValueError):
            pass
    # Usable if we read cards OR an on-screen prompt/button to act on.
    if not top and not hand and not prompts:
        return None

    return {
        "screen_type": raw.get("screen_state") or raw.get("screen_type") or "unknown",
        "whose_turn": raw.get("whose_turn", "unknown"),
        "top_card": top,
        "hand_cards": hand,
        "hand_count": len(hand),
        "prompts": prompts,
        "opponents": opponents,
        "draw_pile": draw_pile,
        "confidence": raw.get("confidence", 0.0),
        "source": "vlm",
    }

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
import hashlib
import json
import os
import re
import time
from collections import OrderedDict
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
# Token budget for the board prompt. This build of Ollama IGNORES the
# think:false flags (verified 2026-08-26: native "think" and
# chat_template_kwargs.enable_thinking both still produce ~7k chars of
# reasoning), so a THINKING VLM must get enough budget for reasoning + JSON.
# At 3072 the answer was truncated mid-JSON (finish_reason=length) and
# perception logged parse_failed / empty_board on every real frame.
# With a non-thinking VLM (qwen2.5-vl) the JSON is ~150 tokens, so the extra
# headroom costs nothing.
VLM_MAX_TOKENS = int(os.getenv("VLM_MAX_TOKENS", "4096"))
# Off by default — enabling it routes perception through the VLM. Set
# VLM_PERCEPTION=1 (and a vision profile) to make it the primary path.
VLM_ENABLED = os.getenv("VLM_PERCEPTION", "0") not in ("0", "", "false", "False")
# Which model-runtime profile to invoke. A vision-capable profile (e.g. a local
# Qwen2-VL served via vLLM) must be registered; falls back to mock otherwise.
VLM_PROFILE_ID = os.getenv("VLM_PROFILE_ID", "mock/uno-assistant")

# ── Response cache ─────────────────────────────────────────────────────────────
# Turn-based games spend whole ticks waiting for the VLM while the board HASN'T
# CHANGED (opponents' turns, lobby screens, repeated observations of the same
# frame). Caching inference results by content hash skips redundant model calls:
# the screenshot is the entire input, so identical bytes + profile + game type
# always yield the same answer. This is a correctness-neutral optimization —
# only fresh frames pay model latency. Bounded ring (FIFO eviction) + TTL keep
# memory flat for long unattended runs.
VLM_CACHE_ENABLED = os.getenv("VLM_CACHE_ENABLED", "1") not in ("0", "false", "False")
VLM_CACHE_TTL_S = float(os.getenv("VLM_CACHE_TTL_S", "120"))
_VLM_CACHE_MAX = 64
_vlm_cache: OrderedDict[str, tuple[float, VisionInference]] = OrderedDict()


def _vlm_cache_key(image_bytes: bytes, profile_id: str, game_type: str) -> str:
  digest = hashlib.sha256(image_bytes).hexdigest()[:24]
  return f"{digest}|{profile_id}|{game_type}"


def _vlm_cache_get(key: str) -> VisionInference | None:
  if not VLM_CACHE_ENABLED or VLM_CACHE_TTL_S <= 0:
    return None
  entry = _vlm_cache.get(key)
  if entry is None:
    return None
  ts, inference = entry
  if time.time() - ts > VLM_CACHE_TTL_S:
    _vlm_cache.pop(key, None)
    return None
  _vlm_cache.move_to_end(key)
  return inference


def _vlm_cache_put(key: str, inference: VisionInference) -> None:
  if not VLM_CACHE_ENABLED:
    return
  _vlm_cache[key] = (time.time(), inference)
  _vlm_cache.move_to_end(key)
  while len(_vlm_cache) > _VLM_CACHE_MAX:
    _vlm_cache.popitem(last=False)


def reset_vlm_cache() -> None:
  """Clear cached inferences (tests / model reloads that change the output)."""
  _vlm_cache.clear()


def vlm_enabled() -> bool:
    """Whether the VLM perception path is turned on (env-gated)."""
    return VLM_ENABLED


def _read_image_bytes(screenshot_path: str) -> bytes | None:
    try:
        return Path(screenshot_path).read_bytes()
    except Exception as exc:  # noqa: BLE001 — any read error → skip VLM, fall back
        logger.warning("vlm_read_image_failed", path=screenshot_path, error=str(exc))
        return None


def _read_image_base64(screenshot_path: str) -> str | None:
    data = _read_image_bytes(screenshot_path)
    return base64.b64encode(data).decode("ascii") if data is not None else None


async def infer_vision(
    screenshot_path: str,
    game_type: str = "uno",
    profile_id: str | None = None,
) -> tuple[VisionInference | None, str]:
    """Screenshot → (VisionInference, status), or (None, reason) on failure.

    The status string surfaces WHY the VLM did/didn't produce a board so it can
    show up in the operator diagnostic ("ok", "cache_hit", "no_image", "http_503"
    = profile disabled, "http_<code>", "error", "parse_failed", "empty_board").
    The caller falls back to the heuristic on any non-("ok", "cache_hit") status.
    """
    image_bytes = _read_image_bytes(screenshot_path)
    if image_bytes is None:
        return None, "no_image"

    effective_profile = profile_id or VLM_PROFILE_ID
    cache_key = _vlm_cache_key(image_bytes, effective_profile, game_type)
    cached = _vlm_cache_get(cache_key)
    if cached is not None:
        return cached, "cache_hit"

    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    body = {
        "context": {"use_case": "perception_board", "correlation_id": f"vlm_{game_type}"},
        "profile_id": profile_id or VLM_PROFILE_ID,
        "prompt": _board_prompt(game_type),
        "image_base64": image_b64,
        "expect_json": True,
        # VLM_MAX_TOKENS (default 4096): this Ollama build ignores think:false, so
        # the qwen3-vl board prompt must fit reasoning + JSON in one budget.
        # 3072 was not enough — the answer was truncated mid-JSON
        # (finish_reason=length) and every real frame logged
        # vlm_parse_failed / vlm_empty_board. With a non-thinking VLM the JSON is
        # ~150 tokens, so the headroom costs nothing.
        "max_tokens": VLM_MAX_TOKENS,
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
    inference = VisionInference(
        model_id=str(result.get("profile_id") or effective_profile),
        raw_output=raw_text or json.dumps(structured),
        structured=normalized,
        confidence=float(normalized.get("confidence", 0.0) or 0.0),
    )
    _vlm_cache_put(cache_key, inference)
    return inference, "ok"


def _extract_json_object(text: str) -> str | None:
    """Try to pull the first JSON object out of a messy model response.

    Handles the failure modes observed on real frames (2026-08-27, qwen2.5-vl):
    - Markdown code fences: ```json\\n{...}\\n``` (closed)
    - **UNCLOSED fences**: the model opens ```json and the JSON is cut off by the
      token budget (finish_reason=length) — the old regex required the closing
      fence and silently returned None on every such frame.
    - Reasoning preamble before the JSON (model ignored /no_think).
    - Truncation mid-object: best-effort tail repair so a mostly-complete board
      (top_card + first N hand_cards) is still usable.

    Returns the raw JSON string (not parsed) so the caller can decide, or None
    if no usable object could be reconstructed.
    """
    if not text:
        return None
    # 1. Closed fence: take the body as-is.
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    # 2. Find the first '{'.
    start = text.find("{")
    if start == -1:
        return None
    # 3. Complete object: string-aware brace counter (braces inside string
    #    values would break a naive counter).
    complete = _first_complete_object(text, start)
    if complete is not None:
        return complete
    # 4. Truncated object (unclosed fence / finish_reason=length): repair tail.
    return _repair_truncated_object(text[start:])


def _first_complete_object(text: str, start: int) -> str | None:
    """Return text[start:end] when braces balance (string-aware), else None."""
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def _repair_truncated_object(fragment: str) -> str | None:
    """Best-effort close of a JSON object truncated by the token budget.

    The damage zone is the incomplete trailing token, so cut a few characters
    from the tail at a time and try to close whatever brackets are still open.
    The last partially-written card is simply absent — far better than
    discarding a 95%-complete board.
    """
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(fragment)
        return json.dumps(obj)
    except json.JSONDecodeError:
        pass
    n = len(fragment)
    for cut in range(n - 1, max(n - 400, 0), -4):
        head = fragment[:cut].rstrip().rstrip(",")
        candidate = _close_open_brackets(head)
        if candidate is None:
            continue
        try:
            decoder.raw_decode(candidate)
            return candidate
        except json.JSONDecodeError:
            continue
    return None


def _close_open_brackets(head: str) -> str | None:
    """Append closing brackets for whatever is left open after `head`.

    Returns None when the head ends in a state that cannot be closed
    (mismatched bracket, stray character at a value boundary, etc.).
    """
    stack: list[str] = []
    in_str = False
    escaped = False
    for ch in head:
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in "}]":
                if not stack or stack[-1] != ch:
                    return None
                stack.pop()
    if in_str:
        # Unterminated string value: close the string first.
        head = head + '"'
    return head + "".join(reversed(stack))


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
        '"drawn_card":{"color":"red|green|blue|yellow|wild","value":"<number or action>"},'
        '"prompts":[{"label":"<button text e.g. Play|Keep|Draw|choose a colour>",'
        '"x":<center px>,"y":<center px>}],'
        '"confidence":0.0-1.0}\n'
        "hand_cards are the current player's own cards at the bottom, left to right. "
        "opponents lists each other player still in the game with their seat position "
        "(left/right/top relative to the current player) and how many cards they are holding. "
        "draw_pile is the pixel coordinate of the centre of the face-down draw deck "
        "(the pile the player draws from); omit or null if not visible. "
        "drawn_card is the card the current player has JUST DRAWN and is being asked about "
        "(shown highlighted/enlarged near the play area next to a 'Play'/'Keep' choice); "
        "omit or null unless that situation is visible. "
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
    # The just-drawn card (the "Play or Keep this?" prompt). Absent on a normal
    # turn; carries colour/value only when the model could read it.
    drawn = card(raw.get("drawn_card"))
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
    # ── PROMPT/DECK COINCIDENCE GUARD (2026-08-28) ─────────────────────────────
    # The small VLM hallucinates a "Play" prompt at the EXACT centre it just
    # reported for the draw pile (session 0859f748: draw_pile=(600,300) AND
    # prompts=[Play @ (600,300)]). Two on-screen targets cannot occupy the same
    # pixel, so a prompt coinciding with the deck is a fabrication, and the agent
    # then "clicked Play" on the deck. Drop any prompt whose centre matches the
    # draw pile within a few px. Gated so a real button that merely sits NEAR the
    # deck is kept — only an exact/near-exact coincidence is rejected.
    if draw_pile and prompts:
        def _dp_coincides(p: dict[str, Any]) -> bool:
            c = p.get("center")
            if not isinstance(c, dict):
                return False
            try:
                return (abs(int(c.get("x", 0)) - draw_pile["x"]) <= 4
                        and abs(int(c.get("y", 0)) - draw_pile["y"]) <= 4)
            except (TypeError, ValueError):
                return False
        kept = [p for p in prompts if not _dp_coincides(p)]
        if len(kept) != len(prompts):
            logger.warning("vlm_prompt_dropped_drawpile_coincidence",
                           dropped=len(prompts) - len(kept))
            prompts = kept
    # Usable if we read cards OR an on-screen prompt/button to act on.
    if not top and not hand and not prompts:
        return None

    # ── PLAUSIBILITY GATE (2026-08-27) ──────────────────────────────────────────
    # A VLM can produce a *syntactically perfect* board that is physically
    # impossible: the live run on 2026-08-27 (session e8d99031, cycle 2) returned
    # 132 hand cards that were ALL `{"color":"red","value":"wild"}` with no parse
    # error — a repetition-collapse degeneration, which the merger then folded
    # straight into game_state (vlm_has_cards was True) and the agent acted on.
    # That is the "confidently wrong perception" this project warns it keeps
    # biting itself with. Reject the board (fall back to the heuristic) when it
    # violates invariants a real UNO hand cannot.
    reason = _board_rejection_reason(hand)
    if reason is not None:
        logger.warning("vlm_board_rejected", reason=reason, hand_count=len(hand))
        return None

    return {
        "screen_type": raw.get("screen_state") or raw.get("screen_type") or "unknown",
        "whose_turn": raw.get("whose_turn", "unknown"),
        "top_card": top,
        "drawn_card": drawn,
        "hand_cards": hand,
        "hand_count": len(hand),
        "prompts": prompts,
        "opponents": opponents,
        "draw_pile": draw_pile,
        "confidence": raw.get("confidence", 0.0),
        "source": "vlm",
    }


def _board_rejection_reason(hand: list[dict[str, str]]) -> str | None:
    """Return a reason string when the VLM hand is physically impossible, else None.

    Two independent invariants a real UNO hand cannot violate:
      1. **Card-count bound.** A hand starts at 7 and only grows by one draw per
         turn; 25 is already a full house plus the drawn card. Anything far above
         that (132 observed) is a degeneration, not a hand.
      2. **Repetition collapse.** A VLM stuck in a loop emits the same
         (color, value) many times in a row. Five identical consecutive cards is
         not a hand — it is the model failing to move its attention.
    """
    if len(hand) > _MAX_PLAUSIBLE_HAND:
        return f"hand_count_{len(hand)}_exceeds_{_MAX_PLAUSIBLE_HAND}"
    run = 1
    for i in range(1, len(hand)):
        if hand[i] == hand[i - 1]:
            run += 1
            if run >= _MAX_IDENTICAL_RUN:
                return f"repetition_collapse_{run}_x_{hand[i].get('color')}_{hand[i].get('value')}"
        else:
            run = 1
    return None


# A real UNO hand is 7 cards at start; even a maximum draw pile can't push the
# current player past ~21+1 before they must be down to play. 25 leaves headroom
# for the drawn-card prompt without ever accepting a degenerate 100+ count.
_MAX_PLAUSIBLE_HAND = 25
# Consecutive identical (color, value) cards that mark a repetition loop.
_MAX_IDENTICAL_RUN = 5

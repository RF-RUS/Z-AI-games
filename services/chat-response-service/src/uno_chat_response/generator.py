"""Chat response generation — template-first with model fallback."""

from __future__ import annotations

import json
import logging

import httpx
from uno_schemas.chat import ChatContext, ChatReply, ChatReplyRequest

logger = logging.getLogger("chat_response")

MODEL_RUNTIME_URL = "http://127.0.0.1:8111"
MODEL_TIMEOUT_S = 8.0

TEMPLATES: dict[ChatContext, list[str]] = {
  ChatContext.HELP: [
    "I'm here to help! What do you need?",
    "Ask me anything about the game.",
  ],
  ChatContext.SOCIAL: [
    "Good game!",
    "Thanks! Playing my best.",
    "gg!",
  ],
  ChatContext.GAMEPLAY: [
    "I'll make my move when it's my turn.",
    "Let's keep playing!",
  ],
  ChatContext.SYSTEM: ["Ready."],
  ChatContext.UNKNOWN: ["Hi there!"],
}

# Safety: words/phrases that should never appear in bot replies
BLOCKED_PATTERNS = [
  "my hand", "my cards", "i have", "strategy is",
  "going to play", "will play", "planning to",
]


def _check_safety(text: str) -> tuple[bool, str]:
  """Check if reply is safe — no strategy leakage."""
  text_lower = text.lower()
  for pattern in BLOCKED_PATTERNS:
    if pattern in text_lower:
      return False, f"Contains strategy hint: '{pattern}'"
  if len(text) > 200:
    return False, "Reply too long"
  return True, ""


def generate_reply_template(req: ChatReplyRequest) -> ChatReply:
  """Template-based reply — fast, deterministic."""
  templates = TEMPLATES.get(req.intent.context, TEMPLATES[ChatContext.UNKNOWN])
  text = templates[0]

  safe, reason = _check_safety(text)
  return ChatReply(
    text=text,
    approved=safe,
    source="template",
    confidence=0.95,
    correlation_id=req.correlation_id,
  )


async def generate_reply_model(req: ChatReplyRequest, game_type: str = "unknown") -> ChatReply:
  """Model-based reply — more natural, uses model-runtime."""
  from uno_shared.model_observability import get_usage_tracker
  tracker = get_usage_tracker()
  record = tracker.start(
    task="chat",
    game_type=game_type,
    provider="openai_compat",
    session_id=req.session_id,
    correlation_id=req.correlation_id,
  )

  chat_history = "\n".join(
    f"{m.sender}: {m.text}" for m in req.recent_messages[-5:]
  )

  try:
    async with httpx.AsyncClient(timeout=MODEL_TIMEOUT_S) as client:
      resp = await client.post(f"{MODEL_RUNTIME_URL}/invoke", json={
        "context": {
          "use_case": "chat_reply",
          "correlation_id": req.correlation_id,
          "session_id": req.session_id,
        },
        "prompt_id": "chat_reply_generate",
        "variables": {
          "game_type": game_type,
          "bot_role": "game assistant",
          "chat_history": chat_history,
          "message": req.intent.trigger_message.text,
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
        logger.warning("model_reply_parse_failed text=%s", text[:200])
        tracker.complete(record, success=False, fallback_used=True, fallback_reason="parse_failed")
        return generate_reply_template(req)

    reply_text = structured.get("reply", "")
    confidence = structured.get("confidence", 0.5)

    if not reply_text:
      tracker.complete(record, success=False, fallback_used=True, fallback_reason="empty_reply")
      return generate_reply_template(req)

    safe, reason = _check_safety(reply_text)
    if not safe:
      logger.warning("model_reply_unsafe reason=%s text=%s", reason, reply_text[:100])
      tracker.complete(record, success=False, fallback_used=True, fallback_reason=f"unsafe: {reason}")
      return generate_reply_template(req)

    tracker.complete(record, success=True, confidence=confidence)

    return ChatReply(
      text=reply_text,
      approved=True,
      source="model",
      confidence=confidence,
      correlation_id=req.correlation_id,
    )

  except Exception as exc:
    logger.warning("model_reply_failed error=%s — falling back to template", str(exc))
    tracker.complete(record, success=False, fallback_used=True, fallback_reason=str(exc))
    return generate_reply_template(req)


async def generate_reply(
  req: ChatReplyRequest,
  game_type: str = "unknown",
  use_model: bool = False,
) -> ChatReply:
  """Main entry point — routes to template or model-based generation."""
  if use_model:
    return await generate_reply_model(req, game_type)
  return generate_reply_template(req)

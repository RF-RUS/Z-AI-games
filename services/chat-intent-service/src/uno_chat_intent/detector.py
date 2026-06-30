"""Detect chat intent — rule-based and model-assisted."""

from __future__ import annotations

import json
import logging
import re
import time
from uuid import uuid4

import httpx
from uno_schemas.chat import ChatContext, ChatIntent, ChatMessage

logger = logging.getLogger("chat_intent")

BOT_ALIASES = ["bot", "uno bot", "operator", "@bot", "hey bot", "ai"]
ADDRESS_PATTERN = re.compile(r"@?\b(bot|operator|ai|uno)\b", re.I)

MODEL_RUNTIME_URL = "http://127.0.0.1:8111"
MODEL_TIMEOUT_S = 5.0


def parse_chat_messages(raw_lines: list[str]) -> list[ChatMessage]:
  messages: list[ChatMessage] = []
  for i, line in enumerate(raw_lines):
    sender, _, text = line.partition(":")
    messages.append(
      ChatMessage(
        message_id=str(uuid4()),
        sender=sender.strip() or "unknown",
        text=text.strip() or line,
        timestamp_ms=int(time.time() * 1000) + i,
      )
    )
  return messages


def detect_intent_rules(messages: list[ChatMessage], bot_name: str = "bot") -> ChatIntent | None:
  """Rule-based intent detection — fast, no model."""
  if not messages:
    return None

  latest = messages[-1]
  if latest.is_bot:
    return None

  text_lower = latest.text.lower()
  directed = any(alias in text_lower for alias in BOT_ALIASES) or bool(ADDRESS_PATTERN.search(latest.text))

  if "?" in latest.text:
    context = ChatContext.HELP
    reply_required = directed
  elif any(w in text_lower for w in ["gg", "nice", "lol", "haha", "thanks"]):
    context = ChatContext.SOCIAL
    reply_required = directed
  elif any(w in text_lower for w in ["play", "card", "turn", "uno"]):
    context = ChatContext.GAMEPLAY
    reply_required = directed and "?" in latest.text
  else:
    context = ChatContext.UNKNOWN
    reply_required = directed

  confidence = 0.9 if directed else 0.3

  return ChatIntent(
    directed_at_bot=directed,
    reply_required=reply_required,
    context=context,
    confidence=confidence,
    trigger_message=latest,
    reason="addressed bot" if directed else "ambient chat",
  )


async def detect_intent_model(
  messages: list[ChatMessage],
  game_type: str = "unknown",
  model_profile_id: str | None = None,
) -> ChatIntent | None:
  """Model-based intent detection — more accurate, uses model-runtime."""
  from uno_shared.model_observability import get_usage_tracker
  tracker = get_usage_tracker()
  record = tracker.start(
    task="intent",
    game_type=game_type,
    provider="openai_compat",
    profile_id=model_profile_id,
  )

  if not messages:
    tracker.complete(record, success=True)
    return None

  latest = messages[-1]
  if latest.is_bot:
    tracker.complete(record, success=True)
    return None

  chat_history = "\n".join(f"{m.sender}: {m.text}" for m in messages[-5:])

  try:
    async with httpx.AsyncClient(timeout=MODEL_TIMEOUT_S) as client:
      resp = await client.post(f"{MODEL_RUNTIME_URL}/invoke", json={
        "context": {
          "use_case": "chat_intent",
          "correlation_id": str(uuid4()),
        },
        "profile_id": model_profile_id,
        "prompt_id": "chat_intent",
        "variables": {
          "chat_history": chat_history,
          "message": latest.text,
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
        logger.warning("model_intent_parse_failed text=%s", text[:200])
        tracker.complete(record, success=False, fallback_used=True, fallback_reason="parse_failed")
        return detect_intent_rules(messages)

    directed = structured.get("directed_at_bot", False)
    reply_required = structured.get("reply_required", False)
    context_str = structured.get("context", "unknown")
    confidence = structured.get("confidence", 0.5)

    try:
      context = ChatContext(context_str)
    except ValueError:
      context = ChatContext.UNKNOWN

    tracker.complete(record, success=True, confidence=confidence)

    return ChatIntent(
      directed_at_bot=directed,
      reply_required=reply_required,
      context=context,
      confidence=confidence,
      trigger_message=latest,
      reason=f"model: {structured.get('reason', 'classified')}",
    )

  except Exception as exc:
    logger.warning("model_intent_detection_failed error=%s — falling back to rules", str(exc))
    tracker.complete(record, success=False, fallback_used=True, fallback_reason=str(exc))
    return detect_intent_rules(messages)


async def detect_intent(
  messages: list[ChatMessage],
  bot_name: str = "bot",
  use_model: bool = False,
  game_type: str = "unknown",
  model_profile_id: str | None = None,
) -> ChatIntent | None:
  """Main entry point — routes to rule-based or model-based detection."""
  if use_model:
    return await detect_intent_model(messages, game_type, model_profile_id)
  return detect_intent_rules(messages, bot_name)


def detect_intent_sync(
  messages: list[ChatMessage],
  bot_name: str = "bot",
) -> ChatIntent | None:
  """Synchronous wrapper for backward compatibility — always uses rules."""
  return detect_intent_rules(messages, bot_name)

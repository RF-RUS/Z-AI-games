"""Chat intent tests."""

import time

from uno_chat_intent.detector import detect_intent_sync, parse_chat_messages
from uno_schemas.chat import ChatMessage


def test_detect_bot_addressed():
  messages = [
    ChatMessage(message_id="1", sender="Player", text="hey bot, what are the rules?", timestamp_ms=int(time.time()*1000))
  ]
  intent = detect_intent_sync(messages)
  assert intent is not None
  assert intent.directed_at_bot
  assert intent.reply_required


def test_parse_raw_lines():
  msgs = parse_chat_messages(["Alice: hello", "Bob: hi"])
  assert len(msgs) == 2
  assert msgs[0].sender == "Alice"

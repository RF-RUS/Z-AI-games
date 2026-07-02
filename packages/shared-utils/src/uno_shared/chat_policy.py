"""Chat policy — controls when the bot responds and safety gating.

Defines explicit rules for:
- When to respond (directed messages, questions, etc.)
- When to stay silent (ambient chat, spam, toxic content)
- Rate limiting / cooldown
- Safety rules (no strategy leakage, no toxic content)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from uno_schemas.chat import ChatContext, ChatIntent, ChatReply


@dataclass
class ChatPolicyConfig:
    """Configuration for chat response policy."""
    
    # Response triggers
    respond_to_directed: bool = True       # respond when bot is addressed
    respond_to_questions: bool = True      # respond to "?" messages
    respond_to_social: bool = True         # respond to "gg", "nice", etc.
    respond_to_gameplay: bool = False      # don't respond to gameplay chatter
    respond_to_system: bool = False        # don't respond to system messages
    
    # Rate limiting
    min_interval_ms: int = 3000            # minimum ms between responses
    max_responses_per_minute: int = 10
    cooldown_after_spam_ms: int = 30000    # cooldown after detecting spam
    
    # Safety
    blocked_words: list[str] = field(default_factory=lambda: [
        "my hand", "my cards", "i have", "strategy is",
        "going to play", "will play", "planning to",
    ])
    max_reply_length: int = 200
    
    # Operator control
    operator_override: bool = False        # if True, always respond
    chat_enabled: bool = True              # master kill switch


@dataclass
class ChatPolicyResult:
    """Result of policy evaluation."""
    allowed: bool
    reason: str
    violations: list[str] = field(default_factory=list)


class ChatPolicy:
    """Evaluates whether a bot response should be sent."""
    
    def __init__(self, config: ChatPolicyConfig | None = None):
        self.config = config or ChatPolicyConfig()
        self._response_timestamps: list[float] = []
        self._cooldown_until: float = 0
    
    def evaluate(
        self,
        intent: ChatIntent,
        recent_replies: list[ChatReply] | None = None,
    ) -> ChatPolicyResult:
        """Evaluate whether the bot should respond to this intent."""
        # Master kill switch
        if not self.config.chat_enabled:
            return ChatPolicyResult(allowed=False, reason="chat_disabled")
        
        # Operator override
        if self.config.operator_override:
            return ChatPolicyResult(allowed=True, reason="operator_override")
        
        # Not directed at bot
        if not intent.directed_at_bot:
            if intent.context == ChatContext.HELP and self.config.respond_to_questions:
                pass  # Allow questions even if not directly addressed
            elif intent.context == ChatContext.SOCIAL and self.config.respond_to_social:
                pass  # Allow social if configured
            else:
                return ChatPolicyResult(allowed=False, reason="not_directed_at_bot")
        
        # Context-based gating
        if intent.context == ChatContext.GAMEPLAY and not self.config.respond_to_gameplay:
            return ChatPolicyResult(allowed=False, reason="gameplay_chat_disabled")
        if intent.context == ChatContext.SYSTEM and not self.config.respond_to_system:
            return ChatPolicyResult(allowed=False, reason="system_chat_disabled")
        
        # Rate limiting
        now = time.time() * 1000
        if now < self._cooldown_until:
            return ChatPolicyResult(allowed=False, reason="cooldown_active")
        
        recent_count = sum(1 for ts in self._response_timestamps if now - ts < 60000)
        if recent_count >= self.config.max_responses_per_minute:
            self._cooldown_until = now + self.config.cooldown_after_spam_ms
            return ChatPolicyResult(allowed=False, reason="rate_limit_exceeded")
        
        if self._response_timestamps:
            last = self._response_timestamps[-1]
            if now - last < self.config.min_interval_ms:
                return ChatPolicyResult(allowed=False, reason="min_interval_not_met")
        
        return ChatPolicyResult(allowed=True, reason="policy_passed")
    
    def record_response(self) -> None:
        """Record that a response was sent (for rate limiting)."""
        self._response_timestamps.append(time.time() * 1000)
        # Keep only last minute
        cutoff = time.time() * 1000 - 60000
        self._response_timestamps = [t for t in self._response_timestamps if t > cutoff]
    
    def check_reply_safety(self, reply: ChatReply) -> ChatPolicyResult:
        """Check if a generated reply is safe to send."""
        violations = []
        text_lower = reply.text.lower()
        
        for word in self.config.blocked_words:
            if word in text_lower:
                violations.append(f"Contains blocked phrase: '{word}'")
        
        if len(reply.text) > self.config.max_reply_length:
            violations.append(f"Reply too long ({len(reply.text)} > {self.config.max_reply_length})")
        
        if violations:
            return ChatPolicyResult(allowed=False, reason="safety_violation", violations=violations)
        
        return ChatPolicyResult(allowed=True, reason="safe")

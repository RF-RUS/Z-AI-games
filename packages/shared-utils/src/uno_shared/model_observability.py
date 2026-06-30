"""Model usage observability — tracks model calls, fallbacks, and latency.

Provides structured logging and metrics for every model-backed path.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("model_observability")


@dataclass
class ModelUsageRecord:
    """Single model invocation record."""
    task: str                    # "strategy" | "vision" | "chat" | "intent"
    game_type: str
    provider: str                # "openai_compat" | "mock" | "heuristic" | "template"
    model_id: str | None = None
    profile_id: str | None = None
    
    # Timing
    started_at_ms: float = 0
    completed_at_ms: float = 0
    latency_ms: float = 0
    
    # Outcome
    success: bool = True
    fallback_used: bool = False
    fallback_reason: str | None = None
    
    # Quality
    confidence: float | None = None
    parse_success: bool = True
    
    # Context
    session_id: str | None = None
    correlation_id: str | None = None


class ModelUsageTracker:
    """Tracks model usage across the platform."""
    
    def __init__(self):
        self._records: list[ModelUsageRecord] = []
        self._max_records = 1000
    
    def start(
        self,
        task: str,
        game_type: str,
        provider: str,
        model_id: str | None = None,
        profile_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ModelUsageRecord:
        """Start tracking a model invocation."""
        record = ModelUsageRecord(
            task=task,
            game_type=game_type,
            provider=provider,
            model_id=model_id,
            profile_id=profile_id,
            started_at_ms=time.time() * 1000,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        return record
    
    def complete(
        self,
        record: ModelUsageRecord,
        success: bool = True,
        fallback_used: bool = False,
        fallback_reason: str | None = None,
        confidence: float | None = None,
        parse_success: bool = True,
    ) -> ModelUsageRecord:
        """Complete a model invocation record."""
        record.completed_at_ms = time.time() * 1000
        record.latency_ms = record.completed_at_ms - record.started_at_ms
        record.success = success
        record.fallback_used = fallback_used
        record.fallback_reason = fallback_reason
        record.confidence = confidence
        record.parse_success = parse_success
        
        self._records.append(record)
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]
        
        # Log structured record
        logger.info(
            "model_usage task=%s game=%s provider=%s model=%s latency_ms=%.0f success=%s fallback=%s reason=%s",
            record.task, record.game_type, record.provider,
            record.model_id or "none", record.latency_ms,
            record.success, record.fallback_used, record.fallback_reason or "none",
        )
        
        return record
    
    def get_recent(self, task: str | None = None, limit: int = 50) -> list[ModelUsageRecord]:
        """Get recent usage records, optionally filtered by task."""
        records = self._records
        if task:
            records = [r for r in records if r.task == task]
        return records[-limit:]
    
    def get_summary(self) -> dict[str, Any]:
        """Get usage summary statistics."""
        if not self._records:
            return {"total": 0}
        
        by_task: dict[str, int] = {}
        by_provider: dict[str, int] = {}
        fallback_count = 0
        total_latency = 0.0
        
        for r in self._records:
            by_task[r.task] = by_task.get(r.task, 0) + 1
            by_provider[r.provider] = by_provider.get(r.provider, 0) + 1
            if r.fallback_used:
                fallback_count += 1
            total_latency += r.latency_ms
        
        return {
            "total": len(self._records),
            "by_task": by_task,
            "by_provider": by_provider,
            "fallback_count": fallback_count,
            "fallback_rate": fallback_count / len(self._records) if self._records else 0,
            "avg_latency_ms": total_latency / len(self._records) if self._records else 0,
        }


# Global tracker instance
_usage_tracker = ModelUsageTracker()


def get_usage_tracker() -> ModelUsageTracker:
    """Get the global model usage tracker."""
    return _usage_tracker

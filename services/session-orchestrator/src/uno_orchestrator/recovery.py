"""Error classification and recovery decisions."""

from __future__ import annotations

import httpx
from uno_schemas.orchestrator import ErrorClass, RecoveryConfig, RecoveryDecision, RecoveryMode
from uno_schemas.session import AdapterType


def format_exception_message(exc: Exception) -> str:
  msg = str(exc).strip()
  if msg:
    return msg
  return type(exc).__name__


def classify_error(exc: Exception, policy_blocked: bool = False, low_confidence: bool = False) -> ErrorClass:
  if policy_blocked:
    return ErrorClass.POLICY_BLOCKED
  if low_confidence:
    return ErrorClass.PERCEPTION_LOW_CONFIDENCE
  if isinstance(exc, httpx.TimeoutException):
    return ErrorClass.TRANSIENT
  if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
    return ErrorClass.TRANSIENT
  if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (408, 429):
    return ErrorClass.TRANSIENT
  if isinstance(exc, (ConnectionError, ConnectionRefusedError, ConnectionResetError, OSError)):
    return ErrorClass.TRANSIENT
  return ErrorClass.PERMANENT


def classify_attach_error(
  exc: Exception,
  adapter_type: AdapterType,
  *,
  classify_all_permanent: bool = False,
) -> ErrorClass:
  """Classify an attach error using policy flags instead of adapter-type branching.

  When classify_all_permanent is True (e.g., for web adapters), all attach
  errors are classified as PERMANENT regardless of the exception type.
  This preserves the previous behavior where web attach failures were
  always treated as permanent.
  """
  if classify_all_permanent:
    return ErrorClass.PERMANENT
  return classify_error(exc)


def decide_attach_recovery(
  error_class: ErrorClass,
  message: str,
  adapter_type: AdapterType,
) -> RecoveryDecision:
  return RecoveryDecision(
    error_class=error_class,
    action=RecoveryMode.STOP,
    reason=message,
  )


def decide_recovery(
  error_class: ErrorClass,
  retry_count: int,
  config: RecoveryConfig,
  *,
  classify_all_permanent: bool = False,
  fallback_to_mock: bool = False,
  fallback_to_manual: bool = True,
  message: str = "",
) -> RecoveryDecision:
  """Decide recovery action — retries aggressively, only stops after exhausting retries."""
  detail = message.strip() or "unknown error"
  if error_class == ErrorClass.POLICY_BLOCKED:
    return RecoveryDecision(
      error_class=error_class, action=RecoveryMode.RETRY, reason=f"policy blocked — retrying: {detail}",
      retry_after_ms=config.backoff_ms,
    )
  if error_class == ErrorClass.PERCEPTION_LOW_CONFIDENCE and retry_count < config.max_retries:
    return RecoveryDecision(
      error_class=error_class,
      action=RecoveryMode.RETRY,
      reason=f"low perception confidence: {detail}",
      retry_after_ms=config.backoff_ms * (retry_count + 1),
    )
  if error_class == ErrorClass.TRANSIENT and retry_count < config.max_retries:
    return RecoveryDecision(
      error_class=error_class,
      action=RecoveryMode.RETRY,
      reason=f"transient failure: {detail}",
      retry_after_ms=config.backoff_ms * (retry_count + 1),
    )
  if classify_all_permanent:
    return RecoveryDecision(error_class=error_class, action=RecoveryMode.STOP, reason=f"unrecoverable: {detail}")
  if fallback_to_mock:
    return RecoveryDecision(
      error_class=error_class, action=RecoveryMode.FALLBACK_MOCK, reason=f"exhausted retries — mock adapter: {detail}"
    )
  if fallback_to_manual:
    return RecoveryDecision(
      error_class=error_class, action=RecoveryMode.FALLBACK_MANUAL, reason=f"switching to manual mode: {detail}"
    )
  return RecoveryDecision(error_class=error_class, action=RecoveryMode.STOP, reason=f"unrecoverable: {detail}")

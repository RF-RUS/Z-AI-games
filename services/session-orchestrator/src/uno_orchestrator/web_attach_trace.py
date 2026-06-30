"""Temporary tracing helpers for web attach startup diagnostics propagation."""

from __future__ import annotations

import json
from typing import Any

from uno_schemas.adapter_web import AdapterMode, AttachWebAdapterResponse, WebStartupDiagnostics
from uno_shared.logging import get_logger

trace_logger = get_logger("orchestrator.web_attach_trace")


def parse_attach_web_http_response(body_text: str) -> AttachWebAdapterResponse | None:
  if not body_text.strip():
    return None
  try:
    return AttachWebAdapterResponse.model_validate_json(body_text)
  except Exception:
    pass
  try:
    raw = json.loads(body_text)
  except json.JSONDecodeError:
    return None
  if not isinstance(raw, dict):
    return None
  diagnostics_raw = raw.get("startup_diagnostics")
  if not diagnostics_raw:
    return None
  try:
    diagnostics = WebStartupDiagnostics.model_validate(diagnostics_raw)
  except Exception:
    return None
  mode_raw = raw.get("mode", AdapterMode.PLAYWRIGHT.value)
  try:
    mode = AdapterMode(mode_raw)
  except ValueError:
    mode = AdapterMode.PLAYWRIGHT
  return AttachWebAdapterResponse(
    adapter_id=raw.get("adapter_id"),
    session_id=str(raw.get("session_id") or "unknown"),
    attached=bool(raw.get("attached", False)),
    mode=mode,
    profile_id=str(raw.get("profile_id") or "unknown"),
    url=str(raw.get("url") or ""),
    message=str(raw.get("message") or ""),
    startup_diagnostics=diagnostics,
  )


def log_attach_diagnostics_checkpoint(checkpoint: int, session_id: str, **fields: Any) -> None:
  trace_logger.info(f"web_attach_diagnostics_checkpoint_{checkpoint}", session_id=session_id, **fields)

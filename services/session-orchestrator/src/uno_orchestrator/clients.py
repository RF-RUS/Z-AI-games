"""HTTP clients for downstream services."""

from __future__ import annotations

import os
from typing import Any

import httpx
from uno_adapter_web.startup import PLAYWRIGHT_ATTACH_HTTP_TIMEOUT_SEC
from uno_orchestrator.web_attach_trace import (
  log_attach_diagnostics_checkpoint,
  parse_attach_web_http_response,
)
from uno_schemas.adapter_web import (
  ActionExecutionRequest,
  ActionExecutionResult,
  AdapterEvidenceBundle,
  AdapterMode,
  AttachWebAdapterRequest,
  AttachWebAdapterResponse,
)
from uno_schemas.adapter_windows import (
  AttachWindowsAdapterRequest,
  AttachWindowsAdapterResponse,
  WindowsActionExecutionRequest,
  WindowsActionExecutionResult,
  WindowsEvidenceBundle,
)
from uno_schemas.api import SERVICE_PORTS
from uno_schemas.chat import ChatIntent, ChatMessage, ChatReply, ChatReplyRequest
from uno_schemas.decision import DecisionRequest, DecisionResult
from uno_schemas.game import DomainEvent, LegalAction
from uno_schemas.model import ModelInvocationRequest
from uno_schemas.orchestrator import AdapterBinding
from uno_schemas.perception import DomEvidence, Observation, ScreenshotFrame, UiEvidence
from uno_schemas.session import AdapterType


def _url(service: str) -> str:
  port = SERVICE_PORTS[service]
  host = os.getenv("UNO_SERVICE_HOST", "127.0.0.1")
  return f"http://{host}:{port}"


# ponytail: perceive/ground run the VLM synchronously (VLM_TIMEOUT_S, default
# 30s) plus a cold-start model load. The generic 15s client timeout is SHORTER
# than that, so the orchestrator would ReadTimeout before the model ever answers
# (the "GPU busy but AI didn't help" bug). Give VLM-bearing calls an HTTP budget
# well above VLM_TIMEOUT_S so the internal timeout always fires first. Env-tunable
# for slow/cold local models.
_VLM_TIMEOUT_S = float(os.getenv("VLM_TIMEOUT_S", "30"))
VLM_HTTP_TIMEOUT_SEC = float(os.getenv("VLM_HTTP_TIMEOUT_SEC", str(_VLM_TIMEOUT_S + 90.0)))


class ServiceClients:
  def __init__(self, timeout: float = 15.0) -> None:
    self.timeout = timeout
    self.perception = _url("perception-service")
    self.decision = _url("decision-service")
    self.policy = _url("policy-guard")
    self.core = _url("uno-core")
    self.replay = _url("state-replay-service")
    self.adapter_web = _url("adapter-web")
    self.adapter_windows = _url("adapter-windows")
    self.model_runtime = _url("model-runtime-service")
    self.chat_intent = _url("chat-intent-service")
    self.chat_response = _url("chat-response-service")

  async def create_game(self, player_names: list[str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.post(f"{self.core}/games", json={"player_names": player_names, "seed": 42})
      r.raise_for_status()
      return r.json()

  async def legal_actions(self, game_id: str) -> list[LegalAction]:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.get(f"{self.core}/games/{game_id}/legal-actions")
      r.raise_for_status()
      return [LegalAction.model_validate(a) for a in r.json()["actions"]]

  async def apply_action(self, game_id: str, action: LegalAction, session_id: str, correlation_id: str) -> dict:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.post(
        f"{self.core}/games/{game_id}/actions",
        json={"action": action.model_dump(mode="json"), "session_id": session_id},
        headers={"X-Correlation-Id": correlation_id},
      )
      r.raise_for_status()
      return r.json()

  async def perceive(
    self, session_id: str, dom: DomEvidence | None = None, ui: UiEvidence | None = None,
    screenshot: ScreenshotFrame | None = None,
  ) -> Observation:
    # VLM-bearing call — use the long budget so a slow/cold vision model isn't
    # cut off by the generic client timeout (see VLM_HTTP_TIMEOUT_SEC).
    async with httpx.AsyncClient(timeout=VLM_HTTP_TIMEOUT_SEC) as client:
      body: dict[str, Any] = {"session_id": session_id}
      if dom:
        body["dom"] = dom.model_dump(mode="json")
      if ui:
        body["ui"] = ui.model_dump(mode="json")
      if screenshot:
        body["screenshot"] = screenshot.model_dump(mode="json")
      r = await client.post(f"{self.perception}/perceive", json=body)
      r.raise_for_status()
      return Observation.model_validate(r.json())

  async def ground(
    self, action_type: str, screenshot_path: str, params: dict | None = None,
    game_type: str = "unknown", profile: dict | None = None, min_confidence: float = 0.5,
  ) -> dict:
    """Resolve a click point for a decided action via perception /ground.

    Returns the raw GroundResponse dict ({found, x, y, confidence, method, ...}).
    Best-effort: on any transport error returns a miss so a grounding outage
    degrades to an ungrounded click rather than stalling the tick.
    """
    body = {
      "action_type": action_type,
      "screenshot_path": screenshot_path,
      "params": params or {},
      "game_type": game_type,
      "profile": profile,
      "min_confidence": min_confidence,
    }
    try:
      async with httpx.AsyncClient(timeout=VLM_HTTP_TIMEOUT_SEC) as client:
        r = await client.post(f"{self.perception}/ground", json=body)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001 — grounding outage must not stall the tick
      return {"found": False, "method": "none", "reason": f"ground_error: {exc}"}

  async def decide(self, req: DecisionRequest) -> DecisionResult:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.post(f"{self.decision}/decide", json=req.model_dump(mode="json"))
      r.raise_for_status()
      return DecisionResult.model_validate(r.json())

  async def guard_decision(self, decision: DecisionResult, legal_actions: list[LegalAction], min_confidence: float) -> dict:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.post(
        f"{self.policy}/guard/decision",
        json={
          "decision": decision.model_dump(mode="json"),
          "legal_actions": [a.model_dump(mode="json") for a in legal_actions],
          "min_confidence": min_confidence,
        },
      )
      r.raise_for_status()
      return r.json()

  async def attach_web(self, req: AttachWebAdapterRequest) -> AttachWebAdapterResponse:
    timeout = PLAYWRIGHT_ATTACH_HTTP_TIMEOUT_SEC if req.mode == AdapterMode.PLAYWRIGHT else self.timeout
    async with httpx.AsyncClient(timeout=timeout) as client:
      r = await client.post(f"{self.adapter_web}/attach", json=req.model_dump(mode="json"))
      body_text = r.text
      log_attach_diagnostics_checkpoint(
        1,
        req.session_id,
        profile_id=req.profile_id,
        http_status=r.status_code,
        raw_body=body_text[:4000],
      )
      parsed = parse_attach_web_http_response(body_text)
      log_attach_diagnostics_checkpoint(
        2,
        req.session_id,
        parsed_attached=parsed.attached if parsed else None,
        failed_stage=(parsed.startup_diagnostics.failed_stage if parsed and parsed.startup_diagnostics else None),
        has_diagnostics=bool(parsed and parsed.startup_diagnostics),
      )
      if parsed is not None:
        return parsed
      r.raise_for_status()
      raise RuntimeError("unreachable attach_web response path")

  async def attach_windows(self, req: AttachWindowsAdapterRequest) -> AttachWindowsAdapterResponse:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.post(f"{self.adapter_windows}/attach", json=req.model_dump(mode="json"))
      r.raise_for_status()
      return AttachWindowsAdapterResponse.model_validate(r.json())

  async def web_evidence(self, adapter_id: str, correlation_id: str) -> AdapterEvidenceBundle:
    timeout = PLAYWRIGHT_ATTACH_HTTP_TIMEOUT_SEC
    async with httpx.AsyncClient(timeout=timeout) as client:
      r = await client.get(f"{self.adapter_web}/adapters/{adapter_id}/evidence", params={"correlation_id": correlation_id})
      r.raise_for_status()
      return AdapterEvidenceBundle.model_validate(r.json())

  async def windows_evidence(self, adapter_id: str, correlation_id: str) -> WindowsEvidenceBundle:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.get(f"{self.adapter_windows}/adapters/{adapter_id}/evidence", params={"correlation_id": correlation_id})
      r.raise_for_status()
      return WindowsEvidenceBundle.model_validate(r.json())

  async def web_execute(self, adapter_id: str, req: ActionExecutionRequest, correlation_id: str) -> ActionExecutionResult:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.post(
        f"{self.adapter_web}/adapters/{adapter_id}/actions",
        params={"correlation_id": correlation_id},
        json=req.model_dump(mode="json"),
      )
      r.raise_for_status()
      return ActionExecutionResult.model_validate(r.json())

  async def windows_execute(
    self, adapter_id: str, req: WindowsActionExecutionRequest, correlation_id: str
  ) -> WindowsActionExecutionResult:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.post(
        f"{self.adapter_windows}/adapters/{adapter_id}/actions",
        params={"correlation_id": correlation_id},
        json=req.model_dump(mode="json"),
      )
      r.raise_for_status()
      return WindowsActionExecutionResult.model_validate(r.json())

  async def detach_web(self, adapter_id: str) -> None:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      await client.post(f"{self.adapter_web}/adapters/{adapter_id}/detach")

  async def detach_windows(self, adapter_id: str) -> None:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      await client.post(f"{self.adapter_windows}/adapters/{adapter_id}/detach")

  async def replay_event(self, replay_id: str, event: DomainEvent) -> None:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      await client.post(f"{self.replay}/replays/{replay_id}/events", json=event.model_dump(mode="json"))

  async def replay_observation(self, replay_id: str, bundle: dict) -> None:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      await client.post(f"{self.replay}/replays/{replay_id}/observations", json=bundle)

  async def model_invoke(self, req: ModelInvocationRequest) -> dict:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.post(f"{self.model_runtime}/invoke", json=req.model_dump(mode="json"))
      r.raise_for_status()
      return r.json()

  async def chat_detect_intent(
    self, messages: list[ChatMessage], game_type: str = "unknown", use_model: bool = False,
  ) -> ChatIntent | None:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.post(f"{self.chat_intent}/detect", json={
        "messages": [m.model_dump(mode="json") for m in messages],
        "use_model": use_model,
        "game_type": game_type,
      })
      r.raise_for_status()
      data = r.json()
      return ChatIntent.model_validate(data) if data else None

  async def chat_reply(
    self, session_id: str, intent: ChatIntent, recent_messages: list[ChatMessage],
    use_model: bool = False, correlation_id: str = "",
  ) -> ChatReply:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.post(f"{self.chat_response}/reply", json=ChatReplyRequest(
        session_id=session_id,
        intent=intent,
        recent_messages=recent_messages,
        use_model=use_model,
        correlation_id=correlation_id,
      ).model_dump(mode="json"))
      r.raise_for_status()
      return ChatReply.model_validate(r.json())

  async def send_bot_message(
    self, session_id: str, text: str, correlation_id: str = "",
  ) -> ChatMessage:
    """Send a bot-authored message to the operator chat."""
    from time import time as _time
    msg = ChatMessage(
      message_id=f"bot-{correlation_id[:8]}",
      sender="bot",
      text=text,
      timestamp_ms=int(_time() * 1000),
      is_bot=True,
    )
    return msg


def binding_for(adapter_type: AdapterType, adapter_id: str, profile_id: str) -> AdapterBinding:
  return AdapterBinding(adapter_type=adapter_type, adapter_id=adapter_id, attached=True, profile_id=profile_id, healthy=True)

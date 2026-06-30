"""In-process HTTP clients for tests and local evaluation (ASGI transport)."""

from httpx import ASGITransport, AsyncClient
from uno_adapter_web.api import app as web_app
from uno_core.api import app as core_app
from uno_decision.api import app as decision_app
from uno_model_runtime.api import app as model_runtime_app
from uno_orchestrator.clients import ServiceClients
from uno_perception.api import app as perception_app
from uno_policy.api import app as policy_app
from uno_schemas.adapter_web import ActionExecutionRequest, AttachWebAdapterRequest
from uno_schemas.decision import DecisionRequest, DecisionResult
from uno_schemas.game import LegalAction
from uno_schemas.perception import Observation
from uno_shared.adapter_protocol import (
    AdapterRetryPolicy,
    GenericActionRequest,
    GenericActionResult,
    GenericAttachRequest,
    GenericAttachResponse,
    GenericEvidenceBundle,
)
from uno_shared.adapter_registry import AdapterRegistry, set_adapter_registry


class InProcessAdapterClient:
    """In-process adapter client using ASGI transport."""

    def __init__(self, adapter_type: str, app):
        self.adapter_type = adapter_type
        self._app = app

    def _transport(self):
        return AsyncClient(transport=ASGITransport(app=self._app), base_url="http://test", timeout=30.0)

    def normalize_attach_request(
        self,
        session_id: str,
        profile_id: str,
        *,
        target_url: str | None = None,
        window_title: str | None = None,
        window_handle: int | None = None,
        window_pid: int | None = None,
        launch_test_target: bool = False,
        use_real_backend: bool = True,
        cdp_url: str | None = None,
    ) -> GenericAttachRequest:
        from uno_shared.adapter_registry import GenericAdapterClient
        delegate = GenericAdapterClient(self.adapter_type, "http://noop")
        return delegate.normalize_attach_request(
            session_id=session_id,
            profile_id=profile_id,
            target_url=target_url,
            window_title=window_title,
            window_handle=window_handle,
            window_pid=window_pid,
            launch_test_target=launch_test_target,
            use_real_backend=use_real_backend,
            cdp_url=cdp_url,
        )

    def get_retry_policy(self) -> AdapterRetryPolicy:
        from uno_shared.adapter_registry import GenericAdapterClient
        delegate = GenericAdapterClient(self.adapter_type, "http://noop")
        return delegate.get_retry_policy()

    def map_action(
        self,
        action_type: str,
        profile_id: str = "local-mock-uno",
        card_color: str | None = None,
        card_value: str | None = None,
        player_id: str | None = None,
        payload: dict | None = None,
    ):
        from uno_shared.adapter_registry import GenericAdapterClient
        delegate = GenericAdapterClient(self.adapter_type, "http://noop")
        return delegate.map_action(action_type, profile_id, card_color, card_value, player_id, payload=payload)

    async def attach(self, request: GenericAttachRequest) -> GenericAttachResponse:
        body = {
            "session_id": request.session_id,
            "profile_id": request.profile_id,
            "url": request.target_url,
            "mode": request.extra.get("mode", "mock"),
            "headless": request.extra.get("headless", True),
            "record_trace": request.extra.get("record_trace", False),
        }
        if request.extra.get("cdp_url"):
            body["cdp_url"] = request.extra["cdp_url"]
        async with self._transport() as c:
            r = await c.post("/attach", json=body)
            r.raise_for_status()
            data = r.json()
        return GenericAttachResponse(
            adapter_id=data.get("adapter_id"),
            session_id=data.get("session_id", request.session_id),
            attached=data.get("attached", False),
            message=data.get("message", ""),
            extra=data,
        )

    async def detach(self, adapter_id: str) -> None:
        async with self._transport() as c:
            await c.post(f"/adapters/{adapter_id}/detach")

    async def capture_evidence(
        self, adapter_id: str, correlation_id: str | None = None
    ) -> GenericEvidenceBundle:
        async with self._transport() as c:
            params = {}
            if correlation_id:
                params["correlation_id"] = correlation_id
            r = await c.get(f"/adapters/{adapter_id}/evidence", params=params)
            r.raise_for_status()
            data = r.json()
        return GenericEvidenceBundle(
            adapter_id=adapter_id,
            session_id=data.get("session_id", ""),
            dom_evidence=data.get("dom_evidence"),
            ui_evidence=data.get("ui_evidence"),
            screenshot_path=data.get("screenshot", {}).get("path") if isinstance(data.get("screenshot"), dict) else None,
            correlation_id=data.get("correlation_id"),
            extra=data,
        )

    async def execute_action(
        self,
        adapter_id: str,
        action: GenericActionRequest,
        correlation_id: str | None = None,
    ) -> GenericActionResult:
        body = {
            "action_type": action.action_type,
            "selector": action.selector,
            "selector_key": action.selector_key,
            "domain_action": action.domain_action,
            "text": action.text,
            "key": action.key,
            "timeout_ms": action.timeout_ms,
        }
        async with self._transport() as c:
            params = {}
            if correlation_id:
                params["correlation_id"] = correlation_id
            r = await c.post(f"/adapters/{adapter_id}/actions", params=params, json=body)
            r.raise_for_status()
            data = r.json()
        return GenericActionResult(
            success=data.get("success", False),
            action_type=data.get("action_type", action.action_type),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0),
            screenshot_path=data.get("screenshot_path"),
            extra=data,
        )

    async def list_profiles(self) -> list[dict]:
        async with self._transport() as c:
            r = await c.get("/profiles")
            r.raise_for_status()
            return r.json()

    async def load_profile(self, profile_id: str) -> dict:
        async with self._transport() as c:
            r = await c.get(f"/profiles/{profile_id}")
            r.raise_for_status()
            return r.json()


def setup_in_process_adapter_registry() -> None:
    """Register in-process adapter clients for testing."""
    registry = AdapterRegistry()
    web_client = InProcessAdapterClient("web", web_app)
    registry.register("web", web_client)
    mock_client = InProcessAdapterClient("mock", web_app)
    registry.register("mock", mock_client)
    set_adapter_registry(registry)


class InProcessClients(ServiceClients):
  def _transport(self, app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30.0)

  async def create_game(self, player_names):
    async with self._transport(core_app) as c:
      r = await c.post("/games", json={"player_names": player_names, "seed": 42})
      r.raise_for_status()
      return r.json()

  async def legal_actions(self, game_id: str):
    async with self._transport(core_app) as c:
      r = await c.get(f"/games/{game_id}/legal-actions")
      r.raise_for_status()
      return [LegalAction.model_validate(a) for a in r.json()["actions"]]

  async def apply_action(self, game_id, action, session_id, correlation_id):
    async with self._transport(core_app) as c:
      r = await c.post(f"/games/{game_id}/actions", json={"action": action.model_dump(mode="json"), "session_id": session_id})
      r.raise_for_status()
      return r.json()

  async def perceive(self, session_id, dom=None, ui=None, screenshot=None):
    async with self._transport(perception_app) as c:
      body = {"session_id": session_id}
      if dom:
        body["dom"] = dom.model_dump(mode="json")
      if ui:
        body["ui"] = ui.model_dump(mode="json")
      if screenshot:
        body["screenshot"] = screenshot.model_dump(mode="json")
      r = await c.post("/perceive", json=body)
      r.raise_for_status()
      return Observation.model_validate(r.json())

  async def decide(self, req: DecisionRequest) -> DecisionResult:
    from uno_decision.policy import decide_heuristic, decide_random
    if req.strategy_id.value == "random":
      return decide_random(req)
    if req.model_profile_id and req.use_model_assist:
      try:
        async with self._transport(model_runtime_app) as c:
          r = await c.post("/invoke", json={
            "context": {"use_case": "policy_advice", "correlation_id": req.correlation_id, "session_id": req.session_id},
            "profile_id": req.model_profile_id,
            "prompt_id": "policy_advice",
            "variables": {
              "game_state": str(req.observation) if req.observation else "",
              "legal_actions": "\n".join(f"{i}: {getattr(a, 'action_type', '?')}" for i, a in enumerate(req.legal_actions)),
              "strategy_context": f"Game type: {req.game_type or 'unknown'}",
            },
            "expect_json": True,
          })
          r.raise_for_status()
          result = r.json()
        structured = result.get("structured") or {}
        action_index = structured.get("action_index", 0)
        confidence = structured.get("confidence", 0.5)
        reasoning = structured.get("reasoning", "model recommendation")
        if 0 <= action_index < len(req.legal_actions):
          chosen = req.legal_actions[action_index]
          from uno_schemas.decision import DecisionCandidate, DecisionExplanation
          return DecisionResult(
            chosen_action=chosen,
            confidence=min(0.95, confidence),
            explanation=DecisionExplanation(
              summary=f"Model chose {getattr(chosen, 'action_type', '?')}: {reasoning}",
              candidates=[DecisionCandidate(action=a, score=confidence if i == action_index else 0.3, reason=reasoning if i == action_index else "not selected") for i, a in enumerate(req.legal_actions[:5])],
              model_used=True,
              model_id=result.get("model_id"),
            ),
            correlation_id=req.correlation_id,
          )
      except Exception:
        pass
    return decide_heuristic(req)

  async def guard_decision(self, decision, legal_actions, min_confidence):
    async with self._transport(policy_app) as c:
      r = await c.post("/guard/decision", json={
        "decision": decision.model_dump(mode="json"),
        "legal_actions": [a.model_dump(mode="json") for a in legal_actions],
        "min_confidence": min_confidence,
      })
      r.raise_for_status()
      return r.json()

  async def attach_web(self, req: AttachWebAdapterRequest):
    from uno_orchestrator.web_attach_trace import (
        log_attach_diagnostics_checkpoint,
        parse_attach_web_http_response,
    )
    from uno_schemas.adapter_web import AttachWebAdapterResponse
    async with self._transport(web_app) as c:
      r = await c.post("/attach", json=req.model_dump(mode="json"))
      log_attach_diagnostics_checkpoint(
        1,
        req.session_id,
        profile_id=req.profile_id,
        http_status=r.status_code,
        raw_body=r.text[:4000],
      )
      parsed = parse_attach_web_http_response(r.text)
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
      return AttachWebAdapterResponse.model_validate(r.json())

  async def web_evidence(self, adapter_id, correlation_id):
    from uno_schemas.adapter_web import AdapterEvidenceBundle
    async with self._transport(web_app) as c:
      r = await c.get(f"/adapters/{adapter_id}/evidence", params={"correlation_id": correlation_id})
      r.raise_for_status()
      return AdapterEvidenceBundle.model_validate(r.json())

  async def web_execute(self, adapter_id, req: ActionExecutionRequest, correlation_id):
    from uno_schemas.adapter_web import ActionExecutionResult
    async with self._transport(web_app) as c:
      r = await c.post(f"/adapters/{adapter_id}/actions", params={"correlation_id": correlation_id}, json=req.model_dump(mode="json"))
      r.raise_for_status()
      return ActionExecutionResult.model_validate(r.json())

  async def detach_web(self, adapter_id):
    async with self._transport(web_app) as c:
      await c.post(f"/adapters/{adapter_id}/detach")

  async def replay_event(self, replay_id, event):
    return None

  async def replay_observation(self, replay_id, bundle):
    return None

  async def model_invoke(self, req):
    return {"text": "{}", "structured": {"parse_success": True}}

  async def send_bot_message(self, session_id, text, correlation_id=""):
    from time import time as _time
    from uno_schemas.chat import ChatMessage
    return ChatMessage(
      message_id=f"bot-{correlation_id[:8]}", sender="bot", text=text,
      timestamp_ms=int(_time() * 1000), is_bot=True,
    )

  async def chat_detect_intent(self, messages, game_type="unknown", use_model=False):
    return None

  async def chat_reply(self, session_id, intent, recent_messages, use_model=False, correlation_id=""):
    from uno_schemas.chat import ChatReply
    return ChatReply(text="ok", approved=True, source="mock", confidence=1.0, correlation_id=correlation_id)

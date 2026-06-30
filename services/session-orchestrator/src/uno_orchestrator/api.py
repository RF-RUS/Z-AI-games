import os

os.environ.setdefault("AGENT_SCREENSHOT_TRACE", "1")
os.environ.setdefault("AGENT_SCREENSHOT_TRACE_DIR", "services\\artifacts")

from fastapi import FastAPI, HTTPException
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_orchestrator.state_machine import InvalidTransition
from uno_schemas.orchestrator import (
  AttachAdapterBody,
  FlowControlResponse,
  OrchestratorStatus,
  SessionDetail,
  SessionSpec,
)
from uno_schemas.session import AdapterType, SessionConfig, SessionState
from uno_shared.service_app import ServiceApp

orchestrator = SessionOrchestrator()
svc = ServiceApp("session-orchestrator", description="Operator session lifecycle and flow control")
svc.set_health_detail("active_sessions", 0)
app: FastAPI = svc.create_app()


@app.post("/sessions", response_model=SessionDetail, tags=["sessions"])
async def create_session(spec: SessionSpec) -> SessionDetail:
  return await orchestrator.create_session_with_game(spec)


@app.get("/sessions", response_model=list[SessionDetail], tags=["sessions"])
async def list_sessions() -> list[SessionDetail]:
  return orchestrator.list_sessions()


@app.get("/sessions/{session_id}", response_model=SessionDetail, tags=["sessions"])
async def get_session(session_id: str) -> SessionDetail:
  s = orchestrator.get_session(session_id)
  if not s:
    raise HTTPException(404, "session not found")
  return s


@app.post("/sessions/{session_id}/attach-adapter", response_model=SessionDetail, tags=["sessions"])
async def attach_adapter(session_id: str, body: AttachAdapterBody) -> SessionDetail:
  try:
    return await orchestrator.attach_adapter(session_id, body)
  except KeyError:
    raise HTTPException(404, "session not found") from None
  except Exception as exc:
    detail = orchestrator.get_session(session_id)
    if detail is not None:
      raise HTTPException(
        502,
        detail={
          "message": str(exc),
          "session": detail.model_dump(mode="json"),
        },
      ) from exc
    raise HTTPException(502, str(exc)) from exc


@app.post("/sessions/{session_id}/detach-adapter", response_model=SessionDetail, tags=["sessions"])
async def detach_adapter(session_id: str, adapter_type: AdapterType | None = None) -> SessionDetail:
  try:
    return await orchestrator.detach_adapter(session_id, adapter_type)
  except KeyError:
    raise HTTPException(404, "session not found") from None


@app.post("/sessions/{session_id}/start", response_model=FlowControlResponse, tags=["flow"])
async def start_session(session_id: str) -> FlowControlResponse:
  try:
    return await orchestrator.start(session_id)
  except KeyError:
    raise HTTPException(404, "session not found") from None
  except InvalidTransition as exc:
    raise HTTPException(409, str(exc)) from exc


@app.post("/sessions/{session_id}/pause", response_model=FlowControlResponse, tags=["flow"])
async def pause_session(session_id: str) -> FlowControlResponse:
  try:
    return await orchestrator.pause(session_id)
  except KeyError:
    raise HTTPException(404, "session not found") from None
  except InvalidTransition as exc:
    raise HTTPException(409, str(exc)) from exc


@app.post("/sessions/{session_id}/resume", response_model=FlowControlResponse, tags=["flow"])
async def resume_session(session_id: str) -> FlowControlResponse:
  try:
    return await orchestrator.resume(session_id)
  except KeyError:
    raise HTTPException(404, "session not found") from None
  except InvalidTransition as exc:
    raise HTTPException(409, str(exc)) from exc


@app.post("/sessions/{session_id}/stop", response_model=FlowControlResponse, tags=["flow"])
async def stop_session(session_id: str) -> FlowControlResponse:
  try:
    return await orchestrator.stop(session_id)
  except KeyError:
    raise HTTPException(404, "session not found") from None
  except InvalidTransition as exc:
    raise HTTPException(409, str(exc)) from exc


@app.get("/sessions/{session_id}/status", response_model=OrchestratorStatus, tags=["sessions"])
async def session_status(session_id: str) -> OrchestratorStatus:
  s = orchestrator.status(session_id)
  if not s:
    raise HTTPException(404, "session not found")
  return s


@app.get("/sessions/{session_id}/steps", tags=["sessions"])
async def session_steps(session_id: str) -> list:
  steps = orchestrator.get_steps(session_id)
  if orchestrator.get_session(session_id) is None:
    raise HTTPException(404, "session not found")
  return [s.model_dump(mode="json") for s in steps]


@app.post("/sessions/{session_id}/tick", tags=["sessions"])
async def tick(session_id: str, dom_snapshot: dict | None = None) -> dict:
  if not orchestrator.get_session(session_id):
    raise HTTPException(404, "session not found")
  return await orchestrator.run_tick(session_id, dom_snapshot)


@app.get("/trace/debug", tags=["trace"])
async def trace_debug() -> dict:
  """Check trace env vars INSIDE the session-orchestrator process."""
  import os

  from uno_adapter_web.agent_trace import TraceManager
  base = TraceManager.base_dir()
  return {
    "env_trace_enabled": os.environ.get("AGENT_SCREENSHOT_TRACE", "NOT_SET"),
    "env_trace_dir": os.environ.get("AGENT_SCREENSHOT_TRACE_DIR", "NOT_SET"),
    "trace_enabled": TraceManager.enabled(),
    "base_dir": str(base),
    "base_dir_exists": base.exists(),
  }


@app.get("/sessions/{session_id}/chat", tags=["sessions"])
async def session_chat(session_id: str) -> list:
  """Get bot chat messages for a session."""
  session = orchestrator._sessions.get(session_id)
  if not session:
    raise HTTPException(404, "session not found")
  return [m.model_dump(mode="json") for m in session.chat_messages]


@app.get("/sessions/{session_id}/screenshot", tags=["sessions"])
async def session_screenshot(session_id: str):
  """Get latest screenshot from adapter evidence for a session.

  Proxies the screenshot from the adapter, supporting both web and windows adapters.
  Returns base64-encoded image data.
  """
  import httpx
  from fastapi.responses import JSONResponse

  sess = orchestrator.get_session(session_id)
  if not sess:
    raise HTTPException(404, "session not found")

  # Find adapter with screenshot
  for b in sess.adapter_bindings:
    if not b.attached or not b.adapter_id:
      continue

    adapter_type = b.adapter_type
    adapter_id = b.adapter_id

    try:
      if adapter_type == "windows":
        url = f"http://127.0.0.1:8105/adapters/{adapter_id}/evidence"
      elif adapter_type in ("web", "mock"):
        url = f"http://127.0.0.1:8104/adapters/{adapter_id}/evidence"
      else:
        continue

      async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        if r.status_code != 200:
          continue
        evidence = r.json()
        screenshot = evidence.get("screenshot")
        if screenshot and screenshot.get("data_base64"):
          return JSONResponse({
            "session_id": session_id,
            "adapter_type": adapter_type,
            "width": screenshot.get("width"),
            "height": screenshot.get("height"),
            "path": screenshot.get("path"),
            "data_base64": screenshot.get("data_base64"),
          })
    except Exception:
      continue

  raise HTTPException(404, "no screenshot available for this session")


# Legacy
@app.post("/sessions/legacy", response_model=SessionState, tags=["sessions"])
async def create_session_legacy(config: SessionConfig) -> SessionState:
  return orchestrator.create_session_legacy(config)


def main() -> None:
  import os

  import uvicorn
  os.environ.setdefault("AGENT_SCREENSHOT_TRACE", "1")
  os.environ.setdefault("AGENT_SCREENSHOT_TRACE_DIR", "services\\artifacts")
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_orchestrator.api:app", host="127.0.0.1", port=SERVICE_PORTS["session-orchestrator"])

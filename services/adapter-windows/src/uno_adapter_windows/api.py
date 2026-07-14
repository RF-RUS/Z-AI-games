import asyncio
import time
from collections import defaultdict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from uno_adapter_windows.profiles import list_profiles, load_profile
from uno_adapter_windows.registry import attach_adapter, get_adapter
from uno_adapter_windows.runtime import is_windows, list_window_candidates, pywinauto_available
from uno_schemas.adapter_windows import (
  AttachWindowsAdapterRequest,
  AttachWindowsAdapterResponse,
  OperatorPreviewState,
  PreviewFrameKind,
  WindowCandidate,
  WindowsActionExecutionRequest,
  WindowsActionExecutionResult,
  WindowsAdapterProfile,
  WindowsEvidenceBundle,
)
from uno_shared.service_app import ServiceApp

svc = ServiceApp("adapter-windows", description="Windows UI Automation adapter")
svc.set_health_detail("pywinauto_available", pywinauto_available())
svc.set_health_detail("is_windows", is_windows())
svc.set_health_detail("profiles_loaded", len(list_profiles()))
app: FastAPI = svc.create_app()

_action_timestamps: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 1.0
_RATE_LIMIT_MAX = 10
# ponytail: adapter-side execution deadline, must stay below the orchestrator's
# HTTP read timeout (clients.py self.timeout=15s) so a hung click/UIA walk comes
# back as a structured failure instead of a ReadTimeout that stalls the session.
_EXECUTE_DEADLINE_S = 12.0


@app.get("/profiles", response_model=list[WindowsAdapterProfile], tags=["profiles"])
async def get_profiles() -> list[WindowsAdapterProfile]:
  return list_profiles()


@app.get("/profiles/{profile_id}", response_model=WindowsAdapterProfile, tags=["profiles"])
async def get_profile(profile_id: str) -> WindowsAdapterProfile:
  try:
    return load_profile(profile_id)
  except FileNotFoundError:
    raise HTTPException(404, "profile not found") from None


@app.get("/windows/candidates", response_model=list[WindowCandidate], tags=["windows"])
async def window_candidates() -> list[WindowCandidate]:
  return await list_window_candidates()


@app.post("/attach", response_model=AttachWindowsAdapterResponse, tags=["adapter"])
async def attach(req: AttachWindowsAdapterRequest) -> AttachWindowsAdapterResponse:
  return await attach_adapter(req)


@app.get("/adapters/{adapter_id}/preview", response_model=OperatorPreviewState, tags=["adapter"])
async def get_preview(adapter_id: str) -> OperatorPreviewState:
  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  if hasattr(a, "refresh_attach_diagnostics"):
    await a.refresh_attach_diagnostics()
  if hasattr(a, "get_preview_state"):
    return a.get_preview_state()
  return OperatorPreviewState(
    adapter_id=adapter_id,
    frame_kind=PreviewFrameKind.NONE,
    message="preview not available for this adapter mode",
  )


@app.get("/adapters/{adapter_id}/ui-tree", tags=["adapter"])
async def ui_tree(adapter_id: str) -> dict:
  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  return await a.capture_ui_tree()


@app.get("/adapters/{adapter_id}/evidence", response_model=WindowsEvidenceBundle, tags=["adapter"])
async def get_evidence(adapter_id: str, correlation_id: str | None = None) -> WindowsEvidenceBundle:
  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  bundle = await a.capture_evidence(adapter_id)
  bundle.correlation_id = correlation_id
  return bundle


@app.post("/adapters/{adapter_id}/actions", response_model=WindowsActionExecutionResult, tags=["adapter"])
async def execute_action(
  adapter_id: str, req: WindowsActionExecutionRequest, correlation_id: str | None = None
) -> WindowsActionExecutionResult:
  now = time.monotonic()
  timestamps = _action_timestamps[adapter_id]
  timestamps[:] = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
  if len(timestamps) >= _RATE_LIMIT_MAX:
    raise HTTPException(429, "rate limit exceeded")
  timestamps.append(now)
  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  try:
    return await asyncio.wait_for(a.execute(req, correlation_id), timeout=_EXECUTE_DEADLINE_S)
  except TimeoutError:
    # Never let a hung execute bubble up as a ReadTimeout — return a structured
    # failure so the orchestrator's verification records "delivery failed" cleanly.
    return WindowsActionExecutionResult(
      success=False,
      action_type=req.action_type,
      error=f"execution exceeded {_EXECUTE_DEADLINE_S:.0f}s deadline",
      correlation_id=correlation_id,
      uncertain=True,
    )


@app.get("/adapters/{adapter_id}/screenshot", tags=["adapter"])
async def get_screenshot(adapter_id: str):
  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  bundle = await a.capture_evidence(adapter_id)
  if not bundle.screenshot or not bundle.screenshot.path:
    raise HTTPException(404, "no screenshot")
  return FileResponse(bundle.screenshot.path, media_type="image/png")


@app.get("/adapters/{adapter_id}/calibration", tags=["adapter"])
async def get_calibration(adapter_id: str) -> dict:
  """Return window vs client bounds for coordinate-space calibration."""
  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  window_bounds = None
  client_bounds = None

  # Get window handle
  handle = None
  if hasattr(a, "window_handle") and a.window_handle:
    handle = a.window_handle
  elif hasattr(a, "_window") and a._window and hasattr(a._window, "handle"):
    try:
      handle = int(a._window.handle)
    except Exception:
      pass

  # Get window rect (screen coordinates)
  if hasattr(a, "_state") and a._state.attachment:
    window_bounds = a._state.attachment.bounds
  if not window_bounds and handle:
    try:
      import ctypes
      from ctypes import wintypes
      rect = wintypes.RECT()
      if ctypes.windll.user32.GetWindowRect(handle, ctypes.byref(rect)):
        window_bounds = {"left": float(rect.left), "top": float(rect.top),
                         "right": float(rect.right), "bottom": float(rect.bottom)}
    except Exception:
      pass

  # Get client rect (local coords → convert to screen coords)
  if handle:
    try:
      import ctypes
      from ctypes import wintypes
      client_rect_local = wintypes.RECT()
      ctypes.windll.user32.GetClientRect(handle, ctypes.byref(client_rect_local))
      wl = window_bounds["left"] if window_bounds else 0
      wt = window_bounds["top"] if window_bounds else 0
      client_bounds = {
        "left": wl + float(client_rect_local.left),
        "top": wt + float(client_rect_local.top),
        "right": wl + float(client_rect_local.right),
        "bottom": wt + float(client_rect_local.bottom),
      }
    except Exception:
      pass

  offset = None
  if window_bounds and client_bounds:
    offset = {
      "left_delta": round(client_bounds["left"] - window_bounds["left"], 1),
      "top_delta": round(client_bounds["top"] - window_bounds["top"], 1),
      "right_delta": round(window_bounds["right"] - client_bounds["right"], 1),
      "bottom_delta": round(window_bounds["bottom"] - client_bounds["bottom"], 1),
      "description": "title_bar_and_border_offsets",
    }

  return {
    "adapter_id": adapter_id,
    "window_bounds": window_bounds,
    "client_bounds": client_bounds,
    "offset": offset,
    "coordinate_space": "client_area" if client_bounds else "window",
  }


@app.post("/adapters/{adapter_id}/capture-fixture", tags=["adapter"])
async def capture_fixture(adapter_id: str, output_dir: str = "tests/fixtures/windows_adapter") -> dict:
  from pathlib import Path
  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  bundle = await a.capture_evidence(adapter_id)
  out = Path(output_dir)
  out.mkdir(parents=True, exist_ok=True)
  fid = bundle.window_snapshot.profile_id or "capture"

  (out / f"{fid}_window_snapshot.json").write_text(bundle.window_snapshot.model_dump_json(indent=2), encoding="utf-8")
  (out / f"{fid}_ui_evidence.json").write_text(bundle.ui_evidence.model_dump_json(indent=2), encoding="utf-8")

  screenshot = None
  if bundle.screenshot and bundle.screenshot.path:
    import shutil
    screenshot = out / f"{fid}_screenshot.png"
    shutil.copy(bundle.screenshot.path, screenshot)

  return {
    "fixture_id": fid,
    "window_snapshot": str(out / f"{fid}_window_snapshot.json"),
    "ui_evidence": str(out / f"{fid}_ui_evidence.json"),
    "screenshot": str(screenshot) if screenshot else None,
  }


@app.post("/adapters/{adapter_id}/detach", tags=["adapter"])
async def detach(adapter_id: str) -> dict:
  from uno_adapter_windows.registry import _adapters
  a = _adapters.pop(adapter_id, None)
  if a:
    await a.detach()
  return {"detached": True}


@app.get("/zones/{game_id}", tags=["zones"])
async def get_learned_zones(game_id: str) -> list[dict]:
  """Inspect learned zones for a game — useful for debugging action memory."""
  from uno_adapter_windows.registry import _zone_store
  return _zone_store.inspect(game_id)


@app.delete("/zones/{game_id}", tags=["zones"])
async def reset_learned_zones(game_id: str) -> dict:
  """Reset all learned zones for a game."""
  from uno_adapter_windows.registry import _zone_store
  zones = _zone_store.list_zones(game_id)
  for z in zones:
    _zone_store.forget(game_id, z.zone_id)
  return {"reset": True, "zones_deleted": len(zones)}


@app.get("/pywinauto/check", tags=["adapter"])
async def pywinauto_check() -> dict:
  return {
    "available": pywinauto_available(),
    "is_windows": is_windows(),
    "profiles": [p.profile_id for p in list_profiles()],
  }


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_adapter_windows.api:app", host="127.0.0.1", port=SERVICE_PORTS["adapter-windows"])

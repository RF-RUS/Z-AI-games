import time
from collections import defaultdict
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from uno_adapter_web.health_store import load_reports, to_history_entry
from uno_adapter_web.navigation_diagnostics import check_url_reachability
from uno_adapter_web.profile_alerts import build_summary, evaluate_alerts
from uno_adapter_web.profile_health import run_playwright_health_check
from uno_adapter_web.profile_metrics import metrics_export
from uno_adapter_web.profiles import list_profiles, load_profile
from uno_adapter_web.registry import attach_adapter, get_adapter
from uno_adapter_web.runtime import playwright_available
from uno_schemas.adapter_web import (
  ActionExecutionRequest,
  ActionExecutionResult,
  AdapterEvidenceBundle,
  AttachWebAdapterRequest,
  AttachWebAdapterResponse,
  ProfileHealthAlert,
  ProfileHealthHistoryEntry,
  ProfileHealthReport,
  ProfileHealthSummary,
  WebAdapterProfile,
)
from uno_shared.service_app import ServiceApp

svc = ServiceApp("adapter-web", description="Playwright web adapter with profile-driven extraction")
svc.set_health_detail("playwright_available", playwright_available())
svc.set_health_detail("profiles_loaded", len(list_profiles()))
app: FastAPI = svc.create_app()

_action_timestamps: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 1.0
_RATE_LIMIT_MAX = 10


@app.get("/profiles", response_model=list[WebAdapterProfile], tags=["profiles"])
async def get_profiles() -> list[WebAdapterProfile]:
  return list_profiles()


@app.get("/profiles/{profile_id}", response_model=WebAdapterProfile, tags=["profiles"])
async def get_profile(profile_id: str) -> WebAdapterProfile:
  try:
    return load_profile(profile_id)
  except FileNotFoundError:
    raise HTTPException(404, "profile not found") from None


@app.post("/attach", response_model=AttachWebAdapterResponse, tags=["adapter"])
async def attach(req: AttachWebAdapterRequest) -> AttachWebAdapterResponse:
  return await attach_adapter(req)


@app.get("/network/check", tags=["adapter"])
async def network_check(url: str) -> dict:
  result = await check_url_reachability(url)
  return result.model_dump(mode="json")


@app.get("/cdp/tabs", tags=["cdp"])
async def list_cdp_tabs(cdp_url: str = "http://127.0.0.1:9222") -> list[dict]:
  """List open Chrome tabs via CDP /json endpoint."""
  import httpx
  try:
    async with httpx.AsyncClient(timeout=5.0) as c:
      r = await c.get(f"{cdp_url}/json")
      r.raise_for_status()
      tabs = r.json()
      return [
        {
          "title": tab.get("title", ""),
          "url": tab.get("url", ""),
          "id": tab.get("id", ""),
          "web_socket_debug_url": tab.get("webSocketDebuggerUrl", ""),
        }
        for tab in tabs
        if tab.get("type") == "page"
      ]
  except Exception:
    return []


@app.get("/cdp/check", tags=["cdp"])
async def check_cdp_port(cdp_url: str = "http://127.0.0.1:9222") -> dict:
  """Check if Chrome CDP debug port is available."""
  import httpx
  try:
    async with httpx.AsyncClient(timeout=3.0) as c:
      r = await c.get(f"{cdp_url}/json/version")
      r.raise_for_status()
      data = r.json()
      return {"available": True, "browser": data.get("Browser", "unknown"), "cdp_url": cdp_url}
  except Exception:
    return {"available": False, "browser": None, "cdp_url": cdp_url}


@app.post("/cdp/launch", tags=["cdp"])
async def launch_debug_chrome(body: dict) -> dict:
  """Launch Chrome with --remote-debugging-port in a dedicated user-data-dir.

  This guarantees the debug port binds even if other Chrome instances are running.
  The dedicated user-data-dir isolates the process from existing Chrome profiles.
  """
  import asyncio
  import subprocess
  import tempfile
  from pathlib import Path

  cdp_port = body.get("cdp_port", 9222)
  initial_url = body.get("url", "about:blank")
  user_data_dir = body.get("user_data_dir") or str(
    Path(tempfile.gettempdir()) / "uno-operator-chrome"
  )

  chrome_paths = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ]
  chrome_exe = None
  for p in chrome_paths:
    if Path(p).exists():
      chrome_exe = p
      break
  if not chrome_exe:
    return {"success": False, "error": "Chrome not found on this system"}

  cdp_url = f"http://127.0.0.1:{cdp_port}"

  try:
    import httpx
    async with httpx.AsyncClient(timeout=2.0) as c:
      r = await c.get(f"{cdp_url}/json/version")
      if r.status_code == 200:
        return {
          "success": True,
          "cdp_url": cdp_url,
          "already_running": True,
          "browser": r.json().get("Browser", "unknown"),
        }
  except Exception:
    pass

  try:
    subprocess.Popen([
      chrome_exe,
      f"--remote-debugging-port={cdp_port}",
      f"--user-data-dir={user_data_dir}",
      "--no-first-run",
      initial_url,
    ], creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
  except Exception as e:
    return {"success": False, "error": f"Failed to launch Chrome: {e}"}

  for _ in range(15):
    await asyncio.sleep(0.5)
    try:
      async with httpx.AsyncClient(timeout=2.0) as c:
        r = await c.get(f"{cdp_url}/json/version")
        if r.status_code == 200:
          data = r.json()
          return {
            "success": True,
            "cdp_url": cdp_url,
            "already_running": False,
            "browser": data.get("Browser", "unknown"),
          }
    except Exception:
      continue

  return {"success": False, "error": "Chrome launched but debug port did not respond within 7.5s"}


@app.get("/profiles/{profile_id}/compatibility", tags=["profiles"])
async def get_profile_compatibility(profile_id: str) -> dict:
  """Return domain compatibility info for a web profile."""
  try:
    profile = load_profile(profile_id)
    return {
      "profile_id": profile.profile_id,
      "display_name": profile.display_name,
      "launch_url": profile.launch_url,
      "allowed_domains": profile.allowed_domains or [],
      "game_type": profile.game_type,
    }
  except FileNotFoundError:
    raise HTTPException(404, "profile not found") from None


@app.get("/adapters/{adapter_id}/dom", tags=["adapter"])
async def read_dom(adapter_id: str) -> dict:
  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  return await a.read_dom()


@app.get("/adapters/{adapter_id}/evidence", response_model=AdapterEvidenceBundle, tags=["adapter"])
async def get_evidence(adapter_id: str, correlation_id: str | None = None) -> AdapterEvidenceBundle:
  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  bundle = await a.capture_evidence(adapter_id)
  bundle.correlation_id = correlation_id
  return bundle


@app.post("/adapters/{adapter_id}/actions", response_model=ActionExecutionResult, tags=["adapter"])
async def execute_action(
  adapter_id: str, req: ActionExecutionRequest, correlation_id: str | None = None
) -> ActionExecutionResult:
  now = time.monotonic()
  timestamps = _action_timestamps[adapter_id]
  timestamps[:] = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
  if len(timestamps) >= _RATE_LIMIT_MAX:
    raise HTTPException(429, "rate limit exceeded")
  timestamps.append(now)
  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  return await a.execute(req, correlation_id)


@app.get("/adapters/{adapter_id}/screenshot", tags=["adapter"])
async def get_screenshot(adapter_id: str):
  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  bundle = await a.capture_evidence(adapter_id)
  if not bundle.screenshot or not bundle.screenshot.path:
    raise HTTPException(404, "no screenshot")
  return FileResponse(bundle.screenshot.path, media_type="image/png")


@app.post("/adapters/{adapter_id}/capture-fixture", tags=["adapter"])
async def capture_fixture(adapter_id: str, output_dir: str = "tests/fixtures/web_adapter") -> dict:
  """Export evidence bundle as fixture files for tests."""
  from pathlib import Path

  a = get_adapter(adapter_id)
  if not a:
    raise HTTPException(404, "adapter not found")
  bundle = await a.capture_evidence(adapter_id)
  out = Path(output_dir)
  out.mkdir(parents=True, exist_ok=True)
  fixture_id = str(uuid4())[:8]

  dom_path = out / f"{fixture_id}_dom.json"
  dom_path.write_text(bundle.dom_snapshot.model_dump_json(indent=2), encoding="utf-8")

  evidence_path = out / f"{fixture_id}_evidence.json"
  evidence_path.write_text(bundle.dom_evidence.model_dump_json(indent=2), encoding="utf-8")

  screenshot_path = None
  if bundle.screenshot and bundle.screenshot.path:
    import shutil
    screenshot_path = out / f"{fixture_id}_screenshot.png"
    shutil.copy(bundle.screenshot.path, screenshot_path)

  return {
    "fixture_id": fixture_id,
    "dom": str(dom_path),
    "evidence": str(evidence_path),
    "screenshot": str(screenshot_path) if screenshot_path else None,
  }


@app.post("/adapters/{adapter_id}/detach", tags=["adapter"])
async def detach(adapter_id: str) -> dict:
  from uno_adapter_web.registry import _adapters
  a = _adapters.pop(adapter_id, None)
  if a:
    await a.detach()
  return {"detached": True}


@app.get("/profiles/{profile_id}/selector-health", response_model=ProfileHealthReport, tags=["profiles"])
async def profile_selector_health(
  profile_id: str,
  headless: bool = True,
  correlation_id: str | None = None,
) -> ProfileHealthReport:
  try:
    return await run_playwright_health_check(
      profile_id, headless=headless, correlation_id=correlation_id, source="api",
    )
  except FileNotFoundError:
    raise HTTPException(404, "profile not found") from None


@app.get("/profiles/{profile_id}/health/history", response_model=list[ProfileHealthHistoryEntry], tags=["profiles"])
async def profile_health_history(profile_id: str, limit: int = 20) -> list[ProfileHealthHistoryEntry]:
  try:
    load_profile(profile_id)
  except FileNotFoundError:
    raise HTTPException(404, "profile not found") from None
  return [to_history_entry(r) for r in load_reports(profile_id, limit=limit)]


@app.get("/profiles/{profile_id}/health/summary", response_model=ProfileHealthSummary, tags=["profiles"])
async def profile_health_summary(profile_id: str, limit: int = 20) -> ProfileHealthSummary:
  try:
    profile = load_profile(profile_id)
  except FileNotFoundError:
    raise HTTPException(404, "profile not found") from None
  return build_summary(profile, limit=limit)


@app.get("/profiles/{profile_id}/health/alerts", response_model=list[ProfileHealthAlert], tags=["profiles"])
async def profile_health_alerts(profile_id: str, limit: int = 20) -> list[ProfileHealthAlert]:
  try:
    profile = load_profile(profile_id)
  except FileNotFoundError:
    raise HTTPException(404, "profile not found") from None
  reports = load_reports(profile_id, limit=limit)
  return evaluate_alerts(reports, profile)


@app.get("/metrics/profile-health", tags=["profiles"])
async def profile_health_metrics() -> dict:
  return metrics_export()


@app.get("/playwright/check", tags=["adapter"])
async def playwright_check() -> dict:
  return {"available": playwright_available(), "profiles": [p.profile_id for p in list_profiles()]}


@app.get("/trace/debug", tags=["trace"])
async def trace_debug() -> dict:
  """Diagnostic endpoint: check trace state inside the running process."""
  import os

  from uno_adapter_web.agent_trace import TraceManager
  base = TraceManager.base_dir()
  base_exists = base.exists()
  session_count = 0
  if base_exists:
    session_count = len([d for d in base.iterdir() if d.is_dir()])
  return {
    "env_trace_enabled": os.environ.get("AGENT_SCREENSHOT_TRACE", "NOT_SET"),
    "env_trace_dir": os.environ.get("AGENT_SCREENSHOT_TRACE_DIR", "NOT_SET"),
    "trace_enabled": TraceManager.enabled(),
    "base_dir": str(base),
    "base_dir_exists": base_exists,
    "session_count": session_count,
  }


@app.get("/trace/sessions", tags=["trace"])
async def list_trace_sessions() -> list[dict]:
  """List all trace sessions with step counts."""

  from uno_adapter_web.agent_trace import TraceManager
  if not TraceManager.enabled():
    return []
  base = TraceManager.base_dir()
  if not base.exists():
    return []
  sessions = []
  for d in sorted(base.iterdir()):
    if d.is_dir():
      steps = sorted(d.iterdir()) if d.exists() else []
      step_dirs = [s.name for s in steps if s.is_dir()]
      latest_meta = None
      for sd in reversed(step_dirs):
        meta_path = d / sd / "meta.json"
        if meta_path.exists():
          try:
            latest_meta = __import__("json").loads(meta_path.read_text(encoding="utf-8"))
          except Exception:
            pass
          break
      sessions.append({
        "session_id": d.name,
        "step_count": len(step_dirs),
        "latest_phase": step_dirs[-1].split("_", 1)[-1] if step_dirs else None,
        "latest_meta": latest_meta,
      })
  return sessions


@app.get("/trace/{session_id}/steps", tags=["trace"])
async def list_trace_steps(session_id: str) -> list[dict]:
  """List all trace steps for a session with metadata summaries."""

  from uno_adapter_web.agent_trace import TraceManager
  if not TraceManager.enabled():
    return []
  session_dir = TraceManager.base_dir() / session_id
  if not session_dir.exists():
    return []
  steps = []
  for d in sorted(session_dir.iterdir()):
    if not d.is_dir():
      continue
    parts = d.name.split("_", 1)
    step_num = int(parts[0]) if parts[0].isdigit() else 0
    phase = parts[1] if len(parts) > 1 else "unknown"
    meta = None
    meta_path = d / "meta.json"
    if meta_path.exists():
      try:
        meta = __import__("json").loads(meta_path.read_text(encoding="utf-8"))
      except Exception:
        pass
    screenshots = [f.name for f in d.iterdir() if f.suffix == ".png"]
    steps.append({
      "step": step_num,
      "phase": phase,
      "path": str(d),
      "step_dir_name": d.name,
      "screenshots": screenshots,
      "meta": meta,
    })
  return steps


@app.get("/trace/{session_id}/{step_dir}/frame.png", tags=["trace"])
async def get_trace_frame(session_id: str, step_dir: str):
  """Serve a trace screenshot."""
  from uno_adapter_web.agent_trace import TraceManager
  path = TraceManager.base_dir() / session_id / step_dir / "frame.png"
  if not path.exists():
    raise HTTPException(404, "frame not found")
  return FileResponse(path, media_type="image/png")


@app.get("/trace/{session_id}/{step_dir}/{filename}", tags=["trace"])
async def get_trace_file(session_id: str, step_dir: str, filename: str):
  """Serve any trace file (before.png, after.png, meta.json)."""

  from uno_adapter_web.agent_trace import TraceManager
  path = TraceManager.base_dir() / session_id / step_dir / filename
  if not path.exists():
    raise HTTPException(404, "file not found")
  if filename.endswith(".json"):
    return __import__("json").loads(path.read_text(encoding="utf-8"))
  return FileResponse(path, media_type="image/png")


@app.get("/trace/{session_id}/latest-frame", tags=["trace"])
async def get_latest_trace_frame(session_id: str):
  """Serve the latest screenshot from the most recent trace step."""
  from uno_adapter_web.agent_trace import TraceManager
  session_dir = TraceManager.base_dir() / session_id
  if not session_dir.exists():
    raise HTTPException(404, "session trace not found")
  steps = sorted([d for d in session_dir.iterdir() if d.is_dir()])
  for step_dir in reversed(steps):
    for name in ["frame.png", "after.png", "before.png"]:
      p = step_dir / name
      if p.exists():
        return FileResponse(p, media_type="image/png")
  raise HTTPException(404, "no screenshots found in trace")


@app.get("/trace/{session_id}/latest-meta", tags=["trace"])
async def get_latest_trace_meta(session_id: str):
  """Serve the latest meta.json from the most recent trace step."""
  import json

  from uno_adapter_web.agent_trace import TraceManager
  session_dir = TraceManager.base_dir() / session_id
  if not session_dir.exists():
    raise HTTPException(404, "session trace not found")
  steps = sorted([d for d in session_dir.iterdir() if d.is_dir()])
  for step_dir in reversed(steps):
    meta_path = step_dir / "meta.json"
    if meta_path.exists():
      return json.loads(meta_path.read_text(encoding="utf-8"))
  raise HTTPException(404, "no meta found in trace")


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_adapter_web.api:app", host="127.0.0.1", port=SERVICE_PORTS["adapter-web"])

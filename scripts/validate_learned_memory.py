"""Hardened real-UNO validation script.

Reads actual window bounds from the adapter preview endpoint,
uses configurable timing, and writes full artifact metadata.

Usage:
  1. Start Postgres + backend services
  2. Open your UNO Desktop game
  3. Attach: curl -X POST http://127.0.0.1:8105/attach -H "Content-Type: application/json" \
       -d '{"session_id":"real-validation","mode":"pywinauto","profile_id":"real-uno-desktop","window_title":"UNO"}'
  4. Run: uv run python scripts/validate_learned_memory.py --adapter-id <ID> [--render-wait 1.0]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

ARTIFACTS_DIR = Path("artifacts/real-validation")
ADAPTER_PORT = 8105
API = f"http://127.0.0.1:{ADAPTER_PORT}"


def get_calibration(adapter_id: str) -> dict:
  """Fetch window + client bounds and offset from adapter calibration endpoint."""
  try:
    r = httpx.get(f"{API}/adapters/{adapter_id}/calibration", timeout=10)
    r.raise_for_status()
    return r.json()
  except Exception as e:
    print(f"  WARNING: calibration endpoint unavailable ({e}), using preview bounds only")
    return {}


def get_bounds(adapter_id: str) -> dict[str, float]:
  """Read actual window bounds from adapter preview endpoint."""
  r = httpx.get(f"{API}/adapters/{adapter_id}/preview", timeout=10)
  r.raise_for_status()
  preview = r.json()
  attachment = preview.get("attachment") or {}
  bounds = attachment.get("bounds")
  if not bounds or bounds.get("right", 0) - bounds.get("left", 0) <= 0:
    print("  WARNING: preview bounds empty, using 1920x1080 fallback")
    return {"left": 0.0, "top": 0.0, "right": 1920.0, "bottom": 1080.0}
  return bounds


def get_window_title(adapter_id: str) -> str:
  r = httpx.get(f"{API}/adapters/{adapter_id}/preview", timeout=10)
  preview = r.json()
  return (preview.get("attachment") or {}).get("window_title", "unknown")


def capture_screenshot(adapter_id: str, label: str) -> Path:
  r = httpx.get(f"{API}/adapters/{adapter_id}/screenshot", timeout=15)
  r.raise_for_status()
  path = ARTIFACTS_DIR / f"{label}.png"
  path.write_bytes(r.content)
  return path


def compute_diff(before_path: Path, after_path: Path, diff_path: Path) -> float:
  from PIL import Image, ImageChops
  b = Image.open(before_path).convert("RGB")
  a = Image.open(after_path).convert("RGB")
  if b.size != a.size:
    a = a.resize(b.size)
  diff = ImageChops.difference(b, a)
  hist = diff.histogram()
  changed = sum(hist[1:])
  total = b.size[0] * b.size[1] * 3
  ratio = changed / total if total else 0.0
  diff.save(diff_path)
  return ratio


def write_metadata(
  session_id: str, adapter_id: str, window_title: str,
  bounds: dict, screen_state_hash: str,
  source_1: str, conf_1: float,
  source_2: str, conf_2: float,
  diff_ratio: float, visual_change: bool,
  zone_conf: float, zone_ok: int, zone_fail: int,
  render_wait: float,
  calibration: dict | None = None,
  resolved_click: dict | None = None,
):
  cal = calibration or {}
  cb = cal.get("client_bounds")
  wb = cal.get("window_bounds") or bounds
  bounds_used = "client_bounds" if cb else "window_bounds"
  resolve_ref = cb or wb

  meta = {
    "session_id": session_id,
    "adapter_id": adapter_id,
    "window_title": window_title,
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "screen_state_hash": screen_state_hash,
    "render_wait_s": render_wait,
    "bounds_used_for_resolution": bounds_used,
    "resolved_point_before_click": resolved_click,
    "client_width": (cb["right"] - cb["left"]) if cb else None,
    "client_height": (cb["bottom"] - cb["top"]) if cb else None,
    "window_width": wb["right"] - wb["left"],
    "window_height": wb["bottom"] - wb["top"],
    "resolution": {
      "first": {"source": source_1, "confidence": conf_1},
      "second": {"source": source_2, "confidence": conf_2},
    },
    "visual_diff": {
      "ratio": diff_ratio,
      "confirmed": visual_change,
    },
    "zone": {
      "confidence": zone_conf,
      "success_count": zone_ok,
      "failure_count": zone_fail,
    },
    "calibration": cal,
  }
  path = ARTIFACTS_DIR / "metadata.json"
  path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
  return meta


def run(adapter_id: str, session_id: str, render_wait: float):
  from uno_shared.learned_zones_pg import PgLearnedZoneStore
  from uno_adapter_windows.profiles import load_profile
  from uno_adapter_windows.rpa.perception.target_locator import ResolutionTrace, locate_selector
  from uno_schemas.adapter_windows import WindowsActionExecutionRequest, WindowsActionType
  from uno_schemas.learned_zones import BoundingBox as BB, Resolution as Res

  ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
  store = PgLearnedZoneStore()
  store.reset_game(session_id)
  profile = load_profile("real-uno-desktop")

  # Read actual window bounds + calibration
  bounds = get_bounds(adapter_id)
  window_title = get_window_title(adapter_id)
  calibration = get_calibration(adapter_id)

  print(f"  Window: {window_title}")
  print(f"  Window bounds: {bounds}")
  if calibration.get("client_bounds"):
    cb = calibration["client_bounds"]
    print(f"  Client bounds: {cb}")
    off = calibration.get("offset", {})
    print(f"  Offset:        left={off.get('left_delta',0)} top={off.get('top_delta',0)} "
          f"right={off.get('right_delta',0)} bottom={off.get('bottom_delta',0)}")
    print(f"  Coord space:   {calibration.get('coordinate_space','unknown')}")
    print(f"  ⚠  If clicks miss, adjust profile layout_targets by the offset above")
  else:
    print(f"  ⚠  Client bounds unavailable — real-game clicks may need layout recalibration")
    print(f"     (title bar / border offsets may shift effective targets)")
  print(f"  Render wait: {render_wait}s")

  # ── 1. Cold start ──
  client_bounds = calibration.get("client_bounds")
  trace1 = ResolutionTrace()
  locate_selector("draw", profile, [], window_bounds=bounds, client_bounds=client_bounds,
                  game_id=session_id, zone_store=store, trace=trace1)
  print(f"\n  [1] COLD: source={trace1.source} conf={trace1.confidence:.2f}")

  # ── 2. Before screenshot ──
  before_path = capture_screenshot(adapter_id, "before")
  print(f"  [2] BEFORE: {before_path.name} ({before_path.stat().st_size} bytes)")

  # ── 3. Execute draw ──
  resp = httpx.post(f"{API}/adapters/{adapter_id}/actions", json={
    "action_type": "click_input", "selector_key": "draw",
    "domain_action": "draw_card", "capture_screenshots": True,
    "min_confidence": 0.3,
  }, timeout=30)
  result = resp.json()
  click = result.get("click_point", {"x": 0, "y": 0})
  print(f"  [3] ACTION: success={result['success']} click=({click['x']:.0f},{click['y']:.0f}) "
        f"latency={result.get('duration_ms')}ms")

  # ── 4. After screenshot ──
  time.sleep(render_wait)
  after_path = capture_screenshot(adapter_id, "after")
  print(f"  [4] AFTER: {after_path.name} ({after_path.stat().st_size} bytes)")

  # ── 5. Visual diff ──
  diff_path = ARTIFACTS_DIR / "diff.png"
  ratio = compute_diff(before_path, after_path, diff_path)
  visual_change = ratio >= 0.005
  print(f"  [5] DIFF: ratio={ratio:.6f} visual_change={visual_change}")

  # ── 6. Record outcome ──
  verified_success = result["success"] and visual_change
  store.record_provisional(
    game_id=session_id, profile_id="real-uno-desktop", selector_key="draw_button",
    bounding_box=BB(left=click["x"]-30, top=click["y"]-15, right=click["x"]+30, bottom=click["y"]+15),
    click_point=click, resolution=Res(width=int(bounds["right"]-bounds["left"]),
                                       height=int(bounds["bottom"]-bounds["top"])),
    semantic_guess="draw_card",
  )
  store.record_verified_outcome(game_id=session_id, profile_id="real-uno-desktop",
                                selector_key="draw_button", success=verified_success)
  zones = store.list_zones(session_id)
  z = zones[0] if zones else None
  print(f"  [6] ZONE: conf={z.clickability_score:.2f} ok={z.success_count} "
        f"fail={z.failure_count} verified={z.last_verified_result}")

  # ── 7. Second resolution ──
  trace2 = ResolutionTrace()
  locate_selector("draw", profile, [], window_bounds=bounds, client_bounds=client_bounds,
                  game_id=session_id, zone_store=store, trace=trace2)
  print(f"  [7] LEARNED: source={trace2.source} zone_conf={trace2.zone_confidence:.2f} "
        f"verified={trace2.zone_verified_backed} hash={trace2.screen_state_hash[:12]}")

  # ── 8. Write metadata ──
  meta = write_metadata(
    session_id=session_id, adapter_id=adapter_id, window_title=window_title,
    bounds=bounds, screen_state_hash=trace2.screen_state_hash,
    source_1=trace1.source, conf_1=trace1.confidence,
    source_2=trace2.source, conf_2=trace2.zone_confidence,
    diff_ratio=ratio, visual_change=visual_change,
    zone_conf=z.clickability_score, zone_ok=z.success_count, zone_fail=z.failure_count,
    render_wait=render_wait, calibration=calibration,
    resolved_click=click,
  )

  store.close()

  print(f"\n  === RESULT ===")
  print(f"  Cold → Learned: {trace1.source} → {trace2.source}")
  print(f"  Visual change:  {visual_change} (ratio={ratio:.6f})")
  print(f"  Zone promoted:  conf={z.clickability_score:.2f} ok={z.success_count}")
  print(f"  Artifacts:      {ARTIFACTS_DIR}/")
  print(f"  Metadata:       {ARTIFACTS_DIR}/metadata.json")
  print(f"  =================")

  if trace2.source != "learned_memory":
    print(f"\n  WARNING: second resolution did not use learned_memory")
    print(f"  Possible causes: zone confidence too low, verification failed, or no zone recorded")


def main():
  parser = argparse.ArgumentParser(description="Validate learned-memory loop on real UNO window")
  parser.add_argument("--adapter-id", required=True, help="Adapter ID from /attach response")
  parser.add_argument("--session-id", default="real-validation", help="Session ID for zone storage")
  parser.add_argument("--render-wait", type=float, default=1.0,
                      help="Seconds to wait for UI render before after-screenshot (default: 1.0)")
  args = parser.parse_args()
  run(args.adapter_id, args.session_id, args.render_wait)


if __name__ == "__main__":
  main()

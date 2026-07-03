"""Live proof: verification-aware learned-memory loop with screenshot confirmation.

Extends the mock UNO app so Draw click produces a visible counter change.
Before/after screenshots are compared to prove visual state change detection.

Requires: Windows, Postgres, pywinauto
Run: uv run python -m pytest tests/integration/test_verification_loop.py -v -s -m integration
"""

import os
import shutil
import socket
import subprocess
import sys
import time

import pytest

if sys.platform != "win32":
  pytest.skip("Windows only", allow_module_level=True)

_pg = False
try:
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.settimeout(2)
  s.connect(("127.0.0.1", 5432))
  s.close()
  _pg = True
except Exception:
  pass
if not _pg:
  pytest.skip("Postgres not available", allow_module_level=True)

try:
  import pywinauto  # noqa: F401
except ImportError:
  pytest.skip("pywinauto not installed", allow_module_level=True)


ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts", "verification-loop")


@pytest.fixture(autouse=True)
def clean_artifacts():
  if os.path.exists(ARTIFACTS_DIR):
    shutil.rmtree(ARTIFACTS_DIR, ignore_errors=True)
  os.makedirs(ARTIFACTS_DIR, exist_ok=True)
  yield
  # keep artifacts for inspection


@pytest.fixture
def pg_store():
  from uno_shared.learned_zones_pg import PgLearnedZoneStore
  s = PgLearnedZoneStore()
  s.reset_game("verification-loop")
  yield s
  s.reset_game("verification-loop")
  s.close()


@pytest.fixture
def adapter_client():
  from fastapi.testclient import TestClient
  from uno_adapter_windows.api import app
  from uno_schemas.adapter_windows import AttachWindowsAdapterRequest, WindowsAdapterMode

  client = TestClient(app)

  # Kill leftover mock targets
  subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-Process python -ErrorAction SilentlyContinue | "
     "Where-Object { $_.MainWindowTitle -like '*UNO Mock*' } | Stop-Process -Force"],
    check=False,
  )
  time.sleep(0.5)

  resp = client.post("/attach", json=AttachWindowsAdapterRequest(
    session_id="verification-loop",
    mode=WindowsAdapterMode.PYWINAUTO,
    profile_id="local-mock-uno",
    launch_test_target=True,
  ).model_dump(mode="json"))
  data = resp.json()
  if not data.get("attached"):
    pytest.skip(f"pywinauto attach failed: {data.get('message')}")

  aid = data["adapter_id"]
  yield client, aid
  try:
    client.post(f"/adapters/{aid}/detach")
  except Exception:
    pass


GAME_ID = "verification-loop"
PROFILE_ID = "local-mock-uno"
BOUNDS = {"left": 0.0, "top": 0.0, "right": 640.0, "bottom": 480.0}


@pytest.mark.integration
def test_verification_aware_loop(adapter_client, pg_store):
  """Full loop: cold start → click → visual change → verified success → learned memory reuse."""
  from uno_adapter_windows.profiles import load_profile
  from uno_adapter_windows.rpa.perception.target_locator import ResolutionTrace, locate_selector
  from uno_schemas.adapter_windows import (
    WindowsActionExecutionRequest,
    WindowsActionType,
  )
  from uno_schemas.learned_zones import BoundingBox as BB
  from uno_schemas.learned_zones import Resolution as Res

  client, aid = adapter_client
  profile = load_profile("local-mock-uno")

  # ── Step 1: Cold start ──
  trace1 = ResolutionTrace()
  target1 = locate_selector(
    "draw", profile, [],
    window_bounds=BOUNDS, game_id=GAME_ID, zone_store=pg_store,
    trace=trace1,
  )
  assert target1 is not None
  assert trace1.source == "layout_targets"
  print(f"\n  [1] COLD START: source={trace1.source} conf={trace1.confidence:.2f}")

  # ── Step 2: Capture before screenshot ──
  before_resp = client.get(f"/adapters/{aid}/screenshot")
  assert before_resp.status_code == 200
  before_path = os.path.join(ARTIFACTS_DIR, "before_draw.png")
  with open(before_path, "wb") as f:
    f.write(before_resp.content)
  print(f"  [2] BEFORE screenshot: {before_path} ({len(before_resp.content)} bytes)")

  # ── Step 3: Execute Draw click ──
  resp = client.post(
    f"/adapters/{aid}/actions",
    json=WindowsActionExecutionRequest(
      action_type=WindowsActionType.CLICK_INPUT,
      selector_key="draw",
      domain_action="draw_card",
      capture_screenshots=True,
      min_confidence=0.3,
    ).model_dump(mode="json"),
    params={"correlation_id": "verify-loop-1"},
  )
  assert resp.status_code == 200
  result = resp.json()
  assert result["success"], f"action failed: {result.get('error')}"
  click = result.get("click_point", {"x": 0, "y": 0})
  print(f"  [3] ACTION: success={result['success']} click=({click['x']:.0f},{click['y']:.0f}) "
        f"latency={result.get('duration_ms')}ms")

  # ── Step 4: Wait for tkinter to render, then capture after screenshot ──
  time.sleep(0.5)  # let tkinter mainloop process the click and update labels
  after_resp = client.get(f"/adapters/{aid}/screenshot")
  assert after_resp.status_code == 200
  after_path = os.path.join(ARTIFACTS_DIR, "after_draw.png")
  with open(after_path, "wb") as f:
    f.write(after_resp.content)
  print(f"  [4] AFTER screenshot: {after_path} ({len(after_resp.content)} bytes)")

  # ── Step 5: Verify visual change ──
  from PIL import Image, ImageChops
  img_before = Image.open(before_path).convert("RGB")
  img_after = Image.open(after_path).convert("RGB")
  if img_before.size != img_after.size:
    img_after = img_after.resize(img_before.size)
  diff = ImageChops.difference(img_before, img_after)
  hist = diff.histogram()
  changed_pixels = sum(hist[1:])  # non-zero channel values
  total_pixels = img_before.size[0] * img_before.size[1] * 3
  change_ratio = changed_pixels / total_pixels if total_pixels else 0.0

  diff_path = os.path.join(ARTIFACTS_DIR, "diff.png")
  diff.save(diff_path)

  visual_change = change_ratio >= 0.005  # same threshold as ui_verifier
  print(f"  [5] VISUAL DIFF: change_ratio={change_ratio:.6f} "
        f"changed_pixels={changed_pixels}/{total_pixels} "
        f"visual_change={visual_change} diff_saved={diff_path}")

  # ── Step 6: Record outcome based on visual confirmation ──
  verified_success = result["success"] and visual_change
  pg_store.record_provisional(
    game_id=GAME_ID, profile_id=PROFILE_ID, selector_key="draw_button",
    bounding_box=BB(
      left=click["x"] - 30, top=click["y"] - 15,
      right=click["x"] + 30, bottom=click["y"] + 15,
    ),
    click_point=click,
    resolution=Res(width=640, height=480),
    semantic_guess="draw_card",
  )
  pg_store.record_verified_outcome(
    game_id=GAME_ID, profile_id=PROFILE_ID,
    selector_key="draw_button",
    success=verified_success,
  )

  zones = pg_store.list_zones(GAME_ID)
  assert len(zones) == 1
  z = zones[0]
  print(f"  [6] ZONE: id={z.zone_id[:8]} conf={z.clickability_score:.2f} "
        f"ok={z.success_count} fail={z.failure_count} "
        f"verified={z.last_verified_result} "
        f"visual_confirmed={visual_change}")

  # ── Step 7: Second resolution uses learned memory ──
  trace2 = ResolutionTrace()
  target2 = locate_selector(
    "draw", profile, [],
    window_bounds=BOUNDS, game_id=GAME_ID, zone_store=pg_store,
    trace=trace2,
  )
  assert target2 is not None
  assert trace2.source == "learned_memory"
  assert trace2.zone_verified_backed is True
  print(f"  [7] LEARNED: source={trace2.source} zone={trace2.zone_label} "
        f"conf={trace2.zone_confidence:.2f} "
        f"ok={trace2.zone_success}/fail={trace2.zone_failure} "
        f"verified={trace2.zone_verified_backed} "
        f"hash={trace2.screen_state_hash[:12]}")

  # ── Step 8: Second draw — verify another visual change ──
  before2_resp = client.get(f"/adapters/{aid}/screenshot")
  before2_path = os.path.join(ARTIFACTS_DIR, "before_draw2.png")
  with open(before2_path, "wb") as f:
    f.write(before2_resp.content)

  resp2 = client.post(
    f"/adapters/{aid}/actions",
    json=WindowsActionExecutionRequest(
      action_type=WindowsActionType.CLICK_INPUT,
      selector_key="draw",
      domain_action="draw_card",
      capture_screenshots=True,
      min_confidence=0.3,
    ).model_dump(mode="json"),
    params={"correlation_id": "verify-loop-2"},
  )
  assert resp2.status_code == 200
  result2 = resp2.json()
  assert result2["success"]

  time.sleep(0.5)  # let tkinter render
  after2_resp = client.get(f"/adapters/{aid}/screenshot")
  after2_path = os.path.join(ARTIFACTS_DIR, "after_draw2.png")
  with open(after2_path, "wb") as f:
    f.write(after2_resp.content)

  img_b2 = Image.open(before2_path).convert("RGB")
  img_a2 = Image.open(after2_path).convert("RGB")
  if img_b2.size != img_a2.size:
    img_a2 = img_a2.resize(img_b2.size)
  diff2 = ImageChops.difference(img_b2, img_a2)
  hist2 = diff2.histogram()
  changed2 = sum(hist2[1:])
  total2 = img_b2.size[0] * img_b2.size[1] * 3
  ratio2 = changed2 / total2 if total2 else 0.0
  visual2 = ratio2 >= 0.005

  # Record second outcome
  pg_store.record_verified_outcome(
    game_id=GAME_ID, profile_id=PROFILE_ID,
    selector_key="draw_button",
    success=result2["success"] and visual2,
  )

  final_zones = pg_store.list_zones(GAME_ID)
  fz = final_zones[0]
  print(f"  [8] SECOND DRAW: visual_change={visual2} ratio={ratio2:.6f} "
        f"zone_conf={fz.clickability_score:.2f} "
        f"ok={fz.success_count} fail={fz.failure_count}")

  # ── Summary ──
  print("\n  === VERIFICATION LOOP PROOF ===")
  print("  Mock change:       Draw click → counter increments (Drawn: 0→1→2)")
  print(f"  Cold start:        source={trace1.source} conf={trace1.confidence:.2f}")
  print(f"  Visual diff #1:    ratio={change_ratio:.6f} confirmed={visual_change}")
  print(f"  Visual diff #2:    ratio={ratio2:.6f} confirmed={visual2}")
  print(f"  Zone after 2 ok:   conf={fz.clickability_score:.2f} ok={fz.success_count} fail={fz.failure_count}")
  print(f"  Learned memory:    source={trace2.source} zone_conf={trace2.zone_confidence:.2f} verified={trace2.zone_verified_backed}")
  print(f"  Artifacts:         {ARTIFACTS_DIR}")
  print("  ================================")

  assert verified_success, "first draw should produce visual change"
  assert visual2, "second draw should also produce visual change"
  assert fz.success_count >= 2, f"zone should have >=2 verified successes, got {fz.success_count}"
  assert fz.clickability_score > 0.7, f"confidence should be >0.7 after 2 verified successes, got {fz.clickability_score}"

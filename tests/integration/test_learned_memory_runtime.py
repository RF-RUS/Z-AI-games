"""Runtime validation: learned memory improves target resolution end-to-end.

Proves the full loop:
  1. First resolution: uses static layout_targets (cold start)
  2. Record provisional + verified outcome in Postgres
  3. Second resolution: uses learned memory before layout_targets
  4. Safety: low-confidence ignored, failure demotes, reset clears

Requires: Postgres running (docker-compose up postgres)
Run: uv run python -m pytest tests/unit/test_learned_memory_runtime.py -v -s
"""

import socket

import pytest
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.rpa.perception.target_locator import ResolutionTrace, locate_selector
from uno_schemas.adapter_windows import UiNodeSnapshot

_pg = False
try:
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.settimeout(2)
  s.connect(("127.0.0.1", 5432))
  s.close()
  _pg = True
except Exception:
  pass

pytestmark = pytest.mark.skipif(not _pg, reason="Postgres not available")


@pytest.fixture
def store():
  from uno_shared.learned_zones_pg import PgLearnedZoneStore
  s = PgLearnedZoneStore()
  s.reset_game("validation-game")
  yield s
  s.reset_game("validation-game")
  s.close()


@pytest.fixture
def profile():
  return load_profile("real-uno-desktop")


GAME_ID = "validation-game"
PROFILE_ID = "real-uno-desktop"
BOUNDS = {"left": 0.0, "top": 0.0, "right": 1920.0, "bottom": 1080.0}
EMPTY_NODES: list[UiNodeSnapshot] = []  # No UIA elements — simulates canvas game


# ── 1. Runtime proof: first run uses layout_targets, second uses learned memory ──

def test_first_resolution_uses_layout_targets(profile, store):
  """Without any learned zones, resolution falls through to static layout_targets."""
  trace = ResolutionTrace()
  target = locate_selector(
    "draw", profile, EMPTY_NODES,
    window_bounds=BOUNDS, game_id=GAME_ID, zone_store=store,
    trace=trace,
  )
  assert target is not None
  assert trace.source == "layout_targets", f"first run should use layout_targets, got {trace.source}"
  assert trace.confidence == 0.72  # static layout confidence
  assert trace.zone_id == ""  # no learned zone
  print(f"\n  [PASS] First resolution: source={trace.source}, conf={trace.confidence:.2f}")


def test_after_verified_success_second_resolution_uses_learned_memory(profile, store):
  """After recording a verified success, second resolution uses learned memory."""
  # First resolution — cold start
  trace1 = ResolutionTrace()
  locate_selector(
    "draw", profile, EMPTY_NODES,
    window_bounds=BOUNDS, game_id=GAME_ID, zone_store=store,
    trace=trace1,
  )
  assert trace1.source == "layout_targets"
  print(f"\n  [1st] source={trace1.source}, conf={trace1.confidence:.2f}")

  # Record provisional observation
  from uno_schemas.learned_zones import BoundingBox as BB
  from uno_schemas.learned_zones import Resolution as Res
  store.record_provisional(
    game_id=GAME_ID, profile_id=PROFILE_ID, selector_key="draw_button",
    bounding_box=BB(left=800, top=300, right=900, bottom=400),
    click_point={"x": 850, "y": 350},
    resolution=Res(width=1920, height=1080),
    semantic_guess="draw_card",
  )

  # Record verified success
  store.record_verified_outcome(
    game_id=GAME_ID, profile_id=PROFILE_ID,
    selector_key="draw_button", success=True,
  )

  # Second resolution — should now use learned memory
  trace2 = ResolutionTrace()
  target2 = locate_selector(
    "draw", profile, EMPTY_NODES,
    window_bounds=BOUNDS, game_id=GAME_ID, zone_store=store,
    trace=trace2,
  )
  assert target2 is not None
  assert trace2.source == "learned_memory", (
    f"second run should use learned_memory, got {trace2.source}"
  )
  assert trace2.zone_id != "", "should have a zone_id"
  assert trace2.zone_verified_backed is True, "should be verified-backed"
  assert trace2.zone_success == 1
  assert trace2.zone_confidence > 0.6, f"confidence should be > 0.6, got {trace2.zone_confidence}"

  # Click point should be from the learned zone, not the static layout
  # Static layout draw_button is at x_ratio=0.44 (844.8), learned is at x=850
  assert target2.click_point is not None
  # The learned zone's x_ratio = 850/1920 ≈ 0.4427, so abs_x = 850
  assert 840 < target2.click_point["x"] < 860, (
    f"learned zone click_x should be ~850, got {target2.click_point['x']}"
  )

  print(f"  [2nd] source={trace2.source}, zone={trace2.zone_label}, "
        f"zone_conf={trace2.zone_confidence:.2f}, "
        f"ok={trace2.zone_success}/fail={trace2.zone_failure}, "
        f"verified={trace2.zone_verified_backed}")
  print("  [PASS] Learned memory took over after verified success")


# ── 2. Traceability: diagnostics are populated correctly ──

def test_trace_populated_for_each_source(profile, store):
  """Each resolution source populates the trace correctly."""
  # layout_targets
  t1 = ResolutionTrace()
  locate_selector("draw", profile, EMPTY_NODES, window_bounds=BOUNDS, trace=t1)
  assert t1.source == "layout_targets"
  assert t1.selector_key == "draw"

  # learned_memory (after seeding)
  from uno_schemas.learned_zones import BoundingBox as BB
  from uno_schemas.learned_zones import Resolution as Res
  store.record_provisional(
    game_id=GAME_ID, profile_id=PROFILE_ID, selector_key="draw_button",
    bounding_box=BB(left=800, top=300, right=900, bottom=400),
    click_point={"x": 850, "y": 350}, resolution=Res(width=1920, height=1080),
  )
  store.record_verified_outcome(game_id=GAME_ID, profile_id=PROFILE_ID, selector_key="draw_button", success=True)

  t2 = ResolutionTrace()
  locate_selector("draw", profile, EMPTY_NODES, window_bounds=BOUNDS,
                  game_id=GAME_ID, zone_store=store, trace=t2)
  assert t2.source == "learned_memory"
  assert t2.zone_id != ""
  assert t2.screen_state_hash != ""

  print(f"\n  [PASS] Trace populated: layout→{t1.source}, learned→{t2.source}")


# ── 3. Safety: low-confidence zones are ignored ──

def test_low_confidence_zone_ignored(profile, store):
  """A zone with confidence < 0.5 is not used for resolution."""
  from uno_schemas.learned_zones import BoundingBox as BB
  from uno_schemas.learned_zones import Resolution as Res
  # Seed a zone
  store.record_provisional(
    game_id=GAME_ID, profile_id=PROFILE_ID, selector_key="draw_button",
    bounding_box=BB(left=800, top=300, right=900, bottom=400),
    click_point={"x": 850, "y": 350}, resolution=Res(width=1920, height=1080),
  )
  # Fail it 10 times — should tank confidence
  for _ in range(10):
    store.record_verified_outcome(game_id=GAME_ID, profile_id=PROFILE_ID,
                                  selector_key="draw_button", success=False)

  zones = store.list_zones(GAME_ID)
  assert len(zones) == 1
  assert zones[0].clickability_score < 0.4, (
    f"10 failures should tank confidence below 0.4, got {zones[0].clickability_score}"
  )

  # Resolution should NOT use the low-confidence zone
  trace = ResolutionTrace()
  locate_selector(
    "draw", profile, EMPTY_NODES,
    window_bounds=BOUNDS, game_id=GAME_ID, zone_store=store,
    trace=trace,
  )
  assert trace.source == "layout_targets", (
    f"low-confidence zone should be ignored, fell back to {trace.source}"
  )
  print(f"\n  [PASS] Low-confidence zone (conf={zones[0].clickability_score:.2f}) ignored → {trace.source}")


# ── 4. Safety: verified failure reduces reuse likelihood ──

def test_failure_reduces_confidence(profile, store):
  """A verified failure lowers confidence, eventually below the threshold."""
  from uno_schemas.learned_zones import BoundingBox as BB
  from uno_schemas.learned_zones import Resolution as Res

  # Seed with a success
  store.record_provisional(
    game_id=GAME_ID, profile_id=PROFILE_ID, selector_key="draw_button",
    bounding_box=BB(left=800, top=300, right=900, bottom=400),
    click_point={"x": 850, "y": 350}, resolution=Res(width=1920, height=1080),
  )
  store.record_verified_outcome(game_id=GAME_ID, profile_id=PROFILE_ID,
                                selector_key="draw_button", success=True)
  zones = store.list_zones(GAME_ID)
  conf_after_success = zones[0].clickability_score
  assert conf_after_success > 0.6

  # Now fail it 3 times
  for _ in range(3):
    store.record_verified_outcome(game_id=GAME_ID, profile_id=PROFILE_ID,
                                  selector_key="draw_button", success=False)
  zones = store.list_zones(GAME_ID)
  conf_after_failures = zones[0].clickability_score
  assert conf_after_failures < conf_after_success, (
    f"confidence should drop after failures: {conf_after_success:.2f} → {conf_after_failures:.2f}"
  )
  print(f"\n  [PASS] Confidence after 1 success: {conf_after_success:.2f}, "
        f"after 3 failures: {conf_after_failures:.2f}")


# ── 5. Safety: reset_game removes all influence ──

def test_reset_game_clears_influence(profile, store):
  """After reset_game, resolution falls back to layout_targets."""
  from uno_schemas.learned_zones import BoundingBox as BB
  from uno_schemas.learned_zones import Resolution as Res

  # Seed
  store.record_provisional(
    game_id=GAME_ID, profile_id=PROFILE_ID, selector_key="draw_button",
    bounding_box=BB(left=800, top=300, right=900, bottom=400),
    click_point={"x": 850, "y": 350}, resolution=Res(width=1920, height=1080),
  )
  store.record_verified_outcome(game_id=GAME_ID, profile_id=PROFILE_ID,
                                selector_key="draw_button", success=True)

  # Verify it's using learned memory
  t1 = ResolutionTrace()
  locate_selector("draw", profile, EMPTY_NODES, window_bounds=BOUNDS,
                  game_id=GAME_ID, zone_store=store, trace=t1)
  assert t1.source == "learned_memory"

  # Reset
  deleted = store.reset_game(GAME_ID)
  assert deleted == 1

  # Now should fall back to layout_targets
  t2 = ResolutionTrace()
  locate_selector("draw", profile, EMPTY_NODES, window_bounds=BOUNDS,
                  game_id=GAME_ID, zone_store=store, trace=t2)
  assert t2.source == "layout_targets", (
    f"after reset_game, should use layout_targets, got {t2.source}"
  )
  print(f"\n  [PASS] After reset_game: {t1.source} → {t2.source}")


# ── 6. Safety: reset_profile removes only that profile's influence ──

def test_reset_profile_scoped(profile, store):
  """reset_profile only removes zones for the specified profile."""
  from uno_schemas.learned_zones import BoundingBox as BB
  from uno_schemas.learned_zones import Resolution as Res

  store.record_provisional(
    game_id=GAME_ID, profile_id=PROFILE_ID, selector_key="draw_button",
    bounding_box=BB(left=800, top=300, right=900, bottom=400),
    click_point={"x": 850, "y": 350}, resolution=Res(width=1920, height=1080),
  )
  store.record_verified_outcome(game_id=GAME_ID, profile_id=PROFILE_ID,
                                selector_key="draw_button", success=True)

  store.record_provisional(
    game_id=GAME_ID, profile_id="other-profile", selector_key="draw_button",
    bounding_box=BB(left=800, top=300, right=900, bottom=400),
    click_point={"x": 850, "y": 350}, resolution=Res(width=1920, height=1080),
  )
  store.record_verified_outcome(game_id=GAME_ID, profile_id="other-profile",
                                selector_key="draw_button", success=True)

  assert len(store.list_zones(GAME_ID)) == 2

  # Reset only one profile
  deleted = store.reset_profile(GAME_ID, PROFILE_ID)
  assert deleted == 1

  remaining = store.list_zones(GAME_ID)
  assert len(remaining) == 1
  assert remaining[0].profile_id == "other-profile"
  print(f"\n  [PASS] reset_profile scoped: deleted={deleted}, remaining={len(remaining)}")

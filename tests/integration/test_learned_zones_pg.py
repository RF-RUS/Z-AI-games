"""Tests for Postgres-backed learned zone store — verification-aware learning.

Requires a running Postgres instance (docker-compose up postgres).
Run with: uv run pytest tests/unit/test_learned_zones_pg.py -v
"""


import pytest
from uno_schemas.learned_zones import BoundingBox, Resolution

# Check Postgres availability — use a simple TCP check + connection test
_pg_available = False
try:
  import socket
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.settimeout(2)
  s.connect(("127.0.0.1", 5432))
  s.close()
  _pg_available = True
except Exception:
  pass

pytestmark = pytest.mark.skipif(not _pg_available, reason="Postgres not available (docker-compose up postgres)")


@pytest.fixture
def store():
  from uno_shared.learned_zones_pg import PgLearnedZoneStore
  s = PgLearnedZoneStore()
  # Clean test data
  s.reset_game("test-game-pg")
  yield s
  s.reset_game("test-game-pg")
  s.close()


def _zone_params():
  return dict(
    game_id="test-game-pg",
    profile_id="test-profile",
    selector_key="draw_button",
    bounding_box=BoundingBox(left=100, top=200, right=200, bottom=250),
    click_point={"x": 150, "y": 225},
    resolution=Resolution(width=1920, height=1080),
    semantic_guess="draw_card",
  )


# ── Provisional vs verified behavior ──

def test_provisional_does_not_promote_confidence(store):
  """A provisional observation should NOT significantly boost confidence."""
  zone = store.record_provisional(**_zone_params())
  assert zone is not None
  # Provisional-only zone should have neutral confidence (~0.5)
  assert 0.4 <= zone.clickability_score <= 0.6, (
    f"provisional confidence should be near 0.5, got {zone.clickability_score}"
  )


def test_verified_success_promotes_confidence(store):
  """A verified success should push confidence above neutral."""
  store.record_provisional(**_zone_params())
  zone = store.record_verified_outcome(
    game_id="test-game-pg", profile_id="test-profile",
    selector_key="draw_button", success=True,
  )
  assert zone is not None
  assert zone.success_count == 1
  assert zone.failure_count == 0
  assert zone.clickability_score > 0.6, (
    f"verified success should promote confidence > 0.6, got {zone.clickability_score}"
  )


def test_verified_failure_demotes_confidence(store):
  """A verified failure should push confidence below neutral."""
  store.record_provisional(**_zone_params())
  zone = store.record_verified_outcome(
    game_id="test-game-pg", profile_id="test-profile",
    selector_key="draw_button", success=False,
  )
  assert zone is not None
  assert zone.failure_count == 1
  assert zone.clickability_score < 0.5, (
    f"verified failure should demote confidence < 0.5, got {zone.clickability_score}"
  )


def test_multiple_provisionals_stay_neutral(store):
  """Multiple provisionals without verification should stay near 0.5."""
  for _ in range(5):
    store.record_provisional(**_zone_params())
  zones = store.list_zones("test-game-pg")
  assert len(zones) == 1
  assert 0.4 <= zones[0].clickability_score <= 0.65


def test_success_failure_mix_produces_moderate_confidence(store):
  """Mix of successes and failures produces moderate confidence."""
  store.record_provisional(**_zone_params())
  for _ in range(3):
    store.record_verified_outcome(
      game_id="test-game-pg", profile_id="test-profile",
      selector_key="draw_button", success=True,
    )
  for _ in range(2):
    store.record_verified_outcome(
      game_id="test-game-pg", profile_id="test-profile",
      selector_key="draw_button", success=False,
    )
  zones = store.list_zones("test-game-pg")
  assert len(zones) == 1
  z = zones[0]
  assert z.success_count == 3
  assert z.failure_count == 2
  # 3/5 = 0.6 verified rate, should be moderate
  assert 0.5 < z.clickability_score < 0.8


def test_one_failure_does_not_permanently_poison(store):
  """A single failure followed by successes recovers confidence."""
  store.record_provisional(**_zone_params())
  store.record_verified_outcome(
    game_id="test-game-pg", profile_id="test-profile",
    selector_key="draw_button", success=False,
  )
  for _ in range(5):
    store.record_verified_outcome(
      game_id="test-game-pg", profile_id="test-profile",
      selector_key="draw_button", success=True,
    )
  zones = store.list_zones("test-game-pg")
  assert zones[0].clickability_score > 0.7, (
    f"5 successes after 1 failure should recover, got {zones[0].clickability_score}"
  )


# ── Upsert / conflict key behavior ──

def test_upsert_merges_nearby_zones(store):
  """Two upserts with nearby bounding boxes should merge, not duplicate."""
  store.record_provisional(**_zone_params())
  # Same zone, slightly different coords (within proximity)
  params2 = _zone_params()
  params2["bounding_box"] = BoundingBox(left=102, top=202, right=202, bottom=252)
  store.record_provisional(**params2)
  zones = store.list_zones("test-game-pg")
  assert len(zones) == 1, f"should merge into 1 zone, got {len(zones)}"
  assert zones[0].clickability_score >= 0.5  # provisional count went up


def test_different_actions_create_separate_zones(store):
  """Different selector_keys create distinct zones."""
  store.record_provisional(**_zone_params())
  params2 = _zone_params()
  params2["selector_key"] = "play_button"
  params2["semantic_guess"] = "play_card"
  store.record_provisional(**params2)
  zones = store.list_zones("test-game-pg")
  assert len(zones) == 2


# ── Lookup ──

def test_find_matching_domain_action_returns_high_confidence(store):
  """find_matching_domain_action only returns zones with confidence >= 0.4."""
  store.record_provisional(**_zone_params())
  # Create a low-confidence zone (many failures)
  params2 = _zone_params()
  params2["selector_key"] = "bad_button"
  params2["semantic_guess"] = "draw"
  store.record_provisional(**params2)
  for _ in range(10):
    store.record_verified_outcome(
      game_id="test-game-pg", profile_id="test-profile",
      selector_key="bad_button", success=False,
    )

  results = store.find_matching_domain_action("test-game-pg", "draw")
  # Should only return the good zone, not the bad one
  labels = [z.label for z in results]
  assert "draw_button" in labels
  assert "bad_button" not in labels


# ── Reset / inspection ──

def test_reset_game_clears_all_zones(store):
  store.record_provisional(**_zone_params())
  assert len(store.list_zones("test-game-pg")) == 1
  deleted = store.reset_game("test-game-pg")
  assert deleted == 1
  assert len(store.list_zones("test-game-pg")) == 0


def test_reset_profile_clears_only_that_profile(store):
  store.record_provisional(**_zone_params())
  params2 = _zone_params()
  params2["profile_id"] = "other-profile"
  store.record_provisional(**params2)
  assert len(store.list_zones("test-game-pg")) == 2
  deleted = store.reset_profile("test-game-pg", "test-profile")
  assert deleted == 1
  remaining = store.list_zones("test-game-pg")
  assert len(remaining) == 1
  assert remaining[0].profile_id == "other-profile"


def test_inspect_returns_human_readable(store):
  store.record_provisional(**_zone_params())
  store.record_verified_outcome(
    game_id="test-game-pg", profile_id="test-profile",
    selector_key="draw_button", success=True,
  )
  report = store.inspect("test-game-pg")
  assert len(report) == 1
  assert report[0]["selector_key"] == "draw_button"
  assert report[0]["success"] == 1
  assert report[0]["confidence"] > 0.5

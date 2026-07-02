"""Persistent store for learned interactive zones.

Zones are stored per game as a single JSON file under ``data/learned-zones``.
Writes are atomic (temp file + os.replace) so concurrent probes from the
adapter do not corrupt the file. The store is intentionally lightweight — no
database, no separate service — to minimize moving parts for the vertical slice.

Pure helpers (fingerprint, scoring) are module-level so they can be unit-tested
without touching the filesystem.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from uno_schemas.learned_zones import (
  BoundingBox,
  Clickability,
  LearnedZone,
  LearnedZoneMap,
  Resolution,
  ZoneType,
)

DEFAULT_STORE_DIR = Path("data/learned-zones")
_PROXIMITY_PX = 12.0  # two boxes whose centers are within this many px are the same zone
_FINGERPRINT_SIZE = 8  # average-hash grid (8x8 -> 64 bits)


def compute_screen_fingerprint(image_path: str, size: int = _FINGERPRINT_SIZE) -> str:
  """Compute a perceptual average-hash fingerprint of a screenshot.

  Uses PIL only (no opencv). Returns a hex string. Two screenshots of the same
  screen layout hash close to each other; animating cards change only part of
  the frame so the hash stays stable enough to match a learned zone to a screen.

  Returns an empty string if the image cannot be read (e.g. PIL missing), so
  callers can treat fingerprint-matching as a best-effort enhancement.
  """
  try:
    from PIL import Image
  except ImportError:
    return ""

  try:
    img = Image.open(image_path).convert("L").resize((size, size))
    pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, px in enumerate(pixels):
      if px >= avg:
        bits |= 1 << i
    return f"{bits:0{size * size // 4}x}"
  except Exception:
    return ""


def hamming_hex(a: str, b: str) -> int | None:
  """Hamming distance between two hex fingerprints. None if incomparable."""
  if not a or not b or len(a) != len(b):
    return None
  try:
    return bin(int(a, 16) ^ int(b, 16)).count("1")
  except ValueError:
    return None


def fingerprint_similarity(a: str, b: str, bits: int = _FINGERPRINT_SIZE * _FINGERPRINT_SIZE) -> float:
  """0..1 similarity. 1.0 = identical layout, 0.0 = maximally different."""
  dist = hamming_hex(a, b)
  if dist is None:
    return 0.0
  return 1.0 - dist / bits


def boxes_overlap_or_near(a: BoundingBox, b: BoundingBox, proximity: float = _PROXIMITY_PX) -> bool:
  """True if two boxes overlap or their centers are within ``proximity`` px."""
  if (
    a.left - proximity <= b.right
    and b.left - proximity <= a.right
    and a.top - proximity <= b.bottom
    and b.top - proximity <= a.bottom
  ):
    return True
  return False


def update_clickability_score(zone: LearnedZone) -> LearnedZone:
  """Recompute clickability_score from empirical probes + explicit clickability.

  Score blends an empirical success-rate estimate with the operator-assigned
  clickability. A zone with no probes yet keeps its prior (0.5 conditional).
  """
  n = zone.total_probes
  if n == 0:
    base = 0.5
  else:
    base = zone.empirical_success_rate
  if zone.clickability == Clickability.CLICKABLE:
    base = max(base, 0.6) if n == 0 else 0.5 * base + 0.5
  elif zone.clickability == Clickability.NON_CLICKABLE:
    base = 0.0
  zone.clickability_score = max(0.0, min(1.0, base))
  return zone


class LearnedZoneStore:
  """File-backed store of learned zones, keyed by game_id."""

  def __init__(self, store_dir: str | Path | None = None) -> None:
    self.store_dir = Path(store_dir) if store_dir else DEFAULT_STORE_DIR

  def _path(self, game_id: str) -> Path:
    safe = "".join(c for c in game_id if c.isalnum() or c in "-_") or "unknown"
    return self.store_dir / f"{safe}.json"

  def load(self, game_id: str) -> LearnedZoneMap:
    """Load the full map for a game. Returns an empty map if absent."""
    path = self._path(game_id)
    if not path.exists():
      return LearnedZoneMap(
        game_id=game_id,
        resolution=Resolution(width=0, height=0),
        zones=[],
        updated_at_ms=0,
      )
    try:
      raw = json.loads(path.read_text(encoding="utf-8"))
      return LearnedZoneMap.model_validate(raw)
    except Exception:
      return LearnedZoneMap(
        game_id=game_id,
        resolution=Resolution(width=0, height=0),
        zones=[],
        updated_at_ms=0,
      )

  def _save(self, m: LearnedZoneMap) -> None:
    self.store_dir.mkdir(parents=True, exist_ok=True)
    path = self._path(m.game_id)
    m.updated_at_ms = int(time.time() * 1000)
    # Atomic write: temp in same dir, then os.replace.
    fd, tmp = tempfile.mkstemp(dir=str(self.store_dir), suffix=".tmp")
    try:
      with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(m.model_dump_json(indent=2))
      os.replace(tmp, path)
    except Exception:
      try:
        os.unlink(tmp)
      except OSError:
        pass
      raise

  def upsert(self, zone: LearnedZone) -> LearnedZone:
    """Insert or update a zone (matched by proximity to an existing box)."""
    m = self.load(zone.game_id)
    if m.resolution.width == 0:
      m.resolution = zone.resolution
    updated = update_clickability_score(zone)
    for i, existing in enumerate(m.zones):
      if boxes_overlap_or_near(existing.bounding_box, updated.bounding_box):
        # Merge: keep counts, prefer non-empty metadata, update geometry.
        existing.bounding_box = updated.bounding_box
        existing.click_point = updated.click_point
        existing.updated_at_ms = updated.updated_at_ms
        existing.success_count += updated.success_count
        existing.failure_count += updated.failure_count
        existing.last_verified_result = updated.last_verified_result or existing.last_verified_result
        if updated.label:
          existing.label = updated.label
        if updated.semantic_guess:
          existing.semantic_guess = updated.semantic_guess
        if updated.zone_type != ZoneType.UNKNOWN:
          existing.zone_type = updated.zone_type
        if updated.clickability != Clickability.CONDITIONAL:
          existing.clickability = updated.clickability
        existing.screen_fingerprint = updated.screen_fingerprint or existing.screen_fingerprint
        existing.profile_id = updated.profile_id or existing.profile_id
        m.zones[i] = update_clickability_score(existing)
        self._save(m)
        return m.zones[i]
    m.zones.append(updated)
    self._save(m)
    return updated

  def record_outcome(self, game_id: str, zone_id: str, success: bool) -> LearnedZone | None:
    """Record a probe outcome (success/failure) on an existing zone."""
    m = self.load(game_id)
    for z in m.zones:
      if z.zone_id == zone_id:
        if success:
          z.success_count += 1
          z.last_verified_result = "success"
        else:
          z.failure_count += 1
          z.last_verified_result = "failure"
        z.updated_at_ms = int(time.time() * 1000)
        update_clickability_score(z)
        self._save(m)
        return z
    return None

  def forget(self, game_id: str, zone_id: str) -> bool:
    m = self.load(game_id)
    before = len(m.zones)
    m.zones = [z for z in m.zones if z.zone_id != zone_id]
    if len(m.zones) != before:
      self._save(m)
      return True
    return False

  def find_by_label(self, game_id: str, label: str) -> list[LearnedZone]:
    """Find zones whose label (case-insensitive) matches."""
    m = self.load(game_id)
    needle = label.lower().strip()
    return [z for z in m.zones if needle and needle in (z.label or "").lower()]

  def find_matching_domain_action(self, game_id: str, action: str) -> list[LearnedZone]:
    """Find zones likely relevant to a domain action (e.g. 'draw' -> draw_button)."""
    m = self.load(game_id)
    key = action.lower().strip()
    # Map domain actions to expected label fragments.
    fragments = _action_label_fragments(key)
    hits: list[LearnedZone] = []
    for z in m.zones:
      lbl = (z.label or "").lower()
      sem = (z.semantic_guess or "").lower()
      if any(frag and (frag in lbl or frag in sem) for frag in fragments):
        hits.append(z)
    return hits

  def match_fingerprint(
    self, game_id: str, fingerprint: str, threshold: float = 0.8
  ) -> list[LearnedZone]:
    """Return zones whose stored fingerprint is similar to the given one."""
    if not fingerprint:
      return []
    m = self.load(game_id)
    out: list[LearnedZone] = []
    for z in m.zones:
      if not z.screen_fingerprint:
        continue
      if fingerprint_similarity(z.screen_fingerprint, fingerprint) >= threshold:
        out.append(z)
    return out

  def list_zones(self, game_id: str) -> list[LearnedZone]:
    return self.load(game_id).zones


# Domain-action -> label fragment mapping for UNO. Kept small and game-agnostic
# enough to generalize; games can extend via their plugin later.
def _action_label_fragments(action: str) -> list[str]:
  table = {
    "draw": ["draw", "deck", "pile"],
    "draw_card": ["draw", "deck", "pile"],
    "play_card": ["play", "card", "hand"],
    "pass": ["pass", "skip turn"],
    "pass_turn": ["pass", "skip turn"],
    "choose_color": ["color", "red", "blue", "green", "yellow", "wild"],
    "call_uno": ["uno"],
    "click_play": ["play", "start", "begin", "new game", "match"],
    "click_start": ["start", "begin", "new game", "play"],
    "click_ready": ["ready", "prepare", "waiting"],
    "start_match": ["start", "play", "match", "begin"],
    "join_match": ["join", "enter", "match"],
    "inspect_screen": [],
  }
  return table.get(action, [action] if action else [])


def make_zone(
  game_id: str,
  resolution: Resolution,
  bounding_box: BoundingBox,
  *,
  label: str = "",
  zone_type: ZoneType = ZoneType.UNKNOWN,
  clickability: Clickability = Clickability.CONDITIONAL,
  semantic_guess: str = "",
  screen_fingerprint: str | None = None,
  profile_id: str | None = None,
  source: str = "discovered",
) -> LearnedZone:
  """Convenience factory: fills timestamps, ids, and click_point (box center)."""
  now = int(time.time() * 1000)
  return LearnedZone(
    zone_id=str(uuid4()),
    game_id=game_id,
    screen_fingerprint=screen_fingerprint,
    resolution=resolution,
    bounding_box=bounding_box,
    click_point=bounding_box.center,
    label=label,
    semantic_guess=semantic_guess,
    zone_type=zone_type,
    clickability=clickability,
    created_at_ms=now,
    updated_at_ms=now,
    profile_id=profile_id,
    source=source,
  )

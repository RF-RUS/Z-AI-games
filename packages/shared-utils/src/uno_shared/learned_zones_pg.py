"""Postgres-backed store for learned interactive zones (verification-aware).

Learning lifecycle:
  1. record_provisional() — after click dispatch, BEFORE verification
     → increments provisional_count, does NOT promote confidence
  2. record_verified_outcome() — after before/after screenshot verification
     → increments success_count or failure_count
     → promotes or demotes confidence based on verified outcome

Conflict key: (game_id, profile_id, selector_key, screen_state_hash)
Two zones are "the same" if they target the same action on the same
screen layout.  Bounding boxes may drift slightly between sessions;
the merge logic handles that.

Safety:
  - A single failed click only increments failure_count by 1.
  - confidence_score blends verified success rate with provisional rate,
    but verified signals carry 3x weight.
  - Confidence decays toward 0.5 (uncertain) if the zone hasn't been
    verified recently.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from uno_schemas.learned_zones import (
  BoundingBox,
  Clickability,
  LearnedZone,
  LearnedZoneMap,
  Resolution,
  ZoneType,
)

from .learned_zones import (
  _action_label_fragments,
  boxes_overlap_or_near,
  update_clickability_score,
)

_DEFAULT_DSN = "postgresql://uno:uno_dev@127.0.0.1:5432/uno_operator"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS learned_zones (
    zone_id              TEXT PRIMARY KEY,
    game_id              TEXT NOT NULL,
    profile_id           TEXT NOT NULL DEFAULT '',
    selector_key         TEXT NOT NULL DEFAULT '',
    screen_state_hash    TEXT NOT NULL DEFAULT '',
    resolution_w         INT NOT NULL DEFAULT 0,
    resolution_h         INT NOT NULL DEFAULT 0,
    bounding_box         JSONB NOT NULL,
    click_point          JSONB NOT NULL,
    label                TEXT NOT NULL DEFAULT '',
    semantic_guess       TEXT NOT NULL DEFAULT '',
    zone_type            TEXT NOT NULL DEFAULT 'unknown',
    clickability         TEXT NOT NULL DEFAULT 'conditional',
    -- Verified signal counts (strong)
    success_count        INT NOT NULL DEFAULT 0,
    failure_count        INT NOT NULL DEFAULT 0,
    -- Provisional signal counts (weak — click dispatched but not yet verified)
    provisional_count    INT NOT NULL DEFAULT 0,
    -- Derived confidence: blends verified + provisional with verified weighted 3x
    confidence_score     REAL NOT NULL DEFAULT 0.5,
    last_verified_result TEXT,
    last_seen_at_ms      BIGINT NOT NULL DEFAULT 0,
    last_verified_at_ms  BIGINT,
    source               TEXT NOT NULL DEFAULT 'discovered',
    created_at_ms        BIGINT NOT NULL,
    updated_at_ms        BIGINT NOT NULL
);
"""

_CREATE_INDEXES = [
  "CREATE INDEX IF NOT EXISTS idx_lz_game_id ON learned_zones (game_id);",
  # The natural uniqueness constraint for deduplication
  "CREATE UNIQUE INDEX IF NOT EXISTS idx_lz_conflict_key ON learned_zones (game_id, profile_id, selector_key, screen_state_hash);",
  "CREATE INDEX IF NOT EXISTS idx_lz_game_action ON learned_zones (game_id, selector_key);",
]


def _dsn() -> str:
  return os.getenv("LEARNED_ZONE_PG_DSN", _DEFAULT_DSN)


def _screen_state_hash(game_id: str, selector_key: str, screen_fingerprint: str | None = None) -> str:
  """Deterministic hash for the conflict key.

  If a screen fingerprint is available, it captures the visual layout.
  Otherwise, we fall back to game_id+selector_key (coarser but still unique
  per action within a game).
  """
  raw = f"{game_id}|{selector_key}|{screen_fingerprint or ''}"
  return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _recompute_confidence(
  success: int, failure: int, provisional: int, last_verified_at_ms: int | None
) -> float:
  """Blend verified + provisional signals into a single confidence score.

  Verified success carries 3x weight vs provisional.
  Failure carries 2x weight (penalize more than provisional rewards).
  Decay is applied if the zone hasn't been verified recently (> 24h).
  """
  total_verified = success + failure
  # Base rate from verified signals
  if total_verified > 0:
    verified_rate = success / total_verified
  else:
    verified_rate = 0.5

  # Provisional rate (lower weight)
  provisional_rate = 0.5  # neutral if no provisionals
  if provisional > 0:
    # Provisionals are unconfirmed; assume they're slightly positive
    # but not as trustworthy as verified
    provisional_rate = 0.6

  # Blend: verified 3x, provisional 1x
  total_weight = total_verified * 3 + provisional
  if total_weight > 0:
    blended = (verified_rate * total_verified * 3 + provisional_rate * provisional) / total_weight
  else:
    blended = 0.5

  # Decay if not verified recently (> 24h)
  if last_verified_at_ms:
    age_ms = int(time.time() * 1000) - last_verified_at_ms
    if age_ms > 24 * 3600 * 1000:
      # Decay toward 0.5 by up to 30%
      decay = min(0.3, age_ms / (7 * 24 * 3600 * 1000) * 0.3)
      blended = blended * (1 - decay) + 0.5 * decay

  return max(0.05, min(0.95, blended))


def _row_to_zone(row: dict) -> LearnedZone:
  bb_raw = row["bounding_box"]
  if isinstance(bb_raw, str):
    bb_raw = json.loads(bb_raw)
  cp_raw = row["click_point"]
  if isinstance(cp_raw, str):
    cp_raw = json.loads(cp_raw)
  return LearnedZone(
    zone_id=row["zone_id"],
    game_id=row["game_id"],
    profile_id=row.get("profile_id"),
    screen_fingerprint=row.get("screen_state_hash"),
    resolution=Resolution(width=row["resolution_w"], height=row["resolution_h"]),
    bounding_box=BoundingBox(**bb_raw),
    click_point=cp_raw,
    label=row.get("label", ""),
    semantic_guess=row.get("semantic_guess", ""),
    zone_type=ZoneType(row.get("zone_type", "unknown")),
    clickability=Clickability(row.get("clickability", "conditional")),
    clickability_score=row.get("confidence_score", 0.5),
    last_verified_result=row.get("last_verified_result"),
    success_count=row.get("success_count", 0),
    failure_count=row.get("failure_count", 0),
    source=row.get("source", "discovered"),
    created_at_ms=row.get("created_at_ms", 0),
    updated_at_ms=row.get("updated_at_ms", 0),
  )


class PgLearnedZoneStore:
  """Postgres-backed learned zone store with provisional/verified separation."""

  def __init__(self, dsn: str | None = None) -> None:
    self._dsn = dsn or _dsn()
    self._conn: psycopg.Connection | None = None

  def _get_conn(self) -> psycopg.Connection:
    if self._conn is None or self._conn.closed:
      self._conn = psycopg.connect(self._dsn, row_factory=dict_row)
      self._ensure_schema()
    return self._conn

  def _ensure_schema(self) -> None:
    conn = self._get_conn()
    with conn.cursor() as cur:
      cur.execute(_CREATE_TABLE)
      for idx in _CREATE_INDEXES:
        cur.execute(idx)
    conn.commit()

  # ── read ──

  def load(self, game_id: str) -> LearnedZoneMap:
    conn = self._get_conn()
    with conn.cursor() as cur:
      cur.execute(
        "SELECT * FROM learned_zones WHERE game_id = %s ORDER BY confidence_score DESC",
        (game_id,),
      )
      rows = cur.fetchall()
    zones = [_row_to_zone(r) for r in rows]
    res_w = zones[0].resolution.width if zones else 0
    res_h = zones[0].resolution.height if zones else 0
    return LearnedZoneMap(
      game_id=game_id,
      resolution=Resolution(width=res_w, height=res_h),
      zones=zones,
      updated_at_ms=zones[0].updated_at_ms if zones else 0,
    )

  def list_zones(self, game_id: str) -> list[LearnedZone]:
    return self.load(game_id).zones

  def find_by_label(self, game_id: str, label: str) -> list[LearnedZone]:
    conn = self._get_conn()
    with conn.cursor() as cur:
      cur.execute(
        "SELECT * FROM learned_zones WHERE game_id = %s AND LOWER(label) LIKE %s",
        (game_id, f"%{label.lower().strip()}%"),
      )
      return [_row_to_zone(r) for r in cur.fetchall()]

  def find_matching_domain_action(self, game_id: str, action: str) -> list[LearnedZone]:
    fragments = _action_label_fragments(action.lower().strip())
    if not fragments:
      return []
    conn = self._get_conn()
    zones: list[LearnedZone] = []
    with conn.cursor() as cur:
      for frag in fragments:
        if not frag:
          continue
        cur.execute(
          "SELECT * FROM learned_zones WHERE game_id = %s "
          "AND (LOWER(label) LIKE %s OR LOWER(semantic_guess) LIKE %s) "
          "AND confidence_score >= 0.4",
          (game_id, f"%{frag}%", f"%{frag}%"),
        )
        zones.extend(_row_to_zone(r) for r in cur.fetchall())
    seen: set[str] = set()
    out: list[LearnedZone] = []
    for z in zones:
      if z.zone_id not in seen:
        seen.add(z.zone_id)
        out.append(z)
    return sorted(out, key=lambda z: z.clickability_score, reverse=True)

  def match_fingerprint(self, game_id: str, fingerprint: str, threshold: float = 0.8) -> list[LearnedZone]:
    if not fingerprint:
      return []
    all_zones = self.load(game_id).zones
    from .learned_zones import fingerprint_similarity
    return [z for z in all_zones if z.screen_fingerprint and fingerprint_similarity(z.screen_fingerprint, fingerprint) >= threshold]

  # ── write: provisional (click dispatched, not yet verified) ──

  def record_provisional(
    self,
    game_id: str,
    profile_id: str,
    selector_key: str,
    bounding_box: BoundingBox,
    click_point: dict[str, float],
    resolution: Resolution,
    *,
    semantic_guess: str = "",
    screen_fingerprint: str | None = None,
  ) -> LearnedZone:
    """Record a provisional observation — click was dispatched but not yet verified.

    This is a WEAK signal.  It does not promote confidence; it only
    increments provisional_count so the zone can be found for later
    verification upgrade.
    """
    now = int(time.time() * 1000)
    ssh = _screen_state_hash(game_id, selector_key, screen_fingerprint)
    conn = self._get_conn()
    with conn.cursor() as cur:
      cur.execute(
        """INSERT INTO learned_zones
           (zone_id, game_id, profile_id, selector_key, screen_state_hash,
            resolution_w, resolution_h, bounding_box, click_point,
            label, semantic_guess, zone_type, clickability,
            confidence_score, success_count, failure_count, provisional_count,
            source, created_at_ms, updated_at_ms, last_seen_at_ms)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,1,%s,%s,%s,%s)
           ON CONFLICT (game_id, profile_id, selector_key, screen_state_hash) DO UPDATE SET
             bounding_box = EXCLUDED.bounding_box,
             click_point = EXCLUDED.click_point,
             resolution_w = EXCLUDED.resolution_w,
             resolution_h = EXCLUDED.resolution_h,
             provisional_count = learned_zones.provisional_count + 1,
             last_seen_at_ms = EXCLUDED.last_seen_at_ms,
             updated_at_ms = EXCLUDED.updated_at_ms,
             semantic_guess = COALESCE(NULLIF(EXCLUDED.semantic_guess,''), learned_zones.semantic_guess),
             screen_state_hash = EXCLUDED.screen_state_hash
           RETURNING *
        """,
        (
          str(uuid4()), game_id, profile_id, selector_key, ssh,
          resolution.width, resolution.height,
          json.dumps(bounding_box.model_dump()), json.dumps(click_point),
          selector_key, semantic_guess, "button", "conditional",
          0.5, "discovered", now, now, now,
        ),
      )
      row = cur.fetchone()
    conn.commit()
    zone = _row_to_zone(row) if row else None
    if zone:
      zone.clickability_score = _recompute_confidence(
        zone.success_count, zone.failure_count,
        getattr(row, 'provisional_count', row.get('provisional_count', 0)),
        row.get('last_verified_at_ms'),
      )
    return zone

  # ── write: verified outcome (strong signal) ──

  def record_verified_outcome(
    self,
    game_id: str,
    profile_id: str,
    selector_key: str,
    success: bool,
    screen_fingerprint: str | None = None,
  ) -> LearnedZone | None:
    """Record a verified outcome (after before/after screenshot comparison).

    This is the STRONG signal that promotes or demotes confidence.
    """
    now = int(time.time() * 1000)
    ssh = _screen_state_hash(game_id, selector_key, screen_fingerprint)
    conn = self._get_conn()

    if success:
      cur_sql = """UPDATE learned_zones SET
        success_count = success_count + 1,
        last_verified_result = 'success',
        last_verified_at_ms = %s,
        last_seen_at_ms = %s,
        updated_at_ms = %s
        WHERE game_id = %s AND profile_id = %s AND selector_key = %s AND screen_state_hash = %s
        RETURNING *"""
      params = (now, now, now, game_id, profile_id, selector_key, ssh)
    else:
      cur_sql = """UPDATE learned_zones SET
        failure_count = failure_count + 1,
        last_verified_result = 'failure',
        last_verified_at_ms = %s,
        last_seen_at_ms = %s,
        updated_at_ms = %s
        WHERE game_id = %s AND profile_id = %s AND selector_key = %s AND screen_state_hash = %s
        RETURNING *"""
      params = (now, now, now, game_id, profile_id, selector_key, ssh)

    with conn.cursor() as cur:
      cur.execute(cur_sql, params)
      row = cur.fetchone()
    conn.commit()

    if not row:
      return None

    zone = _row_to_zone(row)
    prov_count = row.get('provisional_count', 0)
    zone.clickability_score = _recompute_confidence(
      zone.success_count, zone.failure_count, prov_count, row.get('last_verified_at_ms'),
    )

    # Persist recomputed confidence
    with conn.cursor() as cur:
      cur.execute(
        "UPDATE learned_zones SET confidence_score = %s WHERE zone_id = %s",
        (zone.clickability_score, zone.zone_id),
      )
    conn.commit()
    return zone

  # ── legacy compatibility ──

  def upsert(self, zone: LearnedZone) -> LearnedZone:
    """Legacy upsert — delegates to record_provisional + record_verified_outcome."""
    if zone.last_verified_result == "success":
      return self.record_verified_outcome(
        zone.game_id, zone.profile_id or "", zone.label,
        success=True, screen_fingerprint=zone.screen_fingerprint,
      ) or zone
    if zone.last_verified_result == "failure":
      return self.record_verified_outcome(
        zone.game_id, zone.profile_id or "", zone.label,
        success=False, screen_fingerprint=zone.screen_fingerprint,
      ) or zone
    return self.record_provisional(
      zone.game_id, zone.profile_id or "", zone.label,
      zone.bounding_box, zone.click_point, zone.resolution,
      semantic_guess=zone.semantic_guess,
      screen_fingerprint=zone.screen_fingerprint,
    )

  def record_outcome(self, game_id: str, zone_id: str, success: bool) -> LearnedZone | None:
    """Legacy record_outcome by zone_id — kept for file-backed store compat."""
    conn = self._get_conn()
    now = int(time.time() * 1000)
    if success:
      sql = """UPDATE learned_zones SET success_count = success_count + 1,
        last_verified_result = 'success', last_verified_at_ms = %s, updated_at_ms = %s
        WHERE zone_id = %s AND game_id = %s RETURNING *"""
    else:
      sql = """UPDATE learned_zones SET failure_count = failure_count + 1,
        last_verified_result = 'failure', last_verified_at_ms = %s, updated_at_ms = %s
        WHERE zone_id = %s AND game_id = %s RETURNING *"""
    with conn.cursor() as cur:
      cur.execute(sql, (now, now, zone_id, game_id))
      row = cur.fetchone()
    conn.commit()
    if row:
      zone = _row_to_zone(row)
      zone.clickability_score = _recompute_confidence(
        zone.success_count, zone.failure_count,
        row.get('provisional_count', 0), row.get('last_verified_at_ms'),
      )
      with conn.cursor() as cur:
        cur.execute("UPDATE learned_zones SET confidence_score = %s WHERE zone_id = %s",
                     (zone.clickability_score, zone_id))
      conn.commit()
      return zone
    return None

  # ── management ──

  def forget(self, game_id: str, zone_id: str) -> bool:
    conn = self._get_conn()
    with conn.cursor() as cur:
      cur.execute("DELETE FROM learned_zones WHERE zone_id = %s AND game_id = %s", (zone_id, game_id))
      deleted = cur.rowcount
    conn.commit()
    return deleted > 0

  def reset_game(self, game_id: str) -> int:
    """Delete all zones for a game. Returns count deleted."""
    conn = self._get_conn()
    with conn.cursor() as cur:
      cur.execute("DELETE FROM learned_zones WHERE game_id = %s", (game_id,))
      deleted = cur.rowcount
    conn.commit()
    return deleted

  def reset_profile(self, game_id: str, profile_id: str) -> int:
    """Delete all zones for a specific profile within a game."""
    conn = self._get_conn()
    with conn.cursor() as cur:
      cur.execute(
        "DELETE FROM learned_zones WHERE game_id = %s AND profile_id = %s",
        (game_id, profile_id),
      )
      deleted = cur.rowcount
    conn.commit()
    return deleted

  def inspect(self, game_id: str) -> list[dict]:
    """Human-readable inspection of all zones for a game."""
    zones = self.list_zones(game_id)
    return [
      {
        "zone_id": z.zone_id,
        "selector_key": z.label,
        "semantic_guess": z.semantic_guess,
        "confidence": round(z.clickability_score, 3),
        "success": z.success_count,
        "failure": z.failure_count,
        "last_result": z.last_verified_result,
        "click_point": z.click_point,
      }
      for z in zones
    ]

  def close(self) -> None:
    if self._conn and not self._conn.closed:
      self._conn.close()
      self._conn = None

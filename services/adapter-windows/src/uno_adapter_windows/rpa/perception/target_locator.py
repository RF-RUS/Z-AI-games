"""Target acquisition cascade: UIA -> learned memory -> layout_targets.

Priority:
  1. UIA match (auto_id/title from profile.selectors)
  2. action_mappings (title match)
  3. UIA substring coordinate fallback
  4. Learned memory (Postgres-backed zones from past successful actions)
  5. Static layout_targets (cold-start fallback from profile JSON)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from uno_adapter_windows.extraction import find_matching_nodes
from uno_schemas.adapter_windows import (
  TargetAcquisitionMethod,
  UiNodeSnapshot,
  UITarget,
  UITargetSet,
  WindowsAdapterProfile,
)

_trace_log = logging.getLogger("target_locator.trace")


@dataclass
class ResolutionTrace:
  """Lightweight diagnostics for each target resolution attempt."""
  source: str = ""           # "uia" | "uia_mapping" | "uia_coordinate" | "learned_memory" | "layout_targets" | "none"
  selector_key: str = ""
  confidence: float = 0.0
  screen_state_hash: str = ""
  zone_id: str = ""          # learned zone id if source=learned_memory
  zone_label: str = ""
  zone_confidence: float = 0.0
  zone_success: int = 0
  zone_failure: int = 0
  zone_provisional: int = 0
  zone_verified_backed: bool = False
  error: str = ""

  def summary(self) -> str:
    parts = [f"source={self.source}", f"key={self.selector_key}", f"conf={self.confidence:.2f}"]
    if self.source == "learned_memory":
      parts.append(f"zone={self.zone_label}(id={self.zone_id[:8]})")
      parts.append(f"zone_conf={self.zone_confidence:.2f}")
      parts.append(f"ok={self.zone_success}/fail={self.zone_failure}/prov={self.zone_provisional}")
      parts.append(f"verified={self.zone_verified_backed}")
    return " | ".join(parts)


def _center(bounds: dict[str, float] | None) -> dict[str, float] | None:
  if not bounds:
    return None
  return {
    "x": (bounds["left"] + bounds["right"]) / 2,
    "y": (bounds["top"] + bounds["bottom"]) / 2,
  }


def _selector_keys_to_try(selector_key: str, profile: WindowsAdapterProfile) -> list[str]:
  keys: list[str] = [selector_key]
  aliases = {"draw": "draw_button", "play_red_five": "play_button"}
  if selector_key in aliases:
    keys.append(aliases[selector_key])
  mapped_title = profile.action_mappings.get(selector_key)
  if mapped_title:
    for sk, sel in profile.selectors.items():
      if sel.title == mapped_title and sk not in keys:
        keys.append(sk)
  return keys


def _target_from_node(
  selector_key: str,
  node: UiNodeSnapshot,
  method: TargetAcquisitionMethod,
  confidence: float,
) -> UITarget:
  bounds = node.bounds
  return UITarget(
    selector_key=selector_key,
    label=node.name or selector_key,
    method=method,
    confidence=confidence,
    bounds=bounds,
    click_point=_center(bounds),
    auto_id=node.auto_id,
    title=node.name,
  )


def _target_from_learned_zone(
  selector_key: str,
  zone,  # LearnedZone
  window_bounds: dict[str, float],
  client_bounds: dict[str, float] | None = None,
) -> UITarget:
  """Convert a LearnedZone to a UITarget using its normalized ratios.

  Resolves ratios against client_bounds when available (the actual content
  area), falling back to window_bounds.  This prevents title-bar / border
  offsets from shifting click targets into the wrong area.
  """
  # Use client_bounds for ratio resolution if available, else window_bounds
  resolve_bounds = client_bounds or window_bounds
  width = resolve_bounds["right"] - resolve_bounds["left"]
  height = resolve_bounds["bottom"] - resolve_bounds["top"]
  left, top = resolve_bounds["left"], resolve_bounds["top"]

  # Re-compute absolute coordinates from the stored bounding box ratios
  bb = zone.bounding_box
  click = zone.click_point
  # If the stored zone has absolute coords from a different resolution,
  # convert to ratios first
  if zone.resolution.width > 0 and zone.resolution.height > 0:
    x_ratio = (bb.left + bb.width / 2) / zone.resolution.width
    y_ratio = (bb.top + bb.height / 2) / zone.resolution.height
  else:
    x_ratio = click.get("x", 0.5)
    y_ratio = click.get("y", 0.5)

  abs_x = left + width * x_ratio
  abs_y = top + height * y_ratio
  pad = min(width, height) * 0.04
  bounds = {
    "left": abs_x - pad, "top": abs_y - pad,
    "right": abs_x + pad, "bottom": abs_y + pad,
  }

  # Confidence from empirical success rate
  confidence = zone.clickability_score

  return UITarget(
    selector_key=selector_key,
    label=zone.label or selector_key,
    method=TargetAcquisitionMethod.COORDINATE,
    confidence=confidence,
    bounds=bounds,
    click_point={"x": abs_x, "y": abs_y},
    title=zone.label,
  )


def locate_selector(
  selector_key: str,
  profile: WindowsAdapterProfile,
  nodes: list[UiNodeSnapshot],
  *,
  allow_coordinate_fallback: bool = False,
  window_bounds: dict[str, float] | None = None,
  client_bounds: dict[str, float] | None = None,
  game_id: str | None = None,
  zone_store=None,
  trace: ResolutionTrace | None = None,
) -> UITarget | None:
  if trace:
    trace.selector_key = selector_key

  # Step 1-3: UIA cascade
  for key in _selector_keys_to_try(selector_key, profile):
    sel = profile.selectors.get(key)
    if sel:
      matched = find_matching_nodes(nodes, sel)
      if matched:
        t = _target_from_node(key, matched[0], TargetAcquisitionMethod.UIA, 0.9)
        if trace:
          trace.source = "uia"
          trace.confidence = t.confidence
        return t

    title = profile.action_mappings.get(key)
    if title:
      for n in nodes:
        if n.name and n.name == title:
          t = _target_from_node(key, n, TargetAcquisitionMethod.UIA, 0.82)
          if trace:
            trace.source = "uia_mapping"
            trace.confidence = t.confidence
          return t

    if allow_coordinate_fallback and sel:
      for n in nodes:
        if sel.title and n.name and (sel.title == n.name or sel.title.lower() in (n.name or "").lower()):
          t = _target_from_node(key, n, TargetAcquisitionMethod.COORDINATE, 0.45)
          if trace:
            trace.source = "uia_coordinate"
            trace.confidence = t.confidence
          return t

  # Step 4: Learned memory lookup
  if zone_store and game_id and window_bounds:
    try:
      zones = zone_store.find_matching_domain_action(game_id, selector_key)
      # Filter to high-confidence zones
      good = [z for z in zones if z.clickability_score >= 0.5 and z.failure_count < z.success_count + 3]
      if good:
        # Pick the zone with highest clickability_score
        best = max(good, key=lambda z: z.clickability_score)
        t = _target_from_learned_zone(selector_key, best, window_bounds, client_bounds)
        if trace:
          trace.source = "learned_memory"
          trace.confidence = t.confidence
          trace.screen_state_hash = best.screen_fingerprint or ""
          trace.zone_id = best.zone_id
          trace.zone_label = best.label
          trace.zone_confidence = best.clickability_score
          trace.zone_success = best.success_count
          trace.zone_failure = best.failure_count
          trace.zone_provisional = 0  # not stored separately in schema
          trace.zone_verified_backed = best.success_count > 0 or best.failure_count > 0
        _trace_log.info(
          "target_resolved selector=%s source=learned_memory zone_id=%s confidence=%.2f success=%d failure=%d",
          selector_key, best.zone_id[:8], best.clickability_score,
          best.success_count, best.failure_count,
        )
        return t
    except Exception as exc:
      if trace:
        trace.error = f"learned_lookup: {exc}"
      pass  # fall through to static layout

  # Step 5: Static layout_targets (cold-start fallback)
  if window_bounds:
    t = locate_layout_target(selector_key, profile, window_bounds, client_bounds)
    if t and trace:
      trace.source = "layout_targets"
      trace.confidence = t.confidence
    return t
  if trace:
    trace.source = "none"
  return None


def locate_layout_target(
  selector_key: str,
  profile: WindowsAdapterProfile,
  window_bounds: dict[str, float],
  client_bounds: dict[str, float] | None = None,
) -> UITarget | None:
  """Resolve layout_targets against client_bounds (content area), not window_bounds.

  Ratios are applied to the client rectangle so that title-bar / border
  offsets do not shift click targets into the chrome.
  """
  resolve_bounds = client_bounds or window_bounds
  width = resolve_bounds["right"] - resolve_bounds["left"]
  height = resolve_bounds["bottom"] - resolve_bounds["top"]
  if width <= 0 or height <= 0:
    return None
  for key in _selector_keys_to_try(selector_key, profile):
    layout = profile.layout_targets.get(key)
    if not layout:
      continue
    x_ratio = float(layout["x_ratio"])
    y_ratio = float(layout["y_ratio"])
    label = str(layout.get("label") or key)
    left, top = resolve_bounds["left"], resolve_bounds["top"]
    click = {"x": left + width * x_ratio, "y": top + height * y_ratio}
    pad = min(width, height) * 0.04
    bounds = {
      "left": click["x"] - pad,
      "top": click["y"] - pad,
      "right": click["x"] + pad,
      "bottom": click["y"] + pad,
    }
    return UITarget(
      selector_key=key,
      label=label,
      method=TargetAcquisitionMethod.COORDINATE,
      confidence=0.72,
      bounds=bounds,
      click_point=click,
      title=label,
    )
  return None


def locate_targets(
  profile: WindowsAdapterProfile,
  nodes: list[UiNodeSnapshot],
  *,
  selector_keys: list[str] | None = None,
  allow_coordinate_fallback: bool = False,
  sparse_tree: bool = False,
  game_id: str | None = None,
  zone_store=None,
) -> UITargetSet:
  keys = selector_keys or list(profile.selectors.keys()) + list(profile.action_mappings.keys())
  seen: set[str] = set()
  targets: list[UITarget] = []
  for key in keys:
    if key in seen:
      continue
    seen.add(key)
    t = locate_selector(
      key, profile, nodes,
      allow_coordinate_fallback=allow_coordinate_fallback,
      game_id=game_id, zone_store=zone_store,
    )
    if t:
      targets.append(t)
  return UITargetSet(targets=targets, sparse_tree=sparse_tree)


def locate_chat_input(profile: WindowsAdapterProfile, nodes: list[UiNodeSnapshot]) -> UITarget | None:
  sel = profile.chat_selectors.get("chat_input")
  if not sel:
    return None
  matched = find_matching_nodes(nodes, sel)
  if matched:
    return _target_from_node("chat_input", matched[0], TargetAcquisitionMethod.UIA, 0.85)
  return None


def parse_color_buttons(nodes: list[UiNodeSnapshot]) -> list[UITarget]:
  colors = ("red", "blue", "green", "yellow")
  out: list[UITarget] = []
  for n in nodes:
    name = (n.name or "").lower()
    for c in colors:
      if c in name and "button" in (n.control_type or "").lower():
        out.append(_target_from_node(f"choose_color_{c}", n, TargetAcquisitionMethod.UIA, 0.8))
  return out

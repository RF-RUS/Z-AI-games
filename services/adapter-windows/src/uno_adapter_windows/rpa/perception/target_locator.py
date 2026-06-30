"""Target acquisition cascade: UIA -> image stub -> coordinate fallback."""

from __future__ import annotations

from uno_adapter_windows.extraction import find_matching_nodes
from uno_schemas.adapter_windows import (
  TargetAcquisitionMethod,
  UiNodeSnapshot,
  UITarget,
  UITargetSet,
  WindowsAdapterProfile,
)


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


def locate_selector(
  selector_key: str,
  profile: WindowsAdapterProfile,
  nodes: list[UiNodeSnapshot],
  *,
  allow_coordinate_fallback: bool = False,
  window_bounds: dict[str, float] | None = None,
) -> UITarget | None:
  for key in _selector_keys_to_try(selector_key, profile):
    sel = profile.selectors.get(key)
    if sel:
      matched = find_matching_nodes(nodes, sel)
      if matched:
        return _target_from_node(key, matched[0], TargetAcquisitionMethod.UIA, 0.9)

    title = profile.action_mappings.get(key)
    if title:
      for n in nodes:
        if n.name and n.name == title:
          return _target_from_node(key, n, TargetAcquisitionMethod.UIA, 0.82)

    if allow_coordinate_fallback and sel:
      for n in nodes:
        if sel.title and n.name and (sel.title == n.name or sel.title.lower() in (n.name or "").lower()):
          return _target_from_node(key, n, TargetAcquisitionMethod.COORDINATE, 0.45)

  if window_bounds:
    return locate_layout_target(selector_key, profile, window_bounds)
  return None


def locate_layout_target(
  selector_key: str,
  profile: WindowsAdapterProfile,
  window_bounds: dict[str, float],
) -> UITarget | None:
  width = window_bounds["right"] - window_bounds["left"]
  height = window_bounds["bottom"] - window_bounds["top"]
  if width <= 0 or height <= 0:
    return None
  for key in _selector_keys_to_try(selector_key, profile):
    layout = profile.layout_targets.get(key)
    if not layout:
      continue
    x_ratio = float(layout["x_ratio"])
    y_ratio = float(layout["y_ratio"])
    label = str(layout.get("label") or key)
    left, top = window_bounds["left"], window_bounds["top"]
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
) -> UITargetSet:
  keys = selector_keys or list(profile.selectors.keys()) + list(profile.action_mappings.keys())
  seen: set[str] = set()
  targets: list[UITarget] = []
  for key in keys:
    if key in seen:
      continue
    seen.add(key)
    t = locate_selector(key, profile, nodes, allow_coordinate_fallback=allow_coordinate_fallback)
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

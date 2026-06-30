"""Canvas-relative coordinate clicks for WebGL browser games."""

from __future__ import annotations

from uno_schemas.adapter_web import (
  ActionExecutionRequest,
  WebActionType,
  WebAdapterProfile,
  WebAutomationMode,
  WebPageDiagnostics,
)

MATCH_CARD_SELECTOR_KEYS = frozenset(
  {"play_card", "play_red_five", "play_button", "draw", "draw_card", "draw_button"}
)

LOBBY_HTML_AVAILABLE = (
  "Lobby HTML controls are available in the DOM (Quick Play, Create Room). "
  "Use bootstrap actions to enter a match before canvas coordinate play."
)
CANVAS_COORDINATE_REQUIRED = (
  "In-match canvas is active; card actions use canvas-relative coordinates, not UIA or DOM selectors."
)
WEB_ADAPTER_PROFILE_HINT = "Attach web adapter profile scuffed-uno-web (Playwright) for match automation."


def click_point_from_canvas(
  canvas_bounds: dict[str, float],
  x_ratio: float,
  y_ratio: float,
) -> dict[str, float]:
  return {
    "x": canvas_bounds["x"] + canvas_bounds["width"] * x_ratio,
    "y": canvas_bounds["y"] + canvas_bounds["height"] * y_ratio,
  }


def resolve_layout_target_key(selector_key: str, profile: WebAdapterProfile) -> str | None:
  aliases = {
    "play_red_five": "play_card",
    "play_button": "play_card",
    "draw": "draw_card",
    "draw_button": "draw_card",
  }
  for key in (selector_key, aliases.get(selector_key or "", "")):
    if key and key in profile.layout_targets:
      return key
  return None


def build_coordinate_click_payload(
  selector_key: str,
  profile: WebAdapterProfile,
  canvas_bounds: dict[str, float],
) -> tuple[dict[str, float], str]:
  layout_key = resolve_layout_target_key(selector_key, profile)
  if not layout_key:
    raise ValueError(f"no layout_targets entry for selector_key={selector_key}")
  layout = profile.layout_targets[layout_key]
  if "x_ratio" in layout and "y_ratio" in layout:
    point = click_point_from_canvas(canvas_bounds, float(layout["x_ratio"]), float(layout["y_ratio"]))
  elif "click_x" in layout and "click_y" in layout:
    point = {"x": float(layout["click_x"]), "y": float(layout["click_y"])}
  else:
    raise ValueError(f"layout target {layout_key} has neither x_ratio/y_ratio nor click_x/click_y")
  return point, str(layout.get("label") or layout_key)


def diagnose_page(
  canvas_bounds: dict[str, float] | None,
  lobby_count: int,
) -> WebPageDiagnostics:
  if canvas_bounds and canvas_bounds.get("width", 0) >= 10:
    return WebPageDiagnostics(
      automation_mode=WebAutomationMode.CANVAS_COORDINATE,
      canvas_detected=True,
      canvas_bounds=canvas_bounds,
      lobby_control_count=lobby_count,
      uia_actionable_in_match=False,
      message=CANVAS_COORDINATE_REQUIRED,
      recommended_action="Execute CLICK_COORDINATE using profile layout_targets relative to canvas bounds.",
    )
  if lobby_count > 0:
    return WebPageDiagnostics(
      automation_mode=WebAutomationMode.LOBBY_HTML,
      canvas_detected=False,
      lobby_control_count=lobby_count,
      uia_actionable_in_match=False,
      message=LOBBY_HTML_AVAILABLE,
      recommended_action="Click Quick Play (bootstrap) to enter a match, then retry canvas coordinate play.",
    )
  return WebPageDiagnostics(
    automation_mode=WebAutomationMode.UNKNOWN,
    message="Neither canvas nor lobby controls detected on the page.",
    recommended_action="Verify launch_url, canvas_selector, and page load state.",
  )


def is_canvas_profile(profile: WebAdapterProfile) -> bool:
  return profile.match_automation == "canvas_coordinate"


def action_requires_canvas_click(req: ActionExecutionRequest, profile: WebAdapterProfile) -> bool:
  return req.action_type == WebActionType.CLICK_COORDINATE or (
    is_canvas_profile(profile) and (req.selector_key or "") in MATCH_CARD_SELECTOR_KEYS
  )

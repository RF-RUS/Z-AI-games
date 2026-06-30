"""Browser host attach ambiguity detection."""

from __future__ import annotations

import re

from uno_schemas.adapter_windows import UiNodeSnapshot

BROWSER_EXE_NAMES = frozenset(
  {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "vivaldi.exe",
  }
)
BROWSER_CLASS_NAMES = frozenset({"Chrome_WidgetWin_1", "MozillaWindowClass"})
BROWSER_HOST_WARNING = (
  "Browser host window: one HWND is shared by all tabs. "
  "Open the game in a separate browser window for reliable attach."
)
TAB_TITLE_MISMATCH_WARNING = (
  "Active browser tab may not match the selected title. "
  "Focus the game tab before attach, or open the game in its own browser window."
)
CAPTURE_CONTENT_MISMATCH_WARNING = (
  "Captured page content does not match the selected game title. "
  "The browser is likely showing a different tab (for example UNO Operator). "
  "Open the game in a dedicated browser window and re-attach."
)

_BROWSER_SUFFIX_RE = re.compile(
  r"\s+[-–—|]\s+(Google Chrome|Microsoft(?:\s+Edge)?|Mozilla Firefox|Brave|Opera|Vivaldi)\s*$",
  re.I,
)


def is_browser_host(process_name: str | None, class_name: str | None = None) -> bool:
  if process_name and process_name.lower() in BROWSER_EXE_NAMES:
    return True
  return bool(class_name and class_name in BROWSER_CLASS_NAMES)


def title_core(title: str | None) -> str:
  if not title:
    return ""
  return _BROWSER_SUFFIX_RE.sub("", title.strip()).strip()


def tree_text_blob(nodes: list[UiNodeSnapshot]) -> str:
  parts = [n.name.strip() for n in nodes if n.name and n.name.strip()]
  return " ".join(parts).lower()


def browser_candidate_warning(process_name: str | None, class_name: str | None = None) -> str | None:
  if is_browser_host(process_name, class_name):
    return BROWSER_HOST_WARNING
  return None


def verify_browser_attach(
  expected_title: str | None,
  live_title: str | None,
  nodes: list[UiNodeSnapshot],
  *,
  process_name: str | None = None,
  class_name: str | None = None,
) -> tuple[str | None, str | None]:
  """Return (warning, detail) when selected title and active document diverge."""
  if not is_browser_host(process_name, class_name):
    return None, None
  if not expected_title:
    return BROWSER_HOST_WARNING, "browser host without explicit expected title"

  expected_core = title_core(expected_title).lower()
  live_core = title_core(live_title).lower()
  blob = tree_text_blob(nodes)

  if expected_core and expected_core not in live_core and expected_core not in blob:
    return TAB_TITLE_MISMATCH_WARNING, (
      f"expected '{expected_core}' not found in live title '{live_title}' or UIA document text"
    )

  operator_markers = ("uno operator", "control center", "operator panel", "session control")
  game_markers = tuple(part.lower() for part in re.split(r"[\s|]+", expected_core) if len(part) > 3)
  if game_markers and any(marker in blob for marker in operator_markers):
    if not any(marker in blob for marker in game_markers):
      return CAPTURE_CONTENT_MISMATCH_WARNING, (
        f"UIA tree looks like operator UI; expected game markers {game_markers!r}"
      )

  return BROWSER_HOST_WARNING, "browser host attached by shared top-level HWND"

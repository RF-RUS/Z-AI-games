"""UIA actionability diagnostics for browser/canvas targets."""

from __future__ import annotations

from uno_schemas.adapter_windows import UiaTreeDiagnostics, UiNodeSnapshot

CHROME_A11Y_FLAG_HINT = (
  "Try launching Chrome with --force-renderer-accessibility, then re-attach. "
  "Inspect.exe / Accessibility Insights should then expose more controls."
)
BROWSER_UIA_NOT_ACTIONABLE = (
  "This browser page is not UIA-actionable: the game is likely rendered on canvas/WebGL "
  "without accessible controls. Use coordinate or vision fallback instead of UIA selector matching."
)
CANVAS_LIKE_TREE = (
  "UIA tree is canvas-like (Document has no actionable page controls). "
  "Inspect.exe typically cannot see game controls on this page."
)
BROWSER_PAGE_CONTROLS_BUT_NO_SELECTOR = (
  "Page exposes HTML controls in UIA (lobby/menus) but not in-game card targets. "
  "Start a match first, or use coordinate/vision fallback for canvas gameplay."
)
BROWSER_MATCH_CARD_REQUIRES_WEB = (
  "Browser match card play is not supported via Windows UIA. "
  "Attach web adapter profile scuffed-uno-web (Playwright) for canvas coordinate automation."
)

MATCH_CARD_SELECTOR_KEYS = frozenset(
  {"play_card", "play_red_five", "play_button", "draw", "draw_card", "draw_button"}
)


def _control_type(node: UiNodeSnapshot) -> str:
  return (node.control_type or "").lower()


def _document_depth(nodes: list[UiNodeSnapshot]) -> int | None:
  depths = [n.depth for n in nodes if "document" in _control_type(n)]
  return min(depths) if depths else None


def page_nodes(nodes: list[UiNodeSnapshot], *, is_browser_host: bool) -> list[UiNodeSnapshot]:
  if not is_browser_host:
    return nodes
  doc_depth = _document_depth(nodes)
  if doc_depth is None:
    return []
  return [n for n in nodes if n.depth > doc_depth]


def is_actionable_node(node: UiNodeSnapshot) -> bool:
  if not (node.name or node.auto_id):
    return False
  ct = _control_type(node)
  if any(token in ct for token in ("button", "link", "edit", "checkbox", "menuitem", "tabitem", "listitem")):
    return True
  if node.name and len(node.name.strip()) >= 2 and ct not in ("pane", "document", "group", "text", "static", "image"):
    return True
  return False


def analyze_uia_tree(
  nodes: list[UiNodeSnapshot],
  *,
  sparse_tree: bool,
  is_browser_host: bool,
) -> UiaTreeDiagnostics:
  named_nodes = [n for n in nodes if n.name or n.auto_id]
  documents = [n for n in nodes if "document" in _control_type(n)]
  buttons = [n for n in nodes if "button" in _control_type(n)]
  in_page = page_nodes(nodes, is_browser_host=is_browser_host)
  page_actionable = [n for n in in_page if is_actionable_node(n)]

  canvas_like = bool(is_browser_host and documents and len(page_actionable) == 0)
  uia_actionable = len(page_actionable) >= 1 if is_browser_host else len(page_actionable) >= 2

  message = ""
  recommended = ""
  if canvas_like:
    message = BROWSER_UIA_NOT_ACTIONABLE
    recommended = (
      f"{CANVAS_LIKE_TREE} {CHROME_A11Y_FLAG_HINT} "
      "Otherwise use the web adapter (Playwright) or coordinate/vision fallback."
    )
    uia_actionable = False
  elif sparse_tree and len(page_actionable) == 0:
    message = "UIA tree is sparse and exposes no named actionable controls."
    recommended = "Use profile layout_targets or coordinate/vision fallback."
    uia_actionable = False
  elif is_browser_host and not uia_actionable:
    message = BROWSER_UIA_NOT_ACTIONABLE
    recommended = CHROME_A11Y_FLAG_HINT

  return UiaTreeDiagnostics(
    node_count=len(nodes),
    named_node_count=len(named_nodes),
    actionable_control_count=len(page_actionable),
    document_actionable_count=len(page_actionable),
    button_count=len(buttons),
    document_count=len(documents),
    sparse_tree=sparse_tree,
    canvas_like=canvas_like,
    uia_actionable=uia_actionable,
    message=message,
    recommended_action=recommended,
  )


def should_skip_uia_card_lookup(
  is_browser_host: bool,
  selector_key: str | None,
  *,
  match_automation: str | None = None,
) -> bool:
  if not is_browser_host or not selector_key:
    return False
  if match_automation == "web_only":
    return selector_key in MATCH_CARD_SELECTOR_KEYS
  return selector_key in MATCH_CARD_SELECTOR_KEYS


def browser_match_card_message(diagnostics: UiaTreeDiagnostics) -> str:
  base = BROWSER_MATCH_CARD_REQUIRES_WEB
  if diagnostics.canvas_like or not diagnostics.uia_actionable:
    hint = diagnostics.recommended_action or CANVAS_LIKE_TREE
    return f"{base} ({hint})"
  if diagnostics.document_actionable_count > 0:
    return f"{base} ({BROWSER_PAGE_CONTROLS_BUT_NO_SELECTOR})"
  return base


def missing_target_message(
  diagnostics: UiaTreeDiagnostics,
  selector_key: str | None,
  *,
  is_browser_host: bool = False,
) -> str:
  if not diagnostics.uia_actionable:
    base = diagnostics.message or BROWSER_UIA_NOT_ACTIONABLE
    hint = diagnostics.recommended_action
    return f"{base} ({hint})" if hint else base
  key = selector_key or "target"
  if is_browser_host and diagnostics.document_actionable_count > 0:
    return (
      f"target '{key}' not found in page UIA tree. "
      f"{BROWSER_PAGE_CONTROLS_BUT_NO_SELECTOR} "
      f"({diagnostics.document_actionable_count} page controls visible to UIA)"
    )
  return (
    f"target '{key}' not found in UIA tree "
    f"({diagnostics.actionable_control_count} actionable controls, {diagnostics.node_count} nodes)"
  )

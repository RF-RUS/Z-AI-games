"""UIA actionability diagnostics for canvas/browser pages."""

from uno_adapter_windows.uia_actionability import (
  BROWSER_UIA_NOT_ACTIONABLE,
  analyze_uia_tree,
  missing_target_message,
)
from uno_schemas.adapter_windows import UiNodeSnapshot

_node_id = 0


def _node(name: str = "", auto_id: str = "", control_type: str = "Pane", depth: int = 0) -> UiNodeSnapshot:
  global _node_id
  _node_id += 1
  return UiNodeSnapshot(
    node_id=str(_node_id),
    name=name,
    auto_id=auto_id,
    control_type=control_type,
    depth=depth,
  )


def test_chrome_canvas_like_tree_not_actionable():
  nodes = [
    _node("UNO - Google Chrome", control_type="Window", depth=0),
    _node("", control_type="Document", depth=1),
    _node("", control_type="Pane", depth=2),
  ]
  diag = analyze_uia_tree(nodes, sparse_tree=True, is_browser_host=True)
  assert diag.canvas_like is True
  assert diag.uia_actionable is False
  assert diag.document_actionable_count == 0
  assert BROWSER_UIA_NOT_ACTIONABLE in diag.message


def test_browser_lobby_html_controls_are_actionable():
  nodes = [
    _node("Chrome", control_type="Window", depth=0),
    _node("Tab", control_type="TabItem", depth=1),
    _node("", control_type="Document", depth=2),
    _node("Quick Play", control_type="Button", depth=3),
    _node("Create Room", control_type="Button", depth=3),
  ]
  diag = analyze_uia_tree(nodes, sparse_tree=False, is_browser_host=True)
  assert diag.uia_actionable is True
  assert diag.canvas_like is False
  assert diag.document_actionable_count == 2


def test_browser_chrome_shell_buttons_do_not_count_as_page_controls():
  nodes = [
    _node("Chrome", control_type="Window", depth=0),
    _node("Close", control_type="Button", depth=1),
    _node("Back", control_type="Button", depth=1),
    _node("", control_type="Document", depth=1),
  ]
  diag = analyze_uia_tree(nodes, sparse_tree=False, is_browser_host=True)
  assert diag.canvas_like is True
  assert diag.document_actionable_count == 0


def test_missing_target_message_for_canvas_page():
  nodes = [_node("", control_type="Document", depth=0)]
  diag = analyze_uia_tree(nodes, sparse_tree=True, is_browser_host=True)
  msg = missing_target_message(diag, "play_red_five", is_browser_host=True)
  assert "not UIA-actionable" in msg
  assert "coordinate or vision fallback" in msg


def test_missing_target_message_for_lobby_with_html_controls():
  nodes = [
    _node("", control_type="Document", depth=0),
    _node("Quick Play", control_type="Button", depth=1),
  ]
  diag = analyze_uia_tree(nodes, sparse_tree=False, is_browser_host=True)
  msg = missing_target_message(diag, "play_red_five", is_browser_host=True)
  assert "play_red_five" in msg
  assert "lobby/menus" in msg


def test_missing_target_message_for_selector_miss_on_native():
  nodes = [
    _node("Draw", control_type="Button", depth=0),
    _node("Pass", control_type="Button", depth=0),
  ]
  diag = analyze_uia_tree(nodes, sparse_tree=False, is_browser_host=False)
  msg = missing_target_message(diag, "play_red_five", is_browser_host=False)
  assert "play_red_five" in msg
  assert "not UIA-actionable" not in msg


def test_should_skip_uia_card_lookup_for_browser():
  from uno_adapter_windows.uia_actionability import should_skip_uia_card_lookup

  assert should_skip_uia_card_lookup(True, "play_red_five") is True
  assert should_skip_uia_card_lookup(True, "draw") is True
  assert should_skip_uia_card_lookup(False, "play_red_five") is False
  assert should_skip_uia_card_lookup(True, "chat_input") is False

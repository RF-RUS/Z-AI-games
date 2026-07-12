"""Tests for grounding a draw_card click to the perceived deck (draw stall fix).

On canvas/Electron games UIA is empty, so a draw_card action with only
selector_key="draw" has nothing to resolve and the agent stalls when it must
draw. These pin: (1) find_draw_target extracts the deck center from perceived
regions, and (2) _map_action_windows turns a draw_target into a grounded click.
"""

from __future__ import annotations

from uno_shared.adapter_registry import AdapterRegistry, find_draw_target


def test_find_draw_target_from_regions():
    gs = {
        "regions": [
            {"id": "hand", "x": 100, "y": 600, "width": 400, "height": 120},
            {"id": "draw_pile", "x": 300, "y": 200, "width": 80, "height": 110},
        ],
    }
    assert find_draw_target(gs) == (340, 255)  # center of draw_pile


def test_find_draw_target_from_actionable_targets():
    gs = {"actionable_targets": [{"id": "deck", "x": 512, "y": 240}]}
    assert find_draw_target(gs) == (512, 240)


def test_find_draw_target_none_when_absent():
    assert find_draw_target({"regions": [{"id": "hand", "x": 1, "y": 2, "width": 3, "height": 4}]}) is None
    assert find_draw_target({}) is None
    assert find_draw_target(None) is None


def test_windows_draw_action_is_grounded():
    client = AdapterRegistry().get_client("windows")
    req = client.map_action(
        action_type="draw_card",
        profile_id="real-uno-desktop",
        payload={"draw_target": [340, 255]},
    )
    assert req.extra.get("target_x") == 340
    assert req.extra.get("target_y") == 255
    assert req.extra.get("grounded_by") == "cv_detection"


def test_windows_draw_without_target_not_grounded():
    """No perceived deck → no coordinate (falls back to selector, unchanged)."""
    client = AdapterRegistry().get_client("windows")
    req = client.map_action(action_type="draw_card", profile_id="real-uno-desktop")
    assert req.extra.get("target_x") is None
    assert req.selector_key == "draw"

"""Test screenshot perception plugin."""
from pathlib import Path

import pytest
from uno_perception.canvas_plugin import HeuristicCanvasUNOPlugin


def _make_fake_screenshot(tmp_path: Path, width: int = 800, height: int = 600, brightness: int = 100):
    """Create a fake screenshot for testing."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (width, height), (brightness, brightness, brightness))
        # Draw some colored rectangles to simulate game elements
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 420, 800, 600], fill=(200, 100, 100))  # hand area (red-ish)
        draw.rectangle([680, 210, 800, 300], fill=(100, 200, 100))  # draw pile (green-ish)
        path = tmp_path / "test_screenshot.png"
        img.save(str(path))
        return str(path)
    except ImportError:
        # PIL not available, create empty file
        path = tmp_path / "test_screenshot.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        return str(path)


def test_plugin_detects_regions(tmp_path):
    """Plugin should detect regions from a screenshot."""
    screenshot_path = _make_fake_screenshot(tmp_path)
    plugin = HeuristicCanvasUNOPlugin()
    result = plugin.infer_from_screenshot(screenshot_path)

    assert result.screen_valid is True
    assert len(result.regions) > 0
    assert result.confidence > 0


def test_plugin_detects_actionable_targets(tmp_path):
    """Plugin should detect at least one actionable target."""
    screenshot_path = _make_fake_screenshot(tmp_path)
    plugin = HeuristicCanvasUNOPlugin()
    result = plugin.infer_from_screenshot(screenshot_path)

    assert len(result.actionable_targets) > 0
    assert any(r.is_actionable for r in result.regions)


def test_plugin_with_profile_zones(tmp_path):
    """Plugin should use profile zones when provided."""
    screenshot_path = _make_fake_screenshot(tmp_path)
    plugin = HeuristicCanvasUNOPlugin()
    profile = {
        "layout_targets": {
            "hand": {"rel_x": 0.0, "rel_y": 0.7, "rel_w": 1.0, "rel_h": 0.3},
            "draw": {"rel_x": 0.85, "rel_y": 0.35, "rel_w": 0.1, "rel_h": 0.15},
        }
    }
    result = plugin.infer_from_screenshot(screenshot_path, profile)

    assert result.screen_valid is True
    region_ids = [r.region_id for r in result.regions]
    assert "hand" in region_ids
    assert "draw" in region_ids


def test_plugin_black_screen(tmp_path):
    """Plugin should detect black/empty screen."""
    try:
        from PIL import Image
        img = Image.new("RGB", (800, 600), (0, 0, 0))
        path = tmp_path / "black.png"
        img.save(str(path))
        plugin = HeuristicCanvasUNOPlugin()
        result = plugin.infer_from_screenshot(str(path))
        assert result.screen_valid is False
    except ImportError:
        pytest.skip("PIL not available")


def test_plugin_returns_structured_state(tmp_path):
    """Plugin should return structured Inference, not raw text."""
    screenshot_path = _make_fake_screenshot(tmp_path)
    plugin = HeuristicCanvasUNOPlugin()
    result = plugin.infer_from_screenshot(screenshot_path)

    # Verify structured fields exist
    assert hasattr(result, "screen_valid")
    assert hasattr(result, "screen_type")
    assert hasattr(result, "whose_turn")
    assert hasattr(result, "regions")
    assert hasattr(result, "actionable_targets")
    assert hasattr(result, "summary")
    assert hasattr(result, "confidence")

    # Verify regions are structured
    for region in result.regions:
        assert hasattr(region, "region_id")
        assert hasattr(region, "region_type")
        assert hasattr(region, "x")
        assert hasattr(region, "y")
        assert hasattr(region, "is_actionable")

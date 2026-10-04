"""Zone-based click verification (uno_shared.click_verification).

Regression, session 8b4cefc1 (2026-08-24): two "Play" clicks returned
success=True while the game kept showing the same modal. The whole-frame
verifier cannot judge these (opponents redraw the board constantly), so the
verdict comes from the zone around the clicked point. Thresholds were
calibrated on that session's artifacts: noise <= ~0.5%, ignored click ~1.4%,
accepted action >= ~40% of zone pixels change.
"""

from __future__ import annotations

from PIL import Image
from uno_shared.click_verification import (
    click_retry_offsets,
    verify_zone_change,
    zone_config,
)


def _save(img: Image.Image, path) -> str:
    img.save(str(path))
    return str(path)


def _flat(size=(300, 200), color=(200, 200, 200)) -> Image.Image:
    return Image.new("RGB", size, color)


def test_no_change_yields_zero(tmp_path) -> None:
    b = _save(_flat(), tmp_path / "b.png")
    a = _save(_flat(color=(201, 201, 201)), tmp_path / "a.png")  # sub-threshold drift everywhere
    assert verify_zone_change(b, a, 150, 100, half_w=100, half_h=60, pixel_diff=30) == 0.0


def test_local_change_in_zone_is_detected(tmp_path) -> None:
    b = _save(_flat(), tmp_path / "b.png")
    a = _flat()
    a.paste((20, 20, 20), (120, 70, 180, 130))  # dark rectangle centred on (150,100)
    a = _save(a, tmp_path / "a.png")
    ratio = verify_zone_change(b, a, 150, 100, half_w=100, half_h=60, pixel_diff=30)
    assert ratio is not None and ratio > 0.05


def test_change_outside_zone_does_not_count(tmp_path) -> None:
    """Opponents keep redrawing the rest of the table; only the zone matters."""
    b = _save(_flat(), tmp_path / "b.png")
    a = _flat()
    a.paste((20, 20, 20), (0, 0, 40, 30))  # far corner, outside the zone box (zone starts at x=50,y=40)
    a = _save(a, tmp_path / "a.png")
    ratio = verify_zone_change(b, a, 150, 100, half_w=100, half_h=60, pixel_diff=30)
    assert ratio == 0.0


def test_unreadable_frame_returns_none_not_zero(tmp_path) -> None:
    b = _save(_flat(), tmp_path / "b.png")
    assert verify_zone_change(str(tmp_path / "missing.png"), b, 150, 100) is None
    assert verify_zone_change(b, str(tmp_path / "nope.txt"), 150, 100) is None
    # A non-image file: open fails -> None (callers report "unverifiable").
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not a png")
    assert verify_zone_change(str(bad), b, 150, 100) is None


def test_zone_clamps_to_frame_edges(tmp_path) -> None:
    """A click near the border must not raise and must measure what exists."""
    small = (120, 80)
    b = _save(_flat(small, (200, 200, 200)), tmp_path / "b.png")
    a = _flat(small, (200, 200, 200))
    a.paste((20, 20, 20), (0, 0, 40, 30))
    a = _save(a, tmp_path / "a.png")
    ratio = verify_zone_change(b, a, 10, 10, half_w=100, half_h=60, pixel_diff=30)
    assert ratio is not None and ratio > 0


def test_pixel_diff_threshold_filters_jitter(tmp_path) -> None:
    b = _save(_flat(), tmp_path / "b.png")
    a = _save(_flat(color=(210, 210, 210)), tmp_path / "a.png")  # uniform +10 everywhere
    assert verify_zone_change(b, a, 150, 100, pixel_diff=30) == 0.0
    assert verify_zone_change(b, a, 150, 100, pixel_diff=5) == 1.0


def test_size_mismatch_resizes_after_frame(tmp_path) -> None:
    b = _save(_flat(), tmp_path / "b.png")
    a = _save(_flat(size=(190, 190)), tmp_path / "a.png")  # slightly different capture size
    ratio = verify_zone_change(b, a, 150, 100, half_w=80, half_h=50)
    assert ratio == 0.0


def test_defaults_are_sane() -> None:
    cfg = zone_config()
    assert cfg["min_ratio"] >= 0.03  # well above the measured ~1.4% noise floor
    assert cfg["half_w"] >= 40 and cfg["half_h"] >= 30
    assert cfg["pixel_diff"] >= 10


def test_click_retry_offsets_default_three_attempts_with_first_at_centre(monkeypatch) -> None:
    monkeypatch.delenv("CLICK_PROMPT_MAX_ATTEMPTS", raising=False)
    offsets = click_retry_offsets()
    assert len(offsets) == 3
    assert offsets[0] == (0, 0)


def test_click_retry_offsets_env_bounded(monkeypatch) -> None:
    monkeypatch.setenv("CLICK_PROMPT_MAX_ATTEMPTS", "5")
    assert len(click_retry_offsets()) == 5
    monkeypatch.setenv("CLICK_PROMPT_MAX_ATTEMPTS", "0")
    assert len(click_retry_offsets()) == 1  # never zero attempts
    monkeypatch.setenv("CLICK_PROMPT_MAX_ATTEMPTS", "garbage")
    assert len(click_retry_offsets()) == 3


def test_env_tunables_are_read_per_call(monkeypatch) -> None:
    monkeypatch.setenv("CLICK_VERIFY_MIN_CHANGE_RATIO", "0.11")
    monkeypatch.setenv("CLICK_VERIFY_HALF_W", "123")
    cfg = zone_config()
    assert cfg["min_ratio"] == 0.11
    assert cfg["half_w"] == 123

"""Post-click local-zone verification.

WHY THIS EXISTS (session 8b4cefc1, 2026-08-24)
----------------------------------------------
Two consecutive "Play" prompt clicks came back `success=True` while the game kept
showing the same Play/Keep modal — the dispatched click landed somewhere that the
game ignored. Every downstream cycle then decided on a board that never changed.

The existing whole-frame verifier (`ui_verifier.verify_screenshot_transition`)
cannot judge these clicks: in a live multiplayer table opponents act constantly,
so the frame ALWAYS changes between two captures (~2% weighted diff with no click
at all, measured on the session's artifacts). A click is only proven by looking at
the zone right around the point that was clicked: a working button dismisses a
modal or moves the piece under the cursor, producing a locally dense change.

Thresholds were calibrated on that session's saved frames (see AGENT_LOG.md):
  no click, modal shown        <= ~0.5% of zone pixels change (>30 gray levels)
  IGNORED Play click             ~1.4%
  accepted card play           >= ~40%
A 5% minimum sits far above the noise floor and far below any real effect.

Everything is best-effort: any unreadable frame yields None, which callers report
as "unverifiable" (NOT "failed") — the click may still have worked, and guessing
otherwise would reintroduce the original bug from the opposite side.
"""

from __future__ import annotations

import os


def zone_config() -> dict[str, float | int]:
    """Verification parameters, env-tunable per call (never cached at import)."""
    return {
        "half_w": int(os.getenv("CLICK_VERIFY_HALF_W", "100")),
        "half_h": int(os.getenv("CLICK_VERIFY_HALF_H", "60")),
        "min_ratio": float(os.getenv("CLICK_VERIFY_MIN_CHANGE_RATIO", "0.05")),
        "pixel_diff": int(os.getenv("CLICK_VERIFY_PIXEL_DIFF", "30")),
        "settle_s": float(os.getenv("CLICK_RETRY_SETTLE_S", "0.6")),
    }


_RETRY_STEPS: list[tuple[int, int]] = [(0, 0), (-12, -10), (12, 10), (0, -16), (16, 0)]


def click_retry_offsets() -> list[tuple[int, int]]:
    """Point offsets (in screenshot px) for successive click attempts.

    First attempt is the perceived centre; subsequent ones probe around it, since
    a VLM-perceived button centre can be off by several pixels and canvas hit-boxes
    are small. Bounded by CLICK_PROMPT_MAX_ATTEMPTS (default 3).
    """
    try:
        n = max(1, min(5, int(os.getenv("CLICK_PROMPT_MAX_ATTEMPTS", "3"))))
    except ValueError:
        n = 3
    return _RETRY_STEPS[:n]


def verify_zone_change(
    before_path: str,
    after_path: str,
    center_x: int,
    center_y: int,
    *,
    half_w: int = 100,
    half_h: int = 60,
    pixel_diff: int = 30,
) -> float | None:
    """Fraction of zone pixels that changed between two frames, or None if unreadable.

    The zone is a rectangle of (2*half_w) x (2*half_h) centred on the click point,
    clamped to the frame. A pixel counts as changed when its grayscale difference
    exceeds `pixel_diff` (JPEG/compression noise stays well below that). Returns
    None — not 0 — when either frame cannot be read, so callers can distinguish
    "nothing changed" from "I cannot tell".
    """
    try:
        from PIL import Image, ImageChops

        b = Image.open(before_path).convert("RGB")
        a = Image.open(after_path).convert("RGB")
        if a.size != b.size:
            a = a.resize(b.size)
        w, h = b.size
        x0, x1 = max(0, center_x - half_w), min(w, center_x + half_w)
        y0, y1 = max(0, center_y - half_h), min(h, center_y + half_h)
        if x1 - x0 < 8 or y1 - y0 < 8:
            return None
        diff = ImageChops.difference(b.crop((x0, y0, x1, y1)), a.crop((x0, y0, x1, y1))).convert("L")
        hist = diff.histogram()
        changed = sum(hist[bin_index] for bin_index in range(pixel_diff + 1, 256))
        total = (x1 - x0) * (y1 - y0)
        return changed / total if total else None
    except Exception:  # noqa: BLE001 — verification must never break the agent loop
        return None

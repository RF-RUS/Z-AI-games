"""Frame-diff gate for the VLM (L0 event loop, step 2 of the latency plan).

A static board is a wasted VLM call: the opponent's turn, an idle hand, an
unanimated menu — the screen is literally unchanged, so the board the VLM saw
10 seconds ago IS the board now. The gate keeps the last downsampled frame per
session and answers "did the screen change since the last look?" with a cheap
grayscale diff (PIL only, no numpy).

Policy:
- First frame for a session: always CHANGED (the VLM must establish the board).
- A change fires the VLM; the fresh frame becomes the new reference.
- No change: the caller reuses its cached VLM result (see api.py).

The diff is intentionally conservative in the "changed" direction: even a tiny
delta (one card swapped, a timer tick) should count, because a missed change
means the agent plays on a stale board — the exact desync class we have been
fixing. A false positive only costs one VLM call.

Reference resolution: 128x128 grayscale. A real card move is dozens of pixels
at that scale, so it is caught with a large margin; pure sensor/telemetry noise
is well below it.
"""

from __future__ import annotations

import time

# Mean absolute delta (0..255 scale) that by itself counts as a change.
# ~0.2% of the full range. A single card swap on a 1296x759 board lands at
# roughly 0.3-1.5 here even at 128x128, so this is set deliberately low.
DEFAULT_MEAN_THRESHOLD = 0.5
# A single bright local delta (0..255) that counts as a change even if the
# frame-wide mean stays below the threshold. Catches small UI updates (a
# drawn card, a prompt button appearing) the mean alone could wash out.
DEFAULT_MAX_THRESHOLD = 24.0


class FrameGate:
  """Per-session "has the screen changed since I last looked" oracle."""

  def __init__(
    self,
    size: tuple[int, int] = (128, 128),
    mean_threshold: float = DEFAULT_MEAN_THRESHOLD,
    max_threshold: float = DEFAULT_MAX_THRESHOLD,
    max_sessions: int = 32,
  ) -> None:
    self._size = size
    self._mean_threshold = mean_threshold
    self._max_threshold = max_threshold
    self._max_sessions = max_sessions
    self._refs: dict[str, tuple[float, "object"]] = {}  # session -> (ts, grayscale img)

  def observe(self, session_id: str, image) -> tuple[bool, dict]:
    """Feed a fresh frame; return (changed, stats).

    `image` is anything PIL can open as an Image or an Image itself. A read
    failure is reported as changed=True so the VLM runs rather than us
    silently caching on top of a broken capture.
    """
    from PIL import Image, ImageChops

    try:
      img = image if isinstance(image, Image.Image) else Image.open(image)
      img = img.convert("L").resize(self._size)
    except Exception:
      return True, {"error": "unreadable_frame", "changed": True}

    now = time.time()
    ref = self._refs.get(session_id)
    if ref is None:
      self._store(session_id, now, img)
      return True, {"first_frame": True, "changed": True}

    prev_ts, prev_img = ref
    diff = ImageChops.difference(prev_img, img)
    hist = diff.histogram()
    total = self._size[0] * self._size[1]
    mean = (sum(i * c for i, c in enumerate(hist)) / total) if total else 0.0
    max_d = diff.getextrema()[1]

    changed = (mean >= self._mean_threshold) or (max_d >= self._max_threshold)
    self._store(session_id, now, img)
    return changed, {
      "changed": changed,
      "mean": round(mean, 3),
      "max": max_d,
      "prev_age_s": round(now - prev_ts, 2),
    }

  def forget(self, session_id: str) -> None:
    self._refs.pop(session_id, None)

  def _store(self, session_id: str, ts: float, img) -> None:
    # Evict the oldest session when the cache grows past its cap.
    if len(self._refs) >= self._max_sessions and session_id not in self._refs:
      oldest = min(self._refs, key=lambda k: self._refs[k][0])
      self._refs.pop(oldest, None)
    self._refs[session_id] = (ts, img)

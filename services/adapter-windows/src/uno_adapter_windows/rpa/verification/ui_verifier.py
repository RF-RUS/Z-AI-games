"""Before/after UI change detection."""

from __future__ import annotations

from pathlib import Path

from uno_schemas.adapter_windows import VerificationResult


def verify_screenshot_transition(
  before_path: str | None,
  after_path: str | None,
  *,
  min_change_ratio: float = 0.005,
) -> VerificationResult:
  if not before_path or not after_path:
    return VerificationResult(passed=False, status="missing_frame", notes="before or after screenshot missing")
  b, a = Path(before_path), Path(after_path)
  if not b.exists() or not a.exists():
    return VerificationResult(passed=False, status="file_missing", notes="screenshot file not found")

  try:
    from PIL import Image, ImageChops

    img_b = Image.open(b).convert("RGB")
    img_a = Image.open(a).convert("RGB")
    if img_b.size != img_a.size:
      img_a = img_a.resize(img_b.size)
    diff = ImageChops.difference(img_b, img_a)
    hist = diff.histogram()
    # sum of non-zero channel diffs approx
    changed = sum(hist[1:256]) + sum(hist[257:512]) + sum(hist[513:768])
    total = img_b.size[0] * img_b.size[1] * 3 * 255
    ratio = changed / total if total else 0.0
    passed = ratio >= min_change_ratio
    return VerificationResult(
      passed=passed,
      status="passed" if passed else "no_visible_change",
      change_ratio=round(ratio, 6),
      notes="" if passed else "UI did not change enough after action",
    )
  except Exception as exc:
    return VerificationResult(passed=False, status="verify_error", notes=str(exc))

"""Assisted calibration for real-uno-desktop layout_targets.

Screenshot is client-area only (pywinauto capture_as_image), so pixel
coordinates in the image are client-local with origin (0,0).  No screen-
space offset subtraction is needed.

Usage:
  1. Attach to real UNO window
  2. uv run python scripts/calibrate_draw_target.py --adapter-id <ID>
  3. Open artifacts/calibration/draw_screenshot.png
  4. Measure Draw button center in pixels
  5. uv run python scripts/calibrate_draw_target.py --adapter-id <ID> --x 312 --y 164
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

API = "http://127.0.0.1:8105"
PROFILE_PATH = Path("services/adapter-windows/profiles/real-uno-desktop.json")
ARTIFACTS = Path("artifacts/calibration")

# capture_as_image() captures client area only — origin (0,0), no title bar
SCREENSHOT_COORD_SPACE = "client_local"


def get_calibration(adapter_id: str) -> dict:
  r = httpx.get(f"{API}/adapters/{adapter_id}/calibration", timeout=10)
  r.raise_for_status()
  return r.json()


def capture_screenshot(adapter_id: str) -> Path:
  ARTIFACTS.mkdir(parents=True, exist_ok=True)
  r = httpx.get(f"{API}/adapters/{adapter_id}/screenshot", timeout=15)
  r.raise_for_status()
  path = ARTIFACTS / "draw_screenshot.png"
  path.write_bytes(r.content)
  return path


def get_current_ratios() -> tuple[float, float]:
  profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
  layout = profile.get("layout_targets", {}).get("draw_button", {})
  return float(layout.get("x_ratio", 0.44)), float(layout.get("y_ratio", 0.34))


def update_profile(new_x_ratio: float, new_y_ratio: float) -> tuple[float, float]:
  profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
  old = profile["layout_targets"]["draw_button"]
  old_x, old_y = float(old["x_ratio"]), float(old["y_ratio"])
  profile["layout_targets"]["draw_button"]["x_ratio"] = round(new_x_ratio, 4)
  profile["layout_targets"]["draw_button"]["y_ratio"] = round(new_y_ratio, 4)
  PROFILE_PATH.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
  return old_x, old_y


def main():
  parser = argparse.ArgumentParser(description="Calibrate draw target for real UNO layout")
  parser.add_argument("--adapter-id", required=True)
  parser.add_argument("--x", type=float, help="Measured X (pixels from left of client area)")
  parser.add_argument("--y", type=float, help="Measured Y (pixels from top of client area)")
  args = parser.parse_args()

  cal = get_calibration(args.adapter_id)
  cb = cal.get("client_bounds")
  if not cb:
    print("ERROR: client_bounds unavailable")
    sys.exit(1)

  cw = cb["right"] - cb["left"]
  ch = cb["bottom"] - cb["top"]
  old_xr, old_yr = get_current_ratios()
  current_x = cb["left"] + cw * old_xr
  current_y = cb["top"] + ch * old_yr

  print(f"Screenshot coord space: {SCREENSHOT_COORD_SPACE}")
  print(f"Client bounds:         {cb}")
  print(f"Client size:           {cw:.0f} x {ch:.0f}")
  print(f"Current draw point:    ({current_x:.1f}, {current_y:.1f})")
  print(f"Current ratio:         x={old_xr:.4f}  y={old_yr:.4f}")

  if args.x is not None and args.y is not None:
    # Screenshot is client-local: pixel coords = client coords, no offset needed
    new_xr = args.x / cw
    new_yr = args.y / ch
    old_x, old_y = update_profile(new_xr, new_yr)

    print(f"\nNormalization formula:  x_ratio = measured_x / client_width")
    print(f"                        y_ratio = measured_y / client_height")
    print(f"  measured_x = {args.x:.1f}, client_width = {cw:.0f}")
    print(f"  measured_y = {args.y:.1f}, client_height = {ch:.0f}")
    print(f"\nOld ratio:  x={old_x:.4f}  y={old_y:.4f}")
    print(f"New ratio:  x={new_xr:.4f}  y={new_yr:.4f}")
    print(f"Profile:    {PROFILE_PATH}")
  else:
    path = capture_screenshot(args.adapter_id)
    print(f"\nScreenshot: {path}")
    print(f"\nNext steps:")
    print(f"  1. Open the screenshot in an image editor")
    print(f"  2. Find the Draw button center — read (pixel_x, pixel_y)")
    print(f"  3. Those pixels ARE client-area coords (no offset needed)")
    print(f"  4. Run:")
    print(f"     uv run python scripts/calibrate_draw_target.py --adapter-id {args.adapter_id} --x <pixel_x> --y <pixel_y>")


if __name__ == "__main__":
  main()

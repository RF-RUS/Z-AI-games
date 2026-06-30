"""Calibrate scuffed-uno-web profile from live screenshot.

Usage:
    python scripts/calibrate-scuffed-uno-web.py --screenshot <path>
    python scripts/calibrate-scuffed-uno-web.py --live --cdp-url http://127.0.0.1:9222

This script:
1. Captures or loads a screenshot of scuffed-uno-web
2. Runs CV pipeline to detect card positions and draw area
3. Saves calibrated coordinates to profiles/scuffed-uno-web.json
4. Prints a calibration report
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "adapter-web" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "schemas" / "src"))

from PIL import Image
from uno_adapter_web.hand_detection import calibrate_from_screenshot, save_calibration

PROFILE_PATH = Path(__file__).resolve().parents[1] / "services" / "adapter-web" / "profiles" / "scuffed-uno-web.json"


async def capture_live_screenshot(cdp_url: str = "http://127.0.0.1:9222") -> Image.Image | None:
    """Capture a screenshot from a live Chrome CDP session."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{cdp_url}/json")
            r.raise_for_status()
            tabs = [t for t in r.json() if t.get("type") == "page"]
            if not tabs:
                print("ERROR: No browser tabs found")
                return None
    except Exception as e:
        print(f"ERROR: CDP not available: {e}")
        return None

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(cdp_url)
            pages = browser.contexts[0].pages if browser.contexts else []
            target = None
            for p in pages:
                if "scuffeduno" in (p.url or ""):
                    target = p
                    break
            if not target and pages:
                target = pages[0]
            if not target:
                print("ERROR: No matching tab found")
                return None
            screenshot_bytes = await target.screenshot()
            from io import BytesIO
            return Image.open(BytesIO(screenshot_bytes))
    except Exception as e:
        print(f"ERROR: Screenshot capture failed: {e}")
        return None


def calibrate_from_file(screenshot_path: str) -> Image.Image:
    """Load a screenshot from file."""
    return Image.open(screenshot_path)


def main():
    parser = argparse.ArgumentParser(description="Calibrate scuffed-uno-web profile")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--screenshot", help="Path to screenshot file")
    group.add_argument("--live", action="store_true", help="Capture from live Chrome CDP")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="CDP debug port URL")
    parser.add_argument("--profile", default=str(PROFILE_PATH), help="Path to profile JSON")
    parser.add_argument("--dry-run", action="store_true", help="Print report without saving")
    args = parser.parse_args()

    if args.live:
        img = asyncio.run(capture_live_screenshot(args.cdp_url))
        if img is None:
            sys.exit(1)
    else:
        img = calibrate_from_file(args.screenshot)

    w, h = img.size
    print(f"Screenshot: {w}x{h}")

    result = calibrate_from_screenshot(img, w, h)
    print(f"\nDetected {result.card_count} cards in hand region")
    print(f"Hand region: {result.hand_region}")
    print(f"Draw region: {result.draw_region}")

    if result.hand_slots:
        print("\nHand slots:")
        for slot in result.hand_slots:
            print(f"  {slot['slot_id']}: ({slot['click_x']}, {slot['click_y']}) color={slot['color']}")

    if result.draw_area:
        print(f"\nDraw pile: ({result.draw_area['click_x']}, {result.draw_area['click_y']}) color={result.draw_area.get('color', '?')}")

    if not args.dry_run:
        report = save_calibration(result, args.profile)
        print(f"\nSaved to {args.profile}")
        print(f"Calibrated {report['calibrated_slots']} hand slots + draw area")
    else:
        print("\nDry run — not saved")


if __name__ == "__main__":
    main()

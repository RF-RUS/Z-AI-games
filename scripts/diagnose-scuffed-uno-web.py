"""Diagnose live scuffed-uno-web session.

Captures a screenshot from the live browser session and runs the CV pipeline
to show exactly what the system sees. Run after attaching to scuffed-uno-web.

Usage:
    python scripts/diagnose-scuffed-uno-web.py --cdp-url http://127.0.0.1:9222
    python scripts/diagnose-scuffed-uno-web.py --screenshot path/to/screenshot.png
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "adapter-web" / "src"))

from PIL import Image
from uno_adapter_web.hand_detection import (
    _find_color_regions,
    calibrate_from_screenshot,
    detect_game_elements,
    detect_screen_state,
)
from uno_adapter_web.profiles import load_profile


def analyze_screenshot(img, profile):
    """Run full CV pipeline analysis on a screenshot and print results."""
    w, h = img.size
    print("\n=== Screenshot Analysis ===")
    print(f"Size: {w}x{h}")

    hand_region = profile.layout_targets.get("hand_area")
    draw_region = profile.layout_targets.get("draw_area") or profile.layout_targets.get("draw_card")
    print(f"Hand region (profile): {hand_region}")
    print(f"Draw region (profile): {draw_region}")

    # Run detection
    grounding = detect_game_elements(img, hand_region=hand_region, draw_region=draw_region,
                                     canvas_width=w, canvas_height=h)
    print("\n=== Detection Results ===")
    print(f"Method: {grounding.method}")
    print(f"Detection confidence: {grounding.detection_confidence:.2f}")
    print(f"Hand cards detected: {len(grounding.hand)}")
    for card in grounding.hand:
        print(f"  Slot {card.slot_index}: {card.color} {card.number or '?'} "
              f"bbox=({card.bbox['x']},{card.bbox['y']},{card.bbox['width']},{card.bbox['height']}) "
              f"click=({card.click_x},{card.click_y}) "
              f"conf={card.confidence:.2f} num_conf={card.number_confidence:.2f}")
    if grounding.draw_pile:
        dp = grounding.draw_pile
        print(f"Draw pile: bbox=({dp['x']},{dp['y']},{dp['width']},{dp['height']}) "
              f"click=({grounding.draw_pile_click[0]},{grounding.draw_pile_click[1]})")

    # Screen state
    state = detect_screen_state(img)
    print(f"\nScreen state: {state}")

    # Auto-calibration
    print("\n=== Auto-Calibration ===")
    cal = calibrate_from_screenshot(img, w, h)
    print(f"Detected {cal.card_count} cards")
    print(f"Calibrated hand_region: {cal.hand_region}")
    print(f"Calibrated draw_region: {cal.draw_region}")
    for slot in cal.hand_slots:
        print(f"  {slot['slot_id']}: ({slot['click_x']},{slot['click_y']}) color={slot['color']}")
    if cal.draw_area:
        print(f"  draw_area: ({cal.draw_area['click_x']},{cal.draw_area['click_y']})")

    # Check for raw color regions in full image
    all_regions = _find_color_regions(img, min_area=500)
    print("\n=== Raw Color Regions (full image) ===")
    print(f"Total regions: {len(all_regions)}")
    for r in all_regions[:10]:
        print(f"  {r['color']}: bbox=({r['bbox']['x']},{r['bbox']['y']},{r['bbox']['width']},{r['bbox']['height']}) ratio={r['pixel_ratio']:.3f}")

    # Verify detection would produce game_state
    has_top_card = grounding.hand and len(grounding.hand) > 0
    print("\n=== Perception Chain ===")
    print(f"Would produce top_card: {has_top_card}")
    print(f"Would produce hand_cards: {len(grounding.hand) > 0}")
    print(f"Expected game_state confidence: {'>0' if has_top_card else '0 (would trigger not_in_game)'}")

    return grounding


async def capture_from_cdp(cdp_url):
    """Capture screenshot from live Chrome CDP session."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{cdp_url}/json")
            r.raise_for_status()
            tabs = [t for t in r.json() if t.get("type") == "page"]
            print(f"Found {len(tabs)} tabs")
            for t in tabs:
                print(f"  - {t.get('title', '?')} [{t.get('url', '?')}]")
    except Exception as e:
        print(f"CDP not available: {e}")
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
                print("ERROR: No matching tab")
                return None
            print(f"\nSelected tab: {target.url}")
            print(f"Title: {await target.title()}")
            viewport = await target.evaluate("() => ({ w: window.innerWidth, h: window.innerHeight })")
            print(f"Viewport: {viewport}")
            screenshot_bytes = await target.screenshot()
            from io import BytesIO
            return Image.open(BytesIO(screenshot_bytes))
    except Exception as e:
        print(f"Screenshot failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Diagnose scuffed-uno-web session")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--screenshot", help="Path to screenshot file")
    group.add_argument("--live", action="store_true", help="Capture from live Chrome CDP")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args = parser.parse_args()

    if args.live:
        img = asyncio.run(capture_from_cdp(args.cdp_url))
        if img is None:
            sys.exit(1)
    else:
        img = Image.open(args.screenshot)

    profile = load_profile("scuffed-uno-web")
    grounding = analyze_screenshot(img, profile)

    # Summary
    print("\n=== SUMMARY ===")
    if grounding.hand:
        print(f"STATUS: CV detected {len(grounding.hand)} cards — pipeline should produce in_game")
        print("NEXT: Run calibration to update profile coordinates: python scripts/calibrate-scuffed-uno-web.py --live")
    else:
        print("STATUS: CV detected NO cards — pipeline will show not_in_game")
        print("NEXT: Check hand_region coordinates match actual game layout")
        print(f"  Current hand_region: {profile.layout_targets.get('hand_area')}")
        print(f"  Try: python scripts/calibrate-scuffed-uno-web.py --live --cdp-url {args.cdp_url}")


if __name__ == "__main__":
    main()

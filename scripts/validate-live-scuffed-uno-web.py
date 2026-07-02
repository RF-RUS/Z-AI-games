"""Comprehensive live validation for scuffed-uno-web.

Connects to a running Chrome session via CDP, validates the complete
data path from screenshot capture to action grounding, and provides
a calibration step. This is the definitive "does it work live?" test.

Usage:
    python scripts/validate-live-scuffed-uno-web.py --cdp-url http://127.0.0.1:9222
    python scripts/validate-live-scuffed-uno-web.py --cdp-url http://127.0.0.1:9222 --calibrate
    python scripts/validate-live-scuffed-uno-web.py --cdp-url http://127.0.0.1:9222 --click-draw
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "adapter-web" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "schemas" / "src"))

from PIL import Image
from uno_adapter_web.hand_detection import (
    calibrate_from_screenshot,
    detect_game_elements,
    detect_screen_state,
    save_calibration,
)
from uno_adapter_web.profiles import load_profile


@dataclass
class LiveReport:
    cdp_url: str
    page_url: str = ""
    page_title: str = ""
    viewport: dict = None
    dpr: float = 1.0
    canvas_exists: bool = False
    canvas_bounds: dict = None
    screenshot_size: tuple = (0, 0)
    hand_cards_count: int = 0
    hand_cards: list = None
    draw_pile_detected: bool = False
    draw_pile_click: tuple = None
    detection_confidence: float = 0.0
    screen_state: str = "unknown"
    game_state_would_be_set: bool = False
    dom_evidence_has_top_card: bool = False
    action_grounding_present: bool = False
    css_click_coords: dict = None


async def validate_live(cdp_url: str, do_calibrate: bool = False, do_click_draw: bool = False):
    import httpx

    report = LiveReport(cdp_url=cdp_url, hand_cards=[], viewport={})
    errors = []

    # === Step 1: CDP validation ===
    print("=" * 60)
    print("STEP 1: CDP Connection Validation")
    print("=" * 60)

    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{cdp_url}/json")
            r.raise_for_status()
            tabs = r.json()
            page_tabs = [t for t in tabs if t.get("type") == "page"]
            print(f"  CDP endpoint: {cdp_url}")
            print(f"  Total tabs: {len(tabs)}, page tabs: {len(page_tabs)}")
            for t in page_tabs:
                print(f"    - [{t.get('title', '?')[:50]}] {t.get('url', '?')[:80]}")
    except Exception as e:
        print(f"  ERROR: CDP not available: {e}")
        return report, [f"CDP unavailable: {e}"]

    # === Step 2: Connect and validate tab ===
    print("\n" + "=" * 60)
    print("STEP 2: Tab Selection Validation")
    print("=" * 60)

    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.connect_over_cdp(cdp_url)
        except Exception as e:
            errors.append(f"CDP connect failed: {e}")
            print(f"  ERROR: {e}")
            return report, errors

        contexts = browser.contexts
        print(f"  Browser contexts: {len(contexts)}")
        if not contexts:
            errors.append("No browser contexts found")
            return report, errors

        pages = contexts[0].pages
        print(f"  Pages in context: {len(pages)}")

        target = None
        for p in pages:
            url = p.url or ""
            if "scuffeduno" in url.lower() or "scuffed" in url.lower():
                target = p
                break
        if not target and pages:
            target = pages[0]
            print("  WARNING: No scuffed-uno tab found, using first tab")

        if not target:
            errors.append("No page found")
            return report, errors

        report.page_url = target.url
        report.page_title = await target.title()
        print(f"  Selected tab: {report.page_url[:80]}")
        print(f"  Title: {report.page_title[:80]}")

        # Viewport and DPR
        viewport_info = await target.evaluate("""() => ({
            innerW: window.innerWidth,
            innerH: window.innerHeight,
            outerW: window.outerWidth,
            outerH: window.outerHeight,
            dpr: window.devicePixelRatio || 1,
        })""")
        report.viewport = viewport_info
        report.dpr = viewport_info.get("dpr", 1.0)
        print(f"  Viewport: {viewport_info['innerW']}x{viewport_info['innerH']} (outer: {viewport_info['outerW']}x{viewport_info['outerH']})")
        print(f"  DPR: {report.dpr}")

        # Canvas detection
        canvas_info = await target.evaluate("""() => {
            const canvas = document.querySelector('canvas');
            if (!canvas) return null;
            const rect = canvas.getBoundingClientRect();
            return {
                x: rect.x, y: rect.y,
                width: rect.width, height: rect.height,
                canvasWidth: canvas.width,
                canvasHeight: canvas.height,
            };
        }""")
        report.canvas_exists = canvas_info is not None
        report.canvas_bounds = canvas_info
    if canvas_info:
        print(f"  Canvas found: {canvas_info['width']}x{canvas_info['height']} at ({canvas_info['x']},{canvas_info['y']})")
    else:
        print("  Canvas: NOT FOUND (CV pipeline works without DOM canvas element)")

        # === Step 3: Screenshot and CV analysis ===
        print("\n" + "=" * 60)
        print("STEP 3: Screenshot + CV Analysis")
        print("=" * 60)

        screenshot_bytes = await target.screenshot(full_page=False)
        img = Image.open(BytesIO(screenshot_bytes))
        report.screenshot_size = img.size
        print(f"  Screenshot: {img.size[0]}x{img.size[1]}")

        profile = load_profile("scuffed-uno-web")
        hand_region = profile.layout_targets.get("hand_area")
        draw_region = profile.layout_targets.get("draw_area") or profile.layout_targets.get("draw_card")

        print(f"  Hand region (profile): {hand_region}")
        print(f"  Draw region (profile): {draw_region}")

        grounding = detect_game_elements(
            img, hand_region=hand_region, draw_region=draw_region,
            canvas_width=img.size[0], canvas_height=img.size[1],
        )
        report.hand_cards_count = len(grounding.hand)
        report.hand_cards = grounding.hand
        report.draw_pile_detected = grounding.draw_pile is not None
        report.draw_pile_click = grounding.draw_pile_click
        report.detection_confidence = grounding.detection_confidence

        print(f"\n  Detection confidence: {grounding.detection_confidence:.2f}")
        print(f"  Hand cards detected: {len(grounding.hand)}")
        for card in grounding.hand:
            print(f"    Slot {card.slot_index}: {card.color} {card.number or '?'} "
                  f"bbox=({card.bbox['x']},{card.bbox['y']},{card.bbox['width']},{card.bbox['height']}) "
                  f"click=({card.click_x},{card.click_y}) conf={card.confidence:.2f}")
        print(f"  Draw pile: {'YES' if grounding.draw_pile else 'NO'}")
        if grounding.draw_pile_click:
            print(f"    Draw click: ({grounding.draw_pile_click[0]}, {grounding.draw_pile_click[1]})")

        # Screen state
        report.screen_state = detect_screen_state(img)
        print(f"\n  Screen state: {report.screen_state}")

        # === Step 4: Coordinate validation ===
        print("\n" + "=" * 60)
        print("STEP 4: Coordinate-Space Validation")
        print("=" * 60)

        if grounding.hand:
            card = grounding.hand[0]
            css_x = card.click_x / report.dpr
            css_y = card.click_y / report.dpr
            report.css_click_coords = {"x": css_x, "y": css_y}
            print(f"  CV raw coordinates: ({card.click_x}, {card.click_y})")
            print(f"  DPR: {report.dpr}")
            print(f"  CSS pixel coordinates: ({css_x:.1f}, {css_y:.1f})")
            print("  These are page.mouse.click() coordinates")
            if canvas_info:
                in_canvas = (canvas_info['x'] <= css_x <= canvas_info['x'] + canvas_info['width'] and
                             canvas_info['y'] <= css_y <= canvas_info['y'] + canvas_info['height'])
                print(f"  Inside canvas bbox: {'YES' if in_canvas else 'NO'}")
                if not in_canvas:
                    errors.append(f"Click coords ({css_x:.1f},{css_y:.1f}) outside canvas bounds")
        else:
            print("  No hand cards — cannot validate coordinates")

        # === Step 5: DOM evidence propagation check ===
        print("\n" + "=" * 60)
        print("STEP 5: Evidence Propagation Check")
        print("=" * 60)

        report.game_state_would_be_set = grounding.hand_cards if hasattr(grounding, 'hand_cards') else len(grounding.hand) > 0
        report.action_grounding_present = grounding.detection_confidence > 0

        if grounding.hand:
            print("  CV detects hand_cards → top_card will be set → game_state populated")
            print("  → screen_state should be: in_game")
            print(f"  → game_state confidence: {grounding.detection_confidence:.2f}")
            report.dom_evidence_has_top_card = True
        else:
            print("  CV detects NO hand_cards → top_card NOT set → game_state = None")
            print("  → screen_state will be: not_in_game")
            print("  → game_state confidence: 0.0")
            report.dom_evidence_has_top_card = False
            errors.append("No hand cards detected — screen_state will be not_in_game")

        # === Step 6: Calibration ===
        if do_calibrate and grounding.hand:
            print("\n" + "=" * 60)
            print("STEP 6: Live Calibration")
            print("=" * 60)

            cal = calibrate_from_screenshot(img, img.size[0], img.size[1])
            print(f"  Detected {cal.card_count} cards for calibration")

            if cal.hand_slots:
                profile_path = Path(__file__).resolve().parents[1] / "services" / "adapter-web" / "profiles" / "scuffed-uno-web.json"
                save_calibration(cal, profile_path)
                print(f"  Saved to {profile_path}")
                print(f"  Hand region: {cal.hand_region}")
                print(f"  Draw region: {cal.draw_region}")
                for slot in cal.hand_slots:
                    print(f"    {slot['slot_id']}: ({slot['click_x']},{slot['click_y']}) color={slot['color']}")

        # === Step 7: Execute draw_card ===
        if do_click_draw and grounding.draw_pile_click:
            print("\n" + "=" * 60)
            print("STEP 7: Execute Draw Card Click")
            print("=" * 60)

            dp_x = grounding.draw_pile_click[0] / report.dpr
            dp_y = grounding.draw_pile_click[1] / report.dpr
            print(f"  Draw pile CV coords: ({grounding.draw_pile_click[0]}, {grounding.draw_pile_click[1]})")
            print(f"  CSS coords: ({dp_x:.1f}, {dp_y:.1f})")
            print(f"  Executing: page.mouse.click({dp_x:.1f}, {dp_y:.1f})")

            try:
                await target.mouse.click(dp_x, dp_y)
                await asyncio.sleep(1.0)
                after_bytes = await target.screenshot(full_page=False)
                after_img = Image.open(BytesIO(after_bytes))
                after_grounding = detect_game_elements(
                    after_img, hand_region=hand_region, draw_region=draw_region,
                    canvas_width=after_img.size[0], canvas_height=after_img.size[1],
                )
                print("  Click executed successfully")
                print(f"  Hand cards after: {len(after_grounding.hand)}")
                before_count = len(grounding.hand)
                after_count = len(after_grounding.hand)
                if before_count != after_count:
                    print(f"  DELTA: hand count changed from {before_count} to {after_count}")
                else:
                    print(f"  Hand count unchanged: {after_count}")
                after_state = detect_screen_state(after_img)
                print(f"  Screen state after: {after_state}")
            except Exception as e:
                print(f"  Click FAILED: {e}")
                errors.append(f"Click execution failed: {e}")

    # === Summary ===
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    status = "PASS" if not errors else "FAIL"
    print(f"  Status: {status}")
    print(f"  Tab: {report.page_url[:60]}")
    print(f"  DPR: {report.dpr}")
    print(f"  Canvas: {'YES' if report.canvas_exists else 'NO'}")
    print(f"  Screen state: {report.screen_state}")
    print(f"  Hand cards: {report.hand_cards_count}")
    print(f"  Detection confidence: {report.detection_confidence:.2f}")
    print(f"  Would produce game_state: {report.game_state_would_be_set}")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors:
            print(f"    - {e}")

    return report, errors


def main():
    parser = argparse.ArgumentParser(description="Validate live scuffed-uno-web session")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--calibrate", action="store_true", help="Save calibrated profile")
    parser.add_argument("--click-draw", action="store_true", help="Execute one draw_card click")
    args = parser.parse_args()

    report, errors = asyncio.run(validate_live(args.cdp_url, args.calibrate, args.click_draw))
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()

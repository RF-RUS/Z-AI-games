"""Live E2E proof for scuffed-uno-web.

Connects to Chrome CDP, captures screenshots, runs CV, executes gesture,
and produces verification with detailed evidence summary.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
os.environ['AGENT_SCREENSHOT_TRACE'] = '1'
os.environ['AGENT_SCREENSHOT_TRACE_DIR'] = 'artifacts/agent_trace'


async def run_proof():
    from io import BytesIO

    import httpx
    from PIL import Image

    cdp_url = 'http://127.0.0.1:9222'
    proof_dir = Path('artifacts/agent_trace/live_proof_final')
    proof_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f'{cdp_url}/json')
        tabs = [t for t in r.json() if t.get('type') == 'page']
        scuffed = None
        for t in tabs:
            if 'scuffeduno' in t.get('url', ''):
                scuffed = t
                break
        if not scuffed:
            print('ERROR: no scuffed-uno-online tab found')
            return

    print('Tab found:', scuffed['url'][:60])

    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(cdp_url)
        ctx = browser.contexts[0]
        target = None
        for p in ctx.pages:
            if 'scuffeduno' in (p.url or ''):
                target = p
                break
        if not target:
            print('ERROR: no target page')
            return

        vp = await target.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
        print(f'Viewport: {vp["w"]}x{vp["h"]}')

        # --- OBSERVE ---
        print('\n=== OBSERVE ===')
        before_bytes = await target.screenshot(full_page=False)
        before_img = Image.open(BytesIO(before_bytes))
        (proof_dir / 'before.png').write_bytes(before_bytes)

        from uno_adapter_web.action_verification import (
            compare_grounding,
            verify_action,
        )
        from uno_adapter_web.coordinate_reliability import convert_cv_to_css, validate_click_target
        from uno_adapter_web.gesture_planner import plan_gesture
        from uno_adapter_web.hand_detection import detect_game_elements, detect_screen_state
        from uno_adapter_web.profiles import load_profile

        profile = load_profile('scuffed-uno-web')
        hr = profile.layout_targets.get('hand_area')
        dr = profile.layout_targets.get('draw_area')

        grounding_before = detect_game_elements(before_img, hand_region=hr, draw_region=dr,
                                                 canvas_width=before_img.size[0], canvas_height=before_img.size[1])
        state = detect_screen_state(before_img)

        print(f'Screen: {state}')
        print(f'Hand cards: {len(grounding_before.hand)}')
        for card in grounding_before.hand:
            print(f'  {card.color} {card.number} slot={card.slot_index} click=({card.click_x},{card.click_y})')
        print(f'Draw pile: {grounding_before.draw_pile is not None}')
        print(f'Confidence: {grounding_before.detection_confidence:.2f}')

        # --- GESTURE PLAN ---
        print('\n=== GESTURE PLAN ===')
        action = 'draw_card'
        gesture_plan = plan_gesture(action, profile.profile_id,
                                      target_x=grounding_before.draw_pile_click[0] if grounding_before.draw_pile_click else None,
                                      target_y=grounding_before.draw_pile_click[1] if grounding_before.draw_pile_click else None,
                                      raw_x=grounding_before.draw_pile_click[0] if grounding_before.draw_pile_click else None,
                                      raw_y=grounding_before.draw_pile_click[1] if grounding_before.draw_pile_click else None,
                                      target_source='cv_draw' if grounding_before.draw_pile else 'none',
                                      available_grounding=bool(grounding_before.hand))
        print(f'Gesture: {gesture_plan.gesture_type}')
        print(f'Confidence: {gesture_plan.confidence}')
        print(f'Rationale: {gesture_plan.rationale}')

        if not grounding_before.draw_pile_click:
            print('ERROR: no draw pile target')
            return

        # --- COORDINATE CONVERSION ---
        print('\n=== COORDINATES ===')
        raw_x = grounding_before.draw_pile_click[0]
        raw_y = grounding_before.draw_pile_click[1]
        coord = convert_cv_to_css(raw_x, raw_y, 1.0, None, vp['w'], vp['h'])
        print(f'Raw: ({raw_x}, {raw_y})')
        print(f'CSS: ({coord.css_x:.1f}, {coord.css_y:.1f})')
        print(f'Valid: {coord.valid}')
        valid, reason = validate_click_target(coord.css_x, coord.css_y)
        print(f'Validation: {valid} ({reason})')

        # --- EXECUTE ---
        print('\n=== EXECUTE ===')
        print(f'Clicking at ({coord.css_x:.1f}, {coord.css_y:.1f})...')
        await target.mouse.click(coord.css_x, coord.css_y)
        await asyncio.sleep(0.5)

        # --- POST-ACTION ---
        print('\n=== POST-ACTION ===')
        after_bytes = await target.screenshot(full_page=False)
        after_img = Image.open(BytesIO(after_bytes))
        (proof_dir / 'after.png').write_bytes(after_bytes)

        grounding_after = detect_game_elements(after_img, hand_region=hr, draw_region=dr,
                                                canvas_width=after_img.size[0], canvas_height=after_img.size[1])
        after_state = detect_screen_state(after_img)

        print(f'Screen after: {after_state}')
        print(f'Hand cards after: {len(grounding_after.hand)}')
        for card in grounding_after.hand:
            print(f'  {card.color} {card.number} slot={card.slot_index}')
        print(f'Draw pile after: {grounding_after.draw_pile is not None}')
        print(f'Confidence after: {grounding_after.detection_confidence:.2f}')

        # --- VERIFICATION ---
        print('\n=== VERIFICATION ===')
        evidence = compare_grounding(grounding_before, grounding_after)
        vr = verify_action(action, gesture_plan.gesture_type.value,
                            delivery_success=True, evidence=evidence)
        print(f'Delivery: {vr.delivery}')
        print(f'Outcome: {vr.outcome}')
        print(f'Rationale: {vr.rationale}')

        # --- SAVE METADATA ---
        meta = {
            'before': {'screen': state, 'hand_cards': len(grounding_before.hand),
                       'draw_pile': grounding_before.draw_pile is not None,
                       'confidence': grounding_before.detection_confidence,
                       'viewport': vp},
            'gesture': {'type': gesture_plan.gesture_type, 'confidence': gesture_plan.confidence},
            'coords': {'raw': {'x': raw_x, 'y': raw_y}, 'css': {'x': coord.css_x, 'y': coord.css_y}},
            'after': {'screen': after_state, 'hand_cards': len(grounding_after.hand),
                      'draw_pile': grounding_after.draw_pile is not None,
                      'confidence': grounding_after.detection_confidence},
            'verification': {'delivery': vr.delivery, 'outcome': vr.outcome, 'rationale': vr.rationale},
            'evidence': {'before_colors': evidence.before_hand_colors, 'after_colors': evidence.after_hand_colors,
                         'hand_count_changed': evidence.hand_count_changed, 'top_card_changed': evidence.top_card_changed,
                         'draw_pile_changed': evidence.draw_pile_changed},
        }
        (proof_dir / 'proof.json').write_text(json.dumps(meta, indent=2, default=str))
        print(f'\nArtifacts saved to {proof_dir}')
        for f in sorted(proof_dir.iterdir()):
            print(f'  {f.name} ({f.stat().st_size} bytes)')

asyncio.run(run_proof())

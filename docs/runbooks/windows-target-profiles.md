# Windows Target Profiles

Schema: `WindowsAdapterProfile` in `packages/schemas/adapter_windows.py`

## Window Discovery

The picker uses **Win32 `EnumWindows` API** directly (not pywinauto UIA enumeration). This means:

- All visible top-level windows appear in the picker, including protected/game processes
- Some system windows (Program Manager, NVIDIA Overlay) may also appear — these are harmless
- If a window doesn't appear, check: is it visible? does it have a title? is it a top-level window?

## Selection Flow

1. Open picker → see all visible windows
2. Select game window (e.g., "UNO")
3. Click Attach
4. Adapter connects and captures screenshot
5. If screen is black or game state is "Unknown":
   - **Check adapter type**: Canvas/WebGL games need `adapter_type=web`, not `adapter_type=windows`
   - **Check profile**: `real-uno-desktop` is for preview only — actual game play needs `scuffed-uno-web`
   - **Check UIA actionability**: Canvas games don't expose UIA controls

## Which adapter for which game

| Game type | Correct adapter | Profile | Why |
|-----------|----------------|---------|-----|
| DOM web game (Pizzuno) | `web` (Playwright) | `real-unoh-web` | DOM selectors work |
| Canvas/WebGL game (Scuffed UNO) | `web` (Playwright) | `scuffed-uno-web` | Screenshot + coordinates |
| Windows UIA app (tkinter, WPF) | `windows` (pywinauto) | `local-mock-uno` | UIA controls exposed |
| Canvas desktop game (UNO.exe) | `web` (Playwright) via CDP | `scuffed-uno-web` | Canvas not UIA-actionable |
| Preview only (any desktop) | `windows` | `real-uno-desktop` | Screenshot + UIA tree (if available) |

**Key rule**: If the game renders on canvas/WebGL/DirectX, use the **web adapter**. The Windows adapter only works with UIA-accessible controls.

## Authoring steps

1. Copy `profiles/template-external-uno.json`
2. Set `window.title_regex` / `process_name`
3. Map controls in `selectors` and `chat_selectors`
4. Use Inspect.exe or `print_control_identifiers()` to find locators
5. Validate: `pytest tests/unit/test_adapter_windows_profiles.py`

## Locator priority

1. `auto_id`
2. `control_type` + `title`
3. `title_regex`
4. Coordinates (last resort — not primary in this adapter)

## Profiles shipped

| ID | Purpose | Limitations |
|----|---------|-------------|
| `local-mock-uno` | tkinter test app (CI) | Mock only |
| `real-uno-desktop` | Attach to open UNO desktop client | **Preview only** — game play not UIA-actionable |
| `template-external-uno` | Customization template | Generic |

## Why UNO.exe shows "black screen" after attach

UNO.exe is a **canvas/DirectX game** — it renders cards using GPU, not Windows UIA controls. When the Windows adapter attaches:

1. ✅ Attach succeeds (HWND found, window connected)
2. ✅ Screenshot captured (file exists on disk)
3. ❌ UIA extraction returns empty tree (no controls exposed)
4. ❌ Perception service gets empty data → "Game state not extractable"
5. ❌ Operator shows "black screen" (screenshot exists but perception can't read it)

**Fix**: Use web adapter with `scuffed-uno-web` profile for canvas games. The Windows adapter is for UIA-accessible apps only.

### Screenshot pipeline status

The screenshot IS captured by the Windows adapter (`capture_live_frame()` → `capture_window_screenshot()`). The orchestrator now passes screenshot data to the perception service.

The perception service has a `HeuristicCanvasUNOPlugin` that analyzes screenshots using profile-guided zones and color/size heuristics. It detects:
- Screen validity (not black/empty)
- Region detection (hand area, play area, draw pile)
- Actionable targets (clickable regions)

This enables the agent to:
1. Detect screen is valid
2. Detect at least one actionable target (e.g., draw pile)
3. Execute a click on that target
4. Verify screen changed after click

For full card recognition, VLM/CV integration is needed (future work).

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Window not in picker | Window is hidden or not top-level | Verify with Task Manager |
| Attach succeeds but "Unknown" game state | Canvas game, no UIA controls | Switch to web adapter + `scuffed-uno-web` |
| Screenshot is black | Adapter attached to wrong window | Check window title in picker |
| UIA tree is empty | Game renders via DirectX/OpenGL | Use web adapter for canvas games |
| `match_automation: "web_only"` | Profile is preview-only | Use web adapter for actual gameplay |

# Windows UIA Debugging

## Window Discovery

The picker uses **Win32 `EnumWindows` API** (not pywinauto UIA). All visible top-level windows appear, including protected/game processes like UNO.exe.

## Check

```powershell
curl http://127.0.0.1:8105/pywinauto/check
```

## Launch test target

```powershell
python services/adapter-windows/test-target/uno_mock_app.py
```

## List windows

```powershell
curl http://127.0.0.1:8105/windows/candidates
```

## Common issues

| Issue | Fix |
|-------|-----|
| Window not found | Verify title exists and window is visible; use `/windows/candidates` |
| Sparse tree / empty extracted | Try `fallback_backend: win32`; inspect with Inspect.exe |
| Browser/canvas game: "Unknown" game state | Canvas games don't expose UIA controls — use **web adapter** instead |
| Attach succeeds but black screen | Game is canvas/DirectX, not UIA-actionable — switch to web adapter |
| Access denied | Run operator elevated if target is elevated |
| pywinauto missing | `pip install pywinauto pillow` |

## Canvas / WebGL games (UNO.exe, browser games)

**Canvas games are NOT UIA-actionable.** The Windows adapter can attach and take screenshots, but cannot extract game state via UIA.

| Game | Correct adapter | Profile | Why |
|------|----------------|---------|-----|
| UNO.exe (desktop) | web (Playwright via CDP) | `scuffed-uno-web` | Canvas/DirectX, no UIA controls |
| Scuffed UNO (browser) | web (Playwright) | `scuffed-uno-web` | Canvas/WebGL |
| Pizzuno (browser) | web (Playwright) | `real-unoh-web` | DOM selectors |
| tkinter mock | windows (pywinauto) | `local-mock-uno` | UIA controls exposed |

**If you see "Unknown" game state after attaching to a canvas game:**
1. The adapter attached successfully (HWND found)
2. Screenshot was captured (file exists on disk)
3. But UIA extraction found no controls → perception returns "unknown"
4. **Fix**: Switch to web adapter with appropriate profile

## Scuffed Uno (canvas / WebGL)

Use **web adapter** profile `scuffed-uno-web` with Playwright — not Windows UIA.

| Mode | UIA/DOM | Automation |
|------|---------|------------|
| Lobby | HTML buttons visible (Quick Play) | DOM bootstrap or manual |
| In-match | Canvas only — no card controls in tree | `CLICK_COORDINATE` via profile `layout_targets` |

Windows attach (`real-uno-desktop`) remains valid for **preview only**; match `play_card` is blocked with a redirect message.

```powershell
# Session: adapter=web, profile=scuffed-uno-web, mode=playwright
curl -X POST http://127.0.0.1:8100/sessions/.../attach -d '{"adapter_type":"web","profile_id":"scuffed-uno-web"}'
```


Web games rendered on `<canvas>` or WebGL typically expose only `Document` / `Pane` nodes to UIA.
Inspect.exe and Accessibility Insights will **not** show card buttons or game controls unless the page
implements ARIA or Chrome accessibility is forced.

### Verify with Inspect.exe

1. Install [Accessibility Insights for Windows](https://accessibilityinsights.io/docs/windows/overview/) or Windows SDK Inspect.exe.
2. Attach to the Chrome window **after** the UNO game tab is focused.
3. If you see only `Document` / root panes and no `Button` nodes for game actions, the page is **not UIA-actionable**.

### Try `--force-renderer-accessibility`

Launch Chrome with the flag, then re-attach:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --force-renderer-accessibility "https://your-uno-game-url"
```

Re-run Inspect.exe. If controls still do not appear, the game does not publish an accessibility tree.

### Operator behavior

When UIA actionability check fails, the adapter reports:

- `uia_actionable: false` on preview state
- Action errors name **coordinate/vision fallback** or the **web adapter (Playwright)** instead of generic "target not found"

Do not rely on profile UIA selectors (`auto_id` / `name`) for canvas-only browser games.

## Tkinter mock app (`local-mock-uno`)

The test target does not publish control names in UIA/win32. Operator uses:

- **`layout_targets`** — relative coordinates within window bounds
- **Aliases** — `draw` → `draw_button`, `play_red_five` → `play_button`

Locator distinguishes **target not found** vs **confidence below threshold**. Visual executor avoids UNCERTAIN solely from `no_visible_change` on static mock UI.

If click succeeds but action still fails — check post-action verification (`ui_verifier.py`, `visual_executor.py`).

### Playwright startup stages

Attach logs and fails with an explicit stage name:

1. `browser_launch`
2. `context_page`
3. `page_goto`
4. `readiness_wait` (soft for `scuffed-uno-web`)
5. `bootstrap` (optional; disabled on scuffed profile attach)
6. `diagnostics`

If the UI shows `Attach request timed out after 3000ms`, increase client timeout — web attach uses 120s.
Set `UNO_PLAYWRIGHT_CHANNEL=chrome` or `UNO_PLAYWRIGHT_EXECUTABLE` if bundled Chromium fails to launch.

## Capture fixture

```powershell
python scripts/capture-windows-fixture.py --mode mock
python scripts/capture-windows-fixture.py --mode pywinauto --launch-test-target
```

## Failure artifacts

Enable `capture_screenshots: true` on actions — saves before/after/failure PNGs under `services/adapter-windows/artifacts/`.

# AGENT_LOG

Append-only. Newest last.

---

### 2026-07-04 — Real-run debugging: no gameplay + Stop/New bugs
- **Trigger:** User ran real `UNO.exe` via Operator. Symptom: screen captured, mouse kept
  returning to ONE fixed point, no card recognition / no play; Stop didn't stop; New didn't reset.
- **Root causes found (verified in code):**
  1. **No real gameplay is wired for desktop canvas games.** `flow_controller.run_cycle` gets
     legal actions from a *simulated engine* (`game_id`), NOT from the screen; the windows executor
     locates targets by `selector_key` via UIA→static layout and *ignores* screenshot-detected
     coordinates. `HeuristicCanvasUNOPlugin.infer_from_screenshot` (perception) produces card coords
     but nothing consumes them for clicks. → new task #9 + Decision D5.
  2. **Fixed-point mouse:** canvas game = empty UIA → target cascade falls to Step 5 static
     `layout_targets` (`real-uno-desktop.json` `play_button {0.56,0.34}`, conf 0.72 > gate) → same
     absolute point every tick. Profile self-declares `match_automation:web_only`, "preview only,
     use web adapter for match play."
  3. **Pause never held:** `_run_loop` lumped PAUSED with ERROR and force-reset it to ACTIVE, so the
     loop kept acting through Pause.
  4. **New button dead:** `OperatorWorkspace` `onNewSession={() => {}}` — a no-op.
- **Fixes applied (this session):**
  - `orchestrator._run_loop`: PAUSED now HALTS the loop (resume() spawns a fresh loop); ERROR still
    auto-recovers (unchanged, test-backed).
  - `target_locator.locate_selector`: suppress static `layout_targets` fallback when
    `match_automation=="web_only"` → no more blind fixed-point clicks; executor reports uncertain.
  - `App.tsx`/`OperatorWorkspace.tsx`: `onNewSession` wired — stop session + return to setup + clear.
- **Files changed:** `services/session-orchestrator/src/uno_orchestrator/orchestrator.py`,
  `services/adapter-windows/src/uno_adapter_windows/rpa/perception/target_locator.py`,
  `apps/control-center/src/App.tsx`, `apps/control-center/src/operator/OperatorWorkspace.tsx`,
  `tests/unit/test_session_control_and_blind_click.py` (NEW).
- **Verified:** ruff clean; `pytest tests/unit` 295 passed / 7 skipped (+3 new); vitest 34/34.
  Real UNO.exe behavior change (no blind click; Pause holds) is unverified on hardware (macOS host).
- **Next:** #9 CV→execution wiring epic (needs Windows host + direction decision — see BLOCKERS #B2).

---

### 2026-07-04 — Direction decided + CV coordinate plumbing (task #9, step 1)
- **Direction (user):** UNO.exe is a **native Electron app**; play via **Windows adapter + CV**
  (screenshot → cards + coords). B2 resolved; Path A (Decision D5).
- **Two real CV bugs found while wiring:**
  1. `recognize_cards_from_zones` only ran recognition when `output_dir` was set (it needed a crop
     file on disk). The production merger passes no `output_dir` → **card recognition never ran in
     real sessions.** Fixed: crop to a temp file (auto-cleaned) so recognition always runs in-memory.
  2. Detected `bounds` (absolute screen coords) were **dropped** — `recognition_to_dict` omitted them
     and `canvas_plugin` kept only `hand_count`. So even if cards were detected, their click coords
     never reached the observation. Fixed: propagate full `hand_cards` with `bounds` + `center`.
- **Files changed:** `card_recognition.py` (in-memory recognition + bounds/center in dict),
  `canvas_plugin.py` (propagate full hand_cards), `tests/unit/test_cv_hand_coordinates.py` (NEW fixture test).
  (merger already reads `hand_cards` → observation.game_state now carries them.)
- **Verified:** ruff clean; fixture test proves a synthetic screenshot yields hand_cards with absolute
  bounds+center in the observation; `pytest tests/unit` 296 passed / 7 skipped. No hardware validation.
- **Remaining for real play (see BLOCKERS #B3 + TODO #9 breakdown):** per-card hand SEGMENTATION
  (current CV treats the whole hand strip as ONE card — can't locate individual cards), then execution
  grounding (click the detected card coord) + legal actions derived from the detected state. Per-card
  segmentation needs a REAL screenshot of the game to calibrate.

---

### 2026-07-04 — Per-card hand segmentation calibrated on real frames (task #9b)
- **Trigger:** User provided 3 real UNO desktop screenshots → saved as fixtures
  (`tests/fixtures/uno_desktop/{hand7_a,hand7_b,hand8}.jpeg`, 1296x759).
- **Did:** Built `services/perception-service/src/uno_perception/hand_segmentation.py`:
  detect hand extent (bright card cols vs red table) → estimate count (width/~60px) → even slots →
  per-slot bounds + click center + dominant colour (HSV buckets). Integrated into
  `card_recognition.recognize_cards_from_zones` (hand zone → one card per slot). Calibrated
  `canvas_plugin` default zones to the real centered layout (hand/discard/draw).
- **Verified against REAL frames:** hand7_a → 7 cards [G,G,B,B,B,B,wild] exact; click centers land on
  each card (452,513,574,635,696,757,819). Fixture tests assert count ±1, monotonic centers, colour
  signal (green-first / blue-present / wild-last). `pytest tests/unit` 299 passed / 7 skipped (+3).
- **Files:** `hand_segmentation.py` (NEW), `card_recognition.py`, `canvas_plugin.py`,
  `tests/unit/test_hand_segmentation.py` (NEW), fixtures.
- **Honest limits:** card VALUE not recognised yet (colour+coord only); count exact within ±1;
  value recognition + exact count need live tuning on Windows (#B1). B3 resolved.
- **Next:** [9c] execution grounding — click the chosen card's detected coordinate.

---

### 2026-07-04 — Real Windows run diagnosed + CRITICAL screenshot fix + 9c grounding
- **Trigger:** User ran on real Windows. Operator showed GAME STATE **Unknown**, screen_state
  **not_in_game**, "Game state not extractable from UI automation tree", action → draw_card,
  "coarse state unchanged: not_in_game", "session stale". Mouse moved (cursor visible) but no play.
- **ROOT CAUSE (critical):** `flow_controller._observe` read a **non-existent** `bundle.screenshot`
  attribute. `GenericEvidenceBundle` carries the frame as `.screenshot_path` + raw dict in `.extra`,
  so the screenshot was ALWAYS dropped for real windows/web → screenshot CV never ran → empty
  game_state → every frame classified `not_in_game` → agent never played. **This is why nothing
  happened.** Fixed: reconstruct ScreenshotFrame from `extra["screenshot"]` / `screenshot_path`.
  Verified end-to-end: real frame → game_state{in_game, 7 hand_cards w/ coords}. (commit 6d38cd9)
- **9c execution grounding (done):** thread the CV-detected card coordinate through
  `flow._execute` (passes observation.hand_cards) → `map_action`/`_map_action_windows`
  (`_find_card_center` → target_x/target_y) → `WindowsActionExecutionRequest` (+target_x/y) →
  `visual_executor._execute_grounded_click` (screenshot→screen transform + humanized click).
  Now the windows agent clicks the real detected card instead of a static point.
- **Files:** `flow_controller.py`, `adapter_registry.py`, `adapter_windows.py` (schema),
  `visual_executor.py`, + tests `test_observe_screenshot_extraction.py`,
  `test_windows_grounded_click.py`.
- **Verified:** ruff clean; `pytest tests/unit` 307 passed / 7 skipped (+8); mock autonomous run 3/3 ok.
- **Needs Windows host (#B1):** validate the screenshot→screen coordinate transform (DPI scaling)
  and end-to-end real clicks; tune value recognition + exact card count.

---

### 2026-07-05 — Real run still not_in_game → diagnostic marker [CVv2]
- **Trigger:** User reran on Windows. Operator STILL shows the OLD message "Game state not extractable
  from UI automation tree" + GAME STATE Unknown + not_in_game, though confidence rose 55%→80% and
  action became play_card ("number card" — from the SIMULATED engine, not the screen).
- **Diagnosis:** that message only fires when `observation.confidence.game_state == 0.0`, i.e. the
  screenshot-CV branch did NOT run. My whole real path is correct in code (ServiceClients.perceive
  forwards the screenshot L91-92; perception /perceive → build_observation → merger → canvas_plugin).
  So the running BACKEND is almost certainly OLD code (services not restarted after pull), or the
  screenshot isn't reaching perception. The old message still appearing = my code isn't live.
- **Did:** Replaced the vague error with a precise, UI-visible, version-marked diagnostic in
  `flow_controller` perceive step: `[CVv2] screenshot=WxH screen_type=.. gs_conf=.. hand_cards=N`,
  and distinct messages for screenshot=NONE (restart backend) vs received-but-no-cards (calibration).
- **Files:** `services/session-orchestrator/src/uno_orchestrator/flow_controller.py`.
- **Verified:** ruff clean; tests/unit 307 passed / 7 skipped (extraction_guard still green).
- **Action for user:** pull, **restart backend (dev-backend.ps1)**, rerun. NEXT ACTION must show
  `[CVv2]…`; if not, backend wasn't restarted. Send that line + the latest captured frame from
  `services/adapter-windows/artifacts/**/evidence-*.png`.

---

### 2026-07-05 — [CVv2] live → BLACK Electron capture; fixed capture fallthrough
- **Diagnostic came back:** Operator NEXT ACTION now shows `[CVv2] screenshot=1296x759 screen_type=?
  gs_conf=0.00 hand_cards=0` → **my code IS live**; screenshot reaches perception at the right size
  but CV finds 0 cards. The "Agent evidence" preview is dark. → the capture of the GPU-accelerated
  **Electron** window returns an all-BLACK frame (correct size, no pixels).
- **Root cause:** `capture_window_screenshot` method 1 (`capture_as_image`) returns a black-but-valid
  image for Electron/Chromium and short-circuits before the methods that DO capture DWM-composited
  content (PrintWindow with PW_RENDERFULLCONTENT=0x2, screen-region grab).
- **Fixed:** rewrote capture to try methods in order and return the FIRST NON-BLACK result
  (`is_mostly_black` detector); reordered to prefer PrintWindow(PW_RENDERFULLCONTENT) + ImageGrab.
  Added mean-brightness to the [CVv2] diagnostic (`avg_brightness=N(BLACK)`) to confirm.
- **Files:** `runtime.py` (capture rewrite + `is_mostly_black`), `flow_controller.py` (brightness in
  diag), `tests/unit/test_black_frame_detection.py` (NEW).
- **Verified:** ruff clean; tests/unit 310 passed / 7 skipped (+3). Capture itself needs Windows to
  confirm, but the black-detection + method order is the standard fix for Electron capture.
- **Next for user:** pull, restart backend, rerun windows session. Expect the [CVv2] line to show a
  real brightness and hand_cards>0. If avg_brightness still (BLACK), the window needs a different
  capture path (Windows.Graphics.Capture) — will handle then.

### 2026-07-03 16:48 MSK — Audit of screenshot-driven Windows agent
- **Did:** Mapped Windows agent architecture end-to-end (adapter-windows RPA layer, runtime capture,
  orchestrator autonomous loop, recovery). Ran baseline `start-orchestrator-session-windows.py --tick`.
- **Files read:** `adapter-windows/.../rpa/{executor/visual_executor,perception/target_locator,verification/ui_verifier,driver/input_driver,session_state}.py`,
  `runtime.py`, `orchestrator.py` (`_run_loop` L798-831), `recovery.py`, `in_process_clients.py`, `test_windows_session_tick.py`.
- **Verified:** Baseline single-tick script fails standalone — default `SessionOrchestrator()` uses HTTP
  adapter clients (ports 8100+) which aren't running → `httpx.ConnectError`. In-process path
  (`SessionOrchestrator(clients=InProcessClients())` + registered adapter) is the way to run mock cross-platform.
- **Result:** Architecture is mature; the gap for the stated goal is the **autonomous long-run harness**
  (continuous loop entrypoint, checkpoint/resume, watchdog), not the perception/decision core.
- **Files changed:** created AGENT_STATUS/TODO/LOG/DECISIONS/BLOCKERS.md.
- **Next:** [#1] in-process windows adapter registry helper, then [#2] autonomous runner.

---

### 2026-07-03 16:55 MSK — Autonomous runner + checkpoint/resume (tasks #1,#2,#3)
- **Did:** Built the autonomous long-run harness and the in-process wiring it needs.
- **Files changed:**
  - `packages/shared-utils/src/uno_shared/adapter_registry.py` — `GenericAdapterClient` gains
    optional `transport=` (ASGI) via new `_client()` helper; all 6 HTTP calls routed through it.
    Backward compatible (default None = real network).
  - `services/session-orchestrator/src/uno_orchestrator/in_process_clients.py` — new
    `setup_in_process_windows_registry()` registers adapter-windows over ASGI transport.
  - `scripts/run-windows-agent.py` — NEW. Continuous tick loop; `--max-ticks`/`--max-duration`/
    `--tick-interval`; atomic JSON checkpoint per tick; `--resume`; JSONL run log; SIGINT/SIGTERM
    graceful stop; `--in-process` (default) / `--http`.
- **How verified:**
  - `run-windows-agent --run-id smoke --max-ticks 5` → attach OK, 5/5 ticks ok (perceive→decide
    (mock model)→execute→record). Artifacts in `artifacts/agent-runs/smoke/`.
  - `--resume --max-ticks 3` → tick_count continued 6→8, restarts=1, atomic checkpoint intact.
  - `ruff check` clean; `pytest test_windows_session_tick + test_orchestrator_windows_attach` → 8 passed.
- **Result:** Autonomous loop + cross-session resume works end-to-end on the cross-platform mock path.
- **Next:** [#4] process-level watchdog/auto-restart, then [#5] long-run mock validation + fault injection.

---

### 2026-07-03 17:05 MSK — Watchdog + adaptive backoff + long-run/fault validation (#4,#5)
- **Did:** Added process supervisor, self-healing backoff, and validated long unattended runs.
- **Files changed:**
  - `scripts/watchdog-windows-agent.py` — NEW. Supervises the runner; restarts on crash with
    exponential backoff (`--backoff`/`--backoff-max`), `--max-restarts`, always `--resume`;
    forwards SIGINT/SIGTERM; stops on clean child exit (rc=0). Passthrough args → runner.
  - `scripts/run-windows-agent.py` — adaptive backoff: after N consecutive tick errors, wait
    `min(interval*2^N, --error-backoff-max)` before next tick; a success resets cadence.
- **How verified (all on local-mock-uno, in-process):**
  - Watchdog clean-exit: rc=0 → no restart. Crash path: forced non-zero → 2 restarts w/ backoff → giveup.
  - 100-tick continuous run: **0 process crashes**, clean exit. (60 "errors" were adapter 429
    rate-limits from a deliberately aggressive 0.02s interval — an adapter guard, not an agent bug.)
  - 40 ticks @ 0.15s (under rate limit): **40/40 ok**.
  - Adaptive backoff @ 0.02s: self-heals — 22/30 ok with 8 backoff→recover cycles (was ~40% without).
  - **Fault injection:** `kill -9` at tick 5 → checkpoint durable → `--resume` continued 6→9, restarts=1.
- **Result:** Autonomous + recoverable + resumable + long-run + fault-tolerant — all confirmed on mock.
  DoD met except the real-Windows/pywinauto run (#B1, needs a Windows host).
- **Next:** [#8] docs (runbook + resume), then [#6] verification hardening (backlog).

---

### 2026-07-03 17:12 MSK — Docs + regression check (#8)
- **Did:** Documented the autonomous harness for handoff/resume by another session or agent.
- **Files changed:** `docs/runbooks/autonomous-windows-agent.md` (NEW — modes, quick start, resume,
  watchdog, flags, two-tier recovery, artifacts, constraints); `README.md` (runbook table + core
  commands reference the new scripts).
- **How verified:** ruff clean on all changed files; full `pytest tests/unit` regression run.
- **Next:** [#6] verification hardening remains in backlog (needs profile region metadata; deferred
  to avoid unvalidated edits to perception core). [#7] real-Windows run blocked on host (#B1).

---

### 2026-07-05 — ROOT CAUSE of stale perception: dev-backend never stops services
- **Diagnostic:** `[CVv3] pcv=MISSING avg_brightness=101` → capture is fine (real content) but the
  PERCEPTION service (:8103) runs stale code. The pcv marker nailed it.
- **ROOT CAUSE:** `scripts/dev-backend.ps1` only `Start-Process`'d services, never stopped old ones.
  uvicorn runs without `--reload`, so after `git pull` old processes keep serving OLD code and
  re-running just spawns duplicates that fail to bind. → every "restart" left perception stale.
- **Fixed:** dev-backend.ps1 now kills any listener on each service port before starting; added
  `scripts/stop-backend.ps1`. New code guaranteed live after pull.
- **Also:** saved `hand3.jpeg` (3 fanned cards); segmentation over-counts it (6 vs 3) — sparse fanned
  hands overlap without gaps + wider per-card spacing than the width/60 model. Known limitation, needs
  live tuning; NOT a blocker for reaching in_game.
- **Files:** `scripts/dev-backend.ps1`, `scripts/stop-backend.ps1` (NEW), fixture `hand3.jpeg`.
- **Next for user:** pull, run FIXED `dev-backend.ps1` (or `stop-backend.ps1` then `dev-backend.ps1`),
  rerun → expect `pcv=v3`, `screen_type=in_game`, `hand_cards>0`, GAME STATE ≠ Unknown.

---

### 2026-07-12 — Real UNO run: pcv still MISSING + heuristic CV is a dead end for "any game"
- **Trigger:** User ran real **Ubisoft UNO.exe** on Windows. Operator error:
  `Screenshot received but no cards recognized. [CVv3] pcv=MISSING(restart-perception-8103)
  screenshot=1296x759 screen_type=? gs_conf=0.00 hand_cards=0 avg_brightness=101
  frame=…\bc71664f-…\evidence-1783247622720.png`. Agent still not playing. User re-anchored the
  goal: this must be a **universal agent that can play ANY card game**, not a UNO-specific script.
- **Two stacked problems, diagnosed against code:**
  1. **Infra (still open): perception :8103 runs stale code.** `cv_build="v3"` is set in
     `merger.py:93` only inside the perception service; the marker arrives as `pcv=MISSING`, so the
     screenshot reaches the *orchestrator* (1296x759, brightness 101 = real content, NOT black — the
     07-05 capture fix works) but the **perception process was not restarted** with current code.
     `dev-backend.ps1` fix from 07-05 not yet applied on the user's host, or services not killed.
  2. **Architecture (the real one): the heuristic CV cannot read this game and never will.**
     `canvas_plugin.HeuristicCanvasUNOPlugin` uses fixed relative zones (hand `rel_x=0.30,rel_y=0.75`)
     + `hand_segmentation` `width/~60px` card model + HSV colour buckets, all calibrated on the flat
     `scuffed-uno-web` fixtures. The real screenshot is Ubisoft UNO: **3D radial table, 3 cards fanned,
     overlapping and rotated** (red 6 / green reverse / yellow reverse for player "Goldberg"), glossy
     reflections. This is exactly the known `hand3.jpeg` failure mode (sparse fanned hand → over/under
     count, angled cards break axis-aligned slots). Per-game zone calibration does NOT scale to
     "any card game" — it is the wrong abstraction for the stated goal.
- **Key finding (unblocks the pivot):** the perception contract **already has a VLM slot** —
  `api.py:27 vlm: VisionInference|None`, and `merger.py:195/239` already consume `vlm.structured`
  (`top_card`, `hand_cards`). **But nothing ever produces it** — the observe→perceive path passes only
  `dom/ui/screenshot`, so `vlm` is always `None` and we fall back to the UNO heuristic. Wiring a real
  VLM producer (screenshot → structured game state) is both the fix for THIS game and the correct
  architecture for a universal agent. See Decision **D6 (proposed)**.
- **No code changed this session** — diagnosis + status refresh only (user asked to update status).
- **Immediate action for user:** run `stop-backend.ps1` then `dev-backend.ps1`, rerun once. If `pcv`
  finally shows `v3` and `hand_cards` is still 0/wrong on this fanned hand, that CONFIRMS the heuristic
  can't read real UNO → proceed with D6 (VLM perception).
- **Next (proposed):** [#10] VLM perception producer feeding the existing `vlm` slot; make the
  game-specific heuristic a fallback, not the primary path. Then [9d] legal actions from detected state.

---

### 2026-07-12 (b) — ROOT CAUSE of pcv=MISSING: dev-backend.ps1 built a wrong PYTHONPATH
- **Trigger:** User ran the FIXED `stop-backend.ps1`+`dev-backend.ps1` and STILL got
  `pcv=MISSING(restart-perception-8103) … avg_brightness=103 hand_cards=0`. So "stale service" was
  NOT the real cause — a restart couldn't fix it. Stopped telling the user to restart; read the code.
- **ROOT CAUSE (real this time):** `dev-backend.ps1` L44 built each service's source path as
  `services/$($svc.Name -replace '-service','')/src`. The folders on disk keep the suffix
  (`services/perception-service/src`), so for EVERY `*-service` the `-replace` produced a
  NON-EXISTENT dir (`services/perception/src`). `uvicorn` then imported the **stale globally-installed
  `uno_perception`** instead of this repo → the new CV code (`cv_build="v3"`, screenshot branch) never
  loaded, so `pcv` was MISSING no matter how many times the backend was restarted. Verified: real
  dirs are `perception-service`, `config-service`, `decision-service`, `model-runtime-service`,
  `chat-*-service`, `model-registry-service`, `observability-service`, `state-replay-service` — 8 of
  14 services were importing stale installed packages. (adapter-web/-windows, uno-core,
  session-orchestrator have no `-service` suffix so they happened to work — which is why the
  orchestrator's `[CVv3]` marker WAS live while perception was not.)
- **Second, latent bug:** L44 also **overwrote** `$env:PYTHONPATH` each loop iteration instead of
  scoping it per-process, so services leaked each other's paths. Fixed alongside.
- **Why tests never caught it:** `scripts/run-tests.ps1` builds PYTHONPATH via
  `Get-ChildItem services/*/src` (globs real dirs) → tests always imported repo code and passed, while
  the live backend imported stale packages. Classic green-tests / stale-prod split.
- **Fixed:** `dev-backend.ps1` now uses `$svc.Name` verbatim for the source dir, warns if a source dir
  is missing, and logs the resolved `src:` per service so this can never silently regress.
- **Files:** `scripts/dev-backend.ps1`.
- **Verified (macOS):** the `-replace` simulation shows 8/14 services previously pointed at missing
  dirs; with `$svc.Name` verbatim all 14 resolve to real `src` dirs. Live confirmation needs the user's
  Windows host (no backend here).
- **Next for user:** re-pull, run `stop-backend.ps1` then the FIXED `dev-backend.ps1`. Watch the startup
  lines — each must print a real `src:` path and NO "source dir not found" warning. Rerun one session.
  Expect `[CVv3] pcv=v3` at last. If `pcv=v3` but `hand_cards=0` on the fanned hand → that is the REAL
  (D6) heuristic-can't-read-real-UNO result, and we proceed to #10 VLM perception.

---

### 2026-07-12 (c) — Plan A: perceived game state now flows to the operator panel
- **Trigger:** Real run — pcv=v3 live, agent clicks cards but ALWAYS the leftmost regardless of the
  table, and the operator has no panel showing the perceived hand/top card. Two symptoms, same root:
  perception detects cards but that state never reaches (a) the decision or (b) the UI.
- **Diagnosed (code):**
  1. `flow_controller._get_game_snapshot()` hardcodes `return None` ("will be wired properly") → legal
     actions come from the SIMULATED engine (`clients.legal_actions(game_id)`), blind to the screen.
  2. `_find_card_center()` (`adapter_registry.py:528`) falls to branch 3 "first card with a center" =
     leftmost, because heuristic CV gives colour+coord but rarely `value` → no color+value match.
  3. UI: `OrchestratorStatus` carries only `strategy_snapshot` (text). `extractGameState()`
     (`useOperatorPolling.ts`) HARDCODED `topCard/handCards/handCount = null`. The `GameStateCard`
     panel EXISTS but was never fed → always empty.
- **Plan A (this session — UI visibility + state plumbing, no Windows host needed to verify logic):**
  - Schema: added `DetectedCard` + `screen_type/whose_turn/top_card/hand_cards/hand_count` to
    `StrategySnapshot` (`packages/schemas/.../orchestrator.py`).
  - Orchestrator: `_build_strategy_snapshot` now maps `observation.game_state` → those fields via a new
    pure helper `_to_detected_card` (accepts the `recognition_to_dict` shape; None-safe).
  - UI: `unoApiClient.ts` typed the new snapshot fields (+`DetectedCard`); `useOperatorPolling.ts`
    `extractGameState` now reads real `top_card/hand_cards/hand_count/screen_type/whose_turn` instead of
    nulls. `GameStateCard`/`HandCards`/`TopCard` already render them (colour-only cards show blank value).
- **Files:** `packages/schemas/src/uno_schemas/orchestrator.py`,
  `services/session-orchestrator/src/uno_orchestrator/orchestrator.py`,
  `apps/control-center/src/unoApiClient.ts`,
  `apps/control-center/src/operator/hooks/useOperatorPolling.ts`,
  `tests/unit/test_strategy_classifier.py` (+3 `_to_detected_card` tests).
- **Verified:** ruff clean; `pytest tests/unit` 313 passed / 7 skipped (+3 new); snapshot serializes
  end-to-end with real perception card shape (centers preserved, colour-only ok); tsc shows only the 5
  PRE-EXISTING errors (confirmed by stashing my 2 UI files — count unchanged). No new type errors.
- **Effect:** the operator will now SEE the detected hand + top card — which is also the best live
  diagnostic for symptom #1 (is it detecting cards at all, and with what values?).
- **Next:** Plan B = [#10] VLM perception producer (values, not just colour) → then [9d] wire
  `_get_game_snapshot` to the detected state so legal actions + `_find_card_center` match the RIGHT card.

---

### 2026-07-12 (d) — Plan B: VLM perception (#10) + perceived legal actions (9d)
- **Context:** After A, symptom #1 ("always plays leftmost card") root-caused to two decoupled gaps:
  legal actions came from the SIMULATED engine (blind to the screen), and colour-only heuristic CV gave
  no value → `_find_card_center` fell to "first card" = leftmost. User chose a **local VLM** for #10 and
  "verify on my Windows run" for validation.
- **#10 — VLM perception (env-gated, D6). Found the scaffold already existed but unwired with 3 holes;
  finished + connected it rather than building fresh:**
  1. Image never sent: `ModelInvocationRequest` had no image field, and the old `vlm_provider` passed a
     PLACEHOLDER string. Added `image_base64` to the request; `OpenAICompatibleProvider` now attaches
     OpenAI vision content-parts (text + `image_url` data URI) — vLLM/llama.cpp with a VL model accept
     this. Text-only requests unchanged.
  2. Wrong shape: rewrote `vlm_provider.infer_vision()` to read the real screenshot bytes → base64, call
     model-runtime `use_case=perception_board`, and NORMALIZE to the canonical
     `{screen_type, whose_turn, top_card, hand_cards, hand_count}` the UNO adapter's `parse_vlm` + the
     operator panel already consume. Returns a `VisionInference` (or None → clean fallback).
  3. Nobody produced it: `api.perceive` (async) now calls `infer_vision` when `VLM_PERCEPTION=1` and a
     screenshot is present, feeding the existing `vlm` slot. **Off by default** → zero regression.
  - Merger: a VLM board (`source=="vlm"`) is now PRIMARY — its cards fold into `game_state` and the
     per-game heuristic is SKIPPED so it can't overwrite them (sets `cv_build=v3`,
     `recognition_method=vlm`, non-zero game_state confidence so flow won't re-classify not_in_game).
  - `MockProvider` gained a `perception_board` branch returning a canned board → the whole path is
     testable with no real model/GPU. A local Qwen2-VL (vLLM) drops in via `VLM_PROFILE_ID` + a vision
     profile, no code change.
- **9d — legal actions from the PERCEIVED board (the direct "leftmost card" fix):**
  - New pure module `perceived_actions.legal_actions_from_perception(hand, top)` — maps detected cards
    to UNO legal moves via the schema's `Card.matches` (colour/value/wild). A chosen action now carries
    the detected card's colour+value → `_find_card_center` grounds to the RIGHT card. Returns None when
    the board isn't readable (no top card / colour-only hand) → falls back to the engine (unchanged).
  - `flow_controller._legal_actions` now takes `observation` and PREFERS perceived actions; simulated
    engine stays as fallback. `_get_game_snapshot` hardcoded-None is now bypassed on the happy path.
- **Files:** `packages/schemas/src/uno_schemas/model.py` (image_base64, PERCEPTION_BOARD use case),
  `services/model-runtime-service/src/uno_model_runtime/providers.py` (vision content + mock board),
  `services/perception-service/src/uno_perception/vlm_provider.py` (rewritten),
  `services/perception-service/src/uno_perception/api.py` (VLM producer wire),
  `services/perception-service/src/uno_perception/merger.py` (VLM primary, heuristic gated),
  `services/session-orchestrator/src/uno_orchestrator/perceived_actions.py` (NEW),
  `services/session-orchestrator/src/uno_orchestrator/flow_controller.py` (`_legal_actions` prefers CV),
  `tests/unit/test_vlm_perception.py` (NEW, 5), `tests/unit/test_perceived_actions.py` (NEW, 6),
  fixture `tests/fixtures/uno_desktop/ubisoft_hand3.jpeg` (user's real frame).
- **Verified (macOS, no host needed):** ruff clean; `pytest tests/unit` 324 passed / 7 skipped (+11);
  VLM off by default (heuristic path & its 27 tests unchanged); merger keeps VLM's 3 cards even with a
  screenshot attached; 9d matches the user's real board (top yellow-reverse → plays green+yellow
  reverse, NOT red 6, NOT leftmost).
- **Next for user (Windows):** to try the VLM path, register a vision profile and set `VLM_PERCEPTION=1`
  + `VLM_PROFILE_ID` before `dev-backend.ps1`. Even WITHOUT VLM, 9d + Plan A already improve real play:
  once perception returns a readable hand+top (colour+value), the agent plays the matching card and the
  operator panel shows the detected hand. Send the next `[CVv3]` line + a panel screenshot.
- **Still open:** value recognition quality depends on the recognizer — heuristic gives colour-only (9d
  then defers to the engine), so the leftmost-card fix fully lands only once VLM (or a value-capable CV)
  is on. Real-hardware tuning of coordinate transform stays #B1.

---

### 2026-07-12 (e) — Draw stall fixed + Ollama VLM runbook; opponent-aware strategy scoped
- **Trigger:** Real run — play improved (agent plays matching cards) but STALLS when it must draw
  (no matching card): panel shows `NEXT ACTION draw_card`, `Outcome Unknown`, `coarse state unchanged`.
  User also asked (a) whether strategy accounts for opponents' hand counts / discards, and (b) for an
  Ollama VLM enablement guide saved to docs.
- **Draw stall — root cause (code):** `_map_action_windows` grounded ONLY `play_card` to a CV
  coordinate; `draw_card` shipped just `selector_key="draw"`. On canvas/Electron UIA is empty → "draw"
  resolves to nothing → the grounded-click path (executor needs target_x/y) never fires → stall. The
  deck IS on screen and perception already emits a `draw_pile` region with coords — it just wasn't
  threaded to the action.
- **Fix:** new pure `find_draw_target(game_state)` (deck center from `regions`/`actionable_targets`);
  `flow_controller._execute` threads it via `payload["draw_target"]` for draw actions;
  `_map_action_windows` now grounds `draw_card` to that coordinate (same mechanism as card clicks).
  No perceived deck → no coordinate → unchanged selector fallback (safe).
- **Files:** `packages/shared-utils/src/uno_shared/adapter_registry.py` (`find_draw_target` +
  draw grounding), `services/session-orchestrator/src/uno_orchestrator/flow_controller.py`,
  `tests/unit/test_draw_grounding.py` (NEW, 5).
- **Strategy / opponents (answer + scope, NO code yet):** `decision-service` IS its own microservice
  (structure is fine), but `_score_action` (`policy.py`) scores ONLY the agent's own card — it never
  sees opponents' hand counts or discards because **perception doesn't extract opponent state at all**
  (neither heuristic nor VLM emit it). So there is no winning strategy today, by data-gap not by
  architecture. Logged as new tasks #11 (perceive opponents: per-seat hand_count + last discard) and
  #12 (opponent-aware scoring: target the low-card player, hoard wilds, colour management). Deferred to
  a focused follow-up — not blind-added mid-session.
- **Ollama VLM enablement:** added `ModelProviderType.OLLAMA_OPENAI` (routes through the existing
  `OpenAICompatibleProvider` — Ollama is OpenAI-compatible, vision via image_url works with no code
  change), a ready profile `models/profiles/local__ollama-vlm.json` (disabled by default), the runbook
  `docs/runbooks/vlm-ollama-setup.md`, and a README index entry.
- **Verified:** ruff clean; all 4 model profiles validate; `pytest tests/unit` 329 passed / 7 skipped
  (+5); provider routes to OpenAI-compatible; VLM still off by default. Draw grounding + Ollama path
  need the Windows host + a running Ollama for live confirmation.
- **Next:** user enables Ollama per runbook and reruns; then #11/#12 for real strategy. Draw stall
  should be gone once perception emits a draw_pile region (heuristic already does; VLM board does not
  yet emit deck coords — see #11).

---

### 2026-07-12 (f) — Ollama not called (profile disabled) + recognition diagnostics
- **Trigger:** User installed Ollama + llama3.2-vision, set env, but saw NO calls to the model; cards
  still misrecognized (agent DRAWS when a playable card is in hand; top card value wrong). Screenshot
  confirms colour-ish guesses, no values → the heuristic ran, not the VLM.
- **Root cause of "Ollama never called":** the shipped profile `local__ollama-vlm.json` had
  `"enabled": false` (runbook said to flip it; step was missed). model-runtime `/invoke` returns **503**
  for a disabled profile → `infer_vision` swallowed it and fell back to heuristic **silently**. Same
  class of bug as the pcv saga: a real failure with no visibility.
- **Fixes (visibility-first, like the pcv marker):**
  1. Enabled the profile by default (`"enabled": true`).
  2. `infer_vision` now returns `(VisionInference|None, status)`; `api.perceive` stamps `vlm_status`
     onto game_state; the operator `[CVv3]` line now shows `rec=<vlm|heuristic|none>` and, on fallback,
     `vlm=<reason>` — `disabled` / `http_503` (profile off) / `http_404` (bad id) / `error` /
     `mock_fallback`. No more guessing whether Ollama is being hit.
  3. **mock_fallback trap surfaced:** model-runtime silently falls back to a MOCK provider (canned
     board: red6/green-reverse/yellow-reverse) on any real-provider error, returning 200. Now flagged
     as `vlm=mock_fallback` so fabricated cards aren't mistaken for a real read.
  4. Provider now sniffs image MIME (PNG vs JPEG) from magic bytes instead of hardcoding png — a strict
     vision server would reject a mislabeled JPEG and silently break vision.
- **Recognition quality (#2) — diagnosis, not a heuristic tune:** `card_recognition._detect_card_number`
  is vertical-brightness-profile matching vs reference digit shapes — it CANNOT read stylized 3D glossy
  Ubisoft glyphs. This is exactly D6's premise; tuning it is per-render calibration (anti-goal). The fix
  IS getting the VLM to actually run. So #1 and #2 are the same root: VLM wasn't executing. Wrong values
  also explain the draw: 9d needs values → none → falls back to the simulated engine → plays/draws wrong.
- **Files:** `models/profiles/local__ollama-vlm.json` (enabled),
  `services/perception-service/src/uno_perception/vlm_provider.py` (status returns),
  `services/perception-service/src/uno_perception/api.py` (stamp vlm_status),
  `services/session-orchestrator/src/uno_orchestrator/flow_controller.py` ([CVv3] rec=/vlm=),
  `services/model-runtime-service/src/uno_model_runtime/providers.py` (MIME sniff),
  `docs/runbooks/vlm-ollama-setup.md` (diagnostic table + enabled profile).
- **Verified:** ruff clean; `pytest tests/unit` 329 passed / 7 skipped; vlm_status stamping confirmed
  (`disabled` when off); MIME sniff PNG/JPEG. Live Ollama call needs the user's host.
- **Next for user:** re-pull, ensure Ollama running (`ollama serve`, `ollama list` shows the model),
  set `VLM_PERCEPTION=1` + `VLM_PROFILE_ID=local/ollama-vlm`, restart backend, rerun. Read the `[CVv3]`
  line: want `rec=vlm`. If `rec=heuristic vlm=<reason>`, the reason is the exact fix (runbook §4).

---

### 2026-07-12 (g) — Session-crash 400 fixed + on-screen prompts (Play/Keep/colour) + panel
- **Trigger:** Two real frames + a crash. (1) Agent draws when a playable card (matching colour) IS in
  hand; hand mis-shown in panel. (2) On-screen modal buttons (Play/Keep after drawing, colour picker,
  Continue) — agent doesn't see them and stalls; user explicitly wants the AI to READ and CLICK them.
  (3) On game-over → next game: `Client error '400 Bad Request' … /games/<id>/actions … Failed at: execute`.
- **Crash (400) — root cause + fix:** `_execute` applies every action to the SIMULATED uno-core game
  (`apply_action`, `raise_for_status()`). On a real screen the simulator runs a parallel, desynced model;
  a perceived move it considers illegal → 400 → the whole execute step crashes the session. Fixed:
  simulator apply is now **advisory for real adapters** (windows/web) — log + continue on rejection;
  still fatal for `mock` (where the simulator IS the game). The real click is the ground truth.
- **On-screen prompts (new capability, D6-aligned):** VLM board prompt now also returns `prompts`
  (buttons the player must click, with coords). `_normalize_board` carries them; merger folds them into
  game_state; a new pure `choose_prompt()` picks which button (prefer Play/Continue/… over Keep; colour
  picker matches the wanted colour); `flow_controller.run_cycle` handles a prompt FIRST — clicks it via
  `_click_prompt` (grounded to the button coordinate) and ends the cycle. This gets the agent past the
  "draw → Play/Keep → stuck" dead-end. Needs the VLM (Ollama) on to emit prompts.
- **Panel:** hand now shows up to 20 cards (was 7 + "+N") so a big hand is readable.
- **Why draw-instead-of-play persists (answer):** it's the SAME root as before — heuristic can't read
  card VALUES, so `legal_actions_from_perception` gets colour-only → returns None → falls back to the
  simulated engine, which plays/draws wrong. This only truly resolves once `rec=vlm` (Ollama) is live.
  The green-+2-on-blue-+2 case needs value reading; the `+2`/`draw_two` aliases are already in 9d.
- **Files:** `services/session-orchestrator/src/uno_orchestrator/flow_controller.py` (advisory sim apply,
  prompt handling, `_click_prompt`), `services/session-orchestrator/src/uno_orchestrator/perceived_actions.py`
  (`choose_prompt`), `services/perception-service/src/uno_perception/vlm_provider.py` (prompts in board),
  `services/perception-service/src/uno_perception/merger.py` (carry prompts),
  `apps/control-center/src/operator/left/HandCards.tsx` (maxVisible 20),
  `tests/unit/test_perceived_actions.py` (+3 choose_prompt tests).
- **Verified:** ruff clean; `pytest tests/unit` 334 passed / 7 skipped (+3); tsc = 5 pre-existing errors
  only (no new). Crash path + prompt clicks need the Windows host + Ollama for live confirmation.
- **Still gated on Ollama:** value recognition + prompt detection both come from the VLM. Until
  `rec=vlm`, the agent runs on colour-only heuristic and will still misplay. The 400 crash fix, however,
  helps regardless (sessions survive game-over transitions).

---

### 2026-08-03 — ROOT CAUSE of "Ollama never on": .env was never loaded by anything
- **Trigger:** User: "launches the game but can't play", and `.env` already contained `VLM_PERCEPTION=1`.
  Entries (f)/(g) both end with "user must set `VLM_PERCEPTION=1` + restart" — the user DID, and it still
  ran on the heuristic.
- **Root cause:** **nothing in the repo reads `.env`.** No `load_dotenv()` call exists in any Python
  source (`python-dotenv` is in `uv.lock` but unused), and `dev-backend.ps1` set only
  `AGENT_SCREENSHOT_TRACE*`. `Start-Process` inherits only the launching process's env, so every
  `VLM_*` value in `.env` was silently discarded → `VLM_ENABLED=False` → heuristic → colour-only →
  `legal_actions_from_perception` → None → desynced simulator → misplays. Exactly the failure chain
  described in (f)/(g), with a cause one layer below where we were looking.
  Aggravated by `.env` using `KEY = "value"` (spaces + quotes), which a naive parser mangles, and by
  `vlm_provider.py` reading env at **module import** time (so it must be set before the process starts).
- **Fix:** `dev-backend.ps1` now parses `.env` before starting services — splits on the first `=`, trims
  around it, strips one layer of matching quotes, skips blanks/`#`. **Shell env wins over `.env`** so
  ad-hoc `$env:VLM_PERCEPTION="0"` still overrides. It then echoes
  `VLM_PERCEPTION=… VLM_PROFILE_ID=…` and warns loudly when VLM is off.
- **Why `[CVv3]` was invisible (two independent causes, both fixed):** (1) `perception_note` was written
  only into `detail.error` on the failure branch, and the `logger.info("perception_diag")` call omitted
  the note entirely — on a healthy session the line existed nowhere. (2) The `min_confidence` gate raised
  `LowConfidenceError` **above** the diagnostic, so low-confidence runs (the ones you most need to debug)
  never produced it either. Gate moved below the diagnostic; the note is now attached to the error text.
- **Bare `ReadTimeout` made diagnosable:** httpx transport errors have an **empty** `str()`, so
  `format_exception_message` fell back to a bare class name — `perceive`, `capture_evidence` and
  `execute_action` all surfaced identically. Now falls back to `"<Type> on <METHOD> <URL>"` (only when
  `str(exc)` is empty, so `HTTPStatusError`'s status code survives), and `_handle_failure` prefixes the
  step: `execute: ReadTimeout on POST http://127.0.0.1:8105/…`.
- **`Action delivery failed` / 15s timeout:** adapter HTTP budget was hardcoded 15s while the adapter's
  own execute deadline is 12s and **evidence capture has no adapter-side deadline at all**. Screenshot +
  UIA walk gets much slower once a local vision model saturates the machine — which is why 15s only
  started blowing after VLM was switched on. Now `ADAPTER_HTTP_TIMEOUT_SEC` (default 45s, env-tunable).
- **Logs:** each service now writes `logs/<name>.log` (stdout, where structlog prints) and
  `logs/<name>.err.log` (uvicorn). `python -u` added — without it stdout block-buffers when redirected
  and `Get-Content -Wait` shows nothing. Watch with
  `Get-Content logs\session-orchestrator.log -Wait | Select-String CVv3`.
- **Regression check on newly-live `.env` vars:** `UNO_CONFIG_PATH`, `UNO_MODEL_REGISTRY_PATH`,
  `UNO_REPLAY_STORAGE_PATH` equal the code defaults; `UNO_POSTGRES_DSN`, `UNO_REDIS_URL`,
  `UNO_EVENT_BUS_BACKEND`, `UNO_LOG_LEVEL` are read nowhere. Only `UNO_PLAYWRIGHT_CHANNEL=chrome` newly
  takes effect, and only for the web adapter. All `GenericAdapterClient(` call sites pass args
  positionally; no test asserts `timeout == 15`.
- **Files:** `.env`, `scripts/dev-backend.ps1`,
  `services/session-orchestrator/src/uno_orchestrator/flow_controller.py`,
  `services/session-orchestrator/src/uno_orchestrator/recovery.py`,
  `packages/shared-utils/src/uno_shared/adapter_registry.py`,
  `services/adapter-windows/src/uno_adapter_windows/api.py` (stale comment).
- **NOT VERIFIED:** ruff and `pytest tests/unit` (baseline 334/7) were **not run** this session — the
  sandbox shell never started. Run both before trusting these edits.
- **Confirmed non-issue:** user's Ollama model `aeline/opan` exactly matches
  `models/profiles/local__ollama-vlm.json` (`enabled: true`).
- **Deferred (user's call):** in-app Ollama model picker. Needs Ollama `GET /api/tags` (nothing queries
  it), persisted registry-profile edits (mutations are in-memory only), and a runtime-readable
  `VLM_PROFILE_ID` (currently module-import) so a UI change doesn't require a backend restart.
  Gated on "first confirm the agent actually plays".

### 2026-08-04 — The agent was playing a FABRICATED hand; plus stale editable installs, plus mllama
- **Trigger:** with `.env` finally live, the operator showed a confident board — red 6 on the pile, three
  cards in hand — while the real screen had seven. "Агент даже не пытается играть… неверно распознаёт."
- **Root cause #1 — the mock board reached perception.** `invoke_with_fallback` silently substitutes
  `MockProvider` on *any* real-provider error and still returns **200 OK**. `MockProvider._mock_output`
  for `perception_board` emits a deterministic `top_card {red,6}` + hand `[red 6, green reverse,
  yellow reverse]` — byte-for-byte what the operator displayed. `infer_vision` noticed `fallback_used`,
  labelled the status `mock_fallback`, and **returned the board anyway** at confidence 0.8, which
  outranks the heuristic. The agent then reasoned about cards that do not exist on screen.
  **Fix:** `vlm_provider.infer_vision` now returns `None, "mock_fallback"`, so the caller falls back to
  the heuristic — which is what its docstring always claimed happened for a non-`ok` status.
  *Expect lower confidence and fewer cards in the panel until the VLM answers `ok`. That is not a
  regression; it is the fabrication no longer being displayed as truth.*
- **Root cause #2 — services ran half of another project's code.** `/health` came back with an empty
  `details` even after `set_health_detail` was added. `uno-core`, `uno-schemas` and `uno-shared-utils`
  were **editable-installed from `E:\dev\AI-games`** into the *global* interpreter, and a modern pip
  editable install registers a `sys.meta_path` finder that is consulted **before** `sys.path` /
  `PYTHONPATH` — so no amount of PYTHONPATH fixing dislodged them. `uno_perception` resolved to this
  repo while `uno_schemas`/`uno_shared` resolved to the other one.
  **Fix:** `dev-backend.ps1` now launches `.venv\Scripts\python.exe` explicitly and warns if it is
  missing. Confirmed by `perception: vlm_enabled=True profile=local/ollama-vlm timeout=180.0s`.
- **Root cause #3 — Ollama 0.32.5 cannot load `mllama`.** `llama3.2-vision` 500s on a **plain text**
  request: `error loading model: unknown model architecture: 'mllama'`. I recommended that model from the
  profile metadata and the fact it was already pulled, without checking architecture support against this
  Ollama build — my error, and two intermediate hypotheses (JSON mode, VRAM) were wrong too. `qwen3vl`
  demonstrably loads on this build, so the profile now points at
  `bahtiyorovnozim/qwen3-vl-5-4b:latest`. `aeline/opan` is also qwen3vl but is 2.1B **with thinking** —
  too small to read fanned, rotated, glossy glyphs, and its reasoning tokens compete with the JSON for
  the token budget.
- **Diagnostics that made all of this findable:**
  - `invoker._describe()` — same empty-`str(exc)` trap as `recovery.py`. `model_invoke_failed error=`
    was literally blank while the mock quietly took over. Now always logs type + `METHOD URL`, plus
    `has_image` and `timeout_seconds`.
  - `providers.OpenAICompatibleProvider` no longer calls `raise_for_status()`; it raises with the
    **response body** (first 500 chars) plus `model=`, `image=`, `json_mode=`. For a local runtime the
    body is the only place the real reason appears. This is what surfaced the `mllama` message.
  - `dev-backend.ps1` polls every service's `/health` for up to 60s and prints `ready:` / `NOT READY:`,
    then echoes the perception VLM gate. Removes the "Невозможно соединиться" race right after start.
- **Profile tuning (`models/profiles/local__ollama-vlm.json`):** `max_tokens` 512 → **1024** (a reasoning
  preamble can consume a 512 budget and leave truncated JSON → `parse_failed`); `timeout_seconds` 60 →
  **150**, kept *below* `VLM_TIMEOUT_S`(180) < `VLM_HTTP_TIMEOUT_SEC`(280) so the innermost budget fails
  first and the error names the real cause; `supports_json_mode` → **false** (it makes providers.py send
  `response_format`, which Ollama maps to `format=json` — an extra failure surface we don't need, since
  `_parse_structured()` already extracts the JSON substring). Rationale is recorded in the profile's own
  `metadata` so the next session doesn't re-derive it.
- **Files:** `scripts/dev-backend.ps1`, `services/perception-service/src/uno_perception/api.py`,
  `services/perception-service/src/uno_perception/vlm_provider.py`,
  `services/model-runtime-service/src/uno_model_runtime/invoker.py`,
  `services/model-runtime-service/src/uno_model_runtime/providers.py`,
  `models/profiles/local__ollama-vlm.json`.
- **NOT VERIFIED:** ruff and `pytest tests/unit` (baseline 334/7) again **not run** — the sandbox shell
  was unavailable for the whole session. Run `.\.venv\Scripts\python.exe -m pytest tests/unit` before
  trusting these edits. No live session has exercised the qwen3-vl profile yet either: the checkpoint is
  a `[CVv3]` line reading `vlm=ok` (not `mock_fallback`) with `hand_cards` matching the real screen.
- **Environment hygiene (will defeat a correct VLM):** only one UNO window should be open, and nothing
  (Task Manager, the operator) should overlap the game area — the capture was 1296×759 of an occluded
  window.

### 2026-08-04 (later) — Why the model "returned nothing": it was thinking, and the log was lying

Follow-up to the entry above, chasing `vlm=empty_board` to ground.

- **The log was silent because the logger was wrong, not because nothing happened.**
  `vlm_provider.py` used `logging.getLogger()`. The project never configures the stdlib root logger
  (`uno_shared.logging` wires **structlog** to STDOUT), so those records fell through to Python's
  `lastResort` handler: WARNING+ only, unformatted, on **STDERR** → `logs/<svc>.err.log`, and INFO
  dropped entirely. Every VLM diagnostic ever added to that module had been invisible. Switching to
  `uno_shared.logging.get_logger` made the payload appear on the first run.
  **Rule: in this repo a bare `logging.getLogger()` is a silent logger.** `services/` still had ~18 such
  modules; `decision-service/policy.py` is now converted too (it sits on the critical path and its
  fallbacks were equally invisible). Note structlog's `warning()` takes **kwargs, not `%s`** — every
  converted call site must be rewritten, or the format string prints literally.
- **`empty_board` meant `message.content == ""`.** With logging fixed: `keys=[] raw= structured={}`.
  Not malformed JSON — nothing at all, after 11 s of work.
- **Root cause: qwen3-vl is a THINKING model and the reasoning is billed against `max_tokens`.**
  The new `provider_empty_content` warning in `providers.py` (reads `finish_reason`, falls back to
  `reasoning_content` / `reasoning`) proved it: `finish_reason=length`, `reasoning_chars=10275`,
  content empty. **Crucially the reasoning showed the model READS THE BOARD CORRECTLY** — it named the
  bottom player ("Goldberg"), the top card, the hand. Perception was never a vision problem; it was an
  output-budget problem.
- **What did NOT work:** raising `max_tokens` 1024 → 3072 (still `length`), and a `/no_think` +
  "JSON only, do not reason" prompt prefix (ignored). Do not spend another cycle on prompt wording.
- **The fix being tested: turn thinking off server-side.** `providers.py` now merges an optional
  `metadata.extra_body` JSON blob into the request body, and `local__ollama-vlm.json` sets
  `{"think": false, "chat_template_kwargs": {"enable_thinking": false}}` — both spellings, because the
  flag name differs per runtime and these servers drop unknown JSON fields silently. Keeping it in
  profile metadata (not code) means the next runtime swap is a JSON edit, not a patch.
- **If `reasoning_chars` is still large after this**, the build honours neither flag: **switch
  `model_name` to a non-thinking VLM** (qwen2.5vl, minicpm-v, llava). Do not raise the budget a third time.
- **Same bug, second call path:** `policy_advice` was invoking the same thinking model with the schema
  default `max_tokens=256` and dropping every decision to the heuristic. Now sends 768 explicitly.
- **Files:** `services/model-runtime-service/src/uno_model_runtime/providers.py`,
  `services/perception-service/src/uno_perception/vlm_provider.py`,
  `services/decision-service/src/uno_decision/policy.py`, `models/profiles/local__ollama-vlm.json`.
- **NOT VERIFIED:** ruff / `pytest tests/unit` still unrun (no shell). Checkpoint remains a live
  `[CVv3] ... rec=vlm vlm=ok` with a real hand count.

### 2026-08-04 (later still) — Cycle traces + an offline perception stand

Motivation is the multi-game goal (UNO now, Svintus next). Perception is the component that fails
*silently* — it does not raise, it returns a plausible board that is wrong — and the only way to know
whether a change made it better or worse is to re-run it over real frames with a human-verified answer.
Debugging it live cost ~30 min per hypothesis (restart 14 services, launch a game, grep four logs) and
every run was irreproducible because the board differed.

- **Audited the existing trace first and rejected it.** `adapter-web/agent_trace.py` cannot serve as a
  corpus: (1) it is Playwright-specific — it needs a `page`, so it never fires for the Windows adapter,
  which is the one that actually plays Ubisoft UNO; (2) it records **counts, not content**
  (`"hand_cards": len(grounding.hand)`, `"top_card": ... is not None`). You can see that nine cards were
  found, never *which* nine. A corpus of booleans cannot detect a board that is the right size and the
  wrong content — which is exactly how the agent played a blue card onto a red one.
- **New: `packages/shared-utils/src/uno_shared/cycle_trace.py`.** One directory per cycle containing the
  exact frame plus `cycle.json` with the **full** perceived board verbatim, provenance
  (`recognition_method` / `vlm_status` / `cv_build` / `source`), confidence, legal actions, decision,
  guard verdict, outcome and timings. Deliberately **game-agnostic** — nothing in it knows what a card
  is, so adding Svintus must not require touching it. The frame is **copied**, not referenced: the
  adapter recycles its screenshot directory, so a recorded path points at a different frame tomorrow.
  Best-effort throughout — every public function swallows its own exceptions, because tracing must never
  break a cycle. Bounded on disk (frames are 1–3 MB): oldest cycle dirs pruned past
  `AGENT_CYCLE_TRACE_KEEP`. Env: `AGENT_CYCLE_TRACE` (default **on** — the data must exist before you
  know you need it), `AGENT_CYCLE_TRACE_DIR` (default `artifacts/cycle_trace`), `..._KEEP` (200).
  Flags are read **per call, not at import** — `vlm_provider` already made the import-time-caching
  mistake, where "set the var and reload" silently does nothing.
- **Hooked into `flow_controller.run_cycle` from a `finally`, on purpose.** A cycle that died in
  `perceive` still has a frame, and those are the frames worth keeping — the previous trace only ever
  fired on the happy path. The locals are pre-bound before the `try` so the `finally` cannot raise
  `NameError` and swallow the real exception. The cycle number is a new `RuntimeSession.cycle_counter`,
  **not** `metrics.total_steps`: the latter only increments on a *completed* cycle, so every failed cycle
  would overwrite the previous one's directory.
- **New: `scripts/replay_perception.py`.** Re-runs recognition over saved frames with no game, no
  services, no GPU. `run` scores the corpus; `promote <trace_dir>` turns a traced cycle into a fixture.
  `promote` pre-fills `expected.json` with the agent's own guess **plus a `_TODO` key**, and the corpus
  test fails if that key survives — otherwise the label would be the bug and the test would pass
  trivially forever. Hand comparison is order-insensitive but duplicate-sensitive (the hand is fanned;
  left-to-right order is not ground truth, but two red 6s is a different hand from one).
- **New tests:** `tests/unit/test_cycle_trace.py` (frame really copied, full hand preserved, failed
  cycles recorded, survives a missing file / an exploding property / a non-serializable decision /
  path traversal in the session id, pruning bounded) and `tests/unit/test_perception_corpus.py`
  (skips while the corpus is empty — note a **skip means the net does not exist yet**, not that
  perception is fine; runs only the deterministic recognizer, since calling the VLM would make the suite
  depend on a running Ollama at ~11 s/frame).
- **Next:** play one session with tracing on, `promote` a handful of cycles across screen types
  (in_game, own turn, colour picker, end-of-round), then **hand-verify every field**. Environment
  hygiene still applies — the corpus is only as good as the captures, so one UNO window and nothing
  overlapping the game area.
- **VERIFIED:** `pytest tests/unit` → **356 passed, 1 skipped** (was 334 before this work; the 4 failures
  below were found and fixed). The one skip is the perception corpus — it has no labelled cases yet, and
  a skip there means **the regression net does not exist yet**, not that perception is fine. Lint is
  still unrun: ruff is not installed in `.venv`.

#### First run of the suite: 4 failures, three of them real (one class of bug, three places)

`pytest tests/unit` → 4 failed, 352 passed. Triage, because only one was my test being wrong:

- **`getattr(obj, "attr", None)` does NOT protect against an attribute that RAISES** — the default only
  covers `AttributeError`. Three sites had it:
  - `recovery.format_exception_message` did `getattr(exc, "request", None)`, but on httpx exceptions
    `.request` is a **property that raises** `RuntimeError("The .request property has not been set.")`
    when the error was built without one. So the *error formatter* raised, inside `_handle_failure` —
    the recovery path died while reporting a `ReadTimeout` and replaced it with an unrelated
    `RuntimeError`. In live runs httpx does attach the request, so this hid in tests; but error
    formatting must never be able to raise. Now `try/except`.
  - `cycle_trace.write_cycle_trace` had the same pattern on `observation.game_state/confidence` and
    `screenshot.path/width/height`. One raising field aborted the *whole* record — losing the frame,
    which is the thing worth keeping. Added `_safe_attr` and `_dump` (a `_jsonable` that cannot fail):
    the rule is **lose a field, never the cycle**. The test now asserts the record is written, not
    merely that no exception escaped.
- **`test_model_runtime` fake response was incomplete, not the code.** `AsyncMock()` with no
  `status_code`, while the provider now checks `resp.status_code >= 400` to log the response body on
  errors. Set `fake_resp.status_code = 200`.
- **ruff is not installed in `.venv`** (`No module named ruff`), so lint is still unrun. Either add it as
  a dev dep or use `uv tool run ruff check`.
- **After the fixes: 356 passed, 1 skipped.** Net effect of the failures being real: two production
  modules got more defensive and one stale test fake got corrected.

### 2026-08-05 — "Delivered", and the mouse never moved: perception right, decision right, no coordinate

The first live run with the traces on. Operator showed a correct board (yellow 4 top, 7 real hand cards),
`play_card` chosen, guard ✓ allowed, **Delivery: Delivered** — and the mouse never moved for two minutes.
The trace answered it in one pass, which is the whole reason it exists; the previous version of this bug
cost days.

`artifacts/cycle_trace/e9f527e3.../0004/cycle.json`: `recognition_method: "vlm"`, `vlm_status: "ok"`,
confidence 0.95, correct hand, correct legal actions, decision *play red 4 onto yellow 4*, guard allowed.
And every entry of `hand_cards` had **only `color` and `value`** — no `bounds`, no `center`, no `regions`.

**Root cause, one line.** `merger.build_observation` ran the heuristic screenshot plugin under
`if screenshot and screenshot.path and not vlm_has_cards:`. The heuristic is the **only** producer of
pixel geometry (`bounds`/`center` per slot, plus `regions` and `actionable_targets`, which is what grounds
a *draw* click). So the moment the VLM started working — the thing we spent two days fixing — geometry
vanished. The two perception paths were mutually exclusive and each held exactly half of what execution
needs.

The rest of the chain, all silent: `_find_card_center` → `None` → `_map_action_windows` emits
`selector_key="play_red_five"` with no `target_x/target_y` → `visual_executor` falls back to a UIA lookup
that **cannot** succeed on a canvas game → returns `success=False, uncertain=True` → `execute_action`
returns that as an **HTTP 200 body** → and `flow_controller._execute` *discarded the return value*. Hence
"Delivered" for an action that never happened, and a `RECORD` step for a move that was never made.

Three changes:

- **New `services/perception-service/src/uno_perception/hand_fusion.py`** — `attach_hand_geometry(cards,
  slots)`. Identity from the model, geometry from pixels; the VLM's `color`/`value` are never touched
  (the heuristic cannot read a value at all, so letting it near them would be a downgrade).
  The governing rule is **never guess an alignment**: a card with no coordinate makes the agent *stall*,
  which is visible and fixable; a card with the *wrong* coordinate makes it play a card it never decided
  to play, silently — and confidently-wrong perception is what keeps biting this project. Two paths:
  counts match *and* slot colours corroborate the order → align by index (the only path that can ground a
  **wild**, whose colour the heuristic classifier cannot read); otherwise each card takes the leftmost
  unused slot of its own colour, and anything unmatched comes back **bare**. The colour vote is loose on
  purpose (≥0.6 agreement, low-confidence slots abstain): it exists to catch a hand shifted by one, not
  to second-guess the model card by card. `segment_hand_cards` guesses the card count from strip width
  (`round(width / _TYPICAL_CARD_STEP)`), so off-by-one is routine, not exceptional.
- **`merger.py`** now runs the heuristic **for its geometry only** on VLM cycles too, and records a
  `hand_geometry` diagnostic (`{cards, slots, grounded, method, reason}`) on the observation. That
  diagnostic is the point: *"the agent did not click"* and *"the agent had no coordinate to click"* are
  different bugs and were previously indistinguishable after the fact. Wrapped in try/except — geometry
  is an enhancement, never fatal. **Cost:** the heuristic now runs every cycle; cycle 4 already took
  76.9 s, so this needs watching.
- **`flow_controller._execute`** raises on a refused action (`execute_refused_by_adapter`, logging
  `selector_key`, `grounded_by`, `target_x`). Everything downstream — verification, retry, the belief
  that the board changed — is built on "delivered means clicked", so a refusal must be loud.

Also fixed while in there: the trace was labelling **every successful cycle** `failed_at=record, ok=false`.
`failed_at` in `run_cycle` is a **progress** marker, not a failure marker — on success it keeps the name
of the last step and `detail.error` is reset to `None`. A corpus that lies about which cycles worked is
worse than no corpus. The `finally` now records the **exception**; a cycle that returns without raising is
by definition not a failure. And the message is `f"{type(exc).__name__}: {exc}"`, because httpx transport
errors have an **empty `str()`** — which is how cycle 5 came out as "failed at observe" with no reason at
all.

- **New `tests/unit/test_hand_fusion.py`** — 9 cases, weighted toward the *refusals*: contradicting colour
  order must degrade to colour matching instead of pairing index to index; an ambiguous card must come
  back with no geometry; a low-confidence slot colour must not veto alignment; input must not be mutated;
  empty inputs must say *which half* was missing.
- **`_find_card_center` (adapter_registry) lost two fallbacks.** Found by re-reading the executor to
  confirm the fused shape matches what it looks for (it does — `center: {x,y}` / `bounds: {x,y,w,h}`).
  It fell back to "first colour match", then to **"the first card with any resolvable centre at all"**,
  ignoring the requested colour entirely — so a decision of *red 4* with no grounded red card clicked a
  green one and reported success. Those fallbacks made sense when the heuristic was the only source and
  every value was literally `"unknown"`; with real VLM values they *are* the mis-click. Now: exact
  colour+value, else a colour match only for a candidate whose value is unreadable anyway (keeps the
  heuristic-only path working), else **None** — which is a stall, and stalls are visible.
  `test_find_card_center_falls_back_to_first_card` pinned the old behaviour and was rewritten rather than
  deleted: the valueless-heuristic case it protected is still real.
- **NOT VERIFIED:** none of this has been executed — no shell in that session. `pytest tests/unit`,
  ruff (still not installed) and a live run all pending.

#### Live run after the fix: the mouse moves, and two NEW failures separate cleanly

Both confirmed by the operator, and they are different bugs — worth not conflating:

- **The grounding works.** `Delivery: Delivered`, cursor visibly inside the game area, hand read correctly
  (red 1/4/9/skip + green 0/4/8, top card yellow 4). So identity+geometry now reach the adapter.
- **But the click does not play the card** — board unchanged, `Outcome: Unknown` ("coarse state unchanged,
  outcome not confirmable"). The cursor ends up in the empty table area, well above the hand.
- **A second cycle failed loudly with `adapter did not perform play_card: execution exceeded 12s deadline`**
  — which is the new refusal check doing its job; before, this was a silent "Delivered". On that cycle the
  VLM had degraded (operator showed 9 cards, all values `un`, top card misread as yellow 0), so there was
  no grounded coordinate and execution fell into `_execute_visual` → `extract_ui_tree` (the UIA walk) →
  past `_EXECUTE_DEADLINE_S = 12.0`. Note this path can only ever fail on a canvas game, so it is 12 s
  spent to reach a guaranteed failure — a chunk of the 76.9 s cycle (see #17).

**Prime suspect for the wrong click position: the coordinate transform, not the coordinate.**
`_execute_grounded_click` derives its scale from `before_path` — a frame captured *at click time* — while
`target_x/target_y` were measured on the frame *perception* saw. Two different captures. Equal sizes ⇒
correct; any difference (window moved/resized, DPI change between the two) ⇒ every click silently shifts.
The transform is otherwise sound in principle: `_capture_via_printwindow` uses `GetWindowRect`, so frames
really are window-relative and offsetting by the window origin is right.

**Why this was undiagnosable:** the one line that logs it —
`grounded_click ... screenshot=(x,y) screen=(x,y)` — used `logging.getLogger("adapter-windows.audit").info`,
and **no handler for that logger is configured anywhere in the repo**. Silent stdlib logger, INFO dropped:
the same trap that hid every VLM diagnostic for days. Converted to structlog and extended with the entire
transform (`frame_w/h`, `win_w/h`, `origin_x/y`, `scale_x/y`) so one run settles it instead of inferring
from where the cursor landed. The `action_rejected` **warning** was left on the stdlib logger on purpose —
`test_security_hardening.TestAuditLogging` monkeypatches it by name.

---

### 2026-08-06 — Crop failures: PIL "unrecognized data stream" when heuristic runs after VLM timeout

**Trigger:** Session `cd83b7b0`, cycle 3 trace. `vlm_status: "mock_fallback"` (Ollama down). Heuristic
fallback ran and ALL THREE crops failed identically:
```
crop_failed_hand: unrecognized data stream contents when reading image file
crop_failed_play_area: …
crop_failed_draw_pile: …
```
`hand_cards: []` → no geometry → no coordinate → UIA path → RuntimeError (UIA-not-actionable on canvas).
Outcome `failed_at: "execute"`, cycle 43 s.

**Root cause (traced through the whole call stack):**

`req.screenshot.path` = `E:\…\adapter-windows\artifacts\cd83b7b0-…\evidence-1786043964349.png`.
The orchestrator builds `ScreenshotFrame` with only `path` set — `data_base64` is `None`.

The VLM provider reads the file **at request start** via `_read_image_base64(shot_path)` and sends it to
model-runtime. Model-runtime uses MockProvider (Ollama down) → returns `fallback_used=true` → `infer_vision`
returns `(None, "mock_fallback")` after up to 30 s of timeout. Only then does `build_observation` call the
heuristic, which tries `Image.open(screenshot.path)` — but the file may have been deleted, overwritten, or
locked by the adapter in the time since the VLM first read it. PIL gets non-image bytes or an empty/corrupt
file → "unrecognized data stream".

**Why VLM path never suffered it:** VLM reads the file at request start (before anything can corrupt it).
The heuristic runs 30+ s later, by which point the adapter may have cleaned up the artifact.

**Session 2747e3e7 (7 cycles) was also read:** cycles 1–5 showed `vlm_status: "ok"`, full VLM recognition,
no crop errors — because on VLM-ok cycles the heuristic runs for geometry only (line 112 in `merger.py`,
added2026-08-05), and PIL errors there are caught and buried in `hand_geometry.reason`. Crop failures
only become blockers when VLM is entirely absent and the heuristic must supply the whole board including
identity.

**`vlm_status: "mock_fallback"` is an operational issue** (Ollama not running or timed out), not a code
bug. The code path is correct (`infer_vision` already returns `None` and discards the mock board — fixed
2026-08-04). Bringing Ollama back up is the only fix.

**Fix — `services/perception-service/src/uno_perception/api.py`:**

Snapshot the screenshot file bytes into a `tempfile.mkstemp` temp file **at the top of `perceive`**,
before the VLM call. Replace `screenshot.path` with the temp path for all downstream code (VLM and
heuristic). Clean up in `try/finally`. If the snapshot read itself fails (`OSError`), the original path is
kept and downstream gets an explicit error rather than a silent one.

```python
_snap: str | None = None
screenshot = req.screenshot
if screenshot and screenshot.path:
    try:
        with open(screenshot.path, "rb") as fh:
            raw = fh.read()
        fd, _snap = tempfile.mkstemp(suffix=".png")
        os.write(fd, raw); os.close(fd)
        screenshot = screenshot.model_copy(update={"path": _snap})
    except OSError:
        pass  # keep original; downstream will report the specific error
try:
    …  # VLM + build_observation both use `screenshot` (stable path)
finally:
    if _snap:
        try: os.unlink(_snap)
        except OSError: pass
```

**New tests — `tests/unit/test_perception_snapshot.py` (4 cases):**
- `test_snapshot_survives_source_deletion` — PIL can open from snapshot after the source is deleted.
- `test_snapshot_is_independent_copy` — overwriting the source after snapshot does not affect the snapshot.
- `test_snapshot_cleanup_in_finally` — temp file is removed even when downstream raises.
- `test_snapshot_oserror_keeps_original_path` — missing source file keeps the original path, no crash.

**NOT VERIFIED:** ruff and `pytest tests/unit` unrun — shell still unavailable. Baseline was 356 passed
/ 1 skipped before this session. Expected: +4 new tests, all green; no regressions.

---

### 2026-08-07 — Transform confirmed clean; test pollution patched; parse_failed surfaced

**#18 CLOSED — coordinate transform is not the cursor-shift bug.**

Read `logs/adapter-windows.log` and found the `grounded_click` structlog entry added 2026-08-05:

```
grounded_click  frame_w=1296 frame_h=759  win_w=1296.0 win_h=759.0
                scale_x=1.0 scale_y=1.0  origin_x=86.0 origin_y=166.0
                screenshot_x=649 screenshot_y=652  screen_x=735 screen_y=818
                success=True  error=None  grounded_by=None
```

`frame_w == win_w` and `frame_h == win_h`. Scale is exactly 1:1. The arithmetic is clean: `86 + 649 = 735`,
`166 + 652 = 818`. The click for `hand_3` (blue, center 649,652) landed at screen (735,818) and
`success=True` with no error. The "cursor above cards" symptom from 2026-08-05 was almost certainly
pre-T5 behavior — before `attach_hand_geometry` was wired, the agent had no per-card coordinate and fell
through to the UIA path which clicked a different point entirely. There is **no transform mismatch to fix**.

`grounded_by=None` — the grounding provider found no named target for this `play_card`, so the adapter
used the raw card-center coordinate from perception. That is the expected path.

**Session `cd83b7b0` detailed read:**

- **Cycle 1** (82 s): `vlm_status: "parse_failed"`. VLM responded but `vlm_provider.py` could not parse
  the output as JSON (line 114-115, a known handled path). The heuristic took over; 7 cards detected
  with geometry; decision = play blue skip; `ok: true`. `parse_failed` degrades cleanly, no action needed.
  The 82 s cycle time is notable — likely a VLM timeout before the parse error was returned.

- **Cycle 2** (40 s): `vlm_status: "mock_fallback"` + crop failures (these are what #T8 fixes). Legal
  actions come from engine state (blue 3/blue skip). Decision = play blue 3. Outcome:
  `failed_at: "execute"`, `error: "adapter did not perform play_card: execution exceeded 12s deadline"`.
  This is the refusal check (#T6) firing correctly: no grounded coordinate → `_execute_visual` →
  `extract_ui_tree` UIA walk → hits `_EXECUTE_DEADLINE_S = 12.0`. Expected behavior on a canvas game
  with no geometry. Once Ollama is back (#19), crop failures disappear and cycle 2's path never runs.

**Housekeeping: `test_flow_cycle_failure.py` test pollution patched.**

`test_observe_timeout_marks_failed_step_and_keeps_active_on_retry` used `session_id="s1"` and called
`flow.run_cycle` with no `AGENT_CYCLE_TRACE_DIR` override, so pytest left a real directory at
`artifacts/cycle_trace/s1/0001/`. Added `tmp_path` + `monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", ...)`,
consistent with how `test_cycle_trace.py` already isolates traces. The `s1/` directory in the repo is
a pre-existing artifact from before the fix; it can be deleted manually.

**Still NOT VERIFIED:** `pytest tests/unit` and ruff still unrun. Expected baseline: +4 snapshot tests
from 2026-08-06 (→ 360 passed / 1 skipped), plus the `test_flow_cycle_failure` signature change above.

---

### 2026-08-07 (later) — Rescue parse_failed VLM responses: _extract_json_object

**Motivation:** session `cd83b7b0` cycle 1 showed `vlm_status: "parse_failed"`. The VLM responded
but `json.loads(raw_text)` raised `JSONDecodeError`. Two root causes are common even when the prompt
says "JSON only": (1) the model wraps its output in markdown code fences (` ```json ... ``` `), and
(2) the model ignores `/no_think` and emits a reasoning preamble before the JSON object. In both
cases, the JSON is *present* in the response — the old code just never looked for it.

**Fix — `services/perception-service/src/uno_perception/vlm_provider.py`:**

Added `_extract_json_object(text)` helper and `import re`:
- Tries a regex for markdown code fences first (` ```json...``` ` or ` ```...``` `).
- Falls back to a brace-counter scan that finds the first `{...}` block, skipping any preamble.
- Returns the raw string (not parsed) so the caller's `json.loads` decides validity.

The `infer_vision` function now calls this before logging `vlm_parse_failed` and returning
`"parse_failed"`. If `_extract_json_object` finds a candidate, it tries `json.loads` on that; only
if that also fails does it log and return `"parse_failed"`. The existing `vlm_parse_failed` log now
fires exclusively for genuinely unrecoverable responses.

**New tests — `tests/unit/test_vlm_perception.py` (+5 cases):**
- `test_extract_json_fenced_json_block` — ` ```json\n{...}\n``` ` is extracted and parsed.
- `test_extract_json_fenced_no_language_tag` — ` ```\n{...}\n``` ` without language tag works too.
- `test_extract_json_reasoning_preamble` — free-text preamble before `{...}` is skipped.
- `test_extract_json_no_json_returns_none` — empty string, no-brace text, and `None` all return `None`.
- `test_extract_json_nested_object` — brace counter handles nested objects without false-closing.

**NOT VERIFIED:** shell still unavailable. Baseline was 360 passed / 1 skipped (after 2026-08-06 and
2026-08-07 test-pollution fix). Expected: +5 new tests → 365 passed / 1 skipped. No regressions
expected (the added code path is only reached when the primary `json.loads` fails).

---

### 2026-08-07 (later still) — Sub-timing instrumentation in run_cycle

**Motivation:** #17 (76.9 s cycle) says "measure before optimizing — `timings_ms` is in every
`cycle.json`" — but the only entry in `timings_ms` is `"cycle"` (the total). Without sub-timings
you cannot distinguish "VLM took 60 s" from "policy advice took 60 s" from "execute took 60 s";
you can only see the total and guess.

**Fix — `services/session-orchestrator/src/uno_orchestrator/flow_controller.py`:**

Added four `perf_counter()` checkpoints in `run_cycle` around each major async call:
- `t_observe_ms` — time for `_observe` (screenshot capture via adapter)
- `t_perceive_ms` — time for `clients.perceive` (HTTP to perception service, includes VLM call)
- `t_decide_ms` — time for `_decide` (policy, may include a second VLM call for policy_advice)
- `t_execute_ms` — time for `_execute` (adapter click; 0 on cycles that fail before execute)

All four are pre-initialized to `0` before the `try` block (same pattern as `trace_failed_at` and
`trace_error`) so the `finally`'s `write_cycle_trace` never raises `NameError` on early failures.

The `write_cycle_trace` call now passes:
```python
timings_ms={
    "cycle": int((time.perf_counter() - started) * 1000),
    "observe": t_observe_ms,
    "perceive": t_perceive_ms,
    "decide": t_decide_ms,
    "execute": t_execute_ms,
}
```

No schema changes — `timings_ms` is `dict` already. No new tests needed (this is pure
instrumentation with no logic). The next live cycle will have full per-phase breakdowns visible
in `cycle.json`, so #17 can be diagnosed without guessing.

---

### 2026-08-07 (later still) — #11: Opponents + draw_pile in VLM perception

**Motivation:** The VLM already sees the whole table, but the board schema only asked for the current
player's hand. Opponent card counts are the most actionable game-state fact missing from the agent's
world view: knowing who is near UNO is prerequisite to defensive plays (skip, +2 when they're on one
card). The draw pile coordinate is complementary: the heuristic regions block already emits it, but
if that block fails (PIL missing, no screenshot path) the agent loses `find_draw_target` on the VLM
path — the VLM can supply it directly as a second source.

**Changes:**

- **`vlm_provider._board_prompt`** — added two fields to the JSON schema:
  - `"opponents":[{"seat":"left|right|top","hand_count":<int>}]` — each other active player with
    their position relative to the current player and their card count as the VLM reads it.
  - `"draw_pile":{"x":<center px>,"y":<center px>}` — deck coordinate; null/absent if not visible.
  - Extended the instruction text to describe both fields so the model knows what to populate.

- **`vlm_provider._normalize_board`** — added `opponent()` helper (mirrors `card()`/`prompt_btn()`):
  requires a `seat` string; `hand_count` is coerced to int (0 on parse failure). Both `opponents`
  and `draw_pile` are included in the returned dict. `draw_pile` is `None` when the raw value is
  absent or malformed. The existing usability gate (`not top and not hand and not prompts → None`)
  is unchanged — an opponents-only board with no actionable cards/prompts is not useful yet.

- **`merger.build_observation`** — added `"opponents"` to the VLM-board key copy loop. Added a
  `draw_pile` injection block: if the VLM board reports a draw_pile coordinate and no `draw`/`deck`
  target already exists in `actionable_targets`, the coordinate is injected as
  `{"id": "draw_pile", "label": "Draw Pile", "x": ..., "y": ...}` so `find_draw_target` finds it
  on the VLM path even when the heuristic geometry block is unavailable.

**New tests — `tests/unit/test_vlm_perception.py` (+5 cases):**
- `test_normalize_board_extracts_opponents` — opponent list preserved verbatim in `out["opponents"]`.
- `test_normalize_board_extracts_draw_pile` — `draw_pile` typed as int dict `{x, y}`.
- `test_normalize_board_draw_pile_missing_is_none` — no `draw_pile` key → `out["draw_pile"] is None`.
- `test_normalize_board_draw_pile_bad_coords_is_none` — string coords → `None`, no crash.
- `test_merger_passes_draw_pile_to_actionable_targets` — `find_draw_target(obs.game_state)` resolves
  to the VLM-reported coordinate end-to-end through `build_observation`.

**NOT VERIFIED:** shell unavailable. Baseline was 365 passed / 1 skipped (after this session's
earlier parse_failed tests). Expected: +5 new tests → **370 passed / 1 skipped**. No regressions
expected — the opponents/draw_pile fields are additive; the keys loop and usability gate are unchanged.

---

### 2026-08-07 (later still) — Policy parse rescue: `_extract_json_object` wired into `decide_model`

**Motivation:** The same `json.loads`-on-bare-text failure class that caused `vlm_status: "parse_failed"`
in the perception service also exists in the decision service. `decide_model` in `policy.py` called
`json.loads(model_text)` directly on the response from model-runtime-service. When the model returns
fenced JSON (`\`\`\`json\n{...}\n\`\`\``) or emits a reasoning preamble before the JSON object, this raises
`JSONDecodeError` and silently falls through to the heuristic with `fallback_reason="parse_failed"`. The
model's recommendation is discarded even though the JSON is present and valid.

**Fix — `services/decision-service/src/uno_decision/policy.py`:**

The `_extract_json_object` helper was already present in the file (added earlier in this session, mirroring
`vlm_provider._extract_json_object`). Wired it into the `json.JSONDecodeError` handler in `decide_model`:

```python
except json.JSONDecodeError:
    cleaned = _extract_json_object(model_text)
    if cleaned:
        try:
            structured = json.loads(cleaned)
        except json.JSONDecodeError:
            pass
if not structured:
    logger.warning("model_response_parse_failed", text=model_text[:200])
    tracker.complete(record, success=False, fallback_used=True,
                     fallback_reason="parse_failed", parse_success=False)
    return decide_heuristic(req)
```

The `model_response_parse_failed` log and heuristic fallback now only trigger when the rescue also fails —
i.e. when the response is genuinely unrecoverable.

**New tests — `tests/unit/test_decision_policy.py` (+8 cases):**

Five `_extract_json_object` tests (mirrors the vlm_provider coverage):
- `test_policy_extract_json_fenced_block`, `test_policy_extract_json_fenced_no_tag`
- `test_policy_extract_json_reasoning_preamble`, `test_policy_extract_json_no_json_returns_none`
- `test_policy_extract_json_nested_objects`

Three `decide_model` rescue-path tests (httpx mocked, no live model-runtime needed):
- `test_decide_model_rescues_fenced_json` — fenced JSON → model_used=True, correct action_index.
- `test_decide_model_rescues_preamble_json` — preamble JSON → model_used=True, correct action_index.
- `test_decide_model_falls_back_on_unrecoverable` — garbage text → heuristic fallback, model_used=False.

**NOT VERIFIED:** shell still unavailable. Baseline was 370 passed / 1 skipped. Expected: +8 new tests
→ **378 passed / 1 skipped**. No regressions expected — existing 3 tests in `test_decision_policy.py`
are unmodified; new tests add an `autouse` fixture that only patches `get_usage_tracker` (not called by
the existing heuristic/guard tests).


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

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

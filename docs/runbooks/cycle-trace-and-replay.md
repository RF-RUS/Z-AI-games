# Cycle Trace + Offline Perception Replay

Two pieces that only make sense together:

1. **Cycle trace** — while the agent plays, every cycle writes the exact frame plus the **full**
   perceived board to disk.
2. **Replay harness** — afterwards, re-run recognition over those saved frames with **no game, no
   services and no GPU**, and compare against a hand-verified answer.

## Why this exists

Perception is the component of this agent that fails *silently*. It does not raise; it returns a
plausible board that is wrong, and the agent then plays a card that is not on screen. Debugging that
live meant restarting 14 services, launching a real game and grepping four log files — ~30 minutes per
hypothesis, and every run irreproducible because the board differed.

This is also the guard rail for the multi-game goal. **When Svintus support lands, the replay corpus is
what tells you UNO still works.**

### Not the same thing as `AGENT_SCREENSHOT_TRACE`

`docs/runbooks/screenshot-trace.md` describes a different, complementary pipeline. It is not a
replacement for this one, for two reasons:

| | Screenshot trace (`agent_trace.py`) | Cycle trace (`cycle_trace.py`) |
|---|---|---|
| Adapter | **Playwright only** (needs a `page`) — never fires for the Windows adapter, which is what actually plays Ubisoft UNO | any adapter; called from the orchestrator |
| Records | **counts / booleans**: `hand_cards: 9`, `top_card: true` | the **full** board verbatim: which nine cards, which top card |
| Failed cycles | happy path only | every cycle, including ones that died in `perceive` |
| Usable as a regression corpus | no — a corpus of booleans cannot detect a board that is the right *size* and the wrong *content* | yes |

Keep both enabled if you like; they write to separate directories.

## Flags

| Variable | Default | Purpose |
|---|---|---|
| `AGENT_CYCLE_TRACE` | `1` (**on**) | `0` to disable |
| `AGENT_CYCLE_TRACE_DIR` | `artifacts/cycle_trace` | root directory |
| `AGENT_CYCLE_TRACE_KEEP` | `200` | cycle dirs retained **per session** |

On by default on purpose: the data has to already exist at the moment you discover you need it. Flags
are read **per call**, not cached at import — so unlike `vlm_provider`, setting the variable and
reloading actually works.

Only the **session-orchestrator** process (`:8100`) writes cycle traces, so that is the only process
that needs the env vars.

`KEEP` matters: frames are 1–3 MB and a session runs for hours. The oldest cycle directories are pruned.

## Directory layout

```
artifacts/cycle_trace/{session_id}/
├── 0001/
│   ├── frame.png      # COPY of the frame that was actually perceived
│   └── cycle.json
├── 0002/
└── ...
```

The frame is **copied, not referenced**. The adapter recycles its screenshot directory, so a recorded
path points at a different frame tomorrow — and a corpus of dangling paths is worse than no corpus.

Directory numbering comes from `RuntimeSession.cycle_counter`, **not** `metrics.total_steps`: the latter
only increments on a *completed* cycle, so every failed cycle would overwrite the previous one's trace.

### `cycle.json`

| Key | Contents |
|---|---|
| `schema_version` | bump it when the shape changes, so the harness can refuse to mis-read old fixtures |
| `frame` | `file`, `width`, `height`, `source_path`, and `copy_error` if the copy failed |
| `perception` | the **entire** perceived game state, verbatim — this is what the harness compares |
| `provenance` | `recognition_method`, `vlm_status`, `cv_build`, `source` |
| `confidence` | `overall`, `game_state`, `game_elements` |
| `legal_actions`, `decision`, `guard` | what the agent was allowed to do, chose, and was permitted |
| `outcome` | `failed_at`, `error`, `ok` |
| `timings_ms` | per-cycle wall time |

Provenance is recorded rather than inferred because **"9 cards at confidence 0.8" means something
completely different coming from the VLM, from the heuristic, or from a mock.** A fabricated mock board
once reached the agent at confidence 0.8 and it played a hand that did not exist on screen
(`AGENT_LOG.md` 2026-08-04).

## Workflow: growing the corpus

### 1. Play a session

Environment hygiene first — **the corpus is only ever as good as the captures**: exactly one UNO window
open, and nothing (Task Manager, the operator UI) overlapping the game area.

Aim for coverage of the *screen types*, not volume: opponent's turn, your turn, colour picker,
end-of-round, plus at least one frame where perception was visibly wrong.

### 2. Promote traced cycles to fixtures

```powershell
.\.venv\Scripts\python.exe scripts\replay_perception.py promote `
  artifacts\cycle_trace\<session_id>\0003 --game uno --case in_game_own_turn
```

Writes `tests/fixtures/perception/uno/in_game_own_turn/` containing `frame.png` and an `expected.json`
**stub**.

### 3. Hand-verify the label — this is the step that cannot be skipped

The stub is pre-filled with **the agent's own guess** purely as a typing aid, and carries a `_TODO` key.
Check every field against the frame by eye, correct it, then delete that key.

If you skip this, the "expected" answer *is* the bug: the comparison passes trivially and the corpus
enshrines the current behaviour forever. The corpus test therefore **fails** while `_TODO` is present.
Delete keys you do not want to assert — only labelled keys are compared, so a partial label is fine.

### 4. Run the harness

```powershell
.\.venv\Scripts\python.exe scripts\replay_perception.py run --game uno -v
.\.venv\Scripts\python.exe -m pytest tests\unit\test_perception_corpus.py -q
```

`--recognizer vlm` also exists, but **by hand only**: it needs a running Ollama with a loaded model and
takes ~11 s per frame, which is why the pytest path runs the deterministic recognizer only.

## Reading the results

Hand comparison is **order-insensitive but duplicate-sensitive**: the hand is fanned and rotated, so
left-to-right order is not ground truth — but two red 6s is a different hand from one red 6. Case and
the `"number"` spelling some models emit normalize to the same card.

Mismatches are reported as **missed** (in the label, not found) and **invented** (found, not in the
label). Invented cards are the dangerous ones: that is the failure mode that makes the agent play a card
that is not on screen.

> A **skipped** corpus test means the regression net **does not exist yet** — not that perception is
> fine. A fresh checkout is green because the corpus is empty.

## Key files

| File | Role |
|---|---|
| `packages/shared-utils/src/uno_shared/cycle_trace.py` | the writer; game-agnostic by design |
| `services/session-orchestrator/src/uno_orchestrator/flow_controller.py` | calls it from a `finally` in `run_cycle` |
| `scripts/replay_perception.py` | `run` / `promote` CLI + the comparison logic |
| `tests/unit/test_cycle_trace.py` | writer behaviour, incl. hostile inputs |
| `tests/unit/test_perception_corpus.py` | the regression itself + tests for the comparator |

`cycle_trace.py` knows nothing about cards, colours or turns — it serializes whatever the perception
payload contains. **Adding Svintus must not require touching it.**

## Invariants worth not breaking

- **Tracing must never break a cycle.** Every public function swallows its own exceptions and returns
  `None`; it is invoked from a `finally`, and the locals it reads are pre-bound *before* the `try` so the
  `finally` cannot raise `NameError` and swallow the real exception.
- **Lose a field, never the cycle.** Attribute reads go through `_safe_attr` and serialization through
  `_dump`. Note `getattr(obj, "x", None)` is **not** enough — its default only covers `AttributeError`,
  while these payloads are pydantic models whose fields can be properties that raise. The identical bug
  in `recovery.format_exception_message` took down the failure handler itself.
- **Never reduce `perception` to counts.** That is the whole reason this module exists.
- Session ids are sanitized before use as a path component — `sess/../../x` must not escape the root.

## Troubleshooting

| Symptom | Check |
|---|---|
| No directories under `artifacts/cycle_trace/` | `AGENT_CYCLE_TRACE=0`, or the orchestrator process did not get the env var. Grep its log for `cycle_trace_failed` |
| Directories exist but `frame.png` is missing | `cycle.json` → `frame.copy_error`. Usually the adapter already recycled the file |
| `perception` is `{}` | perception genuinely returned nothing — check `provenance.vlm_status` and, in the model-runtime log, `provider_empty_content` |
| `provenance.recognition_method` is a mock | `invoke_with_fallback` substituted `MockProvider` and still returned 200 OK. **Do not label such a frame** |
| Cycle numbers skip | expected — the counter increments per attempted cycle, including skipped/failed ones |
| Old cycles keep disappearing mid-session | `AGENT_CYCLE_TRACE_KEEP` too low for the session length |
| `promote` says "No cycle.json in ..." | you passed the session dir, not a numbered cycle dir |
| Corpus test fails with "was never hand-verified" | the `_TODO` key is still in `expected.json` — step 3 above |

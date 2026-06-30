# Real UNO Web Profile (Pizzuno)

**Site:** [Pizzuno](https://pizz.uno/singleplayer) — free browser UNO-like game with DOM-rendered cards.

**Profile:** `services/adapter-web/profiles/real-unoh-web.json`

**Usage guide:** [docs/USAGE.md](../USAGE.md) · **Operator workflows:** profile health, nightly smoke, fixture capture (sections 5–8)

## Verify

```powershell
python -m pytest tests/unit/test_real_unoh_profile.py tests/unit/test_profile_health.py -v
python scripts/capture-web-fixture.py --mode playwright --profile real-unoh-web --output tests/fixtures/web_adapter/real-unoh
```

Requires Playwright + network access for live capture.

## Selector health & drift detection

Profile-driven health checks validate required/optional selectors and record fallback usage.

| Status | Meaning |
|--------|---------|
| **healthy** | All required selectors match on primary |
| **degraded** | Required match only via fallback, and/or optional selectors fail |
| **broken** | One or more required selectors fail completely |

### Selector priority

1. **primary** — stable semantic/CSS locator (preferred)
2. **fallback_0, fallback_1** — explicit chain in profile JSON; logged when used
3. No silent healing — fallback usage increments `selector_fallback_success_total` and appears in health reports

Required for `real-unoh-web`: `game_root`, `hand_area`, `discard_top_card`, `draw_button`.

Optional: `play_button`, `current_player`, `uno_indicator`, `chat_messages`, `bootstrap_start_game`.

### Run health check manually

```powershell
# API (adapter-web running, port 8104)
curl http://127.0.0.1:8104/profiles/real-unoh-web/selector-health
curl http://127.0.0.1:8104/profiles/real-unoh-web/health/summary
curl http://127.0.0.1:8104/profiles/real-unoh-web/health/history
curl http://127.0.0.1:8104/metrics/profile-health

# CLI smoke (loads real site)
python scripts/nightly-profile-smoke.py --profile real-unoh-web --allow-network
```

Reports: `artifacts/profile-health/{run_id}.json` + screenshot. Alerts: `artifacts/profile-health/alerts/`.

### Operator scripts

```powershell
python scripts/profile-health-summary.py --profile real-unoh-web
python scripts/profile-health-history.py --profile real-unoh-web --json
python scripts/profile-health-alerts.py --profile real-unoh-web
```

Control-center Dashboard shows latest status badge and runbook hint when adapter-web is up.

## Alerting

| Alert | Severity | When |
|-------|----------|------|
| `broken_immediate` | critical | Any run ends BROKEN |
| `sustained_degraded` | warning | Required-selector degraded ≥3 consecutive runs |
| `fallback_spike` | warning | Required fallback ratio ≥50% over last 2 runs |
| `recovery` | info | Previous run broken/degraded, latest HEALTHY |

Optional-only failures do **not** trigger sustained-degraded alerts.

### Escalation

- **broken** → immediate selector investigation; open artifact + screenshot; run `inspect-pizzuno-game.py`
- **degraded** → inspect fallback usage and `dom_signature` trend; fix primary selectors if sustained
- **recovered** → confirm selectors; refresh fixtures if DOM changed

Exit codes (nightly script): `0` healthy, `1` broken, `2` degraded (if `--no-tolerate-degraded`), skip prints `skipped` JSON and exits `0` in CI without network.

### Nightly smoke

Schedule:

```powershell
python scripts/nightly-profile-smoke.py --profile real-unoh-web --allow-network
```

CI without network: skipped with clear reason (not a false pass on broken selectors).

### When nightly smoke fails

1. Open latest report in `artifacts/profile-health/`
2. Check `selector_results` — which primary/fallback failed
3. Compare `dom_signature` with previous runs (UI drift)
4. Run `python scripts/inspect-pizzuno-game.py` if site changed
5. Update profile selectors — prefer stable IDs/classes over brittle XPath
6. Re-run smoke; capture fixtures if perception contract changed

**Fix primary selectors** when fallbacks succeed long-term. Fallbacks are temporary tolerance, not the target state.

## Adjust selectors

1. Run `python scripts/inspect-pizzuno-game.py` after site changes.
2. Update `selectors` / `action_mappings` / `health` in the profile JSON.
3. Re-capture fixtures and run perception pipeline test.

## Debug failures

| Symptom | Fix |
|---------|-----|
| Health **broken** on `game_root` | Site shell changed — update `#app` or fallbacks |
| Health **degraded** (fallback used) | Primary selector drifted — fix primary, keep fallback as backup |
| Readiness timeout | Cookie banner — check `bootstrap_*` mappings |
| No top_card extracted | Update `discard_top_card` selector |
| Cards not clickable | Use `#player-hand .card.playable` not UUID ids |

## Fixtures

Screenshots: `tests/fixtures/web_adapter/real-unoh/`

Health expected sample: `tests/fixtures/web_adapter/real-unoh/health_expected.json`

Capture more:

```powershell
python scripts/capture-web-fixture.py --mode playwright --profile real-unoh-web
```

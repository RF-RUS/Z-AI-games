# PROMPT_TEMPLATES

Compact, copy-paste starters. Fill `<...>`. Always assume `PROJECT_MEMORY.md` is loaded.

## Audit
```
Audit <area>. Load per LOAD_RULES (onboarding/audit row). Report: purpose, key files,
contract touchpoints, invariant risks, drift vs docs. No refactors. Bullets only.
```

## Minimal patch
```
Fix <symptom> in <service/file>. Smallest change. Do not touch contracts in packages/schemas
or cross plugin boundaries. Show diff + which test proves it. Run: pytest <path> -x.
```

## Bug investigation
```
Investigate <bug>. Reproduce first (test or script under scripts/). Trace pipeline layer by layer
(Observed→Inferred→Legal→Decision→Execution). Identify the single owning layer. Propose fix +
regression test. Do not fix until root cause named.
```

## Integration hardening
```
Harden <adapter/model/profile integration>. Check: fallback path (heuristic/template/rule) intact,
timeouts/locks, Uncertainty populated, ModelUsageTracker/ChatPolicy honored. List failure modes +
guards. No new deps without reason.
```

## New game / plugin
```
Add <game> plugin. Use game-plugin-authoring skill. Implement perception/rules/strategy(/execution)
per plugin-interfaces.md, register at startup, add adapter profile JSON. Zero edits to orchestrator/
policy-guard/replay/UI. Confirm boundaries respected.
```

## Contract change
```
Change contract <Model.field> in packages/schemas. List every producer/consumer. Update all + contract
tests in one pass. Treat as breaking. Confirm no inline model drift in services.
```

## Release readiness
```
Assess release of <change>. Verify: ruff clean, bandit -ll clean, coverage >=60, unit+smoke(mock)+
integration green, no 3.12-only syntax if 3.11 needed, Windows paths validated if adapter-windows touched,
no port collisions. Output go/no-go checklist.
```

## Documentation sync
```
Sync docs for <change>. Update only affected docs/** + this ai-context if an invariant/port/convention
changed. Keep PROJECT_MEMORY < ~120 lines. No prose bloat.
```

# Web Profile Authoring

## Schema

`WebAdapterProfile` in `packages/schemas/src/uno_schemas/adapter_web.py`

## Steps

1. Copy `services/adapter-web/profiles/local-mock-uno.json`
2. Set `profile_id`, `launch_url`, `readiness_selector`
3. Map UI areas in `selectors`:
   - `discard_top_card`, `hand_area`, `chat_messages`, `chat_lines`, etc.
4. Add `action_mappings` for bot clicks
5. Document `limitations` for operators

## Validation

```powershell
python -m pytest tests/unit/test_adapter_web_profiles.py -v
```

## Selector maintenance

When a target site changes:
1. Re-capture fixture: `python scripts/capture-web-fixture.py --mode playwright --url <url>`
2. Update profile selectors
3. Re-run contract tests

See `docs/runbooks/playwright-debugging.md`.

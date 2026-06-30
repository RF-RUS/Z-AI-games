# Prompt Versioning

Prompts live in `prompts/{prompt_id}/v*.json`.

## Schema

`PromptProfile` — template with `{variables}`, `expected_output_schema`, `use_case`.

## Resolve active version

Highest active version for use case (see `prompts_registry.resolve_prompt`).

## Add prompt

1. Create `prompts/my_use_case/v1.0.0.json`
2. Set `use_case`, `template`, `expected_output_schema`
3. Run benchmark before promoting

## Change process

1. Add new version file (do not edit production version in place)
2. Benchmark compare
3. Switch callers via `prompt_id` + `prompt_version` or rely on latest active

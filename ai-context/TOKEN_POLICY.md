# TOKEN_POLICY

Three tiers. Default to loading as little as possible.

## Tier 1 — Always load (small, stable)
- `ai-context/PROJECT_MEMORY.md`
- `ai-context/LOAD_RULES.md` (skim to route)

## Tier 2 — Task-specific, load on demand
- Matching skill entry in `SKILLS_INDEX.md`.
- The single service `src/` + its tests for the task.
- Specific `docs/architecture/*` or `docs/runbooks/*` named by LOAD_RULES.
- `packages/schemas` **only** for contract/pipeline work.
- Relevant `PROMPT_TEMPLATES.md` block.

## Tier 3 — Archival / rare (do not load unless explicitly needed)
- `artifacts/**` (screenshots, profile-health, traces) — open a single named file only.
- Full `docs/integration/*` set — one file at a time.
- `.venv/`, lockfiles, `dist-electron/`, generated READMEs.
- `.mimocode/STATE.md` — onboarding/audit only.

## Rules
- Routing and boundary guardrails live in `LOAD_RULES.md` — follow them, not restated here.
- SHOULD read one service at a time; expand only if a boundary/contract forces it.
- MUST NOT bulk-read `services/*` / `docs/**`, or paste `artifacts/` binaries or whole test dirs.
- Keep Tier 1 stable: edit PROJECT_MEMORY only when an invariant, port, or convention actually changes.

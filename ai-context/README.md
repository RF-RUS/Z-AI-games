# AI Context System

Compact, load-on-demand working context for AI-assisted development (v0 / Cursor / Claude Code + GitHub loop).

## Files

| File | Purpose |
|------|---------|
| `PROJECT_MEMORY.md` | Always-load invariants (stack, pipeline, boundaries, ports). |
| `LOAD_RULES.md` | Router: task type → exactly what else to load. |
| `SKILLS_INDEX.md` | Project skills: trigger · scope · keep-out. |
| `PROMPT_TEMPLATES.md` | Copy-paste task starters. |
| `TOKEN_POLICY.md` | What stays in vs out of context. |
| `RUNBOOKS.md` | Pointers to `docs/runbooks/*` + scripts. |

**Start here:** load `PROJECT_MEMORY.md`, then route with `LOAD_RULES.md`. Loading tiers are defined in `TOKEN_POLICY.md`.

This folder is an index/router, not documentation. `docs/**` stays the source of truth for design detail; never copy it here.

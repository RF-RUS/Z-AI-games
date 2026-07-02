# AI Context System

Compact, load-on-demand working context for AI-assisted development (v0 / Cursor / Claude Code + GitHub loop).

## Files

| File | Load when | Size intent |
|------|-----------|-------------|
| `PROJECT_MEMORY.md` | **Always** (every session) | Small, stable |
| `LOAD_RULES.md` | Start of any task — tells you what else to load | Tiny |
| `SKILLS_INDEX.md` | To pick the right skill for the task | Small |
| `PROMPT_TEMPLATES.md` | When starting audit/patch/bug/release work | Small |
| `TOKEN_POLICY.md` | To decide what to keep in vs out of context | Tiny |
| `RUNBOOKS.md` | Setup / run / test / deploy / incident | Index only |

## Rule of use

1. Always load `PROJECT_MEMORY.md`.
2. Read `LOAD_RULES.md`, match your task type, load only what it lists.
3. Pull deeper files (`docs/**`, service source) **on demand**, never preemptively.

Do not duplicate `docs/**` here. This folder indexes and constrains; `docs/**` remains the source of truth for design detail.

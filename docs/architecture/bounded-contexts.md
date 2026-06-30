# Bounded Context Map

> **This document is superseded by [architecture/overview.md](overview.md).**
> 
> The canonical bounded context map, service responsibilities, and ownership boundaries are now in the [Platform Architecture](overview.md) document.
>
> This file is retained only for historical reference.

---

## Historical Content

The original bounded context diagram showed UNO-specific service naming. The current architecture uses plugin-based naming where UNO is one implementation:

| Old (UNO-centric) | Current (universal) |
|-------------------|---------------------|
| Game Truth: `uno-core` | Game Rules: `uno-core` (UNO plugin), extensible per-game |
| Perception: hardcoded UNO | Perception: plugin-based (`PerceptionPlugin` protocol) |
| Intelligence: `decision-service` | Intelligence: plugin-based (`StrategyPlugin` protocol) |

See [overview.md](overview.md) for the current architecture.

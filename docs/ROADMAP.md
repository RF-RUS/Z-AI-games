# Game Agent Platform — Roadmap

> Baseline: 2026-06-19 | Updated: 2026-06-23 | Stage: Beta (~85%)

---

## Platform Roadmap

### Implemented

| Component | Status | Generic? |
|-----------|--------|----------|
| Session orchestrator | Complete | Yes |
| AdapterProtocol + Registry | Complete | Yes |
| Plugin-based perception dispatch | Complete | Yes |
| Plugin-based strategy dispatch | Complete | Yes |
| Policy guard (legality + confidence) | Complete | Yes |
| Operator Control Center | Complete | Yes |
| Screenshot trace pipeline | Complete | Yes |
| CDP browser connect | Complete | Yes |
| Autonomous loop + recovery | Complete | Yes |
| 274 tests (unit + integration) | All pass | Yes |

### In Progress

| Item | Status | Notes |
|------|--------|-------|
| CI/CD pipeline | Blueprint designed | GitHub Actions workflow partial |
| Docker production deployment | Pending | Dockerfiles TBD |
| Observability stack | Pending | Structured logging only; Prometheus/Grafana TBD |

### Planned

| Item | Phase | What it enables |
|------|-------|-----------------|
| VLM integration | P2 | Canvas/WebGL game support without DOM |
| Generic game profile generation | P2 | Auto-create adapter profiles from VLM |
| Second non-UNO game plugin | P2 | Proves true universality |
| World-state synchronization | P3 | Re-observe before decide, reduce drift |
| Full semantic verification | P3 | Action-aware outcome confirmation |
| Real-time monitoring dashboard | P4 | Prometheus + Grafana |

### Deferred

| Item | Reason |
|------|--------|
| Universal GUI agent (any application) | Requires VLM + profile auto-generation |
| Multi-platform beyond browser + Windows | No current user demand |
| SaaS multi-tenant deployment | Internal tool only at this stage |

---

## UNO Reference Implementation

UNO is the first working game plugin. These items are UNO-specific, not platform goals.

### Current Sprint: scuffed-uno-web Playability

**Goal**: Make the canvas UNO game playable via screenshot-based hand detection + dynamic action grounding.

**Phase 1** (Week 1): Fix execute grounding
- Dynamic card-to-canvas coordinate mapping
- Replace hardcoded `play_red_five` with slot-based targeting
- Profile hand_region, table_region, lobby_region, per-slot layout_targets

**Phase 2** (Week 2): Screenshot hand detection
- OpenCV template matching for card identification
- Screen-state classifier from screenshot heuristics
- Post-action screenshot verification

**Definition of Done**: Agent plays 10+ cycles with correct card selection on scuffed-uno-web.

### UNO Implemented

- UNO rules engine (`uno-core`) — full rules, legal actions, game state
- UNO perception adapter — DOM/screenshot → game state extraction
- UNO heuristic strategy — card power scoring
- DOM profiles: `real-unoh-web` (Pizzuno), `local-mock-uno`, `scuffed-uno-web`
- Svintus game plugin — second game proving multi-game architecture

### UNO In Progress

- scuffed-uno-web playability (screenshot CV)
- E2E canvas gameplay not yet confirmed

### UNO Planned

- VLM-based card recognition for canvas games
- Template matching for hand detection
- Dynamic action grounding (slot-based coordinate mapping)

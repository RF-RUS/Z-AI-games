# Plugin Interfaces

This document defines the canonical plugin protocols. Every game implements these interfaces to plug into the universal platform.

## Plugin Boundary Rules

| Plugin | May access | Must never access |
|--------|-----------|-------------------|
| **PerceptionPlugin** | `ObservedState`, `RawAffordances`, VLM models | UI execution, game rules, strategy |
| **RulesPlugin** | `InferredState`, `RawAffordances` | UI elements, DOM, selectors, coordinates |
| **StrategyPlugin** | `InferredState`, `LegalActions`, `Affordances`, models | UI elements, DOM, raw observations |
| **ExecutionPlugin** | `DecisionResult`, `InferredState`, `Affordances` | Game rules, strategy logic |
| **GameModelConfig** | Declarative — declares preferred models, does not call them | Nothing — pure config |

## GameModelConfig

Every game plugin declares preferred models via `GameModelConfig`. This is **declarative** — the plugin says what it wants, the platform resolves and routes.

```python
class GameModelConfig(BaseModel):
    game_type: str
    strategy_models: list[str]    # preferred strategy model profile_ids
    vision_models: list[str]      # preferred vision model profile_ids
    chat_models: list[str]        # preferred chat model profile_ids
    intent_models: list[str]      # preferred intent model profile_ids
    fallback_to_heuristic: bool = True
    fallback_to_template: bool = True
    chat_enabled: bool = True
    model_chat_enabled: bool = False
```

**Resolution:** `resolve_model_profile(game_type, task, available_profiles)` picks the first available preferred model, or returns `None` for fallback.

**Ownership:** Plugin declares preference. Platform resolves route. Plugin never calls models directly.

---

## PerceptionPlugin

**Responsibility**: Convert raw UI observations into game-specific inferred state.

**Input**: `ObservedState` + `RawAffordances`
**Output**: `InferredState`

```python
class PerceptionPlugin(Protocol):
    """Converts raw observations into game-specific inferred state."""
    
    game_type: str
    
    def infer_state(
        self,
        observed: ObservedState,
        raw_affordances: RawAffordances,
    ) -> InferredState:
        """Parse raw UI evidence into game-specific state.
        
        UNO: reads top_card, hand, direction from DOM elements.
        Chess: reads board position from piece positions.
        Canvas: uses VLM/CV to identify game elements from screenshot.
        """
        ...
    
    def extract_entities(
        self,
        observed: ObservedState,
    ) -> list[Entity]:
        """Extract individual game elements (cards, pieces, tokens).
        
        Used for operator display and VLM verification.
        """
        ...
    
    def check_discrepancy(
        self,
        state_a: InferredState,
        state_b: InferredState,
    ) -> Contradiction | None:
        """Compare two observations of the same state."""
        ...
```

### UNO Implementation Notes

```python
class UNOPerceptionPlugin:
    game_type = "uno"
    
    def infer_state(self, observed, raw_affordances):
        entities = []
        for elem in observed.interactive_elements:
            if elem.metadata.get("card_color"):
                entities.append(Entity(
                    entity_id=elem.element_id,
                    entity_type=EntityType.ITEM,
                    name=f"{elem.metadata['card_color']} {elem.metadata['card_value']}",
                    item=ItemData(
                        item_class="card",
                        color=elem.metadata["card_color"],
                        value=elem.metadata["card_value"],
                        is_playable=elem.enabled,
                    ),
                    location=EntityLocation(container="hand"),
                ))
        
        whose_turn = "self" if _detect_your_turn(observed) else "opponent"
        
        return InferredState(
            game_type="uno",
            screen_state=_classify_screen(observed),
            whose_turn=whose_turn,
            turn_confidence=0.9,
            entities=entities,
            summary=_build_summary(entities, whose_turn),
            observation_confidence=observed.source_confidence,
        )
```

### Canvas/VLM Implementation Notes

```python
class CanvasUNOPerceptionPlugin:
    game_type = "uno_canvas"
    
    def infer_state(self, observed, raw_affordances):
        # No DOM elements — must use screenshot + VLM
        vlm_result = call_vlm(observed.screenshot_path, prompt=UNO_EXTRACTION_PROMPT)
        
        entities = []
        for card in vlm_result.detected_cards:
            entities.append(Entity(
                entity_id=f"card_{card.slot_index}",
                entity_type=EntityType.ITEM,
                name=f"{card.color} {card.value}",
                item=ItemData(
                    item_class="card",
                    color=card.color,
                    value=card.value,
                    is_playable=card.is_in_hand,
                ),
                location=EntityLocation(
                    container="hand" if card.is_in_hand else "board",
                    slot_index=card.slot_index,
                    pixel_pos=(card.x, card.y),
                ),
                confidence=card.detection_confidence,
            ))
        
        return InferredState(
            game_type="uno",
            screen_state=vlm_result.screen_state,
            whose_turn=vlm_result.whose_turn,
            turn_confidence=vlm_result.turn_confidence,
            entities=entities,
            summary=vlm_result.summary,
            observation_confidence=vlm_result.overall_confidence,
        )
```

---

## GroundingProvider

**Responsibility**: Resolve *where to click* for a decided action (e.g.
`choose_color=red`) — the counterpart to perception's *what is on screen*. This
seam keeps adapters game-agnostic: they receive a click point and click it, with
no knowledge of cards, colours, or suits.

**Contract**: `services/perception-service/src/uno_perception/grounding.py`

```python
class GroundingProvider(Protocol):
    method: str  # "uia" | "template" | "vlm"
    async def ground(self, req: GroundingRequest) -> GroundingResult: ...

# req: action_type, screenshot_path, params ({"color": "red"}), game_type, profile
# res: found, x, y, confidence, method, reason   (x,y in screenshot pixels)
```

`resolve_grounding(req, providers, min_confidence)` tries providers
**cheapest-first**; the first hit at/above the threshold wins, a broken provider
never blocks a fallback, and `found=True ⟹ confidence ≥ min_confidence`.

**Implementations** (`grounding_providers.py`):

| Provider | Status | Notes |
|----------|--------|-------|
| `VLMGroundingProvider` | **Wired** | Asks the vision model for the click point directly; reuses the VLM `/invoke` path. Gated on `VLM_PERCEPTION=1`. |
| `UIAGroundingProvider` | Planned | Move the existing UIA element lookup behind the contract. |
| `TemplateGroundingProvider` | Planned | OpenCV template/anchor match for games shipping reference assets. |

**Call path**: orchestrator `_execute` → perception `POST /ground`
(`clients.ground`) → `resolve_grounding` → `target_x/target_y` on the adapter
request. For `choose_color`, a cheap path first reuses an already-perceived
`prompts[]` colour button before the VLM round-trip. Verified clicks cache into
learned_zones so repeats resolve via the cheap path.

**Upgrade path**: if direct-coordinate accuracy falls short, switch
`VLMGroundingProvider` to **Set-of-Marks** — generate candidate marks with
OpenCV, overlay numbered labels, ask the VLM for a mark number (OmniParser
style).

---

## RulesPlugin

**Responsibility**: Game rules — legal actions, turn detection, state transitions, affordance reconciliation.

**Input**: `InferredState`, `RawAffordances`
**Output**: `LegalActions`, `Affordances` (reconciled), `VerifiedResult`

```python
class RulesPlugin(Protocol):
    """Game rules: what actions are legal given current state."""
    
    game_type: str
    
    def get_legal_actions(
        self,
        state: InferredState,
    ) -> list[GameAction]:
        """All actions the rules permit, regardless of UI."""
        ...
    
    def validate_action(
        self,
        state: InferredState,
        action: GameAction,
    ) -> bool:
        """Is this specific action legal right now?"""
        ...
    
    def apply_action(
        self,
        state: InferredState,
        action: GameAction,
    ) -> InferredState:
        """Simulate action execution to get resulting state."""
        ...
    
    def reconcile_with_affordances(
        self,
        rule_actions: list[GameAction],
        raw_affordances: RawAffordances,
    ) -> LegalActions:
        """Intersect rule-legal actions with UI-accessible actions.
        
        Returns:
          - actions: the intersection (what we should consider)
          - all_rule_legal: everything rules allow
          - ui_accessible: everything UI exposes
          - blocked_by_ui: rule-legal but not in UI
        """
        ...
    
    def reconcile_affordances(
        self,
        inferred: InferredState,
        raw_affordances: RawAffordances,
        locks: InteractionLocks,
    ) -> Affordances:
        """Build runtime affordances with locks and deferred actions."""
        ...
    
    def whose_turn(
        self,
        state: InferredState,
    ) -> str:
        """Determine whose turn it is.
        Returns: "self" | "opponent" | "unknown"
        """
        ...
    
    def verify_action(
        self,
        before: InferredState,
        after: InferredState,
        action: GameAction,
    ) -> VerifiedResult:
        """Check if action had expected effect."""
        ...
```

### UNO Implementation Notes

```python
class UNORulesPlugin:
    game_type = "uno"
    
    def get_legal_actions(self, state):
        top_card = _find_top_card(state)
        hand = _find_hand(state)
        actions = []
        
        for card in hand:
            if _card_matches(top_card, card):
                actions.append(GameAction(
                    action_id=f"play_{card.entity_id}",
                    action_type="play_card",
                    target_entity_id=card.entity_id,
                    payload={"card_color": card.item.color, "card_value": card.item.value},
                    confidence=1.0,
                    reasoning=f"Matches {top_card.item.color}/{top_card.item.value}",
                ))
        
        actions.append(GameAction(
            action_id="draw",
            action_type="draw",
            confidence=1.0,
            reasoning="Always legal",
        ))
        
        return actions
    
    def reconcile_with_affordances(self, rule_actions, raw):
        ui_ids = {e.element_id for e in raw.elements if e.enabled}
        accessible = [a for a in rule_actions if a.target_entity_id in ui_ids or a.target_entity_id is None]
        blocked = [a for a in rule_actions if a.target_entity_id and a.target_entity_id not in ui_ids]
        
        return LegalActions(
            actions=accessible,
            all_rule_legal=rule_actions,
            ui_accessible=accessible,
            blocked_by_ui=blocked,
        )
```

---

## StrategyPlugin

**Responsibility**: Action selection — choose the best action from legal options.

**Input**: `InferredState`, `LegalActions`, `Affordances`
**Output**: `DecisionResult`

```python
class StrategyPlugin(Protocol):
    """Action selection: which legal action to take."""
    
    game_type: str
    strategy_id: str
    
    def decide(
        self,
        state: InferredState,
        legal_actions: LegalActions,
        affordances: Affordances,
        context: DecisionContext,
    ) -> DecisionResult:
        """Choose the best action from legal options."""
        ...
    
    def explain(self, decision: DecisionResult) -> str:
        """Human-readable explanation of why this action was chosen."""
        ...

@dataclass
class DecisionContext:
    session_history: list[GameAction]
    operator_hints: list[str]
    confidence_threshold: float
```

### UNO Implementation Notes

```python
class UNOHeuristicStrategy:
    game_type = "uno"
    strategy_id = "heuristic"
    
    def decide(self, state, legal_actions, affordances, context):
        scored = []
        for action in legal_actions.actions:
            score = _score_card(action)
            scored.append((action, score))
        
        scored.sort(key=lambda x: -x[1])
        chosen = scored[0][0]
        
        return DecisionResult(
            chosen_action_id=chosen.action_id,
            confidence=min(0.95, scored[0][1]),
            explanation=f"Chose {chosen.action_type}: {_reason(action)}",
            alternatives_considered=len(scored) - 1,
            strategy_id=self.strategy_id,
        )

def _score_card(action):
    if action.action_type == "play_card":
        value = action.payload.get("card_value", "")
        color = action.payload.get("card_color", "")
        if "wild" in str(value) and "draw" in str(value): return 0.9
        if "draw" in str(value): return 0.85
        if value in ("skip", "reverse"): return 0.75
        if str(value).isdigit(): return 0.5 + 0.05 * int(value)
        return 0.5
    if action.action_type == "draw": return 0.1
    return 0.3
```

---

## ExecutionPlugin

**Responsibility**: Convert abstract game actions into concrete multi-step UI interaction plans.

**Input**: `DecisionResult`, `InferredState`, `Affordances`
**Output**: `ExecutionPlan`

```python
class ExecutionPlugin(Protocol):
    """Multi-step action execution planning."""
    
    game_type: str
    
    def plan_execution(
        self,
        action: DecisionResult,
        current_state: InferredState,
        affordances: Affordances,
    ) -> ExecutionPlan:
        """Convert abstract game action into concrete UI step sequence."""
        ...
    
    def get_verification_checkpoints(
        self,
        plan: ExecutionPlan,
    ) -> list[VerificationCheckpoint]:
        """After which steps should we verify state changed correctly?"""
        ...
    
    def handle_failure(
        self,
        plan: ExecutionPlan,
        failed_step: int,
        error: str,
        current_state: InferredState,
    ) -> ExecutionRecovery:
        """What to do when a step in the plan fails."""
        ...
```

### UNO Implementation Notes

```python
class UNOExecutionPlugin:
    game_type = "uno"
    
    def plan_execution(self, action, state, affordances):
        target = affordances.executable.find(a.action_id == action.chosen_action_id)
        
        return ExecutionPlan(
            plan_id=f"exec_{action.chosen_action_id}",
            action_id=action.chosen_action_id,
            steps=[
                ExecutionStep(
                    step_index=0,
                    interaction=InteractionPrimitive(
                        primitive_type="click",
                        target_entity_id=target.target_entity_id,
                        target_coords=target.target_coords,
                    ),
                    post_verification="card_removed_from_hand",
                    timeout_ms=2000,
                )
            ],
            total_estimated_ms=2000,
        )
```

---

## Plugin Registration

Plugins are registered at service startup:

```python
# perception-service startup
from uno_perception.plugins.uno import UNOPerceptionPlugin
from uno_perception.plugins.chess import ChessPerceptionPlugin

register_perception_plugin("uno", UNOPerceptionPlugin())
register_perception_plugin("chess", ChessPerceptionPlugin())

# decision-service startup
from uno_decision.strategies.uno_heuristic import UNOHeuristicStrategy
from uno_decision.strategies.chess_minimax import ChessMinimaxStrategy

register_strategy("uno", "heuristic", UNOHeuristicStrategy())
register_strategy("chess", "minimax", ChessMinimaxStrategy())
```

## Adding a New Game

To add a new game (e.g., Poker):

1. **Create perception plugin**: `services/perception-service/src/plugins/poker.py`
   - Implement `PerceptionPlugin.infer_state()` — parse cards, pot, positions from UI
   - Register in perception-service startup

2. **Create rules plugin**: `services/game-core/src/poker_rules.py`
   - Implement `RulesPlugin.get_legal_actions()` — fold/call/raise/check
   - Implement `RulesPlugin.whose_turn()` — position-based turn detection
   - Register in rules service or embed in perception-service

3. **Create strategy plugin**: `services/decision-service/src/strategies/poker_strategy.py`
   - Implement `StrategyPlugin.decide()` — pot odds, position, bluff detection
   - Register in decision-service startup

4. **Create adapter profile**: `services/adapter-web/profiles/poker-site.json`
   - Define selectors for card elements, bet buttons, chat
   - No code changes needed in adapter-web

5. **Create execution plugin** (if multi-step needed):
   - Implement `ExecutionPlugin.plan_execution()` — select cards → confirm bet → wait

No changes needed to: orchestrator, policy-guard, operator UI, trace system, replay service.

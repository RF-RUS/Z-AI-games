# Intermediate Contract — Canonical Pipeline

This document defines the **single source of truth** for data flowing between pipeline layers. Every game plugin, adapter, and orchestrator must conform to these contracts.

## Contract Layers

| Layer | Purpose | Producer | Consumer | Generic? |
|-------|---------|----------|----------|----------|
| **ObservedState** | Raw UI detection | adapters | PerceptionPlugin | Yes |
| **RawAffordances** | Static UI interaction possibilities | adapters | PerceptionPlugin, RulesPlugin | Yes |
| **InferredState** | Game-specific interpretation | PerceptionPlugin | RulesPlugin, StrategyPlugin, Orchestrator | Per-game |
| **LegalActions** | Rule-legal actions reconciled with UI | RulesPlugin | StrategyPlugin, PolicyGuard | Per-game |
| **Affordances** (reconciled) | Runtime interaction state with locks | RulesPlugin + PerceptionPlugin | StrategyPlugin, ExecutionPlugin | Partially |
| **DecisionResult** | Chosen action + confidence | StrategyPlugin | ExecutionPlugin, Orchestrator | Per-game |
| **ExecutionPlan** | Multi-step UI interaction sequence | ExecutionPlugin | adapters | Per-game |
| **Uncertainty** | Contradictions, missing fields, confidence | All layers | Orchestrator, UI | Yes |
| **VerifiedResult** | Action outcome confirmation | RulesPlugin | Orchestrator | Per-game |

---

## ObservedState

**Purpose**: Raw detection from UI — no game interpretation.

**Producer**: adapter-web / adapter-windows via `capture_evidence()`
**Consumer**: PerceptionPlugin

```python
class ObservedState(BaseModel):
    timestamp_ms: int
    session_id: str
    
    # What we see
    screen_type: str                          # "dom_page" | "canvas" | "windows_uia" | "screenshot"
    interactive_elements: list[UIElement]     # buttons, inputs, cards, links
    text_content: list[TextBlock]             # OCR, DOM text, labels
    screenshot_path: str | None               # raw screenshot for VLM/CV
    
    # Evidence quality
    source_confidence: float                  # 0-1
    evidence_sources: list[str]               # ["dom", "screenshot", "ocr", "uia"]
    
    # Raw passthrough
    raw_dom: dict | None
    raw_ui_tree: dict | None

class UIElement(BaseModel):
    element_id: str
    element_type: str                         # "button" | "card" | "link" | "input" | "canvas_region"
    label: str
    bounds: tuple[int, int, int, int] | None  # x, y, width, height
    enabled: bool
    visible: bool
    confidence: float
    metadata: dict[str, str | int | float | bool | None]  # game-specific hints

class TextBlock(BaseModel):
    text: str
    bounds: tuple[int, int, int, int] | None
    source: str                               # "dom" | "ocr" | "ui_tree"
    confidence: float
```

### UNO Example
```
ObservedState {
  screen_type: "dom_page",
  interactive_elements: [
    UIElement(id="card_0", type="card", label="Red 7", bounds=(120,400,60,90), enabled=true),
    UIElement(id="draw_btn", type="button", label="Draw Card", bounds=(400,300,80,40), enabled=true),
  ],
  text_content: [TextBlock("Your turn", (300,50))],
  evidence_sources: ["dom", "screenshot"]
}
```

### Canvas Game Example
```
ObservedState {
  screen_type: "screenshot",
  interactive_elements: [],        ← NO DOM elements
  text_content: [],                ← NO OCR
  screenshot_path: "artifacts/{session}/001_observe/frame.png",
  evidence_sources: ["screenshot"]
}
```

### Desktop Game Example
```
ObservedState {
  screen_type: "windows_uia",
  interactive_elements: [
    UIElement(id="play_btn", type="button", label="Play Card", bounds=(300,400,80,30), enabled=true),
  ],
  text_content: [TextBlock("Top: Red 7", (200,200))],
  evidence_sources: ["uia", "screenshot"]
}
```

---

## RawAffordances

**Purpose**: Static UI interaction possibilities — what the DOM/UIA exposes.

**Producer**: adapter-web / adapter-windows
**Consumer**: PerceptionPlugin, RulesPlugin

```python
class RawAffordances(BaseModel):
    elements: list[UIElement]               # same elements as ObservedState
    modals: list[ModalOverlay]              # detected dialogs/blockers
    selection_mode: SelectionMode | None    # None | "card_selected" | "targeting"

class ModalOverlay(BaseModel):
    element_id: str
    label: str
    blocks_background: bool = True

class SelectionMode(BaseModel):
    mode: str                               # "card_selected" | "targeting" | "piece_selected"
    selected_element_id: str | None = None
    valid_target_ids: list[str] = []
```

---

## InferredState

**Purpose**: Game-specific interpretation of observations.

**Producer**: PerceptionPlugin (per-game)
**Consumer**: RulesPlugin, StrategyPlugin, Orchestrator

```python
class InferredState(BaseModel):
    game_type: str                          # "uno" | "chess" | "poker" | "custom"
    screen_state: str                       # "lobby" | "in_game" | "menu" | "game_over" | "unknown"
    
    # Turn management
    whose_turn: str                         # "self" | "opponent" | "unknown"
    turn_confidence: float
    
    # Game entities
    entities: list[Entity]
    
    # High-level summary for operator
    summary: str
    
    # Confidence
    observation_confidence: float
```

### Entity Schema

```python
class Entity(BaseModel):
    entity_id: str
    entity_type: EntityType
    name: str
    visibility: Visibility                  # visible | hidden | disabled | animating
    confidence: float
    location: EntityLocation
    owner_id: str | None = None
    is_interactive: bool = False
    interaction_hint: str | None = None     # "clickable" | "selectable" | "draggable"
    
    # Type-specific payloads (exactly one populated)
    actor: ActorData | None = None
    item: ItemData | None = None
    board_region: BoardRegionData | None = None
    resource: ResourceData | None = None
    turn_marker: TurnMarkerData | None = None
    ui_control: UIControlData | None = None
    
    # Game-specific extension
    game_data: dict[str, str | int | float | bool | None] | None = None

class EntityType(StrEnum):
    ACTOR = "actor"
    ITEM = "item"
    BOARD_REGION = "board_region"
    RESOURCE = "resource"
    TURN_MARKER = "turn_marker"
    SELECTABLE_TARGET = "target"
    UI_CONTROL = "ui_control"
    ANNOTATION = "annotation"

class Visibility(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"
    DISABLED = "disabled"
    ANIMATING = "animating"

class EntityLocation(BaseModel):
    container: str | None = None            # "hand" | "board" | "deck" | "discard"
    grid_pos: tuple[int, int] | None = None
    slot_index: int | None = None
    pixel_pos: tuple[int, int] | None = None

class ActorData(BaseModel):
    is_self: bool
    is_turn: bool
    score: int | None = None
    status: str | None = None

class ItemData(BaseModel):
    item_class: str                         # "card" | "piece" | "token"
    color: str | None = None
    value: str | int | None = None
    is_face_up: bool = True
    is_playable: bool = False
    is_selected: bool = False

class BoardRegionData(BaseModel):
    region_class: str
    is_occupied: bool = False
    occupant_id: str | None = None
    is_valid_target: bool = False

class ResourceData(BaseModel):
    resource_class: str
    current: int | float = 0
    max_value: int | float | None = None
    delta_last_action: int | float = 0

class TurnMarkerData(BaseModel):
    current_actor_id: str
    phase: str
    time_remaining_ms: int | None = None

class UIControlData(BaseModel):
    control_class: str
    is_enabled: bool = True
    is_visible: bool = True
    current_value: str | None = None
```

### UNO Example
```
InferredState {
  game_type: "uno",
  screen_state: "in_game",
  whose_turn: "self",
  entities: [
    Entity(id="hand_0", type=ITEM, name="Red 7", item=ItemData(color="red", value="7", is_playable=true),
           location=EntityLocation(container="hand", slot_index=0)),
    Entity(id="top_card", type=ITEM, name="Red 5", item=ItemData(color="red", value="5"),
           location=EntityLocation(container="discard")),
    Entity(id="direction", type=TURN_MARKER, turn_marker=TurnMarkerData(current_actor_id="self", phase="main")),
    Entity(id="hand_count", type=RESOURCE, resource=ResourceData(resource_class="hand_size", current=2)),
  ],
  summary: "Your turn. Red 5 on top. You have Red 7 (playable)."
}
```

---

## LegalActions

**Purpose**: What the rules allow, filtered by UI affordances.

**Producer**: RulesPlugin (per-game)
**Consumer**: StrategyPlugin, PolicyGuard

```python
class LegalActions(BaseModel):
    actions: list[GameAction]               # reconciled: rules ∩ affordances
    all_rule_legal: list[GameAction]        # before UI filtering
    ui_accessible: list[GameAction]         # after UI filtering
    blocked_by_ui: list[GameAction]         # rule-legal but not in UI

class GameAction(BaseModel):
    action_id: str
    action_type: str                        # "play_card" | "draw" | "pass" | "move_piece"
    target_entity_id: str | None
    payload: dict[str, str | int | float | bool | None]
    confidence: float
    reasoning: str
```

---

## Affordances (Reconciled)

**Purpose**: Runtime interaction state with locks — what the agent can actually do right now.

**Producer**: RulesPlugin + PerceptionPlugin (reconciled)
**Consumer**: StrategyPlugin, ExecutionPlugin

```python
class Affordances(BaseModel):
    executable: list[ExecutableAction]      # ready to fire
    deferred: list[DeferredAction]          # need prerequisite
    blocked: list[BlockedAction]            # visible but blocked
    locks: InteractionLocks
    selection: SelectionState

class InteractionLocks(BaseModel):
    modal_active: bool = False
    modal_element_id: str | None = None
    animation_in_progress: bool = False
    animation_element_id: str | None = None
    animation_ends_at_ms: int | None = None
    cooldown_active: bool = False
    cooldown_element_id: str | None = None
    cooldown_remaining_ms: int | None = None
    focus_locked: bool = False
    focus_element_id: str | None = None
    turn_lock: bool = False
    confirmation_pending: bool = False
    confirmation_element_id: str | None = None

class SelectionState(BaseModel):
    mode: str | None = None
    selected_entity_id: str | None = None
    valid_targets: list[str] = []

class ExecutableAction(BaseModel):
    action_id: str
    action_type: str                        # "click" | "type" | "key_press" | "drag"
    target_entity_id: str | None = None
    target_coords: tuple[int, int] | None = None
    label: str
    requires_post_confirmation: bool = False
    estimated_duration_ms: int = 1000

class DeferredAction(BaseModel):
    action_id: str
    action_type: str
    label: str
    prerequisite: Prerequisite
    target_entity_id: str | None = None
    target_coords: tuple[int, int] | None = None

class Prerequisite(BaseModel):
    type: str                               # "select_entity" | "dismiss_modal" | "wait_animation"
    target_entity_id: str | None = None
    target_coords: tuple[int, int] | None = None
    estimated_wait_ms: int = 0

class BlockedAction(BaseModel):
    action_id: str
    action_type: str
    label: str
    blocked_by: str
    retry_after_ms: int | None = None
```

---

## DecisionResult

**Purpose**: Chosen action + confidence + explanation.

**Producer**: StrategyPlugin (per-game)
**Consumer**: ExecutionPlugin, Orchestrator

```python
class DecisionResult(BaseModel):
    chosen_action_id: str
    confidence: float
    explanation: str
    alternatives_considered: int = 0
    strategy_id: str = "heuristic"
```

---

## ExecutionPlan

**Purpose**: Multi-step UI interaction sequence to execute one game action.

**Producer**: ExecutionPlugin (per-game)
**Consumer**: adapters

```python
class ExecutionPlan(BaseModel):
    plan_id: str
    action_id: str                          # which GameAction this executes
    steps: list[ExecutionStep]
    total_estimated_ms: int

class ExecutionStep(BaseModel):
    step_index: int
    interaction: InteractionPrimitive
    pre_condition: str | None = None
    post_verification: str | None = None
    timeout_ms: int

class InteractionPrimitive(BaseModel):
    primitive_type: str                     # "click" | "type" | "key_press" | "drag" | "scroll"
    target_element_id: str | None = None
    target_coords: tuple[int, int] | None = None
    payload: dict | None = None

class VerificationCheckpoint(BaseModel):
    after_step: int
    expected_change: str
    fallback: str                           # "retry" | "abort" | "ask_operator"

class ExecutionRecovery(BaseModel):
    strategy: str                           # "retry_same" | "skip_step" | "replan" | "escalate"
    retry_delay_ms: int | None = None
    modified_plan: ExecutionPlan | None = None
```

---

## Uncertainty

**Purpose**: What we don't know or what contradicts — tracked across all layers.

**Producer**: All layers append to it
**Consumer**: Orchestrator, Operator UI

```python
class Uncertainty(BaseModel):
    contradictions: list[Contradiction]
    missing_fields: list[str]
    low_confidence_fields: list[tuple[str, float]]
    unresolved_ambiguity: list[str]
    needs_human_intervention: bool
    suggested_action: str                   # "re-observe" | "ask_operator" | "proceed_with_caution"

class Contradiction(BaseModel):
    field: str
    source_a: str
    value_a: Any
    source_b: str
    value_b: Any
    severity: str                           # "warning" | "error"
```

---

## VerifiedResult

**Purpose**: Did the action have the expected effect?

**Producer**: RulesPlugin
**Consumer**: Orchestrator

```python
class VerifiedResult(BaseModel):
    confirmed: bool
    outcome: str                            # "card_played" | "state_changed" | "no_change" | "error"
    expected: str | None = None
    observed: str | None = None
    confidence: float = 1.0
```

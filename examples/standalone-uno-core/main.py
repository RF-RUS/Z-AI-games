"""Standalone uno-core example."""

from uno_core.reducer import apply_action, to_public_table_state
from uno_core.rules import generate_legal_actions
from uno_core.state import create_initial_state


def main():
  state = create_initial_state("demo", ["Bot", "Opponent"], seed=42)
  print("Public state:", to_public_table_state(state).model_dump())
  actions = generate_legal_actions(state)
  print(f"Legal actions: {len(actions)}")
  if actions:
    state, events = apply_action(state, actions[0])
    print(f"Applied: {events[0].event_type.value}")


if __name__ == "__main__":
  main()

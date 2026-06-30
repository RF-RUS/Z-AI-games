# Using uno-core Standalone

```python
from uno_core.state import create_initial_state
from uno_core.rules import generate_legal_actions
from uno_core.reducer import apply_action

state = create_initial_state("g1", ["Alice", "Bob"], seed=42)
actions = generate_legal_actions(state)
state, events = apply_action(state, actions[0])
```

Or via HTTP:

```python
from uno_client import UnoCoreClient
import asyncio

async def main():
    client = UnoCoreClient()
    game = await client.create_game(["A", "B"], seed=1)
    actions = await client.legal_actions(game["game_id"])
```

See `examples/standalone-uno-core/`.

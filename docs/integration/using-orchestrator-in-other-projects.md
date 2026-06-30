# Reusing the Orchestrator

Generic modules (no UNO game logic):

- `state_machine.py` — flow state transitions
- `recovery.py` — error classification + retry decisions
- `clients.py` — HTTP adapter pattern (swap endpoints)
- `flow_controller.py` — step loop skeleton

Wire your own `ServiceClients` implementations and `SessionSpec` use cases.

```python
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_orchestrator.clients import ServiceClients

orch = SessionOrchestrator(clients=ServiceClients())
```

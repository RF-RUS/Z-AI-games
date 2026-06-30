# Using adapter-web in Other Projects

`adapter-web` is a reusable browser observation/execution service.

## Minimal integration

```python
import httpx
from uno_schemas.adapter_web import AdapterMode, AttachWebAdapterRequest

async with httpx.AsyncClient() as client:
    attach = await client.post("http://localhost:8104/attach", json=AttachWebAdapterRequest(
        session_id="my-app",
        profile_id="local-mock-uno",  # or your custom profile
        mode=AdapterMode.PLAYWRIGHT,
        url="https://your-game.example",
    ).model_dump(mode="json"))
    adapter_id = attach.json()["adapter_id"]

    evidence = await client.get(f"http://localhost:8104/adapters/{adapter_id}/evidence")
    # evidence.json()["dom_evidence"] — feed to your perception/ML pipeline
```

## Extension points

1. **New profile** — add JSON under `profiles/`, no code changes required
2. **Custom extraction** — extend `extraction.py` or post-process `DomSnapshot.extracted`
3. **Actions** — `POST /adapters/{id}/actions` with `ActionExecutionRequest`

## Without UNO

Do not import `uno-core` or `decision-service`. Use only:
- `adapter-web` for browser I/O
- `WebAdapterProfile` schema for selectors
- Your own business logic for interpreting `DomEvidence`

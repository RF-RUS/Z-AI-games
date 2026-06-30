# Using adapter-windows in Other Projects

```python
import httpx
from uno_schemas.adapter_windows import AttachWindowsAdapterRequest, WindowsAdapterMode

async with httpx.AsyncClient() as client:
    r = await client.post("http://localhost:8105/attach", json=AttachWindowsAdapterRequest(
        session_id="my-desktop-bot",
        profile_id="local-mock-uno",
        mode=WindowsAdapterMode.MOCK,
    ).model_dump(mode="json"))
    aid = r.json()["adapter_id"]
    evidence = await client.get(f"http://localhost:8105/adapters/{aid}/evidence")
    ui = evidence.json()["ui_evidence"]
```

Reuse without UNO: use profiles + evidence only; skip `uno-core` and `decision-service`.

Extension points: `runtime.py`, `extraction.py`, profile JSON.

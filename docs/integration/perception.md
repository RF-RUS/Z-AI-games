# Using perception-service in Another Project

```python
import httpx
from uno_schemas.perception import DomEvidence

async with httpx.AsyncClient() as client:
    resp = await client.post("http://localhost:8103/perceive", json={
        "session_id": "my-automation",
        "dom": {"snapshot": {"top_card": {"color": "red", "value": "5"}}, "confidence": 0.9},
    })
    observation = resp.json()
    # observation.confidence.overall — never treat as canonical truth
```

Key contract: outputs always include confidence metadata.

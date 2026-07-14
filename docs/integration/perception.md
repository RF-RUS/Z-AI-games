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

## Action grounding (`POST /ground`)

Perception also answers *where to click for a decided action*. Give it the
action + the current screenshot; it returns a click point in screenshot pixels
(or `found=false` to fall back). Providers are tried cheapest-first
(UIA → template → VLM); the VLM provider needs `VLM_PERCEPTION=1` + a vision
profile.

```python
resp = await client.post("http://localhost:8103/ground", json={
    "action_type": "choose_color",
    "screenshot_path": "/abs/path/frame.png",
    "params": {"color": "red"},
    "game_type": "uno",
    "min_confidence": 0.5,
})
g = resp.json()   # {found, x, y, confidence, method, reason}
if g["found"]:
    click(g["x"], g["y"])   # screenshot coords → adapter maps to screen
```


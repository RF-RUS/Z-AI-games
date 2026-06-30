# Using chat-intent-service in Another Game Client

```python
import httpx

messages = [{"message_id": "1", "sender": "Player", "text": "@bot help!", "timestamp_ms": 0}]
resp = httpx.post("http://localhost:8108/detect", json={"messages": messages})
intent = resp.json()
if intent and intent["reply_required"]:
    # route to your chat-response handler
    pass
```

Chat is fully isolated from gameplay — safe to integrate in any client.

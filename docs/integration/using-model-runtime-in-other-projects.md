# Reusing Model Runtime

```python
import httpx
from uno_schemas.model import ModelInvocationContext, ModelInvocationRequest, ModelUseCase

async with httpx.AsyncClient() as client:
    r = await client.post("http://localhost:8111/invoke", json=ModelInvocationRequest(
        context=ModelInvocationContext(use_case=ModelUseCase.CHAT_INTENT, correlation_id="x"),
        profile_id="mock/uno-assistant",
        prompt_id="chat_intent",
        variables={"message": "hello"},
        expect_json=True,
    ).model_dump(mode="json"))
```

Reusable pieces: `providers.py`, `prompts_registry.py`, `benchmark_runner.py`.

No UNO imports required.

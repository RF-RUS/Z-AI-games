# Using model-registry-service Standalone

```python
from uno_client import ModelRegistryClient
import asyncio

async def main():
    reg = ModelRegistryClient("http://localhost:8110")
    models = await reg.list_models()
    for m in models:
        print(m.model_id, m.runtime, m.enabled)
```

Manifest schema: `uno_schemas.model.ModelManifest`

See `examples/standalone-model-registry/`.

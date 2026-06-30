# Adding a New Adapter

1. Create `services/adapter-{name}/` with FastAPI app
2. Implement contract:
   - `POST /attach` → `{adapter_id, attached}`
   - Evidence endpoint (`/dom` or `/ui-tree`)
   - `POST /detach`
3. Output maps to `DomEvidence` or `UiEvidence`
4. Register port in `uno_schemas.api.SERVICE_PORTS`
5. Add mock implementation for tests

Extension point: inherit adapter interface, swap via `session-orchestrator` config.

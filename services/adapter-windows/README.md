# adapter-windows

Windows UI Automation adapter — mock + pywinauto real mode.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/profiles` | List profiles |
| POST | `/attach` | `AttachWindowsAdapterRequest` |
| GET | `/adapters/{id}/evidence` | `WindowsEvidenceBundle` |
| GET | `/adapters/{id}/ui-tree` | Legacy tree dict |
| POST | `/adapters/{id}/actions` | `WindowsActionExecutionRequest` |
| GET | `/windows/candidates` | Top-level windows |
| GET | `/pywinauto/check` | Dependency check |

## Dev

```powershell
python services/adapter-windows/test-target/uno_mock_app.py
uvicorn uno_adapter_windows.api:app --port 8105
python scripts/capture-windows-fixture.py --mode mock
```

## Tests

```powershell
pytest tests/unit/test_adapter_windows_profiles.py -v
pytest tests/contracts/test_adapter_windows.py -v
pytest tests/e2e/test_windows_pywinauto.py -v
```

Docs: `docs/architecture/windows-adapter.md`

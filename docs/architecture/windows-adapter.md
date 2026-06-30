# Windows Adapter Architecture

## Modes

| Mode | Description |
|------|-------------|
| `mock` | Deterministic CI default |
| `pywinauto` | Real UIA/win32 via pywinauto |

## Data flow

```
WindowsAdapterProfile → PywinautoSession → WindowSnapshot + Screenshot
                                              ↓
                                        UiEvidence (confidence)
                                              ↓
                                        perception-service → Observation
```

## Backends

- **uia** (preferred) — modern apps, richer trees
- **win32** (fallback) — legacy/sparse UIA

## Sparse trees

Tkinter and some games expose limited accessibility metadata. The pipeline sets `sparse_tree=true` and lowers confidence. OCR/VLM fallback is a future extension point.

## Stubbed

- Direct UIAutomation COM adapter
- OCR-first fallback mode
- Commercial UNO client profiles (template only)

See `docs/runbooks/windows-uia-debugging.md`.

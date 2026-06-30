# Game Agent — Windows Operator Client

Electron + React operator dashboard for the Game Agent platform.

## Quick Start

```powershell
cd apps/control-center
npm install --ignore-scripts
npm run dev
```

Open **http://localhost:5173** in browser, or the Electron window will open automatically.

## Features

- Service health monitoring (ports 8100–8113)
- Session management (create, attach, start, pause, resume, stop)
- Auto / Assist / Manual control modes
- Operator commands via chat
- Evidence preview with screenshot
- Observation summary with game state
- Escalation flow with recommended actions
- Agent transparency panel
- Keyboard shortcuts (F5-F9, /, Escape)

## Build

```powershell
npm run build:win
```

Produces NSIS installer in `release/`.

## First Run

See [docs/USAGE.md](../../docs/USAGE.md#runbook-first-independent-bot-launch-on-windows) for the complete first-run runbook.

**TL;DR:**
1. Start backend: `.\scripts\dev-backend.ps1`
2. Open Game Agent
3. Set mode to **Assist** (not Auto)
4. Select adapter + profile + game window
5. Click "Start Playing"
6. Monitor the bot's actions in the Monitor panel

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| F5 | Start / Tick |
| F6 | Pause |
| F7 | Resume |
| F8 | Toggle Auto/Manual |
| F9 | Return to Bot |
| / | Focus chat input |
| Escape | Dismiss alert |

## Architecture

```
Electron Main Process
├── main.ts          (entry, window, menu)
├── logging.ts       (structured file logging)
├── persistence.ts   (settings, window bounds)
├── crash-reporter.ts (exception capture)
├── updater.ts       (auto-update foundation)
└── preload.ts       (secure IPC bridge)

React Renderer
├── App.tsx           (main layout + state)
├── operatorStore.ts  (useReducer state model)
├── usePolling.ts     (health + session polling)
├── operatorCommands.ts (chat command parser)
├── analytics.ts      (event schema + buffer)
└── components/       (UI components)
```

## User Data

Stored in `%APPDATA%\GameAgent\`:
- `config/settings.json` — user preferences
- `logs/app-{date}.log` — structured logs
- `state/crash-*.json` — crash state files
- `state/last-session.json` — last session reference

## Documentation

- [Full runbook](../../docs/USAGE.md#runbook-first-independent-bot-launch-on-windows)
- [Usage guide](../../docs/USAGE.md)
- [Architecture overview](../../docs/architecture/overview.md)

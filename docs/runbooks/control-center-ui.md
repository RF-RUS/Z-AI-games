# Control Center UI

## Operator tab

- Session list with flow state badges
- Error panel: classification, recovery action, retry count
- Tick / Pause / Resume / Stop

## Dashboard Start Session

Creates session via orchestrator → attach → start → opens Operator tab.

Web adapter uses `real-unoh-web` profile when selected.

## Replay screenshots

- Thumbnails for screenshot artifacts (local path via Electron `readLocalImage`)
- Click to open full preview modal
- Base64 from observation bundles when available

## Experimental

- Real UNO web requires Playwright + network
- Screenshot preview works for local artifact paths only in Electron

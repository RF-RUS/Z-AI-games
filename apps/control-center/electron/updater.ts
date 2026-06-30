/** Auto-updater foundation — safe update checking and notification.

Provides:
- Check for updates on startup or menu action
- Non-intrusive update notification
- Download progress tracking
- Restart prompt when ready
- Error handling for failed updates
*/

import { app, BrowserWindow, dialog, Menu } from "electron";
import { autoUpdater, UpdateInfo } from "electron-updater";
import { logInfo, logWarn, logError } from "./logging";

export type UpdateStatus = "idle" | "checking" | "available" | "downloading" | "ready" | "failed" | "not-available";

interface UpdateState {
  status: UpdateStatus;
  info: UpdateInfo | null;
  error: string | null;
  downloadProgress: number;
}

let _updateState: UpdateState = {
  status: "idle",
  info: null,
  error: null,
  downloadProgress: 0,
};

let _mainWindow: BrowserWindow | null = null;

export function setupUpdater(mainWindow: BrowserWindow): void {
  _mainWindow = mainWindow;

  // Disable auto-download — we'll notify user instead
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = false;

  // Event handlers
  autoUpdater.on("checking-for-update", () => {
    _updateState.status = "checking";
    logInfo("updater", "Checking for updates");
    notifyRenderer("update-status", _updateState);
  });

  autoUpdater.on("update-available", (info) => {
    _updateState.status = "available";
    _updateState.info = info;
    logInfo("updater", "Update available", { version: info.version });
    notifyRenderer("update-status", _updateState);

    // Show non-intrusive notification
    showUpdateNotification(info);
  });

  autoUpdater.on("update-not-available", () => {
    _updateState.status = "not-available";
    logInfo("updater", "No updates available");
    notifyRenderer("update-status", _updateState);
  });

  autoUpdater.on("download-progress", (progress) => {
    _updateState.status = "downloading";
    _updateState.downloadProgress = progress.percent;
    notifyRenderer("update-status", _updateState);
  });

  autoUpdater.on("update-downloaded", (info) => {
    _updateState.status = "ready";
    _updateState.info = info;
    logInfo("updater", "Update downloaded", { version: info.version });
    notifyRenderer("update-status", _updateState);

    // Prompt user to restart
    showRestartPrompt(info);
  });

  autoUpdater.on("error", (error) => {
    _updateState.status = "failed";
    _updateState.error = error.message;
    logError("updater", "Update error", { error: error.message });
    notifyRenderer("update-status", _updateState);
  });
}

export function checkForUpdates(): void {
  logInfo("updater", "Manual update check triggered");
  autoUpdater.checkForUpdates().catch((err) => {
    logWarn("updater", "Update check failed", { error: String(err) });
  });
}

export function getUpdateState(): UpdateState {
  return { ..._updateState };
}

export function installUpdate(): void {
  logInfo("updater", "Installing update and restarting");
  autoUpdater.quitAndInstall();
}

function notifyRenderer(channel: string, data: UpdateState): void {
  if (_mainWindow && !_mainWindow.isDestroyed()) {
    _mainWindow.webContents.send(channel, data);
  }
}

function showUpdateNotification(info: UpdateInfo): void {
  if (!_mainWindow || _mainWindow.isDestroyed()) return;

  dialog.showMessageBox(_mainWindow, {
    type: "info",
    title: "Update Available",
    message: `A new version (${info.version}) is available.`,
    detail: "Would you like to download and install it now?",
    buttons: ["Download", "Later"],
    defaultId: 0,
  }).then(({ response }) => {
    if (response === 0) {
      autoUpdater.downloadUpdate().catch((err) => {
        logError("updater", "Download failed", { error: String(err) });
      });
    }
  });
}

function showRestartPrompt(info: UpdateInfo): void {
  if (!_mainWindow || _mainWindow.isDestroyed()) return;

  dialog.showMessageBox(_mainWindow, {
    type: "info",
    title: "Update Ready",
    message: `Version ${info.version} has been downloaded.`,
    detail: "The application will restart to apply the update. Your session will be preserved.",
    buttons: ["Restart Now", "Later"],
    defaultId: 0,
  }).then(({ response }) => {
    if (response === 0) {
      autoUpdater.quitAndInstall();
    }
  });
}

export function addUpdaterMenu(menuTemplate: Electron.MenuItemConstructorOptions[]): Electron.MenuItemConstructorOptions[] {
  return [
    ...menuTemplate,
    {
      label: "Help",
      submenu: [
        {
          label: "Check for Updates...",
          click: () => checkForUpdates(),
        },
        {
          label: "Export Diagnostics...",
          click: () => exportDiagnostics(),
        },
        { type: "separator" },
        {
          label: "About Game Agent",
          click: () => showAbout(),
        },
      ],
    },
  ];
}

function exportDiagnostics(): void {
  const { getLogDir } = require("./logging");
  const logDir = getLogDir();
  dialog.showOpenDialog(_mainWindow!, {
    title: "Export Diagnostics",
    defaultPath: logDir,
    properties: ["openDirectory"],
  }).then(({ filePaths }) => {
    if (filePaths.length > 0) {
      dialog.showMessageBox(_mainWindow!, {
        type: "info",
        title: "Diagnostics",
        message: `Log directory: ${logDir}`,
        detail: "You can copy the log files from this directory to share with support.",
        buttons: ["OK"],
      });
    }
  });
}

function showAbout(): void {
  dialog.showMessageBox(_mainWindow!, {
    type: "info",
    title: "About Game Agent",
    message: `Game Agent v${app.getVersion()}`,
    detail: `Electron ${process.versions.electron}\nNode ${process.versions.node}\nChrome ${process.versions.chrome}`,
    buttons: ["OK"],
  });
}

export { UpdateState };

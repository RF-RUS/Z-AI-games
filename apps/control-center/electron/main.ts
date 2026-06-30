import { app, BrowserWindow, Menu, shell } from "electron";
import path from "path";
import { logInfo, logWarn, logError, getLogDir } from "./logging";
import { setupCrashReporting, checkForCrashOnStartup } from "./crash-reporter";
import { loadSettings, saveSettings, saveWindowBounds, saveLastSession } from "./persistence";
import { setupUpdater, addUpdaterMenu } from "./updater";

const SERVICES = [
  { name: "session-orchestrator", port: 8100 },
  { name: "uno-core", port: 8101 },
  { name: "perception-service", port: 8103 },
  { name: "decision-service", port: 8106 },
  { name: "model-registry-service", port: 8110 },
];

let mainWindow: BrowserWindow | null = null;

/**
 * Wait for a URL to become available before loading it.
 * Handles the race condition between Electron starting and Vite dev server being ready.
 */
async function waitForUrl(url: string, maxRetries: number = 15, delayMs: number = 500): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(url, { method: "HEAD", signal: AbortSignal.timeout(2000) });
      if (response.ok || response.status < 500) {
        logInfo("app", `Vite dev server ready at ${url} (attempt ${i + 1})`);
        return;
      }
    } catch {
      // Server not ready yet
    }
    logInfo("app", `Waiting for Vite dev server... (attempt ${i + 1}/${maxRetries})`);
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  logWarn("app", `Vite dev server not ready after ${maxRetries} attempts, loading anyway`);
}

function createWindow(): BrowserWindow {
  const settings = loadSettings();

  const windowOptions: Electron.BrowserWindowConstructorOptions = {
    width: settings.windowBounds?.width ?? 1280,
    height: settings.windowBounds?.height ?? 800,
    x: settings.windowBounds?.x ?? undefined,
    y: settings.windowBounds?.y ?? undefined,
    minWidth: 900,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    title: "Game Agent",
    icon: path.join(__dirname, "../build/icon.ico"),
    show: false,
  };

  const win = new BrowserWindow(windowOptions);

  // Show window when ready to prevent flash
  win.once("ready-to-show", () => {
    win.show();
  });

  // Save window bounds on resize/move
  let boundsTimeout: ReturnType<typeof setTimeout> | null = null;
  const saveBounds = () => {
    if (boundsTimeout) clearTimeout(boundsTimeout);
    boundsTimeout = setTimeout(() => {
      if (!win.isDestroyed()) {
        const bounds = win.getBounds();
        saveWindowBounds(bounds);
      }
    }, 500);
  };
  win.on("resize", saveBounds);
  win.on("move", saveBounds);

  // Save last session on close
  win.on("close", () => {
    saveLastSession(null); // Will be updated by renderer before close
  });

  // Open external links in default browser
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  return win;
}

async function loadWindowContent(win: BrowserWindow): Promise<void> {
  const devUrl = process.env.VITE_DEV_SERVER_URL;

  if (devUrl) {
    try {
      await waitForUrl(devUrl, 15, 500);
    } catch (error) {
      logWarn("app", `Vite dev server not ready after retries: ${String(error)}`);
    }

    if (!win.isDestroyed()) {
      await win.loadURL(devUrl);
    }
  } else {
    if (!win.isDestroyed()) {
      await win.loadFile(path.join(__dirname, "../dist/index.html"));
    }
  }
}

function buildMenu(): void {
  const template: Electron.MenuItemConstructorOptions[] = [
    {
      label: "File",
      submenu: [
        { label: "New Session", accelerator: "CmdOrCtrl+N", click: () => mainWindow?.webContents.send("menu-new-session") },
        { type: "separator" },
        { role: "quit" },
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(addUpdaterMenu(template)));
}

// App lifecycle
app.whenReady().then(async () => {
  logInfo("app", "Application starting", {
    version: app.getVersion(),
    electron: process.versions.electron,
    node: process.versions.node,
  });

  // Setup crash reporting first
  setupCrashReporting();

  // Check for crash on startup
  if (checkForCrashOnStartup()) {
    logInfo("app", "Previous crash detected, showing recovery dialog");
  }

  // Create window
  mainWindow = createWindow();
  buildMenu();

  // Runtime verification: track renderer loading
  mainWindow.webContents.once("did-finish-load", () => {
    logInfo("app", "Renderer loaded successfully");
  });
  mainWindow.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL) => {
    logError("app", "Renderer failed to load", {
      errorCode,
      errorDescription,
      url: validatedURL,
    });
  });

  // Load content (waits for Vite dev server in dev mode)
  await loadWindowContent(mainWindow);

  // Setup updater
  setupUpdater(mainWindow);

  // Track app version
  const settings = loadSettings();
  settings.lastVersion = app.getVersion();
  settings.lastLaunch = new Date().toISOString();
  saveSettings(settings);

  logInfo("app", "Application ready");
});

app.on("window-all-closed", () => {
  logInfo("app", "All windows closed");
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    mainWindow = createWindow();
  }
});

app.on("before-quit", () => {
  logInfo("app", "Application quitting");
  saveLastSession(null);
});

export { SERVICES };

/** State persistence — save and restore user settings and session context.

Stores mutable user data in app.getPath("userData") / %APPDATA%-compatible location.
Separates app binaries from user data per Windows best practices.
*/

import { app } from "electron";
import fs from "fs";
import path from "path";
import { logInfo, logWarn } from "./logging";

const SETTINGS_FILE = "settings.json";
const STATE_DIR = "state";

interface WindowBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface PersistedSettings {
  // User preferences
  lastAdapterType: string;
  lastProfileId: string;
  lastControlMode: string;
  windowBounds: WindowBounds | null;

  // UI preferences
  showEvidencePanel: boolean;
  showTransparency: boolean;

  // Version tracking
  lastVersion: string;
  lastLaunch: string;
}

const DEFAULT_SETTINGS: PersistedSettings = {
  lastAdapterType: "windows",
  lastProfileId: "real-uno-desktop",
  lastControlMode: "auto",
  windowBounds: null,
  showEvidencePanel: true,
  showTransparency: true,
  lastVersion: "",
  lastLaunch: "",
};

function getSettingsPath(): string {
  return path.join(app.getPath("userData"), SETTINGS_FILE);
}

function getStateDir(): string {
  const dir = path.join(app.getPath("userData"), STATE_DIR);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return dir;
}

export function loadSettings(): PersistedSettings {
  try {
    const filePath = getSettingsPath();
    if (fs.existsSync(filePath)) {
      const data = fs.readFileSync(filePath, "utf-8");
      const parsed = JSON.parse(data);
      return { ...DEFAULT_SETTINGS, ...parsed };
    }
  } catch (err) {
    logWarn("persistence", "Failed to load settings", { error: String(err) });
  }
  return { ...DEFAULT_SETTINGS };
}

export function saveSettings(settings: PersistedSettings): void {
  try {
    const filePath = getSettingsPath();
    fs.writeFileSync(filePath, JSON.stringify(settings, null, 2), "utf-8");
  } catch (err) {
    logWarn("persistence", "Failed to save settings", { error: String(err) });
  }
}

export function saveWindowBounds(bounds: WindowBounds): void {
  const settings = loadSettings();
  settings.windowBounds = bounds;
  saveSettings(settings);
}

export function saveLastSession(sessionId: string | null): void {
  const stateDir = getStateDir();
  const filePath = path.join(stateDir, "last-session.json");
  try {
    fs.writeFileSync(filePath, JSON.stringify({ sessionId, timestamp: Date.now() }), "utf-8");
  } catch (err) {
    logWarn("persistence", "Failed to save last session", { error: String(err) });
  }
}

export function loadLastSession(): { sessionId: string | null; timestamp: number } | null {
  try {
    const filePath = path.join(getStateDir(), "last-session.json");
    if (fs.existsSync(filePath)) {
      return JSON.parse(fs.readFileSync(filePath, "utf-8"));
    }
  } catch {
    // State load is best-effort
  }
  return null;
}

export function saveCrashState(data: Record<string, unknown>): void {
  const stateDir = getStateDir();
  const timestamp = Date.now();
  const filePath = path.join(stateDir, `crash-${timestamp}.json`);
  try {
    fs.writeFileSync(filePath, JSON.stringify({ ...data, timestamp }, null, 2), "utf-8");
    logInfo("crash", "Crash state saved", { path: filePath });
  } catch (err) {
    logWarn("crash", "Failed to save crash state", { error: String(err) });
  }
}

export function getCrashFiles(): string[] {
  try {
    const stateDir = getStateDir();
    return fs.readdirSync(stateDir)
      .filter((f) => f.startsWith("crash-") && f.endsWith(".json"))
      .sort()
      .reverse();
  } catch {
    return [];
  }
}

export { PersistedSettings };

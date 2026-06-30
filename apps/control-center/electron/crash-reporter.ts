/** Crash reporting — capture and store crash information.

Provides:
- Main process uncaught exception handling
- Renderer process error capture
- Crash state file generation
- Structured crash metadata
*/

import { app, clipboard, dialog } from "electron";
import fs from "fs";
import path from "path";
import { logError, logInfo, getLogDir } from "./logging";
import { saveCrashState } from "./persistence";

interface CrashInfo {
  type: string;
  message: string;
  stack?: string;
  timestamp: string;
  electronVersion: string;
  nodeVersion: string;
  platform: string;
  appVersion: string;
}

function getCrashInfo(error: Error | string, type: string): CrashInfo {
  const message = typeof error === "string" ? error : error.message;
  const stack = typeof error === "object" ? error.stack : undefined;
  return {
    type,
    message,
    stack,
    timestamp: new Date().toISOString(),
    electronVersion: process.versions.electron ?? "unknown",
    nodeVersion: process.versions.node ?? "unknown",
    platform: `${process.platform} ${process.version}`,
    appVersion: app.getVersion(),
  };
}

export function setupCrashReporting(): void {
  // Main process uncaught exceptions
  process.on("uncaughtException", (error: Error) => {
    const info = getCrashInfo(error, "uncaughtException");
    logError("crash", "Uncaught exception", info as unknown as Record<string, unknown>);
    saveCrashState(info as unknown as Record<string, unknown>);
  });

  // Main process unhandled rejections
  process.on("unhandledRejection", (reason: unknown) => {
    const info = getCrashInfo(
      reason instanceof Error ? reason : String(reason),
      "unhandledRejection",
    );
    logError("crash", "Unhandled rejection", info as unknown as Record<string, unknown>);
    saveCrashState(info as unknown as Record<string, unknown>);
  });

  // Renderer process errors (via IPC)
  app.on("web-contents-created", (_, contents) => {
    contents.on("render-process-gone", (_event, details) => {
      const info = getCrashInfo(
        details.reason || "render-process-gone",
        "renderProcessGone",
      );
      logError("crash", "Renderer process gone", {
        ...info as unknown as Record<string, unknown>,
        reason: details.reason,
        exitCode: details.exitCode,
      });
      saveCrashState(info as unknown as Record<string, unknown>);
    });
  });

  logInfo("crash", "Crash reporting initialized");
}

export function showCrashDialog(error: string): void {
  dialog.showMessageBox({
    type: "error",
    title: "Game Agent — Unexpected Error",
    message: "The application encountered an unexpected error.",
    detail: error.length > 500 ? error.slice(0, 500) + "..." : error,
    buttons: ["Copy Error", "Close"],
  }).then(({ response }) => {
    if (response === 0) {
      clipboard.writeText(error);
    }
  });
}

export function checkForCrashOnStartup(): boolean {
  const stateDir = path.join(app.getPath("userData"), "state");
  try {
    if (!fs.existsSync(stateDir)) return false;
    const files = fs.readdirSync(stateDir)
      .filter((f) => f.startsWith("crash-") && f.endsWith(".json"))
      .sort()
      .reverse();
    if (files.length === 0) return false;
    const latestCrash = path.join(stateDir, files[0]);
    const data = JSON.parse(fs.readFileSync(latestCrash, "utf-8"));
    const crashTime = data.timestamp ?? 0;
    const now = Date.now();
    // Only show recovery if crash was within last 24 hours
    if (now - crashTime < 24 * 60 * 60 * 1000) {
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

export { CrashInfo };

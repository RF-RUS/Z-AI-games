/** Main process logging — structured logging with file output.

Provides logging for the Electron main process with:
- Console output in development
- File output in production
- Log rotation (bounded growth)
- Structured format for diagnostics
*/

import { app } from "electron";
import fs from "fs";
import path from "path";

type LogLevel = "debug" | "info" | "warn" | "error";

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  category: string;
  message: string;
  data?: Record<string, unknown>;
}

const LOG_DIR = path.join(app.getPath("userData"), "logs");
const MAX_LOG_SIZE_MB = 10;
const MAX_LOG_FILES = 5;

let _initialized = false;
let _logFile: string | null = null;

function ensureLogDir(): void {
  if (_initialized) return;
  try {
    if (!fs.existsSync(LOG_DIR)) {
      fs.mkdirSync(LOG_DIR, { recursive: true });
    }
    _logFile = path.join(LOG_DIR, `app-${new Date().toISOString().split("T")[0]}.log`);
    _initialized = true;
  } catch {
    // Logging is best-effort
  }
}

function rotateLogs(): void {
  try {
    if (!_logFile || !fs.existsSync(_logFile)) return;
    const stats = fs.statSync(_logFile);
    if (stats.size > MAX_LOG_SIZE_MB * 1024 * 1024) {
      const timestamp = Date.now();
      fs.renameSync(_logFile, `${_logFile}.${timestamp}`);
      // Clean old logs
      const files = fs.readdirSync(LOG_DIR)
        .filter((f) => f.startsWith("app-") && f !== path.basename(_logFile!))
        .sort()
        .reverse();
      for (const file of files.slice(MAX_LOG_FILES)) {
        fs.unlinkSync(path.join(LOG_DIR, file));
      }
    }
  } catch {
    // Rotation is best-effort
  }
}

function writeLog(entry: LogEntry): void {
  ensureLogDir();
  if (!_logFile) return;

  try {
    const line = JSON.stringify(entry) + "\n";
    fs.appendFileSync(_logFile, line, "utf-8");
    rotateLogs();
  } catch {
    // Logging is best-effort
  }
}

export function log(level: LogLevel, category: string, message: string, data?: Record<string, unknown>): void {
  const entry: LogEntry = {
    timestamp: new Date().toISOString(),
    level,
    category,
    message,
    data,
  };

  // Console output in development
  if (process.env.VITE_DEV_SERVER_URL) {
    const prefix = `[${level.toUpperCase()}] [${category}]`;
    console.log(`${prefix} ${message}`, data ?? "");
  }

  writeLog(entry);
}

export function logInfo(category: string, message: string, data?: Record<string, unknown>): void {
  log("info", category, message, data);
}

export function logWarn(category: string, message: string, data?: Record<string, unknown>): void {
  log("warn", category, message, data);
}

export function logError(category: string, message: string, data?: Record<string, unknown>): void {
  log("error", category, message, data);
}

export function logDebug(category: string, message: string, data?: Record<string, unknown>): void {
  log("debug", category, message, data);
}

export function getLogDir(): string {
  ensureLogDir();
  return LOG_DIR;
}

export function getLogFile(): string | null {
  ensureLogDir();
  return _logFile;
}

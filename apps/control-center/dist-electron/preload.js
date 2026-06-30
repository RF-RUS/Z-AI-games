"use strict";
const electron = require("electron");
const fs = require("fs");
const path = require("path");
const API_BASE = "http://127.0.0.1";
const ORCH = `${API_BASE}:8100`;
electron.contextBridge.exposeInMainWorld("unoApi", {
  // Health & connection
  healthCheck: async (port) => {
    const r = await fetch(`${API_BASE}:${port}/health`, { signal: AbortSignal.timeout(3e3) });
    if (!r.ok) {
      throw new Error(`HTTP ${r.status}`);
    }
    return r.json();
  },
  getConfig: async () => {
    const r = await fetch(`${API_BASE}:8113/config`);
    return r.json();
  },
  listModels: async () => {
    const r = await fetch(`${API_BASE}:8110/models`);
    return r.json();
  },
  // Replays
  listReplays: async () => {
    const r = await fetch(`${API_BASE}:8102/replays`);
    return r.json();
  },
  getReplayDetail: async (replayId) => {
    const r = await fetch(`${API_BASE}:8102/replays/${replayId}/detail`);
    return r.json();
  },
  // File system (sandboxed)
  readLocalImage: (filePath) => {
    try {
      const normalized = path.normalize(filePath);
      if (!fs.existsSync(normalized)) return null;
      const buf = fs.readFileSync(normalized);
      const ext = path.extname(normalized).toLowerCase();
      const mime = ext === ".jpg" || ext === ".jpeg" ? "image/jpeg" : "image/png";
      return `data:${mime};base64,${buf.toString("base64")}`;
    } catch {
      return null;
    }
  },
  // Session management
  listSessions: async () => {
    const r = await fetch(`${ORCH}/sessions`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  createSession: async (spec) => {
    const r = await fetch(`${ORCH}/sessions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(spec) });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  attachAdapter: async (sessionId, body) => {
    const timeoutMs = body.adapter_type === "web" ? 12e4 : 3e4;
    const r = await fetch(`${ORCH}/sessions/${sessionId}/attach-adapter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs)
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  startSession: async (sessionId) => {
    const r = await fetch(`${ORCH}/sessions/${sessionId}/start`, { method: "POST" });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  pauseSession: async (sessionId) => {
    const r = await fetch(`${ORCH}/sessions/${sessionId}/pause`, { method: "POST" });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  resumeSession: async (sessionId) => {
    const r = await fetch(`${ORCH}/sessions/${sessionId}/resume`, { method: "POST" });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  stopSession: async (sessionId) => {
    const r = await fetch(`${ORCH}/sessions/${sessionId}/stop`, { method: "POST" });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  tickSession: async (sessionId) => {
    const r = await fetch(`${ORCH}/sessions/${sessionId}/tick`, { method: "POST" });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  getSessionStatus: async (sessionId) => {
    const r = await fetch(`${ORCH}/sessions/${sessionId}/status`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  getSession: async (sessionId) => {
    const r = await fetch(`${ORCH}/sessions/${sessionId}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  getSessionSteps: async (sessionId) => {
    const r = await fetch(`${ORCH}/sessions/${sessionId}/steps`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  // Profiles & health
  getProfileHealthSummary: async (profileId) => {
    const r = await fetch(`${API_BASE}:8104/profiles/${profileId}/health/summary`, {
      signal: AbortSignal.timeout(5e3)
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    return r.json();
  },
  getWindowsRpaPreview: async (adapterId) => {
    const r = await fetch(`${API_BASE}:8105/adapters/${adapterId}/preview`, {
      signal: AbortSignal.timeout(5e3)
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    return r.json();
  },
  // Diagnostics
  getAppVersion: () => {
    try {
      const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, "../package.json"), "utf-8"));
      return { version: pkg.version, name: pkg.name };
    } catch {
      return { version: "unknown", name: "Game Agent" };
    }
  },
  getLogDir: () => {
    const { app } = require("electron");
    return path.join(app.getPath("userData"), "logs");
  },
  openLogsFolder: () => {
    const { app, shell } = require("electron");
    const logDir = path.join(app.getPath("userData"), "logs");
    if (!fs.existsSync(logDir)) {
      fs.mkdirSync(logDir, { recursive: true });
    }
    shell.openPath(logDir);
  },
  // Update status (via IPC)
  onUpdateStatus: (callback) => {
    electron.ipcRenderer.on("update-status", (_event, status) => callback(status));
  }
});

/** Type declarations for the Electron preload bridge (window.unoApi). */
// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="./unoApi.d.ts" />

interface UnoApiBridge {
  healthCheck: (port: number) => Promise<Record<string, unknown>>;
  getConfig: () => Promise<Record<string, unknown>>;
  listModels: () => Promise<Array<Record<string, unknown>>>;
  listReplays: () => Promise<Array<Record<string, unknown>>>;
  getReplayDetail: (replayId: string) => Promise<Record<string, unknown>>;
  readLocalImage: (filePath: string) => string | null;
  listSessions: () => Promise<Array<Record<string, unknown>>>;
  createSession: (spec: Record<string, unknown>) => Promise<Record<string, unknown>>;
  attachAdapter: (sessionId: string, body: Record<string, unknown>) => Promise<Record<string, unknown>>;
  startSession: (sessionId: string) => Promise<Record<string, unknown>>;
  pauseSession: (sessionId: string) => Promise<Record<string, unknown>>;
  resumeSession: (sessionId: string) => Promise<Record<string, unknown>>;
  stopSession: (sessionId: string) => Promise<Record<string, unknown>>;
  tickSession: (sessionId: string) => Promise<Record<string, unknown>>;
  getSessionStatus: (sessionId: string) => Promise<Record<string, unknown>>;
  getSession: (sessionId: string) => Promise<Record<string, unknown>>;
  getSessionSteps: (sessionId: string) => Promise<Array<Record<string, unknown>>>;
  getProfileHealthSummary: (profileId: string) => Promise<Record<string, unknown>>;
  getWindowsRpaPreview: (adapterId: string) => Promise<Record<string, unknown>>;
  getAppVersion: () => { version: string; name: string };
  getLogDir: () => string;
  openLogsFolder: () => void;
  onUpdateStatus: (callback: (status: unknown) => void) => void;
}

declare global {
  interface Window {
    unoApi?: UnoApiBridge;
  }
}

export {};

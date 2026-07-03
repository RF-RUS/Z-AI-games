/** API client with Electron preload bridge + browser fetch fallback. */

const API_BASE = "http://127.0.0.1";
const ORCH = `${API_BASE}:8100`;
const ADAPTER_WEB = `${API_BASE}:8104`;
const ADAPTER_WIN = `${API_BASE}:8105`;
const FETCH_TIMEOUT_MS = 3000;
const WEB_ATTACH_TIMEOUT_MS = 120_000;

export type ServiceHealthState =
  | "loading"
  | "healthy"
  | "degraded"
  | "unhealthy"
  | "offline"
  | "error";

export interface ServiceHealthResponse {
  service: string;
  status: string;
  version?: string;
  details?: Record<string, unknown>;
}

export interface ProfileHealthSummary {
  profile_id: string;
  latest_status: string | null;
  latest_run_id: string | null;
  latest_timestamp_ms: number | null;
  latest_report_path: string | null;
  consecutive_degraded: number;
  consecutive_broken: number;
  fallback_usage_ratio: number;
  selector_drift_counts: Record<string, number>;
  runbook_path: string;
  active_alerts: Array<{ severity: string; alert_type: string; message: string }>;
}

export interface SessionMetrics {
  total_steps: number;
  successful_steps: number;
  failed_steps: number;
  retries: number;
  fallbacks?: number;
}

export interface WindowCandidate {
  handle: number;
  title: string;
  pid: number | null;
  process_name?: string | null;
  class_name?: string | null;
  is_visible?: boolean;
  is_focused?: boolean;
  is_browser_host?: boolean;
  attach_warning?: string | null;
}

export interface CdpTab {
  title: string;
  url: string;
  id: string;
  web_socket_debug_url?: string;
}

export interface CdpCheckResult {
  available: boolean;
  browser: string | null;
  cdp_url: string;
}

export interface OperatorPreviewState {
  adapter_id: string;
  session_id: string;
  status: string;
  automation_active: boolean;
  attach_warning?: string | null;
  uia_diagnostics?: {
    node_count: number;
    named_node_count: number;
    document_actionable_count: number;
    actionable_control_count: number;
    button_count: number;
    document_count: number;
    sparse_tree: boolean;
    canvas_like: boolean;
    uia_actionable: boolean;
    message: string;
    recommended_action: string;
  } | null;
  attachment?: {
    window_title: string;
    bounds?: { left: number; top: number; right: number; bottom: number };
    backend: string;
    window_handle?: number | null;
    expected_title?: string | null;
    live_title?: string | null;
    is_browser_host?: boolean;
    attach_warning?: string | null;
  };
  live_frame?: { data_base64?: string; path: string };
  frame_kind?: "live" | "synthetic" | "none";
  current_action?: string | null;
  planned_action?: string | null;
  current_target?: { label: string; confidence: number; click_point?: { x: number; y: number } };
  confidence: number;
  recent_actions: Array<{
    action_id: string;
    domain_action: string;
    selector_key?: string;
    success: boolean;
    uncertain: boolean;
    click_point?: { x: number; y: number };
  }>;
  message: string;
}

export interface WebStartupDiagnostics {
  failed_stage?: string | null;
  error_message?: string;
  stage_timings_ms?: Record<string, number>;
  screenshot_path?: string | null;
  trace_path?: string | null;
  log_path?: string | null;
  url?: string | null;
  profile_id?: string | null;
  page_goto?: {
    requested_url?: string;
    final_url?: string | null;
    page_title?: string | null;
    document_ready_state?: string | null;
    content_preview?: string | null;
    wait_until?: string;
    browser_launch_mode?: string;
    navigation_responses?: Array<{ url: string; status?: number | null; ok?: boolean }>;
    request_failures?: Array<{ url: string; failure?: string; resource_type?: string }>;
    console_errors?: string[];
    network_reachability?: {
      reachable?: boolean;
      status_code?: number | null;
      elapsed_ms?: number;
      error?: string | null;
    } | null;
  } | null;
}

export interface SessionDetail {
  session_id: string;
  flow_state: string;
  phase: string;
  game_id?: string;
  error?: string;
  attach_startup_diagnostics?: WebStartupDiagnostics | null;
  automatic: boolean;
  config?: {
    adapter_type?: string;
    adapter_id?: string;
    strategy_id?: string;
  };
  adapter_bindings: Array<{
    adapter_type: string;
    adapter_id?: string;
    attached: boolean;
    profile_id?: string | null;
    healthy: boolean;
    last_error?: string | null;
  }>;
  metrics: SessionMetrics;
}

export interface OrchestratorStatusResponse {
  session_id: string;
  flow_state: string;
  phase: string;
  error?: string;
  attach_startup_diagnostics?: WebStartupDiagnostics | null;
  last_recovery?: {
    error_class?: string;
    action?: string;
    reason?: string;
    retry_after_ms?: number;
  };
  metrics?: SessionMetrics;
  strategy_snapshot?: {
    goal?: string;
    detected_state?: string;
    hypothesis?: string;
    next_action?: string;
    why_action?: string;
    confidence?: number;
    blocked_reason?: string;
    last_executed?: string;
    game_type?: string;
    verification?: {
      delivery_status?: string;
      outcome_status?: string;
      expected_transition?: string;
      observed_transition?: string;
      action_category?: string;
      action_family?: string;
      observability_signals?: string[];
      evidence_strength?: string;
      summary?: string;
    };
  };
}

export interface FlowStep {
  step_name: string;
  correlation_id: string;
  flow_state: string;
  result: {
    success: boolean;
    error?: string;
    latency_ms: number;
    error_class?: string;
    retries?: number;
  };
}

const ORCH_TIMEOUT_MS = 5000;
const WINDOWS_ATTACH_TIMEOUT_MS = 60_000;

async function fetchJson<T>(url: string, init?: RequestInit, timeoutMs = FETCH_TIMEOUT_MS): Promise<T> {
  const r = await fetch(url, {
    ...init,
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text?.trim() || `HTTP ${r.status}`);
  }
  return r.json() as Promise<T>;
}

async function orchFetch<T>(path: string, init?: RequestInit): Promise<T> {
  return fetchJson<T>(`${ORCH}${path}`, init, ORCH_TIMEOUT_MS);
}

function parseSessionList(data: unknown): SessionDetail[] {
  if (!Array.isArray(data)) {
    throw new Error("Invalid sessions response: expected array");
  }
  return data as SessionDetail[];
}

function parseFlowSteps(data: unknown): FlowStep[] {
  if (!Array.isArray(data)) {
    throw new Error("Invalid steps response: expected array");
  }
  return data as FlowStep[];
}

export class AttachAdapterFailedError extends Error {
  session?: SessionDetail;

  constructor(message: string, session?: SessionDetail) {
    super(message);
    this.name = "AttachAdapterFailedError";
    this.session = session;
  }
}

export function parseAttachAdapterFailure(raw: string): { message: string; session?: SessionDetail } {
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    const detail = parsed.detail;
    if (typeof detail === "object" && detail !== null && "session" in detail) {
      const payload = detail as { message?: string; session?: SessionDetail };
      return {
        message: payload.message || "Attach failed",
        session: payload.session,
      };
    }
    if (typeof detail === "string") {
      return { message: detail };
    }
  } catch {
    // fall through to raw text
  }
  return { message: raw.trim() || "Attach failed" };
}

export function hasElectronBridge(): boolean {
  return typeof window.unoApi?.healthCheck === "function";
}

export async function checkServiceHealth(port: number): Promise<ServiceHealthState> {
  try {
    let data: ServiceHealthResponse;
    if (window.unoApi?.healthCheck) {
      data = await window.unoApi.healthCheck(port);
    } else {
      data = await fetchJson<ServiceHealthResponse>(`${API_BASE}:${port}/health`);
    }
    const status = data?.status;
    if (status === "healthy" || status === "degraded" || status === "unhealthy") {
      return status;
    }
    return "error";
  } catch {
    return "offline";
  }
}

export async function getProfileHealthSummary(
  profileId: string,
): Promise<ProfileHealthSummary> {
  if (window.unoApi?.getProfileHealthSummary) {
    return (await window.unoApi.getProfileHealthSummary(profileId)) as unknown as ProfileHealthSummary;
  }
  return fetchJson<ProfileHealthSummary>(
    `${ADAPTER_WEB}/profiles/${profileId}/health/summary`,
  );
}

export async function isOrchestratorOnline(): Promise<boolean> {
  const state = await checkServiceHealth(8100);
  return state === "healthy" || state === "degraded" || state === "unhealthy";
}

export async function isAdapterWindowsOnline(): Promise<boolean> {
  const state = await checkServiceHealth(8105);
  return state === "healthy" || state === "degraded" || state === "unhealthy";
}

export async function getWindowsRpaPreview(adapterId: string): Promise<OperatorPreviewState> {
  if (window.unoApi?.getWindowsRpaPreview) {
    return (await window.unoApi.getWindowsRpaPreview(adapterId)) as OperatorPreviewState;
  }
  return fetchJson<OperatorPreviewState>(`${ADAPTER_WIN}/adapters/${adapterId}/preview`, undefined, 5000);
}

export async function listWindowsCandidates(): Promise<WindowCandidate[]> {
  return fetchJson<WindowCandidate[]>(`${ADAPTER_WIN}/windows/candidates`, undefined, 8000);
}

export async function isAdapterWebOnline(): Promise<boolean> {
  const state = await checkServiceHealth(8104);
  return state === "healthy" || state === "degraded" || state === "unhealthy";
}

export async function listModels(): Promise<Array<{ model_id: string; display_name: string; enabled: boolean }>> {
  if (window.unoApi?.listModels) {
    return (await window.unoApi.listModels()) as Array<{ model_id: string; display_name: string; enabled: boolean }>;
  }
  return fetchJson(`${API_BASE}:8110/models`);
}

export async function createSession(spec: Record<string, unknown>): Promise<Record<string, unknown>> {
  if (window.unoApi?.createSession) {
    return window.unoApi.createSession(spec);
  }
  return fetchJson(`${ORCH}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  });
}

export async function attachAdapter(sessionId: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
  if (window.unoApi?.attachAdapter) {
    try {
      return await window.unoApi.attachAdapter(sessionId, body);
    } catch (err) {
      if (err instanceof Error) {
        const parsed = parseAttachAdapterFailure(err.message);
        throw new AttachAdapterFailedError(parsed.message, parsed.session);
      }
      throw err;
    }
  }
  const timeoutMs = body.adapter_type === "web" ? WEB_ATTACH_TIMEOUT_MS : WINDOWS_ATTACH_TIMEOUT_MS;
  try {
    const r = await fetch(`${ORCH}/sessions/${sessionId}/attach-adapter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!r.ok) {
      const text = await r.text();
      const parsed = parseAttachAdapterFailure(text);
      throw new AttachAdapterFailedError(parsed.message, parsed.session);
    }
    return r.json() as Promise<Record<string, unknown>>;
  } catch (err) {
    if (err instanceof AttachAdapterFailedError) {
      throw err;
    }
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new Error(
        `Attach request timed out after ${timeoutMs}ms (adapter=${body.adapter_type ?? "unknown"})`,
      );
    }
    throw err;
  }
}

export async function startSession(sessionId: string): Promise<Record<string, unknown>> {
  if (window.unoApi?.startSession) {
    return (await window.unoApi.startSession(sessionId)) as Record<string, unknown>;
  }
  return orchFetch(`/sessions/${sessionId}/start`, { method: "POST" });
}

export async function listSessions(): Promise<SessionDetail[]> {
  const data = window.unoApi?.listSessions
    ? await window.unoApi.listSessions()
    : await orchFetch<unknown>("/sessions");
  return parseSessionList(data);
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  if (window.unoApi?.getSession) {
    return (await window.unoApi.getSession(sessionId)) as SessionDetail;
  }
  return orchFetch<SessionDetail>(`/sessions/${sessionId}`);
}

export async function getSessionStatus(sessionId: string): Promise<OrchestratorStatusResponse> {
  if (window.unoApi?.getSessionStatus) {
    return (await window.unoApi.getSessionStatus(sessionId)) as OrchestratorStatusResponse;
  }
  return orchFetch<OrchestratorStatusResponse>(`/sessions/${sessionId}/status`);
}

export async function getSessionSteps(sessionId: string): Promise<FlowStep[]> {
  const data = window.unoApi?.getSessionSteps
    ? await window.unoApi.getSessionSteps(sessionId)
    : await orchFetch<unknown>(`/sessions/${sessionId}/steps`);
  return parseFlowSteps(data);
}

export async function pauseSession(sessionId: string): Promise<Record<string, unknown>> {
  if (window.unoApi?.pauseSession) {
    return (await window.unoApi.pauseSession(sessionId)) as Record<string, unknown>;
  }
  return orchFetch(`/sessions/${sessionId}/pause`, { method: "POST" });
}

export async function resumeSession(sessionId: string): Promise<Record<string, unknown>> {
  if (window.unoApi?.resumeSession) {
    return (await window.unoApi.resumeSession(sessionId)) as Record<string, unknown>;
  }
  return orchFetch(`/sessions/${sessionId}/resume`, { method: "POST" });
}

export async function stopSession(sessionId: string): Promise<Record<string, unknown>> {
  if (window.unoApi?.stopSession) {
    return (await window.unoApi.stopSession(sessionId)) as Record<string, unknown>;
  }
  return orchFetch(`/sessions/${sessionId}/stop`, { method: "POST" });
}

export async function tickSession(sessionId: string): Promise<Record<string, unknown>> {
  if (window.unoApi?.tickSession) {
    return (await window.unoApi.tickSession(sessionId)) as Record<string, unknown>;
  }
  return orchFetch(`/sessions/${sessionId}/tick`, { method: "POST" });
}

const ADAPTER_WEB_BASE = "http://127.0.0.1:8104";

export async function checkCdpPort(cdpUrl: string = "http://127.0.0.1:9222"): Promise<CdpCheckResult> {
  const r = await fetch(`${ADAPTER_WEB_BASE}/cdp/check?cdp_url=${encodeURIComponent(cdpUrl)}`);
  return r.json() as Promise<CdpCheckResult>;
}

export async function listCdpTabs(cdpUrl: string = "http://127.0.0.1:9222"): Promise<CdpTab[]> {
  const r = await fetch(`${ADAPTER_WEB_BASE}/cdp/tabs?cdp_url=${encodeURIComponent(cdpUrl)}`);
  return r.json() as Promise<CdpTab[]>;
}

export interface LaunchChromeResult {
  success: boolean;
  cdp_url?: string;
  already_running?: boolean;
  browser?: string;
  error?: string;
}

export interface ProfileCompatibility {
  profile_id: string;
  display_name: string;
  launch_url: string;
  allowed_domains: string[];
  game_type: string | null;
}

export async function launchDebugChrome(options?: {
  cdp_port?: number;
  url?: string;
}): Promise<LaunchChromeResult> {
  const r = await fetch(`${ADAPTER_WEB_BASE}/cdp/launch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options || {}),
  });
  return r.json() as Promise<LaunchChromeResult>;
}

export async function getProfileCompatibility(profileId: string): Promise<ProfileCompatibility | null> {
  try {
    const r = await fetch(`${ADAPTER_WEB_BASE}/profiles/${encodeURIComponent(profileId)}/compatibility`);
    if (!r.ok) return null;
    return r.json() as Promise<ProfileCompatibility>;
  } catch {
    return null;
  }
}

export interface TraceSession {
  session_id: string;
  step_count: number;
  latest_phase: string | null;
  latest_meta: Record<string, unknown> | null;
}

export interface TraceStep {
  step: number;
  phase: string;
  path: string;
  step_dir_name: string;
  screenshots: string[];
  meta: Record<string, unknown> | null;
}

export async function listTraceSessions(): Promise<TraceSession[]> {
  try {
    const r = await fetch(`${ADAPTER_WEB_BASE}/trace/sessions`);
    if (!r.ok) return [];
    return r.json() as Promise<TraceSession[]>;
  } catch {
    return [];
  }
}

export async function listTraceSteps(sessionId: string): Promise<TraceStep[]> {
  try {
    const r = await fetch(`${ADAPTER_WEB_BASE}/trace/${encodeURIComponent(sessionId)}/steps`);
    if (!r.ok) return [];
    return r.json() as Promise<TraceStep[]>;
  } catch {
    return [];
  }
}

export function traceFrameUrl(sessionId: string, stepDir: string, filename: string = "frame.png"): string {
  return `${ADAPTER_WEB_BASE}/trace/${encodeURIComponent(sessionId)}/${encodeURIComponent(stepDir)}/${filename}`;
}

export function traceLatestFrameUrl(sessionId: string): string {
  return `${ADAPTER_WEB_BASE}/trace/${encodeURIComponent(sessionId)}/latest-frame`;
}

export async function traceLatestMeta(sessionId: string): Promise<Record<string, unknown> | null> {
  try {
    const r = await fetch(`${ADAPTER_WEB_BASE}/trace/${encodeURIComponent(sessionId)}/latest-meta`);
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export interface AttachRecoveryInfo {
  error_class?: string;
  action?: string;
  reason?: string;
}

export interface NetworkReachabilityCheck {
  url?: string;
  reachable?: boolean;
  status_code?: number | null;
  final_url?: string | null;
  elapsed_ms?: number;
  error?: string | null;
  content_length?: number | null;
}

export interface PageGotoDiagnostics {
  requested_url?: string;
  final_url?: string | null;
  page_title?: string | null;
  document_ready_state?: string | null;
  content_preview?: string | null;
  content_length?: number | null;
  wait_until?: string;
  browser_launch_mode?: string;
  navigation_responses?: Array<{ url: string; status?: number | null; ok?: boolean }>;
  request_failures?: Array<{ url: string; failure?: string; resource_type?: string }>;
  console_errors?: string[];
  network_reachability?: NetworkReachabilityCheck | null;
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
  page_goto?: PageGotoDiagnostics | null;
}

export interface SessionAttachDiagnosticsView {
  errorText: string;
  startupStage: string | null;
  stageTimings: Array<{ stage: string; elapsedMs: number }>;
  artifactPaths: string[];
  pageGotoLines: string[];
}

export function parsePlaywrightStartupStage(error?: string | null): string | null {
  if (!error) return null;
  const match = error.match(/stage=([a-z_]+)/i);
  return match?.[1] ?? null;
}

export function resolveStartupStage(
  error?: string | null,
  diagnostics?: WebStartupDiagnostics | null,
): string | null {
  return diagnostics?.failed_stage ?? parsePlaywrightStartupStage(error);
}

export function resolveStartupErrorText(
  error?: string | null,
  diagnostics?: WebStartupDiagnostics | null,
  recovery?: AttachRecoveryInfo | null,
): string {
  return diagnostics?.error_message || error || recovery?.reason || "Attach failed";
}

export function formatPageGotoDiagnostics(
  diagnostics?: WebStartupDiagnostics | null,
): string[] {
  const pg = diagnostics?.page_goto;
  if (!pg) return [];
  const lines: string[] = [];
  if (pg.browser_launch_mode) lines.push(`Browser: ${pg.browser_launch_mode}`);
  if (pg.wait_until) lines.push(`wait_until: ${pg.wait_until}`);
  if (pg.final_url) lines.push(`Final URL: ${pg.final_url}`);
  if (pg.page_title) lines.push(`Title: ${pg.page_title}`);
  if (pg.document_ready_state) lines.push(`readyState: ${pg.document_ready_state}`);
  const reach = pg.network_reachability;
  if (reach) {
    lines.push(
      `HTTP reachability: ${reach.reachable ? "ok" : "failed"}`
        + (reach.status_code != null ? ` (${reach.status_code})` : "")
        + (reach.elapsed_ms != null ? ` ${reach.elapsed_ms}ms` : "")
        + (reach.error ? ` — ${reach.error}` : ""),
    );
  }
  if (pg.request_failures?.length) {
    lines.push(`Request failures (${pg.request_failures.length}):`);
    pg.request_failures.slice(0, 5).forEach((f) => {
      lines.push(`  • ${f.resource_type || "request"} ${f.url} — ${f.failure || "failed"}`);
    });
  }
  if (pg.navigation_responses?.length) {
    const chain = pg.navigation_responses
      .slice(-5)
      .map((r) => `${r.status ?? "?"} ${r.url}`)
      .join(" → ");
    lines.push(`Response chain: ${chain}`);
  }
  if (pg.console_errors?.length) {
    lines.push(`Console (${pg.console_errors.length}): ${pg.console_errors.slice(0, 3).join(" | ")}`);
  }
  if (pg.content_preview) {
    lines.push(`Content preview: ${pg.content_preview.slice(0, 240)}${pg.content_preview.length > 240 ? "…" : ""}`);
  }
  return lines;
}

export function buildSessionAttachDiagnosticsView(
  error?: string | null,
  diagnostics?: WebStartupDiagnostics | null,
  recovery?: AttachRecoveryInfo | null,
): SessionAttachDiagnosticsView {
  const errorText = resolveStartupErrorText(error, diagnostics, recovery);
  const stageTimings = Object.entries(diagnostics?.stage_timings_ms ?? {})
    .map(([stage, elapsedMs]) => ({ stage, elapsedMs }))
    .sort((a, b) => a.stage.localeCompare(b.stage));
  const artifactPaths = [diagnostics?.screenshot_path, diagnostics?.trace_path, diagnostics?.log_path].filter(
    (path): path is string => Boolean(path),
  );
  return {
    errorText,
    startupStage: resolveStartupStage(error, diagnostics),
    stageTimings,
    artifactPaths,
    pageGotoLines: formatPageGotoDiagnostics(diagnostics),
  };
}

export function formatAttachFailureSummary(
  error?: string | null,
  recovery?: AttachRecoveryInfo | null,
  diagnostics?: WebStartupDiagnostics | null,
): string {
  return resolveStartupErrorText(error, diagnostics, recovery);
}

export function shouldHideMockRecoveryHint(
  adapterType?: string,
  recovery?: AttachRecoveryInfo | null,
): boolean {
  return adapterType === "web" && recovery?.action === "stop";
}

export function formatRecoveryLabel(
  adapterType: string | undefined,
  recovery: AttachRecoveryInfo | null | undefined,
): string {
  if (!recovery) return "";
  if (shouldHideMockRecoveryHint(adapterType, recovery)) {
    return "Recovery: stop (web attach failed)";
  }
  return `Recovery: ${recovery.action ?? "unknown"}`;
}

export function shouldShowAttachFailurePanel(
  error?: string | null,
  diagnostics?: WebStartupDiagnostics | null,
  recovery?: AttachRecoveryInfo | null,
  adapterType?: string,
): boolean {
  if (diagnostics) return true;
  if (error?.includes("Playwright startup failed")) return true;
  if (error?.includes("web attach failed")) return true;
  return false;
}

export function resolveCycleErrorText(
  error?: string | null,
  recovery?: AttachRecoveryInfo | null,
  failedStep?: string | null,
): string {
  const base = error?.trim() || recovery?.reason?.trim() || "Flow cycle failed";
  return failedStep ? `${base} (step: ${failedStep})` : base;
}

export function shouldShowCycleFailurePanel(
  flowState?: string,
  error?: string | null,
  recovery?: AttachRecoveryInfo | null,
  diagnostics?: WebStartupDiagnostics | null,
): boolean {
  if (diagnostics) return false;
  if (shouldShowAttachFailurePanel(error, diagnostics, recovery)) return false;
  return flowState === "error" && Boolean(error?.trim() || recovery?.reason?.trim());
}

export function buildAttachFailurePanelContent(
  error?: string | null,
  diagnostics?: WebStartupDiagnostics | null,
  recovery?: AttachRecoveryInfo | null,
): {
  summary: string;
  startupStage: string | null;
  stageTimingsText: string;
  artifactPaths: string[];
  pageGotoLines: string[];
} {
  const view = buildSessionAttachDiagnosticsView(error, diagnostics, recovery);
  return {
    summary: formatAttachFailureSummary(error, recovery, diagnostics),
    startupStage: view.startupStage,
    stageTimingsText: formatStageTimings(diagnostics),
    artifactPaths: view.artifactPaths,
    pageGotoLines: view.pageGotoLines,
  };
}

export function formatStageTimings(
  diagnostics?: WebStartupDiagnostics | null,
): string {
  const view = buildSessionAttachDiagnosticsView(undefined, diagnostics);
  if (view.stageTimings.length === 0) return "";
  return view.stageTimings.map(({ stage, elapsedMs }) => `${stage}: ${elapsedMs}ms`).join(" · ");
}

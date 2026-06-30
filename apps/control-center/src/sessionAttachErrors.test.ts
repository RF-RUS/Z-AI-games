import { describe, expect, it } from "vitest";
import {
  buildAttachFailurePanelContent,
  buildSessionAttachDiagnosticsView,
  formatAttachFailureSummary,
  formatPageGotoDiagnostics,
  formatRecoveryLabel,
  formatStageTimings,
  parsePlaywrightStartupStage,
  resolveCycleErrorText,
  resolveStartupStage,
  shouldShowAttachFailurePanel,
  shouldShowCycleFailurePanel,
} from "./sessionAttachErrors";

describe("sessionAttachErrors", () => {
  const diagnostics = {
    failed_stage: "page_goto",
    error_message: "Playwright startup failed at stage=page_goto (60000ms): timeout",
    stage_timings_ms: {
      browser_launch: 1200,
      context_page: 80,
      page_goto: 60000,
    },
    screenshot_path: "artifacts/sess/attach-failure-page_goto.png",
    log_path: "artifacts/sess/startup-failure-page_goto.json",
  };

  it("uses structured diagnostics stage over parsed error text", () => {
    expect(resolveStartupStage("some other error", diagnostics)).toBe("page_goto");
  });

  it("builds UI view with exact backend message and stage field", () => {
    const view = buildSessionAttachDiagnosticsView(undefined, diagnostics);
    expect(view.startupStage).toBe("page_goto");
    expect(view.errorText).toContain("timeout");
    expect(view.stageTimings).toEqual([
      { stage: "browser_launch", elapsedMs: 1200 },
      { stage: "context_page", elapsedMs: 80 },
      { stage: "page_goto", elapsedMs: 60000 },
    ]);
    expect(view.artifactPaths).toContain(diagnostics.screenshot_path);
  });

  it("prefers structured error message in summary", () => {
    expect(
      formatAttachFailureSummary("generic", { reason: "ignored" }, diagnostics),
    ).toContain("page_goto");
  });

  it("parses playwright startup stage from backend message fallback", () => {
    expect(
      parsePlaywrightStartupStage(
        "Playwright startup failed at stage=browser_launch (1200ms): launch failed",
      ),
    ).toBe("browser_launch");
  });

  it("formats stage timings for session panel", () => {
    expect(formatStageTimings(diagnostics)).toContain("page_goto: 60000ms");
  });

  it("shows web stop recovery without mock hint", () => {
    expect(formatRecoveryLabel("web", { action: "stop" })).toContain("web attach failed");
  });

  it("shows attach failure panel only for attach diagnostics or messages", () => {
    expect(
      shouldShowAttachFailurePanel(undefined, null, { action: "stop", reason: "unrecoverable: ReadTimeout" }, "web"),
    ).toBe(false);
    expect(
      shouldShowAttachFailurePanel("Playwright startup failed at stage=page_goto", null, null, "web"),
    ).toBe(true);
    expect(shouldShowAttachFailurePanel(undefined, diagnostics, null, "web")).toBe(true);
  });

  it("shows cycle failure panel for post-attach flow errors", () => {
    expect(
      shouldShowCycleFailurePanel(
        "error",
        "ReadTimeout",
        { action: "stop", reason: "unrecoverable: ReadTimeout" },
        null,
      ),
    ).toBe(true);
    expect(
      shouldShowCycleFailurePanel("error", "", { action: "stop", reason: "unrecoverable: ReadTimeout" }, null),
    ).toBe(true);
  });

  it("formats cycle error with failed step", () => {
    expect(resolveCycleErrorText("ReadTimeout", null, "observe")).toContain("observe");
  });

  it("renders exact stage, message, timings, and artifacts for failed web attach", () => {
    const panel = buildAttachFailurePanelContent(
      "Playwright startup failed at stage=page_goto (60000ms): timeout",
      diagnostics,
      { action: "stop", reason: "Playwright startup failed at stage=page_goto (60000ms): timeout" },
    );
    expect(panel.summary).toContain("page_goto");
    expect(panel.summary).toContain("timeout");
    expect(panel.startupStage).toBe("page_goto");
    expect(panel.stageTimingsText).toContain("page_goto: 60000ms");
    expect(panel.artifactPaths).toContain(diagnostics.screenshot_path);
  });

  it("formats page_goto navigation diagnostics for UI", () => {
    const lines = formatPageGotoDiagnostics({
      failed_stage: "page_goto",
      page_goto: {
        wait_until: "commit",
        browser_launch_mode: "bundled_chromium",
        final_url: "https://scuffeduno.online/",
        page_title: "Scuffed Uno",
        document_ready_state: "interactive",
        network_reachability: { reachable: true, status_code: 200, elapsed_ms: 800 },
        request_failures: [{ url: "https://cdn.example/app.js", failure: "net::ERR_BLOCKED_BY_CLIENT", resource_type: "script" }],
        navigation_responses: [{ url: "https://scuffeduno.online/", status: 200, ok: true }],
        console_errors: ["error: WebGL context lost"],
      },
    });
    expect(lines.some((line) => line.includes("wait_until: commit"))).toBe(true);
    expect(lines.some((line) => line.includes("Final URL"))).toBe(true);
    expect(lines.some((line) => line.includes("HTTP reachability: ok"))).toBe(true);
    expect(lines.some((line) => line.includes("Request failures"))).toBe(true);
  });
});

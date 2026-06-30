import { describe, expect, it } from "vitest";
import { parseAttachAdapterFailure } from "./unoApiClient";

describe("parseAttachAdapterFailure", () => {
  it("extracts session diagnostics from structured attach 502 payload", () => {
    const raw = JSON.stringify({
      detail: {
        message: "Playwright startup failed at stage=page_goto (60000ms): timeout",
        session: {
          session_id: "sess-1",
          flow_state: "error",
          error: "Playwright startup failed at stage=page_goto (60000ms): timeout",
          attach_startup_diagnostics: {
            failed_stage: "page_goto",
            error_message: "Playwright startup failed at stage=page_goto (60000ms): timeout",
            stage_timings_ms: { page_goto: 60000 },
          },
          adapter_bindings: [],
          metrics: { total_steps: 0, successful_steps: 0, failed_steps: 0, retries: 0 },
        },
      },
    });

    const parsed = parseAttachAdapterFailure(raw);

    expect(parsed.message).toContain("page_goto");
    expect(parsed.session?.attach_startup_diagnostics?.failed_stage).toBe("page_goto");
  });
});

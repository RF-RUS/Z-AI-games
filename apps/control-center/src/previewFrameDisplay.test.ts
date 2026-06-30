import { describe, expect, it } from "vitest";
import { resolvePreviewFrameKind, resolveWindowsPreviewDisplay } from "./previewFrameDisplay";
import type { OperatorPreviewState } from "./unoApiClient";

const base: OperatorPreviewState = {
  adapter_id: "a1",
  session_id: "s1",
  status: "ready",
  automation_active: false,
  confidence: 0,
  recent_actions: [],
  message: "",
};

describe("resolvePreviewFrameKind", () => {
  it("uses explicit frame_kind when present", () => {
    expect(resolvePreviewFrameKind({ ...base, frame_kind: "synthetic" })).toBe("synthetic");
    expect(resolvePreviewFrameKind({ ...base, frame_kind: "live" })).toBe("live");
    expect(resolvePreviewFrameKind({ ...base, frame_kind: "none" })).toBe("none");
  });

  it("does not infer live for mock backend with frame data when frame_kind missing", () => {
    const kind = resolvePreviewFrameKind({
      ...base,
      attachment: { window_title: "UNO Mock Test Target", backend: "mock" },
      live_frame: { path: "/tmp/x.png", data_base64: "abc" },
    });
    expect(kind).toBe("synthetic");
  });

  it("infers live for non-mock backend with frame data when frame_kind missing", () => {
    const kind = resolvePreviewFrameKind({
      ...base,
      attachment: { window_title: "UNO", backend: "uia" },
      live_frame: { path: "/tmp/x.png", data_base64: "abc" },
    });
    expect(kind).toBe("live");
  });
});

describe("resolveWindowsPreviewDisplay", () => {
  it("shows synthetic frame for mock backend with frame_kind synthetic", () => {
    const display = resolveWindowsPreviewDisplay({
      ...base,
      frame_kind: "synthetic",
      attachment: { window_title: "UNO Mock Test Target", backend: "mock" },
      live_frame: { path: "/tmp/x.png", data_base64: "abc" },
    });
    expect(display.frameKind).toBe("synthetic");
    expect(display.imageSrc).toContain("abc");
    expect(display.caption).toMatch(/Synthetic schematic/i);
    expect(display.emptyMessage).toBe("");
    expect(display.backendLabel).toMatch(/valid deterministic mode/i);
    expect(display.emptyMessage).not.toMatch(/No live frame/i);
  });

  it("does not show live caption when frame_kind is none despite stale frame data", () => {
    const display = resolveWindowsPreviewDisplay({
      ...base,
      frame_kind: "none",
      attachment: { window_title: "UNO", backend: "uia" },
      live_frame: { path: "/tmp/stale.png", data_base64: "stale" },
    });
    expect(display.frameKind).toBe("none");
    expect(display.imageSrc).toBeNull();
    expect(display.emptyMessage).toMatch(/Waiting for live desktop capture/i);
  });

  it("shows waiting message for live backend without frame", () => {
    const display = resolveWindowsPreviewDisplay({
      ...base,
      frame_kind: "none",
      attachment: { window_title: "UNO", backend: "uia" },
    });
    expect(display.imageSrc).toBeNull();
    expect(display.emptyMessage).toMatch(/Waiting for live desktop capture/i);
  });

  it("shows mock generating message when mock has no frame yet", () => {
    const display = resolveWindowsPreviewDisplay({
      ...base,
      frame_kind: "none",
      attachment: { window_title: "UNO Mock Test Target", backend: "mock" },
    });
    expect(display.emptyMessage).toMatch(/synthetic preview is being generated/i);
    expect(display.emptyMessage).not.toMatch(/No live frame/i);
  });
});

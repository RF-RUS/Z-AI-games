import type { OperatorPreviewState } from "./unoApiClient";

export type PreviewFrameKind = "live" | "synthetic" | "none";

export type PreviewFrameDisplay = {
  frameKind: PreviewFrameKind;
  imageSrc: string | null;
  caption: string;
  emptyMessage: string;
  modeLabel: string;
  backendLabel: string;
};

/** Resolve frame kind from contract field; legacy fallback uses backend, never assumes live for mock. */
export function resolvePreviewFrameKind(preview: OperatorPreviewState): PreviewFrameKind {
  const kind = preview.frame_kind;
  if (kind === "live" || kind === "synthetic" || kind === "none") {
    return kind;
  }
  if (!preview.live_frame?.data_base64) {
    return "none";
  }
  return preview.attachment?.backend === "mock" ? "synthetic" : "live";
}

export function resolveWindowsPreviewDisplay(preview: OperatorPreviewState): PreviewFrameDisplay {
  const backend = preview.attachment?.backend ?? "unknown";
  const frameKind = resolvePreviewFrameKind(preview);
  const hasImage = frameKind !== "none" && Boolean(preview.live_frame?.data_base64);

  const imageSrc = hasImage
    ? `data:image/png;base64,${preview.live_frame!.data_base64}`
    : null;

  const modeLabel =
    frameKind === "synthetic"
      ? "Synthetic mock preview"
      : frameKind === "live"
        ? "Live desktop capture"
        : backend === "mock"
          ? "Mock attended mode"
          : "Attended mode";

  const backendLabel =
    backend === "mock"
      ? "mock (valid deterministic mode — no desktop capture)"
      : backend;

  if (frameKind === "synthetic" && imageSrc) {
    return {
      frameKind,
      imageSrc,
      caption: "Synthetic schematic from mock UIA tree — not a desktop screenshot",
      emptyMessage: "",
      modeLabel,
      backendLabel,
    };
  }

  if (frameKind === "live" && imageSrc) {
    return {
      frameKind,
      imageSrc,
      caption: "Live window capture from pywinauto",
      emptyMessage: "",
      modeLabel,
      backendLabel,
    };
  }

  if (backend === "mock") {
    return {
      frameKind: "none",
      imageSrc: null,
      caption: "",
      emptyMessage: "Mock backend active — synthetic preview is being generated",
      modeLabel,
      backendLabel,
    };
  }

  return {
    frameKind: "none",
    imageSrc: null,
    caption: "",
    emptyMessage: "Waiting for live desktop capture…",
    modeLabel,
    backendLabel,
  };
}

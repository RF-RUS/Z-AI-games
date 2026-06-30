import { useEffect, useState } from "react";
import {
  getWindowsRpaPreview,
  isAdapterWindowsOnline,
  OperatorPreviewState,
} from "./unoApiClient";
import { resolveWindowsPreviewDisplay } from "./previewFrameDisplay";

const STATUS_CLASS: Record<string, string> = {
  ready: "health-ok",
  attached: "health-ok",
  acting: "flow-attaching",
  verifying: "flow-attaching",
  uncertain: "health-warn",
  failed: "health-bad",
  offline: "health-bad",
  stopped: "flow-idle",
  paused: "flow-paused",
};

type Props = {
  adapterId: string | null;
  sessionId?: string | null;
};

export default function WindowsRpaPanel({ adapterId, sessionId }: Props) {
  const [preview, setPreview] = useState<OperatorPreviewState | null>(null);
  const [panelState, setPanelState] = useState<"loading" | "offline" | "no_adapter" | "ready" | "error">("loading");
  const [errorDetail, setErrorDetail] = useState<string | null>(null);

  useEffect(() => {
    if (!adapterId) {
      setPanelState("no_adapter");
      setPreview(null);
      return;
    }

    let cancelled = false;
    const load = async () => {
      setPanelState("loading");
      try {
        const online = await isAdapterWindowsOnline();
        if (cancelled) return;
        if (!online) {
          setPanelState("offline");
          setPreview(null);
          return;
        }
        const p = await getWindowsRpaPreview(adapterId);
        if (cancelled) return;
        setPreview(p);
        setPanelState("ready");
        setErrorDetail(null);
      } catch (e) {
        if (cancelled) return;
        setPanelState("error");
        setErrorDetail(e instanceof Error ? e.message : String(e));
      }
    };

    load();
    const id = setInterval(load, 2000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [adapterId, sessionId]);

  if (panelState === "no_adapter") {
    return (
      <div className="card windows-rpa">
        <h2>Windows RPA</h2>
        <p className="muted">No Windows adapter attached. Start a session with Adapter = Windows.</p>
      </div>
    );
  }

  if (panelState === "loading") {
    return (
      <div className="card windows-rpa">
        <h2>Windows RPA</h2>
        <p className="muted">Loading preview…</p>
      </div>
    );
  }

  if (panelState === "offline") {
    return (
      <div className="card windows-rpa">
        <h2>Windows RPA</h2>
        <p className="muted">Windows adapter offline (port 8105). Run <code>.\scripts\dev-backend.ps1</code></p>
      </div>
    );
  }

  if (panelState === "error") {
    return (
      <div className="card windows-rpa">
        <h2>Windows RPA</h2>
        <p className="error-text">Preview failed{errorDetail ? `: ${errorDetail}` : ""}</p>
      </div>
    );
  }

  if (!preview) return null;

  const badge = preview.status ?? "unknown";
  const cls = STATUS_CLASS[badge] ?? "";
  const display = resolveWindowsPreviewDisplay(preview);
  const attachWarning = preview.attach_warning ?? preview.attachment?.attach_warning ?? null;
  const uiaDiag = preview.uia_diagnostics;
  const uiaNotActionable = uiaDiag && !uiaDiag.uia_actionable;

  return (
    <div className="card windows-rpa">
      <h2>Windows RPA — {display.modeLabel}</h2>
      {attachWarning ? <p className="warn">{attachWarning}</p> : null}
      {uiaNotActionable ? (
        <div className="warn uia-diagnostic">
          <p>{uiaDiag.message}</p>
          {uiaDiag.recommended_action ? <p className="muted">{uiaDiag.recommended_action}</p> : null}
          <p className="muted">
            UIA scan: {uiaDiag.document_actionable_count} page controls / {uiaDiag.node_count} nodes
            {uiaDiag.canvas_like ? " · canvas-like" : ""}
          </p>
        </div>
      ) : null}
      {preview.automation_active ? (
        <p className="warn">Automation in progress — avoid moving mouse/keyboard</p>
      ) : null}
      <p>
        Status: <span className={`health-badge ${cls}`}>{badge}</span>
        {preview.confidence ? (
          <span className="muted"> · confidence {(preview.confidence * 100).toFixed(0)}%</span>
        ) : null}
      </p>
      {preview.attachment ? (
        <ul className="health-meta">
          <li>Window: {preview.attachment.window_title}</li>
          {preview.attachment.expected_title &&
          preview.attachment.live_title &&
          preview.attachment.expected_title !== preview.attachment.live_title ? (
            <li>
              Live title: {preview.attachment.live_title}
            </li>
          ) : null}
          {preview.attachment.window_handle != null ? (
            <li>HWND: {preview.attachment.window_handle}</li>
          ) : null}
          {preview.attachment.bounds ? (
            <li>
              Bounds: {Math.round(preview.attachment.bounds.left)},
              {Math.round(preview.attachment.bounds.top)} —{" "}
              {Math.round(preview.attachment.bounds.right)},
              {Math.round(preview.attachment.bounds.bottom)}
            </li>
          ) : null}
          <li>Backend: {display.backendLabel}</li>
        </ul>
      ) : null}
      {preview.current_action || preview.planned_action ? (
        <p>
          Action: <strong>{preview.current_action ?? preview.planned_action}</strong>
          {preview.current_target?.label ? ` → ${preview.current_target.label}` : ""}
        </p>
      ) : null}
      {display.imageSrc ? (
        <div className="rpa-preview-wrap">
          {display.caption ? <p className="muted rpa-preview-caption">{display.caption}</p> : null}
          <img className="rpa-preview-img" src={display.imageSrc} alt={display.modeLabel} />
        </div>
      ) : (
        <p className="muted">{display.emptyMessage}</p>
      )}
      {preview.recent_actions.length > 0 ? (
        <>
          <h4>Recent actions</h4>
          <ul className="step-list">
            {preview.recent_actions.map((a) => (
              <li key={a.action_id} className={a.success ? "step-ok" : a.uncertain ? "step-warn" : "step-fail"}>
                {a.domain_action || a.selector_key} — {a.success ? "ok" : a.uncertain ? "uncertain" : "fail"}
                {a.click_point ? ` @(${Math.round(a.click_point.x)},${Math.round(a.click_point.y)})` : ""}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {preview.message ? <p className="muted">{preview.message}</p> : null}
    </div>
  );
}

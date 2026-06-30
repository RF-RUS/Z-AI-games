import { useCallback, useEffect, useState } from "react";
import WindowsRpaPanel from "./WindowsRpaPanel";
import GameWindowPicker from "./GameWindowPicker";
import {
  AttachAdapterFailedError,
  attachAdapter,
  createSession,
  FlowStep,
  getSession,
  getSessionStatus,
  getSessionSteps,
  isOrchestratorOnline,
  listSessions,
  OrchestratorStatusResponse,
  pauseSession,
  resumeSession,
  SessionDetail,
  startSession,
  stopSession,
  tickSession,
} from "./unoApiClient";
import { buildWindowsAttachPayload, SelectedGameWindow } from "./windowAttachPayload";
import { assertRequestedAdapterAttached, attachedBindings, formatAdapterBindingLabel } from "./sessionAdapterAttach";
import {
  buildAttachFailurePanelContent,
  buildSessionAttachDiagnosticsView,
  formatRecoveryLabel,
  resolveCycleErrorText,
  shouldShowAttachFailurePanel,
  shouldShowCycleFailurePanel,
} from "./sessionAttachErrors";

type RecoveryInfo = NonNullable<OrchestratorStatusResponse["last_recovery"]>;

type PanelState = "loading" | "offline" | "ready" | "error";

const FLOW_STATE_CLASS: Record<string, string> = {
  active: "flow-active",
  idle: "flow-idle",
  paused: "flow-paused",
  error: "flow-error",
  attaching: "flow-attaching",
};

function explainError(error: string | undefined, recovery: RecoveryInfo | null | undefined): string {
  if (error?.includes("Playwright startup failed at stage=")) {
    return "Web adapter attach failed during Playwright startup. See stage and backend message above.";
  }
  if (!recovery?.error_class && !error) return "";
  const cls = recovery?.error_class ?? "unknown";
  const map: Record<string, string> = {
    transient: "Transient network issue or timeout \u2014 retry may succeed.",
    permanent: "Attach failed \u2014 check adapter-web and Playwright startup stage.",
    policy_blocked: "Policy-guard blocked action \u2014 confidence too low or policy violation.",
    perception_low_confidence: "Low perception confidence \u2014 retry or switch to manual.",
  };
  return map[cls] ?? error ?? "";
}

function getRecoveryHint(
  error: string | undefined,
  recovery: RecoveryInfo | null | undefined,
  failedStep: string | null,
  adapterType?: string,
): { action: string; command?: string } | null {
  const cls = recovery?.error_class;
  if (cls === "transient") {
    return { action: "Retry the tick", command: `curl -X POST http://127.0.0.1:8100/sessions/{id}/tick` };
  }
  if (cls === "permanent" || error?.includes("Playwright startup failed")) {
    if (adapterType === "web") {
      return {
        action: "Check adapter-web health and restart if needed",
        command: "curl http://127.0.0.1:8104/health",
      };
    }
    return {
      action: "Check adapter-windows health",
      command: "curl http://127.0.0.1:8105/health",
    };
  }
  if (failedStep === "observe" || failedStep === "web_evidence") {
    return {
      action: "Test evidence capture directly",
      command: `curl "http://127.0.0.1:8104/adapters/{adapter_id}/evidence?correlation_id=probe"`,
    };
  }
  if (failedStep === "perceive") {
    return {
      action: "Test perception service directly",
      command: "curl -X POST http://127.0.0.1:8103/perceive",
    };
  }
  if (cls === "policy_blocked") {
    return { action: "Review policy-guard rules or lower confidence threshold" };
  }
  if (cls === "perception_low_confidence") {
    return { action: "Check observation quality or switch to manual mode" };
  }
  return null;
}

function mergeSession(base: SessionDetail, status: OrchestratorStatusResponse): SessionDetail {
  const diagnostics = status.attach_startup_diagnostics ?? base.attach_startup_diagnostics;
  return {
    ...base,
    flow_state: status.flow_state ?? base.flow_state,
    phase: status.phase ?? base.phase,
    error: status.error ?? base.error,
    attach_startup_diagnostics: diagnostics,
    metrics: status.metrics ?? base.metrics,
  };
}

type Props = { initialSessionId?: string | null };

export default function OperatorPanel({ initialSessionId }: Props) {
  const [sessions, setSessions] = useState<SessionDetail[]>([]);
  const [selected, setSelected] = useState<string | null>(initialSessionId ?? null);
  const [steps, setSteps] = useState<FlowStep[]>([]);
  const [recovery, setRecovery] = useState<RecoveryInfo | null>(null);
  const [adapter, setAdapter] = useState("mock");
  const [windowsProfile, setWindowsProfile] = useState("real-uno-desktop");
  const [webProfile, setWebProfile] = useState("scuffed-uno-web");
  const [windowTitleHint, setWindowTitleHint] = useState("");
  const [selectedGameWindow, setSelectedGameWindow] = useState<SelectedGameWindow | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [panelState, setPanelState] = useState<PanelState>("loading");
  const [errorDetail, setErrorDetail] = useState<string | null>(null);

  useEffect(() => {
    if (initialSessionId) setSelected(initialSessionId);
  }, [initialSessionId]);

  const loadSessionIntoPanel = useCallback(async (sessionId: string) => {
    const [detail, st, stepList] = await Promise.all([
      getSession(sessionId),
      getSessionStatus(sessionId),
      getSessionSteps(sessionId),
    ]);
    const merged = mergeSession(detail, st);
    setSelected(sessionId);
    setRecovery(st.last_recovery ?? null);
    setSteps(stepList);
    setSessions((prev) => {
      const rest = prev.filter((s) => s.session_id !== sessionId);
      return [...rest, merged];
    });
    return merged;
  }, []);

  const refresh = useCallback(async (focusSessionId?: string | null) => {
    const activeSessionId = focusSessionId ?? selected;
    try {
      const online = await isOrchestratorOnline();
      if (!online) {
        setPanelState("offline");
        setSessions([]);
        setSteps([]);
        setRecovery(null);
        setErrorDetail(null);
        return;
      }

      const list = await listSessions();
      setSessions(list);
      setPanelState("ready");

      if (activeSessionId) {
        try {
          await loadSessionIntoPanel(activeSessionId);
        } catch (e) {
          setErrorDetail(e instanceof Error ? e.message : String(e));
        }
      } else {
        setSteps([]);
        setRecovery(null);
      }
    } catch (e) {
      setPanelState("error");
      setErrorDetail(e instanceof Error ? e.message : String(e));
      setSessions([]);
      setSteps([]);
      setRecovery(null);
    }
  }, [loadSessionIntoPanel, selected]);

  useEffect(() => {
    setPanelState("loading");
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const createAndStart = async () => {
    setActionLoading(true);
    setErrorDetail(null);
    let createdSessionId: string | null = null;
    try {
      const online = await isOrchestratorOnline();
      if (!online) {
        setPanelState("offline");
        return;
      }
      const profile = adapter === "web" ? webProfile : windowsProfile;
      const s = (await createSession({
        config: {
          adapter_type: adapter,
          adapter_id: "pending",
          strategy_id: "heuristic",
          model_assist_enabled: false,
        },
        automatic: true,
        web_profile_id: adapter === "web" ? webProfile : "local-mock-uno",
        windows_profile_id: adapter === "windows" ? windowsProfile : profile,
      })) as SessionDetail;
      if (!s?.session_id) {
        throw new Error("Invalid create session response: missing session_id");
      }
      createdSessionId = s.session_id;
      const attachPayload = buildWindowsAttachPayload({
        adapter,
        windowsProfile,
        webProfile,
        selectedWindow: adapter === "windows" ? selectedGameWindow : null,
        windowTitleHint: adapter === "windows" ? windowTitleHint : undefined,
      });
      const attached = await attachAdapter(s.session_id, attachPayload);
      assertRequestedAdapterAttached(
        attached as SessionDetail,
        adapter,
        adapter === "web" ? webProfile : adapter === "windows" ? windowsProfile : undefined,
      );
      await startSession(s.session_id);
      setSelected(s.session_id);
      await refresh();
    } catch (e) {
      if (createdSessionId) {
        if (e instanceof AttachAdapterFailedError && e.session) {
          const st = await getSessionStatus(createdSessionId).catch(() => null);
          const merged = st ? mergeSession(e.session, st) : e.session;
          setSelected(createdSessionId);
          setRecovery(st?.last_recovery ?? null);
          setSessions((prev) => {
            const rest = prev.filter((s) => s.session_id !== createdSessionId);
            return [...rest, merged];
          });
        } else {
          await refresh(createdSessionId);
        }
      }
      setErrorDetail(e instanceof Error ? e.message : String(e));
      setPanelState("error");
    } finally {
      setActionLoading(false);
    }
  };

  const control = async (action: "pause" | "resume" | "stop" | "tick") => {
    if (!selected) return;
    setActionLoading(true);
    setErrorDetail(null);
    try {
      if (action === "pause") await pauseSession(selected);
      else if (action === "resume") await resumeSession(selected);
      else if (action === "stop") await stopSession(selected);
      else await tickSession(selected);
      await refresh();
    } catch (e) {
      setErrorDetail(e instanceof Error ? e.message : String(e));
    } finally {
      setActionLoading(false);
    }
  };

  const current = sessions.find((s) => s.session_id === selected);
  const flowClass = FLOW_STATE_CLASS[current?.flow_state ?? ""] ?? "flow-idle";
  const metrics = current?.metrics;
  const attachDiag = buildSessionAttachDiagnosticsView(
    current?.error,
    current?.attach_startup_diagnostics,
    recovery,
  );
  const attachPanel = current
    ? buildAttachFailurePanelContent(current.error, current.attach_startup_diagnostics, recovery)
    : null;
  const canTick =
    Boolean(current) &&
    current!.flow_state !== "attaching" &&
    attachedBindings(current!).length > 0 &&
    !actionLoading;
  const showAttachFailurePanel = current
    ? shouldShowAttachFailurePanel(
        current.error,
        current.attach_startup_diagnostics,
        recovery,
        current.config?.adapter_type,
      )
    : false;
  const failedStep = steps.find((st) => st.result?.success === false)?.step_name ?? null;
  const showCycleFailurePanel = current
    ? shouldShowCycleFailurePanel(
        current.flow_state,
        current.error,
        recovery,
        current.attach_startup_diagnostics,
      )
    : false;
  const cycleErrorText = resolveCycleErrorText(current?.error, recovery, failedStep);
  const adapterType = current?.config?.adapter_type;
  const windowsAdapterId =
    current?.adapter_bindings?.find((b) => b.adapter_type === "windows" && b.adapter_id)?.adapter_id ?? null;

  if (panelState === "loading") {
    return (
      <section className="panel">
        <h2>Operator</h2>
        <p className="muted">Loading sessions…</p>
      </section>
    );
  }

  if (panelState === "offline") {
    return (
      <section className="panel">
        <h2>Operator</h2>
        <p className="muted">
          Orchestrator is offline (port 8100). Start backend: <code>.\scripts\dev-backend.ps1</code>
        </p>
        <div className="row">
          <label>
            Adapter
            <select value={adapter} onChange={(e) => setAdapter(e.target.value)} disabled>
              <option value="mock">Mock</option>
              <option value="web">Web (Scuffed Uno / Pizzuno / mock)</option>
              <option value="windows">Windows</option>
            </select>
          </label>
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>Operator</h2>
      {panelState === "error" && errorDetail ? (
        <p className="error-text">Failed to load sessions: {errorDetail}</p>
      ) : null}
      {errorDetail && panelState === "ready" ? (
        <p className="error-text">{errorDetail}</p>
      ) : null}

      {adapter === "mock" ? (
        <p className="muted operator-hint">
          Mock sessions are listed from orchestrator (:8100). In-process evaluation (
          <code>evaluate-full-operator.py</code>) does not appear here.
        </p>
      ) : null}

      <div className="row">
        <label>
          Adapter
          <select value={adapter} onChange={(e) => setAdapter(e.target.value)}>
            <option value="mock">Mock</option>
            <option value="web">Web (Scuffed Uno / Pizzuno / mock)</option>
            <option value="windows">Windows</option>
          </select>
        </label>
        {adapter === "web" ? (
          <label>
            Web profile
            <select value={webProfile} onChange={(e) => setWebProfile(e.target.value)}>
              <option value="scuffed-uno-web">Scuffed Uno (canvas coordinates)</option>
              <option value="real-unoh-web">Pizzuno DOM (real-unoh-web)</option>
              <option value="local-mock-uno">Local mock page</option>
            </select>
          </label>
        ) : null}
        {adapter === "windows" ? (
          <>
            <label>
              Windows profile
              <select
                value={windowsProfile}
                disabled={selectedGameWindow != null}
                onChange={(e) => setWindowsProfile(e.target.value)}
              >
                <option value="real-uno-desktop">Existing UNO game window</option>
                <option value="local-mock-uno">Mock test target (tkinter)</option>
              </select>
            </label>
            <GameWindowPicker
              selected={selectedGameWindow}
              onSelect={(window) => {
                setSelectedGameWindow(window);
                if (window) {
                  setWindowsProfile("real-uno-desktop");
                  setWindowTitleHint("");
                }
              }}
              disabled={actionLoading}
            />
            {!selectedGameWindow ? (
              <label>
                Window title hint (optional)
                <input
                  type="text"
                  value={windowTitleHint}
                  onChange={(e) => setWindowTitleHint(e.target.value)}
                  placeholder="e.g. UNO Championship"
                />
              </label>
            ) : null}
          </>
        ) : null}
        <button type="button" disabled={actionLoading} onClick={createAndStart}>
          New Session
        </button>
      </div>

      {sessions.length === 0 ? (
        <p className="muted">No sessions yet. Click New Session to create one.</p>
      ) : (
        <ul className="session-list">
          {sessions.map((s) => (
            <li key={s.session_id}>
              <button
                type="button"
                className={selected === s.session_id ? "active" : ""}
                onClick={() => setSelected(s.session_id)}
              >
                {s.session_id.slice(0, 8)} —{" "}
                <span className={`flow-badge ${FLOW_STATE_CLASS[s.flow_state] ?? ""}`}>
                  {s.flow_state}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {current ? (
        <div className="card">
          <h3>Session {current.session_id.slice(0, 8)}</h3>
          <p>
            Flow: <span className={`flow-badge ${flowClass}`}>{current.flow_state}</span> | Phase:{" "}
            {current.phase}
          </p>
          {showAttachFailurePanel ? (
            <div className="error-panel attach-failure-panel">
              <div className="error-panel-header">
                <span className="error-panel-icon">\u2717</span>
                <p className="error-text">{attachPanel?.summary}</p>
              </div>
              {attachPanel?.startupStage ? (
                <div className="attach-stage-info">
                  <p className="warn">
                    Failed at stage: <strong>{attachPanel.startupStage}</strong>
                  </p>
                  {attachPanel?.stageTimingsText ? (
                    <p className="muted">Stage timings: {attachPanel.stageTimingsText}</p>
                  ) : null}
                </div>
              ) : null}
              {attachPanel && attachPanel.pageGotoLines.length > 0 ? (
                <details className="attach-diagnostics">
                  <summary className="warn">page_goto diagnostics ({attachPanel.pageGotoLines.length} items)</summary>
                  <ul>
                    {attachPanel.pageGotoLines.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
              {attachPanel && attachPanel.artifactPaths.length > 0 ? (
                <ul className="error-meta">
                  {attachPanel.artifactPaths.map((path) => (
                    <li key={path}>Artifact: {path}</li>
                  ))}
                </ul>
              ) : null}
              {attachedBindings(current).length === 0 ? (
                <p className="warn">No adapter attached \u2014 session cannot run ticks until attach succeeds.</p>
              ) : null}
              {recovery ? (
                <ul className="error-meta">
                  <li>
                    Class: <strong>{recovery.error_class}</strong>
                  </li>
                  <li>{formatRecoveryLabel(adapterType, recovery)}</li>
                  {recovery.reason && recovery.reason !== attachDiag.errorText ? <li>{recovery.reason}</li> : null}
                </ul>
              ) : null}
              <p className="muted">{explainError(attachDiag.errorText, recovery)}</p>
              <div className="attach-recovery-hint">
                <span className="recovery-hint-label">Try:</span>
                <span className="recovery-hint-action">
                  {adapterType === "web"
                    ? "Check adapter-web health, verify Playwright installation, or try different profile"
                    : "Check adapter-windows, verify target window is visible"}
                </span>
                <button
                  type="button"
                  className="copy-command-btn"
                  onClick={() => navigator.clipboard.writeText(adapterType === "web"
                    ? "curl http://127.0.0.1:8104/health"
                    : "curl http://127.0.0.1:8105/health")}
                  title="Copy health check command"
                >
                  Copy command
                </button>
              </div>
              <details className="debug-dump">
                <summary>Debug: attach diagnostics payload</summary>
                <pre>{JSON.stringify(
                  {
                    error: current.error ?? null,
                    attach_startup_diagnostics: current.attach_startup_diagnostics ?? null,
                    last_recovery: recovery ?? null,
                  },
                  null,
                  2,
                )}</pre>
              </details>
            </div>
          ) : null}
          {showCycleFailurePanel ? (() => {
            const hint = getRecoveryHint(current?.error, recovery, failedStep, adapterType);
            return (
              <div className="error-panel cycle-failure-panel">
                <div className="error-panel-header">
                  <span className="error-panel-icon">\u26A0</span>
                  <p className="error-text">{cycleErrorText}</p>
                </div>
                {failedStep ? (
                  <p className="warn">
                    Failed step: <strong>{failedStep}</strong>
                  </p>
                ) : null}
                {recovery ? (
                  <ul className="error-meta">
                    <li>
                      Class: <strong>{recovery.error_class}</strong>
                    </li>
                    <li>{formatRecoveryLabel(adapterType, recovery)}</li>
                    {recovery.reason ? <li>{recovery.reason}</li> : null}
                  </ul>
                ) : null}
                <p className="muted">{explainError(current.error, recovery)}</p>
                {hint ? (
                  <div className="recovery-hint">
                    <span className="recovery-hint-label">Next step:</span>
                    <span className="recovery-hint-action">{hint.action}</span>
                    {hint.command ? (
                      <button
                        type="button"
                        className="copy-command-btn"
                        onClick={() => navigator.clipboard.writeText(hint!.command!.replace(/\{id\}/g, current?.session_id ?? "").replace(/\{adapter_id\}/g, current?.adapter_bindings?.find(b => b.adapter_type === "web")?.adapter_id ?? ""))}
                        title="Copy diagnostic command"
                      >
                        Copy command
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })() : null}
          <p>
            Steps: {metrics?.total_steps ?? 0} | ok {metrics?.successful_steps ?? 0} | fail{" "}
            {metrics?.failed_steps ?? 0}
          </p>
          <div className="row btn-row">
            <button type="button" disabled={!canTick} onClick={() => control("tick")}>
              Tick
            </button>
            <button type="button" disabled={actionLoading} onClick={() => control("pause")}>
              Pause
            </button>
            <button type="button" disabled={actionLoading} onClick={() => control("resume")}>
              Resume
            </button>
            <button type="button" disabled={actionLoading} onClick={() => control("stop")}>
              Stop
            </button>
          </div>
          <h4>Adapters</h4>
          <ul>
            {attachedBindings(current).length === 0 ? (
              <li className="muted">No adapters attached</li>
            ) : (
              attachedBindings(current).map((b, i) => (
                <li key={i}>{formatAdapterBindingLabel(b)}</li>
              ))
            )}
          </ul>
          <h4>Recent Steps</h4>
          <ul className="step-list">
            {steps.length === 0 ? (
              <li className="muted">No steps recorded</li>
            ) : (
              steps.slice(-10).map((st, i) => (
                <li key={i} className={st.result?.success ? "step-ok" : "step-fail"}>
                  <span>{st.step_name}</span>
                  {st.result?.success ? " ✓" : ` ✗ ${st.result?.error ?? "failed"}`}
                  {st.result?.retries ? ` (retry ${st.result.retries})` : ""}
                </li>
              ))
            )}
          </ul>
          {windowsAdapterId ? <WindowsRpaPanel adapterId={windowsAdapterId} /> : null}
        </div>
      ) : null}
    </section>
  );
}

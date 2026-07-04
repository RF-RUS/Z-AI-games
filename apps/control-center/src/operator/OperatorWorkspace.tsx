import { useState, useCallback, useMemo } from "react";
import SessionHeader from "./header/SessionHeader";
import LeftRail from "./left/LeftRail";
import CenterPanel from "./center/CenterPanel";
import RightRail from "./right/RightRail";
import BottomDrawer from "./bottom/BottomDrawer";
import ErrorOverlay from "./shared/ErrorOverlay";
import { useOperatorPolling } from "./hooks/useOperatorPolling";
import { useTraceSelection } from "./hooks/useTraceSelection";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useStaleDetection } from "./hooks/useStaleDetection";
import { canTransition } from "../operatorStore";
import type { ControlMode } from "../operatorStore";

function getRecoveryAction(error?: string | null, recovery?: { error_class?: string; action?: string } | null): string | null {
  const cls = recovery?.error_class;
  if (cls === "transient") return "Transient issue. Click Tick to retry.";
  if (cls === "permanent") return "Adapter failed. Check adapter service health.";
  if (error?.includes("observe") || error?.includes("evidence")) return "Evidence capture failed. Test: curl :8104/adapters/{id}/evidence";
  if (cls === "policy_blocked") return "Action blocked by policy. Review confidence threshold.";
  if (cls === "perception_low_confidence") return "Low observation quality. Switch to Manual.";
  return null;
}

interface Props {
  sessionId: string | null;
  onNewSession?: () => void;
}

export default function OperatorWorkspace({ sessionId, onNewSession }: Props) {
  const [controlMode, setControlMode] = useState<ControlMode>("auto");
  const [escalations, setEscalations] = useState<Array<{ id: string; message: string; status: string; severity: string }>>([]);

  const polling = useOperatorPolling(sessionId);
  const trace = useTraceSelection(polling.traceSteps);
  const freshness = useStaleDetection(polling.lastUpdateTs, polling.pollFailed, !!sessionId);

  const failedStep = useMemo(
    () => polling.steps.find(s => s.result?.success === false)?.step_name ?? null,
    [polling.steps],
  );

  const recoveryAction = useMemo(
    () => getRecoveryAction(polling.status?.error, polling.status?.last_recovery),
    [polling.status?.error, polling.status?.last_recovery],
  );

  const handleModeChange = useCallback((mode: ControlMode) => {
    if (canTransition(controlMode, mode)) {
      setControlMode(mode);
    }
  }, [controlMode]);

  const handleTick = useCallback(async () => {
    if (!sessionId) return;
    try {
      await fetch(`http://127.0.0.1:8100/sessions/${sessionId}/tick`, { method: "POST" });
    } catch { /* ignore */ }
  }, [sessionId]);

  const handlePause = useCallback(async () => {
    if (!sessionId) return;
    try {
      await fetch(`http://127.0.0.1:8100/sessions/${sessionId}/pause`, { method: "POST" });
      setControlMode("paused" as ControlMode);
    } catch { /* ignore */ }
  }, [sessionId]);

  const handleResume = useCallback(async () => {
    if (!sessionId) return;
    try {
      await fetch(`http://127.0.0.1:8100/sessions/${sessionId}/resume`, { method: "POST" });
      setControlMode("auto");
    } catch { /* ignore */ }
  }, [sessionId]);

  const handleStop = useCallback(async () => {
    if (!sessionId) return;
    try {
      await fetch(`http://127.0.0.1:8100/sessions/${sessionId}/stop`, { method: "POST" });
    } catch { /* ignore */ }
  }, [sessionId]);

  const handleAcknowledgeEscalation = useCallback((id: string) => {
    setEscalations(prev => prev.map(e => e.id === id ? { ...e, status: "acknowledged" } : e));
  }, []);

  const handleDismissEscalation = useCallback((id: string) => {
    setEscalations(prev => prev.map(e => e.id === id ? { ...e, status: "dismissed" } : e));
  }, []);

  const handleTakeControl = useCallback(() => {
    setControlMode("manual");
  }, []);

  useKeyboardShortcuts({
    onPrevStep: trace.goToPrevStep,
    onNextStep: trace.goToNextStep,
    onToggleFollow: () => trace.setFollowLatest(f => !f),
    onTabSwitch: () => {},
    onEscape: () => {},
    onTick: handleTick,
    onPause: handlePause,
    onResume: handleResume,
  });

  const flowState = polling.session?.flow_state ?? "idle";
  const hasError = flowState === "error";

  return (
    <div className="operator-workspace">
      <SessionHeader
        flowState={flowState}
        phase={polling.session?.phase ?? null}
        adapterType={polling.session?.config?.adapter_type ?? null}
        controlMode={controlMode}
        isOnline={polling.isOnline}
        freshness={freshness}
        lastUpdateTs={polling.lastUpdateTs}
        onTick={handleTick}
        onPause={handlePause}
        onResume={handleResume}
        onStop={handleStop}
        onNewSession={onNewSession ?? (() => {})}
        onModeChange={handleModeChange}
      />

      <div className="workspace-body">
        <LeftRail
          gameState={polling.gameState}
          escalations={escalations as never[]}
          onAcknowledge={handleAcknowledgeEscalation}
          onTakeControl={handleTakeControl}
        />

        <CenterPanel
          sessionId={sessionId}
          selectedStep={trace.selectedStep}
          steps={polling.traceSteps}
          filteredSteps={trace.filteredSteps}
          selectedStepNum={trace.selectedStepNum}
          followLatest={trace.followLatest}
          activeFilter={trace.activeFilter}
          adapterType={polling.session?.config?.adapter_type ?? null}
          onStepSelect={trace.selectStep}
          onFilterChange={trace.setActiveFilter}
          onJumpToLatest={trace.jumpToLatest}
          onPrev={trace.goToPrevStep}
          onNext={trace.goToNextStep}
          onToggleFollow={() => trace.setFollowLatest(f => !f)}
        />

        <RightRail
          decision={polling.decision}
          verification={polling.verification}
          escalations={escalations as never[]}
          events={[]}
          steps={polling.steps}
          error={polling.status?.error ?? null}
          diagnostics={polling.status?.attach_startup_diagnostics as Record<string, unknown> ?? null}
          observation={null}
          traceMeta={trace.selectedStep?.meta ?? null}
          onAcknowledgeEscalation={handleAcknowledgeEscalation}
          onTakeControl={handleTakeControl}
          onDismissEscalation={handleDismissEscalation}
        />
      </div>

      <BottomDrawer
        events={[]}
        steps={polling.steps}
        observation={null}
        error={polling.status?.error ?? null}
        sessionId={sessionId}
      />

      {polling.stale && flowState === "active" && (
        <div style={{ background: "#fff3cd", color: "#856404", padding: "8px 16px", borderBottom: "1px solid #ffc107", fontSize: "13px" }}>
          Session appears stale — no new steps arriving. Check adapter and orchestrator health.
        </div>
      )}

      {hasError && (
        <ErrorOverlay
          error={polling.status?.error ?? null}
          failedStep={failedStep}
          recoveryAction={recoveryAction}
          onDismiss={() => {}}
        />
      )}
    </div>
  );
}

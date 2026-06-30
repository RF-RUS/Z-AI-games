import { useCallback, useEffect, useReducer, useRef, useState, useMemo } from "react";
import StatusBar from "./StatusBar";
import ControlPanel from "./ControlPanel";
import MonitorPanel from "./MonitorPanel";
import ChatPanel from "./ChatPanel";
import EventLog from "./EventLog";
import AlertBar from "./AlertBar";
import SessionSetup from "./SessionSetup";
import ApprovalPanel from "./ApprovalPanel";
import HandoffBanner from "./HandoffBanner";
import EscalationPanel from "./EscalationPanel";
import AgentTransparencyPanel from "./AgentTransparency";
import StrategyPanel from "./StrategyPanel";
import TracePanel from "./TracePanel";
import OperatorWorkspace from "./operator/OperatorWorkspace";
import {
  createSession,
  attachAdapter,
  startSession,
  tickSession,
} from "./unoApiClient";
import { buildWindowsAttachPayload, SelectedGameWindow } from "./windowAttachPayload";
import { assertRequestedAdapterAttached, attachedBindings } from "./sessionAdapterAttach";
import {
  initialState,
  operatorReducer,
  canTransition,
  ControlMode,
  createChatMessage,
  createEvent,
  createAlert,
  createPendingAction,
  createEscalation,
} from "./operatorStore";
import { useHealthPolling, useSessionPolling } from "./usePolling";
import { parseCommand, executeCommand } from "./operatorCommands";
import { useKeyboardShortcuts } from "./useKeyboardShortcuts";
import { logAnalyticsEvent, ANALYTICS_EVENTS } from "./analytics";

declare global {
  interface Window {
    unoApi: Record<string, (...args: unknown[]) => Promise<unknown>>;
  }
}

export default function App() {
  const [state, dispatch] = useReducer(operatorReducer, initialState);
  const [starting, setStarting] = useState(false);
  const chatInputRef = useRef<HTMLInputElement>(null);

  // Live polling
  useHealthPolling(dispatch);
  useSessionPolling(state.sessionId, dispatch, state.session?.flow_state === "active");

  // Session setup
  const handleStartSession = async (config: {
    adapterType: string;
    profileId: string;
    selectedWindow?: SelectedGameWindow | null;
    selectedTab?: { url: string; id: string } | null;
    gameType?: string;
  }) => {
    setStarting(true);
    try {
      const spec = {
        config: {
          adapter_type: config.adapterType,
          adapter_id: "pending",
          strategy_id: "heuristic",
          model_assist_enabled: false,
        },
        automatic: true,
        web_profile_id: config.adapterType === "web" ? config.profileId : "local-mock-uno",
        windows_profile_id: config.adapterType === "windows" ? config.profileId : "local-mock-uno",
      };
      const created = (await createSession(spec)) as { session_id: string };
      dispatch({ type: "ADD_EVENT", event: createEvent("session", "Session created") });

      const attachPayload = buildWindowsAttachPayload({
        adapter: config.adapterType,
        windowsProfile: config.profileId,
        webProfile: config.profileId,
        selectedWindow: config.selectedWindow ?? null,
        selectedTab: config.selectedTab ?? null,
      });
      await attachAdapter(created.session_id, attachPayload);
      dispatch({ type: "ADD_EVENT", event: createEvent("adapter", "Adapter attached") });

      await startSession(created.session_id);
      dispatch({ type: "ADD_EVENT", event: createEvent("session", "Session started — agent is active") });

      dispatch({ type: "SET_SESSION_ID", sessionId: created.session_id });
      dispatch({ type: "SET_VIEW", view: "operator" });
      dispatch({ type: "CLEAR_ALERTS" });
    } catch (e) {
      dispatch({ type: "ADD_ALERT", alert: createAlert("error", String(e), "setup") });
      dispatch({ type: "ADD_EVENT", event: createEvent("error", `Setup failed: ${String(e)}`, false) });
    } finally {
      setStarting(false);
    }
  };

  // Control actions
  const handleControl = async (action: "pause" | "resume" | "stop" | "tick") => {
    if (!state.sessionId) return;
    try {
      if (action === "pause") {
        const { pauseSession: pause } = await import("./unoApiClient");
        await pause(state.sessionId);
        dispatch({ type: "TRANSITION_CONTROL", to: "paused", reason: "Operator paused" });
        dispatch({ type: "ADD_EVENT", event: createEvent("control", "Session paused") });
      } else if (action === "resume") {
        const { resumeSession: resume } = await import("./unoApiClient");
        await resume(state.sessionId);
        dispatch({ type: "TRANSITION_CONTROL", to: "auto", reason: "Operator resumed" });
        dispatch({ type: "ADD_EVENT", event: createEvent("control", "Session resumed") });
      } else if (action === "stop") {
        const { stopSession: stop } = await import("./unoApiClient");
        await stop(state.sessionId);
        dispatch({ type: "TRANSITION_CONTROL", to: "paused", reason: "Operator stopped" });
        dispatch({ type: "ADD_EVENT", event: createEvent("control", "Session stopped") });
      } else {
        await tickSession(state.sessionId);
        dispatch({ type: "ADD_EVENT", event: createEvent("tick", "Manual tick executed") });
      }
    } catch (e) {
      dispatch({ type: "ADD_ALERT", alert: createAlert("error", String(e), "control") });
    }
  };

  // Mode transitions
  const handleModeChange = useCallback((mode: string) => {
    const newMode = mode as import("./operatorStore").ControlMode;
    if (canTransition(state.controlMode, newMode)) {
      dispatch({ type: "TRANSITION_CONTROL", to: newMode, reason: `Operator switched to ${newMode}` });
      dispatch({ type: "ADD_EVENT", event: createEvent("mode", `Control mode: ${newMode}`) });
    }
  }, [state.controlMode, dispatch]);

  // Toggle mode (for keyboard shortcut)
  const handleToggleMode = useCallback(() => {
    const nextMode = state.controlMode === "auto" ? "manual" : "auto";
    if (canTransition(state.controlMode, nextMode)) {
      dispatch({ type: "TRANSITION_CONTROL", to: nextMode, reason: `Keyboard: toggled to ${nextMode}` });
      logAnalyticsEvent(ANALYTICS_EVENTS.MODE_CHANGED, state.sessionId ?? "", { from: state.controlMode, to: nextMode });
    }
  }, [state.controlMode, state.sessionId, dispatch]);

  // Return to bot
  const handleReturnToBot = useCallback(async () => {
    if (!canTransition(state.controlMode, "returning_to_bot")) return;
    dispatch({ type: "TRANSITION_CONTROL", to: "returning_to_bot", reason: "Returning control to bot" });
    dispatch({ type: "ADD_EVENT", event: createEvent("handoff", "Resyncing bot state...") });
    logAnalyticsEvent(ANALYTICS_EVENTS.RETURN_TO_BOT, state.sessionId ?? "", { from: state.controlMode });

    // Simulate resync (in real implementation, would call backend resync endpoint)
    await new Promise((r) => setTimeout(r, 500));

    dispatch({ type: "SET_HANDOFF_SYNC", handoffId: state.handoffHistory[state.handoffHistory.length - 1]?.id ?? "", syncStatus: "success" });
    dispatch({ type: "TRANSITION_CONTROL", to: "auto", reason: "Resync complete" });
    dispatch({ type: "ADD_EVENT", event: createEvent("handoff", "Bot resumed autonomous control") });
    dispatch({ type: "ADD_CHAT_MESSAGE", message: createChatMessage("system", "Bot has resumed autonomous control.") });
  }, [state.controlMode, state.handoffHistory, dispatch]);

  // Approval actions
  const handleApproveAction = useCallback((actionId: string) => {
    dispatch({ type: "RESOLVE_PENDING_ACTION", actionId, status: "approved" });
    dispatch({ type: "ADD_EVENT", event: createEvent("approval", "Action approved by operator") });
    dispatch({ type: "ADD_CHAT_MESSAGE", message: createChatMessage("system", "Action approved. Bot executing...") });
  }, [dispatch]);

  const handleDenyAction = useCallback((actionId: string, comment?: string) => {
    dispatch({ type: "RESOLVE_PENDING_ACTION", actionId, status: "deny" as "denied", comment });
    dispatch({ type: "ADD_EVENT", event: createEvent("approval", `Action denied${comment ? `: ${comment}` : ""}`) });
    dispatch({ type: "ADD_CHAT_MESSAGE", message: createChatMessage("system", "Action denied.") });
  }, [dispatch]);

  const handleTakeOver = useCallback(() => {
    if (canTransition(state.controlMode, "manual")) {
      dispatch({ type: "TRANSITION_CONTROL", to: "manual", reason: "Operator took manual control" });
      dispatch({ type: "ADD_EVENT", event: createEvent("handoff", "Operator took manual control") });
      dispatch({ type: "ADD_CHAT_MESSAGE", message: createChatMessage("system", "You are now in control. Bot is observing.") });
    }
  }, [state.controlMode, dispatch]);

  // Chat / command handling
  const handleSendMessage = useCallback(async (text: string) => {
    dispatch({ type: "ADD_CHAT_MESSAGE", message: createChatMessage("operator", text, "sent") });

    const command = parseCommand(text);
    try {
      const result = await executeCommand(command, state, dispatch);
      dispatch({
        type: "ADD_CHAT_MESSAGE",
        message: createChatMessage("agent", result.message, result.acknowledged ? "acknowledged" : "error"),
      });
      if (result.action) {
        dispatch({ type: "ADD_EVENT", event: createEvent("command", `Operator: ${command.type} — ${result.message}`, true) });
      }
    } catch (e) {
      dispatch({
        type: "ADD_CHAT_MESSAGE",
        message: createChatMessage("agent", `Error: ${String(e)}`, "error"),
      });
    }
  }, [state, dispatch]);

  // Alert dismiss
  const handleDismissAlert = useCallback((index: number) => {
    const visibleAlerts = state.alerts.filter((a) => !a.dismissed);
    if (visibleAlerts[index]) {
      dispatch({ type: "DISMISS_ALERT", alertId: visibleAlerts[index].id });
    }
  }, [state.alerts, dispatch]);

  // Keyboard shortcuts (must be after all handlers are declared)
  useKeyboardShortcuts({
    onToggleMode: handleToggleMode,
    onPause: () => handleControl("pause"),
    onResume: () => handleControl("resume"),
    onTick: () => handleControl("tick"),
    onReturnToBot: handleReturnToBot,
    onDismissAlert: () => {
      const visible = state.alerts.filter((a) => !a.dismissed);
      if (visible.length > 0) {
        dispatch({ type: "DISMISS_ALERT", alertId: visible[0].id });
      }
    },
    focusChatInput: () => chatInputRef.current?.focus(),
    controlMode: state.controlMode,
    isRunning: state.session?.flow_state === "active",
    isPaused: state.session?.flow_state === "paused",
  });

  // Trace ↔ Event Log sync
  const [highlightedStep, setHighlightedStep] = useState<string | null>(null);
  const highlightTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleTraceStepSelect = useCallback((stepName: string | null) => {
    setHighlightedStep(stepName);
    if (highlightTimeoutRef.current) clearTimeout(highlightTimeoutRef.current);
    if (stepName) {
      highlightTimeoutRef.current = setTimeout(() => setHighlightedStep(null), 3000);
    }
  }, []);

  const handleEventLogStepClick = useCallback((stepName: string) => {
    handleTraceStepSelect(stepName);
  }, [handleTraceStepSelect]);

  // Derived state
  const flowState = state.session?.flow_state ?? "idle";
  const isRunning = flowState === "active";
  const isPaused = flowState === "paused";
  const hasError = flowState === "error";
  const sessionBindings = state.session ? attachedBindings(state.session) : [];
  const metrics = state.session?.metrics;
  const visibleAlerts = state.alerts.filter((a) => !a.dismissed);

  return (
    <div className="app">
      {/* New operator workspace — replaces old layout when operator view is active */}
      {state.view === "operator" ? (
        <OperatorWorkspace sessionId={state.sessionId} />
      ) : (
        <>
          <StatusBar
            health={state.health}
            healthLoading={state.healthLoading}
            flowState={flowState}
            adapterType={state.session?.config?.adapter_type}
            gameType={state.session?.config?.adapter_type === "windows" ? "UNO" : undefined}
            controlMode={state.controlMode}
            onModeChange={handleModeChange}
            currentPhase={state.session?.phase}
            sessionHealth={hasError ? "error" : isRunning ? "healthy" : null}
          />

          {state.view === "setup" && (
            <div className="main-layout">
              <div className="left-panel">
                <SessionSetup
                  health={state.health}
                  onStart={handleStartSession}
                />
              </div>
            </div>
          )}

          {state.view === "setup" && (
            <AlertBar
              alerts={visibleAlerts}
              escalations={state.escalations}
              onDismiss={handleDismissAlert}
              onEscalationAcknowledge={(id) => dispatch({ type: "RESOLVE_ESCALATION", escalationId: id, status: "acknowledged" })}
              onEscalationDismiss={(id) => dispatch({ type: "DISMISS_ESCALATION", escalationId: id })}
            />
          )}
        </>
      )}
    </div>
  );
}

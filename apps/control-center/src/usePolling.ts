/** Polling hooks for live backend status updates.

Provides useHealthPolling and useSessionPolling hooks that periodically
fetch status from the backend and dispatch state updates.
*/

import { useCallback, useEffect, useRef } from "react";
import {
  checkServiceHealth,
  getSession,
  getSessionStatus,
  getSessionSteps,
  ServiceHealthState,
} from "./unoApiClient";
import { OperatorState, OperatorAction, EvidenceData, ObservationData, createEvent, createAlert, deriveAgentPlan, deriveExecutionTrace } from "./operatorStore";

const HEALTH_POLL_MS = 10_000;
const SESSION_POLL_MS = 3_000;
const SERVICE_PORTS = [
  { name: "Orchestrator", port: 8100 },
  { name: "Adapter Web", port: 8104 },
  { name: "Adapter Windows", port: 8105 },
  { name: "Perception", port: 8103 },
  { name: "Decision", port: 8106 },
  { name: "Policy Guard", port: 8107 },
];

export function useHealthPolling(dispatch: React.Dispatch<OperatorAction>) {
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchHealth = useCallback(async () => {
    const results: Record<number, ServiceHealthState> = {};
    await Promise.all(
      SERVICE_PORTS.map(async (s) => {
        results[s.port] = await checkServiceHealth(s.port);
      }),
    );
    dispatch({ type: "SET_HEALTH", health: results, loading: false });

    const allOffline = Object.values(results).every((s) => s === "offline");
    dispatch({ type: "SET_CONNECTION", status: allOffline ? "disconnected" : "connected" });
  }, [dispatch]);

  useEffect(() => {
    fetchHealth();
    pollRef.current = setInterval(fetchHealth, HEALTH_POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchHealth]);
}

export function useSessionPolling(
  sessionId: string | null,
  dispatch: React.Dispatch<OperatorAction>,
  isRunning: boolean,
) {
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevStepsRef = useRef<number>(0);
  const prevErrorRef = useRef<string | undefined>(undefined);

  const fetchSession = useCallback(async () => {
    if (!sessionId) return;
    try {
      const [detail, st, stepList] = await Promise.all([
        getSession(sessionId),
        getSessionStatus(sessionId),
        getSessionSteps(sessionId),
      ]);

      dispatch({ type: "SET_SESSION", session: detail, status: st, steps: stepList });

      // Prefer backend strategy_snapshot over client-side derivation
      const snapshot = st.strategy_snapshot;
      if (snapshot) {
        const plan = {
          goal: snapshot.goal || "No goal",
          detectedState: (snapshot.detected_state || "unknown") as import("./operatorStore").AgentScreenState,
          hypothesis: snapshot.hypothesis || "No hypothesis",
          nextAction: snapshot.next_action || "No next action",
          whyAction: snapshot.why_action || "",
          confidence: snapshot.confidence ?? 0,
          blockedReason: snapshot.blocked_reason,
          lastExecuted: snapshot.last_executed,
          planSteps: ["Observe", "Interpret", "Evaluate", "Choose", "Execute"],
          source: "backend" as const,
          verification: snapshot.verification ? {
            delivery_status: snapshot.verification.delivery_status || "unknown",
            outcome_status: snapshot.verification.outcome_status || "unknown",
            expected_transition: snapshot.verification.expected_transition,
            observed_transition: snapshot.verification.observed_transition,
            action_category: snapshot.verification.action_category || "unknown",
            action_family: snapshot.verification.action_family || "unknown",
            observability_signals: snapshot.verification.observability_signals,
            evidence_strength: snapshot.verification.evidence_strength,
            summary: snapshot.verification.summary || "",
          } : undefined,
        };
        dispatch({ type: "SET_AGENT_PLAN", plan });
      } else {
        // Fallback to client-side derivation if no backend snapshot
        const plan = deriveAgentPlan(detail, st, stepList);
        dispatch({ type: "SET_AGENT_PLAN", plan });
      }
      const trace = deriveExecutionTrace(stepList);
      dispatch({ type: "SET_EXECUTION_TRACE", trace });

      // Detect new steps
      if (stepList.length > prevStepsRef.current) {
        const newSteps = stepList.slice(prevStepsRef.current);
        for (const step of newSteps) {
          dispatch({
            type: "ADD_EVENT",
            event: {
              id: `step-${step.correlation_id}-${step.step_name}`,
              type: step.step_name,
              message: step.result.success
                ? `${step.step_name} completed`
                : `${step.step_name} failed: ${step.result.error ?? "unknown"}`,
              ts: Date.now(),
              success: step.result.success,
            },
          });
        }
        prevStepsRef.current = stepList.length;
      }

      // Detect new errors
      if (st.error && st.error !== prevErrorRef.current) {
        dispatch({
          type: "ADD_ALERT",
          alert: {
            id: `error-${Date.now()}`,
            level: "error",
            message: st.error,
            ts: Date.now(),
            dismissed: false,
            source: "orchestrator",
          },
        });
        prevErrorRef.current = st.error;
      }

      // Detect flow state changes
      if (st.flow_state === "error" && st.last_recovery) {
        dispatch({
          type: "ADD_EVENT",
          event: createEvent(
            "recovery",
            `Recovery: ${st.last_recovery.action} — ${st.last_recovery.reason ?? ""}`,
            false,
          ),
        });
      }

      // Extract evidence from latest step
      const latestStep = stepList.length > 0 ? stepList[stepList.length - 1] : null;
      if (latestStep) {
        const evidenceData: EvidenceData = {
          timestamp: (latestStep as unknown as { timestamp_ms?: number }).timestamp_ms ?? Date.now(),
          adapterType: detail?.config?.adapter_type,
          gameType: detail?.config?.adapter_type === "windows" ? "UNO" : undefined,
          confidence: st.metrics ? Math.min(1, st.metrics.successful_steps / Math.max(1, st.metrics.total_steps)) : undefined,
          sources: detail?.adapter_bindings?.map((b) => b.adapter_type) ?? [],
        };
        dispatch({ type: "SET_EVIDENCE", evidence: evidenceData });
      }

      // Extract observation summary — prefer strategy_snapshot over metrics
      if (snapshot || st.metrics) {
        const conf = snapshot?.confidence ?? (st.metrics && st.metrics.total_steps > 0
          ? Math.min(1, st.metrics.successful_steps / Math.max(1, st.metrics.total_steps))
          : undefined);
        const obsData: ObservationData = {
          gameType: snapshot?.game_type ?? detail?.config?.adapter_type ?? undefined,
          currentPlayer: "—",
          handSize: undefined,
          drawPileCount: undefined,
          topCard: undefined,
          lastDecision: snapshot?.next_action ?? latestStep?.step_name ?? undefined,
          lastAction: snapshot?.last_executed ?? (latestStep?.result.success ? "Executed" : latestStep?.result.error ?? undefined),
          confidence: conf,
          discrepancy: snapshot?.blocked_reason ?? st.error ?? undefined,
        };
        dispatch({ type: "SET_OBSERVATION", observation: obsData });

        // Derive agent transparency from strategy_snapshot
        const agentState = (status?.flow_state === "active" ? "observing" :
          status?.flow_state === "error" ? "needs_help" : "waiting") as import("./operatorStore").AgentState;
        dispatch({
          type: "SET_AGENT_TRANSPARENCY",
          transparency: {
            currentState: agentState,
            currentPhase: status?.phase ?? "idle",
            confidence: snapshot?.confidence ?? 0,
            lastReason: snapshot?.next_action ?? "",
            nextStep: snapshot?.goal ?? "",
            decisionRationale: snapshot?.hypothesis ?? "",
            confidenceFactors: [],
          },
        });
      }
    } catch {
      /* session may have been deleted or backend offline */
    }
  }, [sessionId, dispatch]);

  useEffect(() => {
    if (!sessionId) return;
    prevStepsRef.current = 0;
    prevErrorRef.current = undefined;
    fetchSession();
    pollRef.current = setInterval(fetchSession, SESSION_POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [sessionId, fetchSession]);
}

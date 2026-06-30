import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  checkServiceHealth,
  getSession,
  getSessionStatus,
  getSessionSteps,
  listTraceSteps,
  ServiceHealthState,
  SessionDetail,
  OrchestratorStatusResponse,
  FlowStep,
  TraceStep,
} from "../../unoApiClient";

const HEALTH_POLL_MS = 10_000;
const SESSION_POLL_MS = 3_000;
const TRACE_POLL_MS = 3_000;

const SERVICE_PORTS = [
  { name: "Orchestrator", port: 8100 },
  { name: "Adapter Web", port: 8104 },
  { name: "Adapter Windows", port: 8105 },
  { name: "Perception", port: 8103 },
  { name: "Decision", port: 8106 },
  { name: "Policy Guard", port: 8107 },
];

export interface GameState {
  topCard: { color: string; value: string } | null;
  handCount: number | null;
  handCards: Array<{ color: string; value: string }> | null;
  direction: 1 | -1 | null;
  isYourTurn: boolean | null;
  screenState: "in_game" | "lobby" | "menu" | "unknown";
  confidence: number | null;
}

export interface Decision {
  nextAction: string | null;
  whyAction: string | null;
  guardResult: "allowed" | "blocked" | "unknown";
  confidence: number | null;
  blockedReason: string | null;
  goal: string | null;
  hypothesis: string | null;
}

export interface Verification {
  deliveryStatus: "delivered" | "failed" | "unknown";
  outcomeStatus: "confirmed" | "not_confirmed" | "unknown";
  expectedTransition: string | null;
  observedTransition: string | null;
  signals: string[] | null;
  evidenceStrength: string | null;
  actionFamily: string | null;
  summary: string | null;
}

function extractGameState(snapshot: OrchestratorStatusResponse["strategy_snapshot"]): GameState {
  if (!snapshot) {
    return { topCard: null, handCount: null, handCards: null, direction: null, isYourTurn: null, screenState: "unknown", confidence: null };
  }
  const detected = snapshot.detected_state ?? "unknown";
  return {
    topCard: null,
    handCount: null,
    handCards: null,
    direction: null,
    isYourTurn: null,
    screenState: (detected as GameState["screenState"]),
    confidence: snapshot.confidence ?? null,
  };
}

function extractDecision(snapshot: OrchestratorStatusResponse["strategy_snapshot"]): Decision {
  if (!snapshot) {
    return { nextAction: null, whyAction: null, guardResult: "unknown", confidence: null, blockedReason: null, goal: null, hypothesis: null };
  }
  return {
    nextAction: snapshot.next_action ?? null,
    whyAction: snapshot.why_action ?? null,
    guardResult: snapshot.blocked_reason ? "blocked" : "allowed",
    confidence: snapshot.confidence ?? null,
    blockedReason: snapshot.blocked_reason ?? null,
    goal: snapshot.goal ?? null,
    hypothesis: snapshot.hypothesis ?? null,
  };
}

function extractVerification(snapshot: OrchestratorStatusResponse["strategy_snapshot"]): Verification {
  const v = snapshot?.verification;
  if (!v) {
    return { deliveryStatus: "unknown", outcomeStatus: "unknown", expectedTransition: null, observedTransition: null, signals: null, evidenceStrength: null, actionFamily: null, summary: null };
  }
  return {
    deliveryStatus: (v.delivery_status as Verification["deliveryStatus"]) ?? "unknown",
    outcomeStatus: (v.outcome_status as Verification["outcomeStatus"]) ?? "unknown",
    expectedTransition: v.expected_transition ?? null,
    observedTransition: v.observed_transition ?? null,
    signals: v.observability_signals ?? null,
    evidenceStrength: v.evidence_strength ?? null,
    actionFamily: v.action_family ?? null,
    summary: v.summary ?? null,
  };
}

export function useOperatorPolling(sessionId: string | null) {
  const [health, setHealth] = useState<Record<number, ServiceHealthState>>({});
  const [healthLoading, setHealthLoading] = useState(true);
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [status, setStatus] = useState<OrchestratorStatusResponse | null>(null);
  const [steps, setSteps] = useState<FlowStep[]>([]);
  const [traceSteps, setTraceSteps] = useState<TraceStep[]>([]);
  const [lastUpdateTs, setLastUpdateTs] = useState(0);
  const [pollFailed, setPollFailed] = useState(false);
  const [stale, setStale] = useState(false);

  const prevStepsRef = useRef(0);
  const lastStepCountRef = useRef(0);

  const fetchHealth = useCallback(async () => {
    try {
      const results: Record<number, ServiceHealthState> = {};
      await Promise.all(
        SERVICE_PORTS.map(async (s) => {
          results[s.port] = await checkServiceHealth(s.port);
        }),
      );
      setHealth(results);
      setHealthLoading(false);
    } catch {
      setPollFailed(true);
    }
  }, []);

  const fetchSession = useCallback(async () => {
    if (!sessionId) return;
    try {
      const [s, st, stepList] = await Promise.all([
        getSession(sessionId),
        getSessionStatus(sessionId),
        getSessionSteps(sessionId),
      ]);
      setSession(s);
      setStatus(st);
      setSteps(stepList);
      setLastUpdateTs(Date.now());
      setPollFailed(false);
      const flowActive = st.flow_state === "active";
      const stepCount = stepList.length;
      if (flowActive && stepCount === lastStepCountRef.current && stepCount > 0) {
        setStale(true);
      } else if (flowActive && stepCount > lastStepCountRef.current) {
        setStale(false);
      } else if (!flowActive) {
        setStale(false);
      }
      lastStepCountRef.current = stepCount;
    } catch {
      setPollFailed(true);
    }
  }, [sessionId]);

  const fetchTrace = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await listTraceSteps(sessionId);
      setTraceSteps(data);
    } catch {
      // trace fetch failure is non-critical
    }
  }, [sessionId]);

  useEffect(() => {
    fetchHealth();
    const id = setInterval(fetchHealth, HEALTH_POLL_MS);
    return () => clearInterval(id);
  }, [fetchHealth]);

  useEffect(() => {
    if (!sessionId) return;
    fetchSession();
    fetchTrace();
    const sessionInterval = setInterval(fetchSession, SESSION_POLL_MS);
    const traceInterval = setInterval(fetchTrace, TRACE_POLL_MS);
    return () => {
      clearInterval(sessionInterval);
      clearInterval(traceInterval);
    };
  }, [sessionId, fetchSession, fetchTrace]);

  const gameState = useMemo(() => extractGameState(status?.strategy_snapshot), [status?.strategy_snapshot]);
  const decision = useMemo(() => extractDecision(status?.strategy_snapshot), [status?.strategy_snapshot]);
  const verification = useMemo(() => extractVerification(status?.strategy_snapshot), [status?.strategy_snapshot]);

  const isOnline = useMemo(() => {
    const vals = Object.values(health);
    return vals.length > 0 && vals.some(s => s === "healthy" || s === "degraded" || s === "unhealthy");
  }, [health]);

  return {
    health, healthLoading, isOnline,
    session, status, steps, traceSteps, stale,
    gameState, decision, verification,
    lastUpdateTs, pollFailed,
  };
}

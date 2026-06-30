/** Session history model — structured timeline for audit trail and replay prep. */

export interface SessionEvent {
  id: string;
  type: string;
  category: "system" | "agent" | "operator" | "escalation" | "handoff" | "approval";
  message: string;
  ts: number;
  metadata?: Record<string, unknown>;
  severity?: "info" | "warn" | "error";
}

export interface SessionSummary {
  sessionId: string;
  startTime: number;
  endTime?: number;
  outcome: "running" | "completed" | "stopped" | "error";
  totalEvents: number;
  escalationsRaised: number;
  escalationsResolved: number;
  operatorInterventions: number;
  actionsExecuted: number;
  actionsFailed: number;
  modeChanges: Array<{ from: string; to: string; ts: number }>;
  keyMoments: SessionEvent[];
}

export function createSessionEvent(
  type: string,
  category: SessionEvent["category"],
  message: string,
  metadata?: Record<string, unknown>,
  severity?: SessionEvent["severity"],
): SessionEvent {
  return {
    id: `sevt-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    type,
    category,
    message,
    ts: Date.now(),
    metadata,
    severity,
  };
}

export function buildSessionSummary(events: SessionEvent[], handoffs: Array<{ from: string; to: string; ts: number }>): SessionSummary {
  const escalations = events.filter((e) => e.category === "escalation");
  const operatorActions = events.filter((e) => e.category === "operator");
  const agentActions = events.filter((e) => e.category === "agent" && e.type === "action");
  const failedActions = events.filter((e) => e.category === "agent" && e.type === "action" && e.severity === "error");

  return {
    sessionId: "",
    startTime: events.length > 0 ? events[0].ts : Date.now(),
    outcome: "running",
    totalEvents: events.length,
    escalationsRaised: escalations.filter((e) => e.type === "escalation_raised").length,
    escalationsResolved: escalations.filter((e) => e.type === "escalation_resolved").length,
    operatorInterventions: operatorActions.length,
    actionsExecuted: agentActions.length,
    actionsFailed: failedActions.length,
    modeChanges: handoffs.map((h) => ({ from: h.from, to: h.to, ts: h.ts })),
    keyMoments: events.filter((e) =>
      ["escalation_raised", "mode_change", "action_failed", "session_start", "session_end"].includes(e.type),
    ),
  };
}

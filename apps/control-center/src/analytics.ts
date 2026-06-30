/** Analytics event schema — lightweight telemetry for future analysis.

All operator and agent events are logged with structured metadata
for later analysis of:
- Escalation rates by reason
- Approval / deny rates
- Manual takeover frequency
- Confidence distribution
- Action failure frequency
- Return-to-bot success/failure
*/

export interface AnalyticsEvent {
  event_type: string;
  ts: number;
  session_id: string;
  metadata: Record<string, unknown>;
  tags?: string[];
}

// Event types
export const ANALYTICS_EVENTS = {
  SESSION_START: "session_start",
  SESSION_END: "session_end",
  ACTION_EXECUTED: "action_executed",
  ACTION_FAILED: "action_failed",
  ACTION_APPROVED: "action_approved",
  ACTION_DENIED: "action_denied",
  ESCALATION_RAISED: "escalation_raised",
  ESCALATION_RESOLVED: "escalation_resolved",
  MODE_CHANGED: "mode_changed",
  MANUAL_TAKEOVER: "manual_takeover",
  RETURN_TO_BOT: "return_to_bot",
  CONFIDENCE_LOW: "confidence_low",
  CONFIDENCE_HIGH: "confidence_high",
  OPERATOR_HINT: "operator_hint",
  OBSERVATION_RECORDED: "observation_recorded",
} as const;

let _analyticsBuffer: AnalyticsEvent[] = [];
const MAX_BUFFER_SIZE = 500;

export function logAnalyticsEvent(
  eventType: string,
  sessionId: string,
  metadata: Record<string, unknown> = {},
  tags: string[] = [],
): void {
  _analyticsBuffer.push({
    event_type: eventType,
    ts: Date.now(),
    session_id: sessionId,
    metadata,
    tags,
  });

  // Keep buffer bounded
  if (_analyticsBuffer.length > MAX_BUFFER_SIZE) {
    _analyticsBuffer = _analyticsBuffer.slice(-MAX_BUFFER_SIZE / 2);
  }
}

export function getAnalyticsBuffer(): AnalyticsEvent[] {
  return [..._analyticsBuffer];
}

export function clearAnalyticsBuffer(): void {
  _analyticsBuffer = [];
}

// Convenience loggers
export function logActionExecuted(sessionId: string, actionType: string, success: boolean, confidence?: number) {
  logAnalyticsEvent(
    success ? ANALYTICS_EVENTS.ACTION_EXECUTED : ANALYTICS_EVENTS.ACTION_FAILED,
    sessionId,
    { action_type: actionType, success, confidence },
    [actionType],
  );
}

export function logEscalation(sessionId: string, reasonCode: string, severity: string) {
  logAnalyticsEvent(
    ANALYTICS_EVENTS.ESCALATION_RAISED,
    sessionId,
    { reason_code: reasonCode, severity },
    [reasonCode, severity],
  );
}

export function logModeChange(sessionId: string, from: string, to: string) {
  logAnalyticsEvent(
    ANALYTICS_EVENTS.MODE_CHANGED,
    sessionId,
    { from, to },
    [from, to],
  );
}

export function logConfidence(sessionId: string, level: "low" | "medium" | "high", value: number) {
  logAnalyticsEvent(
    level === "low" ? ANALYTICS_EVENTS.CONFIDENCE_LOW : ANALYTICS_EVENTS.CONFIDENCE_HIGH,
    sessionId,
    { level, value },
    [level],
  );
}

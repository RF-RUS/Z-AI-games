/** Operator client state store — structured state model for the operator UI.

Uses useReducer for predictable state updates. All state mutations
go through actions, making the state flow debuggable and extensible.

Phase C: Added control workflow state machine with:
- Auto / Assist / Manual modes
- Pending action approval queue
- Handoff tracking
- Audit trail
*/

import { SessionDetail, OrchestratorStatusResponse, FlowStep, ServiceHealthState } from "./unoApiClient";

// --- Control Workflow State Machine ---

export type ControlMode =
  | "auto"
  | "assist"
  | "manual"
  | "paused"
  | "awaiting_approval"
  | "returning_to_bot";

// Valid state transitions
const VALID_TRANSITIONS: Record<ControlMode, ControlMode[]> = {
  auto: ["assist", "manual", "paused"],
  assist: ["auto", "manual", "paused", "awaiting_approval"],
  manual: ["auto", "assist", "paused", "returning_to_bot"],
  paused: ["auto", "assist", "manual"],
  awaiting_approval: ["auto", "assist", "manual", "paused"],
  returning_to_bot: ["auto", "assist", "paused"],
};

export function canTransition(from: ControlMode, to: ControlMode): boolean {
  return VALID_TRANSITIONS[from]?.includes(to) ?? false;
}

// --- Types ---

export type ConnectionStatus = "connected" | "reconnecting" | "disconnected";

export interface PendingAction {
  id: string;
  actionType: string;
  description: string;
  reason: string;
  confidence: number;
  status: "pending" | "approved" | "denied" | "expired" | "superseded";
  createdAt: number;
  operatorComment?: string;
}

export interface ChatMessage {
  id: string;
  role: "operator" | "agent" | "system";
  text: string;
  ts: number;
  status?: "sent" | "acknowledged" | "error";
}

export interface Alert {
  id: string;
  level: "info" | "warn" | "error";
  message: string;
  ts: number;
  dismissed: boolean;
  source?: string;
}

export interface OperatorEvent {
  id: string;
  type: string;
  message: string;
  ts: number;
  success?: boolean;
}

// --- Escalation Model ---

export type EscalationSeverity = "low" | "medium" | "high" | "critical";
export type EscalationReasonCode =
  | "low_confidence_observation"
  | "multiple_legal_actions"
  | "repeated_action_failure"
  | "ambiguous_chat_message"
  | "window_lost"
  | "state_mismatch"
  | "low_confidence_decision"
  | "recovery_needed";

export interface Escalation {
  id: string;
  severity: EscalationSeverity;
  reasonCode: EscalationReasonCode;
  message: string;
  recommendedActions: string[];
  ts: number;
  status: "open" | "acknowledged" | "resolved" | "dismissed";
  relatedEvidence?: {
    screenshotPath?: string;
    confidence?: number;
    observation?: Record<string, unknown>;
  };
  operatorComment?: string;
}

// --- Agent Transparency Model ---

export type AgentState =
  | "observing"
  | "perceiving"
  | "deciding"
  | "executing"
  | "waiting"
  | "paused"
  | "needs_help";

export interface AgentTransparency {
  currentState: AgentState;
  currentPhase: string;
  lastReason: string;
  nextStep: string;
  decisionRationale: string;
  confidence: number;
  confidenceFactors: Array<{ source: string; value: number; label: string }>;
}

export interface EvidenceData {
  screenshotPath?: string | null;
  timestamp?: number;
  adapterType?: string;
  gameType?: string;
  confidence?: number;
  sources?: string[];
  observation?: Record<string, unknown>;
  beforeAction?: string | null;
  afterAction?: string | null;
}

export interface ObservationData {
  gameType?: string;
  currentPlayer?: string;
  topCard?: { color: string; value: string };
  handSize?: number;
  drawPileCount?: number;
  pendingDraw?: number;
  direction?: number;
  lastDecision?: string;
  lastAction?: string;
  discrepancy?: string;
  confidence?: number;
}

export interface HandoffRecord {
  id: string;
  from: ControlMode;
  to: ControlMode;
  ts: number;
  reason: string;
  syncStatus?: "pending" | "success" | "failed";
}

// --- Agent Strategy & Plan Model ---

export type AgentScreenState = "lobby" | "menu" | "in_game" | "launcher" | "unknown";

export interface AgentPlan {
  goal: string;
  detectedState: AgentScreenState;
  hypothesis: string;
  nextAction: string;
  whyAction: string;
  confidence: number;
  blockedReason?: string;
  lastExecuted?: string;
  planSteps: string[];
  source?: "backend" | "derived";
  verification?: {
    delivery_status: string;
    outcome_status: string;
    expected_transition?: string;
    observed_transition?: string;
    action_category: string;
    action_family: string;
    observability_signals?: string[];
    evidence_strength?: string;
    summary: string;
  };
}

export interface ExecutionTraceStep {
  phase: "observe" | "interpret" | "candidates" | "choose" | "execute" | "verify";
  message: string;
  ts: number;
  success?: boolean;
}

export interface OperatorState {
  // Connection
  connectionStatus: ConnectionStatus;
  health: Record<number, ServiceHealthState>;
  healthLoading: boolean;

  // Session
  sessionId: string | null;
  session: SessionDetail | null;
  status: OrchestratorStatusResponse | null;
  steps: FlowStep[];

  // Control workflow
  controlMode: ControlMode;
  pendingActions: PendingAction[];
  handoffHistory: HandoffRecord[];

  // Communication
  chatMessages: ChatMessage[];
  events: OperatorEvent[];
  alerts: Alert[];

  // Evidence & Observation
  evidence: EvidenceData | null;
  observation: ObservationData | null;

  // Escalation & Transparency
  escalations: Escalation[];
  agentTransparency: AgentTransparency | null;

  // Agent Strategy & Plan
  agentPlan: AgentPlan | null;
  executionTrace: ExecutionTraceStep[];

  // UI
  view: "setup" | "operator";
  lastRefresh: number;
}

// --- Actions ---

export type OperatorAction =
  | { type: "SET_VIEW"; view: OperatorState["view"] }
  | { type: "SET_HEALTH"; health: Record<number, ServiceHealthState>; loading: boolean }
  | { type: "SET_CONNECTION"; status: ConnectionStatus }
  | { type: "SET_SESSION"; session: SessionDetail | null; status: OrchestratorStatusResponse | null; steps: FlowStep[] }
  | { type: "SET_SESSION_ID"; sessionId: string | null }
  | { type: "TRANSITION_CONTROL"; to: ControlMode; reason: string }
  | { type: "ADD_CHAT_MESSAGE"; message: ChatMessage }
  | { type: "ADD_EVENT"; event: OperatorEvent }
  | { type: "ADD_ALERT"; alert: Alert }
  | { type: "DISMISS_ALERT"; alertId: string }
  | { type: "CLEAR_ALERTS" }
  | { type: "SET_EVIDENCE"; evidence: EvidenceData | null }
  | { type: "SET_OBSERVATION"; observation: ObservationData | null }
  | { type: "SET_AGENT_TRANSPARENCY"; transparency: AgentTransparency | null }
  | { type: "SET_AGENT_PLAN"; plan: AgentPlan | null }
  | { type: "ADD_TRACE_STEP"; step: ExecutionTraceStep }
  | { type: "CLEAR_TRACE" }
  | { type: "ADD_ESCALATION"; escalation: Escalation }
  | { type: "RESOLVE_ESCALATION"; escalationId: string; status: Escalation["status"]; comment?: string }
  | { type: "DISMISS_ESCALATION"; escalationId: string }
  | { type: "ADD_PENDING_ACTION"; action: PendingAction }
  | { type: "RESOLVE_PENDING_ACTION"; actionId: string; status: PendingAction["status"]; comment?: string }
  | { type: "ADD_HANDOFF"; handoff: HandoffRecord }
  | { type: "SET_HANDOFF_SYNC"; handoffId: string; syncStatus: HandoffRecord["syncStatus"] }
  | { type: "TOUCH_REFRESH" };

// --- Initial state ---

export const initialState: OperatorState = {
  connectionStatus: "disconnected",
  health: {},
  healthLoading: true,
  sessionId: null,
  session: null,
  status: null,
  steps: [],
  controlMode: "auto",
  pendingActions: [],
  handoffHistory: [],
  chatMessages: [],
  events: [],
  alerts: [],
  evidence: null,
  observation: null,
  escalations: [],
  agentTransparency: null,
  agentPlan: null,
  executionTrace: [],
  view: "setup",
  lastRefresh: 0,
};

// --- Reducer ---

export function operatorReducer(state: OperatorState, action: OperatorAction): OperatorState {
  switch (action.type) {
    case "SET_VIEW":
      return { ...state, view: action.view };

    case "SET_HEALTH":
      return { ...state, health: action.health, healthLoading: action.loading };

    case "SET_CONNECTION":
      return { ...state, connectionStatus: action.status };

    case "SET_SESSION_ID":
      return { ...state, sessionId: action.sessionId };

    case "SET_SESSION":
      return {
        ...state,
        session: action.session,
        status: action.status,
        steps: action.steps,
        lastRefresh: Date.now(),
      };

    case "TRANSITION_CONTROL": {
      if (!canTransition(state.controlMode, action.to)) {
        return state;
      }
      return {
        ...state,
        controlMode: action.to,
        handoffHistory: [
          ...state.handoffHistory,
          { id: `ho-${Date.now()}`, from: state.controlMode, to: action.to, ts: Date.now(), reason: action.reason },
        ],
      };
    }

    case "ADD_CHAT_MESSAGE":
      return { ...state, chatMessages: [...state.chatMessages, action.message] };

    case "ADD_EVENT":
      return { ...state, events: [...state.events, action.event].slice(-100) };

    case "ADD_ALERT":
      if (state.alerts.some((a) => a.message === action.alert.message && !a.dismissed)) {
        return state;
      }
      return { ...state, alerts: [...state.alerts, action.alert] };

    case "DISMISS_ALERT":
      return {
        ...state,
        alerts: state.alerts.map((a) =>
          a.id === action.alertId ? { ...a, dismissed: true } : a,
        ),
      };

    case "CLEAR_ALERTS":
      return { ...state, alerts: state.alerts.map((a) => ({ ...a, dismissed: true })) };

    case "SET_EVIDENCE":
      return { ...state, evidence: action.evidence };

    case "SET_OBSERVATION":
      return { ...state, observation: action.observation };

    case "SET_AGENT_TRANSPARENCY":
      return { ...state, agentTransparency: action.transparency };

    case "SET_AGENT_PLAN":
      return { ...state, agentPlan: action.plan };

    case "ADD_TRACE_STEP":
      return { ...state, executionTrace: [...state.executionTrace, action.step].slice(-30) };

    case "CLEAR_TRACE":
      return { ...state, executionTrace: [] };

    case "ADD_ESCALATION":
      if (state.escalations.some((e) => e.reasonCode === action.escalation.reasonCode && e.status === "open")) {
        return state;
      }
      return { ...state, escalations: [...state.escalations, action.escalation].slice(-20) };

    case "RESOLVE_ESCALATION":
      return {
        ...state,
        escalations: state.escalations.map((e) =>
          e.id === action.escalationId
            ? { ...e, status: action.status, operatorComment: action.comment }
            : e,
        ),
      };

    case "DISMISS_ESCALATION":
      return {
        ...state,
        escalations: state.escalations.map((e) =>
          e.id === action.escalationId ? { ...e, status: "dismissed" as const } : e,
        ),
      };

    case "ADD_PENDING_ACTION":
      return { ...state, pendingActions: [...state.pendingActions, action.action] };

    case "RESOLVE_PENDING_ACTION":
      return {
        ...state,
        pendingActions: state.pendingActions.map((a) =>
          a.id === action.actionId
            ? { ...a, status: action.status, operatorComment: action.comment }
            : a,
        ),
      };

    case "ADD_HANDOFF":
      return { ...state, handoffHistory: [...state.handoffHistory, action.handoff].slice(-20) };

    case "SET_HANDOFF_SYNC":
      return {
        ...state,
        handoffHistory: state.handoffHistory.map((h) =>
          h.id === action.handoffId ? { ...h, syncStatus: action.syncStatus } : h,
        ),
      };

    case "TOUCH_REFRESH":
      return { ...state, lastRefresh: Date.now() };

    default:
      return state;
  }
}

// --- Helpers ---

let _eventIdCounter = 0;
export function createEvent(type: string, message: string, success?: boolean): OperatorEvent {
  return { id: `evt-${++_eventIdCounter}`, type, message, ts: Date.now(), success };
}

let _alertIdCounter = 0;
export function createAlert(level: Alert["level"], message: string, source?: string): Alert {
  return { id: `alert-${++_alertIdCounter}`, level, message, ts: Date.now(), dismissed: false, source };
}

let _chatIdCounter = 0;
export function createChatMessage(role: ChatMessage["role"], text: string, status?: ChatMessage["status"]): ChatMessage {
  return { id: `chat-${++_chatIdCounter}`, role, text, ts: Date.now(), status };
}

let _pendingIdCounter = 0;
export function createPendingAction(
  actionType: string,
  description: string,
  reason: string,
  confidence: number,
): PendingAction {
  return {
    id: `pending-${++_pendingIdCounter}`,
    actionType,
    description,
    reason,
    confidence,
    status: "pending",
    createdAt: Date.now(),
  };
}

let _escalationIdCounter = 0;
export function createEscalation(
  severity: EscalationSeverity,
  reasonCode: EscalationReasonCode,
  message: string,
  recommendedActions: string[],
  relatedEvidence?: Escalation["relatedEvidence"],
): Escalation {
  return {
    id: `esc-${++_escalationIdCounter}`,
    severity,
    reasonCode,
    message,
    recommendedActions,
    ts: Date.now(),
    status: "open",
    relatedEvidence,
  };
}

// --- Pipeline Derivation Helpers (MVP) ---

import { SessionDetail, OrchestratorStatusResponse, FlowStep } from "./unoApiClient";

const PHASE_MAP: Record<string, string> = {
  observe: "observe",
  perceive: "interpret",
  legal_actions: "candidates",
  decide: "choose",
  execute: "execute",
  record: "recorded",  // honest: this is recording, not verification
};

export function deriveAgentPlan(
  session: SessionDetail | null,
  status: OrchestratorStatusResponse | null,
  steps: FlowStep[],
): AgentPlan | null {
  if (!session) return null;

  const lastStep = steps.length > 0 ? steps[steps.length - 1] : null;
  const lastDecision = steps.find((s) => s.step_name === "decide");
  const lastExecute = steps.find((s) => s.step_name === "execute");
  const error = status?.error;

  // Detected state from session phase — honest, not synthetic
  const detectedState: AgentScreenState =
    session.phase === "observe" ? "unknown" :
    session.flow_state === "active" ? "in_game" :
    session.flow_state === "error" ? "unknown" : "unknown";

  // Goal — from last step if available, otherwise honest unknown
  const goal = lastStep
    ? lastStep.result.success
      ? `${lastStep.step_name} completed`
      : `Retrying ${lastStep.step_name}`
    : steps.length === 0
      ? "Awaiting first observation"
      : "Unknown";

  // Hypothesis — from error or step result, not synthetic
  const hypothesis = error
    ? `Issue: ${error}`
    : lastStep?.result.success
      ? `Last step succeeded`
      : lastStep
        ? `Last step failed: ${lastStep.result.error ?? "unknown"}`
        : "No observations yet";

  // Next action — honest about what's available
  const nextAction = lastDecision?.result.success
    ? "Next action ready"
    : lastDecision
      ? "Decision pending"
      : steps.length === 0
        ? "Awaiting first observation"
        : "No decision yet";

  // Confidence from metrics — honest calculation
  const metrics = status?.metrics;
  const confidence = metrics && metrics.total_steps > 0
    ? Math.min(1, metrics.successful_steps / Math.max(1, metrics.total_steps))
    : 0;

  // Why action — from decision explanation if available
  const whyAction = lastDecision?.result.success
    ? "Selected by decision policy"
    : lastDecision
      ? "Decision not confirmed"
      : "No decision available";

  // Blocked reason — specific, not generic
  let blockedReason: string | undefined;
  if (error) {
    blockedReason = `Error: ${error}`;
  } else if (status?.last_recovery?.action === "stop") {
    blockedReason = "Agent stopped — recovery needed";
  } else if (session.flow_state === "paused") {
    blockedReason = "Session paused";
  } else if (steps.length === 0) {
    blockedReason = "Awaiting first observation";
  }

  return {
    goal,
    detectedState,
    hypothesis,
    nextAction,
    whyAction,
    confidence,
    blockedReason,
    lastExecuted: lastExecute?.result.success ? `${lastExecute.step_name} done` : undefined,
    planSteps: steps.length === 0
      ? ["Waiting for pipeline data"]
      : ["Observe", "Interpret", "Evaluate", "Choose", "Execute"],
  };
}

export function deriveExecutionTrace(steps: FlowStep[]): ExecutionTraceStep[] {
  let lastTs = 0;
  return steps.map((step, index) => {
    // Use step timestamp if available, otherwise use sequential ordering
    const stepTs = (step as unknown as { timestamp_ms?: number }).timestamp_ms;
    const ts = typeof stepTs === "number" && stepTs > 0
      ? stepTs
      : lastTs + (index + 1);  // sequential fallback

    lastTs = ts;

    return {
      phase: (PHASE_MAP[step.step_name] || step.step_name) as ExecutionTraceStep["phase"],
      message: step.result.success
        ? `${step.step_name} completed`
        : `${step.step_name} failed: ${step.result.error ?? "unknown"}`,
      ts,
      success: step.result.success,
    };
  });
}

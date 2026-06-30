import { SessionDetail, OrchestratorStatusResponse, FlowStep } from "./unoApiClient";
import { ControlMode, OperatorEvent } from "./operatorStore";

interface Props {
  session: SessionDetail | null;
  status: OrchestratorStatusResponse | null;
  steps: FlowStep[];
  controlMode: ControlMode;
  events: OperatorEvent[];
  evidence?: {
    screenshotPath?: string | null;
    timestamp?: number;
    adapterType?: string;
    gameType?: string;
    confidence?: number;
    sources?: string[];
    observation?: Record<string, unknown>;
  } | null;
  observation?: {
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
  } | null;
}

const FLOW_LABELS: Record<string, string> = {
  active: "Playing",
  idle: "Ready",
  paused: "Paused",
  error: "Error",
  attaching: "Connecting",
};

const FLOW_COLORS: Record<string, string> = {
  active: "#4caf50",
  idle: "#666",
  paused: "#ff9800",
  error: "#f44336",
  attaching: "#2196f3",
};

function getRecoveryAction(error?: string, recovery?: OrchestratorStatusResponse["last_recovery"]): string | null {
  const cls = recovery?.error_class;
  if (cls === "transient") return "This is a temporary issue. Click Tick to retry.";
  if (cls === "permanent") return "Adapter failed to connect. Check adapter service health and restart backend.";
  if (error?.includes("observe") || error?.includes("evidence")) return "Evidence capture failed. Test with: curl :8104/adapters/{id}/evidence";
  if (cls === "policy_blocked") return "Action was blocked by safety policy. Review confidence threshold or switch to Manual.";
  if (cls === "perception_low_confidence") return "Observation quality is low. Switch to Manual or re-observe.";
  return null;
}

export default function MonitorPanel({
  session,
  status,
  steps,
  controlMode,
  events,
  evidence,
  observation,
}: Props) {
  if (!session) {
    return (
      <div className="monitor-panel">
        <div className="monitor-empty">No active session</div>
      </div>
    );
  }

  const flowState = session.flow_state;
  const hasError = flowState === "error";
  const error = status?.error;
  const recovery = status?.last_recovery;
  const lastStep = steps.length > 0 ? steps[steps.length - 1] : null;
  const failedStep = steps.find(s => s.result?.success === false);
  const recoveryAction = getRecoveryAction(error, recovery);
  const metrics = status?.metrics;

  return (
    <div className="monitor-panel">
      {/* ERROR STATE — full-width banner with clear guidance */}
      {hasError && (
        <div className="monitor-error">
          <div className="monitor-error-head">
            <span className="monitor-error-icon">\u26A0</span>
            <div className="monitor-error-info">
              <span className="monitor-error-title">Something went wrong</span>
              {failedStep && (
                <span className="monitor-error-where">
                  Failed at step: <strong>{failedStep.step_name}</strong>
                </span>
              )}
            </div>
          </div>
          {failedStep?.result?.error && (
            <div className="monitor-error-msg">{failedStep.result.error}</div>
          )}
          {!failedStep && error && (
            <div className="monitor-error-msg">{error}</div>
          )}
          {recoveryAction && (
            <div className="monitor-error-action">
              <span className="monitor-error-action-label">What to do:</span>
              <span className="monitor-error-action-text">{recoveryAction}</span>
            </div>
          )}
        </div>
      )}

      {/* NORMAL STATE — clear primary + secondary info */}
      {!hasError && (
        <>
          {/* Primary: session state as a single readable line */}
          <div className="monitor-state">
            <span
              className="monitor-state-dot"
              style={{ backgroundColor: FLOW_COLORS[flowState] || "#666" }}
            />
            <span className="monitor-state-text">
              {FLOW_LABELS[flowState] || flowState}
            </span>
            {session.phase && session.phase !== "idle" && (
              <span className="monitor-state-phase">
                \u2014 {session.phase}
              </span>
            )}
          </div>

          {/* Secondary: compact info row */}
          <div className="monitor-info-row">
            <span className="monitor-info-item">
              Mode: <strong>{controlMode}</strong>
            </span>
            {metrics && metrics.total_steps > 0 && (
              <span className="monitor-info-item">
                Steps: <strong>{metrics.successful_steps}</strong>/{metrics.total_steps}
              </span>
            )}
            {observation?.confidence != null && (
              <span className={`monitor-info-confidence ${
                observation.confidence >= 0.8 ? "monitor-conf-high" :
                observation.confidence >= 0.5 ? "monitor-conf-mid" : "monitor-conf-low"
              }`}>
                Confidence: {Math.round(observation.confidence * 100)}%
              </span>
            )}
          </div>

          {/* Observation: what the agent sees */}
          {observation && (
            <div className="monitor-observation">
              {observation.topCard && (
                <div className="monitor-card-display">
                  <span className={`monitor-card-swatch card-${observation.topCard.color}`} />
                  <span className="monitor-card-name">{observation.topCard.value}</span>
                </div>
              )}
              {observation.handSize != null && (
                <span className="monitor-obs-detail">Hand: {observation.handSize} cards</span>
              )}
              {observation.lastDecision && (
                <span className="monitor-obs-detail">Next: {observation.lastDecision}</span>
              )}
            </div>
          )}

          {/* Last step: what just happened */}
          {lastStep && (
            <div className={`monitor-last-step ${lastStep.result.success ? "monitor-step-ok" : "monitor-step-fail"}`}>
              <span className="monitor-step-label">Last step:</span>
              <span className="monitor-step-name">{lastStep.step_name}</span>
              {lastStep.result.latency_ms > 0 && (
                <span className="monitor-step-time">{lastStep.result.latency_ms}ms</span>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

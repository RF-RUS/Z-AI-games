import { SessionDetail } from "./unoApiClient";
import { ControlMode } from "./operatorStore";

interface Props {
  flowState: string;
  isRunning: boolean;
  isPaused: boolean;
  hasError: boolean;
  controlMode: ControlMode;
  metrics?: { total_steps: number; successful_steps: number; failed_steps: number };
  attachedBindings: Array<{ adapter_type: string; attached?: boolean; profile_id?: string | null }>;
  onTick: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onBackToSetup: () => void;
}

export default function ControlPanel({
  flowState,
  isRunning,
  isPaused,
  hasError,
  controlMode,
  metrics,
  attachedBindings,
  onTick,
  onPause,
  onResume,
  onStop,
  onBackToSetup,
}: Props) {
  const canControl = flowState === "active" || flowState === "paused" || flowState === "idle";

  return (
    <div className="control-panel">
      <h2>Control</h2>

      <div className="control-buttons">
        {!isRunning && !isPaused && (
          <button type="button" className="btn btn-primary" onClick={onTick} disabled={!canControl} title="Start or tick (F5)">
            ▶ Start
          </button>
        )}
        {isRunning && (
          <button type="button" className="btn btn-warning" onClick={onPause} title="Pause session (F6)">
            ⏸ Pause
          </button>
        )}
        {isPaused && (
          <button type="button" className="btn btn-primary" onClick={onResume} title="Resume session (F7)">
            ▶ Resume
          </button>
        )}
        <button type="button" className="btn btn-danger" onClick={onStop} disabled={!canControl && !isRunning} title="Stop session">
          ⏹ Stop
        </button>
        <button type="button" className="btn btn-secondary" onClick={onBackToSetup} title="Create new session">
          ↩ New Session
        </button>
      </div>

      <div className="control-info">
        <div className="info-row">
          <span className="info-label">Status</span>
          <span className={`info-value flow-${flowState}`}>{flowState}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Mode</span>
          <span className="info-value">{controlMode}</span>
        </div>
        {metrics && (
          <div className="info-row">
            <span className="info-label">Steps</span>
            <span className="info-value">
              {metrics.total_steps} ({metrics.successful_steps} ok, {metrics.failed_steps} fail)
            </span>
          </div>
        )}
      </div>

      <div className="adapter-info">
        <h4>Adapter</h4>
        {attachedBindings.length === 0 ? (
          <p className="muted">Not connected</p>
        ) : (
          <ul>
            {attachedBindings.map((b, i) => (
              <li key={i}>
                <span className={`status-dot ${b.attached ? "online" : "offline"}`} />
                {b.adapter_type} {b.profile_id ? `(${b.profile_id})` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

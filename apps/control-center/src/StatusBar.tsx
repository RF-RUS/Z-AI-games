import { ServiceHealthState } from "./unoApiClient";
import { ControlMode } from "./operatorStore";

interface Props {
  health: Record<number, ServiceHealthState>;
  healthLoading: boolean;
  flowState: string;
  adapterType?: string;
  gameType?: string;
  controlMode: ControlMode;
  onModeChange: (mode: ControlMode) => void;
  currentPhase?: string;
  sessionHealth?: "healthy" | "degraded" | "error" | null;
}

const FLOW_COLORS: Record<string, string> = {
  active: "#4caf50",
  idle: "#666",
  paused: "#ff9800",
  error: "#f44336",
  attaching: "#2196f3",
};

const ADAPTER_LABELS: Record<string, string> = {
  web: "Web",
  windows: "Windows",
  mock: "Mock",
};

const PHASE_LABELS: Record<string, string> = {
  observe: "Observe",
  perceive: "Perceive",
  decide: "Decide",
  execute: "Execute",
};

export default function StatusBar({
  health,
  healthLoading,
  flowState,
  adapterType,
  controlMode,
  onModeChange,
  currentPhase,
  sessionHealth,
}: Props) {
  const healthyCount = Object.values(health).filter(s => s === "healthy" || s === "degraded").length;
  const totalCount = Object.keys(health).length;
  const allHealthy = !healthLoading && healthyCount === totalCount;

  return (
    <header className="status-bar">
      <div className="status-bar-left">
        <span className="app-title">Game Agent</span>
        <span
          className="status-dot"
          style={{ backgroundColor: allHealthy ? "#4caf50" : healthyCount > 0 ? "#ff9800" : "#666" }}
          title={`${healthyCount}/${totalCount} services online`}
        />
      </div>

      <div className="status-bar-center">
        {/* Primary: session flow state — always readable */}
        <span
          className="status-flow-badge"
          style={{ backgroundColor: FLOW_COLORS[flowState] || "#666" }}
        >
          {flowState === "active" ? "Playing" :
           flowState === "idle" ? "Ready" :
           flowState === "paused" ? "Paused" :
           flowState === "error" ? "Error" :
           flowState === "attaching" ? "Connecting" :
           flowState}
        </span>

        {/* Secondary: current phase — only when meaningful */}
        {currentPhase && flowState === "active" && PHASE_LABELS[currentPhase] && (
          <span className="status-phase-label">
            {PHASE_LABELS[currentPhase]}
          </span>
        )}

        {/* Adapter type — readable label */}
        {adapterType && ADAPTER_LABELS[adapterType] && (
          <span className="status-adapter-label">
            {ADAPTER_LABELS[adapterType]}
          </span>
        )}

        {/* Session health — only when degraded/error */}
        {sessionHealth && sessionHealth !== "healthy" && (
          <span className={`status-health-badge status-health-${sessionHealth}`}>
            {sessionHealth === "degraded" ? "Degraded" : "Unhealthy"}
          </span>
        )}
      </div>

      <div className="status-bar-right">
        <div className="status-mode-group">
          {(["auto", "assist", "manual"] as ControlMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              className={`status-mode-btn ${controlMode === mode ? "status-mode-active" : ""}`}
              onClick={() => onModeChange(mode)}
              title={
                mode === "auto" ? "Bot plays autonomously" :
                mode === "assist" ? "Bot proposes, you confirm" :
                "You play, bot observes"
              }
            >
              {mode === "auto" ? "Auto" : mode === "assist" ? "Assist" : "Manual"}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}

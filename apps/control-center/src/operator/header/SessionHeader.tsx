import FlowStateBadge from "./FlowStateBadge";
import PhaseLabel from "./PhaseLabel";
import ModeSwitcher from "./ModeSwitcher";
import FreshnessIndicator from "./FreshnessIndicator";
import StatusDot from "../shared/StatusDot";
import { ControlMode } from "../../operatorStore";
import { DataFreshness } from "../hooks/useStaleDetection";

interface Props {
  flowState: string;
  phase: string | null;
  adapterType: string | null;
  controlMode: ControlMode;
  isOnline: boolean;
  freshness: DataFreshness;
  lastUpdateTs: number;
  onTick: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onNewSession: () => void;
  onModeChange: (mode: ControlMode) => void;
}

const ADAPTER_LABELS: Record<string, string> = {
  web: "Web",
  windows: "Windows",
  mock: "Mock",
};

export default function SessionHeader({
  flowState, phase, adapterType, controlMode, isOnline,
  freshness, lastUpdateTs,
  onTick, onPause, onResume, onStop, onNewSession, onModeChange,
}: Props) {
  return (
    <header className="session-header">
      <div className="header-left">
        <span className="header-title">Game Agent</span>
        <StatusDot status={isOnline ? "healthy" : "offline"} />
        <FlowStateBadge flowState={flowState} />
        <PhaseLabel phase={phase} />
        {adapterType && ADAPTER_LABELS[adapterType] && (
          <span className="adapter-badge">{ADAPTER_LABELS[adapterType]}</span>
        )}
        <FreshnessIndicator freshness={freshness} lastUpdateTs={lastUpdateTs} />
      </div>
      <div className="header-center">
        <ModeSwitcher mode={controlMode} onModeChange={onModeChange} />
      </div>
      <div className="header-right">
        <button type="button" className="header-btn" onClick={onTick} title="Manual tick (F5)">Tick</button>
        {flowState === "active" ? (
          <button type="button" className="header-btn" onClick={onPause} title="Pause (F6)">Pause</button>
        ) : flowState === "paused" ? (
          <button type="button" className="header-btn" onClick={onResume} title="Resume (F7)">Resume</button>
        ) : null}
        <button type="button" className="header-btn header-btn-danger" onClick={onStop}>Stop</button>
        <button type="button" className="header-btn" onClick={onNewSession}>New</button>
      </div>
    </header>
  );
}

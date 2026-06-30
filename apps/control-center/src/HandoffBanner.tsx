import { ControlMode, HandoffRecord } from "./operatorStore";

interface Props {
  controlMode: ControlMode;
  handoffHistory: HandoffRecord[];
  onReturnToBot: () => void;
  onResume: () => void;
}

const MODE_LABELS: Record<ControlMode, { label: string; color: string; icon: string }> = {
  auto: { label: "Bot Playing", color: "#4caf50", icon: "🤖" },
  assist: { label: "Assist Mode", color: "#ff9800", icon: "🤝" },
  manual: { label: "You're in Control", color: "#2196f3", icon: "🖐" },
  paused: { label: "Paused", color: "#9e9e9e", icon: "⏸" },
  awaiting_approval: { label: "Awaiting Approval", color: "#ff9800", icon: "⏳" },
  returning_to_bot: { label: "Resyncing...", color: "#9c27b0", icon: "🔄" },
};

export default function HandoffBanner({ controlMode, handoffHistory, onReturnToBot, onResume }: Props) {
  const modeInfo = MODE_LABELS[controlMode];
  const lastHandoff = handoffHistory[handoffHistory.length - 1];

  return (
    <div className="handoff-banner" style={{ borderColor: modeInfo.color }}>
      <div className="handoff-status">
        <span className="handoff-icon">{modeInfo.icon}</span>
        <span className="handoff-label" style={{ color: modeInfo.color }}>
          {modeInfo.label}
        </span>
        {lastHandoff && (
          <span className="handoff-detail">
            Since {new Date(lastHandoff.ts).toLocaleTimeString()} — {lastHandoff.reason}
          </span>
        )}
      </div>

      <div className="handoff-actions">
        {controlMode === "manual" && (
          <button type="button" className="btn btn-primary btn-sm" onClick={onReturnToBot}>
            🔄 Return to Bot
          </button>
        )}
        {controlMode === "paused" && (
          <button type="button" className="btn btn-primary btn-sm" onClick={onResume}>
            ▶ Resume
          </button>
        )}
        {controlMode === "auto" && (
          <span className="handoff-hint">Bot is playing autonomously</span>
        )}
        {controlMode === "assist" && (
          <span className="handoff-hint">Bot proposes actions for your approval</span>
        )}
      </div>
    </div>
  );
}

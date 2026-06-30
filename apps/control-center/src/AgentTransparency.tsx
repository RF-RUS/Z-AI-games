import { AgentTransparency as AgentTransparencyData, AgentState } from "./operatorStore";

interface Props {
  transparency: AgentTransparencyData | null;
}

const STATE_CONFIG: Record<AgentState, { label: string; icon: string; color: string }> = {
  observing: { label: "Observing", icon: "👁", color: "#4caf50" },
  perceiving: { label: "Analyzing", icon: "🔍", color: "#4caf50" },
  deciding: { label: "Thinking", icon: "🧠", color: "#ff9800" },
  executing: { label: "Acting", icon: "⚡", color: "#4caf50" },
  waiting: { label: "Waiting", icon: "⏳", color: "#9e9e9e" },
  paused: { label: "Paused", icon: "⏸", color: "#9e9e9e" },
  needs_help: { label: "Needs Help", icon: "🙋", color: "#f44336" },
};

function getConfidenceBar(confidence: number): { width: string; color: string } {
  const pct = Math.round(confidence * 100);
  if (pct >= 80) return { width: `${pct}%`, color: "#4caf50" };
  if (pct >= 50) return { width: `${pct}%`, color: "#ff9800" };
  return { width: `${pct}%`, color: "#f44336" };
}

export default function AgentTransparencyPanel({ transparency }: Props) {
  if (!transparency) {
    return (
      <div className="transparency-panel">
        <h3>Agent Status</h3>
        <p className="muted">Waiting for agent data...</p>
      </div>
    );
  }

  const stateConfig = STATE_CONFIG[transparency.currentState];
  const confBar = getConfidenceBar(transparency.confidence);

  return (
    <div className="transparency-panel">
      <h3>Agent Status</h3>

      <div className="transparency-state">
        <span className="transparency-icon">{stateConfig.icon}</span>
        <span className="transparency-label" style={{ color: stateConfig.color }}>
          {stateConfig.label}
        </span>
        <span className="transparency-phase">{transparency.currentPhase}</span>
      </div>

      <div className="transparency-reason">
        <span className="transparency-label">Why</span>
        <span className="transparency-text">{transparency.lastReason || "—"}</span>
      </div>

      <div className="transparency-next">
        <span className="transparency-label">Next</span>
        <span className="transparency-text">{transparency.nextStep || "—"}</span>
      </div>

      <div className="transparency-confidence">
        <span className="transparency-label">Confidence</span>
        <div className="confidence-bar-container">
          <div
            className="confidence-bar-fill"
            style={{ width: confBar.width, backgroundColor: confBar.color }}
          />
        </div>
        <span className="confidence-value">{Math.round(transparency.confidence * 100)}%</span>
      </div>

      {transparency.confidenceFactors.length > 0 && (
        <div className="transparency-factors">
          <span className="transparency-label">Factors</span>
          {transparency.confidenceFactors.map((factor, i) => (
            <div key={i} className="factor-item">
              <span className="factor-source">{factor.source}</span>
              <span className="factor-label">{factor.label}</span>
              <span className="factor-value">{Math.round(factor.value * 100)}%</span>
            </div>
          ))}
        </div>
      )}

      <div className="transparency-rationale">
        <span className="transparency-label">Decision</span>
        <span className="transparency-text">{transparency.decisionRationale || "—"}</span>
      </div>
    </div>
  );
}

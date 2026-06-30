interface ObservationData {
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

interface Props {
  observation: ObservationData | null;
}

function getConfidenceLevel(confidence?: number): { label: string; color: string; icon: string } {
  if (confidence === undefined) return { label: "Unknown", color: "#9e9e9e", icon: "❓" };
  if (confidence >= 0.8) return { label: "High", color: "#4caf50", icon: "✅" };
  if (confidence >= 0.5) return { label: "Medium", color: "#ff9800", icon: "⚠️" };
  return { label: "Low", color: "#f44336", icon: "🔴" };
}

export default function ObservationSummary({ observation }: Props) {
  if (!observation) {
    return (
      <div className="observation-summary">
        <h3>Observation</h3>
        <p className="muted">No observation data available.</p>
      </div>
    );
  }

  const conf = getConfidenceLevel(observation.confidence);

  return (
    <div className="observation-summary">
      <h3>Observation</h3>

      <div className="obs-grid">
        <div className="obs-item">
          <span className="obs-label">Game</span>
          <span className="obs-value">{observation.gameType ?? "—"}</span>
        </div>
        <div className="obs-item">
          <span className="obs-label">Turn</span>
          <span className="obs-value">{observation.currentPlayer ?? "—"}</span>
        </div>
        {observation.topCard && (
          <div className="obs-item">
            <span className="obs-label">Top Card</span>
            <span className="obs-value">
              <span className={`card-color card-${observation.topCard.color}`} />
              {observation.topCard.value}
            </span>
          </div>
        )}
        <div className="obs-item">
          <span className="obs-label">Hand</span>
          <span className="obs-value">{observation.handSize ?? "—"} cards</span>
        </div>
        <div className="obs-item">
          <span className="obs-label">Draw Pile</span>
          <span className="obs-value">{observation.drawPileCount ?? "—"}</span>
        </div>
        {observation.pendingDraw ? (
          <div className="obs-item warn">
            <span className="obs-label">Pending Draw</span>
            <span className="obs-value">{observation.pendingDraw}</span>
          </div>
        ) : null}
        <div className="obs-item">
          <span className="obs-label">Direction</span>
          <span className="obs-value">{observation.direction === 1 ? "→ Clockwise" : "← Counter"}</span>
        </div>
      </div>

      <div className="obs-confidence">
        <span className="obs-label">Confidence</span>
        <span className="confidence-badge" style={{ color: conf.color }}>
          {conf.icon} {conf.label}
        </span>
      </div>

      {observation.lastDecision && (
        <div className="obs-decision">
          <span className="obs-label">Last Decision</span>
          <span className="obs-value">{observation.lastDecision}</span>
        </div>
      )}

      {observation.lastAction && (
        <div className="obs-action">
          <span className="obs-label">Last Action</span>
          <span className="obs-value">{observation.lastAction}</span>
        </div>
      )}

      {observation.discrepancy && (
        <div className="obs-discrepancy">
          <span className="obs-label">⚠️ Discrepancy</span>
          <span className="obs-value warn">{observation.discrepancy}</span>
        </div>
      )}
    </div>
  );
}

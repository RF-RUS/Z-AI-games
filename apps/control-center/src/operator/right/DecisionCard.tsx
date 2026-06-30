import ConfidenceBar from "../shared/ConfidenceBar";
import { Decision } from "../hooks/useOperatorPolling";

interface Props {
  decision: Decision;
}

export default function DecisionCard({ decision }: Props) {
  if (!decision.nextAction && !decision.blockedReason) {
    return (
      <div className="decision-card decision-empty">
        <h4>Next Action</h4>
        <p className="decision-hint">Waiting for decision...</p>
      </div>
    );
  }

  return (
    <div className="decision-card">
      <h4>Next Action</h4>
      {decision.blockedReason ? (
        <div className="decision-blocked">
          <span className="decision-blocked-icon">\u26A0</span>
          <span className="decision-blocked-text">{decision.blockedReason}</span>
        </div>
      ) : (
        <>
          <div className="decision-action">{decision.nextAction}</div>
          {decision.whyAction && (
            <div className="decision-why">Why: {decision.whyAction}</div>
          )}
        </>
      )}
      <div className="decision-meta">
        <span className={`decision-guard ${decision.guardResult === "blocked" ? "guard-blocked" : "guard-allowed"}`}>
          Guard: {decision.guardResult === "blocked" ? "\u2717 blocked" : "\u2713 allowed"}
        </span>
        <ConfidenceBar value={decision.confidence} size="sm" showLabel />
      </div>
    </div>
  );
}

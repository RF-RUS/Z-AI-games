import { Verification } from "../hooks/useOperatorPolling";

interface Props {
  verification: Verification;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  delivered: { label: "Delivered", color: "#4caf50", icon: "\u2713" },
  failed: { label: "Failed", color: "#f44336", icon: "\u2717" },
  unknown: { label: "Unknown", color: "#666", icon: "\u2014" },
  confirmed: { label: "Confirmed", color: "#4caf50", icon: "\u2713" },
  not_confirmed: { label: "Not confirmed", color: "#ff9800", icon: "?" },
};

export default function VerificationCard({ verification }: Props) {
  const delivery = STATUS_CONFIG[verification.deliveryStatus] || STATUS_CONFIG.unknown;
  const outcome = STATUS_CONFIG[verification.outcomeStatus] || STATUS_CONFIG.unknown;

  return (
    <div className="verification-card">
      <h4>Verification</h4>
      <div className="verification-rows">
        <div className="verification-row">
          <span className="verification-dot" style={{ backgroundColor: delivery.color }}>{delivery.icon}</span>
          <span className="verification-label">Delivery:</span>
          <span className="verification-value">{delivery.label}</span>
        </div>
        <div className="verification-row">
          <span className="verification-dot" style={{ backgroundColor: outcome.color }}>{outcome.icon}</span>
          <span className="verification-label">Outcome:</span>
          <span className="verification-value">{outcome.label}</span>
        </div>
        {verification.observedTransition && (
          <div className="verification-row">
            <span className="verification-label">Transition:</span>
            <span className="verification-value verification-transition">
              {verification.expectedTransition && (
                <span className="verification-expected">{verification.expectedTransition} \u2192 </span>
              )}
              {verification.observedTransition}
            </span>
          </div>
        )}
        {verification.signals && verification.signals.length > 0 && (
          <div className="verification-row">
            <span className="verification-label">Signals:</span>
            <span className="verification-value">{verification.signals.length} ({verification.signals.join(", ")})</span>
          </div>
        )}
        {verification.summary && (
          <div className="verification-summary">{verification.summary}</div>
        )}
      </div>
    </div>
  );
}

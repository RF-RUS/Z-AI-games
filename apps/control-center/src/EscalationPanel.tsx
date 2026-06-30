import { Escalation, EscalationSeverity } from "./operatorStore";

interface Props {
  escalations: Escalation[];
  onAcknowledge: (id: string) => void;
  onDismiss: (id: string) => void;
  onTakeHint: (id: string, hint: string) => void;
  onSwitchToManual: () => void;
}

const SEVERITY_CONFIG: Record<EscalationSeverity, { icon: string; color: string; label: string }> = {
  low: { icon: "💡", color: "#ff9800", label: "Notice" },
  medium: { icon: "⚠️", color: "#ff9800", label: "Uncertain" },
  high: { icon: "🔶", color: "#f44336", label: "Needs Help" },
  critical: { icon: "🚨", color: "#f44336", label: "Critical" },
};

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function EscalationPanel({
  escalations,
  onAcknowledge,
  onDismiss,
  onTakeHint,
  onSwitchToManual,
}: Props) {
  const openEscalations = escalations.filter((e) => e.status === "open");

  if (openEscalations.length === 0) return null;

  return (
    <div className="escalation-panel">
      <h3>Agent Needs Help</h3>
      {openEscalations.map((esc) => {
        const config = SEVERITY_CONFIG[esc.severity];
        return (
          <div key={esc.id} className="escalation-card" style={{ borderColor: config.color }}>
            <div className="escalation-header">
              <span className="escalation-icon">{config.icon}</span>
              <span className="escalation-severity" style={{ color: config.color }}>
                {config.label}
              </span>
              <span className="escalation-time">{formatTime(esc.ts)}</span>
            </div>

            <p className="escalation-message">{esc.message}</p>

            {esc.recommendedActions.length > 0 && (
              <div className="escalation-actions-hint">
                <span className="escalation-label">Suggested:</span>
                {esc.recommendedActions.map((action, i) => (
                  <button
                    key={i}
                    type="button"
                    className="btn btn-sm btn-secondary"
                    onClick={() => onTakeHint(esc.id, action)}
                  >
                    {action}
                  </button>
                ))}
              </div>
            )}

            <div className="escalation-actions">
              <button
                type="button"
                className="btn btn-sm btn-primary"
                onClick={() => onAcknowledge(esc.id)}
              >
                ✓ Acknowledge
              </button>
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={onSwitchToManual}
              >
                🖐 Take Control
              </button>
              <button
                type="button"
                className="btn btn-sm btn-danger"
                onClick={() => onDismiss(esc.id)}
              >
                Dismiss
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

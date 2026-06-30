import { Escalation } from "./operatorStore";

interface Alert {
  id: string;
  level: "info" | "warn" | "error";
  message: string;
  dismissed: boolean;
  source?: string;
}

interface Props {
  alerts: Alert[];
  escalations: Escalation[];
  onDismiss: (index: number) => void;
  onEscalationAcknowledge: (id: string) => void;
  onEscalationDismiss: (id: string) => void;
}

export default function AlertBar({
  alerts,
  escalations,
  onDismiss,
  onEscalationAcknowledge,
  onEscalationDismiss,
}: Props) {
  const visibleAlerts = alerts.filter((a) => !a.dismissed);
  const openEscalations = escalations.filter((e) => e.status === "open");

  if (visibleAlerts.length === 0 && openEscalations.length === 0) return null;

  return (
    <div className="alert-bar">
      {openEscalations.length > 0 && (
        <div className="alert alert-escalation">
          <span className="alert-icon">🚨</span>
          <span className="alert-message">
            {openEscalations.length} escalation{openEscalations.length > 1 ? "s" : ""} requiring attention
          </span>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={() => onEscalationAcknowledge(openEscalations[0].id)}
          >
            View
          </button>
        </div>
      )}

      {visibleAlerts.map((alert, i) => (
        <div key={alert.id} className={`alert alert-${alert.level}`}>
          <span className="alert-icon">
            {alert.level === "error" ? "🔴" : alert.level === "warn" ? "🟡" : "🔵"}
          </span>
          <span className="alert-message">{alert.message}</span>
          <button
            type="button"
            className="alert-dismiss"
            onClick={() => onDismiss(i)}
            title="Dismiss"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

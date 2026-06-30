import { Escalation } from "../../operatorStore";

interface Props {
  escalations: Escalation[];
  onAcknowledge: (id: string) => void;
  onTakeControl: () => void;
}

const SEVERITY_CONFIG: Record<string, { icon: string; color: string }> = {
  low: { icon: "\u{1F4A1}", color: "#ff9800" },
  medium: { icon: "\u26A0", color: "#ff9800" },
  high: { icon: "\u{1F534}", color: "#f44336" },
  critical: { icon: "\u{1F6A8}", color: "#f44336" },
};

export default function AlertStack({ escalations, onAcknowledge, onTakeControl }: Props) {
  const open = escalations.filter(e => e.status === "open");
  if (open.length === 0) return null;

  return (
    <div className="alert-stack">
      {open.map(esc => {
        const config = SEVERITY_CONFIG[esc.severity] || SEVERITY_CONFIG.low;
        return (
          <div key={esc.id} className="alert-card" style={{ borderLeftColor: config.color }}>
            <span className="alert-icon">{config.icon}</span>
            <div className="alert-content">
              <span className="alert-message">{esc.message}</span>
              <div className="alert-actions">
                <button type="button" className="alert-btn" onClick={() => onAcknowledge(esc.id)}>
                  Acknowledge
                </button>
                <button type="button" className="alert-btn alert-btn-primary" onClick={onTakeControl}>
                  Take Control
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

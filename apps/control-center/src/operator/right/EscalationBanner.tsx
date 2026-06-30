import { Escalation } from "../../operatorStore";

interface Props {
  escalations: Escalation[];
  onAcknowledge: (id: string) => void;
  onTakeControl: () => void;
  onDismiss: (id: string) => void;
}

export default function EscalationBanner({ escalations, onAcknowledge, onTakeControl, onDismiss }: Props) {
  const open = escalations.filter(e => e.status === "open");
  if (open.length === 0) return null;

  return (
    <div className="escalation-banner">
      <h4>Agent Needs Help</h4>
      {open.map(esc => (
        <div key={esc.id} className="escalation-item">
          <span className="escalation-message">{esc.message}</span>
          <div className="escalation-actions">
            <button type="button" className="escalation-btn" onClick={() => onAcknowledge(esc.id)}>Acknowledge</button>
            <button type="button" className="escalation-btn escalation-btn-primary" onClick={onTakeControl}>Take Control</button>
            <button type="button" className="escalation-btn" onClick={() => onDismiss(esc.id)}>Dismiss</button>
          </div>
        </div>
      ))}
    </div>
  );
}

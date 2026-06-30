import { PendingAction } from "./operatorStore";

interface Props {
  pendingActions: PendingAction[];
  onApprove: (actionId: string) => void;
  onDeny: (actionId: string, comment?: string) => void;
  onTakeOver: () => void;
}

export default function ApprovalPanel({ pendingActions, onApprove, onDeny, onTakeOver }: Props) {
  const activePending = pendingActions.filter((a) => a.status === "pending");

  if (activePending.length === 0) {
    return (
      <div className="approval-panel">
        <div className="approval-empty">
          <p className="muted">No pending actions. Agent is waiting for your approval.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="approval-panel">
      <h3>Pending Actions</h3>
      {activePending.map((action) => (
        <div key={action.id} className="approval-card">
          <div className="approval-header">
            <span className="approval-type">{action.actionType}</span>
            <span className="approval-confidence">
              {Math.round(action.confidence * 100)}% confident
            </span>
          </div>
          <p className="approval-description">{action.description}</p>
          <p className="approval-reason">{action.reason}</p>
          <div className="approval-actions">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => onApprove(action.id)}
            >
              ✓ Approve
            </button>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              onClick={() => onDeny(action.id)}
            >
              ✗ Deny
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onTakeOver}
            >
              🖐 Take Over
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

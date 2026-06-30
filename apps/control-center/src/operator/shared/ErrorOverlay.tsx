interface Props {
  error: string | null;
  failedStep: string | null;
  recoveryAction: string | null;
  onDismiss: () => void;
}

export default function ErrorOverlay({ error, failedStep, recoveryAction, onDismiss }: Props) {
  if (!error) return null;

  return (
    <div className="error-overlay" role="alert">
      <div className="error-overlay-content">
        <div className="error-overlay-header">
          <span className="error-overlay-icon">\u26A0</span>
          <div className="error-overlay-info">
            <span className="error-overlay-title">Something went wrong</span>
            {failedStep && (
              <span className="error-overlay-where">
                Failed at: <strong>{failedStep}</strong>
              </span>
            )}
          </div>
          <button type="button" className="error-overlay-dismiss" onClick={onDismiss} aria-label="Dismiss">
            \u2715
          </button>
        </div>
        <div className="error-overlay-msg">{error}</div>
        {recoveryAction && (
          <div className="error-overlay-action">
            <span className="error-overlay-action-label">What to do:</span>
            <span className="error-overlay-action-text">{recoveryAction}</span>
          </div>
        )}
      </div>
    </div>
  );
}

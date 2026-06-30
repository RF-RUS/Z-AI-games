import CopyButton from "../shared/CopyButton";

interface Props {
  error: string | null;
  diagnostics: Record<string, unknown> | null;
}

export default function AttachDiagnostics({ error, diagnostics }: Props) {
  if (!error && !diagnostics) return null;

  return (
    <div className="attach-diagnostics">
      {error && (
        <div className="attach-error-msg">
          <span className="attach-error-label">Error:</span>
          <span className="attach-error-text">{error}</span>
          <CopyButton text={error} />
        </div>
      )}
      {diagnostics && (
        <details className="attach-diagnostics-details">
          <summary>Diagnostics payload</summary>
          <pre className="attach-diagnostics-json">{JSON.stringify(diagnostics, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}

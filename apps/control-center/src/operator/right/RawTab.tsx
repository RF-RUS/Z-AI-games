interface Props {
  observation: Record<string, unknown> | null;
  traceMeta: Record<string, unknown> | null;
}

export default function RawTab({ observation, traceMeta }: Props) {
  return (
    <div className="tab-content">
      <details className="raw-section">
        <summary>Raw Observation</summary>
        {observation ? (
          <pre className="raw-json">{JSON.stringify(observation, null, 2)}</pre>
        ) : (
          <p className="raw-empty">No observation data</p>
        )}
      </details>
      <details className="raw-section">
        <summary>Trace Metadata</summary>
        {traceMeta ? (
          <pre className="raw-json">{JSON.stringify(traceMeta, null, 2)}</pre>
        ) : (
          <p className="raw-empty">No trace metadata</p>
        )}
      </details>
    </div>
  );
}

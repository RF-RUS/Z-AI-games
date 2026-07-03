import { useEffect, useMemo, useState } from "react";

type ReplaySummary = { replay_id: string; game_id: string; session_id: string; event_count: number };
type ReplayDetail = {
  replay_id: string;
  game_id: string;
  session_id: string;
  events: Array<{ event_id: string; event_type: string; sequence: number; correlation_id?: string; payload: Record<string, unknown> }>;
  artifacts: Array<{ artifact_id: string; artifact_type: string; path?: string; correlation_id?: string; observation_id?: string; metadata?: Record<string, string> }>;
  observations: Array<{
    observation_id: string;
    correlation_id?: string;
    screenshot?: { path?: string; data_base64?: string };
    observation?: { confidence?: { overall: number }; discrepancies?: Array<{ field: string; severity: string }> };
    dom_snapshot?: { url?: string };
    window_snapshot?: { window_title?: string; backend?: string; extracted?: Record<string, unknown> };
  }>;
  metadata: Record<string, unknown>;
};

export default function ReplayViewer() {
  const [replays, setReplays] = useState<ReplaySummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReplayDetail | null>(null);
  const [eventFilter, setEventFilter] = useState("");
  const [corrFilter, setCorrFilter] = useState("");
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const [thumbnails, setThumbnails] = useState<Record<string, string>>({});

  useEffect(() => {
    window.unoApi?.listReplays().then((r) => setReplays(r as ReplaySummary[])).catch(() => setReplays([]));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    window.unoApi?.getReplayDetail(selectedId).then((r) => setDetail(r as ReplayDetail | null)).catch(() => setDetail(null));
  }, [selectedId]);

  useEffect(() => {
    if (!detail) return;
    const load = async () => {
      const thumbs: Record<string, string> = {};
      for (const a of detail.artifacts) {
        if (a.artifact_type !== "screenshot" || !a.path) continue;
        const obs = detail.observations.find((o) => o.screenshot?.data_base64);
        if (obs?.screenshot?.data_base64) {
          thumbs[a.artifact_id] = `data:image/png;base64,${obs.screenshot.data_base64}`;
        } else if (window.unoApi?.readLocalImage) {
          const data = window.unoApi.readLocalImage(a.path) as string | null;
          if (data) thumbs[a.artifact_id] = data;
        }
      }
      for (const o of detail.observations) {
        if (o.screenshot?.data_base64) {
          thumbs[o.observation_id] = `data:image/png;base64,${o.screenshot.data_base64}`;
        } else if (o.screenshot?.path && window.unoApi?.readLocalImage) {
          const data = window.unoApi.readLocalImage(o.screenshot.path) as string | null;
          if (data) thumbs[o.observation_id] = data;
        }
      }
      setThumbnails(thumbs);
    };
    load();
  }, [detail]);

  const filteredEvents = useMemo(() => {
    if (!detail) return [];
    return detail.events.filter((e) => {
      if (eventFilter && !e.event_type.includes(eventFilter)) return false;
      if (corrFilter && e.correlation_id !== corrFilter) return false;
      return true;
    });
  }, [detail, eventFilter, corrFilter]);

  const screenshotArtifacts = detail?.artifacts.filter((a) => a.artifact_type === "screenshot") ?? [];

  return (
    <section className="panel replay-viewer">
      <h2>Replay Viewer</h2>
      <div className="replay-layout">
        <aside className="card replay-list">
          <h3>Replays</h3>
          {replays.length === 0 && <p className="muted">No replays. Import via state-replay-service.</p>}
          <ul>
            {replays.map((r) => (
              <li key={r.replay_id}>
                <button type="button" className={selectedId === r.replay_id ? "active" : ""} onClick={() => setSelectedId(r.replay_id)}>
                  {r.replay_id} <span className="muted">({r.event_count} events)</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <div className="replay-detail">
          {detail ? (
            <>
              <div className="card filters">
                <label>Event type filter <input value={eventFilter} onChange={(e) => setEventFilter(e.target.value)} placeholder="card_played" /></label>
                <label>Correlation ID <input value={corrFilter} onChange={(e) => setCorrFilter(e.target.value)} /></label>
              </div>

              <div className="card">
                <h3>Timeline — Events ({filteredEvents.length})</h3>
                <ol className="timeline">
                  {filteredEvents.map((e) => (
                    <li key={e.event_id}>
                      <strong>#{e.sequence}</strong> {e.event_type}
                      {e.correlation_id && <em> [{e.correlation_id}]</em>}
                      <pre>{JSON.stringify(e.payload, null, 0)}</pre>
                    </li>
                  ))}
                </ol>
              </div>

              <div className="card">
                <h3>Observations ({detail.observations.length})</h3>
                {detail.observations.map((o) => (
                  <div key={o.observation_id} className="obs-row">
                    <span>{o.observation_id}</span>
                    {o.window_snapshot && (
                      <span className="muted">windows: {o.window_snapshot.window_title} [{o.window_snapshot.backend}]</span>
                    )}
                    {o.dom_snapshot?.url && <span className="muted">web: {o.dom_snapshot.url}</span>}
                    {o.observation?.confidence && <span>conf: {o.observation.confidence.overall}</span>}
                    {thumbnails[o.observation_id] && (
                      <button type="button" className="thumb-btn" onClick={() => setPreviewSrc(thumbnails[o.observation_id])}>
                        <img src={thumbnails[o.observation_id]} alt="observation" className="thumb" />
                      </button>
                    )}
                  </div>
                ))}
              </div>

              <div className="card">
                <h3>Artifacts ({detail.artifacts.length})</h3>
                <div className="artifact-grid">
                  {screenshotArtifacts.map((a) => (
                    <div key={a.artifact_id} className="artifact-item">
                      {thumbnails[a.artifact_id] ? (
                        <button type="button" className="thumb-btn" onClick={() => setPreviewSrc(thumbnails[a.artifact_id])}>
                          <img src={thumbnails[a.artifact_id]} alt={a.artifact_id} className="thumb" />
                        </button>
                      ) : (
                        <span className="muted">{a.path || a.artifact_id}</span>
                      )}
                      <small>{a.artifact_type}</small>
                    </div>
                  ))}
                </div>
                {detail.artifacts.filter((a) => a.artifact_type !== "screenshot").map((a) => (
                  <div key={a.artifact_id} className="muted">{a.artifact_type} — {a.path || a.artifact_id}</div>
                ))}
              </div>
            </>
          ) : (
            <p className="muted">Select a replay to view timeline.</p>
          )}
        </div>
      </div>

      {previewSrc && (
        <div className="modal-overlay" onClick={() => setPreviewSrc(null)} role="presentation">
          <div className="modal-content" onClick={(e) => e.stopPropagation()} role="dialog">
            <button type="button" className="modal-close" onClick={() => setPreviewSrc(null)}>Close</button>
            <img src={previewSrc} alt="Screenshot preview" className="preview-full" />
          </div>
        </div>
      )}
    </section>
  );
}

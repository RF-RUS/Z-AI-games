import { useState } from "react";
import { OperatorEvent } from "./operatorStore";

interface EvidenceData {
  screenshotPath?: string | null;
  timestamp?: number;
  adapterType?: string;
  gameType?: string;
  confidence?: number;
  sources?: string[];
  observation?: Record<string, unknown>;
  beforeAction?: string | null;
  afterAction?: string | null;
}

interface Props {
  evidence: EvidenceData | null;
  events: OperatorEvent[];
}

function formatConfidence(confidence?: number): { label: string; color: string } {
  if (confidence === undefined) return { label: "Unknown", color: "#9e9e9e" };
  if (confidence >= 0.8) return { label: "High", color: "#4caf50" };
  if (confidence >= 0.5) return { label: "Medium", color: "#ff9800" };
  return { label: "Low", color: "#f44336" };
}

function formatTimestamp(ts?: number): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function EvidencePanel({ evidence, events }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  const recentEvents = events.filter((e) =>
    ["observe", "perceive", "decision", "action"].includes(e.type),
  ).slice(-5);

  return (
    <div className="evidence-panel">
      <h3>Evidence</h3>

      {!evidence ? (
        <p className="muted">No evidence captured yet.</p>
      ) : (
        <>
          <div className="evidence-meta">
            <div className="evidence-meta-row">
              <span className="evidence-label">Time</span>
              <span className="evidence-value">{formatTimestamp(evidence.timestamp)}</span>
            </div>
            <div className="evidence-meta-row">
              <span className="evidence-label">Adapter</span>
              <span className="evidence-value">{evidence.adapterType ?? "—"}</span>
            </div>
            <div className="evidence-meta-row">
              <span className="evidence-label">Game</span>
              <span className="evidence-value">{evidence.gameType ?? "—"}</span>
            </div>
            <div className="evidence-meta-row">
              <span className="evidence-label">Confidence</span>
              <span
                className="evidence-value confidence-badge"
                style={{ color: formatConfidence(evidence.confidence).color }}
              >
                {formatConfidence(evidence.confidence).label}
                {evidence.confidence !== undefined && (
                  <span className="confidence-raw"> ({Math.round(evidence.confidence * 100)}%)</span>
                )}
              </span>
            </div>
          </div>

          {evidence.sources && evidence.sources.length > 0 && (
            <div className="evidence-sources">
              <span className="evidence-label">Sources</span>
              <div className="source-chips">
                {evidence.sources.map((src) => (
                  <span key={src} className="source-chip">{src}</span>
                ))}
              </div>
            </div>
          )}

          {evidence.screenshotPath && (
            <div className="evidence-screenshot">
              <img
                src={`file://${evidence.screenshotPath}`}
                alt="Agent view"
                className="screenshot-thumb"
                onClick={() => setSelectedImage(evidence.screenshotPath!)}
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
              <p className="screenshot-hint">Click to enlarge</p>
            </div>
          )}

          {evidence.observation && (
            <button
              type="button"
              className="evidence-expand-btn"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? "Hide details" : "Show observation details"}
            </button>
          )}

          {expanded && evidence.observation && (
            <div className="evidence-details">
              <pre>{JSON.stringify(evidence.observation, null, 2)}</pre>
            </div>
          )}

          {recentEvents.length > 0 && (
            <div className="evidence-timeline">
              <h4>Recent Activity</h4>
              {recentEvents.map((evt) => (
                <div key={evt.id} className={`timeline-entry ${evt.success === false ? "timeline-fail" : ""}`}>
                  <span className="timeline-type">{evt.type}</span>
                  <span className="timeline-msg">{evt.message}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {selectedImage && (
        <div className="image-modal" onClick={() => setSelectedImage(null)}>
          <div className="image-modal-content" onClick={(e) => e.stopPropagation()}>
            <img src={`file://${selectedImage}`} alt="Full preview" className="image-modal-img" />
            <button type="button" className="image-modal-close" onClick={() => setSelectedImage(null)}>
              ×
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

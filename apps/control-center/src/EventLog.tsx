import { FlowStep } from "./unoApiClient";
import { OperatorEvent } from "./operatorStore";

interface Props {
  events: OperatorEvent[];
  steps: FlowStep[];
  onStepClick?: (stepName: string) => void;
  highlightStep?: string | null;
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const STEP_COLORS: Record<string, string> = {
  observe: "#2196F3",
  perceive: "#9C27B0",
  decide: "#FF9800",
  execute: "#4CAF50",
  guard: "#F44336",
  legal_actions: "#607D8B",
  record: "#795548",
};

export default function EventLog({ events, steps, onStepClick, highlightStep }: Props) {
  // Merge steps (primary) and events (secondary) into a timeline
  const entries: Array<{
    ts: number;
    text: string;
    ok?: boolean;
    stepName?: string;
    ms?: number;
    isEvent?: boolean;
  }> = [];

  // Add steps as primary entries
  for (const step of steps.slice(-8)) {
    const ts = (step as unknown as { timestamp_ms?: number }).timestamp_ms ?? Date.now();
    entries.push({
      ts,
      text: step.result.success
        ? `${step.step_name} completed`
        : `${step.step_name} failed: ${step.result.error ?? "unknown error"}`,
      ok: step.result.success,
      stepName: step.step_name,
      ms: step.result.latency_ms,
    });
  }

  // Add recent events as context (avoid duplicates)
  const existingTexts = new Set(entries.map(e => e.text));
  for (const evt of events.slice(-5)) {
    if (!existingTexts.has(evt.message) && entries.length < 12) {
      entries.push({
        ts: evt.ts,
        text: evt.message,
        ok: evt.success,
        isEvent: true,
      });
    }
  }

  entries.sort((a, b) => b.ts - a.ts);
  const recent = entries.slice(0, 10);

  return (
    <div className="event-log">
      <div className="event-log-header">
        <span className="event-log-title">Event Log</span>
      </div>
      <div className="event-log-entries">
        {recent.length === 0 && (
          <div className="event-log-empty">No events yet</div>
        )}
        {recent.map((entry, i) => (
          <div
            key={i}
            className={[
              "event-entry",
              entry.ok === false && "event-entry-fail",
              entry.ok === true && "event-entry-ok",
              entry.stepName && highlightStep === entry.stepName && "event-entry-highlight",
            ].filter(Boolean).join(" ")}
            onClick={entry.stepName && onStepClick ? () => onStepClick(entry.stepName!) : undefined}
          >
            {entry.stepName && (
              <span
                className="event-dot"
                style={{ backgroundColor: STEP_COLORS[entry.stepName] || "#666" }}
              />
            )}
            <span className="event-text">{entry.text}</span>
            {entry.ms != null && entry.ms > 0 && (
              <span className="event-latency">
                {entry.ms >= 1000 ? `${(entry.ms / 1000).toFixed(1)}s` : `${entry.ms}ms`}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

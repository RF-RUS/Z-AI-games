import { FlowStep } from "../../unoApiClient";
import { OperatorEvent } from "../../operatorStore";

interface Props {
  events: OperatorEvent[];
  steps: FlowStep[];
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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

export default function EventLog({ events, steps }: Props) {
  const entries: Array<{ ts: number; text: string; ok?: boolean; stepName?: string }> = [];

  for (const step of steps.slice(-8)) {
    const ts = (step as unknown as { timestamp_ms?: number }).timestamp_ms ?? Date.now();
    entries.push({
      ts,
      text: step.result.success ? `${step.step_name} completed` : `${step.step_name} failed: ${step.result.error ?? "unknown"}`,
      ok: step.result.success,
      stepName: step.step_name,
    });
  }

  const recent = entries.sort((a, b) => b.ts - a.ts).slice(0, 10);

  return (
    <div className="event-log">
      {recent.length === 0 && <p className="event-log-empty">No events yet</p>}
      {recent.map((entry, i) => (
        <div key={i} className={`event-entry ${entry.ok === false ? "event-fail" : ""}`}>
          {entry.stepName && (
            <span className="event-dot" style={{ backgroundColor: STEP_COLORS[entry.stepName] || "#666" }} />
          )}
          <span className="event-text">{entry.text}</span>
        </div>
      ))}
    </div>
  );
}

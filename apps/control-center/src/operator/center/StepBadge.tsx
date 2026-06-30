interface Props {
  stepNum: number | null;
  phase: string | null;
  timestamp: number | null;
}

const PHASE_LABELS: Record<string, string> = {
  observe: "Observe",
  perceive: "Perceive",
  execute: "Execute",
};

export default function StepBadge({ stepNum, phase, timestamp }: Props) {
  if (stepNum == null) return null;

  const phaseLabel = phase ? (PHASE_LABELS[phase] || phase) : "";
  const time = timestamp ? new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";

  return (
    <div className="step-badge">
      {phaseLabel && <span className="step-badge-phase">{phaseLabel}</span>}
      <span className="step-badge-num">Step {stepNum}</span>
      {time && <span className="step-badge-time">{time}</span>}
    </div>
  );
}

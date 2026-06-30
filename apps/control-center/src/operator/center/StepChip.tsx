interface Props {
  stepNum: number;
  phase: string;
  isSelected: boolean;
  success: boolean | null;
  onClick: () => void;
}

const PHASE_COLORS: Record<string, string> = {
  observe: "#2196F3",
  perceive: "#9C27B0",
  execute: "#FF9800",
};

const PHASE_ABBR: Record<string, string> = {
  observe: "Ob",
  perceive: "Pe",
  execute: "Ex",
};

export default function StepChip({ stepNum, phase, isSelected, success, onClick }: Props) {
  const color = success === false ? "#f44336" : success === true ? "#4caf50" : PHASE_COLORS[phase] || "#666";

  return (
    <button
      type="button"
      className={`step-chip ${isSelected ? "step-chip-selected" : ""} ${success === false ? "step-chip-fail" : ""}`}
      onClick={onClick}
      title={`Step ${stepNum}: ${phase}${success === false ? " (failed)" : success === true ? " (ok)" : ""}`}
    >
      <span className="step-dot" style={{ backgroundColor: color }} />
      <span className="step-num">{stepNum}</span>
      <span className="step-phase">{PHASE_ABBR[phase] || phase.slice(0, 3)}</span>
    </button>
  );
}

interface Props {
  phase: string | null;
}

const PHASE_LABELS: Record<string, string> = {
  observe: "Observe",
  perceive: "Perceive",
  decide: "Decide",
  execute: "Execute",
  legal_actions: "Legal Actions",
  guard: "Guard",
  record: "Record",
};

export default function PhaseLabel({ phase }: Props) {
  if (!phase || phase === "idle") return null;

  const label = PHASE_LABELS[phase] || phase;
  return <span className="phase-label">{label}</span>;
}

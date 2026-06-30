interface Props {
  flowState: string;
}

const FLOW_COLORS: Record<string, string> = {
  active: "#4caf50",
  idle: "#666",
  paused: "#ff9800",
  error: "#f44336",
  attaching: "#2196f3",
};

const FLOW_LABELS: Record<string, string> = {
  active: "Playing",
  idle: "Ready",
  paused: "Paused",
  error: "Error",
  attaching: "Connecting",
};

export default function FlowStateBadge({ flowState }: Props) {
  const color = FLOW_COLORS[flowState] || "#666";
  const label = FLOW_LABELS[flowState] || flowState;

  return (
    <span className="flow-state-badge" style={{ backgroundColor: color }}>
      {label}
    </span>
  );
}

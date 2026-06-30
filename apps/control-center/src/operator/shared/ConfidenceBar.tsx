interface Props {
  value: number | null;
  size?: "sm" | "md";
  showLabel?: boolean;
}

function getColor(value: number): string {
  if (value >= 0.8) return "#4caf50";
  if (value >= 0.5) return "#ff9800";
  return "#f44336";
}

export default function ConfidenceBar({ value, size = "md", showLabel = true }: Props) {
  if (value == null) return <span className="confidence-unknown">--</span>;

  const pct = Math.round(value * 100);
  const height = size === "sm" ? 4 : 8;

  return (
    <span className="confidence-bar-wrapper">
      <span
        className="confidence-bar-track"
        style={{ height }}
      >
        <span
          className="confidence-bar-fill"
          style={{ width: `${pct}%`, backgroundColor: getColor(value) }}
        />
      </span>
      {showLabel && <span className="confidence-label" style={{ color: getColor(value) }}>{pct}%</span>}
    </span>
  );
}

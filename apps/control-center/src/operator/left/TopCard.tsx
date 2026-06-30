interface Props {
  color: string;
  value: string;
}

const COLOR_HEX: Record<string, string> = {
  red: "#f44336",
  blue: "#2196f3",
  green: "#4caf50",
  yellow: "#ffeb3b",
  wild: "linear-gradient(135deg, #f44336, #2196f3, #4caf50, #ffeb3b)",
};

export default function TopCard({ color, value }: Props) {
  return (
    <div className="top-card-visual">
      <span
        className="top-card-swatch"
        style={{ background: COLOR_HEX[color] || "#999" }}
      />
      <span className="top-card-value">{value}</span>
    </div>
  );
}

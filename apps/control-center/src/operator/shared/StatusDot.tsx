interface Props {
  status: "healthy" | "degraded" | "error" | "offline";
  size?: number;
  tooltip?: string;
}

const COLORS: Record<string, string> = {
  healthy: "#4caf50",
  degraded: "#ff9800",
  error: "#f44336",
  offline: "#666",
};

export default function StatusDot({ status, size = 10, tooltip }: Props) {
  return (
    <span
      className="status-dot"
      style={{ backgroundColor: COLORS[status] || "#666", width: size, height: size }}
      title={tooltip || status}
    />
  );
}

interface Props {
  state: "in_game" | "lobby" | "menu" | "unknown";
}

const STATE_CONFIG: Record<string, { label: string; color: string }> = {
  in_game: { label: "In Game", color: "#4caf50" },
  lobby: { label: "Lobby", color: "#ff9800" },
  menu: { label: "Menu", color: "#2196f3" },
  unknown: { label: "Unknown", color: "#666" },
};

export default function ScreenStateBadge({ state }: Props) {
  const config = STATE_CONFIG[state] || STATE_CONFIG.unknown;

  return (
    <span className="screen-state-badge" style={{ color: config.color }}>
      {config.label}
    </span>
  );
}

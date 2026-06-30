interface Card {
  color: string;
  value: string;
}

interface Props {
  cards: Card[];
  maxVisible?: number;
}

const COLOR_HEX: Record<string, string> = {
  red: "#f44336",
  blue: "#2196f3",
  green: "#4caf50",
  yellow: "#ffeb3b",
};

export default function HandCards({ cards, maxVisible = 7 }: Props) {
  if (cards.length === 0) return null;

  const visible = cards.slice(0, maxVisible);
  const remaining = cards.length - maxVisible;

  return (
    <div className="hand-cards-row" role="list" aria-label={`Hand: ${cards.length} cards`}>
      {visible.map((card, i) => (
        <span
          key={i}
          className="hand-pill"
          style={{ backgroundColor: COLOR_HEX[card.color] || "#999" }}
          role="listitem"
          title={`${card.color} ${card.value}`}
        >
          {card.value.slice(0, 2)}
        </span>
      ))}
      {remaining > 0 && (
        <span className="hand-pill hand-pill-overflow">+{remaining}</span>
      )}
    </div>
  );
}

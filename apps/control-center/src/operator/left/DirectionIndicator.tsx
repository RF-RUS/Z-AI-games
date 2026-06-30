interface Props {
  direction: 1 | -1;
}

export default function DirectionIndicator({ direction }: Props) {
  return (
    <div className="direction-indicator">
      <span className="direction-arrow">{direction === 1 ? "\u2192" : "\u2190"}</span>
      <span className="direction-label">{direction === 1 ? "CW" : "CCW"}</span>
    </div>
  );
}
